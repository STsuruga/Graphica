"""キャンバス・ツールバー・ミニマップ・ステータスバーの組み立て。"""
import logging
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QToolBar, QToolButton,
                               QVBoxLayout)
from graphica.core.axis_settings import axis_setting
from graphica.core.i18n import tr
from graphica.gui import app_settings, theme
from graphica.gui.builders.common import TOOLBAR_ICON_SIZE, _svg_icon
from graphica.gui.canvas import MplCanvas
from graphica.gui.minimap_widget import MinimapWidget
from graphica.gui.theme_color import theme_color_or_default

logger = logging.getLogger(__name__)


def build_canvas_and_toolbar(app):
    app.canvas = MplCanvas(app, width=5, height=4, dpi=100)
    app.canvas.dark_mode = app_settings.DARK_MODE.read(app.settings)
    # アイコンは作るときにテーマの色を焼き込むので、アイコンを作り始める前にテーマを当てる
    # (当てないと、ダークモードで起動したときツールバーのアイコンがライト用の色になって見えない)
    theme.apply_theme(QApplication.instance(), app.canvas.dark_mode,
                      theme_color_or_default(app_settings.THEME_COLOR.read(app.settings)))
    app.canvas.point_label_max_points = app_settings.POINT_LABEL_MAX_POINTS.read(app.settings)
    # 表示範囲の操作はツールバーではなくマウスで行う(gui/tools/view_navigation.py)ので、matplotlib のツールバーは使わない
    _create_mode_actions(app)
    _build_advanced_toolbar(app)
    _build_lite_tool_rail(app)
    _build_card(app)


# マウスの操作のモード: (属性名, アイコン, 短い名前(ツールバーの文字), 説明(ツールチップ), 切り替えのメソッド)。
# 互いに排他にするため、QAction は属性で持つ(gui/tools/manager.py の表から操作する)
_MODE_ACTIONS = (
    ("cursor_action", "pointer", "カーソル", "データカーソル", "_toggle_cursor_mode"),
    ("annotation_action", "message-2", "注釈", "注釈 (クリック:テキスト / ドラッグ:矢印 / 右クリック:削除)",
     "_toggle_annotation_mode"),
    ("range_select_action", "select-all", "範囲選択", "範囲選択 (ドラッグした範囲のカレントデータセットをマスク)",
     "_toggle_range_select_mode"),
    ("peak_placement_action", "mountain", "ピーク",
     "ピーク配置 (クリックで多峰分離フィットの初期値を追加、右クリックで削除)", "_toggle_peak_placement_mode"),
    ("region_highlight_action", "highlight", "領域",
     "領域ハイライト (横ドラッグ:縦帯 / 縦ドラッグ:横帯 / 右クリック:削除)", "_toggle_region_highlight_mode"),
    ("slice_extraction_action", "chart-line", "スライス",
     "スライス抽出 (2Dマップ上でドラッグした線分に沿って1Dデータを抽出)", "_toggle_slice_extraction_mode"),
    ("layout_edit_action", "layout-grid", "配置",
     "レイアウト編集 (自由配置レイアウト時のみ: ドラッグでプロットを移動/リサイズ)", "_toggle_layout_edit_mode"),
)
# テーマを替えたときにアイコンを作り直す QAction(_refresh_custom_svg_icons)
TOOL_ACTION_ICONS = tuple((entry[0], entry[1]) for entry in _MODE_ACTIONS) + (
    ("reset_zoom_action", "refresh"), ("fit_tool_action", "math-function"), ("smoothing_tool_action", "chart-line"))
# シンプルの縦の道具に出すモード(見本: カーソル・注釈・範囲選択、区切りの下にフィット)
LITE_MODE_ACTIONS = ("cursor_action", "annotation_action", "range_select_action")


