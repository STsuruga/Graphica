"""タブ(PlotterApp)の中の骨組み: 左端の帯 | 左パネル | 今の中央(グラフ)。右のプロパティはドックのまま。"""
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from graphica.core.i18n import tr
from graphica.gui.shell.dataset_page import LEFT_PANEL_WIDTH, DatasetPage
from graphica.gui.shell.rail import ActivityRail


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
    app._left_panel_pages = {"datasets": app.dataset_page}

    app.activity_rail.add_page("datasets", "database", tr("データセット"))
    app.activity_rail.page_requested.connect(
        lambda key: app.left_panel.setCurrentWidget(app._left_panel_pages[key]))
    app.activity_rail.add_bottom_button(
        "moon", tr("ダークモード"), lambda: app.dark_mode_action.trigger())
    app.activity_rail.add_bottom_button(
        "settings", tr("環境設定"), lambda: app._on_show_preferences())

    shell = QWidget()
    shell.setObjectName("tab_shell")
    layout = QHBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(app.activity_rail)
    layout.addWidget(app.left_panel)
    layout.addWidget(old_central, 1)
    app.setCentralWidget(shell)
