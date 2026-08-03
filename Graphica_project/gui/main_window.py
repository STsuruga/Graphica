import os
import io
import re
import types
import sys
import logging
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

# ドックの既定配置のバージョン。デフォルトの配置(どのドックをどのエリアに
# 置くか)を変更したときはこの値を上げる。QSettingsに保存された前回のバージョンと
# 異なる場合、保存済みの window_state を復元せず新しい既定配置を優先する
# (そうしないと、restoreState() で常に旧配置が復元され続け、コード側で
# デフォルトのドック配置を変えても既存ユーザーには反映されない)。
DOCK_LAYOUT_VERSION = 4  # v4: 「プロットのプロパティ」「データセットのプロパティ」を1つのドックに統合

# グラフ内テキスト(目盛り・軸ラベル・凡例)の既定フォント。
# アプリのUIフォント(main.py の APP_FONT_FAMILIES)とは意図的に別系統にしている:
# matplotlibは独自のフォント探索(freetypeベースのキャッシュ)を使うため、
# Qt/Windowsの「UI専用」フォントバリアント("Yu Gothic UI"等)を渡すと解決できず
# 文字化けする。"Yu Gothic"は実ファイルとして存在しmatplotlibからも解決できる。
PLOT_DEFAULT_FONT_FAMILY = "Yu Gothic"

# --- オートセーブに関する定数 ---
DEFAULT_AUTOSAVE_INTERVAL_MIN = 5  # 分単位 (0 = 無効化)
MIN_AUTOSAVE_INTERVAL_MIN = 0
MAX_AUTOSAVE_INTERVAL_MIN = 180
AUTOSAVE_FILENAME = "autosave.graphica"  # 新規インストール/セッションは新形式(JSON)でオートセーブする
AUTOSAVE_GENERATIONS = 3  # 保持する世代数 (最新のautosave.graphicaを含む)

# --- 最近使ったファイル一覧に関する定数 ---
MAX_RECENT_FILES = 10

# --- PySide6 ---
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QFileDialog,
                               QComboBox, QLabel, QSpinBox, QDoubleSpinBox, QPushButton,
                               QTextEdit, QCheckBox, QGroupBox, QSizePolicy, QWidget,
                               QDockWidget, QScrollArea, QMessageBox,
                               QLineEdit, QHBoxLayout, QFormLayout, QAbstractItemView,
                               QDialog, QTreeWidget, QTreeWidgetItem, QGridLayout,
                               QInputDialog, QMenu, QFrame, QToolButton, QWidgetAction)
from PySide6.QtGui import QFont, QIcon, QAction, QValidator, QUndoStack
from PySide6.QtCore import Qt, QTimer, QSettings, QSize, Signal
from models.project import ProjectModel
from core.version import APP_NAME, __version__
from core.i18n import tr, set_language, DEFAULT_LANGUAGE
from core.plugin_api import load_plugins_once

# --- Matplotlib ---
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

# --- Qt Designer から生成された UI ---
# ※ main_window.py と同じ階層ではなく大元のフォルダにあるため、そのままインポートできます
from ui_main_window import Ui_MainWindow

# --- 自分で分割したモジュール ---
from core.dataset import Dataset
from gui.canvas import MplCanvas, DEFAULT_POINT_LABEL_MAX_POINTS
from gui.theme import apply_form_spacing
from gui.workers import DataLoadWorker
from gui.dialogs import ColumnPreviewDialog, ExcelMultiSheetDialog, WelcomeDialog
from gui.color_picker_widget import ColorPickerWidget
from gui.icon_utils import load_svg_icon, ICONS_DIR

# ツールバー/ボタンのアイコン(項目67・70)。matplotlibツールバー標準アイコンと
# 近いトーンになるよう、中間的な濃さのニュートラルグレーで統一する。
TOOLBAR_ICON_COLOR = "#3B3F42"

# キャンバス上部ツールバーのアイコンサイズ(px)。Qtの既定は24pxだが、
# カスタムボタンを追加した結果、ウィンドウ幅が狭いときにツールバーが溢れ、
# はみ出したボタンが極小の「>>」に押し込まれて事実上操作できなくなっていた。
# アプリ内の他のアイコンのみボタン(18px)ともトーンを揃える。
TOOLBAR_ICON_SIZE = 18


def _svg_icon(name, size=20):
    """assets/icons/{name}.svg を統一トーンのQIconとして読み込む共通ヘルパー"""
    return load_svg_icon(resource_path(os.path.join(ICONS_DIR, f"{name}.svg")),
                          color=TOOLBAR_ICON_COLOR, size=size)
from core.excel_utils import find_unevaluated_formula_cells
from gui.export_preview_panel import ExportPreviewPanel
from gui.dataset_style_icon import make_dataset_style_icon
from gui.color_history import load_recent_colors_into_picker

# --- 責務ごとに分割した Mixin (God Object 化を避けるための構成) ---
from gui.mixins.ui_setup_mixin import UISetupMixin
from gui.mixins.settings_mixin import SettingsMixin
from gui.mixins.dataset_mixin import DatasetMixin
from gui.mixins.cursor_mixin import CursorMixin
from gui.mixins.annotation_mixin import AnnotationMixin
from gui.mixins.layout_edit_mixin import LayoutEditMixin
from gui.mixins.export_mixin import ExportMixin
from gui.mixins.project_io_mixin import ProjectIOMixin
from gui.mixins.help_mixin import HelpMixin


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

