"""左端の帯の解析・注釈・レイアウト・プラグインのページ(gui/shell/side_pages.py)。GUI 刷新 PR 4。"""
import pytest

import graphica.gui.datasets.processing as processing_module
from graphica.gui.shell.side_pages import ANALYSIS_PROCESSING_KEYS
from test_main_window import _make_isolated_plotter_app


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    w = _make_isolated_plotter_app(tmp_path, monkeypatch)
    yield w
    w.close()


def test_rail_has_the_five_pages_in_the_mockup_order(window):
    rail = window.activity_rail
    keys = ["datasets", "analysis", "notes", "plugins", "layout"]
    assert all(rail.page_button(key) is not None for key in keys)
    layout = rail.layout()
    order = [layout.itemAt(i).widget() for i in range(len(keys))]
    assert order == [rail.page_button(key) for key in keys]
    assert rail.current_page() == "datasets"


@pytest.mark.parametrize("key", ["datasets", "analysis", "notes", "plugins", "layout"])
def test_each_rail_button_shows_its_page(window, key):
    window.activity_rail.page_button(key).click()
    assert window.left_panel.currentWidget() is window._left_panel_pages[key]
    assert window.activity_rail.current_page() == key


def test_analysis_page_runs_the_same_operations_as_the_menu(window, monkeypatch):
    ran = []
    monkeypatch.setattr(processing_module, "run_operation", lambda operation, host, state: ran.append(operation.title))
    page = window._left_panel_pages["analysis"]
    texts = page.row_texts()
    assert "曲線フィット..." in texts and "ピーク検出..." in texts
    row = page.rows[texts.index("規格化(ノーマライズ)...")]
    row.click()
    assert ran == ["規格化(ノーマライズ)"]
    assert len([t for t in texts if t.endswith("...")]) >= len(ANALYSIS_PROCESSING_KEYS)


def test_notes_page_uses_the_menu_actions(window):
    page = window._left_panel_pages["notes"]
    actions = [getattr(row, 'action', None) for row in page.rows]
    assert window.annotation_action in actions and window.panel_labels_action in actions
    row = page.rows[actions.index(window.annotation_action)]
    row.click()
    assert window.annotation_action.isChecked() and row.isChecked()
    row.click()
    assert not window.annotation_action.isChecked()


def test_layout_page_follows_the_layout_edit_availability(window):
    page = window._left_panel_pages["layout"]
    actions = [getattr(row, 'action', None) for row in page.rows]
    assert window.minimap_action in actions and window.canvas_detach_action in actions
    row = page.rows[actions.index(window.layout_edit_action)]
    # 自由配置のときだけ使える(メニューと同じ QAction なので、有効・無効も一緒に変わる)
    assert row.isEnabled() == window.layout_edit_action.isEnabled()


def test_layout_page_opens_the_axis_settings(window):
    window.properties_dock_widget.hide()
    page = window._left_panel_pages["layout"]
    page.rows[page.row_texts().index("サブプロットの数・並び(軸の設定)")].click()
    assert not window.properties_dock_widget.isHidden()
