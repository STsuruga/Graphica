"""GUI 刷新の画面の骨組み(gui/shell/)とモードの出し分け(gui/ui_mode.py)。PR 3。"""
import sys

import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QTabBar

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui import ui_mode
from graphica.gui.main_app_window import MainAppWindow
from graphica.gui.shell.project_tabs import ProjectTabs
from test_main_app_window import _make_isolated_main_app_window


def _pump(n=5):
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _dataset(name="d", n=5):
    df = pd.DataFrame({"x": range(n), "y": [float(v * v) for v in range(n)]})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y")


@pytest.fixture
def main_window(tmp_path, monkeypatch, qapp):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    yield window
    window.close()


# --- ProjectTabs: QTabWidget と同じ呼び方 ---

def test_project_tabs_behave_like_a_tab_widget(qapp):
    tabs = ProjectTabs()
    pages = [QLabel(str(i)) for i in range(3)]
    changes = []
    tabs.currentChanged.connect(changes.append)
    for i, page in enumerate(pages):
        assert tabs.addTab(page, f"tab{i}") == i
    assert tabs.count() == 3 and tabs.widget(1) is pages[1] and tabs.indexOf(pages[2]) == 2
    assert isinstance(tabs.tabBar(), QTabBar)
    tabs.setCurrentIndex(2)
    assert tabs.currentWidget() is pages[2] and changes[-1] == 2
    tabs.setTabText(0, "renamed")
    assert tabs.tabText(0) == "renamed"
    tabs.setCurrentWidget(pages[0])
    assert tabs.currentIndex() == 0
    tabs.removeTab(1)
    assert tabs.count() == 2 and tabs.indexOf(pages[1]) == -1


def test_moving_a_tab_moves_its_page(qapp):
    tabs = ProjectTabs()
    pages = [QLabel(str(i)) for i in range(3)]
    for i, page in enumerate(pages):
        tabs.addTab(page, f"tab{i}")
    tabs.setMovable(True)
    tabs.tabBar().moveTab(0, 2)
    assert [tabs.tabText(i) for i in range(3)] == ["tab1", "tab2", "tab0"]
    assert [tabs.widget(i) for i in range(3)] == [pages[1], pages[2], pages[0]]
    tabs.setCurrentIndex(2)
    assert tabs.currentWidget() is pages[0]


# --- 最初のモード ---

def _settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def test_new_user_starts_in_lite_and_the_choice_is_saved(tmp_path):
    settings = _settings(tmp_path)
    assert ui_mode.initial_mode(settings) == ui_mode.LITE
    assert app_settings_module.UI_MODE.read(settings) == ui_mode.LITE


def test_existing_user_starts_in_advanced(tmp_path):
    settings = _settings(tmp_path)
    app_settings_module.HAS_SHOWN_WELCOME.write(settings, True)
    assert ui_mode.initial_mode(settings) == ui_mode.ADVANCED


def test_a_saved_mode_wins_and_a_broken_one_is_replaced(tmp_path):
    settings = _settings(tmp_path)
    app_settings_module.HAS_SHOWN_WELCOME.write(settings, True)
    app_settings_module.UI_MODE.write(settings, ui_mode.LITE)
    assert ui_mode.initial_mode(settings) == ui_mode.LITE
    app_settings_module.UI_MODE.write(settings, "expert")
    assert ui_mode.initial_mode(settings) == ui_mode.ADVANCED


def test_mode_labels():
    assert ui_mode.MODE_LABELS == {ui_mode.LITE: "シンプル", ui_mode.ADVANCED: "アドバンスド"}


def test_apply_ui_mode_rejects_an_unknown_mode(main_window):
    with pytest.raises(ValueError):
        ui_mode.apply_ui_mode(main_window.tab_widget.currentWidget(), "expert")


def test_every_mode_only_element_exists_on_a_tab(main_window):
    tab = main_window.tab_widget.currentWidget()
    for dotted_name, only_in in ui_mode.MODE_ONLY_ELEMENTS:
        assert only_in in ui_mode.MODES
        assert ui_mode._resolve(tab, dotted_name) is not None, dotted_name


# --- モードの切り替え ---

def test_switching_mode_shows_and_hides_without_touching_values(main_window):
    tab = main_window.tab_widget.currentWidget()
    tab._add_dataset(_dataset("a"))
    tab._sync_project_from_ui()
    before = tab.project.content_fingerprint()
    main_window.set_ui_mode(ui_mode.ADVANCED)
    assert not tab.dataset_stats_advanced_row.isHidden() and not tab.coordinate_label.isHidden()
    main_window.set_ui_mode(ui_mode.LITE)
    assert tab.dataset_stats_advanced_row.isHidden() and tab.coordinate_label.isHidden()
    tab._sync_project_from_ui()
    assert tab.project.content_fingerprint() == before
    assert app_settings_module.UI_MODE.read(main_window._settings) == ui_mode.LITE


