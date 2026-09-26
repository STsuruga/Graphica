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

# 入力途中の "1e" や "1e-" も通す
_SCIENTIFIC_INPUT_RE = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)?([eE][+-]?\d*)?$')


def _scientific_text_from_value(self, value):
    """末尾のゼロを落とし、必要なら指数表記にする(.16g は float64 の有効桁数)。"""
    return f'{value:.16g}'


def _scientific_validate(self, text, pos):
    """QDoubleSpinBox の validate() は "1e-" のような入力途中を弾き、指数表記を打ち込めないので上書きする。"""
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
    spin_box.setDecimals(SPIN_BOX_MAX_DECIMALS)
    spin_box.setRange(minimum, maximum)
    spin_box.textFromValue = types.MethodType(_scientific_text_from_value, spin_box)
    spin_box.validate = types.MethodType(_scientific_validate, spin_box)
    spin_box.setSingleStep(single_step)


def _strip_trailing_colon_from_labels(widget):
    """ラベル末尾の「：」を取る。生成物の ui_main_window.py に焼き込まれていて、.ui が無く作り直せない。

    動的に足したラベルも含むよう、画面を組み立て終えてから呼ぶ。
    """
    from PySide6.QtWidgets import QLabel
    for label in widget.findChildren(QLabel):
        text = label.text()
        if text.endswith('：'):
            label.setText(text[:-1])

DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 800
CONTROL_DOCK_WIDTH = 472  # 縦スクロールバーの分まで含めた幅。狭めると横スクロールバーが出る
EXPORT_PREVIEW_DOCK_INITIAL_HEIGHT = 340
SPIN_BOX_MAX_DECIMALS = 16

# 列番号は dataset_mixin も使うので gui/dataset_style_icon.py にある(循環 import を避けるため)
DATASET_TREE_VISIBILITY_COLUMN_WIDTH = 26  # 目のアイコン(16px)+クリックの余白

DEFAULT_DETACHED_CANVAS_WIDTH = 900
DEFAULT_DETACHED_CANVAS_HEIGHT = 700

# ドックの既定の配置を変えたら上げる。保存時の値と違えば保存済みの配置を戻さない
# (戻すと、新しい既定の配置が既存の利用者に届かない)。
DOCK_LAYOUT_VERSION = 4

# データセットのプロパティ欄の節。行は self._prop_form(キー).addRow で足す(番号指定の挿入はしない)。
DATASET_PROPERTY_SECTIONS = (
    ('data',      'データ列'),
    ('style',     '基本スタイル'),
    ('gradient',  'グラデーション'),
    ('waterfall', 'ウォーターフォール'),
    ('map',       '2Dマップ・値による配色'),
    ('extra',     '表示の追加要素'),
    ('place',     '配置・情報'),
)

# プラグインの種類名は任意の長さなので、コンボの希望幅を固定して省略表示させる
# (広がると QFormLayout の列幅を通じてドックに横スクロールバーが出る)。
PLOT_TYPE_COMBO_MIN_CHARS = 16

COLORMAP_CHOICES = [
    'viridis', 'plasma', 'inferno', 'magma', 'cividis',
    'coolwarm', 'RdBu', 'seismic', 'jet', 'turbo',
    'gray', 'Blues', 'Greens', 'Reds', 'YlOrRd',
]

AUTOSAVE_FILENAME = "autosave.graphica"
AUTOSAVE_GENERATIONS = 3  # 最新の autosave.graphica を含む

MAX_RECENT_FILES = 10

from graphica.gui import notify
from graphica.gui.workers import BUILTIN_DATA_FILE_EXTENSIONS  # noqa: E402
SUPPORTED_DATA_FILE_EXTENSIONS = BUILTIN_DATA_FILE_EXTENSIONS

# 未保存の変更の確認を出すか。テストはモーダルなダイアログで止まるので tests/conftest.py が "0" にする
UNSAVED_CHANGES_PROMPT_ENV = "GRAPHICA_CONFIRM_UNSAVED_CHANGES"


def _unsaved_changes_prompt_enabled():
    return os.environ.get(UNSAVED_CHANGES_PROMPT_ENV, "1") != "0"

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QComboBox, QLabel, QSpinBox, QDoubleSpinBox, QPushButton,
                               QTextEdit, QCheckBox, QGroupBox, QSizePolicy, QWidget,
                               QDockWidget, QScrollArea, QMessageBox,
                               QLineEdit, QHBoxLayout, QFormLayout, QAbstractItemView,
                               QDialog, QTreeWidget, QTreeWidgetItem, QGridLayout,
                               QMenu, QFrame, QToolButton, QWidgetAction,
                               QStyledItemDelegate, QStyleOptionViewItem, QStyle, QHeaderView)
from PySide6.QtGui import QFont, QIcon, QAction, QValidator, QUndoStack, QPainter, QPainterPath
from PySide6.QtCore import Qt, QTimer, QSize, Signal, QRectF, QByteArray
from graphica.models.project import ProjectModel
from graphica.core.version import APP_NAME, __version__
from graphica.core.i18n import tr, set_language
from graphica.core.plugin_api import load_plugins_once, get_registered_importer_extensions
from graphica.core.plugin_types import PluginExecutionError
from graphica.gui import app_settings
from graphica.gui.app_settings import disabled_plugin_names
from graphica.gui.datasets.colors import ColorController
from graphica.gui.datasets.transfer import TransferController
from graphica.gui.datasets.overlays import OverlayController
from graphica.gui.datasets.plugin_runs import PluginRunController
from graphica.gui.datasets.property_panel import DatasetPropertyPanel
from graphica.gui.datasets.fitting import FittingController
from graphica.gui.datasets.host import DatasetHost
from graphica.gui.datasets.order import DatasetOrder
from graphica.gui.datasets.peaks import PeakController
from graphica.gui.datasets.processing import ProcessingController
from graphica.gui.plugin_context import TabPluginContext
from graphica.core.app_paths import get_app_data_dir, get_user_plugins_dir

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

from graphica.ui_main_window import Ui_MainWindow

