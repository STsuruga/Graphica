# gui/detached_canvas_window.py
"""
項目86「マルチモニター対応(Canvasの別ウィンドウ切り離し)」で使う、
既存の self.canvas (MplCanvas) を一時的にホストするだけの、最小限の
独立トップレベルウィンドウ。

★ 設計方針(gui/main_window.py 側の _detach_canvas/_reattach_canvas も参照):
  - self.canvas は「切り離す」操作の前後で同一の Python オブジェクトのまま
    (setParent() で再親付けされるだけ)。gui/main_window.py や各Mixin
    (cursor_mixin, annotation_mixin, layout_edit_mixin, export_mixin など)
    は self.canvas をインスタンス属性として直接参照し続けるため、この
    ウィンドウ自体は「キャンバスの入れ物」以上の機能を持たない
    (PlotterApp本体のような重厚なメニュー/ドック等は不要)。
  - ウィンドウを閉じる操作(OSの×ボタン)は、実際のウィジェット破棄を
    行わずに closed シグナルで呼び出し元(PlotterApp)へ委譲する。
    再アタッチ(キャンバスを元のレイアウトへ戻す)処理は呼び出し元の
    責務とすることで、「メニューの『元に戻す』」と「×ボタン」の
    2経路が同じ後処理に必ず合流するようにしている。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMainWindow


class DetachedCanvasWindow(QMainWindow):
    """
    切り離されたキャンバスをホストする、独立した通常のトップレベルウィンドウ。
    OS標準のウィンドウ移動・リサイズ・最大化がそのまま使えるため、
    サブモニターへドラッグして最大化する、といった操作はQt/OS側の
    標準機能でそのまま実現できる(このクラス側で特別な対応は不要)。
    """

    closed = Signal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # parent を持つ場合でも、埋め込みウィジェットではなく独立した
        # トップレベルウィンドウとして扱われるようにする
        # (gui/main_app_window.py が PlotterApp を埋め込む際に
        #  Qt.WindowType.Widget を明示するのの、ちょうど逆のケース)。
        self.setWindowFlag(Qt.WindowType.Window, True)

    def closeEvent(self, event):
        """
        OSの×ボタンなどで閉じられたときの処理。
        ここではウィジェット自体は破棄せず(まだ self.canvas を抱えたまま
        破棄すると、再アタッチ前にキャンバスごと消えてしまうため)、
        イベントを受理した上で closed シグナルにより呼び出し元へ通知するに
        留める。実際のキャンバスの再親付け・ウィンドウの後始末は
        PlotterApp._reattach_canvas() 側の責務。
        """
        event.accept()
        self.closed.emit()
