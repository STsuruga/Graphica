"""ダイアログ。呼び出し側は `from graphica.gui.dialogs import X` と書く(ここでまとめて再エクスポートする)。

新しいダイアログは内容に合うモジュールに置き、ここの import と `__all__` にも足すこと。
モジュールどうしは import し合わない(循環 import を避けるため、クラス間の参照は同じモジュールの中に収める)。

| モジュール | 担当 |
|---|---|
| `data_import` | ファイルの取り込み・列の型決め・新規データセット |
| `data_edit`   | 列の計算/文字列操作、行フィルタ、重複X、置換など |
| `analysis`    | フィット・ピーク・ベースライン・積分・規格化・外れ値など |
| `export`      | 画像/一括エクスポート、キャプション生成、色覚シミュレーション |
| `appearance`  | ラベル書式、配色パレット、登録色、凡例順、矢印注釈、インセット |
| `app`         | 環境設定、ヘルプ、ようこそ、コマンドパレット、プラグイン引数など |
"""

# データの取り込み
from graphica.gui.dialogs.data_import import (
    ColumnPreviewDialog,
    ColumnTypeDialog,
    ExcelMultiSheetDialog,
    FolderImportDialog,
    NewDatasetDialog,
)

# データの編集・列操作
from graphica.gui.dialogs.data_edit import (
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
from graphica.gui.dialogs.analysis import (
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
from graphica.gui.dialogs.export import (
    ExportDialog,
    BatchExportDialog,
    CaptionGeneratorDialog,
    CVDSimulationDialog,
)

# 見た目・注釈
from graphica.gui.dialogs.appearance import (
    LabelEditDialog,
    ColorPaletteDialog,
    NamedColorManagerDialog,
    NamedColorPickerDialog,
    LegendOrderDialog,
    ArrowAnnotationDialog,
    InsetDialog,
)

# アプリ全体(設定・ヘルプ・操作)
from graphica.gui.dialogs.app import (
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
