# tests/test_plugin_api_contract.py
"""
FakeGraphicaPluginAPI(core/plugin_testing.py)と本物のGraphicaPluginAPI
(core/plugin_api.py)のpublicメソッドシグネチャが一致していることを機械的に
検証する契約テスト(トラック1 フェーズA-4)。

以降のフェーズで新しい register_xxx を追加するたびに、このテストが
「本物とスタブ両方に実装したか」「引数名まで一致しているか」を強制する。
"""
import inspect

from core.plugin_api import GraphicaPluginAPI
from core.plugin_testing import FakeGraphicaPluginAPI


def _register_method_names(cls):
    return {n for n, _ in inspect.getmembers(cls, inspect.isfunction) if n.startswith("register_")}


def test_fake_api_has_the_same_register_methods_as_the_real_api():
    real_methods = _register_method_names(GraphicaPluginAPI)
    fake_methods = _register_method_names(FakeGraphicaPluginAPI)
    assert real_methods == fake_methods


def test_fake_api_register_method_signatures_match_the_real_api():
    real_methods = _register_method_names(GraphicaPluginAPI)
    for name in real_methods:
        real_sig = inspect.signature(getattr(GraphicaPluginAPI, name))
        fake_sig = inspect.signature(getattr(FakeGraphicaPluginAPI, name))
        assert real_sig.parameters.keys() == fake_sig.parameters.keys(), name
        # デフォルト値も一致していること(例: p0=None, shortcut=None)
        for param_name in real_sig.parameters:
            real_default = real_sig.parameters[param_name].default
            fake_default = fake_sig.parameters[param_name].default
            assert real_default == fake_default, f"{name}.{param_name}"
