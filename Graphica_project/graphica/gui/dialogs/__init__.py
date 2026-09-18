# gui/dialogs/__init__.py
"""
このアプリのダイアログ群。

以前は `gui/dialogs.py` 1ファイル(5,560行・47ダイアログ)だった。1ファイルと
して読むには大きすぎ、編集時の競合・検索性・レビューのしやすさに効いてきていた
ため、機能群ごとの6モジュールへ分割した(改善ボード B-2)。

**呼び出し側は変更不要**。従来どおり `from gui.dialogs import ColumnPreviewDialog`
のように書ける(下でまとめて再エクスポートしている)。新しいダイアログを足すときは、
内容に合うモジュールへ置き、ここの `__all__` と import にも1行ずつ足すこと。

| モジュール | 担当 |
|---|---|
| `data_import` | ファイルの取り込み・列の型決め・新規データセット |
| `data_edit`   | 列の計算/文字列操作、行フィルタ、重複X、置換など |
| `analysis`    | フィット・ピーク・ベースライン・積分・規格化・外れ値など |
| `export`      | 画像/一括エクスポート、キャプション生成、色覚シミュレーション |
| `appearance`  | ラベル書式、配色パレット、登録色、凡例順、矢印注釈、インセット |
| `app`         | 環境設定、ヘルプ、ようこそ、コマンドパレット、プラグイン引数など |

分割は**純粋な移動**で、クラスの中身は変えていない。クラス間の参照は4箇所しか
無く(ColumnPreview→ColumnType、MultiPeakFit→PeakSettings、登録色の2つ→
_named_color_icon)、いずれも同じモジュール内に収めてあるため循環importは無い。
"""

# データの取り込み
from gui.dialogs.data_import import (
    ColumnPreviewDialog,
    ColumnTypeDialog,
    ExcelMultiSheetDialog,
    FolderImportDialog,
    NewDatasetDialog,
)

# データの編集・列操作
from gui.dialogs.data_edit import (
    ColumnCalculatorDialog,
    CalcHelpDialog,
    ColumnStringOpsDialog,
    FindReplaceDialog,
    RowFilterDialog,
    ColumnVisibilityDialog,
    DuplicateXDialog,
    ReplicateErrorDialog,
)

# 解析
from gui.dialogs.analysis import (
    FitDialog,
    MultiPeakFitDialog,
    PeakSettingsDialog,
    ResultDialog,
    BaselineCorrectionDialog,
    SavGolDialog,
    IntervalIntegralDialog,
    CumulativeIntegralDialog,
    NormalizeDatasetDialog,
    ResampleDatasetDialog,
    OutlierDetectionDialog,
    HistogramKDEDialog,
    DatasetArithmeticDialog,
    XAxisAlignmentDialog,
)

# エクスポート・出力
from gui.dialogs.export import (
    ExportDialog,
    BatchExportDialog,
    CaptionGeneratorDialog,
    CVDSimulationDialog,
)

# 見た目・注釈
from gui.dialogs.appearance import (
    LabelEditDialog,
    ColorPaletteDialog,
    NamedColorManagerDialog,
    NamedColorPickerDialog,
    LegendOrderDialog,
    ArrowAnnotationDialog,
    InsetDialog,
)

# アプリ全体(設定・ヘルプ・操作)
from gui.dialogs.app import (
    PreferencesDialog,
    HelpDialog,
    AboutDialog,
    WelcomeDialog,
    ShortcutsDialog,
    CommandPaletteDialog,
    QuickAccessManagerDialog,
    AutosaveHistoryDialog,
    PluginParamDialog,
)

__all__ = [
    "AboutDialog",
    "ArrowAnnotationDialog",
    "AutosaveHistoryDialog",
    "BaselineCorrectionDialog",
    "BatchExportDialog",
    "CVDSimulationDialog",
    "CalcHelpDialog",
    "CaptionGeneratorDialog",
    "ColorPaletteDialog",
    "ColumnCalculatorDialog",
    "ColumnPreviewDialog",
    "ColumnStringOpsDialog",
    "ColumnTypeDialog",
    "ColumnVisibilityDialog",
    "CommandPaletteDialog",
    "CumulativeIntegralDialog",
    "DatasetArithmeticDialog",
    "DuplicateXDialog",
    "ExcelMultiSheetDialog",
    "ExportDialog",
    "FindReplaceDialog",
    "FitDialog",
    "FolderImportDialog",
    "HelpDialog",
    "HistogramKDEDialog",
    "InsetDialog",
    "IntervalIntegralDialog",
    "LabelEditDialog",
    "LegendOrderDialog",
    "MultiPeakFitDialog",
    "NamedColorManagerDialog",
    "NamedColorPickerDialog",
    "NewDatasetDialog",
    "NormalizeDatasetDialog",
    "OutlierDetectionDialog",
    "PeakSettingsDialog",
    "PluginParamDialog",
    "PreferencesDialog",
    "QuickAccessManagerDialog",
    "ReplicateErrorDialog",
    "ResampleDatasetDialog",
    "ResultDialog",
    "RowFilterDialog",
    "SavGolDialog",
    "ShortcutsDialog",
    "WelcomeDialog",
    "XAxisAlignmentDialog",
]
