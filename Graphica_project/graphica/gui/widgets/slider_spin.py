"""スライダー+今のスピンボックス。値の持ち主はスピンボックスのまま(バインディングはそちらを見る)。"""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QHBoxLayout, QSlider, QWidget

SPIN_WIDTH = 56


class SliderSpin(QWidget):
    """spinbox を中に取り込み、左にスライダーを付ける。

    スライダーの範囲(slider_min〜slider_max)はよく使う範囲で、スピンボックスはそれより外の値も受け付ける
    (そのときスライダーは端に止まる)。スピンボックスがシグナルを止めて書き換えられた(バインディングの
    「戻す」)後は、refresh() でスライダーを合わせる。
    """

    def __init__(self, spinbox, slider_min, slider_max, step=None, parent=None):
        super().__init__(parent)
        self.spinbox = spinbox
        # QSpinBox(整数)には decimals() が無い
        self._scale = 10 ** (spinbox.decimals() if hasattr(spinbox, 'decimals') else 0)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setObjectName("slider_spin_slider")
        self.slider.setRange(round(slider_min * self._scale), round(slider_max * self._scale))
        self.slider.setSingleStep(max(1, round((step or spinbox.singleStep()) * self._scale)))
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.slider, 1)
        layout.addWidget(spinbox)
        # 見本どおり、上下の矢印を消した数値だけの小さな欄にする(矢印の分の余白は QSS の sliderValue で外す)
        spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinbox.setProperty("sliderValue", True)
        # 既に表示に使われた部品は、プロパティを変えても QSS を当て直さないと見た目が変わらない
        spinbox.style().unpolish(spinbox)
        spinbox.style().polish(spinbox)
        spinbox.setFixedWidth(SPIN_WIDTH)
        self.slider.valueChanged.connect(self._on_slider_moved)
        spinbox.valueChanged.connect(lambda _value: self.refresh())
        # 行の出し入れは数値の欄(値の持ち主)に対して行われるので、それに合わせてスライダーごと出し入れする
        spinbox.installEventFilter(self)
        self.refresh()

    def eventFilter(self, watched, event):
        if watched is self.spinbox and event.type() in (QEvent.Type.HideToParent, QEvent.Type.ShowToParent):
            self.setVisible(event.type() == QEvent.Type.ShowToParent)
        return super().eventFilter(watched, event)

    def refresh(self):
        blocked = self.slider.blockSignals(True)
        self.slider.setValue(round(self.spinbox.value() * self._scale))
        self.slider.blockSignals(blocked)

    def _on_slider_moved(self, position):
        value = position / self._scale
        if abs(value - self.spinbox.value()) >= 0.5 / self._scale:
            self.spinbox.setValue(value)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.spinbox.setEnabled(enabled)
