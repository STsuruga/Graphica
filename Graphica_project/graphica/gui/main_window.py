import os
import io
import re
import types
import sys
import logging
import json
import base64
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 指数表記 (1e-5, -2.3E+10 など) を入力途中の状態も含めて許容するための正規表現
# (X/Y軸の最小値・最大値・目盛り間隔スピンボックスの validate() 上書きで使用)
_SCIENTIFIC_INPUT_RE = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)?([eE][+-]?\d*)?$')


def _scientific_text_from_value(self, value):
    """
    値を「一般的な('g')」形式の文字列に変換するカスタムメソッド。
    不要な末尾のゼロを自動的に削除し、必要に応じて指数表記を使います。
    .16g は float64 (倍精度浮動小数点数) の最大有効桁数(約16桁)を
    保持することを意味します。
    """
    return f'{value:.16g}'


def _scientific_validate(self, text, pos):
    """
    指数表記 (例: "1e-5", "-2.3E+10") を1文字ずつ入力できるようにする
    バリデータ。QDoubleSpinBox 標準の validate() は "1e" や "1e-" のような
    入力途中の文字列を Invalid として弾いてしまい、指数表記を
    キーボードから直接入力できないため、これを上書きする。
    """
    if text == '' or text in ('-', '+'):
        return (QValidator.State.Intermediate, text, pos)
    if _SCIENTIFIC_INPUT_RE.match(text):
        try:
            float(text)
            return (QValidator.State.Acceptable, text, pos)
        except ValueError:
            return (QValidator.State.Intermediate, text, pos)
    return (QValidator.State.Invalid, text, pos)


def _enable_scientific_notation_input(spin_box, minimum, maximum, single_step=0.1):
    """
    QDoubleSpinBox が指数表記 (1e-5 など) を表示・入力できるようにする共通ヘルパー。
    軸の最小値/最大値 (負値も可) と、目盛り間隔 (0以上のみ) の両方で使う。
    """
    spin_box.setDecimals(SPIN_BOX_MAX_DECIMALS)
    spin_box.setRange(minimum, maximum)
    spin_box.textFromValue = types.MethodType(_scientific_text_from_value, spin_box)
    spin_box.validate = types.MethodType(_scientific_validate, spin_box)
    spin_box.setSingleStep(single_step)


def _strip_trailing_colon_from_labels(widget):
    """
    widget配下の全QLabelについて、末尾の全角コロン「：」を取り除く(実機
    フィードバック: 「各設定項目のあとの：はなくして」)。ui_main_window.py
    (Qt Designer/pyside6-uic生成物)のretranslateUi()には多くのフォーム
    ラベルにこの記号が焼き込まれているが、.uiソースファイル自体がこの
    リポジトリに存在せず再生成できないため、構築完了後にQLabel.text()を
    上書きする形で対応する(呼び出しは動的に追加されたラベルも全て構築
    済みの、__init__の最後の方で行うこと)。
    """
    from PySide6.QtWidgets import QLabel
    for label in widget.findChildren(QLabel):
        text = label.text()
        if text.endswith('：'):
            label.setText(text[:-1])

# --- ウィンドウ/レイアウトに関する定数 ---
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 800
CONTROL_DOCK_WIDTH = 472  # 項目68/61: フィールドの見切れ解消のため実測ベースで拡幅(旧350px→380px→400px→440px)
                          # ★ バグ修正(項目102の折りたたみ化で発覚): 440pxのままだと、
                          #   縦スクロールバー(11px)+レイアウト余白の分だけ中身の最小幅を
                          #   下回り、意図しない横スクロールバーが常時出てしまっていた。
                          #   スクロールバー分の余裕を持たせて拡幅する(merged_properties_layout
                          #   の余白圧縮と合わせて横スクロールバーが出ないことを実測確認済み)。
EXPORT_PREVIEW_DOCK_INITIAL_HEIGHT = 340  # エクスポートプレビューを下部ドックに分離した際の初期高さ
SPIN_BOX_MAX_DECIMALS = 16

# --- 項目C-907: データセットリストの表示/非表示トグル(目のアイコン)関連の定数 ---
# 列インデックス自体(DATASET_TREE_NAME_COLUMN/DATASET_TREE_VISIBILITY_COLUMN)は
# dataset_mixin.py からも参照するため gui/dataset_style_icon.py 側で定義している
# (main_window <-> dataset_mixin の循環import回避、同モジュールの他ヘルパーと同じ理由)。
DATASET_TREE_VISIBILITY_COLUMN_WIDTH = 26  # 目アイコン(16px)+クリック余白

# --- 項目86: マルチモニター対応(Canvasの別ウィンドウ切り離し)に関する定数 ---
CANVAS_DETACHED_GEOMETRY_KEY = "canvas_detached_geometry"  # 切り離しウィンドウのサイズ/位置
CANVAS_WAS_DETACHED_KEY = "canvas_was_detached"  # 前回終了時に切り離されていたか
DEFAULT_DETACHED_CANVAS_WIDTH = 900
DEFAULT_DETACHED_CANVAS_HEIGHT = 700

# ドックの既定配置のバージョン。デフォルトの配置(どのドックをどのエリアに
# 置くか)を変更したときはこの値を上げる。QSettingsに保存された前回のバージョンと
# 異なる場合、保存済みの window_state を復元せず新しい既定配置を優先する
# (そうしないと、restoreState() で常に旧配置が復元され続け、コード側で
# デフォルトのドック配置を変えても既存ユーザーには反映されない)。
DOCK_LAYOUT_VERSION = 4  # v4: 「プロットのプロパティ」「データセットのプロパティ」を1つのドックに統合

# ドックレイアウトの名前付きプリセット(項目152、C-911)。上のwindow_state
# (起動時に自動保存/復元される「直近の」1つの状態)とは別の、ユーザーが
# 明示的に名前を付けて保存する複数のプリセットを保持するQSettingsキー。
DOCK_LAYOUT_PRESETS_SETTINGS_KEY = "dock_layout_presets"

# 「データセットのプロパティ」パネルのサブセクション(改善ボード C-1)。
# Designer生成分+実行時追加で39行が1本のQFormLayoutに縦積みになっており、
# プロット種別や2Dマップのトグルひとつでパネル高さが763px〜1134pxまで
# 伸縮していた(実測)。7つの折りたたみ可能なセクションに分け、伸縮する
# ブロック(グラデーション/ウォーターフォール/2Dマップ)がそれぞれ自分の
# 見出しの中で開閉するようにする。
#
# ★ このタプルが唯一の定義元。新しい行を足すときは、対応するセクションの
#   キーを _prop_form() に渡すだけでよく、番号指定の insertRow(N, ...) は
#   もう存在しない(旧 formLayout_4 の「実行順に依存した番号指定挿入」という
#   地雷は、この分割で丸ごと無くなっている)。
DATASET_PROPERTY_SECTIONS = (
    ('data',      'データ列'),
    ('style',     '基本スタイル'),
    ('gradient',  'グラデーション'),
    ('waterfall', 'ウォーターフォール'),
    ('map',       '2Dマップ・値による配色'),
    ('extra',     '表示の追加要素'),
    ('place',     '配置・情報'),
)

# 折りたたみ状態の永続化キー。既定は「全セクション展開」で、ユーザーが
# 閉じたセクションのキーだけをJSON配列として保存する(=キーが無い/空なら
# 従来と同じ全展開。新しいセクションを足しても既定は展開のまま)。
DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY = "dataset_property_collapsed_sections"

# プラグインが register_plot_type() で登録する種別名は任意長のため、
# 何も対策しないと plot_type_combo の sizeHint が最長項目に合わせて広がり、
# QFormLayout の列幅を通じてプロパティドックに横スクロールバーが出る
# (D-2 で実際に踏んだ。当時は組み込み種別名を15文字に縮めて回避した)。
# コンボ自身の希望幅をこの文字数ぶんに固定し、長い名前は省略表示させる。
PLOT_TYPE_COMBO_MIN_CHARS = 16

# 2Dマップ(ヒートマップ、項目C-508)のカラーマップ選択肢。matplotlib組み込みの
# 連続カラーマップから、科学データの可視化でよく使われるものを厳選(全カラーマップを
# 網羅すると選択肢が多すぎて選びにくくなるため)。'viridis'を既定にしているのは
# matplotlib自体の既定カラーマップであり、知覚的に均等(perceptually uniform)で
# 色覚多様性にも配慮された設計のため。
COLORMAP_CHOICES = [
    'viridis', 'plasma', 'inferno', 'magma', 'cividis',
    'coolwarm', 'RdBu', 'seismic', 'jet', 'turbo',
    'gray', 'Blues', 'Greens', 'Reds', 'YlOrRd',
]

# --- オートセーブに関する定数 ---
DEFAULT_AUTOSAVE_INTERVAL_MIN = 5  # 分単位 (0 = 無効化)
MIN_AUTOSAVE_INTERVAL_MIN = 0
MAX_AUTOSAVE_INTERVAL_MIN = 180
AUTOSAVE_FILENAME = "autosave.graphica"  # 新規インストール/セッションは新形式(JSON)でオートセーブする
AUTOSAVE_GENERATIONS = 3  # 保持する世代数 (最新のautosave.graphicaを含む)

# --- 最近使ったファイル一覧に関する定数 ---
MAX_RECENT_FILES = 10

# --- ドラッグ&ドロップでの複数ファイル一括読み込みに関する定数 ---
# gui/workers.py の read_data_file() が実際に読み込める拡張子のみを許可する
# (ファイルダイアログのフィルタと同じ一覧を gui/workers.py から共有する)
from graphica.gui.workers import BUILTIN_DATA_FILE_EXTENSIONS  # noqa: E402
SUPPORTED_DATA_FILE_EXTENSIONS = BUILTIN_DATA_FILE_EXTENSIONS

# 未保存の変更の確認ダイアログ(v1.4.2)を無効にする環境変数。テストスイートは
# ウィンドウを大量に作って閉じるため、モーダルな確認が出るとそこで止まってしまう。
# tests/conftest.py が "0" を設定する(この機能自体のテストは個別に "1" に戻す)。
UNSAVED_CHANGES_PROMPT_ENV = "GRAPHICA_CONFIRM_UNSAVED_CHANGES"


def _unsaved_changes_prompt_enabled():
    return os.environ.get(UNSAVED_CHANGES_PROMPT_ENV, "1") != "0"

# --- PySide6 ---
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QFileDialog,
                               QComboBox, QLabel, QSpinBox, QDoubleSpinBox, QPushButton,
                               QTextEdit, QCheckBox, QGroupBox, QSizePolicy, QWidget,
                               QDockWidget, QScrollArea, QMessageBox,
                               QLineEdit, QHBoxLayout, QFormLayout, QAbstractItemView,
                               QDialog, QTreeWidget, QTreeWidgetItem, QGridLayout,
                               QInputDialog, QMenu, QFrame, QToolButton, QWidgetAction,
                               QStyledItemDelegate, QStyleOptionViewItem, QStyle, QHeaderView)
from PySide6.QtGui import QFont, QIcon, QAction, QValidator, QUndoStack, QPainter, QPainterPath
from PySide6.QtCore import Qt, QTimer, QSettings, QSize, Signal, QRectF, QByteArray
from graphica.models.project import ProjectModel
from graphica.core.version import APP_NAME, __version__
from graphica.core.i18n import tr, set_language, DEFAULT_LANGUAGE
from graphica.core.plugin_api import load_plugins_once, get_registered_importer_extensions
from graphica.core.plugin_types import PluginExecutionError
from graphica.gui.datasets.colors import ColorController
from graphica.gui.datasets.transfer import TransferController
from graphica.gui.datasets.overlays import OverlayController
from graphica.gui.datasets.plugin_runs import PluginRunController
from graphica.gui.datasets.property_panel import DatasetPropertyPanel
from graphica.gui.datasets.fitting import FittingController
from graphica.gui.datasets.host import DatasetHost
from graphica.gui.datasets.peaks import PeakController
from graphica.gui.datasets.processing import ProcessingController
from graphica.gui.plugin_context import TabPluginContext
from graphica.core.app_paths import get_app_data_dir, get_user_plugins_dir

# --- Matplotlib ---
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

# --- Qt Designer から生成された UI ---
# ※ main_window.py と同じ階層ではなく大元のフォルダにあるため、そのままインポートできます
from graphica.ui_main_window import Ui_MainWindow

# --- 自分で分割したモジュール ---
from graphica.core.dataset import Dataset, COLOR_BY_COLUMN_PLOT_TYPE
from graphica.core.unit_conversion import X_AXIS_UNIT_CHOICES, X_AXIS_UNIT_LABELS
from graphica.core.commands import AddDatasetCommand, RemoveDatasetCommand
from graphica.gui.canvas import (MplCanvas, DEFAULT_POINT_LABEL_MAX_POINTS, DEFAULT_MAJOR_TICK_LENGTH,
                        MINOR_TICK_LENGTH_AUTO)
from graphica.gui.minimap_widget import MinimapWidget
from graphica.gui.detached_canvas_window import DetachedCanvasWindow
from graphica.gui import theme
from graphica.gui.theme import apply_form_spacing
from graphica.gui.workers import load_data_file_task, excel_engine_for, is_excel_file
from graphica.gui.task_runner import TaskRunner
from graphica.gui.dialogs import (ColumnPreviewDialog, ExcelMultiSheetDialog, WelcomeDialog,
                         FolderImportDialog, AutosaveHistoryDialog)
from graphica.gui.color_picker_widget import ColorPickerWidget
from graphica.gui.icon_utils import load_svg_icon, ICONS_DIR

# キャンバス上部ツールバーのアイコンサイズ(px)。Qtの既定は24pxだが、
# カスタムボタンを追加した結果、ウィンドウ幅が狭いときにツールバーが溢れ、
# はみ出したボタンが極小の「>>」に押し込まれて事実上操作できなくなっていた。
# アプリ内の他のアイコンのみボタン(18px)ともトーンを揃える。
TOOLBAR_ICON_SIZE = 18

# 項目81(mathtext拡充): タイトル/軸ラベルの文字装飾パネルに追加する
# ギリシャ文字・記号のパレット。(表示するグリフ, 挿入するmathtextマクロ名
# [バックスラッシュ抜き]) のタプル。マクロは matplotlib mathtext がそのまま
# 解釈できるもの(\alpha 等)のみを収録している(\sqrt{...}のように引数を
# 必須とするマクロは、単純な「$\macro$」挿入方式と相性が悪いため対象外。
# 平方根は引数不要な\surdで代用している)。
# 前半16個はギリシャ文字、後半16個は実機フィードバック(「四則演算の記号とか
# プロットでよく使う数学記号があるといいかも」)を受けて追加した算術・数学記号。
LABEL_SYMBOL_PALETTE = [
    ("α", "alpha"), ("β", "beta"), ("γ", "gamma"), ("δ", "delta"),
    ("ε", "epsilon"), ("μ", "mu"), ("π", "pi"), ("ρ", "rho"),
    ("Σ", "Sigma"), ("σ", "sigma"), ("τ", "tau"), ("Ω", "Omega"),
    ("ω", "omega"), ("Δ", "Delta"), ("θ", "theta"), ("φ", "phi"),
    ("×", "times"), ("÷", "div"), ("±", "pm"), ("∓", "mp"),
    ("≈", "approx"), ("≠", "neq"), ("≤", "leq"), ("≥", "geq"),
    ("∞", "infty"), ("→", "rightarrow"), ("←", "leftarrow"), ("∂", "partial"),
    ("∇", "nabla"), ("∫", "int"), ("∝", "propto"), ("°", "degree"),
    # ★ 実機フィードバック: ハイフン(-)やen dash(–)ではなく、正しい
    #   マイナス記号(U+2212、通常のハイフンより長く中央揃えの符号)を
    #   挿入したいとの要望。mathtextのマクロではなく生の文字そのものを
    #   挿入したいので、macro=Noneにして_insert_symbol()側で
    #   $...$のmathtext包装をせず素のテキストとして挿入させる。
    ("−", None),
]


def _svg_icon(name, size=20):
    """
    assets/icons/{name}.svg を統一トーンのQIconとして読み込む共通ヘルパー。
    色は呼び出しの都度、現在のテーマ(gui.theme.current_tokens())の
    text_secondaryトークンから解決する(gui/icon_utils.py の icon() と同じ方針、
    項目H-4)。ボタン/アクションに一度setIcon()した後は、テーマが変わっても
    自動更新はされないため、永続的なウィジェット(メインツールバーのボタン等)
    については_on_toggle_dark_mode側で明示的に再設定する
    (_refresh_custom_svg_icons、gui/mixins/ui_setup_mixin.py参照)。
    """
    from graphica.gui import theme
    color = theme.current_tokens()["text_secondary"]
    return load_svg_icon(resource_path(os.path.join(ICONS_DIR, f"{name}.svg")),
                          color=color, size=size)


def find_unevaluated_formula_cells(file_path, sheet_name=None, max_examples=5, max_scan_cells=200_000):
    """
    core.excel_utils.find_unevaluated_formula_cells() への遅延importラッパー。

    core.excel_utils はopenpyxlに依存しており、これをモジュール先頭でimportすると
    Excelを一切扱わない起動時にも毎回openpyxlの読み込みコストがかかってしまう
    (実測 約350ms)。Excelファイルを実際に読み込む時(_import_loaded_dataframe内)
    にだけ発生するよう、呼び出しの都度ここでimportする。関数名・シグネチャを
    そのまま維持しているのは、既存テストが
    monkeypatch.setattr(main_window_module, "find_unevaluated_formula_cells", ...)
    でこのモジュール属性を直接差し替える前提になっているため。
    """
    from graphica.core.excel_utils import find_unevaluated_formula_cells as _impl
    return _impl(file_path, sheet_name, max_examples, max_scan_cells)


from graphica.gui.export_preview_panel import ExportPreviewPanel
from graphica.gui.residual_panel import ResidualPanel
from graphica.gui.provenance_panel import ProvenancePanel
from graphica.gui.dataset_style_icon import (
    make_dataset_style_icon, make_dataset_visibility_icon, apply_dataset_visibility_text_style,
    DATASET_TREE_NAME_COLUMN, DATASET_TREE_VISIBILITY_COLUMN,
)
from graphica.gui.mathtext_preview import FitWidthPixmapLabel, JP_CAPABLE_FONT_FAMILIES
from graphica.gui.color_history import load_recent_colors_into_picker

# グラフ内テキスト(目盛り・軸ラベル・凡例)の既定フォント。
# アプリのUIフォント(main.py の APP_FONT_FAMILIES)とは意図的に別系統にしている:
# matplotlibは独自のフォント探索(freetypeベースのキャッシュ)を使うため、
# Qt/Windowsの「UI専用」フォントバリアント("Yu Gothic UI"等)を渡すと解決できず
# 文字化けする。"Yu Gothic"は実ファイルとして存在しmatplotlibからも解決できる。
# ★ 単一フォント名ではなくフォールバックリスト(gui/mathtext_preview.py の
#   JP_CAPABLE_FONT_FAMILIESを再利用)にしているのは、"Yu Gothic"がWindows
#   専用フォントでmacOSには存在しないため。QFont.setFamilies()でこのリストを
#   丸ごとQFontに設定し、matplotlib側にもリストのまま(familyキーワードに
#   list)渡すことで、matplotlib 3.6+のフォントフォールバック機構により先頭
#   から順にグリフを持つフォントが選ばれる(実在しないフォント名は黙って
#   スキップされるだけなので、複数OS分の候補を並べておいて害はない)。
PLOT_DEFAULT_FONT_FAMILIES = JP_CAPABLE_FONT_FAMILIES


def _make_default_plot_font():
    """PLOT_DEFAULT_FONT_FAMILIES(フォールバックリスト)を設定したQFontを作る。

    QFont(str)コンストラクタは単一のフォント名しか受け付けないため、
    setFamilies()で複数候補を丸ごと設定する。
    """
    font = QFont()
    font.setFamilies(PLOT_DEFAULT_FONT_FAMILIES)
    return font

# --- 責務ごとに分割した Mixin (God Object 化を避けるための構成) ---
from graphica.gui.mixins.ui_setup_mixin import UISetupMixin
from graphica.gui.mixins.settings_mixin import SettingsMixin
from graphica.gui.mixins.dataset_mixin import DatasetMixin
from graphica.gui.mixins.mouse_mode_mixin import MouseModeMixin
from graphica.gui.mixins.cursor_mixin import CursorMixin
from graphica.gui.mixins.annotation_mixin import (
    AnnotationMixin, DEFAULT_SNAP_TO_GRID_ENABLED, DEFAULT_SNAP_GRID_INTERVAL_PX
)
from graphica.gui.mixins.layout_edit_mixin import LayoutEditMixin, MIN_FREE_RECT_SIZE
from graphica.gui.mixins.range_select_mixin import RangeSelectMixin
from graphica.gui.mixins.peak_placement_mixin import PeakPlacementMixin
from graphica.gui.mixins.slice_extraction_mixin import SliceExtractionMixin
from graphica.gui.mixins.region_highlight_mixin import RegionHighlightMixin
from graphica.gui.mixins.export_mixin import ExportMixin
from graphica.gui.mixins.project_io_mixin import ProjectIOMixin
from graphica.gui.mixins.help_mixin import HelpMixin
from graphica.gui.mixins.quick_access_mixin import QuickAccessMixin


def resource_path(relative_path):
    """
    .exe化された場合に、一時フォルダ内のリソースへの絶対パスを取得する。

    .py での実行時は、カレントディレクトリ(cwd)ではなく、このファイル
    (gui/main_window.py)自身の場所を基準にプロジェクトルート
    (Graphica_project) を求める。★ 以前は os.path.abspath(".") を使っており、
    「Graphica_project をカレントディレクトリにして起動する」という暗黙の
    前提に依存していたため、IDE等の設定次第でcwdがそれ以外の場所になると
    アイコン等のリソースが一切読み込めなくなる問題があった(項目67/70の
    アイコンが表示されない、という report で発覚)。
    """
    try:
        # PyInstaller が作成する一時フォルダ
        base_path = sys._MEIPASS
    except AttributeError:
        # .py での実行時: このファイル(gui/main_window.py)から見て1つ上
        # (gui/ の親、= Graphica_project) をプロジェクトルートとする
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)


def is_frozen():
    """PyInstallerでexe化されたビルドとして実行されているかどうか。"""
    return hasattr(sys, '_MEIPASS')


def plugin_search_paths():
    """
    プラグインの探索先(優先順)。同梱の plugins(同梱サンプル)と、利用者のフォルダ
    (%LOCALAPPDATA%\\Graphica\\plugins、zip からのインストール先)。
    同梱のフォルダはソースから動かすときにだけあり、配布版と pip 版には無いので、あるときだけ加える
    (探索先は起動時に作られるので、無いものを渡すと site-packages の中に作ろうとしてしまう)。
    """
    paths = []
    bundled = resource_path("plugins")
    if not is_frozen() and os.path.isdir(bundled):
        paths.append(bundled)
    paths.append(get_user_plugins_dir())
    return paths


DISABLED_PLUGINS_SETTINGS_KEY = "disabled_plugins"


def disabled_plugin_names(settings):
    """
    QSettingsから、プラグイン管理UI(項目F-2)で個別に無効化されたプラグイン名の
    集合を読み出す。get_recent_files()と同様、要素数1のリストがQSettings上では
    単一の文字列として返ってくることがあるため補正する。
    """
    names = settings.value(DISABLED_PLUGINS_SETTINGS_KEY, [])
    if isinstance(names, str):
        names = [names]
    return set(names) if names else set()


