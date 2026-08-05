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


@dataclass
class PluginImporter:
    """register_importer() (項目B-1) で登録された1件のインポーター。"""
    extension: str            # 先頭ピリオド付き、小文字(例: ".jdx")
    loader: object            # Callable[[str], pandas.DataFrame]
    name: str                 # 診断表示用の名前(通常は登録元プラグイン名)
    priority: int = 0


@dataclass
class PluginExporter:
    """register_exporter() (項目B-2) で登録された1件のエクスポーター。"""
    format_name: str          # BatchExportDialogの形式コンボボックスに表示される名前
    extension: str            # 先頭ピリオド付き、小文字(例: ".xyz")
    writer: object            # Callable[[matplotlib.figure.Figure, str], None]
    name: str                 # 診断表示用の名前(通常は登録元プラグイン名)


class PluginExecutionError(Exception):
    """
    プラグイン提供のimporter/exporterを実際に実行した際の失敗を表す
    (登録時ではなく実行時、項目B-3)。文字列化すると必ずプラグイン名を含むため、
    既存のエラーダイアログ(QMessageBox.critical/warning)にそのまま渡せば
    「どのプラグインが失敗したか」が自動的に表示される。
    """
    def __init__(self, plugin_name, message):
        self.plugin_name = plugin_name
        self.message = message
        super().__init__(f"[{plugin_name}] {message}")
