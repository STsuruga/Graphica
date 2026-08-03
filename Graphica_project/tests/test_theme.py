# tests/test_theme.py
"""
gui/theme.py の disable_scroll_value_change() のテスト。

QSpinBox/QDoubleSpinBox/QComboBoxは既定でフォーカスが無くてもマウスホイールで
値が変わってしまうため、フォーカスが無い間はホイール操作を無視するようにする
挙動を検証する。
"""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox

from gui import theme


def _make_wheel_event():
    return QWheelEvent(
        QPointF(1, 1), QPointF(1, 1), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_wheel_does_not_change_value_when_unfocused(qapp):
    theme.disable_scroll_value_change()

    spin = QDoubleSpinBox()
    spin.setValue(5.0)
    spin.wheelEvent(_make_wheel_event())

    assert spin.value() == 5.0


def test_wheel_changes_value_when_focused(qapp):
    theme.disable_scroll_value_change()

    spin = QDoubleSpinBox()
    spin.setValue(5.0)
    spin.show()
    spin.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    spin.wheelEvent(_make_wheel_event())

    assert spin.value() != 5.0
    spin.hide()


def test_combobox_wheel_ignored_when_unfocused(qapp):
    theme.disable_scroll_value_change()

    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    combo.setCurrentIndex(0)
    combo.wheelEvent(_make_wheel_event())

    assert combo.currentIndex() == 0


def test_disable_scroll_value_change_is_idempotent(qapp):
    # 複数回呼び出してもwheelEventが二重にラップされない (無限再帰等を起こさない)
    theme.disable_scroll_value_change()
    theme.disable_scroll_value_change()

    spin = QDoubleSpinBox()
    spin.setValue(1.0)
    spin.wheelEvent(_make_wheel_event())
    assert spin.value() == 1.0
