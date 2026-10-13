"""グラフの下のパネル(gui/shell/bottom_panel.py)とデータ表(gui/data_table_model.py)。GUI 刷新 PR 7。"""
import logging
import time

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from graphica.core.analysis import calculate_curve_fit, evaluate_saved_fit
from graphica.core.dataset import Dataset
from graphica.gui import theme, ui_mode
from graphica.gui.data_table_model import DatasetTableModel, fit_result_for
from graphica.gui.datasets.operations.fitting import _fit_dataset
from graphica.gui.shell import bottom_panel
from test_main_app_window import _make_isolated_main_app_window


def _pump(n=5):
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _dataset(name="d", n=10, **attrs):
    x = np.arange(n, dtype=float)
    df = pd.DataFrame({"x": x, "y": 2.0 * x + 1.0 + np.where(np.arange(n) % 2 == 0, 0.3, -0.3)})
    dataset = Dataset(name=name, df=df, x_col_name="x", y_col_name="y")
    for attr, value in attrs.items():
        setattr(dataset, attr, value)
    return dataset


def _linear_fit_of(source):
    fit = calculate_curve_fit(source.x_data, source.y_data, "線形")
    fit_dataset, _text = _fit_dataset(source, fit, "線形", None, None, None, None, None, None, None,
                                      "linear", "curve_fit")
    return fit_dataset


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
    if dataset not in tab.project.datasets:
        tab._add_dataset(dataset)
    tab.ui.dataset_list_widget.setCurrentItem(tab._get_dataset_tree_item(dataset))
    _pump()
    assert tab.current_dataset() is dataset


# --- 保存したフィットの値 ---

def test_evaluate_saved_fit_reproduces_the_fitted_line():
    source = _dataset()
    fit_result = _linear_fit_of(source).fit_result
    values = evaluate_saved_fit(fit_result, [0.0, 5.0])
    a, b = fit_result["params"]
    assert values == pytest.approx([b, 5.0 * a + b])


def test_evaluate_saved_fit_gives_none_for_an_unknown_model():
    assert evaluate_saved_fit({"fit_type": "存在しないモデル", "params": [1.0]}, [1.0]) is None


# --- モード ---

def test_the_bottom_panel_is_advanced_only(main_window, tab):
    assert not tab.bottom_panel.isHidden()
    main_window.set_ui_mode(ui_mode.LITE)
    assert tab.bottom_panel.isHidden()


def test_a_view_menu_item_opens_its_tab_and_switches_to_advanced(main_window, tab):
    main_window.set_ui_mode(ui_mode.LITE)
    tab.bottom_panel_actions["provenance"].trigger()
    assert main_window.ui_mode == ui_mode.ADVANCED
    assert not tab.bottom_panel.isHidden()
    assert tab.bottom_panel.current_page() == "provenance"


def test_collapsing_keeps_only_the_header_and_opening_a_tab_expands(tab):
    panel = tab.bottom_panel
    panel.set_collapsed(True)
    assert panel.stack.isHidden()
    panel.show_page("log")
    assert not panel.is_collapsed() and not panel.stack.isHidden()


def test_collapsing_gives_the_height_to_the_plot_and_expanding_restores_it(main_window, tab):
    main_window.resize(1200, 800)
    main_window.show()
    _pump()
    splitter, panel = tab.center_splitter, tab.bottom_panel
    total = sum(splitter.sizes())
    splitter.setSizes([total - 260, 260])
    panel.set_collapsed(True)
    _pump()
    assert splitter.sizes()[1] == bottom_panel.HEADER_HEIGHT + 2
    assert splitter.sizes()[0] == total - bottom_panel.HEADER_HEIGHT - 2
    panel.set_collapsed(False)
    _pump()
    assert splitter.sizes()[1] == 260
    # 開いたままタブを押しても、ドラッグで決めた高さは変えない
    splitter.setSizes([total - 300, 300])
    panel.show_page("log")
    _pump()
    assert splitter.sizes()[1] == 300


# --- データ表 ---

def test_the_table_shows_the_visible_rows_with_their_original_row_numbers(tab):
    dataset = _dataset(n=6)
    dataset.masked_row_indices = [1, 2]
    _select(tab, dataset)
    model = tab.data_table_model
    assert model.rowCount() == 4
    assert [model.value(row, 0) for row in range(4)] == [1, 4, 5, 6]
    assert [model.value(row, 1) for row in range(4)] == list(dataset.x_data)
    assert tab.bottom_panel.meta_label.text() == "d · 4 行"