#==============================================================================
# メインアプリケーションクラス
#==============================================================================
# 各 Mixin が担当する責務:
#   UISetupMixin    : 一度きりのUI初期化 (シグナル接続, メニューバー, 初期状態)
#   SettingsMixin   : プロット(軸)の外観設定の収集/適用、フォント・色ダイアログ
#   DatasetMixin    : データセットの追加/削除/複製/プロパティ編集、フィット・ピーク検出
#   CursorMixin     : データカーソル (グラフ上のクリックで座標表示) 機能
#   ExportMixin     : 画像/PDF/SVGへのエクスポートとプレビュー生成
#   ProjectIOMixin  : プロジェクト保存/読込メニューと書式テンプレート機能
#   HelpMixin       : ヘルプダイアログ
# PlotterApp 本体には、初期化・ファイルI/Oの中核・プロット更新など、
# 上記どれにも属さない「アプリのエントリーポイント」的な処理のみを残す。
class PlotterApp(QMainWindow, UISetupMixin, SettingsMixin, DatasetMixin,
                  CursorMixin, AnnotationMixin, LayoutEditMixin, ExportMixin,
                  ProjectIOMixin, HelpMixin):
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
        アプリケーションの初期化 (コンストラクタ)。
        UIのロード、状態変数の初期化、動的UIの構築、シグナル接続を行います。

        Args:
            run_startup_checks (bool): オートセーブ復元確認・初回起動ウェルカム表示・
                ウィンドウの表示状態(ドック配置)復元/保存・clean_exitフラグの管理を
                行うかどうか。複数プロジェクトタブ(項目40)機能で、MainAppWindowが
                2つ目以降のタブとしてこのクラスを起動する際は False にする
                (これらはアプリ全体で1回・1つのタブに対してのみ意味を持つ処理のため)。
            tab_id (int, optional): タブ化機能で複数インスタンスを同時に開く際、
                オートセーブファイルが衝突しないよう区別するための番号。
                None(既定、単独起動または最初のタブ)の場合は従来通りの
                ファイル名 (autosave.graphica) を使う。
        """
        super().__init__()
        self._run_startup_checks = run_startup_checks
        self.tab_id = tab_id
        # ★ 複数タブが同時にオートセーブすると同じファイルを取り合ってしまうため、
        # 最初のタブ(=従来の単独起動と同じ)以外は専用のファイル名を使う。
        # (保存先ディレクトリの反映は self.settings 作成後に _update_autosave_path で行う)
        self._autosave_base_filename = (
            AUTOSAVE_FILENAME if not tab_id
            else f"autosave_tab{tab_id}{os.path.splitext(AUTOSAVE_FILENAME)[1]}"
        )
        self._autosave_filename = self._autosave_base_filename

        # --- 1. UIファイルのロード ---
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # 塗りつぶし(エリア)プロット / 棒グラフ: Qt Designerが生成したコンボボックスに
        # 実行時に選択肢を追加する (他の動的追加ウィジェットと同じ方針で、
        # ui_main_window.py 自体は編集しない)
        self.ui.plot_type_combo.addItem("Area")
        self.ui.plot_type_combo.addItem("Bar")

        # ★ データセットリストを QListWidget から QTreeWidget に置き換える。
        #   フォルダによるグループ分けに対応するため (Designerが生成する
        #   dataset_list_widget は QListWidget なので、実行時に同じ位置へ差し替える)。
        self._replace_dataset_list_with_tree()

        self.project = ProjectModel()
        # アプリの設定 (オートセーブ間隔、最近使ったファイル一覧) を永続化するためのストレージ
        self.settings = QSettings("Graphica", "Graphica")
        # オートセーブの保存先(環境設定で指定可能): 未設定なら従来どおりアプリのフォルダ
        self._update_autosave_path()
        # 色選択ダイアログの「最近使った色」をカスタムカラー欄に復元する
        load_recent_colors_into_picker(self.settings)

        # UIの多言語対応(項目41): 保存済みの表示言語をここで反映する。
        # (以降に構築されるメニュー・主要ボタン等の tr() 呼び出しに影響するため、
        #  UI構築より前、できるだけ早い段階で行う必要がある)
        set_language(self.settings.value("language", DEFAULT_LANGUAGE))

        # 前回のセッションが正常終了したかどうかのフラグ。
        # 起動時に読み取った直後にFalseへ書き換え、closeEvent()で正常終了時のみ
        # Trueに戻す。次回起動時にFalseのままなら、前回はクラッシュ等で異常終了した
        # とみなし、オートセーブからの復元を提案する (_check_autosave_recovery)。
        # ★ このフラグはアプリ全体で共有する1つのQSettings値のため、複数タブが
        # 同時に読み書きすると意味を成さなくなる。run_startup_checks=Falseの
        # (2つ目以降の)タブでは一切触らない。
        if self._run_startup_checks:
            self._had_clean_exit = self.settings.value("clean_exit", True, type=bool)
            self.settings.setValue("clean_exit", False)
        else:
            self._had_clean_exit = True

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        icon_path = resource_path("Graphica.ico")
        self.setWindowIcon(QIcon(icon_path))
        # Designer で作成したドックウィジェット (右側のパネル) をメインウィンドウに追加
        # (タイトルは、後段でプロパティ/データセットの2セクションを統合する際に
        #  tr("プロパティ") へ設定し直す)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.ui.control_dock_widget)

        # --- 2. 状態変数の初期化 ---
        self.data_editor_dialog = None # データエディタ (非モーダル) のインスタンス保持用
        self.help_dialog = None        # mathtextヘルプ (非モーダル) のインスタンス保持用
        self.calc_help_dialog = None   # 列計算ヘルプ (非モーダル) のインスタンス保持用
        self.fit_result_dialog = None  # 曲線フィット結果 (非モーダル) のインスタンス保持用
        self.peak_result_dialog = None # ピーク検出結果 (非モーダル) のインスタンス保持用
        self._data_load_worker = None  # ファイル読み込み用バックグラウンドワーカーの保持用
        self._copied_dataset_style = None  # 「スタイルをコピー」でコピーした属性値の辞書

        # データセットのプロパティ変更 (色・線種・凡例名など) 用の Undo/Redo スタック
        # (DataEditorDialog 内のセル編集用スタックとは別物)
        self.undo_stack = QUndoStack(self)

        # オートセーブ用タイマーの設定 (間隔は設定から復元。0分なら無効化されたまま)
        # ★ _create_menu_bar() がメニューの初期表示テキストのために参照するため、
        #   メニュー作成より前にここで用意しておく必要がある。
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.auto_save)
        saved_interval_min = self.settings.value(
            "autosave_interval_min", DEFAULT_AUTOSAVE_INTERVAL_MIN, type=int
        )
        if saved_interval_min > 0:
            self.autosave_timer.start(saved_interval_min * 60 * 1000)

        # --- サブプロット管理用の変数 ---
        self.all_axes = []           # すべての主軸 (Matplotlib Axes) を保持するリスト
        self.all_secondary_axes = [] # すべての第2Y軸 (Axes) を保持するリスト
        self.project.all_plot_settings = []  # すべての軸の設定 (辞書) を保持するリスト
        self.project.active_axis_index = 0   # 現在編集中の軸インデックス (0始まり)

        # --- データカーソル機能用の変数 ---
        self.cursor_mode_enabled = False # カーソルモードがONかOFFか
        self.cursor_connection_id = None # Matplotlib イベント接続ID (切断時に使用)
        self.cursor_annotation = None    # 表示中の注釈 (Annotation) オブジェクト

        # --- 自由なテキスト注釈・矢印機能用の変数 ---
        self.annotation_mode_enabled = False   # 注釈モードがONかOFFか
        self._annotation_press_cid = None      # button_press_event の接続ID
        self._annotation_release_cid = None    # button_release_event の接続ID
        self._annotation_drag_start = None     # ドラッグ開始点 (ax, x, y) または None

        # --- 自由配置レイアウト(項目37)の編集モード用の変数 ---
        self.layout_edit_mode_enabled = False  # レイアウト編集モードがONかOFFか
        self._layout_edit_press_cid = None     # button_press_event の接続ID
        self._layout_edit_motion_cid = None    # motion_notify_event の接続ID
        self._layout_edit_release_cid = None   # button_release_event の接続ID
        self._layout_drag_state = None         # ドラッグ中の状態 (dict) または None

        # --- デフォルトの書式設定 (これらが all_plot_settings[0] の初期値になる) ---
        # ★ QFont() (=アプリ全体のUIフォントを継承) ではなく明示的に
        #   PLOT_DEFAULT_FONT_FAMILY を指定する。グラフのテキストは
        #   matplotlib自身のフォント解決系(独自のフォントキャッシュ)を通るため、
        #   Qt側のUIフォント("Yu Gothic UI"等のUI専用バリアント)をそのまま
        #   渡すとmatplotlibがフォントを解決できず文字化けする(findfont警告)。
        #   UIのフォントとプロット内テキストのフォントは別系統として扱う。
        self._tick_font = QFont(PLOT_DEFAULT_FONT_FAMILY)
        self._tick_color = '#000000' # 黒
        self._tick_width = 0.8
        self._axis_label_font = QFont(PLOT_DEFAULT_FONT_FAMILY)
        self._axis_label_color = '#000000'
        self._spine_width = 1.0
        self._spine_color = '#000000'
        self._legend_font = QFont(PLOT_DEFAULT_FONT_FAMILY)
        self._legend_color = '#000000'

        # --- 3. ウィンドウサイズとレイアウトの基本設定 ---
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.ui.control_dock_widget.setFixedWidth(CONTROL_DOCK_WIDTH) # 右側パネルの幅を固定

        # ★ GUI洗練: 中央ウィジェットのgridLayout_2は、どの行にも明示的な
        #   stretch指定が無かったため、ウィンドウの余った縦スペースがキャンバス行(1)と
        #   データセットリスト行(2)に均等に配分されてしまい、データセットが少ない時に
        #   リストの下に大きな空白ができていた(旧properties_groupbox用の行5が
        #   プロパティドックへ移動して空になった分の余白も、キャンバスではなく
        #   リスト側に流れ込んでいた)。余ったスペースは常にキャンバスへ優先的に
        #   割り当てるようにする。
        self.ui.gridLayout_2.setRowStretch(1, 1)  # プロットキャンバス: 余白を優先的に受け取る
        self.ui.gridLayout_2.setRowStretch(2, 0)  # データセットリスト: 内容に応じた高さのみ
        self.ui.gridLayout_2.setRowStretch(3, 0)  # 操作ボタン行: 内容に応じた高さのみ


        # --- 4. Matplotlib キャンバスとツールバーの組み込み ---

        # MplCanvas (グラフ描画領域) を作成
        self.canvas = MplCanvas(self, width=5, height=4, dpi=100)
        # ダークモード設定を復元 (QApplication側の配色は _create_menu_bar で適用する)
        self.canvas.dark_mode = self.settings.value("dark_mode", False, type=bool)
        # データ点ラベルの表示上限(環境設定、項目105: 大量データでのフリーズ防止)
        self.canvas.point_label_max_points = self.settings.value(
            "point_label_max_points", DEFAULT_POINT_LABEL_MAX_POINTS, type=int)
        # Matplotlib 標準のナビゲーションツールバーを作成
        toolbar = NavigationToolbar(self.canvas, self)
        # ★ バグ修正: このツールバーはQMainWindowのツールバー領域ではなく
        #   plot_container の通常のレイアウトに入れているため、幅が足りなくなると
        #   はみ出したボタンが幅12pxほどの極小の「>>」ボタンの中に押し込まれ、
        #   事実上見つけられなくなる。カスタムボタン(データカーソル/注釈/
        #   レイアウト編集/統計情報)を追加した結果、既定の24pxアイコンでは
        #   ウィンドウを少し狭めただけで溢れるようになっていた。
        #   アプリ内の他のアイコンボタン(18px)とトーンを揃えつつ、必要幅を
        #   縮めてオーバーフローしにくくする。
        toolbar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))

        # --- ★ ツールバーにカスタムボタン (データカーソル) を追加 ★ ---
        toolbar.addSeparator()
        # 1. Action (ボタンの動作定義) を作成
        # ★ self.cursor_action として保持する (後で注釈モードとの排他制御のために
        #   setChecked() で外部からこのActionを操作する必要があるため)
        self.cursor_action = QAction(
            # Tabler Icons "pointer"(項目67): matplotlibツールバーと同トーンの線画アイコン
            _svg_icon("pointer"),
            tr("データカーソル"), # ツールチップ
            self # 親ウィジェット
        )
        # 2. Action をチェック可能 (トグルボタン) にする
        self.cursor_action.setCheckable(True)
        # 3. Action がトリガーされたら (checked の bool 値と共に) スロットに接続
        self.cursor_action.triggered.connect(self._toggle_cursor_mode)
        # 4. Action をツールバーに追加
        toolbar.addAction(self.cursor_action)

        # --- ★ ツールバーにカスタムボタン (自由なテキスト注釈・矢印) を追加 ★ ---
        self.annotation_action = QAction(
            _svg_icon("message-2"),  # Tabler Icons "message-2"(項目67)
            tr("注釈 (クリック:テキスト / ドラッグ:矢印 / 右クリック:削除)"),
            self
        )
        self.annotation_action.setCheckable(True)
        self.annotation_action.triggered.connect(self._toggle_annotation_mode)
        toolbar.addAction(self.annotation_action)

        # --- ★ ツールバーにカスタムボタン (自由配置レイアウトの編集) を追加 ★ ---
        # 「自由配置レイアウト」チェックボックスが有効な間だけ使えるモード。
        # ドラッグでサブプロットの位置(内部ドラッグ)・サイズ(右下端ドラッグ)を変更する。
        self.layout_edit_action = QAction(
            _svg_icon("layout-grid"),  # Tabler Icons "layout-grid"(項目67)
            tr("レイアウト編集 (自由配置レイアウト時のみ: ドラッグでプロットを移動/リサイズ)"),
            self
        )
        self.layout_edit_action.setCheckable(True)
        self.layout_edit_action.setEnabled(False)
        self.layout_edit_action.triggered.connect(self._toggle_layout_edit_mode)
        toolbar.addAction(self.layout_edit_action)

        # ★ 統計情報ボタン(項目106)はこの時点ではまだ self.stats_summary_label が
        #   存在しないため、それが作られた後のセクションでこの `toolbar` 変数を
        #   使って追加する(__init__の同じメソッドスコープ内なので参照可能)。

        # Designer で用意した plot_container (おそらく QWidget) にレイアウトを作成
        # 項目72: キャンバス周りに余白とセパレーターを設け、書式パネルの並びとの
        # 境目をはっきりさせる(フォームの塊が続くだけの画面に見えないようにする)。
        self.ui.plot_container.setObjectName("plot_container")
        plot_layout = QVBoxLayout(self.ui.plot_container)
        plot_layout.setContentsMargins(6, 6, 6, 6)
        plot_layout.setSpacing(6)
        plot_layout.addWidget(toolbar) # 上部にツールバー

        canvas_separator = QFrame()
        canvas_separator.setFrameShape(QFrame.Shape.HLine)
        canvas_separator.setObjectName("canvas_separator")
        plot_layout.addWidget(canvas_separator)

        plot_layout.addWidget(self.canvas) # 下部にキャンバス

        # --- 5. ステータスバーの設定 ---
        self.coordinate_label = QLabel("X= ---, Y= ---")
        # addPermanentWidget で、ステータスバーの右側に常時表示
        self.ui.statusbar.addPermanentWidget(self.coordinate_label)


        # --- 6. UIの「動的構築」 (Designer で定義されていないUIをコードで追加) ---

        # 0. データセットの色選択欄を、スウォッチ+カラーコード入力欄の複合ウィジェットに
        #    差し替える(項目65: パレット展開ボタン+カラーコード直接編集)
        old_color_button = self.ui.color_button
        self.color_picker_widget = ColorPickerWidget(self.settings, self)
        self.ui.formLayout_4.replaceWidget(old_color_button, self.color_picker_widget)
        old_color_button.hide()
        old_color_button.deleteLater()

        # 0b. 「新規データセット作成...」ボタン(項目63): ファイル読み込みを介さず、
        #     空のテーブルからデータセットを作成する。「データ追加」ボタンのすぐ隣に配置。
        self.new_dataset_button = QPushButton(tr("新規データセット作成..."))
        self.ui.horizontalLayout_3.insertWidget(1, self.new_dataset_button)

        # 1. 「プロット複製」「データ編集」ボタンをコードで作成
        self.duplicate_dataset_button = QPushButton(tr("プロット複製"))
        self.view_edit_data_button = QPushButton(tr("データ表示/編集"))
        self.fit_curve_button = QPushButton(tr("曲線フィット"))
        self.find_peaks_button = QPushButton(tr("ピーク検出"))
        self.auto_color_button = QPushButton(tr("自動配色"))  # 選択中の(複数可)データセットに配色を自動割り当て
        self.new_folder_button = QPushButton(tr("新しいフォルダ"))  # データセットのグループ分け用フォルダを作成

        # 1b. 操作ボタン行をアイコン付き・グループ分けに再編(項目70):
        #     「データ処理系」「解析系」「整理系」の3グループに分け、間を薄い
        #     セパレーターで区切る。頻度の低い「パレット管理...」はボタンとして
        #     常設せず、「…」オーバーフローメニューに移す。
        #     (シグナル接続は _connect_signals 側で従来どおり各ボタンに対して行うため、
        #      ここではアイコン付与とレイアウト上の並びだけを変更し、ロジックには触れない)
        _button_icons = {
            self.ui.add_dataset_button: ("file-plus", tr("データ追加")),
            self.new_dataset_button: ("table", tr("新規作成")),
            self.duplicate_dataset_button: ("copy", tr("複製")),
            self.view_edit_data_button: ("edit", tr("表示/編集")),
            self.ui.remove_dataset_button: ("trash", tr("削除")),
            self.fit_curve_button: ("chart-line", tr("曲線フィット")),
            self.find_peaks_button: ("mountain", tr("ピーク検出")),
            self.auto_color_button: ("palette", tr("自動配色")),
            self.new_folder_button: ("folder-plus", tr("新しいフォルダ")),
        }
        # ★ GUI洗練: テキスト付きボタンではなく、アイコンのみの正方形ボタンにする。
        #   ラベルはツールチップに残すため発見しやすさは保ちつつ、9個並んだ状態でも
        #   横幅を大きく取らず、右パネル全体の余白・サイズ感を改善する。
        for button, (icon_name, short_label) in _button_icons.items():
            button.setToolTip(button.text() or short_label)
            button.setText("")
            button.setIcon(_svg_icon(icon_name, size=18))
            button.setProperty("iconOnly", True)
            button.setFixedSize(34, 34)

        def _make_group_separator():
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setObjectName("button_row_separator")
            sep.setFixedWidth(2)
            return sep

        # データ処理系グループ: 追加/新規作成/複製/表示編集/削除 の並び順に揃える
        # (remove_dataset_button は Designer 由来ですでにレイアウトの2番目にあるため、
        #  複製・表示編集をその手前に挿入することで並び順だけを調整する)
        self.ui.horizontalLayout_3.insertWidget(2, self.duplicate_dataset_button)
        self.ui.horizontalLayout_3.insertWidget(3, self.view_edit_data_button)

        self.ui.horizontalLayout_3.insertWidget(5, _make_group_separator())
        # 解析系グループ
        self.ui.horizontalLayout_3.addWidget(self.fit_curve_button)
        self.ui.horizontalLayout_3.addWidget(self.find_peaks_button)

        self.ui.horizontalLayout_3.addWidget(_make_group_separator())
        # 整理系グループ
        self.ui.horizontalLayout_3.addWidget(self.auto_color_button)
        self.ui.horizontalLayout_3.addWidget(self.new_folder_button)

        self.ui.horizontalLayout_3.addStretch()

        # オーバーフローメニュー(「…」): 頻度の低い操作をここにまとめる
        self.dataset_overflow_button = QToolButton()
        self.dataset_overflow_button.setText("⋯")  # ⋯ (三点リーダー)
        self.dataset_overflow_button.setToolTip(tr("その他の操作"))
        self.dataset_overflow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.dataset_overflow_button.setFixedSize(34, 34)  # 他のアイコン専用ボタンと正方形サイズを揃える
        overflow_menu = QMenu(self.dataset_overflow_button)
        self.manage_palette_action = overflow_menu.addAction(
            _svg_icon("palette", size=16), tr("パレット管理...")
        )
        self.dataset_overflow_button.setMenu(overflow_menu)
        self.ui.horizontalLayout_3.addWidget(self.dataset_overflow_button)

        # 2. X/Y軸 列選択コンボボックスをコードで作成
        self.x_col_combo = QComboBox()
        self.y_col_combo = QComboBox()
        # Designer 上の既存のフォームレイアウト (formLayout_4) に挿入
        # (insertRow(1,...) を2回呼ぶと、2つ目が1行目、1つ目が2行目になる)
        self.ui.formLayout_4.insertRow(1, "Y軸の列", self.y_col_combo)
        self.ui.formLayout_4.insertRow(1, "X軸の列", self.x_col_combo)

        # 2b. エラーバー用の誤差列選択コンボボックス ("(なし)" を選ぶとエラーバー非表示)
        self.x_err_col_combo = QComboBox()
        self.y_err_col_combo = QComboBox()
        self.ui.formLayout_4.insertRow(3, "Y誤差列", self.y_err_col_combo)
        self.ui.formLayout_4.insertRow(3, "X誤差列", self.x_err_col_combo)

        # 2c. 透明度(アルファ)スピンボックスを追加 (0.0=完全に透明 ～ 1.0=不透明)
        self.alpha_label = QLabel("透明度")
        self.alpha_spinbox = QDoubleSpinBox()
        self.alpha_spinbox.setRange(0.0, 1.0)
        self.alpha_spinbox.setSingleStep(0.05)
        self.alpha_spinbox.setDecimals(2)
        self.alpha_spinbox.setValue(1.0)
        self.ui.formLayout_4.insertRow(5, self.alpha_label, self.alpha_spinbox)

        # 2d. データポイントラベル表示 (各データ点の脇にY値または任意の列の値を表示)
        self.point_labels_checkbox = QCheckBox("データ点にラベルを表示")
        self.ui.formLayout_4.addRow(self.point_labels_checkbox)
        self.point_label_col_label = QLabel("ラベルの内容")
        self.point_label_col_combo = QComboBox()
        self.ui.formLayout_4.addRow(self.point_label_col_label, self.point_label_col_combo)

        # 3. 凡例の位置を選択するUIをコードで作成
        self.legend_loc_label = QLabel("凡例の位置")
        self.legend_loc_combo = QComboBox()
        self.legend_loc_combo.addItems([
            "best", "upper right", "upper left", "lower left", "lower right", "center"
        ])
        # Designer 上の既存のフォームレイアウト (formLayout_3) の7行目に挿入
        self.ui.formLayout_3.insertRow(7, self.legend_loc_label, self.legend_loc_combo)

        # (凡例フォント・色ボタンも同様に追加)
        self.legend_font_label = QLabel("凡例フォント")
        self.legend_font_button = QPushButton("フォント選択...")
        self.ui.formLayout_3.insertRow(8, self.legend_font_label, self.legend_font_button)

        self.legend_color_label = QLabel("凡例 文字色")
        self.legend_color_button = QPushButton("色選択...")
        self.ui.formLayout_3.insertRow(9, self.legend_color_label, self.legend_color_button)

        # (凡例の表示順序: 描画順とは独立にドラッグで並べ替えできるようにする)
        self.legend_order_button = QPushButton("凡例の順序...")
        self.ui.formLayout_3.insertRow(10, self.legend_order_button)

        # フォント選択/色選択ボタン群にアイコンを追加(ユーザーフィードバックを受けて)
        for button, icon_name in (
            (self.ui.tick_font_button, "typography"),
            (self.ui.tick_color_button, "color-swatch"),
            (self.ui.axis_label_font_button, "typography"),
            (self.ui.axis_label_color_button, "color-swatch"),
            (self.ui.spine_color_button, "color-swatch"),
            (self.legend_font_button, "typography"),
            (self.legend_color_button, "color-swatch"),
        ):
            button.setIcon(_svg_icon(icon_name, size=16))

        # 4. フィット情報表示用のUI (非表示で) 追加
        self.fit_info_label = QLabel("フィット情報")
        self.fit_info_textedit = QTextEdit()
        self.fit_info_textedit.setReadOnly(True)
        self.fit_info_textedit.setFixedHeight(100) # 高さを固定
        self.ui.formLayout_4.addRow(self.fit_info_label, self.fit_info_textedit)

        # 4b. 統計サマリー表示用のUI (項目106: 以前は「データセットのプロパティ」に
        #     常時1行を占有していたが、常に使う情報ではないため、ツールバーの
        #     アイコンボタンから必要な時だけポップアップで参照できる方式に変更した。
        #     _update_stats_summary_label (dataset_mixin.py) は選択中データセットが
        #     変わるたびにこのラベルのテキストを更新し続ける(ポップアップが
        #     閉じている間も)。
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
        toolbar.addSeparator()
        toolbar.addWidget(self.stats_toolbar_button)

        # 5. 第2Y軸チェックボックスを追加
        self.use_secondary_y_checkbox = QCheckBox("第2Y軸 (右側) を使用")
        self.ui.formLayout_4.addRow(self.use_secondary_y_checkbox)

        # 6. 第2Y軸ラベル用のUI (非表示で) 追加
        self.y2_label_text_label = QLabel("第2Y軸ラベル")
        self.y2_label_text_edit = QLineEdit()
        self.ui.formLayout_3.insertRow(3, self.y2_label_text_label, self.y2_label_text_edit)

        # 7. 目盛り方向UIを追加
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

        self.ui.formLayout_3.insertRow(5, self.tick_direction_label, dir_layout)
        self.ui.formLayout_3.insertRow(6, self.tick_direction_y2_label, dir_y2_layout)

        # 8. 目盛りの指数表記フォーマット切り替え(項目62)
        #    自動/軸端にまとめて指数表記/目盛りごとに指数表記/常に小数表記 から選択
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

        self.y_tick_format_label = QLabel(tr("目盛り表記"))
        self.y_tick_format_combo = QComboBox()
        self.y_tick_format_combo.addItems(tick_format_choices)
        self.ui.formLayout_2.addRow(self.y_tick_format_label, self.y_tick_format_combo)

        # 9. タイトル/軸ラベル入力欄に、文字装飾メニューボタンを直接埋め込む(項目61)。
        #    ★ 改善(ユーザーフィードバックを受けて): 当初は入力欄から離れた場所に
        #      共通ツールバーを1つ置く形だったが、「どの欄に効くのか分かりにくい」
        #      「B/I/x²/x₂ のボタンが小さく見分けづらい」という指摘を受け、
        #      各入力欄のすぐ右に「Aa」ボタンを1つだけ配置し、クリックすると
        #      「太字」「イタリック」「上付き文字」「下付き文字」とフルテキストで
        #      書かれたメニューが開く形に変更した(欄との対応が一目瞭然になり、
        #      各項目が何をするかも省略なしで読める)。
        #    ★ 修正(さらなるユーザーフィードバック): NoFocusにしていても、
        #      ボタン押下(ポップアップメニューを開く動作)自体でテキスト欄の
        #      選択範囲が失われてしまう環境があることが判明した(メニューが
        #      開く際にフォーカスが他のウィジェットへ移り、選択がクリアされる)。
        #      そのため、メニュー項目が選ばれた時点で選択範囲を読み直すのではなく、
        #      ボタンが「押された瞬間」(pressed、まだ選択が生きている)に選択範囲を
        #      保存しておき、メニュー項目のtriggeredではその保存値を使う。
        # ★ ポップアップパネル化(項目101): 以前はテキストのみのQMenu
        #   (「太字」「イタリック」「上付き文字」「下付き文字」を項目として
        #   縦に並べただけ)だったが、ユーザーフィードバックを受けて、
        #   アイコン付きのボタンを横一列に並べた小さなパネル
        #   (QWidgetAction経由でQMenuに埋め込む)に変更した。見た目が
        #   ツールバーに近くなり、どのボタンが何をするか記号でも判別しやすい。
        self.label_format_menu_buttons = {}
        self._label_format_menus = {}
        self._label_format_pending_selection = {}
        for field_key, line_edit in (
            ('title', self.ui.title_text_edit),
            ('x_label', self.ui.x_label_text_edit),
            ('y_label', self.ui.y_label_text_edit),
        ):
            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setSpacing(4)

            # ★ replaceWidget: 既存のline_editをformLayout_3上の同じ位置に残したまま、
            #   [line_edit + ボタン] の複合ウィジェットに差し替える(項目65の
            #   ColorPickerWidget差し替えと同じ手法。行番号がずれないため安全)。
            self.ui.formLayout_3.replaceWidget(line_edit, wrapper)
            wrapper_layout.addWidget(line_edit, 1)

            format_button = QToolButton()
            format_button.setText("Aa")
            format_button.setToolTip(tr("文字装飾(太字・イタリック・上付き・下付き)"))
            format_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            format_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # ★ 右側パネルの幅は限られているため、ボタンはできるだけ小さく保ち、
            #   タイトル/軸ラベル入力欄自体の幅を圧迫しないようにする。
            format_button.setFixedSize(26, 22)
            small_font = QFont(format_button.font())
            small_font.setPointSize(max(7, small_font.pointSize() - 2))
            format_button.setFont(small_font)
            wrapper_layout.addWidget(format_button)
            format_button.pressed.connect(
                lambda fk=field_key, le=line_edit: self._capture_label_format_selection(fk, le)
            )

            menu = QMenu(format_button)
            panel = QWidget()
            panel_layout = QHBoxLayout(panel)
            panel_layout.setContentsMargins(6, 6, 6, 6)
            panel_layout.setSpacing(4)

            decoration_buttons = {}
            for deco_key, icon_name, tooltip in (
                ('bold', 'bold', tr("太字")),
                ('italic', 'italic', tr("イタリック")),
                ('superscript', 'superscript', tr("上付き文字")),
                ('subscript', 'subscript', tr("下付き文字")),
            ):
                deco_button = QToolButton()
                deco_button.setIcon(_svg_icon(icon_name, size=16))
                deco_button.setToolTip(tooltip)
                deco_button.setProperty("iconOnly", True)
                deco_button.setFixedSize(28, 28)
                panel_layout.addWidget(deco_button)
                decoration_buttons[deco_key] = deco_button

            widget_action = QWidgetAction(format_button)
            widget_action.setDefaultWidget(panel)
            menu.addAction(widget_action)
            format_button.setMenu(menu)

            self.label_format_menu_buttons[field_key] = decoration_buttons
            self._label_format_menus[field_key] = menu

        # --- 7. UIの「動的リファクタリング」 (Designer のUI構造をコードで変更) ---

        # 1. 「描画先」コンボボックスを "プロパティ" 欄に追加
        self.subplot_target_label = QLabel("描画先プロット")
        self.subplot_target_combo = QComboBox()
        self.ui.formLayout_4.addRow(self.subplot_target_label, self.subplot_target_combo)

        # 2. ★ GUI洗練: 「プロットのプロパティ」(control_dock_widget) と
        #    「データセットのプロパティ」(properties_groupbox) は、以前は別々の
        #    QDockWidgetとして右側に縦積みされていた。それぞれが独自のOS標準
        #    タイトルバー(フロート/閉じるアイコン付き)を持つため、右パネルが
        #    「継ぎ目のある2枚の箱」に見えてしまっていた。
        #    1つのドックの中に、見出し付きグループボックス2つを縦に並べる形に
        #    まとめることで、1枚のカードのように見せる
        #    (QDockWidget内のQGroupBoxは、theme.pyで枠なし・プレーンな見出しに
        #    スタイルされている)。
        #
        #    self.properties_dock_widget は control_dock_widget のエイリアスとして
        #    残す (表示メニュー等、他のコードから同名で参照される箇所があるため)。
        self.properties_dock_widget = self.ui.control_dock_widget
        self.ui.control_dock_widget.setWindowTitle(tr("プロパティ"))

        # 2a. 「プロットのプロパティ」セクション: 既存のdockWidgetContents
        #     (目盛/書式/ラベルタブなど) を、見出し付きグループボックスで包み直す
        original_control_widget = self.ui.control_dock_widget.widget()
        plot_properties_group = QGroupBox(tr("プロットのプロパティ"))
        plot_properties_layout = QVBoxLayout(plot_properties_group)
        plot_properties_layout.setContentsMargins(0, 4, 0, 0)
        if original_control_widget:
            plot_properties_layout.addWidget(original_control_widget)
        else:
            logger.warning("control_dock_widget の中身が見つかりません。")

        # 2b. 「データセットのプロパティ」セクション: properties_groupbox は
        #     すでに自身のタイトルを持つグループボックスなので、そのまま使う
        self.ui.properties_groupbox.setTitle(tr("データセットのプロパティ"))

        # 2c. 折りたたみ可能に(項目102): 「データセットのプロパティ」「プロット
        #     のプロパティ」はどちらも項目数が多く縦に長くなりがちなため、
        #     アコーディオン形式(クリックで開閉)にする。
        #     ★ properties_groupbox はDesigner生成のgridLayout_4を直接持つため、
        #     内部の子ウィジェットを1つずつ数えて表示/非表示するのは(ネストした
        #     レイアウト項目を取りこぼす恐れがあり)壊れやすい。代わりに、
        #     QGroupBox自体(枠・タイトルごと)は一切変更せず、外側に新しい
        #     開閉トグルボタンを1つ追加してQGroupBox全体の表示/非表示を
        #     切り替える方式にする(タイトルの二重表示を避けるため、
        #     QGroupBox自身のタイトルは空にし、トグルボタン側にだけ表示する)。
        dataset_section = self._wrap_in_collapsible_section(
            self.ui.properties_groupbox, tr("データセットのプロパティ"))
        plot_section = self._wrap_in_collapsible_section(
            plot_properties_group, tr("プロットのプロパティ"))

        # 2d. 2つのセクションを1本の縦スクロールにまとめ、1つのドックに収める
        # ★ バグ修正: 既定のレイアウト余白のままだと、縦スクロールバー分を差し引いた
        #   ビューポート幅に対して中身がわずかに(数十px)はみ出し、意図しない横スクロール
        #   バーが常時表示されてしまっていた。左右の余白を切り詰めて幅の余裕を作る。
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

        # 2b. ★ 常時表示のエクスポートプレビューパネル (右側ドックに3つ目のタブとして追加)
        #    設定(サイズ・DPI)を変更するたびに自動でプレビューを更新し、
        #    全サブプロットをまとめた完成形をその場で確認しながら保存/コピーできる。
        #    デフォルトでは非表示にしておき (常時描画による負荷を避けるため)、
        #    表示メニューから必要な時だけ開く。
        self.export_preview_panel = ExportPreviewPanel(self)
        self.export_preview_dock_widget = QDockWidget(tr("エクスポートプレビュー"), self)
        self.export_preview_dock_widget.setObjectName("ExportPreviewDockWidget")
        self.export_preview_dock_widget.setWidget(self.export_preview_panel)
        # ★ GUI改善: 「プロットのプロパティ」「データセットのプロパティ」のような
        #   常設パネルとは性質が異なる(必要な時だけ開く「確認用」の存在)ため、
        #   右列や下部にドッキングしてメインのキャンバス領域を圧迫するのではなく、
        #   既定でフローティングの独立ウィンドウとして開く。ドラッグして本体に
        #   ドッキングすることも引き続き可能(QDockWidgetの標準機能のまま)。
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.export_preview_dock_widget)
        self.export_preview_dock_widget.setFloating(True)
        self.export_preview_dock_widget.hide()
        self._export_preview_first_show = True

        def _on_export_preview_visibility_changed(visible):
            if not visible:
                return
            # 初回表示時のみ、見やすいサイズ・位置に整える
            # (フローティングDockWidgetは表示されるまで実際のジオメトリを
            #  持たないことがあるため、初回のshowのタイミングで設定する)
            if self._export_preview_first_show and self.export_preview_dock_widget.isFloating():
                self._export_preview_first_show = False
                preview_width, preview_height = 820, 680
                self.export_preview_dock_widget.resize(preview_width, preview_height)
                center = self.geometry().center()
                self.export_preview_dock_widget.move(
                    center.x() - preview_width // 2, center.y() - preview_height // 2
                )
            self.export_preview_panel.refresh_preview()

        self.export_preview_dock_widget.visibilityChanged.connect(_on_export_preview_visibility_changed)

        # 5. ★ 「ラベル/書式」タブのレイアウトを「手術」する
        #    (サブプロット設定用のUIを先頭に挿入するため)
        layout_group = QGroupBox(tr("グラフ全体レイアウト"))
        layout_form = QFormLayout()
        # (サイズポリシーを設定し、垂直方向に伸びすぎないようにする)
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

        # (自由配置レイアウト: 均等グリッドでなく、サブプロットをドラッグで
        #  自由な位置・サイズに配置できるモード。既定はOFF(従来のグリッド))
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

        layout_group.setLayout(layout_form)

        active_axis_group = QGroupBox(tr("編集対象のプロット"))
        active_axis_layout = QVBoxLayout()
        sizePolicy = active_axis_group.sizePolicy()
        sizePolicy.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        active_axis_group.setSizePolicy(sizePolicy)
        self.active_axis_combo = QComboBox()
        active_axis_layout.addWidget(self.active_axis_combo)
        active_axis_group.setLayout(active_axis_layout)

        # 6. Designer の「ラベル/書式」タブ (tab_3) のレイアウトを取得
        grid_layout = self.ui.tab_3.layout() # (これは QGridLayout であると仮定)

        # 7. 既存のレイアウト (formLayout_3) を (0, 0) から一時的に取得
        existing_layout_item = grid_layout.itemAtPosition(0, 0)

        if existing_layout_item:
            # (0, 0) から一時的に削除
            grid_layout.removeItem(existing_layout_item)

        # 8. 0行目, 1行目に新しいウィジェットを追加
        grid_layout.addWidget(layout_group, 0, 0)
        grid_layout.addWidget(active_axis_group, 1, 0)

        if existing_layout_item:
            # 9. 既存のレイアウトを 2行目 に追加し直す
            grid_layout.addItem(existing_layout_item, 2, 0)

        # --- 8. イベント接続と初期化の呼び出し ---

        # Matplotlib のマウス移動イベント -> ステータスバー座標更新
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)

        # グラフ要素の直接クリック選択(項目35): データカーソル/注釈モードのON/OFFに
        # 関わらず常時有効な、独立したpick_event接続 (詳細は _on_element_pick を参照)
        self.canvas.mpl_connect('pick_event', self._on_element_pick)

        # プラグインの読み込み (メニューバー作成より前に行う必要がある:
        # プラグインが register_menu_action() で追加したメニュー項目を
        # _create_menu_bar() が読むため)。
        # ★ 複数プロジェクトタブ(項目40)ではPlotterAppがタブごとに作られるが、
        # プラグインの読み込み・登録(フィット関数レジストリへの登録等)は
        # プロセス全体で1度だけ行う(load_plugins_once がキャッシュする)。
        # メニューへのアクション追加自体は、タブごとに自分の menuBar() へ
        # 個別に行う必要があるため、_create_menu_bar() 側で行う。
        self.plugin_api = load_plugins_once(resource_path("plugins"))

        # UIコントロールのシグナル接続を _connect_signals ヘルパーメソッドで実行
        self._connect_signals()

        # メニューバー (ファイル, ヘルプなど) を作成
        self._create_menu_bar()

        # ★★★ 重要な初期化プロセス ★★★
        # 1. 現在のUI (デフォルト状態) から設定を辞書として収集
        default_settings = self._gather_settings_from_ui()
        # 2. これを「0番目のプロット」の設定としてリストに追加
        self.project.all_plot_settings.append(default_settings)
        # 3. 不要なUI (第2Y軸ラベルなど) を非表示にする
        self._set_initial_ui_state()
        # 項目69: ミニ統計ラベル分の高さを見込んで、リスト自体の上限は少し控えめにする
        self.ui.dataset_list_widget.setMaximumHeight(175)
        # (複数選択・ドラッグ&ドロップの設定は _replace_dataset_list_with_tree で設定済み)

        spacing_value = 6
        if self.ui.formLayout_3: self.ui.formLayout_3.setSpacing(spacing_value)
        if self.ui.formLayout_4: self.ui.formLayout_4.setSpacing(spacing_value)


        # X/Y軸の最小値・最大値: 負の値も含めて指数表記で入力できるようにする
        for spin_box in [self.ui.x_min_spinbox, self.ui.x_max_spinbox,
                          self.ui.y_min_spinbox, self.ui.y_max_spinbox]:
            _enable_scientific_notation_input(spin_box, minimum=-np.inf, maximum=np.inf)

        # 目盛り間隔 (主目盛/補助目盛): 0以上の値のみだが、同様に指数表記で入力できるようにする
        # (これにより、非常に細かい/広いデータ範囲でも間隔を正確に指定できる)
        for spin_box in [self.ui.x_major_tick_interval_spinbox, self.ui.y_major_tick_interval_spinbox,
                          self.ui.x_minor_tick_interval_spinbox, self.ui.y_minor_tick_interval_spinbox]:
            _enable_scientific_notation_input(spin_box, minimum=0, maximum=np.inf)

        # 4. 最初のプロット描画を実行
        self._update_plot()

        # ドックの配置は、前回終了時の状態をQSettingsから復元する。保存されたものが
        # 無い(初回起動)場合のみ、デフォルトのドック比率(resizeDocks)を使う。
        # ★ ウィンドウ全体のサイズ・位置(saveGeometry/restoreGeometry)は、複数プロジェクト
        # タブ(項目40)ではこのウィンドウ自体が最上位ウィンドウではなくなった
        # (MainAppWindowに埋め込まれるタブの1つになる)ため、そちらの責務に移した。
        # また、複数タブが同じQSettingsキーを取り合わないよう、ここでの
        # ドック状態の保存/復元自体も最初のタブ(run_startup_checks=True)に限定する。
        # ★ デフォルトのドック配置(DOCK_LAYOUT_VERSION)自体を変更した場合、
        #   保存済みのバージョンと異なればあえて restoreState() を使わない
        #   (そうしないと、旧バージョンの配置が復元され続けてしまい、
        #   コード側でデフォルト配置を変えても既存ユーザーに反映されない)。
        # ★ バグ修正: restoreState() はここ(__init__の途中)ではまだ
        #   このウィンドウがMainAppWindowのタブとして実際の最終サイズに
        #   埋め込まれる前(単独のQMainWindowとしてDesigner既定サイズのまま)
        #   に呼ばれてしまい、ドック/ツールバーのスプリッター位置が誤ったサイズ
        #   基準で復元される。この結果、ウィンドウを前回リサイズしてから終了→
        #   再起動した場合にのみ、ボタン等の見た目の描画位置と実際のクリック
        #   判定位置がずれる不具合が発生していた(最大化起動や、起動後の
        #   手動リサイズでは正しい最終サイズで再レイアウトされるため発生しない)。
        #   イベントループが一巡してウィンドウが実際の最終サイズで表示された
        #   後に復元することで解消する。
        QTimer.singleShot(0, self._restore_dock_layout)

        self.setAcceptDrops(True)

        # 起動直後に一度だけ、オートセーブからの復元が必要か確認する。
        # ウィンドウ表示前だとQMessageBoxが親を持てず不自然な位置に出るため、
        # イベントループが一巡した後 (ウィンドウ表示後) に実行されるよう遅延させる。
        # ★ 複数プロジェクトタブ(項目40)では、これらは最初のタブでのみ行う
        # (2つ目以降のタブは新規の空プロジェクトであり、復元/ウェルカム表示の対象外)。
        if self._run_startup_checks:
            QTimer.singleShot(0, self._check_autosave_recovery)
            # 初回起動時のみ、ウェルカムダイアログ(簡単な操作ガイド+サンプルデータ)を表示する。
            # オートセーブ復元の確認より後に登録することで、万一両方表示される場合でも
            # データの安全性に関わる確認(復元)を先に済ませてから案内できるようにする。
            QTimer.singleShot(0, self._check_first_launch)

        # 設定項目間の余白を広げる(ユーザーフィードバックを受けて)。
        # この時点までに Designer 生成/動的生成の QFormLayout はすべて構築済みのため、
        # __init__ の最後でまとめて適用する。
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
            except Exception as e:
                logger.warning("resizeDocks に失敗しました: %s", e)

    def closeEvent(self, event):
        """ウィンドウが閉じられる(正常終了する)ときに呼ばれる。"""
        if self._run_startup_checks:
            self.settings.setValue("clean_exit", True)
            # ドックの配置/表示状態を保存し、次回起動時に復元する
            self.settings.setValue("window_state", self.saveState())
            self.settings.setValue("dock_layout_version", DOCK_LAYOUT_VERSION)
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

        dialog = WelcomeDialog(self)
        dialog.exec()
        if dialog.load_sample_requested:
            self._load_sample_data()

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
        self._autosave_filename を再計算する。未設定/空文字の場合は従来どおり
        アプリのフォルダ(ファイル名のみ、resource_path基準ではなくcwd相対)に
        保存する。保存先ディレクトリが存在しない場合は作成しておく
        (auto_save() が失敗しないようにするため)。
        """
        autosave_dir = self.settings.value("autosave_dir", "", type=str)
        if autosave_dir:
            try:
                os.makedirs(autosave_dir, exist_ok=True)
            except OSError as e:
                logger.warning("オートセーブ保存先フォルダの作成に失敗しました: %s", e)
                autosave_dir = ""
        self._autosave_filename = (
            os.path.join(autosave_dir, self._autosave_base_filename)
            if autosave_dir else self._autosave_base_filename
        )

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

    def auto_save(self):
        """タイマーから定期的に呼ばれるオートセーブ処理"""
        try:
            self.project.dataset_group_tree = self._capture_dataset_group_tree()
            # ★ サブプロットの行数/列数はUIのスピンボックスが真の値であり、
            #   self.project.layout_rows/cols には保存直前まで反映されないため、
            #   ここで同期しないと常にデフォルト値(1x1)で保存されてしまう。
            self.project.layout_rows = self.subplot_rows_spinbox.value()
            self.project.layout_cols = self.subplot_cols_spinbox.value()
            self._rotate_autosave_generations()
            self.project.save_project(self._autosave_filename)
            self.statusBar().showMessage("オートセーブ完了", 3000)
        except Exception as e:
            logger.error("オートセーブに失敗しました: %s", e)
            self.statusBar().showMessage(f"オートセーブ失敗: {e}", 3000)

    def manual_save(self):
        """ユーザーが保存操作をしたときの処理"""
        # ★ 新形式(.graphica, JSON)をデフォルトの保存先とする。任意コード実行の
        #   リスクが無い安全なフォーマットへの移行を促すため、先頭のフィルタを
        #   .graphica にしている。ただし従来形式で保存したいユーザーのために、
        #   .pkl も引き続き選択できるようにしておく。
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "プロジェクトを保存", "",
            "Graphica Project (*.graphica);;Project Files (*.pkl)"
        )
        if filepath:
            # 一部環境ではファイルダイアログが選択フィルタに応じた拡張子を
            # 自動付加しないため、拡張子が無い場合は選択されたフィルタから補う。
            if not os.path.splitext(filepath)[1]:
                filepath += '.graphica' if 'graphica' in selected_filter else '.pkl'
            try:
                # フォルダ構造(現在のツリーの状態)を保存直前にキャプチャする
                self.project.dataset_group_tree = self._capture_dataset_group_tree()
                # ★ サブプロットの行数/列数もUIから保存直前に同期する (auto_saveと同じ理由)
                self.project.layout_rows = self.subplot_rows_spinbox.value()
                self.project.layout_cols = self.subplot_cols_spinbox.value()
                self.project.save_project(filepath)
                self.statusBar().showMessage(f"保存しました: {filepath}", 3000)
                self._add_recent_file(filepath)
                self.project_state_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{e}")

    def manual_load(self):
        """ユーザーが読み込み操作をしたときの処理"""
        # 新形式(.graphica)・旧形式(.pkl)のどちらも開けるようにする
        # (project.load_project側が拡張子で自動判別する)
        filepath, _ = QFileDialog.getOpenFileName(
            self, "プロジェクトを開く", "", "Project Files (*.graphica *.pkl)"
        )
        if filepath:
            self._load_project_from_path(filepath)

    def _load_project_from_path(self, filepath, add_to_recent=True):
        """
        指定されたパスのプロジェクト(.graphica または .pkl)を読み込み、UIを再構築する。
        manual_load (ファイルダイアログ経由)、最近使ったファイル一覧からの
        再オープン、オートセーブからの復元の、いずれからも呼ばれる共通処理。

        Args:
            add_to_recent (bool): 「最近使ったファイル」一覧に追加するかどうか。
                オートセーブファイルはユーザーが明示的に選んだ項目ではないため、
                復元時はFalseにして一覧を汚さないようにする。
        """
        try:
            # 1. Modelにデータを読み込ませる
            self.project.load_project(filepath)

            # 2. 復元されたModelの状態に合わせてUIを再構築
            # (フォルダ構造も含めて dataset_group_tree からツリーを再構築する)
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
            self._block_all_signals(False)

            # UIにアクティブな設定を反映
            if self.project.all_plot_settings:
                self._apply_settings_to_ui_controls(
                    self.project.all_plot_settings[self.project.active_axis_index]
                )

            # 画面状態とプロットの最終更新
            self._update_ui_state()
            self._update_plot()

            self.statusBar().showMessage("プロジェクトを読み込みました", 3000)
            if add_to_recent:
                self._add_recent_file(filepath)
            self.project_state_changed.emit()
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"読み込みに失敗しました:\n{e}")

    def _update_plot(self):
        """グラフ全体を再描画する（MVC対応版）"""
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
        is_secondary_visible_global = self.canvas.redraw_all(
            self.project.datasets, rows, cols, self.project.all_plot_settings, layout_mode=layout_mode
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

    def _update_plot_appearance(self):
        """外観のみを更新する（MVC対応版）"""
        # 外観の更新もCanvasに丸投げ
        self.canvas.update_appearance_only(self.project.all_plot_settings)

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

        wrapper_layout.addWidget(toggle_button)
        wrapper_layout.addWidget(group_box)
        return wrapper

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
        container_layout.setSpacing(4)

        search_edit = QLineEdit(container)
        search_edit.setPlaceholderText("データセットを検索...")
        search_edit.setClearButtonEnabled(True)
        container_layout.addWidget(search_edit)

        tree = QTreeWidget(container)
        tree.setObjectName("dataset_list_widget")
        tree.setHeaderHidden(True)
        tree.setColumnCount(1)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # ★ GUI洗練: gridLayout_2の行stretchを0にした(キャンバスへ余白を譲る)ため、
        #   このリストはsizeHint任せだと窮屈すぎる高さまで縮む可能性がある。
        #   データが2〜3件程度でも下に大きな空白ができない程度の高さを確保する。
        tree.setMinimumHeight(90)
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
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            self.load_data(file_path)  # 直接読み込みメソッドを呼ぶ

    def load_data(self, file_path):
        """
        ファイルをバックグラウンドスレッドで読み込み、既存のDataset(Model)とUIに反映させる。
        大きなCSV/Excelファイルでも、読み込み中にUIがフリーズしないようにするため、
        実際のファイルI/O (gui/workers.py の DataLoadWorker) は別スレッドで実行する。
        """
        if self._data_load_worker is not None:
            QMessageBox.information(self, "読み込み中", "他のファイルを読み込み中です。完了までお待ちください。")
            return

        self.ui.add_dataset_button.setEnabled(False)
        self.statusBar().showMessage(f"読み込み中: {file_path} ...")

        worker = DataLoadWorker(file_path, self)
        worker.load_succeeded.connect(self._on_data_load_succeeded)
        worker.load_failed.connect(self._on_data_load_failed)
        self._data_load_worker = worker
        worker.start()

    def _on_data_load_succeeded(self, df, file_path):
        """
        DataLoadWorker がファイル読み込みに成功したときに呼ばれるスロット。
        複数シートを持つExcelファイルの場合、シートを複数選択すると
        シートごとに別々のデータセットとして追加できる(未選択/単一選択の場合は
        従来通り1ファイル=1データセットの読み込みフローになる)。
        """
        self._cleanup_data_load_worker()

        dataset_name = os.path.basename(file_path)
        is_excel = file_path.lower().endswith(('.xlsx', '.xls'))

        sheet_names = []
        if is_excel:
            try:
                sheet_names = pd.ExcelFile(file_path).sheet_names
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
                    sheet_df = pd.read_excel(file_path, sheet_name=sheet_name)
                except Exception as e:
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

            new_dataset = Dataset(name=preview_name, df=final_df, x_col_name=x_col, y_col_name=y_col)
            self._add_dataset(new_dataset, target_folder)
            added_count += 1

        if added_count > 0:
            self.statusBar().showMessage(f"読み込み完了: {file_path} ({added_count}件)", 3000)
            self._add_recent_file(file_path)
        else:
            self.statusBar().showMessage("読み込みをキャンセルしました", 3000)

    def _on_paste_data_from_clipboard(self):
        """
        「クリップボードから貼り付け」メニューの処理。
        Excel/スプレッドシートでコピーしたセル範囲は、クリップボードに
        タブ区切りテキストとして格納されるため、それをそのままpandasで解釈し、
        新しいデータセットとして追加する。
        """
        text = QApplication.clipboard().text()
        if not text.strip():
            QMessageBox.information(self, "クリップボードから貼り付け", "クリップボードにテキストデータがありません。")
            return

        try:
            df = pd.read_csv(io.StringIO(text), sep='\t', engine='python')
        except Exception as e:
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
        """DataLoadWorker がファイル読み込みに失敗したときに呼ばれるスロット"""
        self._cleanup_data_load_worker()
        self.statusBar().clearMessage()
        QMessageBox.critical(self, "エラー", f"読み込みエラー: {error_message}")

    def _cleanup_data_load_worker(self):
        """読み込み完了/失敗後の後片付け(UIの再有効化とワーカーの破棄)"""
        self.ui.add_dataset_button.setEnabled(True)
        if self._data_load_worker is not None:
            self._data_load_worker.wait()
            self._data_load_worker.deleteLater()
            self._data_load_worker = None

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
            self._load_project_from_path(file_path)
        else:
            self.load_data(file_path)

    def _on_clear_recent_files(self):
        """「履歴をクリア」がクリックされたときの処理"""
        self.settings.setValue("recent_files", [])
        self._update_recent_files_menu()
