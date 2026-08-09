# tests/test_color_history.py
"""gui/color_history.py に対するテスト。

QColorDialog.getColor()/setCustomColor() はQtの静的な状態を書き換えるため、
実際のダイアログを表示せずに monkeypatch で差し替えてテストする。
settings には QSettings 互換の value()/setValue() だけを持つ軽量なフェイクを使う
(実ファイルI/Oを避け、テストを高速・独立に保つため)。
"""
import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog

from gui.color_history import (
    load_recent_colors_into_picker,
    get_color_with_history,
    MAX_RECENT_COLORS,
)


class _FakeSettings:
    """QSettingsのvalue()/setValue()だけを模した辞書ベースのフェイク"""

    def __init__(self, initial=None):
        self._store = dict(initial or {})

    def value(self, key, default=None):
        return self._store.get(key, default)

    def setValue(self, key, value):
        self._store[key] = value


# --- load_recent_colors_into_picker ---

def test_load_recent_colors_into_picker_does_nothing_when_no_history(monkeypatch):
    """保存された履歴が無い場合、setCustomColorは一切呼ばれないこと"""
    calls = []
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: calls.append((i, c))))

    settings = _FakeSettings()
    load_recent_colors_into_picker(settings)

    assert calls == []


def test_load_recent_colors_into_picker_restores_saved_colors(monkeypatch):
    """保存された色名のリストが、順番通りにカスタムカラー欄へ復元されること"""
    calls = []
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: calls.append((i, c.name()))))

    settings = _FakeSettings({"recent_colors": ["#ff0000", "#00ff00", "#0000ff"]})
    load_recent_colors_into_picker(settings)

    assert calls == [(0, "#ff0000"), (1, "#00ff00"), (2, "#0000ff")]


def test_load_recent_colors_into_picker_truncates_to_max_recent_colors(monkeypatch):
    """MAX_RECENT_COLORSを超える履歴があっても、先頭のMAX_RECENT_COLORS件だけ復元すること"""
    calls = []
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: calls.append(i)))

    many_colors = [QColor.fromHsv(h % 360, 200, 200).name() for h in range(0, 360, 10)]
    assert len(many_colors) > MAX_RECENT_COLORS
    settings = _FakeSettings({"recent_colors": many_colors})
    load_recent_colors_into_picker(settings)

    assert calls == list(range(MAX_RECENT_COLORS))


# --- get_color_with_history ---

def test_get_color_with_history_records_selected_color_at_front(monkeypatch):
    """色が選択された(Cancel以外)場合、その色が履歴の先頭に記録・永続化されること"""
    chosen = QColor("#123456")
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: chosen))
    set_custom_calls = []
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: set_custom_calls.append((i, c.name()))))

    settings = _FakeSettings({"recent_colors": ["#aaaaaa"]})
    result = get_color_with_history(settings)

    assert result == chosen
    assert settings.value("recent_colors") == ["#123456", "#aaaaaa"]
    assert set_custom_calls == [(0, "#123456"), (1, "#aaaaaa")]


def test_get_color_with_history_deduplicates_existing_color(monkeypatch):
    """既に履歴にある色が再度選択された場合、重複させず先頭に移動するだけであること"""
    chosen = QColor("#00ff00")
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: chosen))
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: None))

    settings = _FakeSettings({"recent_colors": ["#ff0000", "#00ff00", "#0000ff"]})
    get_color_with_history(settings)

    assert settings.value("recent_colors") == ["#00ff00", "#ff0000", "#0000ff"]


def test_get_color_with_history_truncates_to_max_recent_colors(monkeypatch):
    """履歴がMAX_RECENT_COLORSを超える場合、末尾を切り捨てて上限を保つこと"""
    chosen = QColor("#ffffff")
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: chosen))
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: None))

    existing = [QColor.fromHsv(h % 360, 200, 200).name() for h in range(0, 360, 10)][:MAX_RECENT_COLORS]
    settings = _FakeSettings({"recent_colors": existing})
    get_color_with_history(settings)

    stored = settings.value("recent_colors")
    assert len(stored) == MAX_RECENT_COLORS
    assert stored[0] == "#ffffff"


def test_get_color_with_history_does_not_record_when_cancelled(monkeypatch):
    """Cancelされた(無効なQColorが返る)場合、履歴は変更されないこと"""
    invalid_color = QColor()  # isValid() == False
    assert not invalid_color.isValid()
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: invalid_color))
    set_custom_calls = []
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: set_custom_calls.append((i, c))))

    settings = _FakeSettings({"recent_colors": ["#aaaaaa"]})
    result = get_color_with_history(settings)

    assert not result.isValid()
    assert settings.value("recent_colors") == ["#aaaaaa"]
    assert set_custom_calls == []


def test_get_color_with_history_passes_initial_color_to_dialog(monkeypatch):
    """initial引数が指定された場合、QColorDialog.getColor(initial, parent)の形で渡されること"""
    captured = {}

    def fake_get_color(*args, **kwargs):
        captured['args'] = args
        captured['kwargs'] = kwargs
        return QColor("#654321")

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(fake_get_color))
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: None))

    settings = _FakeSettings()
    initial = QColor("#111111")
    get_color_with_history(settings, parent=None, initial=initial)

    assert captured['args'][0] == initial


def test_get_color_with_history_without_initial_uses_parent_kwarg(monkeypatch):
    """initial引数が省略された場合、QColorDialog.getColor(parent=parent)の形で呼ばれること"""
    captured = {}

    def fake_get_color(*args, **kwargs):
        captured['args'] = args
        captured['kwargs'] = kwargs
        return QColor("#654321")

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(fake_get_color))
    monkeypatch.setattr(QColorDialog, "setCustomColor", staticmethod(lambda i, c: None))

    settings = _FakeSettings()
    get_color_with_history(settings, parent=None)

    assert captured['args'] == ()
    assert captured['kwargs'] == {'parent': None}
