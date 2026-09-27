"""DatasetHost と TabPluginContext は本体(PlotterApp)の公開の名前だけを使う。"""
import ast
import inspect

import graphica.gui.datasets.host as host_module
import graphica.gui.plugin_context as plugin_context_module


def _private_uses_of_the_tab(module):
    """self._app._x・app._x・tabs.widget(i)._x のように、タブの非公開の名前を読んでいる所。"""
    tree = ast.parse(inspect.getsource(module))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or not node.attr.startswith("_") or node.attr.startswith("__"):
            continue
        base = ast.unparse(node.value)
        if base in ("self._app", "app") or base.startswith("tabs.widget("):
            offenders.append(f"{module.__name__}:{node.lineno} {base}.{node.attr}")
    return offenders


def test_dataset_host_uses_only_public_names_of_the_tab():
    assert _private_uses_of_the_tab(host_module) == []


def test_plugin_context_uses_only_public_names_of_the_tab():
    assert _private_uses_of_the_tab(plugin_context_module) == []
