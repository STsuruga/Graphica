"""起動中の Graphica にファイルを渡す(ファイルをダブルクリックしたとき、新しいウィンドウではなく新しいタブで開くため)。

最初に起動したものがローカルサーバーを開き、あとから起動したものはそこへパスを送って終わる。起動画面より前に使うので、
ここでは PySide6 だけを読む。
"""
import getpass
import json
import logging
import os
import re

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

# 起動中のアプリがほかの受け渡しを処理している間は待たされることがある
_CONNECT_TIMEOUT_MS = 2000
_WRITE_TIMEOUT_MS = 1000


def server_name():
    """利用者ごとに別の名前(同じ PC の別の利用者のアプリには渡さない)。"""
    try:
        user = getpass.getuser()
    except (OSError, KeyError, ImportError):  # 利用者名が取れない環境でも起動は止めない
        user = "user"
    return "Graphica-" + re.sub(r"[^A-Za-z0-9_.-]", "_", user)


def files_to_open(argv):
    """起動の引数のうち、開くファイル(オプション以外で、実在するもの)。"""
    return [os.path.abspath(arg) for arg in argv[1:] if not arg.startswith("-") and os.path.isfile(arg)]


def instance_running(name=None):
    """ほかの Graphica が受け渡しの窓口を開いているか。"""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    running = socket.waitForConnected(_CONNECT_TIMEOUT_MS)
    if running:
        socket.disconnectFromServer()
    return running


def send_to_running_instance(paths, name=None):
    """起動中のアプリがあればパスを渡して True。無ければ False(自分が起動を続ける)。"""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(_CONNECT_TIMEOUT_MS):
        return False
    socket.write((json.dumps({"open": list(paths)}) + "\n").encode("utf-8"))
    socket.flush()
    # Windows のパイプは書き込みが後から終わる。切断が済むまで待たないと、すぐ終わるこのプロセスと一緒に消える
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(_WRITE_TIMEOUT_MS)
    return socket.state() == QLocalSocket.LocalSocketState.UnconnectedState and socket.bytesToWrite() == 0


class InstanceServer(QObject):
    """あとから起動したアプリが送ってきたパスを open_requested で知らせる。"""

    open_requested = Signal(list)

    def __init__(self, name=None, parent=None):
        super().__init__(parent)
        self._name = name or server_name()
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._buffers = {}

    def listen(self):
        """開けなければ False。前回の異常終了で残った名前(Unix のソケットファイル)は消して開き直す。"""
        if self._server.listen(self._name):
            return True
        QLocalServer.removeServer(self._name)
        if self._server.listen(self._name):
            return True
        logger.warning("起動中のアプリへのファイルの受け渡しを開けませんでした: %s", self._server.errorString())
        return False

    def close(self):
        self._server.close()

    def _on_new_connection(self):
        # 接続を掴むラムダは使わない(接続が消えたあとに呼ばれると落ちる)。送り手は sender() で引く
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._buffers[socket] = b""
            socket.readyRead.connect(self._on_ready_read)
            socket.disconnected.connect(self._on_disconnected)

    def _on_ready_read(self):
        socket = self.sender()
        if socket is None:
            return
        self._buffers[socket] = self._buffers.get(socket, b"") + bytes(socket.readAll())
        self._emit_complete_lines(socket)

    def _on_disconnected(self):
        socket = self.sender()
        if socket is None:
            return
        self._buffers[socket] = self._buffers.get(socket, b"") + bytes(socket.readAll())
        self._emit_complete_lines(socket, final=True)
        self._buffers.pop(socket, None)
        socket.deleteLater()

    def _emit_complete_lines(self, socket, final=False):
        data = self._buffers.get(socket, b"")
        *lines, rest = data.split(b"\n")
        if final and rest:
            lines.append(rest)
            rest = b""
        self._buffers[socket] = rest
        for line in lines:
            if not line.strip():
                continue
            try:
                paths = json.loads(line.decode("utf-8")).get("open", [])
            except (ValueError, AttributeError):
                logger.warning("起動中のアプリへの受け渡しの中身が読めませんでした: %r", line[:200])
                continue
            paths = [p for p in paths if isinstance(p, str)]
            if paths:
                self.open_requested.emit(paths)


class FileOpenEventFilter(QObject):
    """macOS で Finder から開いたファイル(QFileOpenEvent。起動中でも届く)を open_requested で知らせる。"""

    open_requested = Signal(list)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if path:
                self.open_requested.emit([path])
            return True
        return super().eventFilter(watched, event)
