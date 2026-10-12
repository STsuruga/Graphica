"""GUI 刷新の見た目の部品(gui/widgets/)と、チェックボックスのスイッチの見た目(theme.make_toggle_switch)。"""
import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QStyle

from graphica.gui import theme
from graphica.gui.widgets import (ColorChipRow, ComboMirror, SectionHeader, SegmentedControl, SliderSpin, StatCard,
                                  TypeTileGroup)


def _line_segment():
    seg = SegmentedControl()
    for style, name in (("-", "solid"), ("--", "dashed"), (":", "dotted"), ("-.", "dashdot")):
        seg.addLineStyleItem(style, data=name)
    return seg


def _linestyle_combo():
    combo = QComboBox()
    for name in ("solid", "dashed", "dotted", "dashdot"):
        combo.addItem(name)
    return combo


# --- SegmentedControl ---

def test_segmented_selects_the_first_item_like_a_combo(qapp):
    seg = SegmentedControl()
    spy = QSignalSpy(seg.currentIndexChanged)
    seg.addItem("シンプル", "lite")
    seg.addItem("詳細", "advanced")
    assert seg.currentIndex() == 0
    assert seg.currentData() == "lite"
    assert spy.count() == 1
    assert seg.count() == 2 and seg.itemText(1) == "詳細" and seg.findData("advanced") == 1
    assert seg.findData("nothing") == -1


def test_segmented_click_changes_the_current_item(qapp):
    seg = _line_segment()
    seg.show()
    spy = QSignalSpy(seg.currentIndexChanged)
    button = seg._group.button(2)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert seg.currentIndex() == 2 and seg.currentData() == "dotted"
    assert spy.count() == 1 and spy.at(0) == [2]
    # 同じものをもう一度押しても知らせない
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert spy.count() == 1
    seg.close()


def test_segmented_can_show_no_selection(qapp):
    seg = _line_segment()
    seg.setCurrentIndex(-1)
    assert seg.currentIndex() == -1
    assert not any(button.isChecked() for button in seg._group.buttons())
    seg.setCurrentIndex(1)
    assert seg._group.button(1).isChecked()


def test_segmented_arrow_keys_move_the_selection(qapp):
    seg = _line_segment()
    for key, expected in ((Qt.Key.Key_Right, 1), (Qt.Key.Key_Right, 2), (Qt.Key.Key_Left, 1),
                          (Qt.Key.Key_Left, 0), (Qt.Key.Key_Left, 0)):
        seg.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
        assert seg.currentIndex() == expected


def test_segmented_respects_blocked_signals(qapp):
    seg = _line_segment()
    spy = QSignalSpy(seg.currentIndexChanged)
    seg.blockSignals(True)
    seg.setCurrentIndex(3)
    seg.blockSignals(False)
    assert spy.count() == 0 and seg.currentIndex() == 3


def test_line_segment_buttons_paint_in_both_themes(qapp):
    seg = _line_segment()
    seg.resize(220, 30)
    for dark in (False, True):
        theme.apply_theme(qapp, dark)
        assert not seg.grab().isNull()
    theme.apply_theme(qapp, False)


# --- ComboMirror: 今のコンボを値の持ち主にしたまま同期する ---

def test_mirror_follows_the_combo_and_writes_back(qapp):
    combo = _linestyle_combo()
    combo.setCurrentIndex(1)
    seg = _line_segment()
    mirror = ComboMirror(seg, combo)
    assert seg.currentData() == "dashed"

    combo_spy = QSignalSpy(combo.currentIndexChanged)
    seg.setCurrentIndex(3)
    assert combo.currentText() == "dashdot"
    assert combo_spy.count() == 1  # コンボのシグナルで、今までどおり値が反映される

    combo.setCurrentIndex(0)
    assert seg.currentData() == "solid"

    # バインディングの「戻す」はコンボのシグナルを止めるので、知らせが来ない。refresh() で合わせる
    combo.blockSignals(True)
    combo.setCurrentIndex(2)
    combo.blockSignals(False)
    assert seg.currentData() == "solid"
    mirror.refresh()
    assert seg.currentData() == "dotted"


