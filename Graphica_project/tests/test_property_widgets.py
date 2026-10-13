"""プロパティの見た目の部品(builders/property_widgets.py)とシンプルの行の出し分け。GUI 刷新 PR 6b。"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui import ui_mode
from graphica.gui.builders import property_widgets
from graphica.gui.dataset_bindings import NO_MARKER
from test_main_app_window import _make_isolated_main_app_window


def _pump(n=5):
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _dataset(name="d", **style):
    df = pd.DataFrame({"x": range(5), "y": [float(v * v) for v in range(5)]})
    dataset = Dataset(name=name, df=df, x_col_name="x", y_col_name="y")
    for attr, value in style.items():
        setattr(dataset, attr, value)
    return dataset


@pytest.fixture
def main_window(tmp_path, monkeypatch, qapp):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    window.set_ui_mode(ui_mode.ADVANCED)
    yield window
    window.close()


@pytest.fixture
def tab(main_window):
    return main_window.tab_widget.currentWidget()


def _select(tab, dataset):
    tab._add_dataset(dataset)
    tab.ui.dataset_list_widget.setCurrentItem(tab._get_dataset_tree_item(dataset))
    _pump()
    assert tab.current_dataset() is dataset


def _select_new(tab, name, **style):
    dataset = _dataset(name, **style)
    _select(tab, dataset)
    return dataset


# --- 値の持ち主は今の部品のまま ---

def test_line_style_segments_write_the_combo_and_follow_a_restore(tab):
    first = _select_new(tab, "a", linestyle="dashed")
    assert tab.linestyle_segments.currentData() == "dashed"
    tab.linestyle_segments.setCurrentIndex(tab.linestyle_segments.findData("dotted"))
    assert tab.ui.linestyle_combo.currentText() == "dotted"
    assert first.linestyle == "dotted"

    _select_new(tab, "b", linestyle="dashdot")
    assert tab.linestyle_segments.currentData() == "dashdot"


def test_sliders_write_the_spinboxes_and_follow_a_restore(tab):
    dataset = _select_new(tab, "a", linewidth=3.0, alpha=0.5)
    scale = tab.linewidth_slider._scale
    assert tab.linewidth_slider.slider.value() == round(3.0 * scale)
    assert tab.alpha_slider.slider.value() == round(0.5 * tab.alpha_slider._scale)

    tab.linewidth_slider.slider.setValue(round(1.0 * scale))
    assert tab.ui.linewidth_spinbox.value() == pytest.approx(1.0)
    assert dataset.linewidth == pytest.approx(1.0)


def test_smoothing_checkbox_is_drawn_as_a_switch(tab):
    from graphica.gui import theme
    assert tab.ui.smoothing_checkbox.property(theme.TOGGLE_SWITCH_PROPERTY) is True


def test_a_quick_color_chip_sets_the_dataset_color(tab):
    dataset = _select_new(tab, "a", color="#123456")
    row = tab.color_picker_widget.quick_colors_row
    assert row.colors() == [c.upper() for c in tab.colors.active_color_cycle()[:property_widgets.QUICK_COLOR_COUNT]]
    row.chips[1].click()
    assert dataset.color.upper() == row.colors()[1]
    assert row.chips[1].isChecked()


def test_the_quick_colors_sit_under_the_swatch_and_code(tab):
    picker = tab.color_picker_widget
    _select_new(tab, "a")
    _pump()
    row = picker.quick_colors_row
    assert len(row.chips) == property_widgets.QUICK_COLOR_COUNT
    # 1段目(見本と #RRGGBB)の下の段
    outer = picker.layout()
    assert outer.indexOf(row) > 0 and outer.itemAt(0).layout().indexOf(picker.hex_edit) >= 0


def test_the_secondary_y_switch_is_right_under_the_y_column(tab):
    form = tab._prop_form('data')
    y_row, _ = form.getWidgetPosition(tab.y_col_combo)
    assert form.getWidgetPosition(tab.use_secondary_y_checkbox)[0] == y_row + 1


# --- シンプルの種類のタイル ---

def test_type_tiles_follow_the_plot_type(tab):
    _select_new(tab, "a", plot_type="Bar")
    assert tab.plot_type_tiles.currentData() == "Bar"
    _select_new(tab, "b", plot_type="Step")
    assert tab.plot_type_tiles.currentIndex() == -1  # 4つに無い種類はどれも選ばない


def test_line_and_dots_tile_adds_a_circle_marker_in_one_undo_step(tab):
    dataset = _select_new(tab, "a", plot_type="Line", marker=NO_MARKER)
    tab.plot_type_tiles.setCurrentIndex(tab.plot_type_tiles.findData("Line+Scatter"))
    assert dataset.plot_type == "Line+Scatter"
    assert dataset.marker == "o"
    tab.undo_stack.undo()
    assert dataset.plot_type == "Line"
    assert dataset.marker == NO_MARKER


def test_a_tile_keeps_an_existing_marker(tab):
    dataset = _select_new(tab, "a", plot_type="Line", marker="s")
    tab.plot_type_tiles.setCurrentIndex(tab.plot_type_tiles.findData("Scatter"))
    assert dataset.plot_type == "Scatter"
    assert dataset.marker == "s"


# --- シンプルの行の出し分け ---

def _section_shown(tab, key):
    return not tab._prop_sections[key]['section'].isHidden()


def test_lite_hides_advanced_rows_and_sections_and_advanced_brings_them_back(main_window, tab):
    _select_new(tab, "a", plot_type="Line")
    main_window.set_ui_mode(ui_mode.LITE)
    for name in ("use_secondary_y_checkbox", "x_err_col_combo", "nan_policy_combo", "alpha_slider",
                 "smoothing_method_combo"):
        assert getattr(tab, name).isHidden(), name
    assert tab.ui.plot_type_combo.isHidden() and tab.ui.smoothing_checkbox.isHidden()
    assert tab.color_picker_widget.hex_edit.isHidden()
    assert not tab._plot_type_tiles_row.isHidden() and not tab.lite_more_box.isHidden()
    assert _section_shown(tab, "data") and _section_shown(tab, "style")
    for key in ("marker", "gradient", "waterfall", "map", "extra", "place"):
        assert not _section_shown(tab, key), key

    main_window.set_ui_mode(ui_mode.ADVANCED)
    for name in ("use_secondary_y_checkbox", "x_err_col_combo", "nan_policy_combo", "alpha_slider",
                 "smoothing_method_combo"):
        assert not getattr(tab, name).isHidden(), name
    # 平滑化は線の種類でだけ出す(今の条件は残る)
    assert not tab.ui.smoothing_checkbox.isHidden()
    assert tab._plot_type_tiles_row.isHidden() and tab.lite_more_box.isHidden()
    assert _section_shown(tab, "place")


def test_lite_still_hides_rows_after_a_selection_reapplies_the_conditions(main_window, tab):
    main_window.set_ui_mode(ui_mode.LITE)
    _select_new(tab, "a", plot_type="Line")
    assert tab.ui.smoothing_checkbox.isHidden()
    assert not _section_shown(tab, "gradient")


def test_switching_mode_keeps_values(main_window, tab):
    _select_new(tab, "a", plot_type="Line+Scatter", alpha=0.4, linestyle="dashed")
    tab._sync_project_from_ui()
    before = tab.project.content_fingerprint()
    main_window.set_ui_mode(ui_mode.LITE)
    main_window.set_ui_mode(ui_mode.ADVANCED)
    tab._sync_project_from_ui()
    assert tab.project.content_fingerprint() == before


def test_the_lite_hint_switches_every_tab_to_advanced(main_window, tab):
    second = main_window.add_new_project_tab()
    main_window.set_ui_mode(ui_mode.LITE)
    tab.lite_more_button.click()
    assert main_window.ui_mode == ui_mode.ADVANCED and second.ui_mode == ui_mode.ADVANCED
    assert app_settings_module.UI_MODE.read(main_window._settings) == ui_mode.ADVANCED
