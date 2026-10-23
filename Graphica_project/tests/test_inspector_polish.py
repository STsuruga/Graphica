"""インスペクタの手直し(編集するサブプロットの升目・軸タブの節・セグメントとスライダー・フィット結果の表)。"""
import pandas as pd
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from graphica.core.dataset import Dataset
from graphica.core.marker_style import MARKER_FILL_COLOR, MARKER_FILL_HOLLOW
from graphica.gui import ui_mode
from graphica.gui.shell import fit_result_view
from test_main_app_window import _make_isolated_main_app_window


def _pump(n=5):
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _dataset(name="d", **attrs):
    df = pd.DataFrame({"x": [float(v) for v in range(6)], "y": [float(v * v) for v in range(6)]})
    dataset = Dataset(name=name, df=df, x_col_name="x", y_col_name="y")
    for attr, value in attrs.items():
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


def _set_grid(tab, rows, cols):
    tab.subplot_rows_spinbox.setValue(rows)
    tab.subplot_cols_spinbox.setValue(cols)
    _pump()


# --- 編集するサブプロットの升目 ---

def test_the_target_bar_is_hidden_with_one_subplot(tab):
    assert tab.subplot_target_bar.isHidden()


def test_clicking_a_cell_selects_that_subplot(tab):
    _set_grid(tab, 2, 2)
    bar = tab.subplot_target_bar
    assert not bar.isHidden() and not bar.grid.isHidden() and bar.combo.isHidden()
    grid = bar.grid
    target = grid._cell_rect(3).center()
    assert grid.cell_at(QPointF(target)) == 3
    grid.cellClicked.emit(3)
    assert tab.active_axis_combo.currentIndex() == 3
    assert tab.project.active_axis_index == 3
    assert bar.name_label.text() == tab.active_axis_combo.itemText(3)


def test_too_many_subplots_fall_back_to_the_combo(tab):
    _set_grid(tab, 2, 5)
    bar = tab.subplot_target_bar
    assert bar.grid.isHidden() and not bar.combo.isHidden()


# --- 軸タブの節 ---

def test_the_secondary_y_section_opens_when_a_dataset_uses_it(tab):
    toggle = tab._axis_tab_sections["y2"]['toggle']
    assert not toggle.isChecked()
    _select(tab, _dataset("a", use_secondary_y=True))
    tab._update_plot()
    assert toggle.isChecked()


def test_every_inspector_form_starts_its_fields_at_the_same_column(tab):
    from PySide6.QtWidgets import QFormLayout, QLabel
    from graphica.gui import dock_layout
    widths = set()
    for form in dock_layout.inspector_forms(tab):
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item is not None and isinstance(item.widget(), QLabel):
                widths.add(item.widget().minimumWidth())
    assert widths == {92}


# --- セグメントとスライダー ---

def test_the_tick_mode_segments_write_the_combo(tab):
    segments = tab.tick_mode_mirrors[0].view
    segments.setCurrentIndex(1)
    assert tab.ui.x_major_tick_mode_combo.currentIndex() == 1
    assert tab.ui.x_major_tick_interval_spinbox.isEnabled()


def test_the_marker_fill_segments_follow_the_combo_and_lock_the_colour_choice_for_mapped_types(tab):
    _select(tab, _dataset("p", plot_type="Scatter", marker="o"))
    tab.marker_fill_segments.setCurrentIndex(tab.marker_fill_segments.findData(MARKER_FILL_HOLLOW))
    assert tab.marker_fill_combo.currentData() == MARKER_FILL_HOLLOW
    _select(tab, _dataset("z", plot_type="Density Scatter", marker="o"))
    button = tab.marker_fill_segments._group.button(tab.marker_fill_segments.findData(MARKER_FILL_COLOR))
    assert not button.isEnabled()


def test_the_contour_slider_takes_an_integer_spinbox(tab):
    slider = tab.contour_levels_slider
    slider.slider.setValue(20)
    assert tab.contour_levels_spinbox.value() == 20


def test_the_copy_format_segments_choose_svg(tab):
    panel = tab.export_preview_panel
    panel.copy_format_segments.setCurrentIndex(1)
    assert panel.copy_format_combo.currentText() == "SVG"


# --- フィット結果の表 ---

def test_values_are_rounded_to_the_error_and_copied_unrounded():
    assert fit_result_view.format_value_and_error(79.4291, 1.83) == ("79.4", "± 1.8")
    assert fit_result_view.format_value_and_error(-0.070729, 0.0031) == ("-0.0707", "± 0.0031")
    assert fit_result_view.format_value_and_error(2.5, 0.0) == ("2.5", "")
    result = {"param_names": ["a", "b"], "params": [79.4291, -0.070729], "param_errors": [1.83, 0.0031],
              "r_squared": 0.93661, "fixed_params": {"b": -0.070729}}
    lines = fit_result_view.table_tsv(result).splitlines()
    assert lines[1].split("\t")[:3] == ["a", "79.4291", "1.83"]
    assert lines[2].split("\t")[2] == "固定"
    assert lines[-1] == "R²\t0.93661"
    assert fit_result_view.values_tsv(result) == "79.4291\t-0.070729"


def test_the_fit_tab_shows_a_table_for_a_fit_and_the_text_otherwise(qapp):
    from PySide6.QtWidgets import QTextEdit
    text = QTextEdit()
    view = fit_result_view.FitResultView(text)
    view.set_result({"fit_type": "線形", "param_names": ["a", "b"], "params": [2.0, 1.0],
                     "param_errors": [0.1, 0.2], "residuals": [0.0] * 5})
    assert view.stack.currentIndex() == 0
    assert view.table.rowCount() == 2 and view.detail_label.text() == "5 点"
    view.set_result({"fit_type": "plugin", "params": []})
    assert view.stack.currentWidget() is text