def test_mirror_refresh_does_not_write_back_to_the_combo(qapp):
    combo = _linestyle_combo()
    seg = _line_segment()
    mirror = ComboMirror(seg, combo)
    combo_spy = QSignalSpy(combo.currentIndexChanged)
    mirror.refresh()
    assert combo_spy.count() == 0


def test_mirror_matches_by_item_data_first(qapp):
    combo = QComboBox()
    combo.addItem("円", "o")
    combo.addItem("三角(上)", "^")
    seg = SegmentedControl()
    seg.addItem("○", "o")
    seg.addItem("△", "^")
    ComboMirror(seg, combo)
    seg.setCurrentIndex(1)
    assert combo.currentData() == "^"


def test_mirror_shows_nothing_for_a_value_without_a_segment(qapp):
    combo = _linestyle_combo()
    combo.addItem("loosely dotted")
    seg = _line_segment()
    ComboMirror(seg, combo)
    combo.setCurrentIndex(4)
    assert seg.currentIndex() == -1


# --- TypeTileGroup ---

def test_type_tiles_behave_like_a_combo(qapp):
    tiles = TypeTileGroup()
    for glyph, text, value in (("line", "線", "Line"), ("scatter", "点", "Scatter"),
                               ("line_scatter", "線+点", "Line+Marker"), ("bar", "棒", "Bar")):
        tiles.addTile(glyph, text, value)
    assert tiles.count() == 4 and tiles.currentData() == "Line"
    tiles.setCurrentIndex(3)
    assert tiles.currentData() == "Bar"
    tiles.setCurrentIndex(-1)
    assert not any(button.isChecked() for button in tiles._group.buttons())
    tiles.resize(300, 50)
    assert not tiles.grab().isNull()


def test_type_tiles_reject_an_unknown_glyph(qapp):
    with pytest.raises(ValueError):
        TypeTileGroup().addTile("pie", "円", "Pie")


# --- SliderSpin: 値の持ち主は今のスピンボックス ---

def _spin(value=1.5, maximum=20.0):
    spin = QDoubleSpinBox()
    spin.setDecimals(2)
    spin.setRange(0.0, maximum)
    spin.setValue(value)
    return spin


def test_slider_and_spinbox_stay_in_step(qapp):
    spin = _spin()
    widget = SliderSpin(spin, 0.0, 5.0)
    assert widget.slider.value() == 150
    spin_spy = QSignalSpy(spin.valueChanged)
    widget.slider.setValue(275)
    assert spin.value() == pytest.approx(2.75)
    assert spin_spy.count() == 1
    spin.setValue(0.5)
    assert widget.slider.value() == 50


def test_slider_stops_at_its_end_but_the_spinbox_keeps_the_value(qapp):
    spin = _spin()
    widget = SliderSpin(spin, 0.0, 5.0)
    spin.setValue(12.0)
    assert spin.value() == pytest.approx(12.0)
    assert widget.slider.value() == widget.slider.maximum()


def test_slider_refresh_after_a_blocked_restore(qapp):
    spin = _spin()
    widget = SliderSpin(spin, 0.0, 5.0)
    spin.blockSignals(True)
    spin.setValue(4.0)
    spin.blockSignals(False)
    widget.refresh()
    assert widget.slider.value() == 400


def test_slider_spin_hides_the_arrows_and_follows_enabled(qapp):
    spin = _spin()
    widget = SliderSpin(spin, 0.0, 5.0)
    assert spin.buttonSymbols() == QDoubleSpinBox.ButtonSymbols.NoButtons
    assert spin.property("sliderValue") is True
    widget.setEnabled(False)
    assert not spin.isEnabled() and not widget.slider.isEnabled()


# --- スイッチの見た目(チェックボックスのまま) ---