# register_panel() (項目D-1) の area 文字列 -> Qt.DockWidgetArea のマッピング。
# coreはPySide6に依存しないため、この変換はGUI側(ここ)で行う。
_PLUGIN_PANEL_AREA_MAP = {
    "right": Qt.DockWidgetArea.RightDockWidgetArea,
    "left": Qt.DockWidgetArea.LeftDockWidgetArea,
    "top": Qt.DockWidgetArea.TopDockWidgetArea,
    "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
}

class _DatasetTreeSelectionDelegate(QStyledItemDelegate):
    """
    dataset_list_widget専用のアイテムデリゲート(項目H-2-2、実機フィードバックで
    複数回の調整を経て導入)。

    QSSの `QTreeWidget::item:selected { background: ...; border-radius: ...px; }`
    だけでは、選択時のハイライトを「アイコン列+テキスト列にまたがる単一の
    角丸矩形」として描画できない。Qt(Fusionスタイル)は、CE_ItemViewItemの
    描画時にデコレーション(アイコン)列とテキスト(display)列をそれぞれ独立した
    矩形として扱い、::item:selectedのbackground/border-radiusを両方に別々に
    適用するため、2つの矩形の角丸がわずかにズレて隙間が生じる(実機でピクセルを
    直接比較して確認済み。border-radiusを0にすれば隙間自体は消えるが、今度は
    行の見た目が完全な直角になり、リスト自体の角丸(border-radius: 8px)と
    揃わなくなる)。

    そのため、選択時の背景描画だけはこのデリゲートで自前に行う: paint()の中で
    選択状態を検知したら先に単一のQPainterPathで角丸矩形を1回だけ塗り、その後
    option.stateからState_Selectedを外してから基底実装に委譲することで、Qt標準の
    (2矩形に分かれた)選択背景描画を無効化する。アイコン・テキスト自体の描画は
    引き続き基底実装(QStyledItemDelegate.paint)に任せる。
    """

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        if opt.state & QStyle.StateFlag.State_Selected:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # ★ opt.rect はデコレーション(アイコン)+テキスト部分だけの矩形で、
            #   分岐(展開矢印)用インデント列の分だけ左端が空く(実機フィードバックで
            #   「ここの隙間」として指摘された)。インデント列はこのリストでは
            #   何も描画されない(::item:selectedのbackgroundをtransparentに
            #   している)ため、左端をビューポートの0まで伸ばしてハイライトで
            #   埋めても他の描画と衝突しない。
            rect = QRectF(opt.rect)
            rect.setLeft(0)
            path = QPainterPath()
            path.addRoundedRect(
                rect, theme.DATASET_LIST_ITEM_RADIUS, theme.DATASET_LIST_ITEM_RADIUS
            )
            painter.fillPath(path, theme.current_selection_highlight_qcolor())
            painter.restore()
            # ★ 基底実装(super().paint)がQt標準の選択背景を重ねて描画しないよう、
            #   ここでフラグを落としてから委譲する。アイコン/テキストの見た目は
            #   選択・非選択で変えていないため(色は{text_primary}で共通)、
            #   これによる副作用は無い。
            opt.state &= ~QStyle.StateFlag.State_Selected

        super().paint(painter, opt, index)


