"""幅に収まらない文字を「…」で省くラベル。データセット名のように長さの決まらない文字で、親の幅を広げない。"""
from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    """text() は省く前の全文を返す(翻訳・テスト・記録はそのまま使える)。省いたときだけ全文をツールチップに出す。"""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        # 余裕があれば全文の幅、足りなければ 0 まで縮む(最小の幅は minimumSizeHint で主張しない)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text):
        self._full_text = text or ""
        self._elide()

    def text(self):
        return self._full_text

    def sizeHint(self):
        hint = super().sizeHint()
        margins = self.contentsMargins()
        width = self.fontMetrics().horizontalAdvance(self._full_text) + margins.left() + margins.right() + 2
        return QSize(width, hint.height())

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        # QSS で太字・大きさが変わると、同じ幅に入る文字数が変わる
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._elide()

    def _elide(self):
        width = self.contentsRect().width()
        shown = self._full_text if width <= 0 else self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, width)
        super().setText(shown)
        super().setToolTip(self._full_text if shown != self._full_text else "")
