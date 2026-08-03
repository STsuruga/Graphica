# tests/test_color_picker_widget.py
"""gui/color_picker_widget.py の ColorPickerWidget に対するテスト(項目65)。

QColorDialogを実際に開く経路(スウォッチボタンのクリック)はテスト対象外とし、
プログラム的な色更新(set_color)とカラーコード欄への直接入力(_on_hex_edited)の
挙動のみを検証する(QColorDialog.getColor()はモーダルでブロックするため)。
"""
from gui.color_picker_widget import ColorPickerWidget


def test_initial_color():
    widget = ColorPickerWidget(settings=None, initial_color="#112233")
    assert widget.color_name() == "#112233"
    assert widget.hex_edit.text() == "#112233"


def test_set_color_updates_display_without_emitting_signal():
    widget = ColorPickerWidget(settings=None, initial_color="#000000")
    received = []
    widget.colorChanged.connect(lambda c: received.append(c))

    widget.set_color("#ff0000")

    assert widget.color_name() == "#ff0000"
    assert widget.hex_edit.text() == "#ff0000"
    assert received == []  # set_color() はプログラム的な更新であり、シグナルは発火しない


def test_set_color_ignores_invalid_input():
    widget = ColorPickerWidget(settings=None, initial_color="#123456")
    widget.set_color("not-a-color")
    assert widget.color_name() == "#123456"


def test_hex_edit_valid_input_updates_color_and_emits_signal():
    widget = ColorPickerWidget(settings=None, initial_color="#000000")
    received = []
    widget.colorChanged.connect(lambda c: received.append(c))

    widget.hex_edit.setText("#00ff00")
    widget._on_hex_edited()

    assert widget.color_name() == "#00ff00"
    assert received == ["#00ff00"]


def test_hex_edit_invalid_input_reverts_to_current_color():
    widget = ColorPickerWidget(settings=None, initial_color="#123456")
    received = []
    widget.colorChanged.connect(lambda c: received.append(c))

    widget.hex_edit.setText("not-a-color")
    widget._on_hex_edited()

    assert widget.color_name() == "#123456"
    assert widget.hex_edit.text() == "#123456"
    assert received == []


def test_hex_edit_same_color_does_not_emit_signal():
    widget = ColorPickerWidget(settings=None, initial_color="#123456")
    received = []
    widget.colorChanged.connect(lambda c: received.append(c))

    widget.hex_edit.setText("#123456")
    widget._on_hex_edited()

    assert received == []


def test_block_signals_propagates_to_children():
    """dataset_mixin.py の「UI一括更新中はシグナルを止める」パターンで使われるため、
    親のblockSignals()呼び出しが内部のswatch/hex_edit両方に伝播する必要がある。"""
    widget = ColorPickerWidget(settings=None, initial_color="#123456")
    widget.blockSignals(True)
    assert widget.swatch_button.signalsBlocked() is True
    assert widget.hex_edit.signalsBlocked() is True
    widget.blockSignals(False)
    assert widget.swatch_button.signalsBlocked() is False
    assert widget.hex_edit.signalsBlocked() is False
