# tests/test_plugin_types.py
"""core/plugin_types.py (トラック1 フェーズA-1) に対する軽量なテスト。"""
from core.plugin_types import PluginHookKind, PluginRegistrationError


def test_plugin_hook_kind_values():
    assert PluginHookKind.FIT_FUNCTION.value == "fit_function"
    assert PluginHookKind.MENU_ACTION.value == "menu_action"


def test_plugin_registration_error_defaults():
    err = PluginRegistrationError(
        plugin_name="my_plugin", hook_kind=PluginHookKind.FIT_FUNCTION, message="失敗しました"
    )
    assert err.plugin_name == "my_plugin"
    assert err.hook_kind is PluginHookKind.FIT_FUNCTION
    assert err.message == "失敗しました"
    assert err.exception is None


def test_plugin_registration_error_carries_original_exception():
    original = ValueError("bad name")
    err = PluginRegistrationError(
        plugin_name="my_plugin", hook_kind=PluginHookKind.MENU_ACTION,
        message=str(original), exception=original,
    )
    assert err.exception is original
