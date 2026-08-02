import os
import re
import types
import sys
import logging
import numpy as np

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
CONTROL_DOCK_WIDTH = 350
CONTROL_DOCK_INITIAL_HEIGHT = 700
PROPERTIES_DOCK_INITIAL_HEIGHT = 300
SPIN_BOX_MAX_DECIMALS = 16

# --- オートセーブに関する定数 ---
DEFAULT_AUTOSAVE_INTERVAL_MIN = 5  # 分単位 (0 = 無効化)
MIN_AUTOSAVE_INTERVAL_MIN = 0
MAX_AUTOSAVE_INTERVAL_MIN = 180
AUTOSAVE_FILENAME = "autosave.pkl"

# --- 最近使ったファイル一覧に関する定数 ---
MAX_RECENT_FILES = 10

# --- PySide6 ---
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QFileDialog,
                               QComboBox, QLabel, QSpinBox, QDoubleSpinBox, QPushButton,
                               QTextEdit, QCheckBox, QGroupBox, QSizePolicy,
                               QStyle, QDockWidget, QScrollArea, QMessageBox,
                               QLineEdit, QHBoxLayout, QFormLayout, QAbstractItemView,
                               QDialog, QTreeWidget, QTreeWidgetItem, QGridLayout,
                               QInputDialog, QMenu)
from PySide6.QtGui import QFont, QIcon, QAction, QValidator, QUndoStack
from PySide6.QtCore import Qt, QTimer, QSettings
from models.project import ProjectModel
from core.version import APP_NAME, __version__

# --- Matplotlib ---
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

# --- Qt Designer から生成された UI ---
# ※ main_window.py と同じ階層ではなく大元のフォルダにあるため、そのままインポートできます
from ui_main_window import Ui_MainWindow

# --- 自分で分割したモジュール ---
from core.dataset import Dataset
from gui.canvas import MplCanvas
from gui.workers import DataLoadWorker
from gui.dialogs import ColumnPreviewDialog

# --- 責務ごとに分割した Mixin (God Object 化を避けるための構成) ---
from gui.mixins.ui_setup_mixin import UISetupMixin
from gui.mixins.settings_mixin import SettingsMixin
from gui.mixins.dataset_mixin import DatasetMixin
from gui.mixins.cursor_mixin import CursorMixin
from gui.mixins.export_mixin import ExportMixin
from gui.mixins.project_io_mixin import ProjectIOMixin
from gui.mixins.help_mixin import HelpMixin


