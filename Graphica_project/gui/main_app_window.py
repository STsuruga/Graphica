# gui/main_app_window.py
"""
複数プロジェクトのタブ化(項目40)。

アプリケーションの実際の最上位ウィンドウ。中央に QTabWidget を持ち、
各タブには完全に独立した PlotterApp インスタンス(自身のUndoスタック・
データセット一覧・キャンバス・メニューバー・ドック配置などをすべて
個別に持つ、それ自体が元々の単独アプリと同じQMainWindow)を埋め込む。

「完全に独立」であることを保証するため、既存の PlotterApp / 各Mixin の
実装には一切手を加えず(すべて self.xxx のインスタンス属性を前提とした
コードのまま)、QMainWindowを子ウィジェットとして埋め込めるというQtの
性質をそのまま利用している。共有すべきでない状態(オートセーブ復元確認・
初回起動ウェルカム・ウィンドウのドック配置の永続化・clean_exitフラグ)は
最初のタブだけが担当するよう PlotterApp 側に run_startup_checks フラグを
渡して制御し、オートセーブファイル名はタブごとに重複しないようにしている。
"""
import logging

from PySide6.QtCore import Qt, QSettings, QSize
from PySide6.QtGui import QIcon, QUndoGroup
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QToolButton, QMessageBox, QDockWidget,
                               QUndoView, QWidget, QHBoxLayout)

from gui.main_window import PlotterApp, resource_path
from gui.app_context import AppContext
from gui.icon_utils import icon as svg_icon
from core.version import APP_NAME, __version__

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_WIDTH = 1300
DEFAULT_WINDOW_HEIGHT = 850


