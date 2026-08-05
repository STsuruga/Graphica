# core/plugin_types.py
"""
プラグインAPI全体で共有する型(トラック1 フェーズA-1)。

各 register_xxx フックの種別と、登録失敗時のエラー情報を統一した形で
表現する。core/plugin_api.py の GraphicaPluginAPI がこれらを使って
登録失敗をプラグイン単位ではなくフック単位で隔離する(フェーズA-2)。
"""
from dataclasses import dataclass
from enum import Enum


class PluginHookKind(Enum):
    """register_xxx フックの種別。今後のフェーズで追加されるフックもここに列挙する。"""
    IMPORTER = "importer"
    EXPORTER = "exporter"
    PROCESSOR = "processor"
    ANALYZER = "analyzer"
    PANEL = "panel"
    PLOT_TYPE = "plot_type"
    FIT_FUNCTION = "fit_function"       # 既存
    MENU_ACTION = "menu_action"         # 既存
    RENDER_BACKEND = "render_backend"


@dataclass
class PluginRegistrationError:
    """1つのフック登録呼び出しが失敗したことを表す。"""
    plugin_name: str
    hook_kind: PluginHookKind
    message: str
    exception: Exception | None = None