class _ClickableMathPreviewLabel(FitWidthPixmapLabel):
    """
    タイトル/X軸ラベル/Y軸ラベル欄の見た目を担う、クリックで編集ダイアログを
    開くプレビューラベル(項目H-2-4追加分、実機フィードバック: 「画像の
    テキスト欄をクリックしたらポップアップが展開するようにして」「mathtextを
    翻訳した形式をプレビューしといて」)。

    実データは引き続き(非表示にした)元のQLineEditが保持している
    (`_open_label_edit_dialog`が直接読み書きする対象、`textChanged`シグナルも
    そのまま生きている)。このラベルは「クリックで開く」トリガーと
    「レンダリング済みプレビューの表示」だけを担当する、見た目専用の
    軽量ウィジェット。表示の幅フィット処理はFitWidthPixmapLabel(gui/
    mathtext_preview.py)から継承している。
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mathtext_preview_label")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setToolTip(tr("クリックして編集"))
        # ★ QLabelは既定でマウスホバーの追跡をしないため、QSSの:hover疑似
        #   クラス(hover時に枠線をselection_accentへ)が反映されない。
        #   WA_Hover属性を明示的に有効化する必要がある(QPushButton/
        #   QToolButtonなどは既定で有効だが、QLabelのような一般的な
        #   QWidgetでは無効)。
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _insert_form_row_after(form, anchor, *row):
    """
    form の、anchor(ラベルか欄のウィジェット)がある行の次に行を入れる。
    行番号で入れると、ほかの挿入の順番が変わったときに黙って別の位置に入る。
    """
    anchor_row, _ = form.getWidgetPosition(anchor)
    if anchor_row < 0:
        raise ValueError(f"{anchor!r} は {form.objectName()} にありません")
    form.insertRow(anchor_row + 1, *row)


# 1つのタブ。機能ごとの mixin の役割は CLAUDE.md の「PlotterApp mixin composition」
class PlotterApp(QMainWindow, UISetupMixin, SettingsMixin, DatasetMixin,
                  MouseModeMixin,
                  CursorMixin, AnnotationMixin, LayoutEditMixin, RangeSelectMixin,
                  PeakPlacementMixin, SliceExtractionMixin, RegionHighlightMixin,
                  ExportMixin, ProjectIOMixin, HelpMixin, QuickAccessMixin):
    """
    メインアプリケーションウィンドウクラス。
    QMainWindow を継承し、ui_main_window.py からロードしたUI骨格に、
    MplCanvas (グラフ) や動的なコントロールUIを組み込みます。
    """

    # 複数プロジェクトタブ(項目40)で、外側のMainAppWindowがタブのタイトル
    # (プロジェクト名)を追従表示するために、保存/読込のたびに発行するシグナル。
    project_state_changed = Signal()

    def __init__(self, run_startup_checks=True, tab_id=None):
        """
        画面を組み立てる。組み立ての各段は後の段が前の段で作った部品を使うので、呼ぶ順番は変えない。

        Args:
            run_startup_checks (bool): オートセーブからの復元確認・初回の案内・ドック配置の復元と保存・
                clean_exit の管理をするか。アプリ全体で1回だけ意味を持つので、2つ目以降のタブでは False。
            tab_id (int, optional): 2つ目以降のタブの番号。オートセーブのファイル名が重ならないようにする。
                None なら autosave.graphica。
        """
        super().__init__()
        self._run_startup_checks = run_startup_checks
        self.tab_id = tab_id
        # 保存先のフォルダは self.settings を作った後に _update_autosave_path で決める
        self._autosave_base_filename = (
            AUTOSAVE_FILENAME if not tab_id
            else f"autosave_tab{tab_id}{os.path.splitext(AUTOSAVE_FILENAME)[1]}"
        )
        self._autosave_filename = self._autosave_base_filename

        self._load_designer_ui()
        self._init_state()
        self._setup_window()
        self._build_canvas_and_toolbar()
        self._setup_status_bar()
        self._build_dataset_color_picker()
        self._build_dataset_list_buttons()
        self._build_dataset_style_controls()
        self._build_legend_location_control()
        self._build_fit_info_and_stats()
        self._build_secondary_y_controls()
        self._build_tick_grid_and_colorbar_controls()
        self._build_tick_format_controls()
        self._build_label_editors()
        self._add_subplot_target_row()
        self._arrange_property_docks()
        self._rebuild_label_tab()
        self._connect_and_initialize()

    def _load_designer_ui(self):
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # ui_main_window.py は生成物なので、Designer に無い種類はここで足す
        self.ui.plot_type_combo.addItem("Area")
        self.ui.plot_type_combo.addItem("Bar")
        self.ui.plot_type_combo.addItem("Step")
        self.ui.plot_type_combo.addItem("Density Scatter")
        self.ui.plot_type_combo.addItem(COLOR_BY_COLUMN_PLOT_TYPE)

        # フォルダ分けのため、Designer の QListWidget を同じ位置の QTreeWidget に差し替える
        self._replace_dataset_list_with_tree()

        self.project = ProjectModel()
        # 新しい変更の経路が project.notify_changed() だけで描き直せるように(既存の箇所は _update_plot を直接呼ぶ)
        self.project.changed.connect(self._update_plot)
        self.settings = QSettings("Graphica", "Graphica")
        self._update_autosave_path()
        load_recent_colors_into_picker(self.settings)

        # 以降に作るメニューやボタンの tr() に効くので、画面を組み立てる前に
        set_language(self.settings.value("language", DEFAULT_LANGUAGE))

        # 起動時に False にし、正常に閉じたときだけ closeEvent で True に戻す。次の起動で False なら異常終了とみなし、
        # オートセーブからの復元を勧める。アプリ全体で1つの値なので、2つ目以降のタブは触らない
        if self._run_startup_checks:
            self._had_clean_exit = self.settings.value("clean_exit", True, type=bool)
            self.settings.setValue("clean_exit", False)
        else:
            self._had_clean_exit = True

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        icon_path = resource_path("Graphica.ico")
        self.setWindowIcon(QIcon(icon_path))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.ui.control_dock_widget)

    def _init_state(self):
        # 非モーダルのダイアログとバックグラウンドの処理は、回収されないよう参照を持っておく
        self.data_editor_dialog = None
        self.help_dialog = None
        self.calc_help_dialog = None
        self._data_load_task_runner = None
        self._batch_export_task_runner = None
        self._update_check_task_runner = None
        # 複数ファイルをまとめて読み込むときの待ち行列と進捗
        self._data_load_queue = []
        self._data_load_queue_total = 0
        self._data_load_queue_done = 0
        # フォルダからの一括取り込みで、ファイル名から列を取り出す正規表現。待ち行列を使い切ったら None に戻す
        self._batch_import_filename_regex = None
        # 上書き保存先。None なら manual_save() は「名前を付けて保存」になる。
        # タブ名もこの値から作る(ProjectModel.current_filepath はオートセーブでも変わる)。
        self._current_project_path = None
        self._restored_unsaved = False  # オートセーブから復元し、まだ保存していない
        # 直前に保存/読み込みした時点の内容のハッシュ(未保存の変更の判定)。None はファイルと対応していない
        self._saved_content_fingerprint = None

        # データエディタのセル編集の Undo とは別
        self.undo_stack = QUndoStack(self)

        # データセットに対する操作を機能ごとに分けたクラス。窓口(DatasetHost)は本体に使うときに触れるので、
        # 画面を組み立てる前に作っておける(組み立ての途中からも使われる)。
        self._dataset_host = DatasetHost(self)
        self.peaks = PeakController(self._dataset_host)
        self.fitting = FittingController(self._dataset_host)
        self.processing = ProcessingController(self._dataset_host)
        self.colors = ColorController(self._dataset_host)
        self.transfer = TransferController(self._dataset_host)
        self.overlays = OverlayController(self._dataset_host)
        self.plugin_runs = PluginRunController(self._dataset_host)
        self.property_panel = DatasetPropertyPanel(self)

        # メニューを作るときに参照するので、ここで用意する(0分なら止めたまま)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.auto_save)
        saved_interval_min = self.settings.value(
            "autosave_interval_min", DEFAULT_AUTOSAVE_INTERVAL_MIN, type=int
        )
        if saved_interval_min > 0:
            self.autosave_timer.start(saved_interval_min * 60 * 1000)

        self.all_axes = []
        self.all_secondary_axes = []
        self.project.all_plot_settings = []
        self.project.active_axis_index = 0

        # マウス操作の各モードの状態(接続 ID は切るときに使う)
        self.cursor_mode_enabled = False
        self.cursor_connection_id = None
        self.cursor_annotation = None

        # 中ボタンでのパン。ドラッグ中かどうかは _middle_pan_axes が None かどうか
        self._middle_pan_axes = None
        self._middle_pan_start_data = None
        self._middle_pan_start_xlim = None
        self._middle_pan_start_ylim = None

        self.annotation_mode_enabled = False
        self._annotation_press_cid = None
        self._annotation_release_cid = None
        self._annotation_drag_start = None     # (ax, x, y)
        self.snap_to_grid_enabled = self.settings.value(
            "snap_to_grid_enabled", DEFAULT_SNAP_TO_GRID_ENABLED, type=bool)
        self.snap_grid_interval_px = self.settings.value(
            "snap_grid_interval_px", DEFAULT_SNAP_GRID_INTERVAL_PX, type=int)

        self.layout_edit_mode_enabled = False
        self._layout_edit_press_cid = None
        self._layout_edit_motion_cid = None
        self._layout_edit_release_cid = None
        self._layout_edit_leave_cid = None     # ドラッグ中に図の外へ出たとき用
        self._layout_drag_state = None
        # クリックで選んだ軸(ドラッグとは別)。位置と大きさの数値欄の対象
        self._layout_selected_axis_index = None

        self.range_select_mode_enabled = False
        self._range_select_press_cid = None
        self._range_select_motion_cid = None
        self._range_select_release_cid = None
        self._range_select_axes = None
        self._range_select_start_x = None
        self._range_select_preview_artist = None

        self.peak_placement_mode_enabled = False
        self._peak_placement_press_cid = None
        self._pending_peak_guesses = []   # [{'center':, 'height':, 'width':}, ...]
        self._pending_peak_markers = []   # [(guess, axvline, plot point), ...]

        self.slice_extraction_mode_enabled = False
        self._slice_extraction_press_cid = None
        self._slice_extraction_motion_cid = None
        self._slice_extraction_release_cid = None
        self._slice_extraction_axes = None
        self._slice_extraction_start = None         # (x, y) データ座標
        self._slice_extraction_preview_artist = None

        self.region_highlight_mode_enabled = False
        self._region_highlight_press_cid = None
        self._region_highlight_motion_cid = None
        self._region_highlight_release_cid = None
        self._region_highlight_axes = None
        self._region_highlight_start = None         # (x, y) データ座標
        self._region_highlight_preview_artist = None

        # 最初の軸の設定の既定値になる。フォントは QFont()(UI のフォント)にしない:
        # matplotlib は "Yu Gothic UI" のような UI 用のフォントを解決できず、文字化けする
        self._tick_font = _make_default_plot_font()
        self._tick_color = '#000000'
        self._tick_width = 0.8
        self._axis_label_font = _make_default_plot_font()
        self._axis_label_color = '#000000'
        self._spine_width = 1.0
        self._spine_color = '#000000'
        self._legend_font = _make_default_plot_font()
        self._legend_color = '#000000'

    def _setup_window(self):
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.ui.control_dock_widget.setFixedWidth(CONTROL_DOCK_WIDTH)

        # 余った縦の空きはキャンバスに回す(指定しないとデータセット一覧と均等に分けられ、一覧の下が空く)
        self.ui.gridLayout_2.setRowStretch(1, 1)  # キャンバス
        self.ui.gridLayout_2.setRowStretch(2, 0)  # データセット一覧
        self.ui.gridLayout_2.setRowStretch(3, 0)  # ボタンの行

    def _build_canvas_and_toolbar(self):
        self.canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.canvas.dark_mode = self.settings.value("dark_mode", False, type=bool)
        # アイコンは作るときにテーマの色を焼き込むので、アイコンを作り始める前にテーマを当てる
        # (当てないと、ダークモードで起動したときツールバーのアイコンがライト用の色になって見えない)
        theme.apply_theme(QApplication.instance(), self.canvas.dark_mode)
        self.canvas.point_label_max_points = self.settings.value(
            "point_label_max_points", DEFAULT_POINT_LABEL_MAX_POINTS, type=int)
        toolbar = NavigationToolbar(self.canvas, self)
        # matplotlib のツールバーはアイコンの明暗を作ったときに一度だけ決めるので、
        # ダークモードの切り替え(_on_toggle_dark_mode)で作り直せるよう持っておく
        self.mpl_toolbar = toolbar
        # 普通のレイアウトに入れたツールバーは、幅が足りないとボタンが小さな「>>」に押し込まれて見つからない。
        # アイコンを小さくしてはみ出しにくくする
        toolbar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
        self._localize_navigation_toolbar(toolbar)

        # マウス操作のモード。互いに排他にするため、アクションは属性で持つ(mouse_mode_mixin の表から操作する)
        toolbar.addSeparator()
        self.cursor_action = QAction(
            _svg_icon("pointer"),
            tr("データカーソル"),
            self
        )
        self.cursor_action.setCheckable(True)
        self.cursor_action.triggered.connect(self._toggle_cursor_mode)
        toolbar.addAction(self.cursor_action)

        self.annotation_action = QAction(
            _svg_icon("message-2"),
            tr("注釈 (クリック:テキスト / ドラッグ:矢印 / 右クリック:削除)"),
            self
        )
        self.annotation_action.setCheckable(True)
        self.annotation_action.triggered.connect(self._toggle_annotation_mode)
        toolbar.addAction(self.annotation_action)

        # 自由配置レイアウトのときだけ使える
        self.layout_edit_action = QAction(
            _svg_icon("layout-grid"),
            tr("レイアウト編集 (自由配置レイアウト時のみ: ドラッグでプロットを移動/リサイズ)"),
            self
        )
        self.layout_edit_action.setCheckable(True)
        self.layout_edit_action.setEnabled(False)
        self.layout_edit_action.triggered.connect(self._toggle_layout_edit_mode)
        toolbar.addAction(self.layout_edit_action)

        self.range_select_action = QAction(
            _svg_icon("select-all"),
            tr("範囲選択 (ドラッグした範囲のカレントデータセットをマスク)"),
            self
        )
        self.range_select_action.setCheckable(True)
        self.range_select_action.triggered.connect(self._toggle_range_select_mode)
        toolbar.addAction(self.range_select_action)

        self.peak_placement_action = QAction(
            _svg_icon("mountain"),  # ピーク検出ボタンと同じ
            tr("ピーク配置 (クリックで多峰分離フィットの初期値を追加、右クリックで削除)"),
            self
        )
        self.peak_placement_action.setCheckable(True)
        self.peak_placement_action.triggered.connect(self._toggle_peak_placement_mode)
        toolbar.addAction(self.peak_placement_action)

        self.slice_extraction_action = QAction(
            _svg_icon("chart-line"),
            tr("スライス抽出 (2Dマップ上でドラッグした線分に沿って1Dデータを抽出)"),
            self
        )
        self.slice_extraction_action.setCheckable(True)
        self.slice_extraction_action.triggered.connect(self._toggle_slice_extraction_mode)
        toolbar.addAction(self.slice_extraction_action)

        self.region_highlight_action = QAction(
            _svg_icon("highlight"),
            tr("領域ハイライト (横ドラッグ:縦帯 / 縦ドラッグ:横帯 / 右クリック:削除)"),
            self
        )
        self.region_highlight_action.setCheckable(True)
        self.region_highlight_action.triggered.connect(self._toggle_region_highlight_mode)
        toolbar.addAction(self.region_highlight_action)

        self.reset_zoom_action = QAction(
            _svg_icon("refresh"),
            tr("表示をリセット (拡大/パンを元に戻す)"),
            self
        )
        self.reset_zoom_action.triggered.connect(self._reset_zoom)
        toolbar.addAction(self.reset_zoom_action)

        # 統計情報のボタンは stats_summary_label を作った後(_build_fit_info_and_stats)で足す

        # キャンバスの周りに余白と区切り線を置いて、右のパネルとの境目をはっきりさせる
        self.ui.plot_container.setObjectName("plot_container")
        plot_layout = QVBoxLayout(self.ui.plot_container)
        plot_layout.setContentsMargins(6, 6, 6, 6)
        plot_layout.setSpacing(6)
        plot_layout.addWidget(toolbar)

        canvas_separator = QFrame()
        canvas_separator.setFrameShape(QFrame.Shape.HLine)
        canvas_separator.setObjectName("canvas_separator")
        plot_layout.addWidget(canvas_separator)

        plot_layout.addWidget(self.canvas)

        # キャンバスを別ウィンドウへ切り離したあと、元の位置に戻せるようにする
        # (この後に足すミニマップはキャンバスより後ろなので、この位置は変わらない)
        self._plot_layout = plot_layout
        self._canvas_layout_index = plot_layout.indexOf(self.canvas)
        self._canvas_detach_window = None
        self.canvas_detached = False

        # グラフの下の小さな全体図。ドラッグで全部の軸の X の範囲を絞る。区切り線は canvas_separator のスタイルを使う
        self.minimap_separator = QFrame()
        self.minimap_separator.setFrameShape(QFrame.Shape.HLine)
        self.minimap_separator.setObjectName("canvas_separator")
        plot_layout.addWidget(self.minimap_separator)

        self.minimap = MinimapWidget(self)
        self.minimap.range_selected.connect(self._on_minimap_range_selected)
        plot_layout.addWidget(self.minimap)

        self.minimap_visible = self.settings.value("minimap_visible", True, type=bool)
        self.minimap.setVisible(self.minimap_visible)
        self.minimap_separator.setVisible(self.minimap_visible)

    def _setup_status_bar(self):
        self.coordinate_label = QLabel("X= ---, Y= ---")
        self.ui.statusbar.addPermanentWidget(self.coordinate_label)

    def _build_dataset_color_picker(self):
        old_color_button = self.ui.color_button
        self.color_picker_widget = ColorPickerWidget(self.settings, self)
        self.ui.formLayout_4.replaceWidget(old_color_button, self.color_picker_widget)
        old_color_button.hide()
        old_color_button.deleteLater()

        # 「データ追加」のすぐ隣
        self.new_dataset_button = QPushButton(tr("新規データセット作成..."))
        self.ui.horizontalLayout_3.insertWidget(1, self.new_dataset_button)

    def _build_dataset_list_buttons(self):
        self.duplicate_dataset_button = QPushButton(tr("プロット複製"))
        self.view_edit_data_button = QPushButton(tr("データ表示/編集"))
        self.fit_curve_button = QPushButton(tr("曲線フィット"))
        self.find_peaks_button = QPushButton(tr("ピーク検出"))
        self.multi_peak_fit_button = QPushButton(tr("多峰フィット"))
        self.auto_color_button = QPushButton(tr("自動配色"))
        self.new_folder_button = QPushButton(tr("新しいフォルダ"))

        # ボタンをアイコンだけにして「データ処理」「解析」「整理」の3組に分ける(文字はツールチップに残す)。
        # ダークモードの切り替えでアイコンを作り直すので(_refresh_custom_svg_icons)、対応を持っておく
        self._dataset_action_button_icons = {
            self.ui.add_dataset_button: ("file-plus", tr("データ追加")),
            self.new_dataset_button: ("table", tr("新規作成")),
            self.duplicate_dataset_button: ("copy", tr("複製")),
            self.view_edit_data_button: ("edit", tr("表示/編集")),
            self.ui.remove_dataset_button: ("trash", tr("削除")),
            self.fit_curve_button: ("chart-line", tr("曲線フィット")),
            self.find_peaks_button: ("mountain", tr("ピーク検出")),
            self.multi_peak_fit_button: ("chart-histogram", tr("多峰フィット")),
            self.auto_color_button: ("palette", tr("自動配色")),
            self.new_folder_button: ("folder-plus", tr("新しいフォルダ")),
        }
        for button, (icon_name, short_label) in self._dataset_action_button_icons.items():
            button.setToolTip(button.text() or short_label)
            button.setText("")
            button.setIcon(_svg_icon(icon_name, size=18))
            button.setProperty("iconOnly", True)
            button.setFixedSize(34, 34)
            # フォーカスを持つと、押した後も :focus の枠が残って押されたままに見える
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def _make_group_separator():
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setObjectName("button_row_separator")
            sep.setFixedWidth(2)
            return sep

        # データ処理: 追加・新規作成・複製・表示編集・削除(削除は Designer の配置のまま)
        self.ui.horizontalLayout_3.insertWidget(2, self.duplicate_dataset_button)
        self.ui.horizontalLayout_3.insertWidget(3, self.view_edit_data_button)

        self.ui.horizontalLayout_3.insertWidget(5, _make_group_separator())
        # 解析
        self.ui.horizontalLayout_3.addWidget(self.fit_curve_button)
        self.ui.horizontalLayout_3.addWidget(self.find_peaks_button)
        self.ui.horizontalLayout_3.addWidget(self.multi_peak_fit_button)

        self.ui.horizontalLayout_3.addWidget(_make_group_separator())
        # 整理
        self.ui.horizontalLayout_3.addWidget(self.auto_color_button)
        self.ui.horizontalLayout_3.addWidget(self.new_folder_button)

        self.ui.horizontalLayout_3.addStretch()

        # 「⋯」: たまにしか使わない操作
        self.dataset_overflow_button = QToolButton()
        self.dataset_overflow_button.setText("⋯")
        self.dataset_overflow_button.setToolTip(tr("その他の操作"))
        self.dataset_overflow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.dataset_overflow_button.setFixedSize(34, 34)
        overflow_menu = QMenu(self.dataset_overflow_button)
        self.manage_palette_action = overflow_menu.addAction(
            _svg_icon("palette", size=16), tr("パレット管理...")
        )
        self.colormap_assign_action = overflow_menu.addAction(
            _svg_icon("palette", size=16), tr("カラーマップから自動配色...")
        )
        # 登録はいつでも変わるので開くたびに作り直す。QMenu と menuAction() の両方を持つ(持たないと回収される)
        self._named_color_apply_menu = overflow_menu.addMenu(
            _svg_icon("color-swatch", size=16), tr("登録した色を適用"))
        self._named_color_apply_menu_action = self._named_color_apply_menu.menuAction()
        self._named_color_apply_menu.aboutToShow.connect(
            self.colors.populate_named_color_menu)
        self.colors.populate_named_color_menu()
        self.dataset_overflow_button.setMenu(overflow_menu)
        self.ui.horizontalLayout_3.addWidget(self.dataset_overflow_button)

        # データセットのプロパティ欄を7つの節に分ける。Designer の行もここで移すので、formLayout_4 を触る
        # 色欄の差し替え(_build_dataset_color_picker)より後であること。以降の行は self._prop_form(キー) に足す
        self._build_dataset_property_sections()

    def _build_dataset_style_controls(self):
        self.x_col_combo = QComboBox()
        self.y_col_combo = QComboBox()
        self._prop_form('data').addRow("X軸の列", self.x_col_combo)
        self._prop_form('data').addRow("Y軸の列", self.y_col_combo)

        self.x_err_col_combo = QComboBox()
        self.y_err_col_combo = QComboBox()
        self._prop_form('data').addRow("X誤差列", self.x_err_col_combo)
        self._prop_form('data').addRow("Y誤差列", self.y_err_col_combo)

        self.alpha_label = QLabel("透明度")
        self.alpha_spinbox = QDoubleSpinBox()
        self.alpha_spinbox.setRange(0.0, 1.0)
        self.alpha_spinbox.setSingleStep(0.05)
        self.alpha_spinbox.setDecimals(2)
        self.alpha_spinbox.setValue(1.0)
        self._prop_form('style').addRow(self.alpha_label, self.alpha_spinbox)

        # グラデーション(線・面の塗り)。出し入れは property_panel.update_gradient_controls_visibility
        self.gradient_checkbox = QCheckBox(tr("グラデーションを適用"))
        self._prop_form('gradient').addRow(self.gradient_checkbox)

        self.gradient_color2_label = QLabel(tr("終端色"))
        self.gradient_color2_picker = ColorPickerWidget(self.settings, self, initial_color='#ffffff')
        self._prop_form('gradient').addRow(self.gradient_color2_label, self.gradient_color2_picker)

        self.gradient_target_label = QLabel(tr("対象"))
        self.gradient_target_combo = QComboBox()
        self.gradient_target_combo.addItem(tr("線"), "line")
        self.gradient_target_combo.addItem(tr("塗り"), "fill")
        self.gradient_target_combo.addItem(tr("両方"), "both")
        self._prop_form('gradient').addRow(self.gradient_target_label, self.gradient_target_combo)

        # ウォーターフォールは種類ではなく、どの種類とも組み合わせられるオプション。
        # 出し入れは property_panel.update_waterfall_controls_visibility
        self.waterfall_checkbox = QCheckBox(tr("ウォーターフォール表示(積み重ね)"))
        self._prop_form('waterfall').addRow(self.waterfall_checkbox)

        self.waterfall_offset_x_label = QLabel(tr("Xオフセット"))
        self.waterfall_offset_x_spinbox = QDoubleSpinBox()
        self.waterfall_offset_x_spinbox.setRange(-1e6, 1e6)
        self.waterfall_offset_x_spinbox.setSingleStep(0.1)
        self.waterfall_offset_x_spinbox.setDecimals(4)
        self.waterfall_offset_x_spinbox.setValue(0.0)
        self._prop_form('waterfall').addRow(self.waterfall_offset_x_label, self.waterfall_offset_x_spinbox)

        self.waterfall_offset_y_label = QLabel(tr("Yオフセット"))
        self.waterfall_offset_y_spinbox = QDoubleSpinBox()
        self.waterfall_offset_y_spinbox.setRange(-1e6, 1e6)
        self.waterfall_offset_y_spinbox.setSingleStep(0.1)
        self.waterfall_offset_y_spinbox.setDecimals(4)
        self.waterfall_offset_y_spinbox.setValue(1.0)
        self._prop_form('waterfall').addRow(self.waterfall_offset_y_label, self.waterfall_offset_y_spinbox)

        self.waterfall_occlusion_checkbox = QCheckBox(tr("背面のトレースを隠す(オクルージョン)"))
        self.waterfall_occlusion_checkbox.setChecked(True)
        self._prop_form('waterfall').addRow(self.waterfall_occlusion_checkbox)

        # 奥の段ほど Y をわずかに縮めて立体風にする
        self.waterfall_depth_checkbox = QCheckBox(tr("奥行き効果(奥のトレースをわずかに縮小)"))
        self.waterfall_depth_checkbox.setChecked(False)
        self._prop_form('waterfall').addRow(self.waterfall_depth_checkbox)

        self.waterfall_depth_ratio_label = QLabel(tr("1段あたりの縮小率"))
        self.waterfall_depth_ratio_spinbox = QDoubleSpinBox()
        self.waterfall_depth_ratio_spinbox.setRange(0.0, 0.9)
        self.waterfall_depth_ratio_spinbox.setSingleStep(0.01)
        self.waterfall_depth_ratio_spinbox.setDecimals(3)
        self.waterfall_depth_ratio_spinbox.setValue(0.03)
        self._prop_form('waterfall').addRow(self.waterfall_depth_ratio_label, self.waterfall_depth_ratio_spinbox)

        self.point_labels_checkbox = QCheckBox("データ点にラベルを表示")
        self._prop_form('extra').addRow(self.point_labels_checkbox)
        # 点が上限を超えてラベルを描かないときに、その理由を出す
        self.point_labels_limit_note = QLabel()
        self.point_labels_limit_note.setObjectName("point_labels_limit_note")
        self.point_labels_limit_note.setWordWrap(True)
        self.point_labels_limit_note.setVisible(False)
        self._prop_form('extra').addRow(self.point_labels_limit_note)
        self.point_label_col_label = QLabel("ラベルの内容")
        self.point_label_col_combo = QComboBox()
        self._prop_form('extra').addRow(self.point_label_col_label, self.point_label_col_combo)

        # 誤差の表し方。誤差列が無ければどれを選んでも描かれない
        self.error_display_label = QLabel(tr("誤差の表示形式"))
        self.error_display_combo = QComboBox()
        self.error_display_combo.addItem(tr("エラーバー"), "bar")
        self.error_display_combo.addItem(tr("誤差バンド"), "band")
        self.error_display_combo.addItem(tr("両方"), "both")
        self._prop_form('extra').addRow(self.error_display_label, self.error_display_combo)

        # X/Y/Z 列の長形式を2Dマップとして描く。関係する欄の出し入れは property_panel.update_2d_controls_visibility
        self.data_2d_checkbox = QCheckBox(tr("2Dグリッドデータとして扱う(ヒートマップ)"))
        self._prop_form('map').addRow(self.data_2d_checkbox)

        self.z_col_label = QLabel(tr("Z軸の列"))
        self.z_col_combo = QComboBox()
        self._prop_form('map').addRow(self.z_col_label, self.z_col_combo)

        self.colormap_label = QLabel(tr("カラーマップ"))
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems(COLORMAP_CHOICES)
        self._prop_form('map').addRow(self.colormap_label, self.colormap_combo)

        self.map_display_mode_label = QLabel(tr("表示方式"))
        self.map_display_mode_combo = QComboBox()
        self.map_display_mode_combo.addItem(tr("ヒートマップ"), "heatmap")
        self.map_display_mode_combo.addItem(tr("等高線(線)"), "contour")
        self.map_display_mode_combo.addItem(tr("等高線(塗りつぶし)"), "contour_filled")
        self.map_display_mode_combo.addItem(tr("ヒートマップ+等高線"), "heatmap_contour")
        self._prop_form('map').addRow(self.map_display_mode_label, self.map_display_mode_combo)

        self.contour_levels_label = QLabel(tr("等高線レベル数"))
        self.contour_levels_spinbox = QSpinBox()
        self.contour_levels_spinbox.setRange(2, 100)
        self.contour_levels_spinbox.setValue(10)
        self._prop_form('map').addRow(self.contour_levels_label, self.contour_levels_spinbox)

        self.grid_interp_method_label = QLabel(tr("補間方法"))
        self.grid_interp_method_combo = QComboBox()
        self.grid_interp_method_combo.addItems(['linear', 'cubic', 'nearest'])
        self._prop_form('map').addRow(self.grid_interp_method_label, self.grid_interp_method_combo)

        self.color_range_auto_checkbox = QCheckBox(tr("値域を自動"))
        self.color_range_auto_checkbox.setChecked(True)
        self._prop_form('map').addRow(self.color_range_auto_checkbox)

        self.vmin_label = QLabel(tr("値域の最小"))
        self.vmin_spinbox = QDoubleSpinBox()
        self.vmin_spinbox.setRange(-1e12, 1e12)
        self.vmin_spinbox.setDecimals(4)
        self.vmin_spinbox.setEnabled(False)
        self._prop_form('map').addRow(self.vmin_label, self.vmin_spinbox)

        self.vmax_label = QLabel(tr("値域の最大"))
        self.vmax_spinbox = QDoubleSpinBox()
        self.vmax_spinbox.setRange(-1e12, 1e12)
        self.vmax_spinbox.setDecimals(4)
        self.vmax_spinbox.setValue(1.0)
        self.vmax_spinbox.setEnabled(False)
        self._prop_form('map').addRow(self.vmax_label, self.vmax_spinbox)

        # 欠損値の扱いは描くときだけに効く(データ自体は変えない)。
        # ラベルの列幅は全部の節で揃えるので、ここが一番長いと全体の入力欄が狭まる。「(NaN)」はツールチップに回す
        self.nan_policy_label = QLabel(tr("欠損値の扱い"))
        self.nan_policy_label.setToolTip(tr("欠損値(NaN)を含む点の描画方法"))
        self.nan_policy_combo = QComboBox()
        self.nan_policy_combo.addItem(tr("線を切る(既定)"), "gap")
        self.nan_policy_combo.addItem(tr("前の値で埋める"), "ffill")
        self.nan_policy_combo.addItem(tr("無視してつなぐ"), "drop")
        self._prop_form('data').addRow(self.nan_policy_label, self.nan_policy_combo)

        # 平滑化の手法。オン/オフは Designer の smoothing_checkbox
        self.smoothing_method_label = QLabel(tr("平滑化の手法"))
        self.smoothing_method_combo = QComboBox()
        self.smoothing_method_combo.addItem(tr("CubicSpline(既定)"), "cubic_spline")
        self.smoothing_method_combo.addItem(tr("移動平均"), "moving_average")
        self.smoothing_method_combo.addItem(tr("中央値フィルタ"), "median")
        self.smoothing_method_combo.addItem(tr("ガウシアンフィルタ"), "gaussian")
        # 「平滑化」のチェックは手法と対なので、_build_dataset_property_sections では移さずここで手法の直前に置く
        # (そうしないと間に「透明度」が挟まる)
        self._prop_form('style').addRow(self.ui.smoothing_checkbox)
        self._prop_form('style').addRow(self.smoothing_method_label, self.smoothing_method_combo)

    def _build_legend_location_control(self):
        self.legend_loc_label = QLabel("凡例の位置")
        self.legend_loc_combo = QComboBox()
        self.legend_loc_combo.addItems([
            "best", "upper right", "upper left", "lower left", "lower right", "center"
        ])
        _insert_form_row_after(self.ui.formLayout_3, self.ui.legend_visible_checkbox,
                               self.legend_loc_label, self.legend_loc_combo)

        self.legend_font_label = QLabel("凡例フォント")
        self.legend_font_button = QPushButton("フォント選択...")
        _insert_form_row_after(self.ui.formLayout_3, self.legend_loc_combo,
                               self.legend_font_label, self.legend_font_button)

        self.legend_color_label = QLabel("凡例 文字色")
        self.legend_color_button = QPushButton("色選択...")
        _insert_form_row_after(self.ui.formLayout_3, self.legend_font_button,
                               self.legend_color_label, self.legend_color_button)

        # 凡例の並びは描画順とは別に決められる
        self.legend_order_button = QPushButton("凡例の順序...")
        _insert_form_row_after(self.ui.formLayout_3, self.legend_color_button, self.legend_order_button)

        # ダークモードの切り替えで作り直すので(_refresh_custom_svg_icons)、対応を持っておく
        self._field_icon_buttons = {
            self.ui.tick_font_button: "typography",
            self.ui.tick_color_button: "color-swatch",
            self.ui.axis_label_font_button: "typography",
            self.ui.axis_label_color_button: "color-swatch",
            self.ui.spine_color_button: "color-swatch",
            self.legend_font_button: "typography",
            self.legend_color_button: "color-swatch",
        }
        for button, icon_name in self._field_icon_buttons.items():
            button.setIcon(_svg_icon(icon_name, size=16))

    def _build_fit_info_and_stats(self):
        self.fit_info_label = QLabel("フィット情報")
        self.fit_info_textedit = QTextEdit()
        self.fit_info_textedit.setReadOnly(True)
        self.fit_info_textedit.setFixedHeight(100)
        # 節の最後(描画先の後ろ)に置く(_add_subplot_target_row)。フィットが無いと隠れる欄なので、
        # 先頭に置くとフィットのたびに下の項目が押し下げられる

        # 統計値はいつも見るものではないので、ツールバーのボタンから開く小窓に出す。
        # 中身は選択が変わるたびに property_panel.update_stats_summary_label が更新する(閉じている間も)
        self.stats_summary_label = QLabel("-")
        self.stats_summary_label.setWordWrap(True)
        self.stats_summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.stats_toolbar_button = QToolButton()
        self.stats_toolbar_button.setIcon(_svg_icon("chart-histogram"))
        self.stats_toolbar_button.setToolTip(tr("統計情報 (選択中データセットのY列の要約統計量)"))
        self.stats_toolbar_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        stats_popup = QWidget()
        stats_popup_layout = QVBoxLayout(stats_popup)
        stats_popup_layout.setContentsMargins(10, 8, 10, 8)
        stats_popup_title = QLabel(tr("統計 (Y列)"))
        stats_popup_title_font = QFont(stats_popup_title.font())
        stats_popup_title_font.setBold(True)
        stats_popup_title.setFont(stats_popup_title_font)
        stats_popup_layout.addWidget(stats_popup_title)
        self.stats_summary_label.setMinimumWidth(260)
        stats_popup_layout.addWidget(self.stats_summary_label)

        stats_menu = QMenu(self.stats_toolbar_button)
        stats_widget_action = QWidgetAction(self.stats_toolbar_button)
        stats_widget_action.setDefaultWidget(stats_popup)
        stats_menu.addAction(stats_widget_action)
        self.stats_toolbar_button.setMenu(stats_menu)
        self.mpl_toolbar.addSeparator()
        self.mpl_toolbar.addWidget(self.stats_toolbar_button)

    def _build_secondary_y_controls(self):
        self.use_secondary_y_checkbox = QCheckBox("第2Y軸 (右側) を使用")
        self._prop_form('place').addRow(self.use_secondary_y_checkbox)

        self.y2_label_text_label = QLabel("第2Y軸ラベル")
        self.y2_label_text_edit = QLineEdit()
        _insert_form_row_after(self.ui.formLayout_3, self.ui.y_label_text_edit,
                               self.y2_label_text_label, self.y2_label_text_edit)

    def _build_tick_grid_and_colorbar_controls(self):
        self.tick_direction_label = QLabel("主軸目盛(主/補助)")
        self.major_tick_direction_combo = QComboBox()
        self.major_tick_direction_combo.addItems(["out", "in", "inout"])
        self.minor_tick_direction_combo = QComboBox()
        self.minor_tick_direction_combo.addItems(["out", "in", "inout"])
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.major_tick_direction_combo)
        dir_layout.addWidget(self.minor_tick_direction_combo)

        self.tick_direction_y2_label = QLabel("第2軸目盛(主/補助)")
        self.major_tick_direction_y2_combo = QComboBox()
        self.major_tick_direction_y2_combo.addItems(["out", "in", "inout"])
        self.minor_tick_direction_y2_combo = QComboBox()
        self.minor_tick_direction_y2_combo.addItems(["out", "in", "inout"])
        dir_y2_layout = QHBoxLayout()
        dir_y2_layout.addWidget(self.major_tick_direction_y2_combo)
        dir_y2_layout.addWidget(self.minor_tick_direction_y2_combo)

        _insert_form_row_after(self.ui.formLayout_3, self.ui.tick_format_label, self.tick_direction_label, dir_layout)
        _insert_form_row_after(self.ui.formLayout_3, self.tick_direction_label, self.tick_direction_y2_label, dir_y2_layout)

        # グリッド線の線種・太さ・透明度(X/Y × 主/補助)。「補助グリッドの表示」のすぐ下に置く
        self.grid_linestyle_choices = [
            (tr("実線"), '-'), (tr("破線"), '--'), (tr("点線"), ':'), (tr("一点鎖線"), '-.'),
        ]

        def _make_grid_style_row(default_linestyle, default_width):
            linestyle_combo = QComboBox()
            for choice_label, _code in self.grid_linestyle_choices:
                linestyle_combo.addItem(choice_label)
            default_index = next(
                (i for i, (_label, code) in enumerate(self.grid_linestyle_choices) if code == default_linestyle),
                0
            )
            linestyle_combo.setCurrentIndex(default_index)
            linestyle_combo.setToolTip(tr("線種"))
            linestyle_combo.setMaximumWidth(90)

            width_spinbox = QDoubleSpinBox()
            width_spinbox.setRange(0.1, 10.0)
            width_spinbox.setSingleStep(0.1)
            width_spinbox.setDecimals(1)
            width_spinbox.setValue(default_width)
            width_spinbox.setToolTip(tr("太さ"))
            # これより狭いと矢印ボタンと重なって "10.0" のような値が見切れる
            width_spinbox.setMinimumWidth(60)
            width_spinbox.setMaximumWidth(78)

            alpha_spinbox = QDoubleSpinBox()
            alpha_spinbox.setRange(0.0, 1.0)
            alpha_spinbox.setSingleStep(0.05)
            alpha_spinbox.setDecimals(2)
            alpha_spinbox.setValue(1.0)
            alpha_spinbox.setToolTip(tr("透過度(アルファ)"))
            alpha_spinbox.setMinimumWidth(60)
            alpha_spinbox.setMaximumWidth(78)

            row_layout = QHBoxLayout()
            row_layout.addWidget(linestyle_combo)
            row_layout.addWidget(width_spinbox)
            row_layout.addWidget(alpha_spinbox)
            return linestyle_combo, width_spinbox, alpha_spinbox, row_layout

        (self.x_major_grid_linestyle_combo, self.x_major_grid_width_spinbox,
         self.x_major_grid_alpha_spinbox, x_major_grid_layout) = _make_grid_style_row('-', 0.8)
        (self.x_minor_grid_linestyle_combo, self.x_minor_grid_width_spinbox,
         self.x_minor_grid_alpha_spinbox, x_minor_grid_layout) = _make_grid_style_row('--', 0.5)
        (self.y_major_grid_linestyle_combo, self.y_major_grid_width_spinbox,
         self.y_major_grid_alpha_spinbox, y_major_grid_layout) = _make_grid_style_row('-', 0.8)
        (self.y_minor_grid_linestyle_combo, self.y_minor_grid_width_spinbox,
         self.y_minor_grid_alpha_spinbox, y_minor_grid_layout) = _make_grid_style_row('--', 0.5)

        self.x_major_grid_style_label = QLabel(tr("X軸主目盛"))
        self.x_minor_grid_style_label = QLabel(tr("X軸補助目盛"))
        self.y_major_grid_style_label = QLabel(tr("Y軸主目盛"))
        self.y_minor_grid_style_label = QLabel(tr("Y軸補助目盛"))

        _grid_style_anchor = self.ui.minor_grid_visible_checkbox
        for _grid_style_label, _grid_style_layout in (
            (self.x_major_grid_style_label, x_major_grid_layout),
            (self.x_minor_grid_style_label, x_minor_grid_layout),
            (self.y_major_grid_style_label, y_major_grid_layout),
            (self.y_minor_grid_style_label, y_minor_grid_layout),
        ):
            _insert_form_row_after(self.ui.formLayout_3, _grid_style_anchor, _grid_style_label, _grid_style_layout)
            _grid_style_anchor = _grid_style_label

        # 目盛線の長さ(pt)。「目盛の太さ」の直後。補助目盛の最小値(-0.5)は「自動」(主目盛 × MINOR_TICK_LENGTH_RATIO)
        self.tick_length_label = QLabel(tr("目盛の長さ(主/補助)"))
        self.major_tick_length_spinbox = QDoubleSpinBox()
        self.major_tick_length_spinbox.setRange(0.0, 20.0)
        self.major_tick_length_spinbox.setSingleStep(0.5)
        self.major_tick_length_spinbox.setDecimals(1)
        self.major_tick_length_spinbox.setSuffix(" pt")
        self.major_tick_length_spinbox.setValue(DEFAULT_MAJOR_TICK_LENGTH)
        self.major_tick_length_spinbox.setToolTip(tr("主目盛の線の長さ(pt)"))
        self.minor_tick_length_spinbox = QDoubleSpinBox()
        self.minor_tick_length_spinbox.setRange(MINOR_TICK_LENGTH_AUTO, 20.0)
        self.minor_tick_length_spinbox.setSingleStep(0.5)
        self.minor_tick_length_spinbox.setDecimals(1)
        self.minor_tick_length_spinbox.setSuffix(" pt")
        self.minor_tick_length_spinbox.setSpecialValueText(tr("自動"))
        self.minor_tick_length_spinbox.setValue(MINOR_TICK_LENGTH_AUTO)
        self.minor_tick_length_spinbox.setToolTip(
            tr("補助目盛の線の長さ(pt)。「自動」は主目盛の長さの約0.57倍"))
        # QDoubleSpinBox を2つ並べると最小幅が約306pxになり、フォームの列幅を広げてドックに横スクロールが出る
        # (tests/test_main_window.py が検出)。すぐ上の目盛方向の欄と同じ幅に揃える
        for _tick_length_spin in (self.major_tick_length_spinbox, self.minor_tick_length_spinbox):
            _tick_length_spin.setMinimumWidth(self.major_tick_direction_combo.minimumSizeHint().width())
        tick_length_layout = QHBoxLayout()
        tick_length_layout.addWidget(self.major_tick_length_spinbox)
        tick_length_layout.addWidget(self.minor_tick_length_spinbox)
        _insert_form_row_after(self.ui.formLayout_3, self.ui.tick_width_spinbox,
                               self.tick_length_label, tick_length_layout)

        # カラーバーは2Dマップ(か値で色分けした散布図)がある軸でだけ効く
        self.colorbar_enabled_checkbox = QCheckBox(tr("カラーバーを表示"))
        self.colorbar_enabled_checkbox.setChecked(True)
        self.ui.formLayout_3.addRow(self.colorbar_enabled_checkbox)

        self.colorbar_position_label = QLabel(tr("カラーバーの位置"))
        self.colorbar_position_combo = QComboBox()
        self.colorbar_position_combo.addItem(tr("右"), "right")
        self.colorbar_position_combo.addItem(tr("左"), "left")
        self.colorbar_position_combo.addItem(tr("上"), "top")
        self.colorbar_position_combo.addItem(tr("下"), "bottom")
        self.ui.formLayout_3.addRow(self.colorbar_position_label, self.colorbar_position_combo)

        self.colorbar_width_label = QLabel(tr("カラーバーの幅(割合)"))
        self.colorbar_width_spinbox = QDoubleSpinBox()
        self.colorbar_width_spinbox.setRange(0.01, 0.5)
        self.colorbar_width_spinbox.setSingleStep(0.01)
        self.colorbar_width_spinbox.setDecimals(2)
        self.colorbar_width_spinbox.setValue(0.05)
        self.ui.formLayout_3.addRow(self.colorbar_width_label, self.colorbar_width_spinbox)

        self.colorbar_label_label = QLabel(tr("カラーバーのラベル"))
        self.colorbar_label_edit = QLineEdit()
        self.ui.formLayout_3.addRow(self.colorbar_label_label, self.colorbar_label_edit)

    def _build_tick_format_controls(self):
        tick_format_choices = [
            tr("自動"),
            tr("軸端にまとめて指数表記 (×10ⁿ)"),
            tr("目盛りごとに指数表記 (例: 1.0×10¹⁰)"),
            tr("常に小数表記"),
        ]
        self.x_tick_format_label = QLabel(tr("目盛り表記"))
        self.x_tick_format_combo = QComboBox()
        self.x_tick_format_combo.addItems(tick_format_choices)
        self.ui.formLayout.addRow(self.x_tick_format_label, self.x_tick_format_combo)

        # 目盛線と目盛数値の表示は X/Y で別々なので、それぞれの軸のタブに置く
        self.x_ticks_visible_checkbox = QCheckBox(tr("目盛を表示"))
        self.x_ticks_visible_checkbox.setChecked(True)
        self.ui.formLayout.addRow(self.x_ticks_visible_checkbox)
        self.x_tick_labels_visible_checkbox = QCheckBox(tr("目盛の数値を表示"))
        self.x_tick_labels_visible_checkbox.setChecked(True)
        self.ui.formLayout.addRow(self.x_tick_labels_visible_checkbox)

        # 目盛数値の小数点以下の桁数。-1(最小値)は「自動」で、指数表記の設定に任せる
        self.x_tick_decimals_spinbox = QSpinBox()
        self.x_tick_decimals_spinbox.setRange(-1, 10)
        self.x_tick_decimals_spinbox.setSpecialValueText(tr("自動"))
        self.x_tick_decimals_spinbox.setValue(-1)
        self.x_tick_decimals_spinbox.setToolTip(
            tr("目盛りの数値を表示する小数点以下の桁数(「自動」以外を選ぶと指数表記モードより優先されます)"))
        self.ui.formLayout.addRow(QLabel(tr("小数桁数")), self.x_tick_decimals_spinbox)

        # 対数軸で補助目盛を出すときだけ使う(出し入れは _on_x_minor_tick_visibility_changed)。
        # ラベルの列幅は X/Y のタブで揃えるので、長いと両方の入力欄が狭まる。説明はツールチップに回す
        self.x_log_minor_subs_label = QLabel(tr("対数補助目盛"))
        self.x_log_minor_subs_label.setToolTip(tr("対数軸の補助目盛りをどこに打つか"))
        self.x_log_minor_subs_combo = QComboBox()
        self.x_log_minor_subs_combo.addItem(tr("自動(既定)"), "auto")
        self.x_log_minor_subs_combo.addItem(tr("全て(2〜9)"), "all")
        self.x_log_minor_subs_combo.addItem(tr("少なめ(2, 5)"), "few")
        self.x_log_minor_subs_combo.addItem(tr("最小限(5)"), "one")
        self.ui.formLayout.addRow(self.x_log_minor_subs_label, self.x_log_minor_subs_combo)
        self.x_log_minor_labels_checkbox = QCheckBox(tr("補助目盛りに数値ラベルを表示"))
        self.ui.formLayout.addRow(self.x_log_minor_labels_checkbox)
        self.x_log_minor_subs_label.setVisible(False)
        self.x_log_minor_subs_combo.setVisible(False)
        self.x_log_minor_labels_checkbox.setVisible(False)

        # X の単位と上に出したい単位が別々に選ばれていれば、単位を変換した第2X軸を上に付ける。
        # ラベルは短く保つ(フォームの全行でラベルの列幅を共有するので、長いとドックに横スクロールが出る。
        # test_properties_dock_has_no_horizontal_scrollbar)。説明はツールチップに置く
        unit_combo_choices = [X_AXIS_UNIT_LABELS[u] for u in X_AXIS_UNIT_CHOICES]
        self.x_secondary_axis_source_unit_label = QLabel(tr("X軸単位"))
        self.x_secondary_axis_source_unit_combo = QComboBox()
        self.x_secondary_axis_source_unit_combo.addItems(unit_combo_choices)
        self.x_secondary_axis_source_unit_combo.setToolTip(tr("X軸データが表している物理量の単位"))
        self.ui.formLayout.addRow(
            self.x_secondary_axis_source_unit_label, self.x_secondary_axis_source_unit_combo)

        self.x_secondary_axis_target_unit_label = QLabel(tr("第2X軸単位"))
        self.x_secondary_axis_target_unit_combo = QComboBox()
        self.x_secondary_axis_target_unit_combo.addItems(unit_combo_choices)
        self.x_secondary_axis_target_unit_combo.setToolTip(tr("上部に追加する第2X軸に変換して表示する単位"))
        self.ui.formLayout.addRow(
            self.x_secondary_axis_target_unit_label, self.x_secondary_axis_target_unit_combo)

        self.y_tick_format_label = QLabel(tr("目盛り表記"))
        self.y_tick_format_combo = QComboBox()
        self.y_tick_format_combo.addItems(tick_format_choices)
        self.ui.formLayout_2.addRow(self.y_tick_format_label, self.y_tick_format_combo)

        self.y_ticks_visible_checkbox = QCheckBox(tr("目盛を表示"))
        self.y_ticks_visible_checkbox.setChecked(True)
        self.ui.formLayout_2.addRow(self.y_ticks_visible_checkbox)
        self.y_tick_labels_visible_checkbox = QCheckBox(tr("目盛の数値を表示"))
        self.y_tick_labels_visible_checkbox.setChecked(True)
        self.ui.formLayout_2.addRow(self.y_tick_labels_visible_checkbox)

        self.y_tick_decimals_spinbox = QSpinBox()
        self.y_tick_decimals_spinbox.setRange(-1, 10)
        self.y_tick_decimals_spinbox.setSpecialValueText(tr("自動"))
        self.y_tick_decimals_spinbox.setValue(-1)
        self.y_tick_decimals_spinbox.setToolTip(
            tr("目盛りの数値を表示する小数点以下の桁数(「自動」以外を選ぶと指数表記モードより優先されます)"))
        self.ui.formLayout_2.addRow(QLabel(tr("小数桁数")), self.y_tick_decimals_spinbox)

        # X 軸と同じく、ラベルは短くして説明はツールチップへ
        self.y_log_minor_subs_label = QLabel(tr("対数補助目盛"))
        self.y_log_minor_subs_label.setToolTip(tr("対数軸の補助目盛りをどこに打つか"))
        self.y_log_minor_subs_combo = QComboBox()
        self.y_log_minor_subs_combo.addItem(tr("自動(既定)"), "auto")
        self.y_log_minor_subs_combo.addItem(tr("全て(2〜9)"), "all")
        self.y_log_minor_subs_combo.addItem(tr("少なめ(2, 5)"), "few")
        self.y_log_minor_subs_combo.addItem(tr("最小限(5)"), "one")
        self.ui.formLayout_2.addRow(self.y_log_minor_subs_label, self.y_log_minor_subs_combo)
        self.y_log_minor_labels_checkbox = QCheckBox(tr("補助目盛りに数値ラベルを表示"))
        self.ui.formLayout_2.addRow(self.y_log_minor_labels_checkbox)
        self.y_log_minor_subs_label.setVisible(False)
        self.y_log_minor_subs_combo.setVisible(False)
        self.y_log_minor_labels_checkbox.setVisible(False)

    def _build_label_editors(self):
        # タイトルと軸ラベルは、mathtext を描いたプレビューに差し替え、クリックで編集ダイアログを開く。
        # 元の QLineEdit は値の置き場と textChanged の発信元として、見えないまま残す
        self._label_preview_widgets = []  # [(preview_label, line_edit, placeholder), ...]
        for field_key, line_edit, dialog_title, placeholder in (
            ('title', self.ui.title_text_edit, tr("タイトルを編集"), tr("タイトルを入力")),
            ('x_label', self.ui.x_label_text_edit, tr("X軸ラベルを編集"), tr("X軸ラベルを入力")),
            ('y_label', self.ui.y_label_text_edit, tr("Y軸ラベルを編集"), tr("Y軸ラベルを入力")),
        ):
            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setSpacing(4)

            # 同じ位置に差し替える(行の位置がずれない)
            self.ui.formLayout_3.replaceWidget(line_edit, wrapper)
            # レイアウトには入れない(隠れていても余白の計算に関わることがある)。親を wrapper にするだけ
            line_edit.setParent(wrapper)
            line_edit.hide()

            preview_label = _ClickableMathPreviewLabel(wrapper)
            wrapper_layout.addWidget(preview_label, 1)
            preview_label.clicked.connect(
                lambda le=line_edit, dt=dialog_title: self._open_label_edit_dialog(le, dt)
            )
            self._label_preview_widgets.append((preview_label, line_edit, placeholder))
            line_edit.textChanged.connect(
                lambda text, lbl=preview_label, ph=placeholder:
                    self._refresh_label_preview(lbl, text, ph)
            )
            self._refresh_label_preview(preview_label, line_edit.text(), placeholder)

            # 軸ラベルだけ、文字を残したまま隠せる(タイトルには付けない)
            if field_key in ('x_label', 'y_label'):
                visible_checkbox = QCheckBox()
                visible_checkbox.setChecked(True)
                visible_checkbox.setToolTip(tr("ラベルの表示/非表示(テキスト自体は保持されます)"))
                wrapper_layout.addWidget(visible_checkbox)
                setattr(self, f'{field_key}_visible_checkbox', visible_checkbox)

            format_button = QToolButton()
            format_button.setText("Aa")
            format_button.setToolTip(tr("タイトル/ラベルを編集(書式・記号入力)"))
            format_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # パネルの幅が狭いので、ボタンは小さくして欄の幅を取らない
            format_button.setFixedSize(26, 22)
            small_font = QFont(format_button.font())
            small_font.setPointSize(max(7, small_font.pointSize() - 2))
            format_button.setFont(small_font)
            wrapper_layout.addWidget(format_button)
            format_button.clicked.connect(
                lambda checked=False, le=line_edit, dt=dialog_title:
                    self._open_label_edit_dialog(le, dt)
            )

    def _add_subplot_target_row(self):
        self.subplot_target_label = QLabel("描画先プロット")
        self.subplot_target_combo = QComboBox()
        self._prop_form('place').addRow(self.subplot_target_label, self.subplot_target_combo)
        # フィット情報欄 (上で構築済み) は、このセクションの最後に置く
        self._prop_form('place').addRow(self.fit_info_label, self.fit_info_textedit)

    def _arrange_property_docks(self):
        # 「プロットのプロパティ」と「データセットのプロパティ」を1つのドックに縦に並べ、1枚のパネルに見せる。
        # properties_dock_widget は control_dock_widget の別名(表示メニューなどがこの名前で使う)
        self.properties_dock_widget = self.ui.control_dock_widget
        self.ui.control_dock_widget.setWindowTitle(tr("プロパティ"))

        original_control_widget = self.ui.control_dock_widget.widget()
        plot_properties_group = QGroupBox(tr("プロットのプロパティ"))
        plot_properties_layout = QVBoxLayout(plot_properties_group)
        plot_properties_layout.setContentsMargins(0, 4, 0, 0)
        if original_control_widget:
            plot_properties_layout.addWidget(original_control_widget)
        else:
            logger.warning("control_dock_widget の中身が見つかりません。")

        self.ui.properties_groupbox.setTitle(tr("データセットのプロパティ"))

        # どちらも長いので開閉できるようにする。中身を1つずつ隠すと入れ子のレイアウトを取りこぼすので、
        # グループボックスごと出し入れする開閉ボタンを外に付ける(見出しはボタン側だけに出す)
        dataset_section = self._wrap_in_collapsible_section(
            self.ui.properties_groupbox, tr("データセットのプロパティ"))
        plot_section = self._wrap_in_collapsible_section(
            plot_properties_group, tr("プロットのプロパティ"))

        # 既定の余白だと縦スクロールバーの分だけ中身がはみ出し、横スクロールバーが出るので左右を詰める
        merged_properties_container = QWidget()
        merged_properties_layout = QVBoxLayout(merged_properties_container)
        merged_properties_layout.setContentsMargins(2, 4, 2, 4)
        merged_properties_layout.addWidget(dataset_section)
        merged_properties_layout.addWidget(plot_section)
        merged_properties_layout.addStretch()

        merged_scroll_area = QScrollArea()
        merged_scroll_area.setWidgetResizable(True)
        merged_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        merged_scroll_area.setWidget(merged_properties_container)
        self.ui.control_dock_widget.setWidget(merged_scroll_area)

        # エクスポートのプレビュー。描き続けると重いので既定では隠し、表示メニューから開く
        self.export_preview_panel = ExportPreviewPanel(self)
        self.export_preview_dock_widget = QDockWidget(tr("エクスポートプレビュー"), self)
        self.export_preview_dock_widget.setObjectName("ExportPreviewDockWidget")
        self.export_preview_dock_widget.setWidget(self.export_preview_panel)
        # 必要なときだけ見るものなので、キャンバスを狭めないよう独立した窓で開く(ドッキングもできる)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.export_preview_dock_widget)
        self.export_preview_dock_widget.setFloating(True)
        self.export_preview_dock_widget.hide()
        self._export_preview_first_show = True

        def _on_export_preview_visibility_changed(visible):
            if not visible:
                return
            # 浮いたドックは表示されるまで大きさを持たないことがあるので、最初に表示したときに整える
            if self._export_preview_first_show and self.export_preview_dock_widget.isFloating():
                self._export_preview_first_show = False
                preview_width, preview_height = 820, 680
                self.export_preview_dock_widget.resize(preview_width, preview_height)
                center = self.geometry().center()
                self.export_preview_dock_widget.move(
                    center.x() - preview_width // 2, center.y() - preview_height // 2
                )
            self.export_preview_panel.refresh_preview()

        # 選んだデータセットのフィットの残差。既定では隠し、開くときはキャンバスの下に付ける
        self.residual_panel = ResidualPanel(self)
        self.residual_dock_widget = QDockWidget(tr("残差プロット"), self)
        self.residual_dock_widget.setObjectName("ResidualDockWidget")
        self.residual_dock_widget.setWidget(self.residual_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.residual_dock_widget)
        self.residual_dock_widget.hide()

        # 選んだデータセットの処理の履歴。既定では隠す
        self.provenance_panel = ProvenancePanel(self)
        self.provenance_dock_widget = QDockWidget(tr("処理履歴"), self)
        self.provenance_dock_widget.setObjectName("ProvenanceDockWidget")
        self.provenance_dock_widget.setWidget(self.provenance_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.provenance_dock_widget)
        self.provenance_dock_widget.hide()

        self.export_preview_dock_widget.visibilityChanged.connect(_on_export_preview_visibility_changed)

    def _rebuild_label_tab(self):
        # 「ラベル/書式」タブの先頭に、グラフ全体のレイアウトと編集対象の軸の欄を入れる
        layout_group = QGroupBox(tr("グラフ全体レイアウト"))
        layout_form = QFormLayout()
        sizePolicy = layout_group.sizePolicy()
        sizePolicy.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        layout_group.setSizePolicy(sizePolicy)
        self.subplot_rows_spinbox = QSpinBox()
        self.subplot_rows_spinbox.setRange(1, 10)
        self.subplot_rows_spinbox.setValue(1)
        self.subplot_cols_spinbox = QSpinBox()
        self.subplot_cols_spinbox.setRange(1, 10)
        self.subplot_cols_spinbox.setValue(1)
        layout_form.addRow(tr("行数"), self.subplot_rows_spinbox)
        layout_form.addRow(tr("列数"), self.subplot_cols_spinbox)

        # 軸の共有は自由配置では意味が無いので、_on_toggle_free_layout で有効/無効を合わせる
        self.share_x_checkbox = QCheckBox(tr("X軸を共有(グリッドレイアウト時)"))
        self.share_y_checkbox = QCheckBox(tr("Y軸を共有(グリッドレイアウト時)"))
        layout_form.addRow(self.share_x_checkbox)
        layout_form.addRow(self.share_y_checkbox)

        self.free_layout_checkbox = QCheckBox(tr("自由配置レイアウト(ドラッグで配置)"))
        layout_form.addRow(self.free_layout_checkbox)

        free_layout_button_row = QHBoxLayout()
        self.add_free_subplot_button = QPushButton(tr("+ プロット追加"))
        self.remove_free_subplot_button = QPushButton(tr("- プロット削除"))
        self.add_free_subplot_button.setEnabled(False)
        self.remove_free_subplot_button.setEnabled(False)
        free_layout_button_row.addWidget(self.add_free_subplot_button)
        free_layout_button_row.addWidget(self.remove_free_subplot_button)
        layout_form.addRow(free_layout_button_row)

        # 自由配置で選んだ軸の位置と大きさを数値でも入れられる。値は Figure に対する割合(ax.set_position と同じ)で、
        # ドラッグと同じく少しなら範囲外も許す
        self.free_layout_position_group = QGroupBox(tr("選択中のサブプロットの位置・サイズ"))
        free_layout_position_form = QFormLayout()
        self.free_layout_x_spinbox = QDoubleSpinBox()
        self.free_layout_y_spinbox = QDoubleSpinBox()
        self.free_layout_width_spinbox = QDoubleSpinBox()
        self.free_layout_height_spinbox = QDoubleSpinBox()
        for spinbox in (self.free_layout_x_spinbox, self.free_layout_y_spinbox):
            spinbox.setRange(-1.0, 2.0)
            spinbox.setDecimals(3)
            spinbox.setSingleStep(0.01)
        for spinbox in (self.free_layout_width_spinbox, self.free_layout_height_spinbox):
            spinbox.setRange(MIN_FREE_RECT_SIZE, 2.0)
            spinbox.setDecimals(3)
            spinbox.setSingleStep(0.01)
        free_layout_position_form.addRow(tr("X"), self.free_layout_x_spinbox)
        free_layout_position_form.addRow(tr("Y"), self.free_layout_y_spinbox)
        free_layout_position_form.addRow(tr("幅"), self.free_layout_width_spinbox)
        free_layout_position_form.addRow(tr("高さ"), self.free_layout_height_spinbox)
        self.free_layout_position_group.setLayout(free_layout_position_form)
        # 自由配置モードで、かつサブプロットが選択されている間だけ表示する
        self.free_layout_position_group.setVisible(False)
        layout_form.addRow(self.free_layout_position_group)

        layout_group.setLayout(layout_form)

        active_axis_group = QGroupBox(tr("編集対象のプロット"))
        active_axis_layout = QVBoxLayout()
        sizePolicy = active_axis_group.sizePolicy()
        sizePolicy.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        active_axis_group.setSizePolicy(sizePolicy)
        self.active_axis_combo = QComboBox()
        active_axis_layout.addWidget(self.active_axis_combo)
        active_axis_group.setLayout(active_axis_layout)

        grid_layout = self.ui.tab_3.layout()  # QGridLayout

        # 既存の formLayout_3 を (0, 0) から外し、新しい2つの下(2行目)に入れ直す
        existing_layout_item = grid_layout.itemAtPosition(0, 0)

        if existing_layout_item:
            grid_layout.removeItem(existing_layout_item)

        grid_layout.addWidget(layout_group, 0, 0)
        grid_layout.addWidget(active_axis_group, 1, 0)

        if existing_layout_item:
            grid_layout.addItem(existing_layout_item, 2, 0)

    def _connect_and_initialize(self):

        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)

        # グラフの要素のクリックでの選択は、どのモードでも常に有効
        self.canvas.mpl_connect('pick_event', self._on_element_pick)

        # ホイールでのズームと中ボタンでのパンは、各モードの左クリックとぶつからないので常に有効
        self.canvas.mpl_connect('scroll_event', self._on_scroll_zoom)
        self.canvas.mpl_connect('button_press_event', self._on_middle_button_press_pan)
        self.canvas.mpl_connect('motion_notify_event', self._on_middle_button_motion_pan)
        self.canvas.mpl_connect('button_release_event', self._on_middle_button_release_pan)
        # 凡例をドラッグした位置を設定へ保存する
        self.canvas.mpl_connect('button_release_event', self._on_legend_drag_release)

        # プラグインの登録はメニューを作る(_create_menu_bar)より前に。読み込みはアプリ全体で1回
        # (load_plugins_once)、メニューへの追加はタブごとに _create_menu_bar が行う
        self.plugin_api = load_plugins_once(
            plugin_search_paths(), disabled_names=disabled_plugin_names(self.settings)
        )

        # プラグインへの窓口は (このタブ, プラグイン) ごとに1つ。
        self._plugin_contexts = {}

        # プラグインのパネル。メニューに表示切替を足すのは _create_menu_bar() なので、
        # ドックはそれより前に作る。1つ失敗しても他のパネルとタブの起動は続ける。
        self._plugin_panel_docks = {}
        for panel in self.plugin_api.get_panels():
            try:
                widget = panel.widget_factory(self.plugin_context(panel.plugin_name))
                if not isinstance(widget, QWidget):
                    raise TypeError(f"QWidgetを返しませんでした(型: {type(widget).__name__})。")
            except Exception as e:
                logger.warning(
                    "[plugin:%s] パネル '%s' の構築に失敗しました: %s",
                    panel.plugin_name, panel.name, e,
                )
                continue
            dock = QDockWidget(panel.name, self)
            dock.setObjectName(f"PluginPanel_{panel.name}")
            dock.setWidget(widget)
            self.addDockWidget(_PLUGIN_PANEL_AREA_MAP.get(panel.area, Qt.DockWidgetArea.RightDockWidgetArea), dock)
            dock.hide()  # 表示するかはドック配置の復元に任せる
            self._plugin_panel_docks[panel.name] = dock

        # フォーカスのあるドックの枠を強調する(プラグインのドックも含め、全部に効く)
        theme.install_dock_focus_highlight(self)

        # プラグインの plot_type を種類の欄の最後に足す(描き方は canvas._draw_plot_type が探す)
        for plot_type in self.plugin_api.get_plot_types():
            self.ui.plot_type_combo.addItem(plot_type.type_name)

        self._connect_signals()

        self._create_menu_bar()

        # クイックアクセスのピン留めを戻す。プラグインのものを含めて全メニューができた後であること
        self._restore_quick_access_actions()
        self._install_quick_access_context_menus()

        # 画面の既定の状態を最初の軸の設定にする
        default_settings = self._gather_settings_from_ui()
        self.project.all_plot_settings.append(default_settings)
        self._set_initial_ui_state()
        # 生成物の ui_main_window.py のラベルには末尾に「：」が付いている。.ui が無く作り直せないので、ここで取る
        _strip_trailing_colon_from_labels(self)
        # 下の1行の統計値の分だけ、一覧の高さの上限を控えめにする
        self.ui.dataset_list_widget.setMaximumHeight(175)

        spacing_value = 6
        if self.ui.formLayout_3: self.ui.formLayout_3.setSpacing(spacing_value)
        # formLayout_4 は空なので、各節の QFormLayout に掛ける
        for key, _title in DATASET_PROPERTY_SECTIONS:
            self._prop_form(key).setSpacing(spacing_value)

        # 入力欄の左端を揃える(プロパティ欄の7節どうし、X/Y 軸のタブどうし)。ラベルが全部できた後で
        self._align_form_label_columns(
            [self._prop_form(key) for key, _title in DATASET_PROPERTY_SECTIONS])
        self._align_form_label_columns([self.ui.formLayout, self.ui.formLayout_2])


        # 軸の範囲と目盛りの間隔は、指数表記でも入力できるようにする
        for spin_box in [self.ui.x_min_spinbox, self.ui.x_max_spinbox,
                          self.ui.y_min_spinbox, self.ui.y_max_spinbox]:
            _enable_scientific_notation_input(spin_box, minimum=-np.inf, maximum=np.inf)

        for spin_box in [self.ui.x_major_tick_interval_spinbox, self.ui.y_major_tick_interval_spinbox,
                          self.ui.x_minor_tick_interval_spinbox, self.ui.y_minor_tick_interval_spinbox]:
            _enable_scientific_notation_input(spin_box, minimum=0, maximum=np.inf)

        self._update_plot()

        # ドックの配置は前回の状態を戻す(最初のタブだけ。窓の大きさと位置は MainAppWindow が扱う)。
        # 既定の配置の版(DOCK_LAYOUT_VERSION)が保存時と違えば戻さない(戻すと新しい既定が既存の利用者に届かない)。
        # 戻すのはイベントループが一巡してタブが最終の大きさになってから。ここで戻すと仮の大きさで
        # スプリッターの位置が決まり、見た目とクリックの位置がずれる。
        # 「リセット」用の素の配置は、戻す前のここで控える
        self._pristine_dock_state = self.saveState()

        QTimer.singleShot(0, self._restore_dock_layout)

        # キャンバスを切り離したまま閉じていれば同じ状態に戻す。ダークモードなどと同じ軽い設定なので、どのタブでも戻す
        if self.settings.value(CANVAS_WAS_DETACHED_KEY, False, type=bool):
            QTimer.singleShot(0, lambda: self._detach_canvas(restore_geometry=True))

        self.setAcceptDrops(True)

        # 起動時の確認は最初のタブだけ。窓が表示される前だとダイアログが変な位置に出るので、一巡してから
        if self._run_startup_checks:
            QTimer.singleShot(0, self._check_autosave_recovery)
            # 初回の案内は復元の確認の後(データに関わる確認を先に)
            QTimer.singleShot(0, self._check_first_launch)
            # 新しい版の確認は上の2つの邪魔をしないよう少し遅らせる。公開 API への匿名の GET 1回だけで、
            # 新しい版があるときだけ知らせ、失敗しても何も出さない
            QTimer.singleShot(1500, self._start_startup_update_check)

        # 項目の間の余白を広げる。フォームが全部できた最後に
        apply_form_spacing(self)

    def _restore_dock_layout(self):
        """前回終了時のドック/ツールバー配置をQSettingsから復元する。

        __init__からQTimer.singleShot(0, ...)経由で、ウィンドウが実際の
        最終サイズ(タブとして埋め込まれた後のサイズ)で表示された後に
        呼ばれる想定。__init__内で直接呼ぶと、まだDesigner既定サイズの
        ままの状態でrestoreState()が実行されてしまい、スプリッター位置が
        誤ったサイズ基準で復元されてしまう。
        """
        saved_layout_version = self.settings.value("dock_layout_version", 0, type=int) if self._run_startup_checks else DOCK_LAYOUT_VERSION
        saved_state = self.settings.value("window_state") if self._run_startup_checks else None
        state_restored = False
        if saved_state is not None and saved_layout_version == DOCK_LAYOUT_VERSION:
            state_restored = bool(self.restoreState(saved_state))

        if not state_restored:
            try:
                # ★ 「プロットのプロパティ」「データセットのプロパティ」は1つのドックに
                #   統合したため、もう互いの高さ比率を指定する必要はない
                #   (ドック自体がRightDockWidgetAreaの高さいっぱいに広がる)。
                self.resizeDocks(
                    [self.export_preview_dock_widget],
                    [EXPORT_PREVIEW_DOCK_INITIAL_HEIGHT],
                    Qt.Orientation.Vertical
                )
            except Exception:
                logger.exception("resizeDocks に失敗しました")

    # --- ドックレイアウトの保存/復元/リセット(項目152、C-911) ---
    # 「最初のタブ・初回起動のみ復元」という既存の制約(起動シーケンス自体は
    # ドキュメントで「壊れやすい」と明記されているため変更しない)とは別に、
    # いつでも手動で名前付きレイアウトを保存・復元・既定にリセットできる経路を
    # 追加する(全てのタブで利用可能、_run_startup_checksに関わらず動作する)。

    def _load_dock_layout_presets(self):
        """保存済みのドックレイアウトプリセット一式を{名前: base64文字列}で返す。"""
        raw = self.settings.value(DOCK_LAYOUT_PRESETS_SETTINGS_KEY, "{}")
        if not isinstance(raw, str):
            raw = "{}"
        try:
            presets = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("ドックレイアウトプリセットの読み込みに失敗しました。空として扱います。")
            return {}
        return presets if isinstance(presets, dict) else {}

    def _save_dock_layout_presets(self, presets: dict):
        self.settings.setValue(DOCK_LAYOUT_PRESETS_SETTINGS_KEY, json.dumps(presets))

    def _on_save_dock_layout_preset(self):
        """「現在のレイアウトを保存...」メニューの処理。"""
        name, ok = QInputDialog.getText(self, "レイアウトを保存", "プリセット名:")
        name = name.strip()
        if not ok or not name:
            return
        presets = self._load_dock_layout_presets()
        presets[name] = base64.b64encode(bytes(self.saveState())).decode('ascii')
        self._save_dock_layout_presets(presets)
        self.statusBar().showMessage(f"レイアウト「{name}」を保存しました", 3000)

    def _populate_load_layout_menu(self):
        """「レイアウトを読み込み」サブメニューを、表示される直前に毎回作り直す
        (aboutToShow経由、保存/削除のたびにここを個別更新する必要が無いようにするため)。"""
        self.load_layout_menu.clear()
        presets = self._load_dock_layout_presets()
        if not presets:
            empty_action = self.load_layout_menu.addAction("(保存済みレイアウトはありません)")
            empty_action.setEnabled(False)
            return
        for name in sorted(presets.keys()):
            action = self.load_layout_menu.addAction(name)
            action.triggered.connect(lambda checked=False, n=name: self._on_load_dock_layout_preset(n))

    def _on_load_dock_layout_preset(self, name):
        presets = self._load_dock_layout_presets()
        state_b64 = presets.get(name)
        if state_b64 is None:
            return
        try:
            state_bytes = base64.b64decode(state_b64)
        except (ValueError, TypeError):
            QMessageBox.warning(self, "レイアウトの復元", "保存されたレイアウトデータが壊れています。")
            return
        if not self.restoreState(QByteArray(state_bytes)):
            QMessageBox.warning(self, "レイアウトの復元", "レイアウトの復元に失敗しました。")

    def _on_reset_dock_layout(self):
        """「既定のレイアウトにリセット」メニューの処理。__init__末尾で保存しておいた
        「素の」状態(_pristine_dock_state)に戻す。"""
        self.restoreState(self._pristine_dock_state)

    def closeEvent(self, event):
        """ウィンドウが閉じられる(正常終了する)ときに呼ばれる。"""
        # ★ バグ修正: バックグラウンドでファイル読み込み中(項目C-004フェーズ4で
        # TaskRunner化する前は専用のDataLoadWorker、gui/workers.py)にタブ/アプリを
        # 閉じると、実行中のQThreadが破棄されQtが即座にプロセスをfail-fast
        # abortさせる(実機で再現確認済み、例外機構を経由しないハードクラッシュの
        # ため他の全タブの未保存データも道連れになる)。読み込みは通常CSV/Excelの
        # 読み取りのみで長時間にはならないため、閉じる前にここでブロッキング待機
        # して完了させる。待機後にsignalをつなぎ直さず先に切断しておくことで、
        # 待機中にemitされたsucceeded/failedが、閉じている最中のウィンドウに対して
        # (キュー処理や再描画を伴う)通常のスロットを実行してしまうのも防ぐ。
        # read_data_file()自体は中断不能なため、requestInterruption()を呼んでも
        # ここでのwait()は読み込み完了まで実際にブロックしうる(曲線フィットの計算
        # と同じ扱い、v1では許容)。
        if self._data_load_task_runner is not None:
            try:
                self._data_load_task_runner.succeeded.disconnect()
                self._data_load_task_runner.failed.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._data_load_task_runner.requestInterruption()
            self._data_load_task_runner.wait()
            self._data_load_task_runner.deleteLater()
            self._data_load_task_runner = None

        self.fitting.shutdown()

        # ★ 項目C-004フェーズ5b: バッチエクスポート用のTaskRunnerも同じ理由で
        # 同型のクリーンアップを行う。
        if self._batch_export_task_runner is not None:
            try:
                self._batch_export_task_runner.succeeded.disconnect()
                self._batch_export_task_runner.failed.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._batch_export_task_runner.requestInterruption()
            self._batch_export_task_runner.wait()
            self._batch_export_task_runner.deleteLater()
            self._batch_export_task_runner = None

        # 項目161(C-1203): アップデート確認用のTaskRunnerも同じ理由で同型のクリーンアップを行う。
        if self._update_check_task_runner is not None:
            try:
                self._update_check_task_runner.succeeded.disconnect()
                self._update_check_task_runner.failed.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._update_check_task_runner.requestInterruption()
            self._update_check_task_runner.wait()
            self._update_check_task_runner.deleteLater()
            self._update_check_task_runner = None

        if self._run_startup_checks:
            self.settings.setValue("clean_exit", True)
            # ドックの配置/表示状態を保存し、次回起動時に復元する
            self.settings.setValue("window_state", self.saveState())
            self.settings.setValue("dock_layout_version", DOCK_LAYOUT_VERSION)

        # 項目86: 「元に戻す」を経由せず切り離した状態のまま終了した場合も、
        # 次回起動時に同じ状態・ジオメトリで復元できるようここで保存する。
        # ★ ミニマップの表示/非表示やダークモードと同じ「軽量なUI設定」の
        # 性質のものなので、window_stateとは異なり最初のタブに限定しない。
        if self.canvas_detached and self._canvas_detach_window is not None:
            self.settings.setValue(
                CANVAS_DETACHED_GEOMETRY_KEY, self._canvas_detach_window.saveGeometry()
            )
        self.settings.setValue(CANVAS_WAS_DETACHED_KEY, self.canvas_detached)

        # 項目86: 切り離しウィンドウを開いたままこのタブ/アプリが閉じられると
        # 孤立したトップレベルウィンドウが残ってしまうため、ここで明示的に
        # 片付ける。★ 上で保存した「切り離されていた」状態をFalseに巻き戻して
        # しまわないよう、通常の再アタッチ処理(_reattach_canvas、closedシグナル
        # 経由でQSettingsを更新する)は経由せず、直接キャンバスを切り離して
        # ウィンドウだけを破棄する(self.canvasの親としてぶら下がったまま
        # deleteLater()されるとキャンバスごと破棄されてしまうため、
        # 明示的にsetParent(None)しておく)。
        if self._canvas_detach_window is not None:
            self._canvas_detach_window.closed.disconnect(self._on_detach_window_closed)
            self._canvas_detach_window.takeCentralWidget()
            self.canvas.setParent(None)
            self._canvas_detach_window.close()
            self._canvas_detach_window.deleteLater()
            self._canvas_detach_window = None

        super().closeEvent(event)

    def _check_autosave_recovery(self):
        """
        起動時に一度だけ呼ばれる。前回のセッションが正常終了しなかった
        (クラッシュ・強制終了など) と判断され、かつオートセーブファイルが
        残っている場合、復元するかどうかをユーザーに確認する。

        ★ 新形式(.graphica)への移行対応: このアプリのバージョンにアップデートした
        直後の初回起動では、旧バージョンで発生したクラッシュにより、新形式ではなく
        旧形式(.pkl)のオートセーブファイルだけが残っている可能性がある。そのため、
        新形式のファイルが見つからない場合は、同じベース名の旧形式ファイルが
        無いか一時的なフォールバックとして確認する(恒久的な二重管理ではなく、
        移行期のみの措置)。どちらの形式でも load_project 側が拡張子で判別する。
        """
        if self._had_clean_exit:
            return

        autosave_path = self._autosave_filename
        if not os.path.exists(autosave_path):
            legacy_path = os.path.splitext(self._autosave_filename)[0] + '.pkl'
            if os.path.exists(legacy_path):
                autosave_path = legacy_path
            else:
                return

        reply = QMessageBox.question(
            self, "オートセーブからの復元",
            "前回はプロジェクトが正常に終了しなかったようです。\n"
            "自動保存されていたデータを復元しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._load_project_from_path(autosave_path, add_to_recent=False)

    def _check_first_launch(self):
        """
        起動時に一度だけ呼ばれる。このPC/設定でまだ一度もウェルカムダイアログを
        表示していなければ、簡単な操作ガイドとサンプルデータの読み込み口を表示する。
        """
        if self.settings.value("has_shown_welcome", False, type=bool):
            return
        self.settings.setValue("has_shown_welcome", True)
        self._show_welcome_dialog()

    def _on_show_startup_screen(self):
        """
        「スタートアップ画面...」メニューの処理(項目C-912)。初回起動時にのみ
        表示される_check_first_launchのWelcomeDialogを、いつでも開けるように
        したもの(最近使ったファイル・サンプルデータ・書式テンプレートへの入口)。
        """
        self._show_welcome_dialog()

    def _show_welcome_dialog(self):
        """
        WelcomeDialog(初回起動時のウェルカム画面兼スタートアップ画面、項目C-912)を
        表示し、閉じた後の選択結果に応じた処理を行う共通ヘルパー。
        _check_first_launch(初回のみ)と_on_show_startup_screen(いつでも)の
        両方から呼ばれる。
        """
        dialog = WelcomeDialog(self, recent_files=self._get_recent_files())
        dialog.exec()
        if dialog.load_sample_requested:
            self._load_sample_data()
        elif dialog.selected_recent_file:
            self._on_open_recent_file(dialog.selected_recent_file)
        elif dialog.load_template_requested:
            self._on_load_plot_template()

    def _on_show_autosave_history(self):
        """
        「自動バックアップ履歴から復元...」メニューの処理(項目C-107)。
        既存のオートセーブ世代ローテーション(_rotate_autosave_generations、
        autosave.graphica / .1. / .2. …)が実際に残している世代ファイルを
        新しい順に列挙してAutosaveHistoryDialogで見せ、選択された世代を
        _load_project_from_path(add_to_recent=False)で読み込む
        (自動復元確認ダイアログ_check_autosave_recoveryと同じadd_to_recent=False
        の理由: 「最近使ったファイル」を汚さず、次回の上書き保存先にも
        しないため)。
        """
        base, ext = os.path.splitext(self._autosave_filename)
        candidates = [(self._autosave_filename, "現在(最新)")]
        for gen in range(1, AUTOSAVE_GENERATIONS):
            candidates.append((f"{base}.{gen}{ext}", f"{gen}世代前"))

        generations = []
        for path, label in candidates:
            if not os.path.exists(path):
                continue
            try:
                mtime_text = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                mtime_text = "(更新日時不明)"
            generations.append((path, label, mtime_text))

        if not generations:
            QMessageBox.information(self, "自動バックアップ履歴", "自動バックアップファイルが見つかりませんでした。")
            return

        dialog = AutosaveHistoryDialog(generations, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_path = dialog.get_selected_path()
        if not selected_path:
            return

        reply = QMessageBox.question(
            self, "自動バックアップ履歴",
            "選択した世代の内容で復元します。現在の未保存の変更は失われます。よろしいですか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._load_project_from_path(selected_path, add_to_recent=False)

    def _load_sample_data(self):
        """ウェルカムダイアログの「サンプルデータを開く」ボタンから呼ばれる"""
        sample_path = resource_path(os.path.join("sample_data", "cooling_curve_sample.csv"))
        if not os.path.exists(sample_path):
            QMessageBox.warning(self, "サンプルデータ", "サンプルデータファイルが見つかりませんでした。")
            return
        self.load_data(sample_path)

    def _update_autosave_path(self):
        """
        QSettingsの "autosave_dir" (環境設定ダイアログで指定可能) に基づいて
        self._autosave_filename を再計算する。保存先ディレクトリが存在しない
        場合は作成しておく(auto_save() が失敗しないようにするため)。

        ★ 実機フィードバック(バグ報告、ログで確認): 未設定/空文字時、以前は
        「アプリのフォルダ」のつもりでファイル名のみ(cwd相対)を使っていたが、
        これはCLAUDE.mdの「プロセスのカレントディレクトリに依存しない」方針に
        反しており、macOSで.appとして起動した際のcwdが読み取り専用領域になる
        ケースがあった(実機ログ: "[Errno 30] Read-only file system:
        'autosave.graphica'" が5分間隔で繰り返し失敗、オートセーブが実質
        機能していなかった)。ログファイル(gui/crash_handler.py)やユーザー
        プラグイン(get_user_plugins_dir)と同じget_app_data_dir()(常に
        書き込み可能なユーザーごとのディレクトリ)を既定値にする。
        """
        autosave_dir = self.settings.value("autosave_dir", "", type=str)
        if autosave_dir:
            try:
                os.makedirs(autosave_dir, exist_ok=True)
            except OSError as e:
                logger.warning("オートセーブ保存先フォルダの作成に失敗しました: %s", e)
                autosave_dir = ""
        if not autosave_dir:
            autosave_dir = get_app_data_dir()
        self._autosave_filename = os.path.join(autosave_dir, self._autosave_base_filename)

    def _rotate_autosave_generations(self):
        """
        オートセーブファイルを世代ローテーションする。
        autosave.graphica (拡張子は AUTOSAVE_FILENAME に依存) は常に最新の状態を指し、
        直前までの内容は autosave.1.graphica, autosave.2.graphica, ... として
        押し出される (AUTOSAVE_GENERATIONS世代を超える最古のものは破棄する)。
        """
        base, ext = os.path.splitext(self._autosave_filename)

        oldest = f"{base}.{AUTOSAVE_GENERATIONS - 1}{ext}"
        if os.path.exists(oldest):
            os.remove(oldest)

        for gen in range(AUTOSAVE_GENERATIONS - 2, 0, -1):
            src = f"{base}.{gen}{ext}"
            dst = f"{base}.{gen + 1}{ext}"
            if os.path.exists(src):
                os.replace(src, dst)

        if os.path.exists(self._autosave_filename):
            os.replace(self._autosave_filename, f"{base}.1{ext}")

    def _sync_project_from_ui(self):
        """
        UI 側にしか無い状態を、保存・比較の直前に ProjectModel へ反映する。
        フォルダ構造(ツリーの現在の状態)と、サブプロットの行数/列数
        (UIのスピンボックスが真の値で、self.project.layout_rows/cols には
        保存直前まで反映されないため、同期しないと常に既定値(1x1)で保存される)。
        """
        self.project.dataset_group_tree = self._capture_dataset_group_tree()
        self.project.layout_rows = self.subplot_rows_spinbox.value()
        self.project.layout_cols = self.subplot_cols_spinbox.value()

    def _remember_saved_content(self):
        """いまの内容を「保存済み」とみなす(保存・読み込みの成功直後に呼ぶ)。"""
        self._sync_project_from_ui()
        self._saved_content_fingerprint = self.project.content_fingerprint()

    def plugin_context(self, plugin_name):
        """このタブでプラグインに渡す窓口(PluginContext)。"""
        context = self._plugin_contexts.get(plugin_name)
        if context is None:
            context = TabPluginContext(self, plugin_name)
            self._plugin_contexts[plugin_name] = context
        return context

    def _notify_plugins_datasets_changed(self):
        for context in self._plugin_contexts.values():
            context._notify_datasets_changed()

    def _notify_plugins_selection_changed(self):
        current = self._get_current_dataset()
        for context in self._plugin_contexts.values():
            context._notify_selection_changed(current)

    def _run_plugin_menu_action(self, menu_action):
        try:
            menu_action.callback(self.plugin_context(menu_action.plugin_name))
        except Exception as e:
            logger.exception("[plugin:%s] メニュー「%s」の実行に失敗しました", menu_action.plugin_name, menu_action.text)
            QMessageBox.critical(self, "プラグインのエラー", str(PluginExecutionError(
                menu_action.plugin_name, f"「{menu_action.text}」の実行に失敗しました: {e}"
            )))

    def document_title(self):
        """タブ名・ウィンドウタイトル・保存確認に出す文書名。"""
        if self._current_project_path:
            return os.path.basename(self._current_project_path)
        if self._restored_unsaved:
            return "無題のプロジェクト(復元)"
        return "無題のプロジェクト"

    def has_unsaved_changes(self):
        """
        保存していない変更があるか(v1.4.2)。
        データセットが1つも無く、ファイルとも対応していない(新しいタブのまま)
        場合は、保存する意味のあるものが無いので False。
        """
        if not self.project.datasets and not self._current_project_path:
            return False
        if self._saved_content_fingerprint is None:
            return True  # 一度も保存していない、またはオートセーブから復元した
        self._sync_project_from_ui()
        return self.project.content_fingerprint() != self._saved_content_fingerprint

    def confirm_unsaved_changes(self, action_text):
        """
        未保存の変更があれば「保存 / 保存しない / キャンセル」を尋ねる(v1.4.2)。
        ウィンドウ/タブを閉じる前、別のプロジェクトを開く前に呼ぶ。

        Args:
            action_text (str): 何をしようとしているか(例: "タブを閉じる")。
        Returns:
            bool: 続行してよければ True(保存した・保存しないを選んだ・変更が無い)。
                キャンセルされた、または保存に失敗した場合は False。
        """
        if not _unsaved_changes_prompt_enabled() or not self.has_unsaved_changes():
            return True
        name = self.document_title()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("保存されていない変更")
        box.setText(f"「{name}」には保存されていない変更があります。")
        box.setInformativeText(f"{action_text}前に保存しますか?")
        save_button = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        discard_button = box.addButton("保存しない", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_button)
        box.setEscapeButton(cancel_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is discard_button:
            return True
        if clicked is save_button:
            self.manual_save()
            # 名前を付けて保存をキャンセルした/保存に失敗した場合は、続行しない
            return not self.has_unsaved_changes()
        return False

    def auto_save(self):
        """タイマーから定期的に呼ばれるオートセーブ処理"""
        try:
            self._sync_project_from_ui()
            self._rotate_autosave_generations()
            self.project.save_project(self._autosave_filename)
            self.statusBar().showMessage("オートセーブ完了", 3000)
        except Exception as e:
            logger.exception("オートセーブに失敗しました")
            self.statusBar().showMessage(f"オートセーブ失敗: {e}", 3000)

    def manual_save(self):
        """
        「上書き保存」の処理。実機フィードバック(「プロジェクトの上書き保存と
        名前つけて保存を追加」)を受け、以前は保存操作が常に「名前を付けて
        保存」ダイアログを開いていた(既存の保存先へ即座に上書きする手段が
        無かった)ものを分離した。self._current_project_path(現在開いている/
        直前に保存したプロジェクトのパス)が分かっていればそこへ直接
        上書き保存し、まだ一度も保存/読込していない(パス不明)場合のみ
        manual_save_as()にフォールバックしてダイアログを出す。
        """
        if not self._current_project_path:
            self.manual_save_as()
            return
        self._save_project_to_path(self._current_project_path)

    def manual_save_as(self):
        """「名前を付けて保存」の処理。常に保存先ダイアログを開く。"""
        # ★ 新形式(.graphica, JSON)をデフォルトの保存先とする。任意コード実行の
        #   リスクが無い安全なフォーマットへの移行を促すため、先頭のフィルタを
        #   .graphica にしている。ただし従来形式で保存したいユーザーのために、
        #   .pkl も引き続き選択できるようにしておく。
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "名前を付けて保存", "",
            "Graphica Project (*.graphica);;Project Files (*.pkl)"
        )
        if filepath:
            # 一部環境ではファイルダイアログが選択フィルタに応じた拡張子を
            # 自動付加しないため、拡張子が無い場合は選択されたフィルタから補う。
            if not os.path.splitext(filepath)[1]:
                filepath += '.graphica' if 'graphica' in selected_filter else '.pkl'
            self._save_project_to_path(filepath)

    def _save_project_to_path(self, filepath):
        """manual_save()/manual_save_as()共通の実際の保存処理。"""
        try:
            # フォルダ構造・サブプロットの行数/列数を保存直前に反映する
            self._sync_project_from_ui()
            self.project.save_project(filepath)
            self._current_project_path = filepath
            self._restored_unsaved = False
            self._saved_content_fingerprint = self.project.content_fingerprint()
            self.statusBar().showMessage(f"保存しました: {filepath}", 3000)
            self._add_recent_file(filepath)
            self.project_state_changed.emit()
        except Exception as e:
            logger.exception("プロジェクトの保存に失敗しました: %s", filepath)
            QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{e}")

    def manual_load(self):
        """ユーザーが読み込み操作をしたときの処理"""
        if not self.confirm_unsaved_changes("別のプロジェクトを開く"):
            return
        # 新形式(.graphica)・旧形式(.pkl)のどちらも開けるようにする
        # (project.load_project側が拡張子で自動判別する)
        filepath, _ = QFileDialog.getOpenFileName(
            self, "プロジェクトを開く", "", "Project Files (*.graphica *.pkl)"
        )
        if filepath:
            self._load_project_from_path(filepath)

    def _load_project_from_path(self, filepath, add_to_recent=True):
        """
        プロジェクト(.graphica / .pkl)を読み込み、UIを再構築する。

        Args:
            add_to_recent (bool): False はオートセーブからの復元。最近使ったファイルに
                載せず、上書き保存の対象にもしない(未保存扱い)。
        """
        try:
            self.project.load_project(filepath)
            # 中身はもう入れ替わっている。この先で失敗したとき前のファイルが保存先に
            # 残っていると、上書き保存でそのファイルを別の内容で壊してしまう。
            self._current_project_path = None
            self._saved_content_fingerprint = None
            self._restored_unsaved = False

            self._rebuild_dataset_tree_widget()

            self._block_all_signals(True)
            self.subplot_rows_spinbox.setValue(self.project.layout_rows)
            self.subplot_cols_spinbox.setValue(self.project.layout_cols)
            is_free_layout = getattr(self.project, 'layout_mode', 'grid') == 'free'
            self.free_layout_checkbox.setChecked(is_free_layout)
            self.subplot_rows_spinbox.setEnabled(not is_free_layout)
            self.subplot_cols_spinbox.setEnabled(not is_free_layout)
            self.add_free_subplot_button.setEnabled(is_free_layout)
            self.remove_free_subplot_button.setEnabled(is_free_layout)
            self.layout_edit_action.setEnabled(is_free_layout)
            if not is_free_layout and self.layout_edit_action.isChecked():
                self.layout_edit_action.setChecked(False)
                self._toggle_layout_edit_mode(False)
            self.panel_labels_action.setChecked(self.project.panel_labels_enabled)
            self.share_x_checkbox.setChecked(getattr(self.project, 'share_x_axis', False))
            self.share_y_checkbox.setChecked(getattr(self.project, 'share_y_axis', False))
            self.share_x_checkbox.setEnabled(not is_free_layout)
            self.share_y_checkbox.setEnabled(not is_free_layout)
            self._block_all_signals(False)

            # UIにアクティブな設定を反映
            if self.project.all_plot_settings:
                self._apply_settings_to_ui_controls(
                    self.project.all_plot_settings[self.project.active_axis_index]
                )

            # 前の文書へのコマンドは datasets をリストごと差し戻すので、残すと
            # Undo 1回で読み込んだ内容が前の文書に置き換わる。
            self.undo_stack.clear()

            # 画面状態とプロットの最終更新
            self.property_panel.update_ui_state()
            self._update_plot()

            self.statusBar().showMessage("プロジェクトを読み込みました", 3000)
            if add_to_recent:
                self._add_recent_file(filepath)
                self._current_project_path = filepath
                self._remember_saved_content()
            else:
                self._restored_unsaved = True
            self.project_state_changed.emit()
        except Exception as e:
            logger.exception("プロジェクトの読み込みに失敗しました: %s", filepath)
            QMessageBox.critical(self, "エラー", f"読み込みに失敗しました:\n{e}")

    def _reset_zoom(self):
        """
        ツールバー/マウスドラッグ等で拡大・パンした表示を、設定通りの既定表示
        (各軸のautoscale設定に従った全データ表示、または明示的に指定された
        軸範囲)に戻す。matplotlib純正のNavigationToolbar2QT自身のHomeボタンは
        内部で拡大操作時のAxesをキャッシュしているが、このアプリでは
        _update_plot()がfig.clf()で毎回Axesを作り直すため、作り直しを挟んだ
        後はHomeボタンのキャッシュが古いAxesを指したまま効かなくなることが
        ある(gui/canvas.pyのdocstring記載の既知の制約と同根)。ここでは
        キャッシュに頼らず、常に効く_update_plot()のフル再描画をそのまま
        使うことで確実にリセットする。
        """
        self._update_plot()

    def _update_plot(self, light=False, full_resolution=False):
        """
        グラフ全体を再描画する（MVC対応版）。

        light=True(項目C-003フェーズ2): Axesの枚数・GridSpec配置・所属
        (subplot_target/use_secondary_y)は一切変わらない、パネルラベル表示
        切替・ダークモード切替のようなトリガー専用の軽量パス。
        canvas.redraw_all()(fig.clf()で全Axesを作り直す)の代わりに
        canvas.update_all_axes_appearance_and_data()(既存Axesのデータ・外観
        だけを描き直す)を使う。呼び出し側は上記の前提が崩れないことを保証する
        こと(レイアウト行数/列数変更やデータセット追加削除では使わない)。

        full_resolution=True: LTTB表示用ダウンサンプリング(項目C-1001)を
        無視して常に全点描画する。単発エクスポート(export_mixin.py の
        _on_export_plot)が「フル解像度でエクスポート」オプション有効時に、
        savefig直前でTrueとして呼び、savefig後に既定(False)で呼び直して
        画面表示を通常の間引き済み状態へ戻す。
        """
        layout_mode = getattr(self.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            # 自由配置レイアウトでは行数×列数ではなく、all_plot_settingsの
            # 要素数そのものがサブプロット数になる (canvas.redraw_all側で使用)
            rows, cols = 0, 0
            if len(self.project.all_plot_settings) == 0:
                return
        else:
            rows = self.subplot_rows_spinbox.value()
            cols = self.subplot_cols_spinbox.value()
            if rows * cols == 0:
                return

        # ★ 描画処理をすべてCanvasに「丸投げ」する！
        canvas_update_method = (
            self.canvas.update_all_axes_appearance_and_data if light else self.canvas.redraw_all
        )
        is_secondary_visible_global = canvas_update_method(
            self.project.datasets, rows, cols, self.project.all_plot_settings, layout_mode=layout_mode,
            panel_labels_enabled=self.project.panel_labels_enabled,
            share_x_axis=getattr(self.project, 'share_x_axis', False),
            share_y_axis=getattr(self.project, 'share_y_axis', False),
            full_resolution=full_resolution,
        )

        # ★ Canvasから返ってきた結果をもとに、UI（チェックボックス等）を制御する
        self.tick_direction_y2_label.setVisible(is_secondary_visible_global)
        self.major_tick_direction_y2_combo.setVisible(is_secondary_visible_global)
        self.minor_tick_direction_y2_combo.setVisible(is_secondary_visible_global)
        self.y2_label_text_label.setVisible(is_secondary_visible_global)
        self.y2_label_text_edit.setVisible(is_secondary_visible_global)

        # データカーソル用にAxesの参照を同期
        self.all_axes = self.canvas.all_axes
        self.all_secondary_axes = self.canvas.all_secondary_axes

        # ★ エクスポートプレビューパネルが表示されている場合は、そちらも追従させる
        # (パネル非表示中は refresh_preview 内で何もしないため、常に呼んで問題ない)
        if hasattr(self, 'export_preview_panel'):
            self.export_preview_panel.refresh_preview()

        # ★ フルの再描画 (redraw_all) は Figure を作り直すため、以前のハイライト表示は
        #   消えてしまう。データエディタが開いていて行が選択中なら再度反映する。
        self._reapply_editor_row_highlight()

        # ミニマップは別の Figure なので、redraw_all() では描き直されない。
        self._refresh_minimap()
        self._notify_plugins_datasets_changed()

    def _refresh_minimap(self):
        """
        ミニマップ(項目83)の概観表示を、現在のデータセット/ダークモード設定に
        合わせて描き直す。ウィジェットがまだ作られていない(または非表示中の)
        場合でも安全に呼べるよう、常に描画自体は行う(非表示中でも次に表示した
        ときに最新の概観になっているようにするため)。
        """
        if not hasattr(self, 'minimap'):
            return
        self.minimap.refresh(self.project.datasets, self.canvas.dark_mode)

    def _on_minimap_range_selected(self, xmin, xmax):
        """
        ミニマップ(項目83)でドラッグ選択された範囲を、メインキャンバスの
        全サブプロットのX軸ズーム範囲として一括適用する。
        ★ ここでは _update_plot()(fig.clf()を伴うフル再描画)は呼ばない。
        ズーム範囲の変更だけならAxesを作り直す必要はなく、標準のナビゲーション
        ツールバーのズーム/パンと同様に set_xlim() + draw_idle() で十分かつ軽量。
        """
        for ax in self.canvas.all_axes:
            ax.set_xlim(xmin, xmax)
        self.canvas.draw_idle()

    def _on_toggle_minimap(self, checked):
        """「表示」メニューの「ミニマップ」チェック状態が変更されたときの処理。"""
        self.minimap_visible = checked
        self.minimap.setVisible(checked)
        self.minimap_separator.setVisible(checked)
        self.settings.setValue("minimap_visible", checked)

    def _on_toggle_panel_labels(self, checked):
        """
        「表示」メニューの「パネルラベルを自動表示」チェック状態が変更されたときの処理
        (項目C-712)。QSettingsではなくプロジェクトごとの状態として保存する
        (.graphica/.pklに含まれ、プロジェクトファイルを開き直すたびに復元される)。
        """
        self.project.panel_labels_enabled = checked
        self._update_plot(light=True)

    # --- ★ 項目86: マルチモニター対応(Canvasの別ウィンドウ切り離し) ---
    #
    # self.canvas (MplCanvas) は setParent() で再親付けされるだけで、
    # 破棄・再生成は一切行わない。cursor_mixin/annotation_mixin/
    # layout_edit_mixin/export_mixin/settings_mixin/project_io_mixin/
    # ui_setup_mixin など、アプリ内の多数の箇所が self.canvas を
    # インスタンス属性として直接参照し続けているため、同一性を保つことが
    # この機能が成立するための絶対条件(同じオブジェクトの「住所」が
    # 変わるだけ、という考え方)。

    def _on_toggle_canvas_detached(self, checked):
        """「表示」メニューの「キャンバスを別ウィンドウに切り離す」チェック状態が変更されたときの処理。"""
        if checked:
            self._detach_canvas()
        else:
            self._reattach_canvas()

    def _sync_canvas_detach_action(self):
        """
        self.canvas_detached の値をメニューのチェック状態・表示文言に反映する
        (二重トグル防止のためシグナルはブロックする)。切り離し中は「元に戻す」、
        非切り離し中は「切り離す」と、状態に応じて文言そのものを切り替える。
        """
        if not hasattr(self, 'canvas_detach_action'):
            return
        self.canvas_detach_action.blockSignals(True)
        self.canvas_detach_action.setChecked(self.canvas_detached)
        self.canvas_detach_action.setText(
            tr("キャンバスを元に戻す") if self.canvas_detached else tr("キャンバスを別ウィンドウに切り離す")
        )
        self.canvas_detach_action.blockSignals(False)

    def _detach_canvas(self, restore_geometry=False):
        """
        self.canvas を plot_container のレイアウトから取り外し、独立した
        トップレベルウィンドウ(DetachedCanvasWindow)へ再親付けする。
        OS標準のウィンドウ移動/最大化がそのまま使えるため、サブモニターへ
        ドラッグして最大化する、といった操作は呼び出し側では何もしなくてよい。

        Args:
            restore_geometry (bool): Trueの場合、QSettingsに保存された
                前回のウィンドウサイズ・位置を復元する(起動時の状態復元用)。
        """
        if self.canvas_detached:
            return

        self._plot_layout.removeWidget(self.canvas)

        title = f"{APP_NAME} - {tr('グラフキャンバス')}"
        self._canvas_detach_window = DetachedCanvasWindow(title)
        self._canvas_detach_window.setCentralWidget(self.canvas)
        self._canvas_detach_window.closed.connect(self._on_detach_window_closed)

        saved_geometry = self.settings.value(CANVAS_DETACHED_GEOMETRY_KEY) if restore_geometry else None
        if saved_geometry is not None:
            # ★ バグ修正済みパターンを踏襲: restoreGeometry() を show() より前
            #   (=このウィンドウがまだ一度もOSに実体化されていない段階)で
            #   呼ぶと、ウィンドウ枠の実寸が未確定なままジオメトリが復元され、
            #   画面上の位置とQtの内部認識がズレる(gui/main_app_window.py の
            #   同じ処理を参照)。winId()で先にネイティブハンドルを確定させる。
            self._canvas_detach_window.winId()
            self._canvas_detach_window.restoreGeometry(saved_geometry)
        else:
            self._canvas_detach_window.resize(DEFAULT_DETACHED_CANVAS_WIDTH, DEFAULT_DETACHED_CANVAS_HEIGHT)

        self._canvas_detach_window.show()
        self.canvas.show()

        self.canvas_detached = True
        self._sync_canvas_detach_action()
        self.settings.setValue(CANVAS_WAS_DETACHED_KEY, True)

    def _reattach_canvas(self):
        """
        切り離されたキャンバスを plot_container のレイアウトへ、元の位置
        (canvas_separatorの直後)にそのまま戻す。「元に戻す」メニュー操作、
        および切り離しウィンドウがOSの×ボタンで閉じられた場合の両方から
        呼ばれる。
        """
        if not self.canvas_detached:
            return

        if self._canvas_detach_window is not None:
            # 閉じる前に現在のサイズ・位置を保存しておく(次回の切り離し時、
            # および次回起動時の復元に使う)。
            self.settings.setValue(
                CANVAS_DETACHED_GEOMETRY_KEY, self._canvas_detach_window.saveGeometry()
            )
            self._canvas_detach_window.closed.disconnect(self._on_detach_window_closed)
            self._canvas_detach_window.takeCentralWidget()
            self._canvas_detach_window.close()
            self._canvas_detach_window.deleteLater()
            self._canvas_detach_window = None

        self.canvas.setParent(self.ui.plot_container)
        self._plot_layout.insertWidget(self._canvas_layout_index, self.canvas)
        self.canvas.show()

        self.canvas_detached = False
        self._sync_canvas_detach_action()
        self.settings.setValue(CANVAS_WAS_DETACHED_KEY, False)

    def _on_detach_window_closed(self):
        """
        切り離しウィンドウがOSの×ボタンで閉じられたときに呼ばれる
        (DetachedCanvasWindow.closeEvent -> closed シグナル経由)。
        「元に戻す」メニュー操作と全く同じ後処理(_reattach_canvas)に合流させる。
        """
        self._reattach_canvas()

    def _update_plot_appearance(self):
        """外観のみを更新する（MVC対応版）"""
        layout_mode = getattr(self.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            rows, cols = 0, 0
        else:
            rows = self.subplot_rows_spinbox.value()
            cols = self.subplot_cols_spinbox.value()
        # 外観の更新もCanvasに丸投げ
        self.canvas.update_appearance_only(
            self.project.all_plot_settings, datasets=self.project.datasets, rows=rows, cols=cols,
            layout_mode=layout_mode,
            share_x_axis=getattr(self.project, 'share_x_axis', False),
            share_y_axis=getattr(self.project, 'share_y_axis', False),
        )

        if hasattr(self, 'export_preview_panel'):
            self.export_preview_panel.refresh_preview()

    def _on_editor_rows_highlighted(self, master_indices):
        """
        データエディタ (DataEditorDialog) で選択されている行が変わったときに呼ばれる。
        対応するデータ点をグラフ上でハイライトする(逆方向: グラフ上の点クリックで
        エディタの行を選択する処理は cursor_mixin.py の _on_pick 側にある)。
        """
        if self.data_editor_dialog is None:
            return
        self.canvas.set_highlighted_points(self.data_editor_dialog.dataset, master_indices)

    def _reapply_editor_row_highlight(self):
        """データエディタが開いていれば、現在選択中の行のハイライトを再描画後に復元する"""
        if self.data_editor_dialog is None:
            return
        self.canvas.set_highlighted_points(
            self.data_editor_dialog.dataset, self.data_editor_dialog.get_selected_master_indices()
        )

    def _wrap_in_collapsible_section(self, group_box, title):
        """
        折りたたみ可能に(項目102): 「データセットのプロパティ」「プロットの
        プロパティ」をアコーディオン形式(クリックで開閉)にするためのヘルパー。

        group_box (QGroupBox) 自体の内部構造には一切手を加えず、外側に新しい
        開閉トグルボタン(シェブロンアイコン付き)を1つ追加し、そのボタンで
        group_box 全体(枠・中身ごと)の表示/非表示を切り替える。
        タイトルの二重表示を避けるため、group_box 自身のタイトルは空にし、
        トグルボタン側にだけ表示する。
        """
        group_box.setTitle("")
        # theme.py の QDockWidget QGroupBox は「自身のタイトルを置く場所」として
        # margin-top/padding-top を確保する。ここではタイトルを空にして見出しを
        # 外のトグルボタンへ移しているので、その確保分は見出しと中身の間の
        # 死んだ隙間にしかならない。プロパティで見分けて0にする。
        group_box.setProperty("collapsibleBody", True)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(2)

        toggle_button = QToolButton()
        toggle_button.setText(title)
        toggle_button.setCheckable(True)
        toggle_button.setChecked(True)
        toggle_button.setIcon(_svg_icon("chevron-down", size=14))
        toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle_button.setObjectName("collapsible_section_toggle")
        toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def _on_toggled(checked, box=group_box, btn=toggle_button):
            box.setVisible(checked)
            btn.setIcon(_svg_icon("chevron-down" if checked else "chevron-right", size=14))

        toggle_button.toggled.connect(_on_toggled)
        # ★ 項目H-4: このメソッドは複数のグループボックスに対して繰り返し
        #   呼ばれるため、生成した各トグルボタンをリストに蓄積しておき、
        #   _refresh_custom_svg_icons側で一括してアイコンを再読み込みできる
        #   ようにする。
        if not hasattr(self, '_collapsible_toggle_buttons'):
            self._collapsible_toggle_buttons = []
        self._collapsible_toggle_buttons.append(toggle_button)

        wrapper_layout.addWidget(toggle_button)
        wrapper_layout.addWidget(group_box)
        return wrapper

    #==========================================================================
    # データセットのプロパティパネルのサブセクション (改善ボード C-1)
    #==========================================================================

    def _build_dataset_property_sections(self):
        """
        「データセットのプロパティ」の中身を、DATASET_PROPERTY_SECTIONS で定義した
        7つの折りたたみ可能なサブセクションに分割する(改善ボード C-1)。

        Designer が作った formLayout_4 に全部を縦積みするのをやめ、セクションごとに
        独立した QFormLayout を持たせる。これには2つの効果がある:

        1. 番号指定の insertRow(N, ...) が不要になる。従来は行1〜5の挿入が
           「この順に実行されること」に依存しており、間に1行足すと無関係な
           フィールドが黙ってずれるという地雷だった(CLAUDE.md参照)。
        2. QFormLayout の列幅は「そのレイアウト内の最長ウィジェット」で決まるため、
           レイアウトを分ければ幅の波及もセクション内に閉じる。D-2 で踏んだ
           「plot_type_combo が広がってフォーム全体が横にはみ出す」波及範囲が、
           フォーム全体から「基本スタイル」1セクションへ縮む。

        Designer 生成の8行(凡例名/種別/色/線の種類/線の太さ/マーカー/サイズ/平滑化)は
        takeRow() で formLayout_4 から取り外して移設する。removeRow() はウィジェット
        ごと破棄してしまうので使ってはいけない。平滑化チェックボックスだけは、
        後から追加される「透明度」「平滑化の手法」との並び順を揃えるため、ここでは
        移設せず保留し、_prop_form('style') への追加は呼び出し側が行う
        (self._pending_smoothing_checkbox_row)。
        """
        self._prop_sections = {}

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        collapsed = self._load_collapsed_property_sections()

        for key, title in DATASET_PROPERTY_SECTIONS:
            body = QWidget()
            form = QFormLayout(body)
            # 見出し7本ぶんの高さは純増になるので、上下の余白は詰める。
            # ★ 実機フィードバック:「見出しと項目の区別がつきにくい」
            #   →「インデントが逆転してるのなんかやだ」。実測すると、親の見出しは
            #   padding-left:4px で描かれるのに対し子の見出しは0で、子のほうが
            #   4px左に出ていた。親(4px) → 子(theme.pyで12px) → 中身(ここ)
            #   の階段になるよう字下げする。
            form.setContentsMargins(24, 2, 0, 6)
            form.setSpacing(6)

            toggle_button = QToolButton()
            toggle_button.setText(tr(title))
            toggle_button.setCheckable(True)
            toggle_button.setIcon(_svg_icon("chevron-down", size=13))
            toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            # ★ トップレベルの2セクション(項目102)とは別のobjectNameにする。
            #   theme.py 側で一段控えめな見出しとしてスタイルでき、既存の
            #   「トグルボタンはちょうど2つ」というテストも壊れない。
            toggle_button.setObjectName("property_subsection_toggle")
            toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # QToolButton の既定は「文字幅ぴったり」なので、区切りの罫線
            # (theme.py の border-top) が見出しの文字の下までしか引かれない。
            # 横いっぱいに広げて、罫線がセクションの区切りとして機能するようにする。
            toggle_button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            toggle_button.setChecked(key not in collapsed)
            # 1本目だけは上の罫線を引かない(親の見出しのすぐ下なので二重線に見える)。
            if key == DATASET_PROPERTY_SECTIONS[0][0]:
                toggle_button.setProperty("firstSection", True)

            section = QWidget()
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(0)
            section_layout.addWidget(toggle_button)
            section_layout.addWidget(body)
            body.setVisible(toggle_button.isChecked())

            toggle_button.toggled.connect(
                lambda checked, k=key: self._on_property_section_toggled(k, checked))

            container_layout.addWidget(section)
            self._prop_sections[key] = {
                'form': form, 'body': body, 'toggle': toggle_button, 'section': section,
            }

        # 空になった formLayout_4 は、Designer 生成物 (ui_main_window.py) 側の
        # 構造なので取り除かずそのまま残す。余白だけ潰して高さ0にしておく。
        for row in range(self.ui.formLayout_4.rowCount() - 1, -1, -1):
            self.ui.formLayout_4.takeRow(row)
        self.ui.formLayout_4.setContentsMargins(0, 0, 0, 0)
        self.ui.formLayout_4.setSpacing(0)
        # Designer の既定余白(9px)は、見出しと最初のセクションの間の隙間に
        # なるだけなので落とす(左右のインデントは各セクションの body 側が持つ)。
        self.ui.gridLayout_4.setContentsMargins(0, 0, 0, 0)
        self.ui.gridLayout_4.addWidget(container, 1, 0, 1, 1)
        self._dataset_property_sections_container = container

        # ★ 実機フィードバック:「データ追加するまで(セクションを)動かせない」。
        #   Designer は properties_groupbox 自体を setEnabled(False) にしており、
        #   Qt では無効な親の下のウィジェットは個別に有効化できないため、
        #   中に入れたセクション見出しまで道連れで押せなくなっていた。
        #   開閉は「選択中のデータセットを編集する操作」ではなく「パネルの
        #   見せ方を変える操作」なので、選択の有無とは無関係に常に押せるべき。
        #   グループボックスは常に有効にしておき、無効化はセクションの中身
        #   (body)だけに掛ける。
        self.ui.properties_groupbox.setEnabled(True)
        self._set_dataset_property_fields_enabled(False)

        style_form = self._prop_form('style')
        style_form.addRow(self.ui.legend_name_label, self.ui.legend_name_edit)
        style_form.addRow(self.ui.plot_type_label, self.ui.plot_type_combo)
        style_form.addRow(self.ui.color_label, self.color_picker_widget)
        style_form.addRow(self.ui.linestyle_label, self.ui.linestyle_combo)
        style_form.addRow(self.ui.linewidth_label, self.ui.linewidth_spinbox)
        style_form.addRow(self.ui.marker_label, self.ui.marker_combo)
        style_form.addRow(self.ui.makersize_label, self.ui.markersize_spinbox)

        # D-2 でフラグした横はみ出し対策: コンボ自身の希望幅を文字数で固定し、
        # プラグインが長い種別名を登録しても列幅が引きずられないようにする。
        self.ui.plot_type_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.ui.plot_type_combo.setMinimumContentsLength(PLOT_TYPE_COMBO_MIN_CHARS)

    def _prop_form(self, section_key):
        """サブセクション(DATASET_PROPERTY_SECTIONS のキー)の QFormLayout を返す。"""
        return self._prop_sections[section_key]['form']

    def _align_form_label_columns(self, forms):
        """
        複数の QFormLayout でラベル列の幅を揃える(実機フィードバック:
        「X軸タブとY軸タブで入力ボックスの大きさが微妙に違う」
        「ここのタブでボックスの大きさばらばら」)。

        QFormLayout のラベル列幅は「**そのレイアウト内**で最も widest なラベル」で
        決まる。X軸/Y軸タブのように別々のレイアウトが縦に切り替わる場合や、
        C-1 でプロパティパネルを7つのレイアウトに分けた場合、レイアウトごとに
        列幅が変わるため、入力欄の左端が揃わずガタつく。全ラベルの最大幅を
        求めて、全員にその最小幅を課すことで列幅を共有させる。

        ★ 非表示のラベルも計算に含める。QFormLayout は非表示のウィジェットを
        列幅の計算から外すため、含めないと「対数表示をONにした瞬間に
        『対数軸の補助目盛り』が現れて列幅が広がり、入力欄が一斉にずれる」
        という別のガタつきが残る。

        戻り値は決定した列幅(px)。
        """
        labels = []
        widest = 0
        for form in forms:
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if item is None or not isinstance(item.widget(), QLabel):
                    continue
                label = item.widget()
                labels.append(label)
                widest = max(widest, label.sizeHint().width())

        for label in labels:
            label.setMinimumWidth(widest)
        return widest

    def _set_dataset_property_fields_enabled(self, enabled):
        """
        データセットのプロパティ「欄」の有効/無効を切り替える(選択が無いときは無効)。

        ★ 無効化するのは各セクションの中身(body)だけで、見出しのトグルボタンと
        properties_groupbox 自体は常に有効なままにする。以前は
        properties_groupbox を丸ごと無効化していたが、Qt は無効な親の下の子を
        個別に有効化できないため、データセットを1つも追加していない状態では
        セクションの開閉すらできなかった(実機フィードバック)。
        """
        for entry in getattr(self, '_prop_sections', {}).values():
            entry['body'].setEnabled(enabled)

    def _load_collapsed_property_sections(self):
        """QSettings から「閉じている」セクションキーの集合を読む(既定は空=全展開)。"""
        raw = self.settings.value(DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY, "[]")
        try:
            keys = json.loads(raw) if isinstance(raw, str) else list(raw)
        except (ValueError, TypeError):
            return set()
        valid = {key for key, _ in DATASET_PROPERTY_SECTIONS}
        return {k for k in keys if k in valid}

    def _on_property_section_toggled(self, section_key, checked):
        """
        サブセクションの開閉。本体の表示を切り替え、シェブロンの向きを直し、
        閉じているセクションの一覧を QSettings へ書き戻す(ユーザー決定:
        既定は全展開だが、一度閉じたものは次の起動でも閉じたまま)。
        """
        entry = self._prop_sections.get(section_key)
        if entry is None:
            return
        entry['body'].setVisible(checked)
        entry['toggle'].setIcon(
            _svg_icon("chevron-down" if checked else "chevron-right", size=13))

        collapsed = sorted(
            key for key, _ in DATASET_PROPERTY_SECTIONS
            if not self._prop_sections[key]['toggle'].isChecked()
        )
        self.settings.setValue(
            DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY, json.dumps(collapsed))

    def _update_property_section_visibility(self):
        """
        中身の行が1つも表示されないセクションは、見出しごと隠す。

        条件付き表示(property_panel.update_gradient_controls_visibility 等)で中身が全部消えた
        セクションの見出しだけが残ると、折りたたみで減らしたぶんの場所を
        見出しが食い返してしまう。C-2 で「選択状態によって空になるサブメニューは
        出さない」としたのと同じ方針。
        """
        sections = getattr(self, '_prop_sections', None)
        if not sections:
            return
        for key, _ in DATASET_PROPERTY_SECTIONS:
            entry = sections.get(key)
            if entry is None:
                continue
            form = entry['form']
            has_visible = False
            for row in range(form.rowCount()):
                for role in (QFormLayout.ItemRole.LabelRole,
                             QFormLayout.ItemRole.FieldRole,
                             QFormLayout.ItemRole.SpanningRole):
                    item = form.itemAt(row, role)
                    if item is not None and item.widget() is not None \
                            and not item.widget().isHidden():
                        has_visible = True
                        break
                if has_visible:
                    break
            entry['section'].setVisible(has_visible)

    #==========================================================================
    # データセットリスト (QTreeWidget) 関連のヘルパー
    #==========================================================================
    # dataset_list_widget は Designer 上は QListWidget だが、フォルダによる
    # グループ分けに対応するため __init__ の最初 (_replace_dataset_list_with_tree)
    # で QTreeWidget に差し替えている。データセットは「leaf」、フォルダは
    # 「内部ノード」として表現し、leaf の Qt.ItemDataRole.UserRole には対応する
    # Dataset オブジェクトそのものを、フォルダには None を格納することで区別する。

    def _replace_dataset_list_with_tree(self):
        """
        Designer が生成した dataset_list_widget (QListWidget) を、
        同じレイアウト位置に「検索ボックス + QTreeWidget」の縦並びコンテナで
        置き換える。QGridLayout上の1セルに収まる構成にすることで、他のセルの
        配置に影響を与えずに検索ボックスをツリーの直上へ追加できる。
        """
        old_widget = self.ui.dataset_list_widget
        parent_widget = old_widget.parentWidget()
        parent_layout = parent_widget.layout()

        idx = parent_layout.indexOf(old_widget)
        row = col = rowspan = colspan = None
        if isinstance(parent_layout, QGridLayout):
            row, col, rowspan, colspan = parent_layout.getItemPosition(idx)

        parent_layout.removeWidget(old_widget)
        old_widget.setParent(None)
        old_widget.deleteLater()

        container = QWidget(parent_widget)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        # ★ 項目H-2-2(実機フィードバック): 検索ボックスとリストの間の余白を
        #   狭すぎると感じたとの指摘を受け、元の4pxから約1.5倍の6pxに広げた。
        container_layout.setSpacing(6)

        search_edit = QLineEdit(container)
        # ★ 項目H-2-2: 検索ボックス単体の枠線を消すQSS(theme.py側
        #   #dataset_search_edit)をスコープするためのobjectName。リストと
        #   統合するためではなく、あくまで検索ボックス自身の見た目調整用。
        search_edit.setObjectName("dataset_search_edit")
        search_edit.setPlaceholderText("データセットを検索...")
        search_edit.setClearButtonEnabled(True)
        container_layout.addWidget(search_edit)

        tree = QTreeWidget(container)
        tree.setObjectName("dataset_list_widget")
        tree.setHeaderHidden(True)
        # ★ 項目C-907: 列0(スタイルアイコン+名前、既存)に加え、列1に
        #   表示/非表示トグル用の目アイコン専用の列を追加する。ヘッダーは非表示
        #   (setHeaderHidden)だが、列0を伸縮(Stretch)・列1を固定幅(Fixed)にする
        #   ことで、ウィンドウ幅が変わっても目アイコンが常に同じ位置・幅を保つ。
        #   デフォルトのstretchLastSectionがTrueのままだと最後の列(=目アイコン列)
        #   が余白を吸収して不必要に広がってしまうため明示的に無効化する。
        tree.setColumnCount(2)
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(DATASET_TREE_NAME_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(DATASET_TREE_VISIBILITY_COLUMN, QHeaderView.ResizeMode.Fixed)
        tree.setColumnWidth(DATASET_TREE_VISIBILITY_COLUMN, DATASET_TREE_VISIBILITY_COLUMN_WIDTH)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # ★ GUI洗練: gridLayout_2の行stretchを0にした(キャンバスへ余白を譲る)ため、
        #   このリストはsizeHint任せだと窮屈すぎる高さまで縮む可能性がある。
        #   データが2〜3件程度でも下に大きな空白ができない程度の高さを確保する。
        tree.setMinimumHeight(90)
        # ★ 項目H-2-2: 選択ハイライトをアイコン列+テキスト列にまたがる単一の
        #   角丸矩形として描画するための専用デリゲート(理由は
        #   _DatasetTreeSelectionDelegateのdocstringを参照)。
        tree.setItemDelegate(_DatasetTreeSelectionDelegate(tree))
        container_layout.addWidget(tree)

        # 項目69: リストとボタン行の間の余白を、選択中データセットのミニ統計で埋める
        # (詳細な統計は引き続きプロパティタブの stats_summary_label に表示する。
        #  こちらは「今何を選んでいるか」がリストのすぐ下で一目で分かるようにする用途)
        mini_stats_label = QLabel("-")
        mini_stats_label.setObjectName("dataset_mini_stats_label")
        mini_stats_label.setWordWrap(True)
        container_layout.addWidget(mini_stats_label)
        self.dataset_mini_stats_label = mini_stats_label

        if isinstance(parent_layout, QGridLayout) and row is not None:
            parent_layout.addWidget(container, row, col, rowspan, colspan)
        else:
            parent_layout.addWidget(container)

        self.ui.dataset_list_widget = tree
        self.dataset_search_edit = search_edit

    def _add_dataset_list_item(self, dataset, parent_item=None):
        """
        dataset_list_widget にデータセットの葉(leaf)アイテムを追加する共通ヘルパー。
        Dataset オブジェクトそのものを Qt.ItemDataRole.UserRole に保持させることで、
        ドラッグ&ドロップによる並べ替え後も (同名データセットがあっても) 各アイテムが
        どの Dataset に対応するかを一意に追跡できるようにする。

        Args:
            dataset (Dataset): 追加するデータセット。
            parent_item (QTreeWidgetItem, optional): 追加先のフォルダ。
                None ならツリーの最上位に追加する。
        """
        item = QTreeWidgetItem([dataset.name])
        item.setData(0, Qt.ItemDataRole.UserRole, dataset)
        item.setIcon(0, make_dataset_style_icon(dataset))
        # ★ 項目C-907: 専用列(列1)に表示/非表示トグル用の目アイコンを表示する。
        #   クリック検知は _on_dataset_tree_item_clicked (dataset_mixin.py) が
        #   itemClicked シグナル経由で列インデックスを見て判定する。
        item.setIcon(DATASET_TREE_VISIBILITY_COLUMN, make_dataset_visibility_icon(dataset))
        apply_dataset_visibility_text_style(item, dataset)
        # データセット自身はフォルダではないので、ドロップ先にはしない
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
        if parent_item is not None:
            parent_item.addChild(item)
        else:
            self.ui.dataset_list_widget.addTopLevelItem(item)
        return item

    def _get_target_folder_for_new_dataset(self):
        """
        現在ツリーで選択中のアイテムがフォルダであれば、それを返す
        (新規データセットをそのフォルダの中に追加するため)。それ以外は None。
        """
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is not None and current_item.data(0, Qt.ItemDataRole.UserRole) is None:
            return current_item
        return None

    def _add_dataset(self, dataset, parent_folder=None, select=True):
        """
        新しい Dataset を project.datasets とツリーウィジェットの両方に追加し、
        必要ならプロットも再描画する共通ヘルパー。
        ファイル読み込み・データセット間演算・バッチ処理・クリップボード貼り付けなど、
        「新しいDatasetを1つ作って追加する」複数の機能から共通で使われる。
        """
        self.project.datasets.append(dataset)
        new_item = self._add_dataset_list_item(dataset, parent_folder)
        if select:
            self.ui.dataset_list_widget.setCurrentItem(new_item)
        self._update_plot()
        return new_item

    def _add_dataset_with_undo(self, dataset, parent_folder=None, description="データセットの追加"):
        """
        _add_dataset() をUndo/Redo可能にしたバージョン(項目C-1、プラグインの
        register_processor/register_analyzerが生成したDatasetの追加専用)。
        AddDatasetCommand参照: 既存の他の追加経路(規格化・Savitzky-Golay等)は
        意図的にUndo非対応のまま据え置いている(削除側は改善ボード A-3 で
        _remove_dataset_items_with_undo() としてUndo対応済み)。
        """
        def do_add():
            self._add_dataset(dataset, parent_folder, select=True)

        def do_remove():
            row = self._find_dataset_row(dataset)
            if row != -1:
                del self.project.datasets[row]
            item = self._get_dataset_tree_item(dataset)
            if item is not None:
                parent = item.parent()
                if parent is not None:
                    parent.removeChild(item)
                else:
                    idx = self.ui.dataset_list_widget.indexOfTopLevelItem(item)
                    if idx != -1:
                        self.ui.dataset_list_widget.takeTopLevelItem(idx)
            self.property_panel.update_ui_state()
            self._update_plot()

        command = AddDatasetCommand(do_add, do_remove, description=description)
        self.undo_stack.push(command)

    def _remove_dataset_items_with_undo(self, top_level_items, description=None):
        """
        ツリー上のアイテム(データセットの葉、またはフォルダ)をUndo/Redo可能に
        削除する共通ヘルパー(改善ボード A-3、RemoveDatasetCommand参照)。

        `top_level_items` には「最上位の削除対象」だけを渡すこと
        (フォルダとその中身が両方選択されていた場合、フォルダだけを渡す。
        dataset_mixin._top_level_selected_items がこの絞り込みを行う)。
        フォルダを渡すと、その中のデータセットもまとめて削除・復元される。

        復元時に元の見た目へ正確に戻すため、削除の前に次の2つを控えておく:

        - `project.datasets` のリスト全体(=描画順/重なり順)。削除で
          インデックスがずれるため、行単位ではなくリストごと差し戻す。
        - 各アイテムのツリー上の位置(親アイテムと、その親の中でのインデックス)。
          フォルダの中の何番目だったかまで復元する。

        取り外したQTreeWidgetItemはクロージャが参照を保持し続けるため破棄されず、
        そのまま同じオブジェクトを差し戻せる(子アイテム=フォルダの中身も
        ぶら下がったまま維持される)。
        """
        tree = self.ui.dataset_list_widget

        # --- 削除前のスナップショット ---
        snapshots = []  # [(item, parent_item_or_None, index_in_parent), ...]
        for item in top_level_items:
            parent = item.parent()
            index = parent.indexOfChild(item) if parent is not None else tree.indexOfTopLevelItem(item)
            if index == -1:
                continue  # 既にツリーから外れている(想定外だが安全側に倒す)
            snapshots.append((item, parent, index))
        if not snapshots:
            return

        def collect_datasets(item, out):
            dataset = item.data(0, Qt.ItemDataRole.UserRole)
            if dataset is not None:
                out.append(dataset)
            else:  # フォルダ: 中身を再帰的に集める
                for i in range(item.childCount()):
                    collect_datasets(item.child(i), out)

        removed_datasets = []
        for item, _parent, _index in snapshots:
            collect_datasets(item, removed_datasets)

        datasets_before = list(self.project.datasets)

        if description is None:
            if len(removed_datasets) == 1:
                description = f"「{removed_datasets[0].name}」の削除"
            else:
                description = f"{len(removed_datasets)}件のデータセットの削除"

        def do_remove():
            # 【★ 重要 ★】ツリー操作中に currentItemChanged が意図せず発行されるのを防ぐ
            tree.blockSignals(True)
            try:
                rows_to_remove = sorted(
                    {row for ds in removed_datasets if (row := self._find_dataset_row(ds)) != -1},
                    reverse=True
                )
                for row in rows_to_remove:
                    del self.project.datasets[row]

                # 同じ親を持つアイテムが複数ある場合にインデックスがずれないよう降順で外す
                for item, parent, _index in sorted(snapshots, key=lambda s: s[2], reverse=True):
                    if parent is not None:
                        parent.removeChild(item)
                    else:
                        idx = tree.indexOfTopLevelItem(item)
                        if idx != -1:
                            tree.takeTopLevelItem(idx)
            finally:
                tree.blockSignals(False)
            self.property_panel.update_ui_state()
            self._update_plot()

        def do_restore():
            tree.blockSignals(True)
            try:
                # 控えておいた元のインデックスへ昇順に差し戻す(降順で外した逆順)
                for item, parent, index in sorted(snapshots, key=lambda s: s[2]):
                    if parent is not None:
                        parent.insertChild(min(index, parent.childCount()), item)
                    else:
                        tree.insertTopLevelItem(min(index, tree.topLevelItemCount()), item)
                # 行単位ではなくリストごと差し戻して、描画順もまとめて元に戻す
                # (リストオブジェクト自体は入れ替えず中身だけ差し替える)
                self.project.datasets[:] = datasets_before
            finally:
                tree.blockSignals(False)
            self.property_panel.update_ui_state()
            self._update_plot()

        self.undo_stack.push(
            RemoveDatasetCommand(do_remove, do_restore, description=description)
        )

    def _add_dataset_folder_item(self, name, parent_item=None):
        """dataset_list_widget にフォルダ(内部ノード)を追加する共通ヘルパー"""
        item = QTreeWidgetItem([name])
        item.setData(0, Qt.ItemDataRole.UserRole, None) # None はフォルダの目印
        if parent_item is not None:
            parent_item.addChild(item)
        else:
            self.ui.dataset_list_widget.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    def _flatten_dataset_tree(self, parent_item=None):
        """
        ツリーを先行順 (depth-first) に辿り、データセットの leaf アイテムだけを
        表示順のリストとして返す (フォルダ自体は含めず、中身を再帰的に辿る)。
        この順序がそのままプロットの描画順 (project.datasets の順序) になる。
        """
        items = []
        tree = self.ui.dataset_list_widget
        source = tree.invisibleRootItem() if parent_item is None else parent_item
        for i in range(source.childCount()):
            child = source.child(i)
            dataset = child.data(0, Qt.ItemDataRole.UserRole)
            if dataset is not None:
                items.append(child)
            else:
                items.extend(self._flatten_dataset_tree(child))
        return items

    def _get_current_dataset(self):
        """現在「カレント」になっているアイテムに対応する Dataset を返す (フォルダやNoneならNone)"""
        item = self.ui.dataset_list_widget.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _get_selected_datasets(self):
        """選択中の全アイテムのうち、データセット (フォルダでない) だけをリストで返す"""
        result = []
        for item in self.ui.dataset_list_widget.selectedItems():
            dataset = item.data(0, Qt.ItemDataRole.UserRole)
            if dataset is not None:
                result.append(dataset)
        return result

    def _get_dataset_tree_item(self, dataset):
        """指定した Dataset に対応する QTreeWidgetItem を検索する (オブジェクト同一性で判定)"""
        for item in self._flatten_dataset_tree():
            if item.data(0, Qt.ItemDataRole.UserRole) is dataset:
                return item
        return None

    def _capture_dataset_group_tree(self):
        """現在の dataset_list_widget の状態から、保存用のフォルダ構造 (辞書) を構築する"""
        def walk(parent_item):
            children = []
            source = self.ui.dataset_list_widget.invisibleRootItem() if parent_item is None else parent_item
            for i in range(source.childCount()):
                child = source.child(i)
                dataset = child.data(0, Qt.ItemDataRole.UserRole)
                if dataset is not None:
                    children.append({'dataset': dataset})
                else:
                    children.append({'name': child.text(0), 'children': walk(child)})
            return children
        return {'name': '', 'children': walk(None)}

    def _rebuild_dataset_tree_widget(self):
        """project.dataset_group_tree からツリーウィジェットの中身を再構築する"""
        tree = self.ui.dataset_list_widget
        tree.clear()

        def build(node, parent_item):
            for child_node in node.get('children', []):
                if 'dataset' in child_node:
                    self._add_dataset_list_item(child_node['dataset'], parent_item)
                else:
                    folder_item = self._add_dataset_folder_item(child_node.get('name', 'フォルダ'), parent_item)
                    build(child_node, folder_item)

        build(self.project.dataset_group_tree, None)

    def _sync_dataset_list_widget_order(self):
        """
        project.datasets の現在の順序に合わせて、各フォルダ内でのデータセットの
        表示順を再構築する (フォルダ自体の位置や、フォルダ間の移動は行わない)。
        データセットの並べ替えを Undo/Redo したとき、コマンドが project.datasets の
        順序だけを書き換えるため、ウィジェット側の表示順をこれに追従させるために使う。
        選択状態と「現在の項目」もできる限り復元する。
        """
        tree = self.ui.dataset_list_widget
        order_index = {id(ds): i for i, ds in enumerate(self.project.datasets)}
        selected_ids = {id(item.data(0, Qt.ItemDataRole.UserRole)) for item in tree.selectedItems()}
        current_item = tree.currentItem()
        current_dataset = current_item.data(0, Qt.ItemDataRole.UserRole) if current_item else None

        tree.blockSignals(True)

        def sort_children(parent_item):
            source = tree.invisibleRootItem() if parent_item is None else parent_item
            children = [source.child(i) for i in range(source.childCount())]

            # データセットの葉だけを project.datasets の順序に従って並べ替え、
            # フォルダは元の相対位置のまま動かさない
            dataset_positions = [
                i for i, c in enumerate(children) if c.data(0, Qt.ItemDataRole.UserRole) is not None
            ]
            dataset_items_sorted = sorted(
                (children[i] for i in dataset_positions),
                key=lambda it: order_index.get(id(it.data(0, Qt.ItemDataRole.UserRole)), 0)
            )
            new_children = list(children)
            for pos, item in zip(dataset_positions, dataset_items_sorted):
                new_children[pos] = item

            for _ in range(source.childCount()):
                source.takeChild(0)
            for item in new_children:
                source.addChild(item)

            for item in new_children:
                if item.data(0, Qt.ItemDataRole.UserRole) is None:
                    sort_children(item)

        sort_children(None)

        for item in self._flatten_dataset_tree():
            ds = item.data(0, Qt.ItemDataRole.UserRole)
            if id(ds) in selected_ids:
                item.setSelected(True)
            if ds is current_dataset:
                tree.setCurrentItem(item)
        tree.blockSignals(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """
        複数ファイルの一括ドラッグ&ドロップ読み込み(項目77)。
        ドロップされた全ファイルパスを取得し、対応拡張子のものだけを
        読み込みキューに積む。実際の読み込みは _process_next_queued_file() が
        既存の単一ファイル読み込み経路 (load_data) を使って1件ずつ順番に行う。
        """
        urls = event.mimeData().urls()
        file_paths = [url.toLocalFile() for url in urls if url.toLocalFile()]
        if file_paths:
            self._queue_data_files(file_paths)

    def _all_supported_data_file_extensions(self):
        """
        ドラッグ&ドロップ一括取込・ファイルダイアログで受け付ける拡張子一覧。
        ビルトイン対応分(SUPPORTED_DATA_FILE_EXTENSIONS)に、プラグインが
        register_importer() (項目B-1) で登録した拡張子を加えたもの。
        """
        extensions = list(SUPPORTED_DATA_FILE_EXTENSIONS)
        for ext in get_registered_importer_extensions():
            if ext not in extensions:
                extensions.append(ext)
        return tuple(extensions)

    def _queue_data_files(self, file_paths):
        """
        ドロップ/一括指定された複数のファイルパスを、対応拡張子かどうかで
        振り分ける。非対応拡張子はまとめて1回の警告ダイアログでスキップを
        通知し(1ファイルずつダイアログを出さない)、対応拡張子のファイルは
        読み込みキューに積んで、他に読み込み中でなければ処理を開始する。
        """
        valid_paths = []
        skipped_names = []
        allowed_extensions = self._all_supported_data_file_extensions()
        for file_path in file_paths:
            if file_path.lower().endswith(allowed_extensions):
                valid_paths.append(file_path)
            else:
                skipped_names.append(os.path.basename(file_path))

        if skipped_names:
            QMessageBox.warning(
                self, "非対応のファイル形式",
                "以下のファイルは対応していない形式のため読み込みをスキップしました:\n"
                + "\n".join(skipped_names)
            )

        if not valid_paths:
            return

        self._data_load_queue.extend(valid_paths)
        self._data_load_queue_total += len(valid_paths)

        if self._data_load_task_runner is None:
            self._process_next_queued_file()
        # 既に読み込み中の場合は、その完了後に _process_next_queued_file が
        # 自動的にキューの続きを処理する

    def _process_next_queued_file(self):
        """
        読み込みキューの先頭を取り出し、load_data() で読み込みを開始する。
        キューが空ならバッチの進捗カウンタをリセットするだけで何もしない。
        _on_data_load_succeeded / _on_data_load_failed の両方から、読み込みの
        成否によらず呼ばれる(1件読み終わるたびに次を進める)。
        """
        if not self._data_load_queue:
            self._data_load_queue_total = 0
            self._data_load_queue_done = 0
            # 項目C-104: フォルダ一括インポートのファイル名正規表現は、その
            # バッチが完全に処理し終わったタイミングでリセットする(以降の
            # 通常のドラッグ&ドロップ取込みに引き継がれないようにするため)。
            self._batch_import_filename_regex = None
            return

        next_path = self._data_load_queue.pop(0)
        self._data_load_queue_done += 1
        self.load_data(next_path, queue_progress=(self._data_load_queue_done, self._data_load_queue_total))

    def load_data(self, file_path, queue_progress=None):
        """
        ファイルをバックグラウンドスレッドで読み込み、既存のDataset(Model)とUIに反映させる。
        大きなCSV/Excelファイルでも、読み込み中にUIがフリーズしないようにするため、
        実際のファイルI/O (gui/workers.py の load_data_file_task) は
        TaskRunner(項目C-004フェーズ4)経由で別スレッドで実行する。

        queue_progress: ドラッグ&ドロップの複数ファイル一括読み込み(項目77)で、
            キュー内の進捗を (現在の件数, 総件数) のタプルで渡すと、
            ステータスバーに "読み込み中 (2/5): ..." のように表示する。
            単体読み込み(メニューからの「データセット追加」等)では None のまま。
        """
        if self._data_load_task_runner is not None:
            QMessageBox.information(self, "読み込み中", "他のファイルを読み込み中です。完了までお待ちください。")
            return

        self.ui.add_dataset_button.setEnabled(False)
        if queue_progress is not None:
            done, total = queue_progress
            self.statusBar().showMessage(f"読み込み中 ({done}/{total}): {os.path.basename(file_path)} ...")
        else:
            self.statusBar().showMessage(f"読み込み中: {file_path} ...")

        runner = TaskRunner(load_data_file_task, file_path, parent=self)
        runner.succeeded.connect(lambda df: self._on_data_load_succeeded(df, file_path))
        runner.failed.connect(lambda msg: self._on_data_load_failed(msg, file_path))
        self._data_load_task_runner = runner
        runner.start()

    def _on_data_load_succeeded(self, df, file_path):
        """
        ファイル読み込みに成功したときに呼ばれるスロット。
        実際のデータセット追加処理は _import_loaded_dataframe に委譲し、
        その途中でユーザーがダイアログをキャンセルした場合も含め、
        必ず finally でキューの次のファイル読み込みに進む
        (複数ファイル一括ドラッグ&ドロップ、項目77)。
        """
        self._cleanup_data_load_task_runner()
        try:
            self._import_loaded_dataframe(df, file_path)
        finally:
            self._process_next_queued_file()

    def _import_loaded_dataframe(self, df, file_path):
        """
        複数シートを持つExcelファイルの場合、シートを複数選択すると
        シートごとに別々のデータセットとして追加できる(未選択/単一選択の場合は
        従来通り1ファイル=1データセットの読み込みフローになる)。
        """
        dataset_name = os.path.basename(file_path)
        is_excel = is_excel_file(file_path)

        sheet_names = []
        if is_excel:
            try:
                sheet_names = pd.ExcelFile(file_path, engine=excel_engine_for(file_path)).sheet_names
            except Exception as e:
                logger.warning("Excelのシート一覧取得に失敗しました: %s", e)

        # None は「ワーカーが既に読み込み済みの df をそのまま使う」ことを表す
        # (従来通りの、シート選択ダイアログを介さない単純な読み込みフロー)
        sheets_to_import = [None]
        if is_excel and len(sheet_names) > 1:
            multi_dialog = ExcelMultiSheetDialog(sheet_names, self)
            if multi_dialog.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage("読み込みをキャンセルしました", 3000)
                return
            selected_sheets = multi_dialog.get_selected_sheets()
            if not selected_sheets:
                self.statusBar().showMessage("シートが選択されなかったため読み込みをキャンセルしました", 3000)
                return
            sheets_to_import = selected_sheets

        target_folder = self._get_target_folder_for_new_dataset()
        added_count = 0

        for sheet_name in sheets_to_import:
            if sheet_name is None:
                sheet_df = df  # ワーカーが既に読み込み済みのDataFrame
                preview_name = dataset_name
            else:
                try:
                    sheet_df = pd.read_excel(file_path, sheet_name=sheet_name, engine=excel_engine_for(file_path))
                except Exception as e:
                    logger.exception("シート「%s」の読み込みに失敗しました", sheet_name)
                    QMessageBox.warning(self, "読み込みエラー", f"シート「{sheet_name}」の読み込みに失敗しました:\n{e}")
                    continue
                if sheet_df.shape[1] < 2:
                    QMessageBox.warning(
                        self, "読み込みエラー",
                        f"シート「{sheet_name}」には少なくとも2列必要です。スキップします。"
                    )
                    continue
                preview_name = f"{dataset_name} [{sheet_name}]" if len(sheets_to_import) > 1 else dataset_name

            if is_excel:
                checked_sheet = sheet_name if sheet_name is not None else (sheet_names[0] if sheet_names else None)
                found, examples, scanned_all = find_unevaluated_formula_cells(file_path, checked_sheet)
                if found:
                    example_text = "\n".join(examples)
                    more_note = "" if scanned_all else "\n(他にも存在する可能性があります)"
                    reply = QMessageBox.warning(
                        self, "数式セルの警告",
                        f"シート「{checked_sheet}」に、計算済みの値を持たない数式セルが見つかりました:\n"
                        f"{example_text}{more_note}\n\n"
                        "これらのセルは空欄(NaN)として読み込まれます。Excelで開いて再計算・保存してから"
                        "読み込み直すことをお勧めします。このまま続行しますか?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        continue

            # ★ 列数の多いファイルで意図しない列が自動選択されるのを防ぐため、
            #   プレビューを見せつつX/Y軸の列をユーザーに選ばせる。
            #   Excelファイルの場合は、このダイアログ内でシート切り替え・ヘッダー行・
            #   使用する列(usecols)・最大行数(nrows)の指定も行える。
            preview_dialog = ColumnPreviewDialog(sheet_df, preview_name, self, file_path=file_path)
            if sheet_name is not None and preview_dialog.sheet_combo is not None:
                preview_dialog.sheet_combo.blockSignals(True)
                preview_dialog.sheet_combo.setCurrentText(sheet_name)
                preview_dialog.sheet_combo.blockSignals(False)

            if preview_dialog.exec() != QDialog.DialogCode.Accepted:
                continue  # このシート/ファイルだけスキップ (複数シート選択時は他のシートは続行)

            x_col, y_col = preview_dialog.get_selected_columns()
            # シート/ヘッダー行/usecols/nrowsを変更していた場合はそちらを反映したDataFrameを使う
            final_df = preview_dialog.get_dataframe()

            # 元ファイルへのリンク保持(項目C-103): 「再読み込み」
            # (gui/datasets/transfer.py の reload_from_source)が
            # このパスからファイルを読み直せるよう、絶対パスを保持しておく。
            # Excelでシートを切り替えていた場合に備え、ダイアログのシートコンボの
            # 最終的な選択値(checked_sheetではなく、こちらが実際に使われた値)を使う。
            source_sheet = (
                preview_dialog.sheet_combo.currentText()
                if (is_excel and preview_dialog.sheet_combo is not None) else None
            )
            # フォルダ一括インポート(項目C-104)でファイル名正規表現が指定されて
            # いれば、ファイル名から抽出した値を新しい列として追加する。
            if self._batch_import_filename_regex:
                final_df = self._apply_filename_regex_columns(
                    final_df, file_path, self._batch_import_filename_regex
                )
            new_dataset = Dataset(
                name=preview_name, df=final_df, x_col_name=x_col, y_col_name=y_col,
                source_file=os.path.abspath(file_path), source_sheet=source_sheet,
            )
            self._add_dataset(new_dataset, target_folder)
            added_count += 1

        if added_count > 0:
            self.statusBar().showMessage(f"読み込み完了: {file_path} ({added_count}件)", 3000)
            self._add_recent_file(file_path)
        else:
            self.statusBar().showMessage("読み込みをキャンセルしました", 3000)

    @staticmethod
    def _apply_filename_regex_columns(df, file_path, pattern):
        """
        フォルダ一括インポート(項目C-104)で指定した正規表現の名前付きグループ
        (?P<name>...)を、ファイル名(拡張子込みのbasename)から抽出して新しい列
        として追加する(各行に同じ値をブロードキャスト)。数値に変換できる値は
        float列として、できなければ文字列列として追加する。パターンが不正/
        マッチしない/名前付きグループが無い場合は、インポート自体は継続したい
        ため例外を投げず元のdfをそのまま返す(呼び出し側のFolderImportDialog
        でも同じロジックのライブプレビューを見せているため、通常はここで
        マッチしない事態にはならない想定だが、フォルダ内のファイル名が
        統一されていないケースへの保険)。
        """
        try:
            match = re.search(pattern, os.path.basename(file_path))
        except re.error as e:
            logger.warning("正規表現が不正なため、ファイル名からの列抽出をスキップしました: %s", e)
            return df
        if match is None:
            return df
        groups = match.groupdict()
        if not groups:
            return df

        df = df.copy()
        for name, value in groups.items():
            if value is None:
                continue
            try:
                df[name] = float(value)
            except (TypeError, ValueError):
                df[name] = value
        return df

    def _on_import_folder(self):
        """
        「フォルダから一括インポート...」メニューの処理(項目C-104)。

        フォルダ内の対応拡張子ファイル(サブフォルダは対象外、_all_supported_
        data_file_extensions()で判定)を集め、FolderImportDialogで対象一覧と
        任意のファイル名正規表現(測定条件をファイル名から抜き出して新しい
        列にする)を確認させた上で、既存のドラッグ&ドロップ一括取込み機構
        (_queue_data_files)にそのまま渡す。列選択・シート選択等のダイアログは
        ファイルごとに引き続き表示される(複数ファイルドラッグ&ドロップと
        同じ挙動、フォルダ一括インポート固有の省略はしない)。
        """
        dir_path = QFileDialog.getExistingDirectory(self, "フォルダから一括インポート", "")
        if not dir_path:
            return

        allowed_extensions = self._all_supported_data_file_extensions()
        try:
            file_paths = sorted(
                str(p) for p in Path(dir_path).iterdir()
                if p.is_file() and p.suffix.lower() in allowed_extensions
            )
        except OSError as e:
            QMessageBox.warning(self, "フォルダから一括インポート", f"フォルダの読み取りに失敗しました:\n{e}")
            return

        if not file_paths:
            QMessageBox.information(
                self, "フォルダから一括インポート",
                "対応する形式のファイルがフォルダ内に見つかりませんでした。"
            )
            return

        file_names = [os.path.basename(p) for p in file_paths]
        dialog = FolderImportDialog(dir_path, file_names, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._batch_import_filename_regex = dialog.get_regex_pattern()
        self._queue_data_files(file_paths)

    def _on_paste_data_from_clipboard(self):
        """
        「クリップボードから貼り付け」メニューの処理(項目C-102、スマート貼り付け)。
        Excel/スプレッドシートでコピーしたセル範囲は、クリップボードに
        タブ区切りテキストとして格納されるのが一般的だが、プレーンテキストの
        CSV(カンマ区切り)やセミコロン区切りのデータが貼り付けられることもある
        ため、区切り文字を自動判定する(gui/workers.pyのdetect_clipboard_delimiter、
        C-101のファイル読み込みウィザードと同じSnifferロジックを共有)。
        """
        text = QApplication.clipboard().text()
        if not text.strip():
            QMessageBox.information(self, "クリップボードから貼り付け", "クリップボードにテキストデータがありません。")
            return

        from graphica.gui.workers import detect_clipboard_delimiter
        delimiter = detect_clipboard_delimiter(text)
        try:
            df = pd.read_csv(io.StringIO(text), sep=delimiter, engine='python')
        except Exception as e:
            logger.exception("クリップボードの内容を表として読めませんでした")
            QMessageBox.warning(
                self, "貼り付けエラー",
                f"クリップボードの内容を表として解釈できませんでした:\n{e}"
            )
            return

        if df.shape[1] < 2:
            QMessageBox.warning(self, "貼り付けエラー", "クリップボードのデータには少なくとも2列必要です。")
            return

        self._clipboard_paste_counter = getattr(self, '_clipboard_paste_counter', 0) + 1
        dataset_name = f"クリップボード貼り付け {self._clipboard_paste_counter}"

        preview_dialog = ColumnPreviewDialog(df, dataset_name, self, file_path=None)
        if preview_dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("貼り付けをキャンセルしました", 3000)
            return

        x_col, y_col = preview_dialog.get_selected_columns()
        final_df = preview_dialog.get_dataframe()
        new_dataset = Dataset(name=dataset_name, df=final_df, x_col_name=x_col, y_col_name=y_col)
        self._add_dataset(new_dataset, self._get_target_folder_for_new_dataset())
        self.statusBar().showMessage("クリップボードからデータを貼り付けました", 3000)

    def _on_data_load_failed(self, error_message, file_path):
        """
        ファイル読み込みに失敗したときに呼ばれるスロット。
        失敗時も、複数ファイル一括ドラッグ&ドロップ(項目77)のキューが
        残っていれば次のファイルの読み込みに進む。
        """
        self._cleanup_data_load_task_runner()
        self.statusBar().clearMessage()
        QMessageBox.critical(self, "エラー", f"読み込みエラー: {error_message}")
        self._process_next_queued_file()

    def _localize_navigation_toolbar(self, toolbar):
        """
        matplotlib純正のNavigationToolbar2QTが持つボタンのツールチップは、
        matplotlib側にハードコードされた英語文字列("Reset original view"等)の
        ため、アプリ全体を日本語化してもここだけ英語のまま残ってしまう。
        NavigationToolbar2QT._actions(コールバックメソッド名→QActionの辞書、
        matplotlib内部実装だが長年安定している)経由でツールチップ/ステータス
        バー文言を差し替える。将来のmatplotlibで_actionsの構造が変わっても
        アプリがクラッシュしないよう、失敗時は静かに元の英語表示のまま諦める。
        """
        labels = {
            'home': (tr("元の表示に戻す"), tr("最初の表示範囲にリセットします")),
            'back': (tr("前の表示に戻る"), tr("1つ前の表示範囲に戻ります")),
            'forward': (tr("次の表示に進む"), tr("戻る前の表示範囲に進みます")),
            'pan': (tr("パン/ズーム"),
                    tr("左ドラッグで移動、右ドラッグで拡大縮小(x/yキーで軸固定)")),
            'zoom': (tr("矩形ズーム"), tr("ドラッグした矩形範囲に拡大します(x/yキーで軸固定)")),
            'configure_subplots': (tr("サブプロット調整"), tr("サブプロット間の余白を調整します")),
            'save_figure': (tr("画像として保存"), tr("グラフを画像ファイルとして保存します")),
        }
        try:
            actions = toolbar._actions
        except AttributeError:
            logger.warning("NavigationToolbar2QTの_actionsが見つからず、ツールチップの日本語化をスキップしました。")
            return
        for name, action in actions.items():
            localized = labels.get(name)
            if localized is None:
                continue
            tooltip, status_tip = localized
            action.setToolTip(tooltip)
            action.setStatusTip(status_tip)

    def _cleanup_data_load_task_runner(self):
        """読み込み完了/失敗後の後片付け(UIの再有効化とTaskRunnerの破棄)"""
        self.ui.add_dataset_button.setEnabled(True)
        if self._data_load_task_runner is not None:
            self._data_load_task_runner.wait()
            self._data_load_task_runner.deleteLater()
            self._data_load_task_runner = None

    #==========================================================================
    # 最近使ったファイル一覧
    #==========================================================================
    # プロジェクト(.graphica/.pkl)とデータファイル(csv/xlsx等)の両方をまとめて履歴管理する。
    # 履歴自体は QSettings で永続化するため、アプリを再起動しても保持される。

    def _get_recent_files(self):
        """QSettings から履歴リスト (新しい順) を取得する"""
        files = self.settings.value("recent_files", [])
        if isinstance(files, str):
            # QSettings は要素数1のリストを単一の文字列として返すことがあるため補正する
            files = [files]
        return list(files) if files else []

    def _add_recent_file(self, file_path):
        """履歴の先頭にファイルパスを追加し、上限件数でトリムして保存する"""
        file_path = os.path.abspath(file_path)
        files = self._get_recent_files()
        if file_path in files:
            files.remove(file_path)
        files.insert(0, file_path)
        files = files[:MAX_RECENT_FILES]
        self.settings.setValue("recent_files", files)
        self._update_recent_files_menu()

    def _update_recent_files_menu(self):
        """「最近使ったファイル」サブメニューの中身を、現在の履歴に合わせて再構築する"""
        try:
            self.recent_files_menu.clear()
            files = self._get_recent_files()

            if not files:
                empty_action = self.recent_files_menu.addAction("(履歴なし)")
                empty_action.setEnabled(False)
                return

            for file_path in files:
                action = self.recent_files_menu.addAction(file_path)
                action.triggered.connect(lambda checked=False, p=file_path: self._on_open_recent_file(p))

            self.recent_files_menu.addSeparator()
            clear_action = self.recent_files_menu.addAction("履歴をクリア")
            clear_action.triggered.connect(self._on_clear_recent_files)
        except RuntimeError:
            # ★ ごく稀に、このメニューのC++側オブジェクトが既に破棄されている
            #   状態でこのメソッドが呼ばれることがある(shiboken6絡みの既知の
            #   問題、原因箇所は未特定)。実害は「履歴メニューの表示が古いまま」
            #   程度のため、アプリ全体をクラッシュさせずログに残すだけに留める。
            logger.warning("recent_files_menuの更新に失敗しました(既に破棄されている可能性があります)。", exc_info=True)

    def _on_open_recent_file(self, file_path):
        """「最近使ったファイル」の項目がクリックされたときの処理"""
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", f"ファイルが見つかりません:\n{file_path}")
            files = self._get_recent_files()
            if file_path in files:
                files.remove(file_path)
                self.settings.setValue("recent_files", files)
                self._update_recent_files_menu()
            return

        if file_path.lower().endswith(('.graphica', '.pkl')):
            if not self.confirm_unsaved_changes("別のプロジェクトを開く"):
                return
            self._load_project_from_path(file_path)
        else:
            self.load_data(file_path)

    def _on_clear_recent_files(self):
        """「履歴をクリア」がクリックされたときの処理"""
        self.settings.setValue("recent_files", [])
        self._update_recent_files_menu()