def test_the_table_has_fit_and_residual_columns_for_a_fitted_source(tab):
    source = _dataset()
    _select(tab, source)
    fit_dataset = _linear_fit_of(source)
    tab._add_dataset(fit_dataset)
    _select(tab, source)
    model = tab.data_table_model
    assert model.columnCount() == 5
    fitted = evaluate_saved_fit(fit_dataset.fit_result, source.x_data)
    for row in range(model.rowCount()):
        assert model.value(row, 3) == pytest.approx(fitted[row])
        assert model.value(row, 4) == pytest.approx(source.y_data[row] - fitted[row])
    negative = next(row for row in range(model.rowCount()) if model.value(row, 4) < 0)
    brush = model.data(model.index(negative, 4), Qt.ItemDataRole.ForegroundRole)
    assert brush.color() == QColor(theme.current_tokens()["danger"])


def test_the_fit_tab_shows_the_fit_text_and_r_squared_for_the_source_and_the_curve(tab):
    source = _dataset()
    fit_dataset = _linear_fit_of(source)
    tab._add_dataset(source)
    tab._add_dataset(fit_dataset)
    for selected in (source, fit_dataset):
        _select(tab, selected)
        assert tab.fit_info_textedit.toPlainText() == fit_dataset.fit_info
        assert tab.bottom_panel.badge_text("fit") == f"R² {fit_dataset.fit_result['r_squared']:.3f}"
    plain = _dataset("plain")
    _select(tab, plain)
    assert tab.fit_info_textedit.toPlainText() == ""
    assert tab.bottom_panel.badge_text("fit") == ""
    assert fit_result_for(plain, tab.project.datasets) is None


@pytest.mark.parametrize("waterfall", [False, True])
def test_the_cursor_row_matches_the_table_row_with_masked_rows(tab, waterfall):
    dataset = _dataset(n=8, waterfall_enabled=waterfall, waterfall_offset_x=0.5, waterfall_offset_y=3.0)
    dataset.masked_row_indices = [2, 5]
    other = _dataset("other", n=8, waterfall_enabled=waterfall)
    tab._add_dataset(other)
    _select(tab, dataset)
    tab._update_plot()
    cursor = tab.mouse_tools["cursor"]
    model = tab.data_table_model
    for ind in range(len(dataset.x_data)):
        row_number = cursor._picked_row_number(dataset, ind)
        bottom_panel.highlight_table_row(tab, dataset, row_number)
        assert model.highlighted_row() == ind
        assert model.value(ind, 1) == dataset.x_data[ind]


def test_a_row_of_another_dataset_is_not_highlighted(tab):
    shown, other = _dataset("shown"), _dataset("other")
    tab._add_dataset(other)
    _select(tab, shown)
    bottom_panel.highlight_table_row(tab, other, 1)
    assert tab.data_table_model.highlighted_row() is None


def test_a_large_dataset_fills_the_table_quickly(qapp):
    n = 50_000
    x = np.linspace(0.0, 1.0, n)
    dataset = Dataset(name="big", df=pd.DataFrame({"x": x, "y": x * x}), x_col_name="x", y_col_name="y")
    model = DatasetTableModel()
    started = time.perf_counter()
    model.set_dataset(dataset)
    assert model.rowCount() == n
    assert model.row_for_number(n) == n - 1
    assert time.perf_counter() - started < 5.0


def test_a_2d_map_leaves_the_table_empty(qapp):
    dataset = _dataset(data_kind="2d_grid")
    model = DatasetTableModel()
    model.set_dataset(dataset)
    assert model.rowCount() == 0 and model.columnCount() == 0


# --- ログ ---

def test_the_log_tab_shows_new_log_lines(tab):
    logging.getLogger("graphica.test_bottom_panel").warning("下のパネルに出す行")
    assert "下のパネルに出す行" in tab.bottom_log.toPlainText()


def test_destroying_the_log_view_removes_its_handler(main_window):
    from PySide6.QtCore import QEvent
    second = main_window.add_new_project_tab()
    handler = second.bottom_log._handler
    assert handler in logging.getLogger().handlers
    second.bottom_log.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert handler not in logging.getLogger().handlers
