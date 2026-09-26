"""キャンバス・ツールバー・ミニマップ・ステータスバーの組み立て。"""
import logging
from PySide6.QtCore import QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout
from graphica.core.i18n import tr
from graphica.gui import app_settings, theme
from graphica.gui.builders.common import TOOLBAR_ICON_SIZE, _svg_icon
from graphica.gui.canvas import MplCanvas
from graphica.gui.minimap_widget import MinimapWidget
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

logger = logging.getLogger(__name__)


def build_canvas_and_toolbar(app):
    app.canvas = MplCanvas(app, width=5, height=4, dpi=100)
    app.canvas.dark_mode = app_settings.DARK_MODE.read(app.settings)
    # アイコンは作るときにテーマの色を焼き込むので、アイコンを作り始める前にテーマを当てる
    # (当てないと、ダークモードで起動したときツールバーのアイコンがライト用の色になって見えない)
    theme.apply_theme(QApplication.instance(), app.canvas.dark_mode)
    app.canvas.point_label_max_points = app_settings.POINT_LABEL_MAX_POINTS.read(app.settings)
    toolbar = NavigationToolbar(app.canvas, app)
    # matplotlib のツールバーはアイコンの明暗を作ったときに一度だけ決めるので、
    # ダークモードの切り替え(_on_toggle_dark_mode)で作り直せるよう持っておく
    app.mpl_toolbar = toolbar
    # 普通のレイアウトに入れたツールバーは、幅が足りないとボタンが小さな「>>」に押し込まれて見つからない。
    # アイコンを小さくしてはみ出しにくくする
    toolbar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
    app._localize_navigation_toolbar(toolbar)

    # マウス操作のモード。互いに排他にするため、アクションは属性で持つ(mouse_mode_mixin の表から操作する)
    toolbar.addSeparator()
    app.cursor_action = QAction(
        _svg_icon("pointer"),
        tr("データカーソル"),
        app
    )
    app.cursor_action.setCheckable(True)
    app.cursor_action.triggered.connect(app._toggle_cursor_mode)
    toolbar.addAction(app.cursor_action)

    app.annotation_action = QAction(
        _svg_icon("message-2"),
        tr("注釈 (クリック:テキスト / ドラッグ:矢印 / 右クリック:削除)"),
        app
    )
    app.annotation_action.setCheckable(True)
    app.annotation_action.triggered.connect(app._toggle_annotation_mode)
    toolbar.addAction(app.annotation_action)

    # 自由配置レイアウトのときだけ使える
    app.layout_edit_action = QAction(
        _svg_icon("layout-grid"),
        tr("レイアウト編集 (自由配置レイアウト時のみ: ドラッグでプロットを移動/リサイズ)"),
        app
    )
    app.layout_edit_action.setCheckable(True)
    app.layout_edit_action.setEnabled(False)
    app.layout_edit_action.triggered.connect(app._toggle_layout_edit_mode)
    toolbar.addAction(app.layout_edit_action)

    app.range_select_action = QAction(
        _svg_icon("select-all"),
        tr("範囲選択 (ドラッグした範囲のカレントデータセットをマスク)"),
        app
    )
    app.range_select_action.setCheckable(True)
    app.range_select_action.triggered.connect(app._toggle_range_select_mode)
    toolbar.addAction(app.range_select_action)

    app.peak_placement_action = QAction(
        _svg_icon("mountain"),  # ピーク検出ボタンと同じ
        tr("ピーク配置 (クリックで多峰分離フィットの初期値を追加、右クリックで削除)"),
        app
    )
    app.peak_placement_action.setCheckable(True)
    app.peak_placement_action.triggered.connect(app._toggle_peak_placement_mode)
    toolbar.addAction(app.peak_placement_action)

    app.slice_extraction_action = QAction(
        _svg_icon("chart-line"),
        tr("スライス抽出 (2Dマップ上でドラッグした線分に沿って1Dデータを抽出)"),
        app
    )
    app.slice_extraction_action.setCheckable(True)
    app.slice_extraction_action.triggered.connect(app._toggle_slice_extraction_mode)
    toolbar.addAction(app.slice_extraction_action)

    app.region_highlight_action = QAction(
        _svg_icon("highlight"),
        tr("領域ハイライト (横ドラッグ:縦帯 / 縦ドラッグ:横帯 / 右クリック:削除)"),
        app
    )
    app.region_highlight_action.setCheckable(True)
    app.region_highlight_action.triggered.connect(app._toggle_region_highlight_mode)
    toolbar.addAction(app.region_highlight_action)

    app.reset_zoom_action = QAction(
        _svg_icon("refresh"),
        tr("表示をリセット (拡大/パンを元に戻す)"),
        app
    )
    app.reset_zoom_action.triggered.connect(app._reset_zoom)
    toolbar.addAction(app.reset_zoom_action)

    # 統計情報のボタンは stats_summary_label を作った後(_build_fit_info_and_stats)で足す

    # キャンバスの周りに余白と区切り線を置いて、右のパネルとの境目をはっきりさせる
    app.ui.plot_container.setObjectName("plot_container")
    plot_layout = QVBoxLayout(app.ui.plot_container)
    plot_layout.setContentsMargins(6, 6, 6, 6)
    plot_layout.setSpacing(6)
    plot_layout.addWidget(toolbar)

    canvas_separator = QFrame()
    canvas_separator.setFrameShape(QFrame.Shape.HLine)
    canvas_separator.setObjectName("canvas_separator")
    plot_layout.addWidget(canvas_separator)

    plot_layout.addWidget(app.canvas)

    # キャンバスを別ウィンドウへ切り離したあと、元の位置に戻せるようにする
    # (この後に足すミニマップはキャンバスより後ろなので、この位置は変わらない)
    app._plot_layout = plot_layout
    app._canvas_layout_index = plot_layout.indexOf(app.canvas)
    app._canvas_detach_window = None
    app.canvas_detached = False

    # グラフの下の小さな全体図。ドラッグで全部の軸の X の範囲を絞る。区切り線は canvas_separator のスタイルを使う
    app.minimap_separator = QFrame()
    app.minimap_separator.setFrameShape(QFrame.Shape.HLine)
    app.minimap_separator.setObjectName("canvas_separator")
    plot_layout.addWidget(app.minimap_separator)

    app.minimap = MinimapWidget(app)
    app.minimap.range_selected.connect(app._on_minimap_range_selected)
    plot_layout.addWidget(app.minimap)

    app.minimap_visible = app_settings.MINIMAP_VISIBLE.read(app.settings)
    app.minimap.setVisible(app.minimap_visible)
    app.minimap_separator.setVisible(app.minimap_visible)


def setup_status_bar(app):
    app.coordinate_label = QLabel("X= ---, Y= ---")
    app.ui.statusbar.addPermanentWidget(app.coordinate_label)


def localize_navigation_toolbar(app, toolbar):
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