def test_toggle_switch_keeps_the_checkbox_and_its_value(qapp):
    checkbox = QCheckBox()
    assert theme.make_toggle_switch(checkbox) is checkbox
    assert checkbox.property(theme.TOGGLE_SWITCH_PROPERTY) is True
    spy = QSignalSpy(checkbox.toggled)
    checkbox.show()
    QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton, pos=QPoint(8, checkbox.height() // 2))
    assert checkbox.isChecked() and spy.count() == 1
    checkbox.close()


def test_toggle_switch_indicator_size(qapp):
    theme.apply_theme(qapp, False)
    checkbox = theme.make_toggle_switch(QCheckBox())
    style = checkbox.style()
    assert style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, checkbox) == theme.TOGGLE_SWITCH_SIZE[0]
    assert style.pixelMetric(QStyle.PixelMetric.PM_IndicatorHeight, None, checkbox) == theme.TOGGLE_SWITCH_SIZE[1]
    # 普通のチェックボックスは今までの大きさのまま
    plain = QCheckBox()
    assert style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, plain) != theme.TOGGLE_SWITCH_SIZE[0]


def test_only_checkboxes_can_be_toggle_switches(qapp):
    """スイッチかどうかは型を先に確かめる(Qt から別の型の器が渡っても property() を呼ばない)。"""
    from PySide6.QtWidgets import QLabel, QWidgetItem
    theme.apply_theme(qapp, False)
    label = QLabel()
    label.setProperty(theme.TOGGLE_SWITCH_PROPERTY, True)
    assert not theme._is_toggle_switch(label)
    assert not theme._is_toggle_switch(QWidgetItem(label))
    assert not theme._is_toggle_switch(None)
    assert theme._is_toggle_switch(theme.make_toggle_switch(QCheckBox()))


@pytest.mark.parametrize("checked", [False, True])
def test_toggle_switch_track_color(qapp, checked):
    theme.apply_theme(qapp, False)
    checkbox = theme.make_toggle_switch(QCheckBox())
    checkbox.setChecked(checked)
    checkbox.resize(40, 24)
    image = checkbox.grab().toImage()
    # つまみの反対側のトラックの色
    y = image.height() // 2
    x = 6 if checked else theme.TOGGLE_SWITCH_SIZE[0] - 6
    color = image.pixelColor(x, y)
    expected = QColor(theme.current_tokens()["accent" if checked else "border_strong"])
    assert (color.red(), color.green(), color.blue()) == (expected.red(), expected.green(), expected.blue())


# --- カードと見出し ---

def test_stat_card_value(qapp):
    card = StatCard("平均", "42.99")
    assert card.label.text() == "平均" and card.value() == "42.99"
    card.set_value("43.10")
    assert card.value() == "43.10"
    assert card.objectName() == "stat_card"


def test_section_header_state_text_and_paint(qapp):
    header = SectionHeader("グラデーション")
    assert header.isCheckable() and header.isChecked()
    header.set_state_text("オフ")
    assert header.state_text() == "オフ"
    header.resize(300, 30)
    assert not header.grab().isNull()


# --- 色のチップ ---

def test_color_chips_pick_and_mark_the_current_color(qapp):
    row = ColorChipRow(["#1f77b4", "#ff7f0e"])
    assert row.colors() == ["#1F77B4", "#FF7F0E"]
    spy = QSignalSpy(row.colorPicked)
    row.show()
    QTest.mouseClick(row.chips[1], Qt.MouseButton.LeftButton)
    assert spy.count() == 1 and spy.at(0) == ["#FF7F0E"]
    assert [chip.isChecked() for chip in row.chips] == [False, True]
    row.set_current_color("#1F77B4")
    assert [chip.isChecked() for chip in row.chips] == [True, False]
    row.set_current_color("#000000")
    assert not any(chip.isChecked() for chip in row.chips)
    row.set_colors(["#2ca02c"])
    assert row.colors() == ["#2CA02C"]
    row.close()


# --- QSS ---

@pytest.mark.parametrize("selector", [
    "QFrame#segmented_control", "QToolButton#segment:checked", "QToolButton#type_tile:checked",
    "QSlider#slider_spin_slider::handle:horizontal", "QFrame#stat_card", "QToolButton#section_header",
])
def test_qss_has_rules_for_the_new_widgets(selector):
    for tokens in (theme.LIGHT_TOKENS, theme.DARK_TOKENS):
        assert selector + " {" in theme.build_qss(tokens)


def test_checked_segment_is_raised_above_its_track():
    for tokens in (theme.LIGHT_TOKENS, theme.DARK_TOKENS):
        assert tokens["raised"] != tokens["surface_2"]
