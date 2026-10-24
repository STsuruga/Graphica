"""グラフの下のパネル(アドバンスドだけ): データ表・フィット結果・残差・来歴・ログのタブ。

グラフのカードとは仕切り(つまんで高さを変える)で上下に分ける。中身は選んでいるデータセットに合わせて
refresh_bottom_panel() が更新する(プロパティ欄の update_ui_state から)。
"""
import logging
import math
import numbers

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFrame, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QSizePolicy,
    QSplitter, QSplitterHandle, QStackedWidget, QTableView, QToolButton, QVBoxLayout, QWidget)

from graphica.core.i18n import tr
from graphica.gui import motion, theme
from graphica.gui.builders.common import _svg_icon
from graphica.gui.data_table_model import DatasetTableModel, fit_dataset_for, fit_result_for
from graphica.gui.provenance_panel import ProvenancePanel
from graphica.gui.shell.fit_result_view import FitResultView
from graphica.gui.residual_panel import ResidualPanel

BOTTOM_PANEL_HEIGHT = 200
HEADER_HEIGHT = 36
GRIP_HEIGHT = 10
LOG_MAX_LINES = 1000
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# (キー, 表示名, アイコン)。見本の順に、残差(決定 11)をフィット結果の隣へ
BOTTOM_PAGES = (
    ("table", "データ表", "table"),
    ("fit", "フィット結果", "math-function"),
    ("residual", "残差", "chart-dots"),
    ("provenance", "来歴", "history"),
    ("log", "ログ", "terminal-2"),
)


class _GripHandle(QSplitterHandle):
    """仕切りのつまみ: 真ん中に短い横棒(見本の .grip)。"""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.current_tokens()["border_strong"]))
        painter.drawRoundedRect(QRectF((self.width() - 40) / 2, (self.height() - 3) / 2, 40, 3), 1.5, 1.5)
        painter.end()


class CenterSplitter(QSplitter):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setObjectName("center_splitter")
        self.setChildrenCollapsible(False)
        self.setHandleWidth(GRIP_HEIGHT)

    def createHandle(self):
        return _GripHandle(self.orientation(), self)