def _create_mode_actions(app):
    for attr, icon_name, label, description, toggle in _MODE_ACTIONS:
        action = QAction(_svg_icon(icon_name), tr(label), app)
        action.setToolTip(tr(description))
        action.setCheckable(True)
        action.triggered.connect(getattr(app, toggle))
        setattr(app, attr, action)
    # 自由配置レイアウトのときだけ使える
    app.layout_edit_action.setEnabled(False)

    app.reset_zoom_action = QAction(_svg_icon("refresh"), tr("表示をリセット (拡大/パンを元に戻す)"), app)
    app.reset_zoom_action.triggered.connect(app._reset_zoom)
    app.fit_tool_action = QAction(_svg_icon("math-function"), tr("フィット"), app)
    app.fit_tool_action.setToolTip(tr("曲線フィット..."))
    app.fit_tool_action.triggered.connect(lambda _checked=False: app.fitting.fit_current_dataset())
    app.smoothing_tool_action = QAction(_svg_icon("chart-line"), tr("平滑化"), app)
    app.smoothing_tool_action.setToolTip(tr("Savitzky-Golayフィルタ") + "...")
    app.smoothing_tool_action.triggered.connect(lambda _checked=False: app.processing.savgol_smooth())


def _build_advanced_toolbar(app):
    """アドバンスドの、プロットの上の文字付きの道具。モードの7つは1つの塊に見せる(QSS の toolSegment)。"""
    toolbar = QToolBar(tr("プロット"), app)
    toolbar.setObjectName("plot_toolbar")
    toolbar.setIconSize(QSize(TOOLBAR_ICON_SIZE - 3, TOOLBAR_ICON_SIZE - 3))
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    app.plot_toolbar = toolbar
    attrs = [entry[0] for entry in _MODE_ACTIONS]
    for position, attr in enumerate(attrs):
        action = getattr(app, attr)
        toolbar.addAction(action)
        if position == 0:
            place = "first"
        elif position == len(attrs) - 1:
            place = "last"
        else:
            place = "middle"
        toolbar.widgetForAction(action).setProperty("toolSegment", place)
    toolbar.addSeparator()
    toolbar.addAction(app.fit_tool_action)
    toolbar.addAction(app.smoothing_tool_action)


def _build_lite_tool_rail(app):
    """シンプルの、グラフの左に浮かせた縦の道具(アイコンだけ)。QAction はアドバンスドのものと同じ。"""
    rail = QToolBar(tr("道具"), app)
    rail.setObjectName("plot_tool_rail")
    rail.setOrientation(Qt.Orientation.Vertical)
    rail.setIconSize(QSize(18, 18))
    rail.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    for attr in LITE_MODE_ACTIONS:
        rail.addAction(getattr(app, attr))
    rail.addSeparator()
    rail.addAction(app.fit_tool_action)
    app.plot_tool_rail = rail


