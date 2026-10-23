"""タブ(PlotterApp)の中の骨組み: 左端の帯 | 左パネル | 今の中央(グラフ)。右のプロパティはドックのまま。"""
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from graphica.core.i18n import tr
from graphica.gui import motion
from graphica.gui.shell.bottom_panel import build_bottom_panel
from graphica.gui.shell.dataset_page import LEFT_PANEL_WIDTH, DatasetPage
from graphica.gui.shell.rail import ActivityRail
from graphica.gui.shell.settings_popover import toggle_settings_popover
from graphica.gui.shell.side_pages import PluginPage


def build_tab_shell(app):
    """中央の部品を帯と左パネルの右に置き直す。データセットの一覧とボタンは左パネルへ移す。

    データセットの一覧のボタン(_build_dataset_list_buttons)とプロパティのドック(_arrange_property_docks)を
    作った後に呼ぶ。ダークモードの切り替えと設定のボタンは、メニュー(_create_menu_bar)ができてから効く。
    """
    old_central = app.takeCentralWidget()

    app.activity_rail = ActivityRail()
    app.left_panel = QStackedWidget()
    app.left_panel.setObjectName("left_panel")
    app.left_panel.setFixedWidth(LEFT_PANEL_WIDTH)
    app.dataset_page = DatasetPage(app)
    app.left_panel.addWidget(app.dataset_page)
    # プラグインのパネルは、この後 _connect_and_initialize がプラグインを読んでから足す。解析・注釈・レイアウトの
    # ページはメニューの QAction を使うので、メニューを作った後に side_pages.populate_side_pages() が足す
    app.plugin_page = PluginPage(app)
    app.left_panel.addWidget(app.plugin_page)
    app._left_panel_pages = {"datasets": app.dataset_page, "plugins": app.plugin_page}

    for key, icon_name, tooltip in (("datasets", "database", "データセット"), ("analysis", "math-function", "解析"),
                                    ("notes", "message-2", "注釈"), ("plugins", "puzzle", "プラグイン"),
                                    ("layout", "layout-grid", "レイアウト")):
        app.activity_rail.add_page(key, icon_name, tr(tooltip))
    app.activity_rail.page_requested.connect(
        lambda key: _show_left_page(app, key))
    app.activity_rail.add_bottom_button(
        "moon", tr("ダークモード"), lambda: app.dark_mode_action.trigger())
    # ⚙ はテーマカラーのポップアップ(環境設定への入口もその中)
    app.settings_rail_button = app.activity_rail.add_bottom_button(
        "settings", tr("設定"), lambda: toggle_settings_popover(app, app.settings_rail_button))

    # グラフのカードの下のパネル(アドバンスドだけ)。残差・来歴のドックはここのタブになった
    build_bottom_panel(app)

    shell = QWidget()
    shell.setObjectName("tab_shell")
    layout = QHBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(app.activity_rail)
    layout.addWidget(app.left_panel)
    layout.addWidget(old_central, 1)
    app.setCentralWidget(shell)


def _show_left_page(app, key):
    page = app._left_panel_pages[key]
    if app.left_panel.currentWidget() is not page:
        before = motion.grab(app.left_panel)
        app.left_panel.setCurrentWidget(page)
        motion.crossfade(app.left_panel, before)