from graphica.core.dataset import Dataset, COLOR_BY_COLUMN_PLOT_TYPE
from graphica.core.unit_conversion import X_AXIS_UNIT_CHOICES, X_AXIS_UNIT_LABELS
from graphica.core.commands import AddDatasetCommand, RemoveDatasetCommand
from graphica.gui.canvas import MplCanvas, DEFAULT_MAJOR_TICK_LENGTH, MINOR_TICK_LENGTH_AUTO
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

# Qt 既定の 24px だと、狭いウィンドウでボタンが「>>」に押し込まれて押せない
TOOLBAR_ICON_SIZE = 18

# 文字装飾パネルの記号。(表示, mathtext のマクロ名)。引数の要るマクロ(\sqrt{...})は
# 「$\macro$」で挿入できないので入れない(平方根は \surd)。
LABEL_SYMBOL_PALETTE = [
    ("α", "alpha"), ("β", "beta"), ("γ", "gamma"), ("δ", "delta"),
    ("ε", "epsilon"), ("μ", "mu"), ("π", "pi"), ("ρ", "rho"),
    ("Σ", "Sigma"), ("σ", "sigma"), ("τ", "tau"), ("Ω", "Omega"),
    ("ω", "omega"), ("Δ", "Delta"), ("θ", "theta"), ("φ", "phi"),
    ("×", "times"), ("÷", "div"), ("±", "pm"), ("∓", "mp"),
    ("≈", "approx"), ("≠", "neq"), ("≤", "leq"), ("≥", "geq"),
    ("∞", "infty"), ("→", "rightarrow"), ("←", "leftarrow"), ("∂", "partial"),
    ("∇", "nabla"), ("∫", "int"), ("∝", "propto"), ("°", "degree"),
    # マイナス記号(U+2212)は mathtext で包まず、文字のまま入れる
    ("−", None),
]


def _svg_icon(name, size=20):
    """テーマの text_secondary 色で描いたアイコン。テーマが変わっても自動では変わらない

    (常に見えているものは _refresh_custom_svg_icons で作り直す)。
    """
    from graphica.gui import theme
    color = theme.current_tokens()["text_secondary"]
    return load_svg_icon(resource_path(os.path.join(ICONS_DIR, f"{name}.svg")),
                          color=color, size=size)