def resource_path(relative_path):
    """ .exe化された場合に、一時フォルダ内のリソースへの絶対パスを取得する """
    try:
        # PyInstaller が作成する一時フォルダ
        base_path = sys._MEIPASS
    except Exception:
        # .py での実行時（通常のパス）
        base_path = os.path.abspath(".")

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
                  CursorMixin, ExportMixin, ProjectIOMixin, HelpMixin):
    """
    メインアプリケーションウィンドウクラス。
    QMainWindow を継承し、ui_main_window.py からロードしたUI骨格に、
    MplCanvas (グラフ) や動的なコントロールUIを組み込みます。
    """

    def __init__(self):
        """
        アプリケーションの初期化 (コンストラクタ)。
        UIのロード、状態変数の初期化、動的UIの構築、シグナル接続を行います。
        """
        super().__init__()

        # --- 1. UIファイルのロード ---
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # ★ データセットリストを QListWidget から QTreeWidget に置き換える。
        #   フォルダによるグループ分けに対応するため (Designerが生成する
        #   dataset_list_widget は QListWidget なので、実行時に同じ位置へ差し替える)。
        self._replace_dataset_list_with_tree()

        self.project = ProjectModel()
        # アプリの設定 (オートセーブ間隔、最近使ったファイル一覧) を永続化するためのストレージ
        self.settings = QSettings("Graphica", "Graphica")
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        icon_path = resource_path("Graphica.ico")
        self.setWindowIcon(QIcon(icon_path))
        # Designer で作成したドックウィジェット (右側のパネル) をメインウィンドウに追加
        self.ui.control_dock_widget.setWindowTitle("プロットのプロパティ")
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.ui.control_dock_widget)

        # --- 2. 状態変数の初期化 ---
        self.data_editor_dialog = None # データエディタ (非モーダル) のインスタンス保持用
        self.help_dialog = None        # mathtextヘルプ (非モーダル) のインスタンス保持用
        self.calc_help_dialog = None   # 列計算ヘルプ (非モーダル) のインスタンス保持用
        self.fit_result_dialog = None  # 曲線フィット結果 (非モーダル) のインスタンス保持用
        self.peak_result_dialog = None # ピーク検出結果 (非モーダル) のインスタンス保持用
        self._data_load_worker = None  # ファイル読み込み用バックグラウンドワーカーの保持用

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

        # --- デフォルトの書式設定 (これらが all_plot_settings[0] の初期値になる) ---
        self._tick_font = QFont() # デフォルトフォント
        self._tick_color = '#000000' # 黒
        self._tick_width = 0.8
        self._axis_label_font = QFont()
        self._axis_label_color = '#000000'
        self._spine_width = 1.0
        self._spine_color = '#000000'
        self._legend_font = QFont()
        self._legend_color = '#000000'

        # --- 3. ウィンドウサイズとレイアウトの基本設定 ---
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.ui.control_dock_widget.setFixedWidth(CONTROL_DOCK_WIDTH) # 右側パネルの幅を固定


        # --- 4. Matplotlib キャンバスとツールバーの組み込み ---

        # MplCanvas (グラフ描画領域) を作成
        self.canvas = MplCanvas(self, width=5, height=4, dpi=100)
        # ダークモード設定を復元 (QApplication側の配色は _create_menu_bar で適用する)
        self.canvas.dark_mode = self.settings.value("dark_mode", False, type=bool)
        # Matplotlib 標準のナビゲーションツールバーを作成
        toolbar = NavigationToolbar(self.canvas, self)

        # --- ★ ツールバーにカスタムボタン (データカーソル) を追加 ★ ---
        toolbar.addSeparator()
        # 1. Action (ボタンの動作定義) を作成
        cursor_action = QAction(
            # 標準アイコン (SP_ArrowRight: ->) を使用
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight),
            "データカーソル", # ツールチップ
            self # 親ウィジェット
        )
        # 2. Action をチェック可能 (トグルボタン) にする
        cursor_action.setCheckable(True)
        # 3. Action がトリガーされたら (checked の bool 値と共に) スロットに接続
        cursor_action.triggered.connect(self._toggle_cursor_mode)
        # 4. Action をツールバーに追加
        toolbar.addAction(cursor_action)

        # Designer で用意した plot_container (おそらく QWidget) にレイアウトを作成
        plot_layout = QVBoxLayout(self.ui.plot_container)
        plot_layout.addWidget(toolbar) # 上部にツールバー
        plot_layout.addWidget(self.canvas) # 下部にキャンバス

        # --- 5. ステータスバーの設定 ---
        self.coordinate_label = QLabel("X= ---, Y= ---")
        # addPermanentWidget で、ステータスバーの右側に常時表示
        self.ui.statusbar.addPermanentWidget(self.coordinate_label)


        # --- 6. UIの「動的構築」 (Designer で定義されていないUIをコードで追加) ---

        # 1. 「プロット複製」「データ編集」ボタンをコードで作成
        self.duplicate_dataset_button = QPushButton("プロット複製")
        self.view_edit_data_button = QPushButton("データ表示/編集")
        self.fit_curve_button = QPushButton("曲線フィット")
        self.find_peaks_button = QPushButton("ピーク検出")
        self.auto_color_button = QPushButton("自動配色")  # 選択中の(複数可)データセットに配色を自動割り当て
        self.new_folder_button = QPushButton("新しいフォルダ")  # データセットのグループ分け用フォルダを作成
        # Designer 上の既存のレイアウト (horizontalLayout_3) に追加
        self.ui.horizontalLayout_3.addWidget(self.duplicate_dataset_button)
        self.ui.horizontalLayout_3.addWidget(self.view_edit_data_button)
        self.ui.horizontalLayout_3.addWidget(self.fit_curve_button)
        self.ui.horizontalLayout_3.addWidget(self.find_peaks_button)
        self.ui.horizontalLayout_3.addWidget(self.auto_color_button)
        self.ui.horizontalLayout_3.addWidget(self.new_folder_button)

        # 2. X/Y軸 列選択コンボボックスをコードで作成
        self.x_col_combo = QComboBox()
        self.y_col_combo = QComboBox()
        # Designer 上の既存のフォームレイアウト (formLayout_4) に挿入
        # (insertRow(1,...) を2回呼ぶと、2つ目が1行目、1つ目が2行目になる)
        self.ui.formLayout_4.insertRow(1, "Y軸の列:", self.y_col_combo)
        self.ui.formLayout_4.insertRow(1, "X軸の列:", self.x_col_combo)

        # 2b. エラーバー用の誤差列選択コンボボックス ("(なし)" を選ぶとエラーバー非表示)
        self.x_err_col_combo = QComboBox()
        self.y_err_col_combo = QComboBox()
        self.ui.formLayout_4.insertRow(3, "Y誤差列:", self.y_err_col_combo)
        self.ui.formLayout_4.insertRow(3, "X誤差列:", self.x_err_col_combo)

        # 2c. 透明度(アルファ)スピンボックスを追加 (0.0=完全に透明 ～ 1.0=不透明)
        self.alpha_label = QLabel("透明度:")
        self.alpha_spinbox = QDoubleSpinBox()
        self.alpha_spinbox.setRange(0.0, 1.0)
        self.alpha_spinbox.setSingleStep(0.05)
        self.alpha_spinbox.setDecimals(2)
        self.alpha_spinbox.setValue(1.0)
        self.ui.formLayout_4.insertRow(5, self.alpha_label, self.alpha_spinbox)

        # 3. 凡例の位置を選択するUIをコードで作成
        self.legend_loc_label = QLabel("凡例の位置:")
        self.legend_loc_combo = QComboBox()
        self.legend_loc_combo.addItems([
            "best", "upper right", "upper left", "lower left", "lower right", "center"
        ])
        # Designer 上の既存のフォームレイアウト (formLayout_3) の7行目に挿入
        self.ui.formLayout_3.insertRow(7, self.legend_loc_label, self.legend_loc_combo)

        # (凡例フォント・色ボタンも同様に追加)
        self.legend_font_label = QLabel("凡例フォント:")
        self.legend_font_button = QPushButton("フォント選択...")
        self.ui.formLayout_3.insertRow(8, self.legend_font_label, self.legend_font_button)

        self.legend_color_label = QLabel("凡例 文字色:")
        self.legend_color_button = QPushButton("色選択...")
        self.ui.formLayout_3.insertRow(9, self.legend_color_label, self.legend_color_button)

        # 4. フィット情報表示用のUI (非表示で) 追加
        self.fit_info_label = QLabel("フィット情報:")
        self.fit_info_textedit = QTextEdit()
        self.fit_info_textedit.setReadOnly(True)
        self.fit_info_textedit.setFixedHeight(100) # 高さを固定
        self.ui.formLayout_4.addRow(self.fit_info_label, self.fit_info_textedit)

        # 5. 第2Y軸チェックボックスを追加
        self.use_secondary_y_checkbox = QCheckBox("第2Y軸 (右側) を使用")
        self.ui.formLayout_4.addRow(self.use_secondary_y_checkbox)

        # 6. 第2Y軸ラベル用のUI (非表示で) 追加
        self.y2_label_text_label = QLabel("第2Y軸ラベル:")
        self.y2_label_text_edit = QLineEdit()
        self.ui.formLayout_3.insertRow(3, self.y2_label_text_label, self.y2_label_text_edit)

        # 7. 目盛り方向UIを追加
        self.tick_direction_label = QLabel("主軸目盛(主/補助):")
        self.major_tick_direction_combo = QComboBox()
        self.major_tick_direction_combo.addItems(["out", "in", "inout"])
        self.minor_tick_direction_combo = QComboBox()
        self.minor_tick_direction_combo.addItems(["out", "in", "inout"])
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.major_tick_direction_combo)
        dir_layout.addWidget(self.minor_tick_direction_combo)

        self.tick_direction_y2_label = QLabel("第2軸目盛(主/補助):")
        self.major_tick_direction_y2_combo = QComboBox()
        self.major_tick_direction_y2_combo.addItems(["out", "in", "inout"])
        self.minor_tick_direction_y2_combo = QComboBox()
        self.minor_tick_direction_y2_combo.addItems(["out", "in", "inout"])
        dir_y2_layout = QHBoxLayout()
        dir_y2_layout.addWidget(self.major_tick_direction_y2_combo)
        dir_y2_layout.addWidget(self.minor_tick_direction_y2_combo)

        self.ui.formLayout_3.insertRow(5, self.tick_direction_label, dir_layout)
        self.ui.formLayout_3.insertRow(6, self.tick_direction_y2_label, dir_y2_layout)

        # --- 7. UIの「動的リファクタリング」 (Designer のUI構造をコードで変更) ---

        # 1. 「描画先」コンボボックスを "プロパティ" 欄に追加
        self.subplot_target_label = QLabel("描画先プロット:")
        self.subplot_target_combo = QComboBox()
        self.ui.formLayout_4.addRow(self.subplot_target_label, self.subplot_target_combo)

        # 2. ★ Designer 上の「プロパティ」グループボックスを、
        #    新しい「タブ付きドックウィジェット」に移動させる
        self.properties_dock_widget = QDockWidget("データセットのプロパティ", self)
        self.properties_dock_widget.setObjectName("PropertiesDockWidget")

        # 3. ★ self.ui.properties_groupbox を、元の親から切り離し、
        #    新しいドックウィジェット (properties_dock_widget) の子に設定
        self.properties_dock_widget.setWidget(self.ui.properties_groupbox)

        # 4. 新しいドックウィジェットを、メインウィンドウの右側
        #    (元の control_dock_widget と同じ場所) に追加
        #    -> これにより、2つのドックが「タブ」として表示される
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock_widget)

        # --- Control Dock の中身を ScrollArea に入れる ---
        original_control_widget = self.ui.control_dock_widget.widget()
        if original_control_widget:
             control_scroll_area = QScrollArea()
             control_scroll_area.setWidgetResizable(True)
             control_scroll_area.setWidget(original_control_widget)
             self.ui.control_dock_widget.setWidget(control_scroll_area)
        else:
             logger.warning("control_dock_widget の中身が見つかりません。")

        # --- Properties Dock の中身を ScrollArea に入れる ---
        original_properties_widget = self.properties_dock_widget.widget()
        if original_properties_widget:
             properties_scroll_area = QScrollArea()
             properties_scroll_area.setWidgetResizable(True)
             properties_scroll_area.setWidget(original_properties_widget)
             self.properties_dock_widget.setWidget(properties_scroll_area)
        else:
             logger.warning("properties_dock_widget の中身が見つかりません。")

        # 5. ★ 「ラベル/書式」タブのレイアウトを「手術」する
        #    (サブプロット設定用のUIを先頭に挿入するため)
        layout_group = QGroupBox("グラフ全体レイアウト")
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
        layout_form.addRow("行数:", self.subplot_rows_spinbox)
        layout_form.addRow("列数:", self.subplot_cols_spinbox)
        layout_group.setLayout(layout_form)

        active_axis_group = QGroupBox("編集対象のプロット")
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
        self.ui.dataset_list_widget.setMaximumHeight(200)
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

        try:
            self.resizeDocks(
                [self.ui.control_dock_widget, self.properties_dock_widget], # 上側のドック, 下側のドック
                [CONTROL_DOCK_INITIAL_HEIGHT, PROPERTIES_DOCK_INITIAL_HEIGHT], # 各ドックの初期の高さ (合計値に意味はない、比率が重要)
                Qt.Orientation.Vertical # 高さを指定するため Vertical
            )
        except Exception as e:
            logger.warning("resizeDocks に失敗しました: %s", e)

        self.setAcceptDrops(True)

    def auto_save(self):
        """タイマーから定期的に呼ばれるオートセーブ処理"""
        try:
            self.project.dataset_group_tree = self._capture_dataset_group_tree()
            self.project.save_project(AUTOSAVE_FILENAME)
            self.statusBar().showMessage("オートセーブ完了", 3000)
        except Exception as e:
            logger.error("オートセーブに失敗しました: %s", e)
            self.statusBar().showMessage(f"オートセーブ失敗: {e}", 3000)

    def manual_save(self):
        """ユーザーが保存操作をしたときの処理"""
        filepath, _ = QFileDialog.getSaveFileName(self, "プロジェクトを保存", "", "Project Files (*.pkl)")
        if filepath:
            try:
                # フォルダ構造(現在のツリーの状態)を保存直前にキャプチャする
                self.project.dataset_group_tree = self._capture_dataset_group_tree()
                self.project.save_project(filepath)
                self.statusBar().showMessage(f"保存しました: {filepath}", 3000)
                self._add_recent_file(filepath)
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{e}")

    def manual_load(self):
        """ユーザーが読み込み操作をしたときの処理"""
        filepath, _ = QFileDialog.getOpenFileName(self, "プロジェクトを開く", "", "Project Files (*.pkl)")
        if filepath:
            self._load_project_from_path(filepath)

    def _load_project_from_path(self, filepath):
        """
        指定されたパスの プロジェクト(.pkl) を読み込み、UIを再構築する。
        manual_load (ファイルダイアログ経由) と、最近使ったファイル一覧からの
        再オープンの両方から呼ばれる共通処理。
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
            self._add_recent_file(filepath)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"読み込みに失敗しました:\n{e}")

    def _update_plot(self):
        """グラフ全体を再描画する（MVC対応版）"""
        rows = self.subplot_rows_spinbox.value()
        cols = self.subplot_cols_spinbox.value()

        if rows * cols == 0:
            return

        # ★ 描画処理をすべてCanvasに「丸投げ」する！
        is_secondary_visible_global = self.canvas.redraw_all(
            self.project.datasets, rows, cols, self.project.all_plot_settings
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

    def _update_plot_appearance(self):
        """外観のみを更新する（MVC対応版）"""
        # 外観の更新もCanvasに丸投げ
        self.canvas.update_appearance_only(self.project.all_plot_settings)

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
        同じレイアウト位置に QTreeWidget を差し込むことで置き換える。
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

        tree = QTreeWidget(parent_widget)
        tree.setObjectName("dataset_list_widget")
        tree.setHeaderHidden(True)
        tree.setColumnCount(1)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        if isinstance(parent_layout, QGridLayout) and row is not None:
            parent_layout.addWidget(tree, row, col, rowspan, colspan)
        else:
            parent_layout.addWidget(tree)

        self.ui.dataset_list_widget = tree

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
        # データセット自身はフォルダではないので、ドロップ先にはしない
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
        if parent_item is not None:
            parent_item.addChild(item)
        else:
            self.ui.dataset_list_widget.addTopLevelItem(item)
        return item

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
        """DataLoadWorker がファイル読み込みに成功したときに呼ばれるスロット"""
        self._cleanup_data_load_worker()

        dataset_name = os.path.basename(file_path)

        # ★ 列数の多いファイルで意図しない列が自動選択されるのを防ぐため、
        #   プレビューを見せつつX/Y軸の列をユーザーに選ばせる。
        preview_dialog = ColumnPreviewDialog(df, dataset_name, self)
        if preview_dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("読み込みをキャンセルしました", 3000)
            return
        x_col, y_col = preview_dialog.get_selected_columns()

        # 既存の Dataset オブジェクトを作成
        new_dataset = Dataset(name=dataset_name,
                              df=df,
                              x_col_name=x_col,
                              y_col_name=y_col)

        # リストに追加してUIリストを更新
        # ★ フォルダが選択中であれば、その中に追加する
        current_item = self.ui.dataset_list_widget.currentItem()
        target_folder = current_item if (current_item is not None and
                                          current_item.data(0, Qt.ItemDataRole.UserRole) is None) else None
        self.project.datasets.append(new_dataset)
        new_item = self._add_dataset_list_item(new_dataset, target_folder)

        # ★ 追加したアイテムを選択状態にする（これによって既存の _update_ui_state が連動して動く）
        self.ui.dataset_list_widget.setCurrentItem(new_item)

        # 既存の描画ロジックを呼び出す
        self._update_plot()

        self.statusBar().showMessage(f"読み込み完了: {file_path}", 3000)
        self._add_recent_file(file_path)

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
    # プロジェクト(.pkl)とデータファイル(csv/xlsx等)の両方をまとめて履歴管理する。
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

        if file_path.lower().endswith('.pkl'):
            self._load_project_from_path(file_path)
        else:
            self.load_data(file_path)

    def _on_clear_recent_files(self):
        """「履歴をクリア」がクリックされたときの処理"""
        self.settings.setValue("recent_files", [])
        self._update_recent_files_menu()
