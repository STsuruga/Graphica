"""欄と値の対応表(gui/binding.py)。画面を組み立てずに、欄だけを持つ持ち主で確かめる。"""
import pytest
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit

from graphica.gui.binding import Binder, check, choice, item_data, number, shown_text, text


class _Owner:
    def __init__(self):
        self.calls = []
        self.title = QLineEdit()
        self.flag = QCheckBox()
        self.size = QDoubleSpinBox()
        self.size.setRange(0.0, 10.0)
        self.size.setDecimals(1)
        self.where = QComboBox()
        self.where.addItem("右", "right")
        self.where.addItem("左", "left")
        self.unit = QComboBox()
        self.unit.addItems(["なし", "nm", "eV"])
        self.direction = QComboBox()
        self.direction.addItems(["out", "in"])

    def changed(self, *_args):
        self.calls.append("changed")

    def also(self, *_args):
        self.calls.append("also")


def _binder(owner):
    return Binder(owner, (
        text("title", "title", ("changed",)),
        check("flag", "flag", ("changed", "also")),
        number("size", "size", ("changed",)),
        item_data("where", "where", ("changed",)),
        choice("unit", "unit", ["none", "nm", "eV"], ("changed",)),
        shown_text("direction", "direction", ("also",)),
    ))


def test_restore_then_gather_round_trip_in_table_order():
    owner = _Owner()
    binder = _binder(owner)
    values = {"title": "T", "flag": True, "size": 3.14, "where": "left", "unit": "eV", "direction": "in"}
    binder.restore(values.__getitem__)
    assert binder.gather() == {"title": "T", "flag": True, "size": 3.1, "where": "left", "unit": "eV",
                               "direction": "in"}
    assert list(binder.gather()) == ["title", "flag", "size", "where", "unit", "direction"]


def test_unknown_choices_fall_back_to_the_first_item():
    owner = _Owner()
    binder = _binder(owner)
    owner.where.setCurrentIndex(1)
    owner.unit.setCurrentIndex(2)
    binder.restore({"title": "", "flag": False, "size": 99, "where": "middle", "unit": "Hz",
                    "direction": "sideways"}.__getitem__)
    gathered = binder.gather()
    assert (gathered["where"], gathered["unit"], gathered["size"]) == ("right", "none", 10.0)
    # 選べない文字は今の選択のまま
    assert gathered["direction"] == "out"


def test_a_failing_row_leaves_the_earlier_rows_restored():
    owner = _Owner()
    binder = _binder(owner)
    with pytest.raises(TypeError):
        binder.restore({"title": "途中", "flag": True, "size": "abc"}.__getitem__)
    assert owner.title.text() == "途中" and owner.flag.isChecked()


def test_connect_follows_the_slot_order_and_block_signals_silences_every_row():
    owner = _Owner()
    binder = _binder(owner)
    binder.connect()
    owner.flag.setChecked(True)
    owner.direction.setCurrentText("in")
    assert owner.calls == ["changed", "also", "also"]

    owner.calls.clear()
    binder.block_signals(True)
    binder.restore({"title": "x", "flag": False, "size": 1.0, "where": "left", "unit": "nm",
                    "direction": "out"}.__getitem__)
    binder.block_signals(False)
    assert owner.calls == []