class BottomPanel(QFrame):
    """角丸のパネル。上にアイコン付きのタブと、右に表示中のデータセットの名前・行数、畳むボタン。"""

    page_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottom_panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QWidget()
        self.header.setObjectName("bottom_panel_header")
        self.header.setFixedHeight(HEADER_HEIGHT)
        self._header_layout = QHBoxLayout(self.header)
        self._header_layout.setContentsMargins(6, 0, 6, 0)
        self._header_layout.setSpacing(2)
        self._tab_end = 0  # タブとバッジを足す位置(右の名前の手前)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(lambda index: self.show_page(self._keys[index]))

        self._header_layout.addStretch(1)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("bottom_panel_meta")
        self._header_layout.addWidget(self.meta_label)
        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("card_button")
        self.collapse_button.setCheckable(True)
        self.collapse_button.setFixedSize(26, 26)
        self.collapse_button.setIconSize(QSize(16, 16))
        self.collapse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.collapse_button.toggled.connect(self.set_collapsed)
        self._header_layout.addWidget(self.collapse_button)
        layout.addWidget(self.header)

        self.stack = QStackedWidget()
        self.stack.setObjectName("bottom_panel_stack")
        layout.addWidget(self.stack, 1)

        self._keys = []
        self._buttons = {}
        self._icons = {}
        self._badges = {}
        self._restore_height = BOTTOM_PANEL_HEIGHT
        self.refresh_icons()

    def add_page(self, key, title, icon_name, widget):
        button = QToolButton()
        button.setObjectName("bottom_tab")
        button.setText(title)
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(14, 14))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        index = len(self._keys)
        self._keys.append(key)
        self._buttons[key] = button
        self._icons[key] = icon_name
        button.setIcon(_svg_icon(icon_name, size=14))
        self._group.addButton(button, index)
        self._header_layout.insertWidget(self._tab_end, button)
        self._tab_end += 1
        badge = QLabel()
        badge.setObjectName("bottom_badge")
        badge.setFixedHeight(18)
        badge.hide()
        self._header_layout.insertWidget(self._tab_end, badge)
        self._tab_end += 1
        self._badges[key] = badge
        self.stack.addWidget(widget)
        if index == 0:
            self.show_page(key)

    def show_page(self, key):
        if key not in self._keys:
            raise KeyError(key)
        index = self._keys.index(key)
        self._buttons[key].setChecked(True)
        if self.stack.currentIndex() != index:
            before = motion.grab(self.stack)
            self.stack.setCurrentIndex(index)
            motion.crossfade(self.stack, before)
            self.page_changed.emit(key)
        self.set_collapsed(False)

    def current_page(self):
        return self._keys[self.stack.currentIndex()] if self._keys else None

    def set_badge(self, key, text, ok=True):
        badge = self._badges[key]
        badge.setText(text)
        badge.setProperty("ok", bool(ok))
        badge.style().unpolish(badge)
        badge.style().polish(badge)
        badge.setVisible(bool(text))

    def badge_text(self, key):
        return self._badges[key].text() if self._badges[key].isVisibleTo(self) else ""

    def set_meta(self, text):
        self.meta_label.setText(text)

    def is_collapsed(self):
        return self.collapse_button.isChecked()

    def set_collapsed(self, collapsed):
        """畳むと見出しの行だけを残し、空いた高さはグラフに回す(仕切りは見出しの高さで止まる)。"""
        if self.collapse_button.isChecked() != collapsed:
            self.collapse_button.setChecked(collapsed)
            return
        collapsed_height = HEADER_HEIGHT + 2
        splitter = self.parentWidget()
        if not isinstance(splitter, QSplitter):
            splitter = None
        own = splitter.sizes()[splitter.indexOf(self)] if splitter is not None else self.height()
        if collapsed and own > collapsed_height:
            # パネルの高さではなく仕切りの持ち分で覚える(見出しだけの高さに縮んだ後でも正しい)
            self._restore_height = own
        self.collapse_button.setIcon(_svg_icon("chevron-right" if collapsed else "chevron-down", size=16))
        self.collapse_button.setToolTip(tr("広げる") if collapsed else tr("畳む"))

        total = sum(splitter.sizes()) if splitter is not None else 0

        def set_panel_height(height):
            height = int(height)
            splitter.setSizes([max(0, total - height), height])

        def finish(resize=True):
            self.stack.setVisible(not collapsed)
            self.setMaximumHeight(collapsed_height if collapsed else 16777215)
            if splitter is not None and resize:
                set_panel_height(collapsed_height if collapsed else self._restore_height)

        if splitter is None:
            finish()
            return
        if not collapsed and own > collapsed_height:
            finish(resize=False)
            return  # 開いたまま(タブを押しただけ)なら、ドラッグで決めた高さを変えない

        # 動かす間は中身を出したまま高さだけ変え、止まってから畳んだ形(見出しだけ)にする
        self.stack.setVisible(True)
        self.setMaximumHeight(16777215)
        target = collapsed_height if collapsed else self._restore_height
        motion.animate_value(self, "_motion_collapse", own, target, set_panel_height, finish, motion.EXPAND_MS,
                             motion.EXPAND_EASING)

    def refresh_icons(self):
        for key, button in self._buttons.items():
            button.setIcon(_svg_icon(self._icons[key], size=14))
        collapsed = self.collapse_button.isChecked()
        self.collapse_button.setIcon(_svg_icon("chevron-right" if collapsed else "chevron-down", size=16))


QUIET_LOGGERS = ("matplotlib.font_manager",)


class _LogEmitter(QObject):
    line = Signal(str)


