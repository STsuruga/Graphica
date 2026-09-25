"""最上位のウィンドウ。各タブは独立した PlotterApp(QMainWindow)で、Undo もメニューもドックも別々に持つ。

アプリ全体で1回だけの処理(オートセーブの復元確認、初回の案内、ドック配置の保存、clean_exit)は最初のタブだけが行う。
"""
import logging

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QUndoGroup
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QToolButton, QMessageBox, QDockWidget,
                               QUndoView, QWidget, QHBoxLayout)

from graphica.gui import app_settings
from graphica.gui.main_window import PlotterApp, resource_path
from graphica.gui.icon_utils import icon as svg_icon
from graphica.gui import theme
from graphica.core.version import APP_NAME, __version__

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_WIDTH = 1300
DEFAULT_WINDOW_HEIGHT = 850


class MainAppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        icon_path = resource_path("Graphica.ico")
        self.setWindowIcon(QIcon(icon_path))

        # ウィンドウ全体の大きさと位置はここで持つ
        self._settings = app_settings.open_settings()

        # 各タブは自分の QUndoStack を持ち、ここでグループにまとめて、表示中のタブのものを有効にする
        # (履歴パネルはグループを通して表示中のタブの履歴を出す)
        self.undo_group = QUndoGroup(self)
        self._create_undo_history_dock()
        # 履歴パネルはこのウィンドウのドックなので、タブとは別にここでもフォーカスの強調を付ける
        theme.install_dock_focus_highlight(self)

        self._next_tab_id = 1

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self.tab_widget)

        add_tab_button = QToolButton()
        add_tab_button.setObjectName("add_tab_button")
        add_tab_button.setIcon(svg_icon("file-plus", size=18))
        add_tab_button.setIconSize(QSize(18, 18))
        add_tab_button.setToolTip("新しいプロジェクトタブを開く")
        add_tab_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_tab_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_tab_button.clicked.connect(lambda: self.add_new_project_tab())

        # setDefaultAction() はボタンのアイコンとツールチップを QAction のもので上書きするので、先に QAction に設定する
        undo_history_action = self.undo_history_dock.toggleViewAction()
        undo_history_action.setIcon(svg_icon("history", size=18))
        undo_history_action.setToolTip("Undo履歴パネルの表示/非表示")
        undo_history_button = QToolButton()
        undo_history_button.setObjectName("undo_history_button")
        undo_history_button.setIconSize(QSize(18, 18))
        undo_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        undo_history_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        undo_history_button.setCheckable(True)
        undo_history_button.setDefaultAction(undo_history_action)

        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(2)
        corner_layout.addWidget(undo_history_button)
        corner_layout.addWidget(add_tab_button)
        self.tab_widget.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

        saved_geometry = app_settings.WINDOW_GEOMETRY.read(self._settings)
        if saved_geometry is not None:
            # 先にネイティブのハンドルを作る。窓が実体化する前に restoreGeometry() すると枠の幅が確定しておらず、
            # 画面上の位置の認識がずれて、ポップアップやクリックの位置が全部ずれる
            self.winId()
            self.restoreGeometry(saved_geometry)
        else:
            self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        # 最初のタブは起動時の確認をするタブ
        self.add_new_project_tab(run_startup_checks=True)

    def _create_undo_history_dock(self):
        """表示中のタブの Undo 履歴(既定では隠す)。"""
        self.undo_history_dock = QDockWidget("Undo履歴", self)
        self.undo_history_dock.setObjectName("undo_history_dock")
        undo_view = QUndoView(self.undo_group, self.undo_history_dock)
        self.undo_history_dock.setWidget(undo_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.undo_history_dock)
        self.undo_history_dock.setVisible(False)

    def add_new_project_tab(self, run_startup_checks=False):
        tab_id = self._next_tab_id
        self._next_tab_id += 1

        project_window = PlotterApp(
            run_startup_checks=run_startup_checks,
            tab_id=(None if run_startup_checks else tab_id),
        )
        project_window.project_state_changed.connect(
            lambda pw=project_window: self._refresh_tab_title(pw)
        )

        self.undo_group.addStack(project_window.undo_stack)

        # 埋め込んだ QMainWindow は最上位ウィンドウのフラグが残るので外す。親を確定させてから1回だけ変える
        # (変更と付け替えの2段階にすると、macOS でタブが入力を受け付けなくなる)
        index = self.tab_widget.addTab(project_window, self._tab_title_for(project_window))
        project_window.setWindowFlags(Qt.WindowType.Widget)
        self.tab_widget.setCurrentIndex(index)
        project_window.show()
        return project_window

    def _tab_title_for(self, project_window):
        return project_window.document_title()

    def _refresh_tab_title(self, project_window):
        index = self.tab_widget.indexOf(project_window)
        if index != -1:
            self.tab_widget.setTabText(index, self._tab_title_for(project_window))
            if index == self.tab_widget.currentIndex():
                self._update_window_title(project_window)

    def _update_window_title(self, project_window):
        self.setWindowTitle(f"{APP_NAME} {__version__} - {self._tab_title_for(project_window)}")

    def _on_current_tab_changed(self, index):
        if index == -1:
            return
        project_window = self.tab_widget.widget(index)
        if project_window is not None:
            self._update_window_title(project_window)
            self.undo_group.setActiveStack(project_window.undo_stack)

    def _on_tab_close_requested(self, index):
        """最後の1つは閉じられない。"""
        if self.tab_widget.count() <= 1:
            QMessageBox.information(
                self, "タブを閉じる", "最後の1つのタブは閉じられません。"
            )
            return

        project_window = self.tab_widget.widget(index)
        if project_window is not None and not project_window.confirm_unsaved_changes("タブを閉じる"):
            return
        self.tab_widget.removeTab(index)
        if project_window is not None:
            # 閉じた直後から履歴パネルの対象に残らないよう、明示的に外す
            self.undo_group.removeStack(project_window.undo_stack)
            project_window.close()
            project_window.deleteLater()

    def closeEvent(self, event):
        """全部のタブに正常終了の処理をさせてから閉じる。"""
        # 未保存の変更は、そのタブを前に出して尋ねる。全部尋ねてから閉じ始めるので、1つでもキャンセルなら何も閉じない
        for index in range(self.tab_widget.count()):
            project_window = self.tab_widget.widget(index)
            if project_window is None or not project_window.has_unsaved_changes():
                continue
            self.tab_widget.setCurrentIndex(index)
            if not project_window.confirm_unsaved_changes("Graphica を終了する"):
                event.ignore()
                return
        app_settings.WINDOW_GEOMETRY.write(self._settings, self.saveGeometry())
        for index in range(self.tab_widget.count()):
            project_window = self.tab_widget.widget(index)
            if project_window is not None:
                project_window.close()
        super().closeEvent(event)
