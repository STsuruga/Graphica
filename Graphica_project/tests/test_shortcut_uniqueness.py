# tests/test_shortcut_uniqueness.py
"""
キーボードショートカットの重複(v1.4.2)。

「名前を付けて保存」と「名前を付けてエクスポート」がどちらも
StandardKey.SaveAs(Ctrl+Shift+S)を持っており、Qt が曖昧なショートカットとして
どちらも発火させなかった。Ctrl+Shift+S は名前を付けて保存だけに割り当てる
(ユーザー判断)。同じ種類の重複が再発しないよう、ウィンドウ内の全アクションで
ショートカットが一意であることも確認する。
"""
import collections

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp


def _window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.instance().processEvents()
    return w


def test_save_as_keeps_ctrl_shift_s(tmp_path, monkeypatch):
    w = _window(tmp_path, monkeypatch)
    assert w.save_project_as_action.shortcut().matches(
        QKeySequence(QKeySequence.StandardKey.SaveAs)) == QKeySequence.SequenceMatch.ExactMatch


def test_export_as_has_no_shortcut(tmp_path, monkeypatch):
    w = _window(tmp_path, monkeypatch)
    assert w.save_action.shortcut().isEmpty()
    assert not w.save_action.shortcuts()


def test_no_two_actions_share_a_shortcut(tmp_path, monkeypatch):
    w = _window(tmp_path, monkeypatch)
    owners = collections.defaultdict(list)
    for action in w.findChildren(QAction):
        for sequence in action.shortcuts():
            if not sequence.isEmpty():
                owners[sequence.toString()].append(action.text())
    duplicated = {key: texts for key, texts in owners.items() if len(texts) > 1}
    assert duplicated == {}


def test_shortcut_list_shows_ctrl_shift_s_only_once(tmp_path, monkeypatch):
    w = _window(tmp_path, monkeypatch)
    save_as_key = QKeySequence(QKeySequence.StandardKey.SaveAs).toString()
    holders = [text for text, action in w._collect_menu_actions()
               if action.shortcut().toString() == save_as_key]
    assert len(holders) == 1