def find_unevaluated_formula_cells(file_path, sheet_name=None, max_examples=5, max_scan_cells=200_000):
    """openpyxl の読み込み(約350ms)を起動時に払わないよう、呼ぶときに import する。

    テストがこのモジュール属性を monkeypatch で差し替えるので、名前を変えない。
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

# グラフの既定フォント。UI のフォント("Yu Gothic UI" など)は matplotlib が解決できず文字化けする。
# "Yu Gothic" は Windows だけにあるので、OS ごとの候補を並べたリストを QFont と matplotlib の両方に渡す
# (無いフォント名は飛ばされる)。
PLOT_DEFAULT_FONT_FAMILIES = JP_CAPABLE_FONT_FAMILIES


def _make_default_plot_font():
    """QFont(str) は1つの名前しか取らないので、setFamilies() で候補を全部入れる。"""
    font = QFont()
    font.setFamilies(PLOT_DEFAULT_FONT_FAMILIES)
    return font

from graphica.gui.mixins.ui_setup_mixin import UISetupMixin
from graphica.gui.mixins.settings_mixin import SettingsMixin
from graphica.gui.mixins.dataset_mixin import DatasetMixin
from graphica.gui.mixins.mouse_mode_mixin import MouseModeMixin
from graphica.gui.mixins.cursor_mixin import CursorMixin
from graphica.gui.mixins.annotation_mixin import AnnotationMixin
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
    """同梱のリソースの絶対パス。凍結時は sys._MEIPASS、ソースからは graphica/ を基準にする。

    カレントディレクトリは使わない(起動の仕方次第でアイコンなどが読めなくなる)。
    """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)


def is_frozen():
    return hasattr(sys, '_MEIPASS')


def plugin_search_paths():
    """プラグインの探索先(優先順)。同梱の plugins と、利用者のフォルダ(%LOCALAPPDATA%\\Graphica\\plugins)。

    同梱のフォルダはソースから動かすときだけあるので、あるときだけ加える
    (探索先は起動時に作られるので、無いものを渡すと site-packages の中に作ろうとする)。
    """
    paths = []
    bundled = resource_path("plugins")
    if not is_frozen() and os.path.isdir(bundled):
        paths.append(bundled)
    paths.append(get_user_plugins_dir())
    return paths


# core は Qt に依存しないので、area の文字列から Qt の値への変換はここでする
_PLUGIN_PANEL_AREA_MAP = {
    "right": Qt.DockWidgetArea.RightDockWidgetArea,
    "left": Qt.DockWidgetArea.LeftDockWidgetArea,
    "top": Qt.DockWidgetArea.TopDockWidgetArea,
    "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
}

class _DatasetTreeSelectionDelegate(QStyledItemDelegate):
    """選択の背景を、アイコンの列と文字の列にまたがる1つの角丸で描く。

    QSS の ::item:selected は2つの列に別々の角丸を描き、間に隙間ができる。背景だけ自前で塗り、
    State_Selected を外してから標準の描画に任せる。
    """

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        if opt.state & QStyle.StateFlag.State_Selected:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # 展開矢印の字下げの分だけ左が空くので、左端まで塗る(字下げの列には何も描かれない)
            rect = QRectF(opt.rect)
            rect.setLeft(0)
            path = QPainterPath()
            path.addRoundedRect(
                rect, theme.DATASET_LIST_ITEM_RADIUS, theme.DATASET_LIST_ITEM_RADIUS
            )
            painter.fillPath(path, theme.current_selection_highlight_qcolor())
            painter.restore()
            # 標準の選択の背景を重ねないよう落とす(文字とアイコンの色は選択で変わらない)
            opt.state &= ~QStyle.StateFlag.State_Selected

        super().paint(painter, opt, index)


class _ClickableMathPreviewLabel(FitWidthPixmapLabel):
    """タイトルと軸ラベルの欄。mathtext を描いたプレビューで、クリックで編集ダイアログを開く。

    値は隠した元の QLineEdit が持つ(textChanged もそちらから出る)。
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mathtext_preview_label")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setToolTip(tr("クリックして編集"))
        # QLabel は既定でホバーを追跡せず、QSS の :hover が効かない
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _insert_form_row_after(form, anchor, *row):
    """form の anchor(ラベルか欄)の行の次に入れる。行番号で入れると、ほかの挿入の順番が変わったときに黙って別の位置に入る。"""
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
    # 保存・読み込みのたびに出す。MainAppWindow がタブ名を更新する
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
        self.settings = app_settings.open_settings()
        self._update_autosave_path()
        load_recent_colors_into_picker(self.settings)

        # 以降に作るメニューやボタンの tr() に効くので、画面を組み立てる前に
        set_language(app_settings.LANGUAGE.read(self.settings))

        # 起動時に False にし、正常に閉じたときだけ closeEvent で True に戻す。次の起動で False なら異常終了とみなし、
        # オートセーブからの復元を勧める。アプリ全体で1つの値なので、2つ目以降のタブは触らない
        if self._run_startup_checks:
            self._had_clean_exit = app_settings.CLEAN_EXIT.read(self.settings)
            app_settings.CLEAN_EXIT.write(self.settings, False)
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
        self.dataset_order = DatasetOrder(
            self.project, lambda: self.ui.dataset_list_widget, self._add_dataset_list_item)
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
        saved_interval_min = app_settings.AUTOSAVE_INTERVAL_MIN.read(self.settings)
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
        self.snap_to_grid_enabled = app_settings.SNAP_TO_GRID_ENABLED.read(self.settings)
        self.snap_grid_interval_px = app_settings.SNAP_GRID_INTERVAL_PX.read(self.settings)

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
        self.canvas.dark_mode = app_settings.DARK_MODE.read(self.settings)
        # アイコンは作るときにテーマの色を焼き込むので、アイコンを作り始める前にテーマを当てる
        # (当てないと、ダークモードで起動したときツールバーのアイコンがライト用の色になって見えない)
        theme.apply_theme(QApplication.instance(), self.canvas.dark_mode)
        self.canvas.point_label_max_points = app_settings.POINT_LABEL_MAX_POINTS.read(self.settings)
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

        self.minimap_visible = app_settings.MINIMAP_VISIBLE.read(self.settings)
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
        if app_settings.CANVAS_WAS_DETACHED.read(self.settings):
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
        """前回のドック配置を戻す。タブが最終の大きさになってから呼ぶ(でないとスプリッターの位置がずれる)。"""
        saved_layout_version = (app_settings.DOCK_LAYOUT_VERSION.read(self.settings) if self._run_startup_checks
                                else DOCK_LAYOUT_VERSION)
        saved_state = app_settings.WINDOW_STATE.read(self.settings) if self._run_startup_checks else None
        state_restored = False
        if saved_state is not None and saved_layout_version == DOCK_LAYOUT_VERSION:
            state_restored = bool(self.restoreState(saved_state))

        if not state_restored:
            try:
                self.resizeDocks(
                    [self.export_preview_dock_widget],
                    [EXPORT_PREVIEW_DOCK_INITIAL_HEIGHT],
                    Qt.Orientation.Vertical
                )
            except Exception:
                logger.exception("resizeDocks に失敗しました")

    # 名前付きのドック配置。起動時の復元(最初のタブだけ)と違い、どのタブでもいつでも使える

    def _load_dock_layout_presets(self):
        """{名前: base64 の saveState}"""
        raw = app_settings.DOCK_LAYOUT_PRESETS.read(self.settings)
        if not isinstance(raw, str):
            raw = "{}"
        try:
            presets = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("ドックレイアウトプリセットの読み込みに失敗しました。空として扱います。")
            return {}
        return presets if isinstance(presets, dict) else {}

    def _save_dock_layout_presets(self, presets: dict):
        app_settings.DOCK_LAYOUT_PRESETS.write(self.settings, json.dumps(presets))

    def _on_save_dock_layout_preset(self):
        name, ok = notify.get_text(self, "レイアウトを保存", "プリセット名:")
        name = name.strip()
        if not ok or not name:
            return
        presets = self._load_dock_layout_presets()
        presets[name] = base64.b64encode(bytes(self.saveState())).decode('ascii')
        self._save_dock_layout_presets(presets)
        self.statusBar().showMessage(f"レイアウト「{name}」を保存しました", 3000)

    def _populate_load_layout_menu(self):
        """保存や削除のたびに更新しなくて済むよう、開く直前に作り直す。"""
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
            notify.warning(self, "レイアウトの復元", "保存されたレイアウトデータが壊れています。")
            return
        if not self.restoreState(QByteArray(state_bytes)):
            notify.warning(self, "レイアウトの復元", "レイアウトの復元に失敗しました。")

    def _on_reset_dock_layout(self):
        """組み立てた直後、配置を戻す前に控えた状態(_pristine_dock_state)に戻す。"""
        self.restoreState(self._pristine_dock_state)

    def closeEvent(self, event):
        # 読み込み中の QThread を破棄すると Qt がプロセスごと止め、ほかのタブの未保存データも失う。
        # 読み込みは中断できないので終わるまで待つ。待つ間に届く完了の通知が閉じかけの窓で動かないよう、先に切る
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

        # 同じ理由
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

        # 同じ理由
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
            app_settings.CLEAN_EXIT.write(self.settings, True)
            app_settings.WINDOW_STATE.write(self.settings, self.saveState())
            app_settings.DOCK_LAYOUT_VERSION.write(self.settings, DOCK_LAYOUT_VERSION)

        # 切り離したまま閉じたら次の起動で同じ状態に戻す。軽い設定なので最初のタブに限らない
        if self.canvas_detached and self._canvas_detach_window is not None:
            app_settings.CANVAS_DETACHED_GEOMETRY.write(self.settings, self._canvas_detach_window.saveGeometry())
        app_settings.CANVAS_WAS_DETACHED.write(self.settings, self.canvas_detached)

        # 切り離した窓が残らないよう片付ける。_reattach_canvas を通すと、上で保存した「切り離していた」を
        # 消してしまうので通さない。窓と一緒に破棄されないよう、先にキャンバスの親を外す
        if self._canvas_detach_window is not None:
            self._canvas_detach_window.closed.disconnect(self._on_detach_window_closed)
            self._canvas_detach_window.takeCentralWidget()
            self.canvas.setParent(None)
            self._canvas_detach_window.close()
            self._canvas_detach_window.deleteLater()
            self._canvas_detach_window = None

        super().closeEvent(event)

    def _check_autosave_recovery(self):
        """前回が正常に終わらず、オートセーブが残っていれば、復元するか尋ねる(起動時に1回)。

        新しい形式のファイルが無ければ、古い版が残した .pkl を探す。
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

        reply = notify.question(
            self, "オートセーブからの復元",
            "前回はプロジェクトが正常に終了しなかったようです。\n"
            "自動保存されていたデータを復元しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._load_project_from_path(autosave_path, add_to_recent=False)

    def _check_first_launch(self):
        if app_settings.HAS_SHOWN_WELCOME.read(self.settings):
            return
        app_settings.HAS_SHOWN_WELCOME.write(self.settings, True)
        self._show_welcome_dialog()

    def _on_show_startup_screen(self):
        self._show_welcome_dialog()

    def _show_welcome_dialog(self):
        dialog = WelcomeDialog(self, recent_files=self._get_recent_files())
        dialog.exec()
        if dialog.load_sample_requested:
            self._load_sample_data()
        elif dialog.selected_recent_file:
            self._on_open_recent_file(dialog.selected_recent_file)
        elif dialog.load_template_requested:
            self._on_load_plot_template()

    def _on_show_autosave_history(self):
        """オートセーブの世代を新しい順に見せ、選んだものを読み込む(復元確認と同じく、最近使ったファイルに載せず、上書き保存の対象にもしない)。"""
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
            notify.information(self, "自動バックアップ履歴", "自動バックアップファイルが見つかりませんでした。")
            return

        dialog = AutosaveHistoryDialog(generations, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_path = dialog.get_selected_path()
        if not selected_path:
            return

        reply = notify.question(
            self, "自動バックアップ履歴",
            "選択した世代の内容で復元します。現在の未保存の変更は失われます。よろしいですか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._load_project_from_path(selected_path, add_to_recent=False)

    def _load_sample_data(self):
        sample_path = resource_path(os.path.join("sample_data", "cooling_curve_sample.csv"))
        if not os.path.exists(sample_path):
            notify.warning(self, "サンプルデータ", "サンプルデータファイルが見つかりませんでした。")
            return
        self.load_data(sample_path)

    def _update_autosave_path(self):
        """autosave_dir(空なら get_app_data_dir())から保存先を決め、フォルダを作る。

        カレントディレクトリは使わない(macOS の .app では書き込めない場所になる)。
        """
        autosave_dir = app_settings.AUTOSAVE_DIR.read(self.settings)
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
        """autosave.graphica を autosave.1.graphica, autosave.2.graphica, ... へ押し出す。"""
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
        """UI にしか無い状態(フォルダ構造、サブプロットの行数と列数)を、保存や比較の前に ProjectModel へ移す。"""
        self.project.dataset_group_tree = self._capture_dataset_group_tree()
        self.project.layout_rows = self.subplot_rows_spinbox.value()
        self.project.layout_cols = self.subplot_cols_spinbox.value()

    def _remember_saved_content(self):
        """いまの内容を保存済みとみなす(保存・読み込みの成功直後に呼ぶ)。"""
        self._sync_project_from_ui()
        self._saved_content_fingerprint = self.project.content_fingerprint()

    def plugin_context(self, plugin_name):
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
            notify.critical(self, "プラグインのエラー", str(PluginExecutionError(
                menu_action.plugin_name, f"「{menu_action.text}」の実行に失敗しました: {e}"
            )))

    def document_title(self):
        if self._current_project_path:
            return os.path.basename(self._current_project_path)
        if self._restored_unsaved:
            return "無題のプロジェクト(復元)"
        return "無題のプロジェクト"

    def has_unsaved_changes(self):
        """データセットが無く、ファイルとも対応していない新しいタブは False。"""
        if not self.project.datasets and not self._current_project_path:
            return False
        if self._saved_content_fingerprint is None:
            return True
        self._sync_project_from_ui()
        return self.project.content_fingerprint() != self._saved_content_fingerprint

    def confirm_unsaved_changes(self, action_text):
        """未保存の変更があれば「保存 / 保存しない / キャンセル」を尋ねる。続けてよければ True。"""
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
            return not self.has_unsaved_changes()
        return False

    def auto_save(self):
        try:
            self._sync_project_from_ui()
            self._rotate_autosave_generations()
            self.project.save_project(self._autosave_filename)
            self.statusBar().showMessage("オートセーブ完了", 3000)
        except Exception as e:
            logger.exception("オートセーブに失敗しました")
            self.statusBar().showMessage(f"オートセーブ失敗: {e}", 3000)

    def manual_save(self):
        """保存先が分かっていればそこへ上書きし、無ければ「名前を付けて保存」にする。"""
        if not self._current_project_path:
            self.manual_save_as()
            return
        self._save_project_to_path(self._current_project_path)

    def manual_save_as(self):
        # 任意のコードを実行されない .graphica を既定にする。.pkl も選べる
        filepath, selected_filter = notify.get_save_file_name(
            self, "名前を付けて保存", "",
            "Graphica Project (*.graphica);;Project Files (*.pkl)"
        )
        if filepath:
            # 選んだ形式の拡張子を付けないファイルダイアログがある
            if not os.path.splitext(filepath)[1]:
                filepath += '.graphica' if 'graphica' in selected_filter else '.pkl'
            self._save_project_to_path(filepath)

    def _save_project_to_path(self, filepath):
        try:
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
            notify.critical(self, "エラー", f"保存に失敗しました:\n{e}")

    def manual_load(self):
        if not self.confirm_unsaved_changes("別のプロジェクトを開く"):
            return
        filepath, _ = notify.get_open_file_name(
            self, "プロジェクトを開く", "", "Project Files (*.graphica *.pkl)"
        )
        if filepath:
            self._load_project_from_path(filepath)

    def _load_project_from_path(self, filepath, add_to_recent=True):
        """add_to_recent=False はオートセーブからの復元。最近使ったファイルに載せず、上書き保存の対象にもしない。"""
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

            if self.project.all_plot_settings:
                self._apply_settings_to_ui_controls(
                    self.project.all_plot_settings[self.project.active_axis_index]
                )

            # 前の文書へのコマンドは datasets をリストごと差し戻すので、残すと
            # Undo 1回で読み込んだ内容が前の文書に置き換わる。
            self.undo_stack.clear()

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
            notify.critical(self, "エラー", f"読み込みに失敗しました:\n{e}")

    def _reset_zoom(self):
        """設定どおりの表示範囲に戻す。

        matplotlib の Home ボタンは作り直す前の Axes を覚えているので、描き直しを挟むと効かない。
        """
        self._update_plot()

    def _update_plot(self, light=False, full_resolution=False):
        """グラフ全体を描き直す。

        light=True は Axes の数・配置・所属が変わらないときだけ(既存の Axes の上で描き直す)。
        full_resolution=True は表示用の間引きをしない(フル解像度でのエクスポート用)。
        """
        layout_mode = getattr(self.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            # 自由配置では行数×列数ではなく、軸の設定の数がサブプロットの数になる
            rows, cols = 0, 0
            if len(self.project.all_plot_settings) == 0:
                return
        else:
            rows = self.subplot_rows_spinbox.value()
            cols = self.subplot_cols_spinbox.value()
            if rows * cols == 0:
                return

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

        self.tick_direction_y2_label.setVisible(is_secondary_visible_global)
        self.major_tick_direction_y2_combo.setVisible(is_secondary_visible_global)
        self.minor_tick_direction_y2_combo.setVisible(is_secondary_visible_global)
        self.y2_label_text_label.setVisible(is_secondary_visible_global)
        self.y2_label_text_edit.setVisible(is_secondary_visible_global)

        self.all_axes = self.canvas.all_axes
        self.all_secondary_axes = self.canvas.all_secondary_axes

        if hasattr(self, 'export_preview_panel'):
            self.export_preview_panel.refresh_preview()

        # 全体の描き直しでハイライトも消えるので、データエディタの選択を戻す
        self._reapply_editor_row_highlight()

        # ミニマップは別の Figure なので、redraw_all() では描き直されない。
        self._refresh_minimap()
        self._notify_plugins_datasets_changed()

    def _refresh_minimap(self):
        """隠れていても描く(次に出したときに最新になっているように)。"""
        if not hasattr(self, 'minimap'):
            return
        self.minimap.refresh(self.project.datasets, self.canvas.dark_mode)

    def _on_minimap_range_selected(self, xmin, xmax):
        """ミニマップで選んだ範囲を全部の軸の X の範囲にする。Axes は作り直さない(set_xlim と draw_idle で足りる)。"""
        for ax in self.canvas.all_axes:
            ax.set_xlim(xmin, xmax)
        self.canvas.draw_idle()

    def _on_toggle_minimap(self, checked):
        self.minimap_visible = checked
        self.minimap.setVisible(checked)
        self.minimap_separator.setVisible(checked)
        app_settings.MINIMAP_VISIBLE.write(self.settings, checked)

    def _on_toggle_panel_labels(self, checked):
        """QSettings ではなくプロジェクトに保存する。"""
        self.project.panel_labels_enabled = checked
        self._update_plot(light=True)

    # キャンバスの切り離し。self.canvas はあちこちから直接参照されているので、破棄も作り直しもせず親を替えるだけ。

    def _on_toggle_canvas_detached(self, checked):
        if checked:
            self._detach_canvas()
        else:
            self._reattach_canvas()

    def _sync_canvas_detach_action(self):
        """メニューのチェックと文言(「切り離す」/「元に戻す」)を状態に合わせる。"""
        if not hasattr(self, 'canvas_detach_action'):
            return
        self.canvas_detach_action.blockSignals(True)
        self.canvas_detach_action.setChecked(self.canvas_detached)
        self.canvas_detach_action.setText(
            tr("キャンバスを元に戻す") if self.canvas_detached else tr("キャンバスを別ウィンドウに切り離す")
        )
        self.canvas_detach_action.blockSignals(False)

    def _detach_canvas(self, restore_geometry=False):
        if self.canvas_detached:
            return

        self._plot_layout.removeWidget(self.canvas)

        title = f"{APP_NAME} - {tr('グラフキャンバス')}"
        self._canvas_detach_window = DetachedCanvasWindow(title)
        self._canvas_detach_window.setCentralWidget(self.canvas)
        self._canvas_detach_window.closed.connect(self._on_detach_window_closed)

        saved_geometry = app_settings.CANVAS_DETACHED_GEOMETRY.read(self.settings) if restore_geometry else None
        if saved_geometry is not None:
            # 先にネイティブのハンドルを作る。窓が実体化する前に restoreGeometry() すると位置がずれる
            self._canvas_detach_window.winId()
            self._canvas_detach_window.restoreGeometry(saved_geometry)
        else:
            self._canvas_detach_window.resize(DEFAULT_DETACHED_CANVAS_WIDTH, DEFAULT_DETACHED_CANVAS_HEIGHT)

        self._canvas_detach_window.show()
        self.canvas.show()

        self.canvas_detached = True
        self._sync_canvas_detach_action()
        app_settings.CANVAS_WAS_DETACHED.write(self.settings, True)

    def _reattach_canvas(self):
        """「元に戻す」と、切り離した窓を閉じたときの両方から呼ばれる。"""
        if not self.canvas_detached:
            return

        if self._canvas_detach_window is not None:
            app_settings.CANVAS_DETACHED_GEOMETRY.write(self.settings, self._canvas_detach_window.saveGeometry())
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
        app_settings.CANVAS_WAS_DETACHED.write(self.settings, False)

    def _on_detach_window_closed(self):
        self._reattach_canvas()

    def _update_plot_appearance(self):
        layout_mode = getattr(self.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            rows, cols = 0, 0
        else:
            rows = self.subplot_rows_spinbox.value()
            cols = self.subplot_cols_spinbox.value()
        self.canvas.update_appearance_only(
            self.project.all_plot_settings, datasets=self.project.datasets, rows=rows, cols=cols,
            layout_mode=layout_mode,
            share_x_axis=getattr(self.project, 'share_x_axis', False),
            share_y_axis=getattr(self.project, 'share_y_axis', False),
        )

        if hasattr(self, 'export_preview_panel'):
            self.export_preview_panel.refresh_preview()

    def _on_editor_rows_highlighted(self, master_indices):
        """データエディタで選んだ行の点をグラフ上で強調する(逆向きは cursor_mixin の _on_pick)。"""
        if self.data_editor_dialog is None:
            return
        self.canvas.set_highlighted_points(self.data_editor_dialog.dataset, master_indices)

    def _reapply_editor_row_highlight(self):
        if self.data_editor_dialog is None:
            return
        self.canvas.set_highlighted_points(
            self.data_editor_dialog.dataset, self.data_editor_dialog.get_selected_master_indices()
        )

    def _wrap_in_collapsible_section(self, group_box, title):
        """group_box の外に開閉ボタンを付け、グループボックスごと出し入れする。見出しはボタンにだけ出す。"""
        group_box.setTitle("")
        # theme.py はグループボックスのタイトル用に上の余白を取る。タイトルを空にしたので、それを 0 にする目印
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
        # ダークモードの切り替えでアイコンを作り直すので、ボタンを集めておく
        if not hasattr(self, '_collapsible_toggle_buttons'):
            self._collapsible_toggle_buttons = []
        self._collapsible_toggle_buttons.append(toggle_button)

        wrapper_layout.addWidget(toggle_button)
        wrapper_layout.addWidget(group_box)
        return wrapper


    def _build_dataset_property_sections(self):
        """データセットのプロパティ欄を DATASET_PROPERTY_SECTIONS の節に分け、節ごとに QFormLayout を持たせる。

        列幅の広がりが節の中に閉じる。Designer の行は takeRow() で移す(removeRow() はウィジェットごと破棄する)。
        平滑化のチェックだけは「平滑化の手法」の直前に置くので、ここでは移さない。
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
            # 親の見出し(4px)→ 子の見出し(12px)→ 中身、の階段になるよう字下げする
            form.setContentsMargins(24, 2, 0, 6)
            form.setSpacing(6)

            toggle_button = QToolButton()
            toggle_button.setText(tr(title))
            toggle_button.setCheckable(True)
            toggle_button.setIcon(_svg_icon("chevron-down", size=13))
            toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            # 上の2つの開閉ボタンとは別の名前(theme.py で控えめに描き、2つだけであることをテストが確かめる)
            toggle_button.setObjectName("property_subsection_toggle")
            toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # QToolButton は文字幅なので、区切りの罫線が見出しの下にしか引かれない
            toggle_button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            toggle_button.setChecked(key not in collapsed)
            # 1本目は親の見出しのすぐ下なので、罫線が二重に見える
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

        # 空の formLayout_4 は生成物の構造なので残し、余白だけ潰す
        for row in range(self.ui.formLayout_4.rowCount() - 1, -1, -1):
            self.ui.formLayout_4.takeRow(row)
        self.ui.formLayout_4.setContentsMargins(0, 0, 0, 0)
        self.ui.formLayout_4.setSpacing(0)
        self.ui.gridLayout_4.setContentsMargins(0, 0, 0, 0)
        self.ui.gridLayout_4.addWidget(container, 1, 0, 1, 1)
        self._dataset_property_sections_container = container

        # 無効な親の下の子は有効にできないので、グループボックスは常に有効にして中身だけ無効にする
        # (でないと、データセットが無い間は節を開閉できない)
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

        self.ui.plot_type_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.ui.plot_type_combo.setMinimumContentsLength(PLOT_TYPE_COMBO_MIN_CHARS)

    def _prop_form(self, section_key):
        return self._prop_sections[section_key]['form']

    def _align_form_label_columns(self, forms):
        """ラベルの列幅を複数の QFormLayout で揃え、入力欄の左端を合わせる。決めた幅(px)を返す。

        隠れているラベルも数える(QFormLayout は隠れたものを外すので、出た瞬間に列幅が変わって欄がずれる)。
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
        """選択が無いときは無効にする。無効にするのは節の中身だけ(見出しまで無効にすると開閉できない)。"""
        for entry in getattr(self, '_prop_sections', {}).values():
            entry['body'].setEnabled(enabled)

    def _load_collapsed_property_sections(self):
        raw = app_settings.DATASET_PROPERTY_COLLAPSED_SECTIONS.read(self.settings)
        try:
            keys = json.loads(raw) if isinstance(raw, str) else list(raw)
        except (ValueError, TypeError):
            return set()
        valid = {key for key, _ in DATASET_PROPERTY_SECTIONS}
        return {k for k in keys if k in valid}

    def _on_property_section_toggled(self, section_key, checked):
        """開閉し、閉じている節を QSettings に書き戻す(一度閉じたものは次の起動でも閉じたまま)。"""
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
        app_settings.DATASET_PROPERTY_COLLAPSED_SECTIONS.write(self.settings, json.dumps(collapsed))

    def _update_property_section_visibility(self):
        """中の行が全部隠れた節は見出しごと隠す。"""
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

    # データセット一覧(QTreeWidget)。データセットの葉は UserRole に Dataset を、フォルダは None を持つ。

    def _replace_dataset_list_with_tree(self):
        """Designer の QListWidget を、同じセルに「検索欄 + QTreeWidget」を縦に並べたものへ差し替える。"""
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
        container_layout.setSpacing(6)

        search_edit = QLineEdit(container)
        search_edit.setObjectName("dataset_search_edit")
        search_edit.setPlaceholderText("データセットを検索...")
        search_edit.setClearButtonEnabled(True)
        container_layout.addWidget(search_edit)

        tree = QTreeWidget(container)
        tree.setObjectName("dataset_list_widget")
        tree.setHeaderHidden(True)
        # 列1は表示/非表示の目のアイコン。stretchLastSection のままだと目の列が余白を吸って広がる
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
        # 行の伸びをキャンバスに譲ったので、放っておくと数件でも窮屈な高さまで縮む
        tree.setMinimumHeight(90)
        tree.setItemDelegate(_DatasetTreeSelectionDelegate(tree))
        container_layout.addWidget(tree)

        # 一覧のすぐ下に、選んでいるデータセットの短い統計値
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
        """UserRole に Dataset そのものを持たせる(並べ替えても、同名があっても対応が崩れない)。"""
        item = QTreeWidgetItem([dataset.name])
        item.setData(0, Qt.ItemDataRole.UserRole, dataset)
        item.setIcon(0, make_dataset_style_icon(dataset))
        # 目のアイコンのクリックは dataset_mixin の _on_dataset_tree_item_clicked が列で見分ける
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
        """選択中の項目がフォルダならそれを返す(新しいデータセットをその中に入れる)。"""
        return self.dataset_order.target_folder()

    def _add_dataset(self, dataset, parent_folder=None, select=True):
        new_item = self.dataset_order.append(dataset, parent_folder)
        if select:
            self.ui.dataset_list_widget.setCurrentItem(new_item)
        self._update_plot()
        return new_item

    def _add_dataset_with_undo(self, dataset, parent_folder=None, description="データセットの追加"):
        """_add_dataset() の Undo できる版(プラグインの処理と解析の結果用)。"""
        def do_add():
            self._add_dataset(dataset, parent_folder, select=True)

        def do_remove():
            self.dataset_order.remove_added(dataset)
            self.property_panel.update_ui_state()
            self._update_plot()

        command = AddDatasetCommand(do_add, do_remove, description=description)
        self.undo_stack.push(command)

    def _remove_dataset_items_with_undo(self, top_level_items, description=None):
        """ツリーの項目(データセットかフォルダ)を Undo できるように削除する。

        top_level_items には最上位の対象だけを渡す(フォルダを渡すと中身も一緒に消える)。
        """
        steps = self.dataset_order.removal(top_level_items)
        if steps is None:
            return
        remove, restore, removed_datasets = steps

        if description is None:
            if len(removed_datasets) == 1:
                description = f"「{removed_datasets[0].name}」の削除"
            else:
                description = f"{len(removed_datasets)}件のデータセットの削除"

        def do_remove():
            remove()
            self.property_panel.update_ui_state()
            self._update_plot()

        def do_restore():
            restore()
            self.property_panel.update_ui_state()
            self._update_plot()

        self.undo_stack.push(
            RemoveDatasetCommand(do_remove, do_restore, description=description)
        )

    def _add_dataset_folder_item(self, name, parent_item=None):
        return self.dataset_order.add_folder(name, parent_item)

    def _flatten_dataset_tree(self, parent_item=None):
        """データセットの葉を表示順(深さ優先)に返す。"""
        return self.dataset_order.dataset_items(parent_item)

    def _get_current_dataset(self):
        return self.dataset_order.current_dataset()

    def _get_selected_datasets(self):
        return self.dataset_order.selected_datasets()

    def _get_dataset_tree_item(self, dataset):
        return self.dataset_order.item_for(dataset)

    def _capture_dataset_group_tree(self):
        return self.dataset_order.group_tree()

    def _rebuild_dataset_tree_widget(self):
        self.dataset_order.rebuild_tree()

    def _sync_dataset_list_widget_order(self):
        """フォルダの中の並びを project.datasets の順に合わせる(並べ替えの Undo/Redo 用)。"""
        self.dataset_order.sort_tree_to_draw_order()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        file_paths = [url.toLocalFile() for url in urls if url.toLocalFile()]
        if file_paths:
            self._queue_data_files(file_paths)

    def _all_supported_data_file_extensions(self):
        """組み込みの拡張子に、プラグインの読み込み機能の拡張子を足したもの。"""
        extensions = list(SUPPORTED_DATA_FILE_EXTENSIONS)
        for ext in get_registered_importer_extensions():
            if ext not in extensions:
                extensions.append(ext)
        return tuple(extensions)

    def _queue_data_files(self, file_paths):
        """対応していない拡張子はまとめて1回だけ知らせ、残りを待ち行列に積む。"""
        valid_paths = []
        skipped_names = []
        allowed_extensions = self._all_supported_data_file_extensions()
        for file_path in file_paths:
            if file_path.lower().endswith(allowed_extensions):
                valid_paths.append(file_path)
            else:
                skipped_names.append(os.path.basename(file_path))

        if skipped_names:
            notify.warning(
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

    def _process_next_queued_file(self):
        """読み込みの成否によらず、1件終わるたびに呼ばれる。"""
        if not self._data_load_queue:
            self._data_load_queue_total = 0
            self._data_load_queue_done = 0
            # 待ち行列を使い切ったら戻す(この後の普通の取り込みに引き継がない)
            self._batch_import_filename_regex = None
            return

        next_path = self._data_load_queue.pop(0)
        self._data_load_queue_done += 1
        self.load_data(next_path, queue_progress=(self._data_load_queue_done, self._data_load_queue_total))

    def load_data(self, file_path, queue_progress=None):
        """別スレッドで読み込み、終わったらデータセットとして加える(大きいファイルで画面を止めない)。

        queue_progress=(何件目, 総数) はステータスバーの表示に使う。
        """
        if self._data_load_task_runner is not None:
            notify.information(self, "読み込み中", "他のファイルを読み込み中です。完了までお待ちください。")
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
        """途中でキャンセルされても、必ず待ち行列の次へ進む。"""
        self._cleanup_data_load_task_runner()
        try:
            self._import_loaded_dataframe(df, file_path)
        finally:
            self._process_next_queued_file()

    def _import_loaded_dataframe(self, df, file_path):
        """Excel でシートを複数選ぶと、シートごとに別のデータセットにする。"""
        dataset_name = os.path.basename(file_path)
        is_excel = is_excel_file(file_path)

        sheet_names = []
        if is_excel:
            try:
                sheet_names = pd.ExcelFile(file_path, engine=excel_engine_for(file_path)).sheet_names
            except Exception as e:
                logger.warning("Excelのシート一覧取得に失敗しました: %s", e)

        # None は「読み込み済みの df をそのまま使う」
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
                sheet_df = df
                preview_name = dataset_name
            else:
                try:
                    sheet_df = pd.read_excel(file_path, sheet_name=sheet_name, engine=excel_engine_for(file_path))
                except Exception as e:
                    logger.exception("シート「%s」の読み込みに失敗しました", sheet_name)
                    notify.warning(self, "読み込みエラー", f"シート「{sheet_name}」の読み込みに失敗しました:\n{e}")
                    continue
                if sheet_df.shape[1] < 2:
                    notify.warning(
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
                    reply = notify.warning(
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

            # 列の多いファイルで意図しない列が選ばれないよう、プレビューを見せて X/Y の列を選ばせる
            preview_dialog = ColumnPreviewDialog(sheet_df, preview_name, self, file_path=file_path)
            if sheet_name is not None and preview_dialog.sheet_combo is not None:
                preview_dialog.sheet_combo.blockSignals(True)
                preview_dialog.sheet_combo.setCurrentText(sheet_name)
                preview_dialog.sheet_combo.blockSignals(False)

            if preview_dialog.exec() != QDialog.DialogCode.Accepted:
                continue

            x_col, y_col = preview_dialog.get_selected_columns()
            final_df = preview_dialog.get_dataframe()

            # 再読み込みのために元ファイルとシートを持つ。シートはダイアログで最後に選ばれたもの
            source_sheet = (
                preview_dialog.sheet_combo.currentText()
                if (is_excel and preview_dialog.sheet_combo is not None) else None
            )
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
        """フォルダ一括取り込みの正規表現の名前付きグループを、ファイル名から取り出して列にする。

        数値にできれば float の列。パターンが合わなくても取り込みは続けたいので、そのときは df をそのまま返す。
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
        """フォルダ内(サブフォルダは除く)の対応ファイルを、確認させてからドラッグ&ドロップと同じ待ち行列に積む。"""
        dir_path = notify.get_existing_directory(self, "フォルダから一括インポート", "")
        if not dir_path:
            return

        allowed_extensions = self._all_supported_data_file_extensions()
        try:
            file_paths = sorted(
                str(p) for p in Path(dir_path).iterdir()
                if p.is_file() and p.suffix.lower() in allowed_extensions
            )
        except OSError as e:
            notify.warning(self, "フォルダから一括インポート", f"フォルダの読み取りに失敗しました:\n{e}")
            return

        if not file_paths:
            notify.information(
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
        """区切り文字はファイル読み込みと同じ判定で決める(Excel からのコピーはタブ区切り)。"""
        text = QApplication.clipboard().text()
        if not text.strip():
            notify.information(self, "クリップボードから貼り付け", "クリップボードにテキストデータがありません。")
            return

        from graphica.gui.workers import detect_clipboard_delimiter
        delimiter = detect_clipboard_delimiter(text)
        try:
            df = pd.read_csv(io.StringIO(text), sep=delimiter, engine='python')
        except Exception as e:
            logger.exception("クリップボードの内容を表として読めませんでした")
            notify.warning(
                self, "貼り付けエラー",
                f"クリップボードの内容を表として解釈できませんでした:\n{e}"
            )
            return

        if df.shape[1] < 2:
            notify.warning(self, "貼り付けエラー", "クリップボードのデータには少なくとも2列必要です。")
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
        self._cleanup_data_load_task_runner()
        self.statusBar().clearMessage()
        notify.critical(self, "エラー", f"読み込みエラー: {error_message}")
        self._process_next_queued_file()

    def _localize_navigation_toolbar(self, toolbar):
        """matplotlib のツールバーの英語のツールチップを差し替える。

        _actions は matplotlib の内部なので、構造が変わっていたら何もしない(英語のまま)。
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
        self.ui.add_dataset_button.setEnabled(True)
        if self._data_load_task_runner is not None:
            self._data_load_task_runner.wait()
            self._data_load_task_runner.deleteLater()
            self._data_load_task_runner = None


    def _get_recent_files(self):
        return app_settings.as_list_keeping_empty_string(app_settings.RECENT_FILES.read(self.settings))

    def _add_recent_file(self, file_path):
        file_path = os.path.abspath(file_path)
        files = self._get_recent_files()
        if file_path in files:
            files.remove(file_path)
        files.insert(0, file_path)
        files = files[:MAX_RECENT_FILES]
        app_settings.RECENT_FILES.write(self.settings, files)
        self._update_recent_files_menu()

    def _update_recent_files_menu(self):
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
            # まれにメニューの C++ 側が破棄済みのことがある(PySide6 の回収、原因は未特定)。表示が古いだけなので落とさない
            logger.warning("recent_files_menuの更新に失敗しました(既に破棄されている可能性があります)。", exc_info=True)

    def _on_open_recent_file(self, file_path):
        if not os.path.exists(file_path):
            notify.warning(self, "エラー", f"ファイルが見つかりません:\n{file_path}")
            files = self._get_recent_files()
            if file_path in files:
                files.remove(file_path)
                app_settings.RECENT_FILES.write(self.settings, files)
                self._update_recent_files_menu()
            return

        if file_path.lower().endswith(('.graphica', '.pkl')):
            if not self.confirm_unsaved_changes("別のプロジェクトを開く"):
                return
            self._load_project_from_path(file_path)
        else:
            self.load_data(file_path)

    def _on_clear_recent_files(self):
        app_settings.RECENT_FILES.write(self.settings, [])
        self._update_recent_files_menu()
