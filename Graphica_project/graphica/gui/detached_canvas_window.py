"""切り離したキャンバスを入れるだけの独立したウィンドウ。

self.canvas は親を替えるだけで同じオブジェクトのまま。閉じられても破棄せず closed で知らせ、戻す処理は
PlotterApp._reattach_canvas() に任せる(「元に戻す」と×ボタンが同じ後処理を通るように)。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMainWindow


class DetachedCanvasWindow(QMainWindow):
    closed = Signal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # parent があっても、埋め込みではなく独立したウィンドウにする
        self.setWindowFlag(Qt.WindowType.Window, True)

    def closeEvent(self, event):
        """破棄せずに closed を出すだけ(キャンバスを抱えたまま破棄すると、戻す前にキャンバスごと消える)。"""
        event.accept()
        self.closed.emit()
