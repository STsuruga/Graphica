# tests/test_crash_handler.py
"""gui/crash_handler.py のセーフモード起動プロンプト(項目F-4)に対するテスト。"""
import sys

import pytest

import core.plugin_api as plugin_api_module
import gui.crash_handler as crash_handler_module
from gui.crash_handler import (
    install_crash_handler,
    prompt_safe_mode_and_apply,
    should_prompt_safe_mode,
)


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


# --- install_crash_handler() / _handle_uncaught_exception() ---


def test_install_crash_handler_replaces_sys_excepthook(monkeypatch):
    """install_crash_handler() は sys.excepthook を差し替える(項目29行目)。"""
    sentinel_hook = object()
    monkeypatch.setattr(sys, "excepthook", sentinel_hook)

    install_crash_handler()

    assert sys.excepthook is crash_handler_module._handle_uncaught_exception


def test_handle_uncaught_exception_keyboard_interrupt_delegates_to_original(monkeypatch):
    """KeyboardInterruptは案内ダイアログを出さず、元のexcepthookに委譲する。"""
    calls = []
    monkeypatch.setattr(
        crash_handler_module, "_original_excepthook",
        lambda *a: calls.append(a),
    )
    monkeypatch.setattr(
        crash_handler_module.QMessageBox, "exec",
        lambda self: pytest.fail("KeyboardInterruptなのにダイアログが表示された"),
    )

    exc = KeyboardInterrupt()
    crash_handler_module._handle_uncaught_exception(KeyboardInterrupt, exc, None)

    assert calls == [(KeyboardInterrupt, exc, None)]


def test_handle_uncaught_exception_shows_dialog_for_normal_exception(monkeypatch):
    """通常の未処理例外では、案内ダイアログが構築・表示される。"""
    exec_calls = []
    monkeypatch.setattr(
        crash_handler_module.QMessageBox, "exec",
        lambda self: exec_calls.append(self) or 0,
    )

    try:
        raise ValueError("boom")
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        crash_handler_module._handle_uncaught_exception(exc_type, exc_value, exc_tb)

    assert len(exec_calls) == 1
    shown_box = exec_calls[0]
    assert "予期しないエラー" in shown_box.text()
    assert "boom" in shown_box.detailedText()


def test_handle_uncaught_exception_dialog_failure_is_swallowed(monkeypatch, caplog):
    """案内ダイアログの表示自体が失敗しても、例外を伝播させずログに残すだけにする。"""

    def _raise_on_exec(self):
        raise RuntimeError("dialog display failed")

    monkeypatch.setattr(crash_handler_module.QMessageBox, "exec", _raise_on_exec)

    try:
        raise ValueError("boom")
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        with caplog.at_level("CRITICAL"):
            # 例外を投げずに正常に戻ってくることを確認する。
            crash_handler_module._handle_uncaught_exception(exc_type, exc_value, exc_tb)