def _card_button(icon_name, tooltip):
    button = QToolButton()
    button.setObjectName("card_button")
    button.setToolTip(tooltip)
    button.setIcon(_svg_icon(icon_name))
    button.setProperty("iconName", icon_name)
    button.setIconSize(QSize(17, 17))
    button.setFixedSize(28, 28)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _build_card(app):
    """グラフのカード: タイトルの行、(アドバンスドの道具)、(シンプルの縦の道具 | キャンバスとミニマップ)。"""
    app.ui.plot_container.setObjectName("plot_container")
    card_layout = QVBoxLayout(app.ui.plot_container)
    card_layout.setContentsMargins(14, 10, 14, 10)
    card_layout.setSpacing(6)

    title_row = QHBoxLayout()
    title_row.setSpacing(6)
    app.card_title_label = QLabel()
    app.card_title_label.setObjectName("card_title")
    app.card_series_label = QLabel()
    app.card_series_label.setObjectName("card_meta")
    app.card_subplot_label = QLabel()
    app.card_subplot_label.setObjectName("card_meta")
    app.card_reset_button = _card_button("refresh", app.reset_zoom_action.text())
    app.card_reset_button.clicked.connect(lambda _checked=False: app.reset_zoom_action.trigger())
    # ミニマップと切り離しの QAction はメニューと同じもので、メニューを作った後に finish_card() がつなぐ
    app.card_minimap_button = _card_button("map", tr("ミニマップ"))
    app.card_detach_button = _card_button("external-link", tr("キャンバスを別ウィンドウに切り離す"))
    title_row.addWidget(app.card_title_label)
    title_row.addWidget(app.card_series_label)
    title_row.addStretch(1)
    for widget in (app.card_subplot_label, app.card_reset_button, app.card_minimap_button, app.card_detach_button):
        title_row.addWidget(widget)
    card_layout.addLayout(title_row)
    card_layout.addWidget(app.plot_toolbar)

    body = QHBoxLayout()
    body.setSpacing(10)
    body.addWidget(app.plot_tool_rail, 0, Qt.AlignmentFlag.AlignTop)
    plot_layout = QVBoxLayout()
    plot_layout.setSpacing(6)
    plot_layout.addWidget(app.canvas)
    body.addLayout(plot_layout, 1)
    card_layout.addLayout(body, 1)

    # キャンバスを別ウィンドウへ切り離したあと、元の位置に戻せるようにする
    # (この後に足すミニマップはキャンバスより後ろなので、この位置は変わらない)
    app._plot_layout = plot_layout
    app._canvas_layout_index = plot_layout.indexOf(app.canvas)
    app._canvas_detach_window = None
    app.canvas_detached = False

    # グラフの下の小さな全体図。ドラッグで全部の軸の X の範囲を絞る。区切りは見本どおり線を引かず、すき間だけ
    app.minimap_separator = QFrame()
    app.minimap_separator.setObjectName("canvas_separator")
    app.minimap_separator.setFixedHeight(2)
    plot_layout.addWidget(app.minimap_separator)

    app.minimap = MinimapWidget(app)
    app.minimap.range_selected.connect(app._on_minimap_range_selected)
    plot_layout.addWidget(app.minimap)

    app.minimap_visible = app_settings.MINIMAP_VISIBLE.read(app.settings)
    app.minimap.setVisible(app.minimap_visible)
    app.minimap_separator.setVisible(app.minimap_visible)

    app.canvas.mpl_connect('draw_event', lambda _event: refresh_card_title(app))


def finish_card(app):
    """メニューを作った後に呼ぶ: タイトルの行のボタンを、メニューと同じ QAction につなぐ。"""
    app.card_minimap_button.setCheckable(True)
    app.card_minimap_button.setChecked(app.minimap_action.isChecked())
    app.card_minimap_button.clicked.connect(lambda _checked=False: app.minimap_action.trigger())
    app.minimap_action.toggled.connect(app.card_minimap_button.setChecked)
    app.card_detach_button.clicked.connect(lambda _checked=False: app.canvas_detach_action.trigger())
    refresh_card_title(app)


def refresh_card_title(app):
    """タイトルは選んでいるサブプロットのタイトル(数式の $ は外す)。無ければ「サブプロット N」(決定 8)。"""
    settings_list = getattr(app.project, 'all_plot_settings', None) or []
    index = getattr(app.project, 'active_axis_index', 0) or 0
    settings = settings_list[index] if 0 <= index < len(settings_list) else {}
    title = str(axis_setting(settings, 'title') or '').replace('$', '').strip()
    app.card_title_label.setText(title or tr("サブプロット {n}").format(n=index + 1))
    count = sum(1 for ds in app.project.datasets
                if getattr(ds, 'visible', True) and getattr(ds, 'subplot_target', 0) == index)
    app.card_series_label.setText(tr("{n} 系列").format(n=count))
    total = max(1, len(settings_list))
    app.card_subplot_label.setText(tr("サブプロット {i} / {n}").format(i=index + 1, n=total))


def setup_status_bar(app):
    app.coordinate_label = QLabel("X= ---, Y= ---")
    app.ui.statusbar.addPermanentWidget(app.coordinate_label)

