"""最上位のウィンドウ。各タブは独立した PlotterApp(QMainWindow)で、Undo もメニューもドックも別々に持つ。

アプリ全体で1回だけの処理(オートセーブの復元確認、初回の案内、ドック配置の保存、clean_exit)は最初のタブだけが行う。
上部バー(gui/shell/header.py)はここに1つだけ置き、押したときは表示中のタブに届ける。
"""
import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QUndoGroup
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMenu, QUndoView, QVBoxLayout, QWidget

from graphica.core.i18n import tr
from graphica.gui import app_settings, theme, ui_mode
from graphica.gui import motion
from graphica.gui.theme_color import theme_color_or_default
from graphica.gui.main_window import PlotterApp, resource_path
from graphica.gui.shell.header import AppHeader
from graphica.gui.shell.project_tabs import ProjectTabs
from graphica.core.version import APP_NAME, __version__
from graphica.models.project import LEGACY_PICKLE_EXTENSION, PROJECT_FILE_EXTENSIONS

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
        motion.set_enabled(app_settings.ANIMATIONS.read(self._settings))
        # 最初のタブがスタートアップ画面を見たことにする前に決める(今までの利用者はアドバンスドで始める)
        self.ui_mode = ui_mode.initial_mode(self._settings)

        # 各タブは自分の QUndoStack を持ち、ここでグループにまとめて、表示中のタブのものを有効にする
        # (履歴パネルと上部バーの元に戻す・やり直すは、グループを通して表示中のタブに効く)
        self.undo_group = QUndoGroup(self)
        self._create_undo_history_dock()
        # 履歴パネルはこのウィンドウのドックなので、タブとは別にここでもフォーカスの強調を付ける
        theme.install_dock_focus_highlight(self)

        self._next_tab_id = 1
        self._tab_menus = {}  # タブ -> ≡ で開くメニュー(回収されないよう持つ)

        self.tab_widget = ProjectTabs()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)

        self.header = AppHeader(self.tab_widget.tabBar(), icon_path)
        self._connect_header()

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.header)
        central_layout.addWidget(self.tab_widget, 1)
        self.setCentralWidget(central)

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

    @property
    def add_tab_button(self):
        return self.header.add_tab_button

    def _create_undo_history_dock(self):
        """表示中のタブの Undo 履歴(既定では隠す)。"""
        self.undo_history_dock = QDockWidget(tr("Undo履歴"), self)
        self.undo_history_dock.setObjectName("undo_history_dock")
        undo_view = QUndoView(self.undo_group, self.undo_history_dock)
        self.undo_history_dock.setWidget(undo_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.undo_history_dock)
        self.undo_history_dock.setVisible(False)
        self.undo_history_action = self.undo_history_dock.toggleViewAction()
        self.undo_history_action.setText(tr("Undo履歴"))

    def _connect_header(self):
        header = self.header
        header.add_tab_button.clicked.connect(lambda: self.add_new_project_tab())
        self._undo_action = self.undo_group.createUndoAction(self, tr("元に戻す"))
        self._redo_action = self.undo_group.createRedoAction(self, tr("やり直し"))
        for button, action in ((header.undo_button, self._undo_action), (header.redo_button, self._redo_action)):
            icon = button.icon()
            button.setDefaultAction(action)
            # setDefaultAction() はボタンのアイコンを QAction のもので上書きするので、戻す
            action.setIcon(icon)
        header.save_button.clicked.connect(lambda: self._trigger_on_current_tab("save_project_action"))
        header.export_button.clicked.connect(lambda: self._trigger_on_current_tab("save_action"))
        header.search_button.clicked.connect(lambda: self._trigger_on_current_tab("command_palette_action"))
        header.quick_access_menu.aboutToShow.connect(self._fill_quick_access_menu)
        header.set_mode(self.ui_mode)
        header.mode_switch.mode_changed.connect(self.set_ui_mode)

    def _fill_quick_access_menu(self):
        """★ の一覧: 表示中のタブのピン留め(ピン留めした順)と、管理の項目。"""
        menu = self.header.quick_access_menu
        menu.clear()
        tab = self.tab_widget.currentWidget()
        if tab is None:
            return
        pinned = [action for action in tab.quick_access_toolbar.actions() if not action.isSeparator()
                  and action is not tab.quick_access_manage_action]
        for action in pinned:
            menu.addAction(action)
        if not pinned:
            hint = menu.addAction(tr("ピン留めした項目はありません(メニューの項目を右クリックで追加)"))
            hint.setEnabled(False)
        menu.addSeparator()
        menu.addAction(tab.quick_access_manage_action)

    def _trigger_on_current_tab(self, action_attr):
        tab = self.tab_widget.currentWidget()
        action = getattr(tab, action_attr, None) if tab is not None else None
        if action is not None:
            action.trigger()

    def set_theme_color(self, color):
        """テーマカラーを替えて保存し、全部のタブと上部バーに当てる(QSS とパレットはアプリ全体、アイコンや図はタブごと)。"""
        color = theme_color_or_default(color)
        app_settings.THEME_COLOR.write(self._settings, color)
        current = self.tab_widget.currentWidget()
        dark = current.canvas.dark_mode if current is not None else app_settings.DARK_MODE.read(self._settings)
        theme.apply_theme(QApplication.instance(), dark, color)
        for index in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(index)
            if tab is not None and hasattr(tab, 'refresh_theme_colors'):
                tab.refresh_theme_colors()
        self.header.refresh_icons()

    def set_ui_mode(self, mode):
        """シンプル / アドバンスドを全部のタブに当て、次の起動のために保存する。"""
        if mode not in ui_mode.MODES:
            return
        self.ui_mode = mode
        app_settings.UI_MODE.write(self._settings, mode)
        self.header.set_mode(mode)
        for index in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(index)
            if tab is not None:
                ui_mode.apply_ui_mode(tab, mode)

    def _attach_tab_chrome(self, project_window):
        """タブを上部バーにつなぐ: ≡ のメニュー、ショートカット、クイックアクセス、モード、アイコンの色。"""
        menu = QMenu(self.header)
        # 最上位のメニューは、組み立て時に持たせた属性から取る(menuBar().actions() から .menu() で辿ると回収されることがある)
        for attr in ("_file_menu", "_edit_menu", "_dataset_menu", "_view_menu", "_plugin_menu", "_help_menu"):
            top_menu = getattr(project_window, attr, None)
            if top_menu is not None:
                menu.addMenu(top_menu)
        menu.addSeparator()
        menu.addAction(project_window.quick_access_manage_action)
        menu.addAction(self.undo_history_action)
        self._tab_menus[project_window] = menu

        if sys.platform != "darwin":
            # Windows では上部バーの ≡ にまとめる(macOS は画面上のメニューバーのまま)。メニューバーを隠すと
            # そこにしか無い QAction のショートカットが効かなくなるので、全部をタブにも足す
            project_window.menuBar().hide()
            project_window.addActions([action for _path, action in project_window._collect_menu_actions()
                                       if not action.shortcut().isEmpty()])

        # クイックアクセスのツールバーは画面に出さず、ピン留めの並びを持つだけにする(上部バーの ★ が一覧で出す)
        toolbar = project_window.quick_access_toolbar
        project_window.removeToolBar(toolbar)
        toolbar.hide()

        ui_mode.apply_ui_mode(project_window, self.ui_mode)
        project_window.dark_mode_action.toggled.connect(lambda _checked: self.header.refresh_icons())

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
        self._attach_tab_chrome(project_window)

        # 埋め込んだ QMainWindow は最上位ウィンドウのフラグが残るので外す。親を確定させてから1回だけ変える
        # (変更と付け替えの2段階にすると、macOS でタブが入力を受け付けなくなる)
        index = self.tab_widget.addTab(project_window, self._tab_title_for(project_window))
        project_window.setWindowFlags(Qt.WindowType.Widget)
        self.tab_widget.setCurrentIndex(index)
        project_window.show()
        return project_window

    def open_files(self, paths, reuse_empty_tab=False):
        """外から渡されたファイル(起動の引数・起動中のアプリへの受け渡し・macOS の Finder)を開く。

        プロジェクトは 1 つずつ新しいタブに開き、データファイルは最後に開いたタブ(無ければ新しいタブ)に加える。
        reuse_empty_tab なら、今のタブが空で未保存の変更も無いときだけ最初のプロジェクトをそこに開く(起動直後)。
        """
        project_suffixes = PROJECT_FILE_EXTENSIONS + (LEGACY_PICKLE_EXTENSION,)
        project_paths = [p for p in paths if p.lower().endswith(project_suffixes)]
        data_paths = [p for p in paths if not p.lower().endswith(project_suffixes)]

        target = None
        current = self.tab_widget.currentWidget()
        if reuse_empty_tab and current is not None and not current.project.datasets \
                and not current.has_unsaved_changes():
            target = current
        for index, path in enumerate(project_paths):
            if target is None or index > 0:
                target = self.add_new_project_tab()
            target._load_project_from_path(path)
        if data_paths:
            if target is None:
                target = current if reuse_empty_tab and current is not None else self.add_new_project_tab()
            target._queue_data_files(data_paths)
        self.bring_to_front()

    def bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

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
            menu = self._tab_menus.get(project_window)
            if menu is not None:
                self.header.menu_button.setMenu(menu)

    def _on_tab_close_requested(self, index):
        """最後の1つを閉じたら、空のプロジェクトのタブに置き換えてスタートアップ画面を出す。

        タブが無くなる時はつくらない(メニューは各タブが持つので、0枚だと何もできなくなる)。
        """
        project_window = self.tab_widget.widget(index)
        if project_window is not None and not project_window.confirm_unsaved_changes("タブを閉じる"):
            return
        replacement = self.add_new_project_tab() if self.tab_widget.count() <= 1 else None
        self.tab_widget.removeTab(self.tab_widget.indexOf(project_window))
        if project_window is not None:
            # 閉じた直後から履歴パネルの対象に残らないよう、明示的に外す
            self.undo_group.removeStack(project_window.undo_stack)
            self._tab_menus.pop(project_window, None)
            project_window.close()
            project_window.deleteLater()
        if replacement is not None:
            replacement._show_welcome_dialog(last_tab_closed=True)

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
