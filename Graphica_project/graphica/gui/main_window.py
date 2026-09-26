import os
import re
import types
import sys
import logging
import numpy as np

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
    for label in widget.findChildren(QLabel):
        text = label.text()
        if text.endswith('：'):
            label.setText(text[:-1])

DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 800
CONTROL_DOCK_WIDTH = 472  # 縦スクロールバーの分まで含めた幅。狭めると横スクロールバーが出る
SPIN_BOX_MAX_DECIMALS = 16


DEFAULT_DETACHED_CANVAS_WIDTH = 900
DEFAULT_DETACHED_CANVAS_HEIGHT = 700





AUTOSAVE_FILENAME = "autosave.graphica"


from graphica.gui import notify




from PySide6.QtWidgets import (QMainWindow, QWidget,
                               QDockWidget, QLabel, QTreeWidgetItem)
from PySide6.QtGui import QFont, QIcon, QValidator, QUndoStack
from PySide6.QtCore import Qt, QTimer, Signal
from graphica.models.project import ProjectModel
from graphica.core.version import APP_NAME, __version__
from graphica.core.i18n import tr, set_language
from graphica.core.plugin_api import load_plugins_once
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
from graphica.gui import data_import_flow
# テストがこのモジュールの属性として引くので残す(使うコードは data_import_flow と project_files に移した)
import pandas as pd  # noqa: F401
from PySide6.QtWidgets import QMessageBox  # noqa: F401
from graphica.core.app_paths import get_app_data_dir  # noqa: F401
from graphica.gui import project_files
from graphica.gui.data_import_flow import (  # noqa: F401
    SUPPORTED_DATA_FILE_EXTENSIONS, find_unevaluated_formula_cells)
from graphica.gui.project_files import (  # noqa: F401
    AUTOSAVE_GENERATIONS, MAX_RECENT_FILES, UNSAVED_CHANGES_PROMPT_ENV, _unsaved_changes_prompt_enabled)
from graphica.gui.builders import axis_panel
from graphica.gui.builders import canvas_area
from graphica.gui.builders import dataset_panel
from graphica.gui.builders import property_sections
from graphica.gui import dock_layout
from graphica.gui.builders.common import (  # noqa: F401
    EXPORT_PREVIEW_DOCK_INITIAL_HEIGHT, DATASET_TREE_VISIBILITY_COLUMN_WIDTH, DOCK_LAYOUT_VERSION, DATASET_PROPERTY_SECTIONS, PLOT_TYPE_COMBO_MIN_CHARS, COLORMAP_CHOICES, TOOLBAR_ICON_SIZE, _svg_icon, _DatasetTreeSelectionDelegate, _ClickableMathPreviewLabel, _insert_form_row_after)
from graphica.gui.resources import resource_path
from graphica.gui.axis_bindings import AXIS_BINDINGS, AXIS_BUTTONS
from graphica.gui.binding import Binder
from graphica.gui.datasets.peaks import PeakController
from graphica.gui.datasets.processing import ProcessingController
from graphica.gui.plugin_context import TabPluginContext
from graphica.core.app_paths import get_user_plugins_dir


from graphica.ui_main_window import Ui_MainWindow

from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE
from graphica.core.commands import AddDatasetCommand, RemoveDatasetCommand
from graphica.gui.detached_canvas_window import DetachedCanvasWindow
from graphica.gui import theme
from graphica.gui.theme import apply_form_spacing
from graphica.gui.dialogs import (WelcomeDialog)


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






