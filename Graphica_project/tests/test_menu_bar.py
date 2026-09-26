"""メニューバーの一覧表(graphica/gui/menu_bar.py)。"""
import gc

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
import graphica.gui.menu_bar as menu_bar
from graphica.gui.main_window import PlotterApp


def _make_window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.processEvents()
    return window


def _method_names(items):
    for item in items:
        if isinstance(item, menu_bar.Item):
            yield item.slot
            if item.after:
                yield item.after
        elif isinstance(item, menu_bar.Submenu):
            yield from filter(None, (item.on_show, item.after))
            yield from _method_names(item.items)
        elif isinstance(item, menu_bar.Call):
            yield item.method


def test_every_name_in_the_table_is_a_plotter_app_method():
    """表の呼び先は文字列なので、書き間違いは組み立てるまで分からない。"""
    tops = (menu_bar.FILE_MENU, menu_bar.EDIT_MENU, menu_bar.DATASET_MENU, menu_bar.VIEW_MENU, menu_bar.HELP_MENU)
    names = set()
    for top in tops:
        names.update(_method_names(top.items))
        if top.on_show:
            names.add(top.on_show)

    missing = sorted(name for name in names if not callable(getattr(PlotterApp, name, None)))

    assert missing == []


def test_menus_survive_being_walked_repeatedly(tmp_path, monkeypatch):
    """PySide6 は参照の無くなったメニューを回収する。辿るたびに消えていかないこと。"""
    window = _make_window(tmp_path, monkeypatch)

    first = [path for path, _ in window._collect_menu_actions()]
    gc.collect()
    second = [path for path, _ in window._collect_menu_actions()]
    gc.collect()

    assert second == first
    assert window._dock_layout_menu.actions()
    assert window.recent_files_menu.menuAction() is window._recent_files_menu_action


def test_pinned_menu_paths_keep_their_text(tmp_path, monkeypatch):
    """ピン留めはメニューのパスで保存されるので、文字を変えると外れる。"""
    window = _make_window(tmp_path, monkeypatch)
    paths = {tuple(path) for path, _ in window._collect_menu_actions()}

    for expected in (
        ("ファイル(F)", "上書き保存(P)"),
        ("ファイル(F)", "エクスポート", "印刷(R)..."),
        ("編集(E)", "コマンドパレット(K)..."),
        ("表示(V)", "ドックレイアウト", "既定のレイアウトにリセット"),
        ("表示(V)", "ダークモード"),
    ):
        assert expected in paths, expected