class MainAppWindow(QMainWindow):
    """複数の PlotterApp インスタンスをタブとして保持する最上位ウィンドウ。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        icon_path = resource_path("Graphica.ico")
        self.setWindowIcon(QIcon(icon_path))

        # ★ ウィンドウ全体のサイズ・位置(項目56)は、複数タブ化に伴い
        # このクラスが最上位ウィンドウの責務を持つようになったため、ここで管理する。
        self._settings = QSettings("Graphica", "Graphica")

        # タブをまたいで共有されるグローバル状態(QSettings/最近使ったファイル/
        # プラグインレジストリ)の集約点(項目C-006)。プロセスにつき1つ、
        # ここで生成して以後使い回す。
        self.app_context = AppContext(self)

        # タブ横断のUndo一元化(項目C-007)。各タブ(PlotterApp)は従来通り
        # 自分自身の QUndoStack を持ち続ける(PlotterApp側は無改修)が、
        # ここでそれらをQUndoGroupに登録し、タブ切り替え時に
        # setActiveStack()でアクティブなスタックを追従させる。
        # Undo履歴パネル(項目C-901、下のQUndoView)はこのグループ経由で
        # 常にアクティブなタブの履歴を表示する。
        self.undo_group = QUndoGroup(self)
        self._create_undo_history_dock()

        self._next_tab_id = 1

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self.tab_widget)

        # タブバー右端の「+」ボタン (新しいプロジェクトタブを開く)
        # ★ GUI洗練: プレーンな文字ボタンではなく、他のツールバー類と同じ
        #   Tabler Iconsのトーンに揃えたアイコンボタンにする。
        add_tab_button = QToolButton()
        add_tab_button.setObjectName("add_tab_button")
        add_tab_button.setIcon(svg_icon("file-plus", size=18))
        add_tab_button.setIconSize(QSize(18, 18))
        add_tab_button.setToolTip("新しいプロジェクトタブを開く")
        add_tab_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_tab_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_tab_button.clicked.connect(lambda: self.add_new_project_tab())

        # Undo履歴パネルの表示/非表示切り替えボタン(項目C-901)。専用アイコンの
        # 手持ちが無いため(assets/icons/参照、外部から新規調達するほどでもない
        # ため)、他の低頻度操作ボタン(dataset_overflow_button の "⋯")と同じ
        # 方針でテキストボタンにする。
        undo_history_button = QToolButton()
        undo_history_button.setObjectName("undo_history_button")
        undo_history_button.setText("履歴")
        undo_history_button.setToolTip("Undo履歴パネルの表示/非表示")
        undo_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        undo_history_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        undo_history_button.setCheckable(True)
        undo_history_button.setDefaultAction(self.undo_history_dock.toggleViewAction())

        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(2)
        corner_layout.addWidget(undo_history_button)
        corner_layout.addWidget(add_tab_button)
        self.tab_widget.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

        saved_geometry = self._settings.value("window_geometry")
        if saved_geometry is not None:
            # ★ バグ修正: restoreGeometry() を show() より前(=ウィンドウがまだ
            #   一度もOSに実体化されていない段階)で呼ぶと、Windowsのウィンドウ枠
            #   (タイトルバー等)の実寸がまだ確定しておらず、Qtが不正確な枠幅を
            #   前提にジオメトリを復元してしまう。この結果、ウィンドウ自身の画面
            #   上の位置についてQtが持つ内部認識が実際とズレたままになり、以降
            #   ポップアップ位置・クリック判定・matplotlibのマウス座標など、
            #   画面座標変換を伴うものすべてが一律にズレて見える不具合が起きていた
            #   (最大化はこの枠幅計算に依存しない別経路のため影響を受けない)。
            #   winId() でネイティブウィンドウハンドルだけを先に生成させることで、
            #   画面に表示せずに正確な枠幅をQtに確定させてから復元する。
            self.winId()
            self.restoreGeometry(saved_geometry)
        else:
            self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        # 起動時は必ず1つ、最初のタブ(従来通りのオートセーブ復元確認・
        # ウェルカム表示・ドック配置復元を行う「本体」)を開く。
        self.add_new_project_tab(run_startup_checks=True)

    def _create_undo_history_dock(self):
        """
        Undo履歴パネル(項目C-901)。QUndoGroupに登録された、現在アクティブな
        タブのUndoスタックの操作履歴をQUndoView(Qt標準ウィジェット)で
        リスト表示する。タブが切り替わると _on_current_tab_changed が
        undo_group.setActiveStack() を呼ぶため、表示内容も自動的に追従する。
        既定では非表示(必要な人だけ「履歴」ボタンで開く低頻度機能のため)。
        """
        self.undo_history_dock = QDockWidget("Undo履歴", self)
        self.undo_history_dock.setObjectName("undo_history_dock")
        undo_view = QUndoView(self.undo_group, self.undo_history_dock)
        self.undo_history_dock.setWidget(undo_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.undo_history_dock)
        self.undo_history_dock.setVisible(False)

    def add_new_project_tab(self, run_startup_checks=False):
        """新しいプロジェクトタブ(独立した PlotterApp インスタンス)を開く。"""
        tab_id = self._next_tab_id
        self._next_tab_id += 1

        project_window = PlotterApp(
            run_startup_checks=run_startup_checks,
            tab_id=(None if run_startup_checks else tab_id),
        )
        # QMainWindow を子ウィジェットとして埋め込む際、既定のウィンドウフラグのままだと
        # 最上位ウィンドウとして扱われてしまうことがあるため、明示的に通常ウィジェット化する。
        project_window.setWindowFlags(Qt.WindowType.Widget)
        project_window.project_state_changed.connect(
            lambda pw=project_window: self._refresh_tab_title(pw)
        )

        # タブ横断Undo一元化(項目C-007): このタブ自身のQUndoStack(既存の
        # project_window.undo_stack、PlotterApp側は無改修)をグループに登録する。
        self.undo_group.addStack(project_window.undo_stack)

        index = self.tab_widget.addTab(project_window, self._tab_title_for(project_window))
        self.tab_widget.setCurrentIndex(index)
        project_window.show()
        return project_window

    def _tab_title_for(self, project_window):
        """プロジェクトの現在のファイルパスから、タブに表示する短いタイトルを作る。"""
        import os
        filepath = project_window.project.current_filepath
        if filepath:
            return os.path.basename(filepath)
        return "無題のプロジェクト"

    def _refresh_tab_title(self, project_window):
        index = self.tab_widget.indexOf(project_window)
        if index != -1:
            self.tab_widget.setTabText(index, self._tab_title_for(project_window))

    def _on_current_tab_changed(self, index):
        if index == -1:
            return
        project_window = self.tab_widget.widget(index)
        if project_window is not None:
            self.setWindowTitle(f"{APP_NAME} {__version__} - {self._tab_title_for(project_window)}")
            # タブ横断Undo一元化(項目C-007): アクティブなタブのスタックに
            # 追従させる。Undo履歴パネル(QUndoView)もこれを通じて連動する。
            self.undo_group.setActiveStack(project_window.undo_stack)

    def _on_tab_close_requested(self, index):
        """タブの「×」ボタンが押されたときの処理。タブを1つも無くすことはできない。"""
        if self.tab_widget.count() <= 1:
            QMessageBox.information(
                self, "タブを閉じる", "最後の1つのタブは閉じられません。"
            )
            return

        project_window = self.tab_widget.widget(index)
        self.tab_widget.removeTab(index)
        if project_window is not None:
            # タブ横断Undo一元化(項目C-007): 閉じるタブのスタックをグループから
            # 明示的に外す(project_window.deleteLater()によるQt側の自動的な
            # 後始末に頼らず、閉じた直後からQUndoView/undo_groupの対象に
            # 残らないようにするため)。
            self.undo_group.removeStack(project_window.undo_stack)
            project_window.close()
            project_window.deleteLater()

    def closeEvent(self, event):
        """アプリ全体が閉じられるとき、開いている全タブに正常終了処理をさせてから閉じる。"""
        self._settings.setValue("window_geometry", self.saveGeometry())
        for index in range(self.tab_widget.count()):
            project_window = self.tab_widget.widget(index)
            if project_window is not None:
                project_window.close()
        super().closeEvent(event)
