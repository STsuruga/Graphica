"""目盛り・軸ラベル・凡例のフォントの選択(gui/panels/axis_settings.py の _ask_font)。

macOS の OS のフォントパネルは、選んだフォントが Qt に届かないと最初のフォントのまま返す(選んでも反映されない)ので、
どの OS でも Qt のダイアログを使う。
"""
import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFontDialog

import graphica.gui.panels.axis_settings as axis_settings_module
from tests.test_main_window import _make_isolated_plotter_app

HANDLERS = [
    ("_on_change_tick_font", "_tick_font", "tick_font"),
    ("_on_change_axis_label_font", "_axis_label_font", "axis_label_font"),
    ("_on_change_legend_font", "_legend_font", "legend_font"),
]


@pytest.fixture
def window(tmp_path, monkeypatch):
    w = _make_isolated_plotter_app(tmp_path, monkeypatch)
    yield w
    w.close()


@pytest.mark.parametrize("handler, attr, _key", HANDLERS)
def test_font_is_chosen_in_qts_own_dialog_not_the_os_panel(window, monkeypatch, handler, attr, _key):
    calls = []

    def fake_get_font(*args, **kwargs):
        calls.append((args, kwargs))
        return False, QFont()

    monkeypatch.setattr(axis_settings_module.QFontDialog, "getFont", staticmethod(fake_get_font))

    getattr(window.panels['axis_settings'], handler)()

    (args, kwargs), = calls
    assert args[0] == getattr(window, attr)  # 今のフォントから選び始める
    options = kwargs.get('options', args[3] if len(args) > 3 else None)
    assert options & QFontDialog.FontDialogOption.DontUseNativeDialog


@pytest.mark.parametrize("handler, attr, key", HANDLERS)
def test_the_chosen_font_reaches_the_axis_settings(window, monkeypatch, handler, attr, key):
    chosen = QFont("Arial", 17)
    chosen.setBold(True)
    monkeypatch.setattr(axis_settings_module.QFontDialog, "getFont", staticmethod(lambda *a, **k: (True, chosen)))
    monkeypatch.setattr(window.panels['axis_settings'], "_warn_if_font_family_unavailable_for_graph", lambda font: None)

    getattr(window.panels['axis_settings'], handler)()

    assert getattr(window, attr).family() == "Arial"
    saved = window.project.all_plot_settings[window.project.active_axis_index][key]
    assert saved['family'][0] == "Arial"
    assert saved['size'] == 17
    assert saved['weight'] == 'bold'