def test_mode_switch_in_the_header_applies_to_every_tab(main_window):
    second = main_window.add_new_project_tab()
    _pump()
    switch = main_window.header.mode_switch
    switch.setCurrentIndex(switch.findData(ui_mode.LITE))
    assert main_window.ui_mode == ui_mode.LITE
    for index in range(main_window.tab_widget.count()):
        assert main_window.tab_widget.widget(index).ui_mode == ui_mode.LITE
    switch.setCurrentIndex(switch.findData(ui_mode.ADVANCED))
    assert second.ui_mode == ui_mode.ADVANCED
    third = main_window.add_new_project_tab()
    assert third.ui_mode == ui_mode.ADVANCED


# --- 上部バー ---

def test_header_buttons_reach_the_current_tab(main_window, monkeypatch):
    second = main_window.add_new_project_tab()
    _pump()
    hits = []
    for attr in ("save_project_action", "save_action", "command_palette_action"):
        monkeypatch.setattr(second, attr, type("A", (), {"trigger": lambda self, a=attr: hits.append(a)})())
    header = main_window.header
    header.save_button.click()
    header.export_button.click()
    header.search_button.click()
    assert hits == ["save_project_action", "save_action", "command_palette_action"]


def test_menu_button_opens_the_current_tabs_menus(main_window):
    second = main_window.add_new_project_tab()
    _pump()
    menu = main_window.header.menu_button.menu()
    assert isinstance(menu, QMenu)
    submenus = [action.menu() for action in menu.actions() if action.menu() is not None]
    assert second._file_menu in submenus and second._help_menu in submenus
    assert second.quick_access_manage_action in menu.actions()
    main_window.tab_widget.setCurrentIndex(0)
    first = main_window.tab_widget.widget(0)
    assert first._file_menu in [a.menu() for a in main_window.header.menu_button.menu().actions()]


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS は画面上のメニューバーのまま")
def test_menu_bar_is_hidden_but_shortcuts_still_reach_the_tab(main_window):
    tab = main_window.tab_widget.currentWidget()
    assert tab.menuBar().isHidden()
    assert tab.save_project_action in tab.actions()
    assert tab.command_palette_action in tab.actions()


def test_quick_access_toolbar_lives_in_the_header_and_follows_the_tab(main_window):
    first = main_window.tab_widget.widget(0)
    second = main_window.add_new_project_tab()
    _pump()
    stack = main_window.header.quick_access_stack
    assert stack.currentWidget() is second.quick_access_toolbar
    assert second.quick_access_manage_action not in second.quick_access_toolbar.actions()
    main_window.tab_widget.setCurrentIndex(0)
    assert stack.currentWidget() is first.quick_access_toolbar


def test_closing_a_tab_drops_its_header_parts(main_window):
    second = main_window.add_new_project_tab()
    _pump()
    count = main_window.header.quick_access_stack.count()
    main_window._on_tab_close_requested(main_window.tab_widget.indexOf(second))
    assert main_window.header.quick_access_stack.count() == count - 1
    assert second not in main_window._tab_menus


def test_add_tab_button_opens_a_tab(main_window):
    count = main_window.tab_widget.count()
    main_window.add_tab_button.click()
    assert main_window.tab_widget.count() == count + 1


# --- 左パネルのデータセットのページ ---

def test_dataset_page_counts_and_shows_stats(main_window):
    tab = main_window.tab_widget.currentWidget()
    page = tab.dataset_page
    assert page.count_label.text() == "0"
    tab._add_dataset(_dataset("a", n=5))
    tab._add_dataset(_dataset("b", n=3))
    _pump()
    assert page.count_label.text() == "2"
    page.set_stats(_dataset("c", n=4))
    assert page.cards["n"].value() == "4"
    assert page.cards["missing"].value() == "0"
    page.set_stats(None)
    assert all(card.value() == "-" for card in page.cards.values())


def test_stats_cards_count_missing_values(main_window):
    page = main_window.tab_widget.currentWidget().dataset_page
    df = pd.DataFrame({"x": [0, 1, 2, 3], "y": [1.0, None, 3.0, None]})
    page.set_stats(Dataset(name="gaps", df=df, x_col_name="x", y_col_name="y"))
    assert page.cards["n"].value() == "2" and page.cards["missing"].value() == "2"