from graphica.gui.dataset_style_icon import (
    make_dataset_style_icon, make_dataset_visibility_icon, apply_dataset_visibility_text_style,
    DATASET_TREE_VISIBILITY_COLUMN,
)
from graphica.gui.mathtext_preview import JP_CAPABLE_FONT_FAMILIES
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
from graphica.gui.mixins.layout_edit_mixin import LayoutEditMixin
from graphica.gui.mixins.range_select_mixin import RangeSelectMixin
from graphica.gui.mixins.peak_placement_mixin import PeakPlacementMixin
from graphica.gui.mixins.slice_extraction_mixin import SliceExtractionMixin
from graphica.gui.mixins.region_highlight_mixin import RegionHighlightMixin
from graphica.gui.mixins.export_mixin import ExportMixin
from graphica.gui.mixins.project_io_mixin import ProjectIOMixin
from graphica.gui.mixins.help_mixin import HelpMixin
from graphica.gui.mixins.quick_access_mixin import QuickAccessMixin


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
        # 軸の設定の欄と値の対応(集める・戻す・止める・つなぐ)
        self._axis_binder = Binder(self, AXIS_BINDINGS, also_blocked=AXIS_BUTTONS)

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
        return canvas_area.build_canvas_and_toolbar(self)

    def _setup_status_bar(self):
        return canvas_area.setup_status_bar(self)

    def _build_dataset_color_picker(self):
        return dataset_panel.build_dataset_color_picker(self)

    def _build_dataset_list_buttons(self):
        return dataset_panel.build_dataset_list_buttons(self)

    def _build_dataset_style_controls(self):
        return dataset_panel.build_dataset_style_controls(self)

    def _build_legend_location_control(self):
        return axis_panel.build_legend_location_control(self)

    def _build_fit_info_and_stats(self):
        return dataset_panel.build_fit_info_and_stats(self)

    def _build_secondary_y_controls(self):
        return dataset_panel.build_secondary_y_controls(self)

    def _build_tick_grid_and_colorbar_controls(self):
        return axis_panel.build_tick_grid_and_colorbar_controls(self)

    def _build_tick_format_controls(self):
        return axis_panel.build_tick_format_controls(self)

    def _build_label_editors(self):
        return axis_panel.build_label_editors(self)

    def _add_subplot_target_row(self):
        return dataset_panel.add_subplot_target_row(self)

    def _arrange_property_docks(self):
        return dock_layout.arrange_property_docks(self)

    def _rebuild_label_tab(self):
        return axis_panel.rebuild_label_tab(self)

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
        return dock_layout.restore_dock_layout(self)

    # 名前付きのドック配置。起動時の復元(最初のタブだけ)と違い、どのタブでもいつでも使える

    def _load_dock_layout_presets(self):
        return dock_layout.load_dock_layout_presets(self)

    def _save_dock_layout_presets(self, presets: dict):
        return dock_layout.save_dock_layout_presets(self, presets)

    def _on_save_dock_layout_preset(self):
        return dock_layout.on_save_dock_layout_preset(self)

    def _populate_load_layout_menu(self):
        return dock_layout.populate_load_layout_menu(self)

    def _on_load_dock_layout_preset(self, name):
        return dock_layout.on_load_dock_layout_preset(self, name)

    def _on_reset_dock_layout(self):
        return dock_layout.on_reset_dock_layout(self)

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
        return project_files.check_autosave_recovery(self)

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
        return project_files.on_show_autosave_history(self)

    def _load_sample_data(self):
        sample_path = resource_path(os.path.join("sample_data", "cooling_curve_sample.csv"))
        if not os.path.exists(sample_path):
            notify.warning(self, "サンプルデータ", "サンプルデータファイルが見つかりませんでした。")
            return
        self.load_data(sample_path)

    def _update_autosave_path(self):
        return project_files.update_autosave_path(self)

    def _rotate_autosave_generations(self):
        return project_files.rotate_autosave_generations(self)

    def _sync_project_from_ui(self):
        return project_files.sync_project_from_ui(self)

    def _remember_saved_content(self):
        return project_files.remember_saved_content(self)

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
        return project_files.document_title(self)

    def has_unsaved_changes(self):
        return project_files.has_unsaved_changes(self)

    def confirm_unsaved_changes(self, action_text):
        return project_files.confirm_unsaved_changes(self, action_text)

    def auto_save(self):
        return project_files.auto_save(self)

    def manual_save(self):
        return project_files.manual_save(self)

    def manual_save_as(self):
        return project_files.manual_save_as(self)

    def _save_project_to_path(self, filepath):
        return project_files.save_project_to_path(self, filepath)

    def manual_load(self):
        return project_files.manual_load(self)

    def _load_project_from_path(self, filepath, add_to_recent=True):
        return project_files.load_project_from_path(self, filepath, add_to_recent)

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
        return property_sections.wrap_in_collapsible_section(self, group_box, title)


    def _build_dataset_property_sections(self):
        return property_sections.build_dataset_property_sections(self)

    def _prop_form(self, section_key):
        return property_sections.prop_form(self, section_key)

    def _align_form_label_columns(self, forms):
        return property_sections.align_form_label_columns(self, forms)

    def _set_dataset_property_fields_enabled(self, enabled):
        return property_sections.set_dataset_property_fields_enabled(self, enabled)

    def _load_collapsed_property_sections(self):
        return property_sections.load_collapsed_property_sections(self)

    def _on_property_section_toggled(self, section_key, checked):
        return property_sections.on_property_section_toggled(self, section_key, checked)

    def _update_property_section_visibility(self):
        return property_sections.update_property_section_visibility(self)

    # データセット一覧(QTreeWidget)。データセットの葉は UserRole に Dataset を、フォルダは None を持つ。

    def _replace_dataset_list_with_tree(self):
        return dataset_panel.replace_dataset_list_with_tree(self)

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

    def _push_dataset_additions(self, add, datasets, description):
        """add() で足す datasets を、Undo 1回で取り除けるように積む(積むとすぐ add() が走る)。"""
        def remove():
            for dataset in reversed(datasets):
                self.dataset_order.remove_added(dataset)
            self.property_panel.update_ui_state()
            self._update_plot()

        self.undo_stack.push(AddDatasetCommand(add, remove, description=description))

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
        return data_import_flow.dragEnterEvent(self, event)

    def dropEvent(self, event):
        return data_import_flow.dropEvent(self, event)

    def _all_supported_data_file_extensions(self):
        return data_import_flow.all_supported_data_file_extensions(self)

    def _queue_data_files(self, file_paths):
        return data_import_flow.queue_data_files(self, file_paths)

    def _process_next_queued_file(self):
        return data_import_flow.process_next_queued_file(self)

    def load_data(self, file_path, queue_progress=None):
        return data_import_flow.load_data(self, file_path, queue_progress)

    def _on_data_load_succeeded(self, df, file_path):
        return data_import_flow.on_data_load_succeeded(self, df, file_path)

    def _import_loaded_dataframe(self, df, file_path):
        return data_import_flow.import_loaded_dataframe(self, df, file_path)

    @staticmethod
    def _apply_filename_regex_columns(df, file_path, pattern):
        return data_import_flow.apply_filename_regex_columns(df, file_path, pattern)

    def _on_import_folder(self):
        return data_import_flow.on_import_folder(self)

    def _on_paste_data_from_clipboard(self):
        return data_import_flow.on_paste_data_from_clipboard(self)

    def _on_data_load_failed(self, error_message, file_path):
        return data_import_flow.on_data_load_failed(self, error_message, file_path)

    def _localize_navigation_toolbar(self, toolbar):
        return canvas_area.localize_navigation_toolbar(self, toolbar)

    def _cleanup_data_load_task_runner(self):
        return data_import_flow.cleanup_data_load_task_runner(self)


    def _get_recent_files(self):
        return project_files.get_recent_files(self)

    def _add_recent_file(self, file_path):
        return project_files.add_recent_file(self, file_path)

    def _update_recent_files_menu(self):
        return project_files.update_recent_files_menu(self)

    def _on_open_recent_file(self, file_path):
        return project_files.on_open_recent_file(self, file_path)

    def _on_clear_recent_files(self):
        return project_files.on_clear_recent_files(self)
