# tests/test_theme.py
"""
gui/theme.py の disable_scroll_value_change() のテスト。

QSpinBox/QDoubleSpinBox/QComboBoxは既定でマウスホイールにより値が変わって
しまうため、ホイール操作による値変更を常に無効化する挙動を検証する。
(フォーカスの有無で条件分岐する実装は一度試したが、QAbstractSpinBoxの既定の
フォーカスポリシーがWheelFocusであるため実際には効果がなく、無条件に
無効化する方式に変更した経緯がある)
"""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QMainWindow, QWidget, QVBoxLayout

from gui import theme


def _make_wheel_event():
    return QWheelEvent(
        QPointF(1, 1), QPointF(1, 1), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_wheel_does_not_change_spinbox_value(qapp):
    theme.disable_scroll_value_change()

    spin = QDoubleSpinBox()
    spin.setValue(5.0)
    QApplication.sendEvent(spin, _make_wheel_event())

    assert spin.value() == 5.0


def test_wheel_does_not_change_value_even_when_focused(qapp):
    # フォーカスの有無に関わらず無効化されることを確認する。
    # (実際のフォームでは、直前に触っていた別のフィールドがフォーカスを
    #  保持したまま、ユーザーはマウスを動かしてスクロールするだけのことが
    #  多いため、フォーカスの有無では判定しない設計にしている)
    theme.disable_scroll_value_change()

    win = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    spin = QDoubleSpinBox()
    spin.setValue(5.0)
    layout.addWidget(spin)
    win.setCentralWidget(central)
    win.show()
    qapp.processEvents()

    assert spin.hasFocus()  # 唯一のフォーカス可能ウィジェットなので自動的にフォーカスされる
    QApplication.sendEvent(spin, _make_wheel_event())

    assert spin.value() == 5.0
    win.close()


def test_wheel_does_not_change_combobox_selection(qapp):
    theme.disable_scroll_value_change()

    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    combo.setCurrentIndex(0)
    QApplication.sendEvent(combo, _make_wheel_event())

    assert combo.currentIndex() == 0


def test_disable_scroll_value_change_is_idempotent(qapp):
    # 複数回呼び出してもwheelEventが二重にラップされない
    theme.disable_scroll_value_change()
    theme.disable_scroll_value_change()

    spin = QDoubleSpinBox()
    spin.setValue(1.0)
    QApplication.sendEvent(spin, _make_wheel_event())
    assert spin.value() == 1.0
