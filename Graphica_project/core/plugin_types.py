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


@dataclass
class PluginProcessor:
    """register_processor() (項目C-1) で登録された1件のデータ処理。"""
    name: str                 # メニューに表示される名前
    fn: object                 # Callable[[Dataset, dict], Dataset] (非破壊、新規Datasetを返す)
    category: str              # メニューでのグルーピングに使う
    param_schema: list         # list[dict]。パラメータ入力フォームの自動生成に使う
                                # (例: [{"name": "window", "label": "窓幅", "type": "int",
                                #        "default": 5, "min": 1, "max": 999}])
    plugin_name: str           # 診断表示用の名前(通常は登録元プラグイン名)


@dataclass
class AnalysisResult:
    """
    register_analyzer() (項目C-2) のfnが返す、構造化された解析結果。
    7章-7の方針(結果は文字列ではなく構造化データで保持する)に準拠する。
    """
    table: object = None            # pandas.DataFrame | None。ResultDialogでCSV出力可能に表示する
    annotations: list | None = None  # list[dict] | None。現在の軸にSetAnnotationsCommand経由で追加する
    new_datasets: list | None = None  # list[Dataset] | None。AddDatasetCommand経由で非破壊に追加する


@dataclass
class PluginAnalyzer:
    """register_analyzer() (項目C-2) で登録された1件の解析処理。"""
    name: str                  # メニューに表示される名前
    fn: object                  # Callable[[Dataset, dict], AnalysisResult]
    output_kind: str            # "table" 等、解析結果の主な性質を表す(現状は表示上の分類用途)
    param_schema: list          # list[dict]。PluginProcessorのparam_schemaと同じ形式
    plugin_name: str            # 診断表示用の名前(通常は登録元プラグイン名)


@dataclass
class PluginPanel:
    """
    register_panel() (項目D-1) で登録された1件のプラグイン製ドックパネル。
    widget_factoryはタブ(PlotterAppインスタンス)ごとに個別に呼ばれる
    (register_dockは別フックにせず、このフックに統合する方針)。
    """
    name: str                  # パネルのタイトル(ドックのタイトルバー・表示メニューに使う)
    widget_factory: object     # Callable[[ProjectModel, QUndoStack], QWidget]
    area: str                  # "right"/"left"/"top"/"bottom"。Qt.DockWidgetAreaへの
                                # マッピングはGUI側(coreはPySide6に依存しないため)
    plugin_name: str           # 診断表示用の名前(通常は登録元プラグイン名)


@dataclass
class PluginPlotType:
    """register_plot_type() (項目D-2) で登録された1件のプラグイン製プロット種別。"""
    type_name: str             # ds.plot_typeに設定される値、データセットプロパティの
                                # プロット種別コンボボックスに表示される名前でもある
    drawer: object              # Callable[[Dataset, Axes, np.ndarray, np.ndarray], Artist | None]
                                # (dataset, ax, x_data, y_data) -> 描画したArtist(凡例用、無ければNone)
    requires_2d: bool           # 現状は表示上の分類用途のみ(将来の2Dマップ系プラグインplot_type向け)
    plugin_name: str           # 診断表示用の名前(通常は登録元プラグイン名)


class PluginExecutionError(Exception):
    """
    プラグイン提供のフック(importer/exporter/processor/analyzer)を実際に実行した
    際の失敗を表す(登録時ではなく実行時、項目B-3)。文字列化すると必ずプラグイン名を
    含むため、既存のエラーダイアログ(QMessageBox.critical/warning)にそのまま渡せば
    「どのプラグインが失敗したか」が自動的に表示される。
    """
    def __init__(self, plugin_name, message):
        self.plugin_name = plugin_name
        self.message = message
        super().__init__(f"[{plugin_name}] {message}")
