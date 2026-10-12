"""ステータスバーと ⚙ のテーマカラーのポップアップ・環境設定のテーマカラー。GUI 刷新 PR 8。"""
import pandas as pd
import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui import theme, ui_mode
from graphica.gui.builders.canvas_area import autosave_status_text, refresh_status_bar
from graphica.gui.shell.settings_popover import theme_color_preview, toggle_settings_popover
from graphica.gui.theme_color import DEFAULT_THEME_COLOR, derive_accent
from test_main_app_window import _make_isolated_main_app_window


def _pump(n=5):
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _dataset(name):
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 4.0]})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y")


@pytest.fixture
def main_window(tmp_path, monkeypatch, qapp):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    window.set_ui_mode(ui_mode.ADVANCED)
    yield window
    # テーマはアプリ全体の状態なので、ほかのテストに持ち越さない
    theme.apply_theme(QApplication.instance(), False, DEFAULT_THEME_COLOR)
    window.close()


@pytest.fixture
def tab(main_window):
    return main_window.tab_widget.currentWidget()


# --- ステータスバー ---

@pytest.mark.parametrize("enabled, interval, since, expected", [
    (False, 0, None, "自動保存 オフ"),
    (True, 5, None, "自動保存 5 分ごと"),
    (True, 5, 30.0, "自動保存 たった今"),
    (True, 5, 125.0, "自動保存 2 分前"),
])
def test_autosave_status_text(enabled, interval, since, expected):
    assert autosave_status_text(enabled, interval, since) == expected


def test_the_status_bar_counts_datasets_and_the_selection(tab):
    first, second = _dataset("a"), _dataset("b")
    tab._add_dataset(first)
    tab._add_dataset(second)
    tab.ui.dataset_list_widget.setCurrentItem(tab._get_dataset_tree_item(first))
    _pump()
    assert tab.status_selection_label.text() == "2 データセット · 1 選択"


def test_an_autosave_shows_just_now(tab, monkeypatch):
    monkeypatch.setattr(tab.project, "save_project", lambda path: None)
    tab.autosave_timer.start(5 * 60 * 1000)
    tab.auto_save()
    assert tab.autosave_status_label.text() == "自動保存 たった今"
    tab.autosave_timer.stop()
    refresh_status_bar(tab)
    assert tab.autosave_status_label.text() == "自動保存 オフ"


def test_lite_keeps_only_ready_and_autosave(main_window, tab):
    main_window.set_ui_mode(ui_mode.LITE)
    assert tab.status_selection_label.isHidden() and tab.coordinate_label.isHidden()
    assert not tab.status_ready.isHidden() and not tab.autosave_status_label.isHidden()


# --- テーマカラー ---

def test_setting_the_theme_color_applies_and_saves_it_for_every_tab(main_window, tab):
    second = main_window.add_new_project_tab()
    _pump()
    main_window.set_theme_color("#e11d48")
    assert theme.current_theme_color() == "#E11D48"
    assert app_settings_module.THEME_COLOR.read(main_window._settings) == "#E11D48"
    expected = derive_accent("#E11D48", theme.LIGHT_TOKENS["surface"], dark=False)["accent"]
    assert theme.current_tokens()["accent"] == expected
    assert QApplication.instance().palette().highlight().color() == QColor(expected)
    assert second.ui_mode == ui_mode.ADVANCED  # 替えてもほかの状態はそのまま


def test_a_broken_color_falls_back_to_the_default(main_window):
    main_window.set_theme_color("not a color")
    assert theme.current_theme_color() == DEFAULT_THEME_COLOR


def test_the_preview_explains_an_adjusted_color():
    light, dark, note = theme_color_preview("#FACC15")
    assert light != "#FACC15" and "ライトでは" in note
    light, dark, note = theme_color_preview(DEFAULT_THEME_COLOR)
    assert light == DEFAULT_THEME_COLOR and "ダークでは" in note and "ライトでは" not in note


def test_the_popover_swatches_and_reset_change_the_theme_color(main_window, tab):
    toggle_settings_popover(tab, tab.settings_rail_button)
    popover = tab.settings_popover
    assert popover.isVisible()
    yellow = next(s for s in popover.swatches if s.color == "#FACC15")
    yellow.click()
    assert theme.current_theme_color() == "#FACC15"
    assert yellow.isChecked() and not popover.note_label.isHidden()
    assert popover.hex_label.text() == "#FACC15"
    popover.reset_button.click()
    assert theme.current_theme_color() == DEFAULT_THEME_COLOR
    toggle_settings_popover(tab, tab.settings_rail_button)
    assert not popover.isVisible()


def test_the_popover_custom_color(main_window, tab, monkeypatch):
    import graphica.gui.shell.settings_popover as popover_module
    monkeypatch.setattr(popover_module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#123abc")))
    toggle_settings_popover(tab, tab.settings_rail_button)
    tab.settings_popover.custom_button.click()
    assert theme.current_theme_color() == "#123ABC"


def test_preferences_has_the_theme_color(main_window, tab, monkeypatch):
    from graphica.gui.dialogs import PreferencesDialog
    dialog = PreferencesDialog(False, 5, theme_color="#2563eb", parent=tab)
    assert dialog.get_theme_color() == "#2563EB"
    from PySide6.QtWidgets import QColorDialog
    # ダイアログは押したときに QColorDialog を import するので、クラスの方を差し替える
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#7c3aed")))
    dialog.theme_color_button.click()
    assert dialog.get_theme_color() == "#7C3AED"
    dialog.close()