def test_overflow_menu_clicks_the_moved_buttons(main_window, monkeypatch):
    tab = main_window.tab_widget.currentWidget()
    clicked = []
    tab.fit_curve_button.clicked.connect(lambda: clicked.append("fit"))
    menu = tab.dataset_overflow_button.menu()
    tab.fit_curve_button.setEnabled(True)
    menu.aboutToShow.emit()  # 開くときにボタンの有効・無効を写す
    texts = {action.text(): action for action in menu.actions()}
    assert "曲線フィット..." in texts and "新規作成..." in texts
    assert texts["曲線フィット..."].isEnabled()
    texts["曲線フィット..."].trigger()
    assert clicked == ["fit"]
    assert tab.fit_curve_button.isHidden()


def test_rail_dark_mode_button_uses_the_menu_action(main_window):
    tab = main_window.tab_widget.currentWidget()
    toggled = []
    tab.dark_mode_action.triggered.connect(lambda *args: toggled.append(True))
    buttons = [b for b in tab.activity_rail.findChildren(type(tab.activity_rail.page_button("datasets")))
               if b.property("iconName") == "moon"]
    assert len(buttons) == 1
    buttons[0].click()
    assert toggled
    tab.dark_mode_action.trigger()  # 元に戻す


def test_dataset_rows_show_point_counts_and_are_taller(main_window):
    from graphica.gui.builders.common import DATASET_TREE_ROW_HEIGHT, _point_count_text
    tab = main_window.tab_widget.currentWidget()
    tab._add_dataset(_dataset("a", n=5))
    _pump()
    tree = tab.ui.dataset_list_widget
    item = tree.topLevelItem(0)
    index = tree.indexFromItem(item, 0)
    assert _point_count_text(index) == "5 点"
    assert _point_count_text(tree.indexFromItem(item, 1)) == ""
    assert tree.visualItemRect(item).height() >= DATASET_TREE_ROW_HEIGHT


def test_standalone_tab_keeps_its_menu_bar(qapp):
    """MainAppWindow に入れない PlotterApp(多くのテストの使い方)は、今までどおりメニューバーを持つ。"""
    from graphica.gui.main_window import PlotterApp
    tab = PlotterApp(run_startup_checks=False, tab_id=99)
    assert not tab.menuBar().isHidden() or sys.platform == "darwin"
    assert tab.quick_access_toolbar.parent() is tab
    assert hasattr(tab, "dataset_page") and hasattr(tab, "activity_rail")
    tab.close()


def test_main_window_is_a_main_app_window(main_window):
    assert isinstance(main_window, MainAppWindow)


# --- グラフのカード(PR 5) ---

def test_graph_tools_follow_the_mode(main_window):
    tab = main_window.tab_widget.currentWidget()
    main_window.set_ui_mode(ui_mode.LITE)
    assert not tab.plot_tool_rail.isHidden() and tab.plot_toolbar.isHidden()
    assert tab.card_subplot_label.isHidden() and tab.card_minimap_button.isHidden()
    main_window.set_ui_mode(ui_mode.ADVANCED)
    assert tab.plot_tool_rail.isHidden() and not tab.plot_toolbar.isHidden()
    # どちらの並びも同じ QAction(モードの排他はそのまま)
    assert tab.cursor_action in tab.plot_tool_rail.actions() and tab.cursor_action in tab.plot_toolbar.actions()


def test_lite_tools_are_the_mockups_four(main_window):
    tab = main_window.tab_widget.currentWidget()
    actions = [a for a in tab.plot_tool_rail.actions() if not a.isSeparator()]
    assert actions == [tab.cursor_action, tab.annotation_action, tab.range_select_action, tab.fit_tool_action]


def test_card_title_shows_the_subplot_title_or_its_number(main_window):
    from graphica.gui.builders.canvas_area import refresh_card_title
    tab = main_window.tab_widget.currentWidget()
    tab._add_dataset(_dataset("a"))
    refresh_card_title(tab)
    assert tab.card_title_label.text() == "サブプロット 1"
    assert tab.card_series_label.text() == "1 系列"
    tab.project.all_plot_settings[0]['title'] = "温度の変化 $T$"
    refresh_card_title(tab)
    assert tab.card_title_label.text() == "温度の変化 T"


def test_card_minimap_button_uses_the_menu_action(main_window):
    tab = main_window.tab_widget.currentWidget()
    before = tab.minimap_action.isChecked()
    tab.card_minimap_button.click()
    assert tab.minimap_action.isChecked() is not before
    assert tab.card_minimap_button.isChecked() is tab.minimap_action.isChecked()
    tab.card_minimap_button.click()
