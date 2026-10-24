"""プラグインのパネルの部品(graphica.plugin.ui、プラグイン API 2.2)。"""
import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QLineEdit

from graphica.gui import theme
from graphica.plugin import ui


def test_a_section_gives_a_form_and_folds_while_its_switch_is_off(qapp):
    switch = QCheckBox("前処理")
    box, form = ui.section("前処理", switch=switch)
    form.addRow("窓の幅", QLineEdit())
    box.show()
    assert form.rowCount() == 1
    assert switch.property(theme.TOGGLE_SWITCH_PROPERTY)
    body = form.parentWidget()
    assert body.isHidden()
    switch.click()
    assert not body.isHidden()
    box.close()


def test_make_switch_keeps_the_checkbox(qapp):
    checkbox = QCheckBox("x")
    assert ui.make_switch(checkbox) is checkbox
    assert checkbox.property(theme.TOGGLE_SWITCH_PROPERTY)


def test_segmented_control_behaves_like_a_combo(qapp):
    segments = ui.SegmentedControl()
    segments.addItem("線", "line")
    segments.addItem("点", "point")
    seen = []
    segments.currentIndexChanged.connect(seen.append)
    segments.setCurrentIndex(segments.findData("point"))
    assert segments.currentData() == "point" and seen == [1]


def test_theme_color_follows_the_theme_and_rejects_unknown_names(qapp):
    assert QColor(ui.theme_color("accent")).isValid()
    assert ui.theme_color("surface") == theme.current_tokens()["surface"]
    with pytest.raises(ValueError):
        ui.theme_color("not_a_color")


def test_show_toast_puts_a_message_on_the_window(qapp):
    from PySide6.QtWidgets import QWidget
    window = QWidget()
    window.resize(300, 200)
    window.show()
    ui.show_toast(window, "書き出しました")
    assert window._toast.text() == "書き出しました"
    window.close()