class _PanelLogHandler(logging.Handler):
    """アプリのログ(graphica.log と同じ行)をパネルに流す。どのスレッドから来ても、シグナルで GUI のスレッドに渡す。"""

    def __init__(self, emitter):
        super().__init__(level=logging.INFO)
        self._emitter = emitter
        self.setFormatter(logging.Formatter(LOG_FORMAT))

    def filter(self, record):
        # OS ごとの日本語フォントの候補を順に探すので、見つからない候補の警告が毎回並ぶ(graphica.log には残す)
        if record.name.startswith(QUIET_LOGGERS) and record.levelno < logging.ERROR:
            return False
        return super().filter(record)

    def emit(self, record):
        try:
            self._emitter.line.emit(self.format(record))
        except RuntimeError:
            # パネルが先に消えた(タブを閉じた直後)
            pass


class LogView(QPlainTextEdit):
    """このウィンドウを開いてからのログ。古い行は LOG_MAX_LINES で捨てる。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottom_log")
        self.setReadOnly(True)
        self.setMaximumBlockCount(LOG_MAX_LINES)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setPlaceholderText(tr("このウィンドウを開いてからのログがここに出ます(全部は graphica.log)。"))
        self._emitter = _LogEmitter(self)
        self._emitter.line.connect(self.appendPlainText)
        self._handler = _PanelLogHandler(self._emitter)
        logging.getLogger().addHandler(self._handler)
        self.destroyed.connect(lambda *_args, handler=self._handler: logging.getLogger().removeHandler(handler))


def _copy_text_of_value(value):
    """コピーする文字。数は丸めずに(表示は桁を詰めている)、欠損は空に。numpy の数も素の数として書く。"""
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real):
        number = float(value)
        return "" if math.isnan(number) else repr(number)
    return "" if value is None else str(value)


def selected_cells_tsv(table):
    """選んだセルを、選んだ範囲の行×列のタブ区切りにする(範囲の中の選んでいないセルは空)。"""
    indexes = table.selectionModel().selectedIndexes()
    if not indexes:
        return ""
    model = table.model()
    selected = {(index.row(), index.column()) for index in indexes}
    rows = sorted({row for row, _column in selected})
    columns = sorted({column for _row, column in selected})
    lines = []
    for row in rows:
        lines.append("\t".join(_copy_text_of_value(model.value(row, column)) if (row, column) in selected else ""
                               for column in columns))
    return "\n".join(lines)


def _build_data_table(app):
    app.data_table_model = DatasetTableModel(app)
    table = QTableView()
    table.setObjectName("bottom_data_table")
    table.setModel(app.data_table_model)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(24)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    # セルを選んで Ctrl+C(右クリックの「コピー」でも)。行・列ごとに選ぶには見出しを押す
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    copy_action = QAction(tr("コピー"), table)
    copy_action.setShortcut(QKeySequence.StandardKey.Copy)
    copy_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
    def copy_cells(_checked=False):
        text = selected_cells_tsv(table)
        if text:
            QGuiApplication.clipboard().setText(text)
            motion.toast(table, tr("コピーしました"))

    copy_action.triggered.connect(copy_cells)
    table.addAction(copy_action)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
    app.data_table_copy_action = copy_action
    table.setShowGrid(False)
    table.setWordWrap(False)
    # 見本どおり列は幅を等分(# だけ細い)。数万行でも重くならないよう、中身から幅を測らない
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setMinimumSectionSize(56)
    header.setHighlightSections(False)

    def _fix_row_number_column():
        if app.data_table_model.columnCount() > 0:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(0, 56)

    app.data_table_model.modelReset.connect(_fix_row_number_column)
    app.data_table = table
    return table


def build_bottom_panel(app):
    """グラフのカード(plot_container)を、カードと下のパネルの仕切りに置き換える。build_tab_shell から呼ぶ。"""
    app.fit_info_textedit.setFrameShape(QFrame.Shape.NoFrame)
    app.residual_panel = ResidualPanel(app)
    app.provenance_panel = ProvenancePanel(app)
    app.bottom_log = LogView()
    for widget in (app.residual_panel, app.provenance_panel):
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    app.fit_result_view = FitResultView(app.fit_info_textedit)
    panel = BottomPanel()
    pages = {"table": _build_data_table(app), "fit": app.fit_result_view, "residual": app.residual_panel,
             "provenance": app.provenance_panel, "log": app.bottom_log}
    for key, title, icon_name in BOTTOM_PAGES:
        panel.add_page(key, tr(title), icon_name, pages[key])
    app.bottom_panel = panel

    card = app.ui.plot_container
    parent_layout = card.parentWidget().layout()
    app.center_splitter = CenterSplitter()
    parent_layout.replaceWidget(card, app.center_splitter)
    app.center_splitter.addWidget(card)
    app.center_splitter.addWidget(panel)
    app.center_splitter.setStretchFactor(0, 1)
    app.center_splitter.setStretchFactor(1, 0)
    app.center_splitter.setSizes([10000, BOTTOM_PANEL_HEIGHT])


def refresh_bottom_panel(app, dataset):
    """表示しているデータセット(None なら空)に合わせて、表・フィット結果・残差・来歴を更新する。"""
    if not hasattr(app, 'bottom_panel'):
        return
    datasets = app.project.datasets
    fit_result = fit_result_for(dataset, datasets)
    app.data_table_model.set_dataset(dataset, fit_result)
    rows = app.data_table_model.rowCount()
    app.bottom_panel.set_meta(tr("{name} · {rows} 行").format(name=dataset.name, rows=rows)
                              if dataset is not None and rows else "")

    fit_dataset = fit_dataset_for(dataset, datasets)
    fit_text = getattr(fit_dataset, 'fit_info', None) or ""
    if app.fit_info_textedit.toPlainText() != fit_text:
        app.fit_info_textedit.setPlainText(fit_text)
    app.fit_result_view.set_result(fit_result)
    r_squared = fit_result.get('r_squared') if fit_result else None
    if isinstance(r_squared, (int, float)) and r_squared == r_squared:
        app.bottom_panel.set_badge("fit", f"R² {r_squared:.3f}")
    else:
        app.bottom_panel.set_badge("fit", "")

    app.residual_panel.refresh(dataset, fit_result, residual_x_label(dataset, fit_result, datasets))
    app.provenance_panel.refresh(dataset, app.project)


def refresh_theme(app):
    """明暗を替えたとき: アイコンと、トークンの色で描いた残差の図を描き直す。"""
    if not hasattr(app, 'bottom_panel'):
        return
    app.bottom_panel.refresh_icons()
    shown = app.property_panel.shown_dataset()
    fit_result = fit_result_for(shown, app.project.datasets)
    app.residual_panel.refresh(shown, fit_result, residual_x_label(shown, fit_result, app.project.datasets))


def residual_x_label(dataset, fit_result, datasets):
    """フィットした元のデータの X の列名(フィットの曲線の列は x_fit なので、元をたどる)。"""
    source_id = fit_result.get('source_dataset_id') if fit_result else None
    source = next((other for other in datasets if source_id and other.dataset_id == source_id), dataset)
    return str(getattr(source, 'x_col_name', None) or "X")


def highlight_table_row(app, dataset, row_number):
    """カーソルで選んだ点の行を、表で薄いアクセントの色にして見える位置まで送る。"""
    if not hasattr(app, 'data_table_model'):
        return
    shown = app.property_panel.shown_dataset()
    row = app.data_table_model.row_for_number(row_number) if dataset is shown else None
    app.data_table_model.set_highlighted_row(row)
    if row is not None:
        app.data_table.scrollTo(app.data_table_model.index(row, 0), QAbstractItemView.ScrollHint.EnsureVisible)
