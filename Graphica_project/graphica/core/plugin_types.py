"""プラグイン API で共有する型。登録されたフックの記録と、失敗の表し方。"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class PluginHookKind(Enum):
    IMPORTER = "importer"
    EXPORTER = "exporter"
    PROCESSOR = "processor"
    ANALYZER = "analyzer"
    PANEL = "panel"
    PLOT_TYPE = "plot_type"
    FIT_FUNCTION = "fit_function"
    MENU_ACTION = "menu_action"
    RENDER_BACKEND = "render_backend"


@dataclass
class PluginRegistrationError:
    """register_xxx の1回の呼び出しが失敗したこと。"""
    plugin_name: str
    hook_kind: PluginHookKind
    message: str
    exception: Exception | None = None


@dataclass
class PluginMenuAction:
    text: str
    callback: Callable[..., Any]  # (PluginContext) -> None
    shortcut: str | None
    plugin_name: str


@dataclass
class PluginImporter:
    extension: str            # ピリオド付きの小文字(例: ".jdx")
    loader: Callable[[str], Any]  # (パス) -> pandas.DataFrame
    name: str                 # エラー表示用(通常はプラグイン名)
    priority: int = 0


@dataclass
class PluginExporter:
    format_name: str
    extension: str            # ピリオド付きの小文字
    writer: Callable[[Any, str], Any]  # (matplotlib の Figure, 出力パス) -> None
    name: str


@dataclass
class PluginProcessor:
    name: str
    fn: Callable[[Any, dict[str, Any]], Any]  # (Dataset, 入力値) -> Dataset。元の Dataset は変えない
    category: str
    param_schema: list[dict[str, Any]]  # 入力フォームの定義(register_processor の説明を参照)
    plugin_name: str


@dataclass
class AnalysisResult:
    """
    register_analyzer の fn が返す解析結果。どれも省略できる。

    Attributes:
        table (pandas.DataFrame | None): 結果の表。CSV に保存できる形で表示する。
        annotations (list[dict] | None): 現在の軸に追加する注釈(Undo できる)。
        new_datasets (list[Dataset] | None): 追加するデータセット(Undo できる)。
    """
    table: Any = None
    annotations: list[dict[str, Any]] | None = None
    new_datasets: list[Any] | None = None


@dataclass
class PluginAnalyzer:
    name: str
    fn: Callable[[Any, dict[str, Any]], Any]  # (Dataset, 入力値) -> AnalysisResult
    output_kind: str          # 表示上の分類だけ
    param_schema: list[dict[str, Any]]
    plugin_name: str


@dataclass
class PluginPanel:
    name: str
    widget_factory: Callable[..., Any]  # (PluginContext) -> QWidget。タブごとに1回呼ぶ
    area: str                 # "right"/"left"/"top"/"bottom"。Qt への対応付けは GUI 側(core は Qt に依存しない)
    plugin_name: str


@dataclass
class PluginPlotType:
    type_name: str
    drawer: Callable[..., Any]  # (Dataset, Axes, x, y) -> Artist | None
    requires_2d: bool         # 予約(動作に影響しない)
    plugin_name: str


class RenderBackend:
    """描画バックエンドの型の予約。描画には未接続で、持つべきメソッドも未定。"""


@dataclass
class PluginRenderBackend:
    name: str
    backend: "RenderBackend"
    plugin_name: str


class PluginExecutionError(Exception):
    """プラグインのフックの実行時の失敗。文字列にするとプラグイン名が付くので、そのまま表示に使える。"""

    def __init__(self, plugin_name: str, message: str) -> None:
        self.plugin_name = plugin_name
        self.message = message
        super().__init__(f"[{plugin_name}] {message}")
