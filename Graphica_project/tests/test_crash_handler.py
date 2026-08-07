# tests/test_crash_handler.py
"""gui/crash_handler.py のセーフモード起動プロンプト(項目F-4)に対するテスト。"""
import pytest

import core.plugin_api as plugin_api_module
import gui.crash_handler as crash_handler_module
from gui.crash_handler import prompt_safe_mode_and_apply, should_prompt_safe_mode


@pytest.fixture(autouse=True)
def _isolate_plugin_state():
    """
    core/plugin_api.py のセーフモードフラグはプロセス全体のグローバル状態のため、
    このテストファイルだけでなく他のテストファイル(test_plugin_api_safe_mode.py等)
    とも同じプロセス内で共有される。テスト前後でリセットしないと、pytestを
    1プロセスでまとめて実行した際に他のテストへ状態が漏れる
    (このセッションで実際に踏んだ問題のクラスなので、必ずリセットする)。
    """
    yield
    plugin_api_module._safe_mode_enabled = False


class _FakeSettings:
    """QSettings互換の最小スタブ(.value(key, default, type=...)のみ実装)。"""

    def __init__(self, clean_exit):
        self._clean_exit = clean_exit

    def value(self, key, default=True, type=bool):
        assert key == "clean_exit"
        return self._clean_exit


def test_should_prompt_safe_mode_false_when_clean_exit_true():
    """前回正常終了していた場合はセーフモードを尋ねる必要が無い。"""
    assert should_prompt_safe_mode(_FakeSettings(clean_exit=True)) is False


def test_should_prompt_safe_mode_true_when_clean_exit_false():
    """前回異常終了(clean_exit=False)していた場合のみ尋ねる。"""
    assert should_prompt_safe_mode(_FakeSettings(clean_exit=False)) is True


def test_prompt_safe_mode_and_apply_skips_dialog_when_clean_exit_true(monkeypatch):
    """前回正常終了していれば、QMessageBox.questionは一切呼ばれない。"""

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("clean_exit=Trueなのにダイアログが表示された")

    monkeypatch.setattr(crash_handler_module.QMessageBox, "question", staticmethod(_fail_if_called))

    result = prompt_safe_mode_and_apply(_FakeSettings(clean_exit=True))

    assert result is False
    assert plugin_api_module.is_safe_mode_enabled() is False


def test_prompt_safe_mode_and_apply_yes_enables_safe_mode(monkeypatch):
    """異常終了検出時、ダイアログでYesを選ぶとセーフモードが有効化される。"""
    monkeypatch.setattr(
        crash_handler_module.QMessageBox, "question",
        staticmethod(lambda *a, **k: crash_handler_module.QMessageBox.StandardButton.Yes),
    )

    result = prompt_safe_mode_and_apply(_FakeSettings(clean_exit=False))

    assert result is True
    assert plugin_api_module.is_safe_mode_enabled() is True


def test_prompt_safe_mode_and_apply_no_leaves_safe_mode_disabled(monkeypatch):
    """異常終了検出時でも、ダイアログでNoを選べばセーフモードは有効化されない。"""
    monkeypatch.setattr(
        crash_handler_module.QMessageBox, "question",
        staticmethod(lambda *a, **k: crash_handler_module.QMessageBox.StandardButton.No),
    )

    result = prompt_safe_mode_and_apply(_FakeSettings(clean_exit=False))

    assert result is False
    assert plugin_api_module.is_safe_mode_enabled() is False
