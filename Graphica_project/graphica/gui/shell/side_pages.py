"""左パネルの「解析」「注釈」「レイアウト」「プラグイン」のページ。

まずは今の操作を節ごとのボタンの並びで出す(GUI 刷新の決定 6。中身の作り込みは刷新の後)。押したときの動きは
メニューやボタンと同じ(同じ QAction か、同じメソッドを呼ぶ)。
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QComboBox, QLabel, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from graphica.core.i18n import tr
from graphica.gui.datasets.operations.processing import PROCESSING_OPERATIONS
from graphica.gui.shell.dataset_page import LEFT_PANEL_WIDTH


class ActionListPage(QWidget):
    """見出しと、節ごとのボタンの並び。"""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("side_page")
        self.setFixedWidth(LEFT_PANEL_WIDTH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        heading = QLabel(tr(title))
        heading.setObjectName("panel_title")
        heading.setFixedHeight(52)
        heading.setContentsMargins(14, 0, 0, 0)
        outer.addWidget(heading)
        scroll = QScrollArea()
        scroll.setObjectName("side_page_scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("side_page_body")
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(8, 0, 8, 12)
        self._body.setSpacing(2)
        self._body.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.rows = []

    def _insert(self, widget):
        self._body.insertWidget(self._body.count() - 1, widget)

    def add_section(self, title):
        label = QLabel(tr(title))
        label.setObjectName("side_page_section")
        self._insert(label)
        return label

    def _row_button(self):
        # QToolButton は文字を左に寄せられない(QSS の text-align が効かない)ので QPushButton にする
        button = QPushButton()
        button.setObjectName("side_page_row")
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setFixedHeight(32)
        return button

    def add_action(self, action, text):
        """メニューと同じ QAction の行。チェックの状態と有効・無効はメニューと一緒に変わる。

        行の文字は短い名前にする(ツールバーの QAction の文字は説明を兼ねて長いので、それはツールチップに出す)。
        """
        button = self._row_button()
        button.setText(tr(text))
        button.setCheckable(action.isCheckable())
        button.action = action

        def sync():
            button.setEnabled(action.isEnabled())
            button.setChecked(action.isChecked())
            button.setToolTip(action.text().replace("&", ""))
            button.setIcon(action.icon())

        action.changed.connect(sync)
        action.toggled.connect(lambda _checked: sync())
        # 押すとボタンのチェックが先に変わるので、QAction の側で決め直す(trigger が反転させる)
        button.clicked.connect(lambda _checked=False: (action.trigger(), sync()))
        sync()
        self._insert(button)
        self.rows.append(button)
        return button

    def add_command(self, text, slot):
        button = self._row_button()
        button.setText(tr(text))
        button.clicked.connect(lambda _checked=False: slot())
        self._insert(button)
        self.rows.append(button)
        return button

    def row_texts(self):
        return [button.text().replace("&", "") for button in self.rows]


# 解析のページのデータ処理(PROCESSING_OPERATIONS のキー。よく使うものだけ。全部はデータセットのメニューにある)
ANALYSIS_PROCESSING_KEYS = ("normalize", "savgol_smooth", "baseline_correction", "interval_integral",
                            "cumulative_integral", "resample", "detect_outliers")


def build_analysis_page(app):
    page = ActionListPage("解析")
    page.add_section("フィット")
    page.add_command("曲線フィット...", app.fitting.fit_current_dataset)
    page.add_command("一括フィット...", app.fitting.batch_fit_selected)
    page.add_command("多峰フィット...", app.fitting.multi_peak_fit_current_dataset)
    page.add_command("フィット結果を表示", app.fitting.show_fit_result)
    page.add_section("ピーク")
    page.add_command("ピーク検出...", app.peaks.find_peaks)
    page.add_command("ピークにラベルを付ける", app.peaks.add_peak_labels)
    page.add_section("データ処理")
    for key in ANALYSIS_PROCESSING_KEYS:
        # ProcessingController のメソッドは、ここに挙げたキーと同じ名前
        page.add_command(tr(PROCESSING_OPERATIONS[key].title) + "...", getattr(app.processing, key))
    return page


def populate_side_pages(app):
    """解析・注釈・レイアウトのページを作って左パネルに足す。メニューの QAction を使うので、メニューを作った後に呼ぶ。"""
    for key, builder in (("analysis", build_analysis_page), ("notes", build_notes_page),
                         ("layout", build_layout_page)):
        page = builder(app)
        app.left_panel.addWidget(page)
        app._left_panel_pages[key] = page


def build_notes_page(app):
    page = ActionListPage("注釈")
    page.add_section("グラフに描く")
    page.add_action(app.annotation_action, "注釈")
    page.add_action(app.region_highlight_action, "領域ハイライト")
    page.add_action(app.range_select_action, "範囲選択")
    page.add_section("表示")
    page.add_action(app.panel_labels_action, "パネルラベルを自動表示")
    return page


def build_layout_page(app):
    page = ActionListPage("レイアウト")
    page.add_section("配置")
    page.add_action(app.layout_edit_action, "レイアウト編集(自由配置のとき)")
    page.add_command("サブプロットの数・並び(軸の設定)", lambda: _open_axis_settings(app))
    page.add_section("表示")
    page.add_action(app.minimap_action, "ミニマップ")
    page.add_action(app.canvas_detach_action, "キャンバスを別ウィンドウに切り離す")
    return page


def _open_axis_settings(app):
    """サブプロットの行と列は、右のプロパティの「プロットのプロパティ」にある。そこを見せる。"""
    app.properties_dock_widget.show()
    app.properties_dock_widget.raise_()


class PluginPage(QWidget):
    """プラグインが register_panel で登録したパネル。上で選び、下に1つずつ出す。"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setObjectName("side_page")
        self.setFixedWidth(LEFT_PANEL_WIDTH)
        self._app = app
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        heading = QLabel(tr("プラグイン"))
        heading.setObjectName("panel_title")
        heading.setFixedHeight(52)
        heading.setContentsMargins(14, 0, 0, 0)
        layout.addWidget(heading)
        self.selector = QComboBox()
        self.selector.setObjectName("plugin_panel_selector")
        self.selector.currentIndexChanged.connect(self._on_selected)
        selector_row = QVBoxLayout()
        selector_row.setContentsMargins(12, 0, 12, 8)
        selector_row.addWidget(self.selector)
        layout.addLayout(selector_row)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(14, 8, 14, 8)
        message = QLabel(tr("プラグインのパネルはありません。プラグインは環境設定から追加できます。"))
        message.setObjectName("side_page_note")
        message.setWordWrap(True)
        manage = QPushButton(tr("環境設定を開く..."))
        manage.clicked.connect(lambda _checked=False: app._on_show_preferences())
        empty_layout.addWidget(message)
        empty_layout.addWidget(manage, 0, Qt.AlignmentFlag.AlignLeft)
        empty_layout.addStretch(1)
        self.stack.addWidget(self.empty)
        self.panels = {}
        self._refresh_selector()

    def add_panel(self, name, widget):
        self.panels[name] = widget
        self.stack.addWidget(widget)
        self.selector.addItem(name)
        self._refresh_selector()

    def show_panel(self, name):
        index = self.selector.findText(name)
        if index >= 0:
            self.selector.setCurrentIndex(index)

    def _refresh_selector(self):
        # 1つだけなら選ぶ欄は要らない
        self.selector.setVisible(len(self.panels) > 1)
        if not self.panels:
            self.stack.setCurrentWidget(self.empty)
        elif self.selector.currentIndex() < 0:
            self.selector.setCurrentIndex(0)
        else:
            self._on_selected(self.selector.currentIndex())

    def _on_selected(self, index):
        if index < 0:
            return
        widget = self.panels.get(self.selector.itemText(index))
        if widget is not None:
            self.stack.setCurrentWidget(widget)
