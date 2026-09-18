"""
プラグイン向けの公開の入口(プラグイン API 2.0)。

プラグインが本体から import してよいのは、ここと graphica.plugin.testing だけ。
本体の内部(core / gui / models)は予告なく動くが、ここの名前はプラグイン API の版で守る。
"""
from core.dataset import Dataset
from core.plugin_api import GraphicaPluginAPI
from core.plugin_context import PluginContext
from core.plugin_manifest import PLUGIN_API_VERSION
from core.plugin_types import AnalysisResult, PluginExecutionError

__all__ = [
    "PLUGIN_API_VERSION",
    "AnalysisResult",
    "Dataset",
    "GraphicaPluginAPI",
    "PluginContext",
    "PluginExecutionError",
]
