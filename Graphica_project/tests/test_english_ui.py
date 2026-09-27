"""英語表示: メインの画面・メニュー・データセットのメニュー・環境設定に日本語が残らない(プラグインが付けた名前は除く)。"""
import re

import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QDockWidget, QGroupBox, QLabel, QLineEdit, QMenu,
                               QTabWidget, QToolBar, QWidget)

import graphica.gui.app_settings as app_settings_module
from graphica.core import i18n
from graphica.core.dataset import Dataset

_JAPANESE = re.compile(r"[぀-ヿ一-鿿]")
# プラグイン(example_plugin)が自分で付けたメニューの名前は、本体の訳の対象ではない
_PLUGIN_TEXTS = {"選択中データセットの点数を表示"}


@pytest.fixture
def english(monkeypatch, tmp_path):
    settings_path = str(tmp_path / "settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    IsolatedQSettings().setValue("language", "en")
    previous = i18n.get_language()
    i18n.set_language("en")
    yield
    i18n.set_language(previous)


def _japanese_texts(root):
    found = set()

    def note(text):
        if text and _JAPANESE.search(text) and text not in _PLUGIN_TEXTS:
            found.add(text)

    for widget in [root] + root.findChildren(QWidget):
        note(widget.toolTip())
        if isinstance(widget, (QLabel, QAbstractButton)):
            note(widget.text())
        if isinstance(widget, QGroupBox):
            note(widget.title())
        if isinstance(widget, (QDockWidget, QToolBar)):
            note(widget.windowTitle())
        if isinstance(widget, QLineEdit):
            note(widget.placeholderText())
        if isinstance(widget, QTabWidget):
            for i in range(widget.count()):
                note(widget.tabText(i))
        if isinstance(widget, QComboBox):
            for i in range(widget.count()):
                note(widget.itemText(i))
    return found


def _menu_texts(menu):
    texts = set()
    for action in menu.actions():
        texts.add(action.text())
        if action.menu() is not None:
            texts |= _menu_texts(action.menu())
    return texts


def test_main_window_menus_and_dataset_menu_are_english(english):
    from graphica.gui.datasets.actions_menu import populate_dataset_actions_menu
    from graphica.gui.main_window import PlotterApp

    window = PlotterApp(run_startup_checks=False, tab_id=2)
    try:
        leftovers = _japanese_texts(window)
        for top in (window._file_menu, window._edit_menu, window._view_menu, window._help_menu):
            leftovers |= {t for t in _menu_texts(top) if _JAPANESE.search(t) and t not in _PLUGIN_TEXTS}
        window._add_dataset(Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x",
                                    y_col_name="y"))
        menu = QMenu()
        populate_dataset_actions_menu(window, menu)
        leftovers |= {t for t in _menu_texts(menu) if _JAPANESE.search(t) and t not in _PLUGIN_TEXTS}
        assert leftovers == set()
    finally:
        window.close()


def test_preferences_dialog_is_english(english):
    from graphica.gui.dialogs import PreferencesDialog

    dialog = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    # 言語の選択肢は各言語の自分の名前で出す(「日本語」はそのまま)
    assert _japanese_texts(dialog) - {"日本語"} == set()


def test_export_units_keep_their_japanese_value_while_shown_in_english(english):
    from graphica.gui.dialogs import ExportDialog

    dialog = ExportDialog()
    shown = [dialog.unit_combo.itemText(i) for i in range(dialog.unit_combo.count())]
    assert "Inches (in)" in shown
    dialog.unit_combo.setCurrentIndex(shown.index("Inches (in)"))
    assert dialog.get_options()["unit"] == "インチ (in)"


def test_japanese_mode_leaves_the_texts_alone():
    from graphica.gui.widget_translation import translate_widget_texts

    label = QLabel("タイトル")
    translate_widget_texts(label)
    assert label.text() == "タイトル"
