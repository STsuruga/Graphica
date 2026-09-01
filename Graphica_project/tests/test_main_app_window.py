# tests/test_main_app_window.py
"""
gui/main_app_window.py (MainAppWindow) に対する回帰テスト。
主にタブ横断Undo一元化(項目C-007)とUndo履歴パネル(項目C-901)を対象とする。

MainAppWindowは最初のタブを常に run_startup_checks=True で開くため、
オートセーブ復元確認・初回起動ウェルカムダイアログ(いずれもQTimer.singleShot(0, ...)
経由の遅延呼び出し+モーダルexec())が実際に開いてテストをハングさせないよう、
該当ダイアログ/QMessageBox.questionを軽量なフェイクに差し替えてから使う。
"""
from PySide6.QtCore import QSettings
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QApplication, QMessageBox

import gui.main_app_window as main_app_window_module
import gui.main_window as main_window_module
import gui.app_context as app_context_module
from gui.main_app_window import MainAppWindow


def _make_isolated_main_app_window(tmp_path, monkeypatch):
    """
    QSettingsを一時ファイルにリダイレクトし、起動時ダイアログが一切ブロックしない
    状態でMainAppWindowを1つ作る。
    """
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_app_window_module, "QSettings", IsolatedQSettings)
    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    monkeypatch.setattr(app_context_module, "QSettings", IsolatedQSettings)

    # 初回起動ウェルカムダイアログ・オートセーブ復元確認ダイアログは、いずれも
    # QTimer.singleShot(0, ...)経由の遅延呼び出し+モーダルexec()のため、
    # 実際に開いてテストをハングさせないよう安全側に倒す。
    # QMessageBox.information は「最後の1つのタブは閉じられません」の案内
    # (_on_tab_close_requested)で使われるため、同様にモックしておく。
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    class FakeWelcomeDialog:
        def __init__(self, *args, **kwargs):
            self.load_sample_requested = False
            # 項目C-912: 実際のWelcomeDialogはこれらも常に設定するため、
            # _show_welcome_dialog()の分岐(elif dialog.selected_recent_file: 等)が
            # AttributeErrorにならないよう、フェイクでも同じ属性一式を用意する。
            self.selected_recent_file = None
            self.load_template_requested = False

        def exec(self):
            return 0

    monkeypatch.setattr(main_window_module, "WelcomeDialog", FakeWelcomeDialog)

    window = MainAppWindow()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def test_first_tab_stack_is_registered_and_active(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    first_tab = window.tab_widget.widget(0)
    assert window.undo_group.activeStack() is first_tab.undo_stack


def test_adding_second_tab_registers_its_stack_and_makes_it_active(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    second_tab = window.add_new_project_tab()
    assert window.undo_group.activeStack() is second_tab.undo_stack


def test_added_tab_is_correctly_embedded_not_top_level(tmp_path, monkeypatch):
    """
    実機フィードバック(Mac): 「タブを増やしたときに増やしたタブが何も
    操作できない」。QMainWindowをタブとして埋め込む際、reparent(addTab)と
    ウィンドウフラグの変更(Qt.WindowType.Widget)の順序次第では、フラグを
    変更してもなお最上位ウィンドウ扱いのまま(またはその逆の中途半端な
    状態)になりうる。ヘッドレス環境(offscreen)では実際のクリック応答性
    までは検証できないが、少なくとも「最終的にisWindow()==Falseかつ
    QTabWidget内部のQStackedWidgetの子になっている」という状態不変条件は
    検証できる。
    """
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    second_tab = window.add_new_project_tab()

    assert second_tab.isWindow() is False
    assert second_tab.parent() is not None
    # 埋め込み後の親をたどるとQTabWidget自身に行き着くはず
    ancestor = second_tab.parent()
    found_tab_widget = False
    while ancestor is not None:
        if ancestor is window.tab_widget:
            found_tab_widget = True
            break
        ancestor = ancestor.parent()
    assert found_tab_widget


def test_toggling_dark_mode_on_one_tab_syncs_sibling_tabs(tmp_path, monkeypatch):
    """
    回帰テスト: 各タブは完全に独立したPlotterAppインスタンスのため、
    片方のタブでダークモードを切り替えても、Qt側の共有QSS/パレット
    (theme.apply_theme、プロセス全体に効く)はすぐ反映されるのに対し、
    他のタブのmatplotlib配色・ツールバーアイコン・「ダークモード」
    メニューのチェック状態は古いまま取り残される「二重人格」状態に
    なっていた。トリガーしたタブ以外にも同じ状態が伝播することを確認する。
    """
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    first_tab = window.tab_widget.widget(0)
    second_tab = window.add_new_project_tab()

    assert first_tab.canvas.dark_mode is False
    assert second_tab.canvas.dark_mode is False

    first_tab.dark_mode_action.setChecked(True)

    assert first_tab.canvas.dark_mode is True
    assert second_tab.canvas.dark_mode is True
    assert second_tab.dark_mode_action.isChecked() is True

    # 元に戻す方向の伝播も確認する。
    first_tab.dark_mode_action.setChecked(False)
    assert second_tab.canvas.dark_mode is False
    assert second_tab.dark_mode_action.isChecked() is False


def test_switching_tabs_follows_active_stack(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    first_tab = window.tab_widget.widget(0)
    window.add_new_project_tab()  # 2番目のタブがアクティブになる

    window.tab_widget.setCurrentIndex(0)
    assert window.undo_group.activeStack() is first_tab.undo_stack

    window.tab_widget.setCurrentIndex(1)
    second_tab = window.tab_widget.widget(1)
    assert window.undo_group.activeStack() is second_tab.undo_stack


def test_undo_group_only_undoes_the_active_tabs_command(tmp_path, monkeypatch):
    """タブ横断で1つのUndo/Redoにまとめても、実際にundo()されるのは
    アクティブなタブのスタックの操作だけであること(タブ間の独立性の回帰確認)。"""
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    first_tab = window.tab_widget.widget(0)
    second_tab = window.add_new_project_tab()

    first_tab.undo_stack.push(QUndoCommand("tab1のコマンド"))
    second_tab.undo_stack.push(QUndoCommand("tab2のコマンド"))

    # 現在アクティブなのはtab2(後から追加・選択されたタブ)
    assert window.undo_group.activeStack() is second_tab.undo_stack
    window.undo_group.undo()
    assert second_tab.undo_stack.canUndo() is False  # tab2の操作が取り消された
    assert first_tab.undo_stack.canUndo() is True    # tab1の操作には影響しない


def test_closing_tab_removes_its_stack_from_undo_group(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    second_tab = window.add_new_project_tab()
    stacks_before = list(window.undo_group.stacks())
    assert second_tab.undo_stack in stacks_before

    window._on_tab_close_requested(1)

    stacks_after = list(window.undo_group.stacks())
    assert second_tab.undo_stack not in stacks_after


def test_last_tab_cannot_be_closed_and_stack_stays_registered(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    first_tab = window.tab_widget.widget(0)
    window._on_tab_close_requested(0)  # 唯一のタブ、閉じられないはず
    assert window.tab_widget.count() == 1
    assert first_tab.undo_stack in list(window.undo_group.stacks())


def test_undo_history_dock_starts_hidden(tmp_path, monkeypatch):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    assert window.undo_history_dock.isVisible() is False


def test_undo_history_dock_toggle_action_shows_it(tmp_path, monkeypatch):
    """
    トップレベルウィンドウ自体を show() していない状態では QDockWidget.isVisible()
    が常にFalseを返す(Qtの仕様、実際に画面に出ているかどうかに依存するため)ので、
    トグルアクション自体のチェック状態(論理的な表示/非表示の意図)で確認する。
    """
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    action = window.undo_history_dock.toggleViewAction()
    assert action.isChecked() is False
    action.trigger()
    assert action.isChecked() is True


def test_undo_history_dock_gets_focus_highlight_installed(tmp_path, monkeypatch):
    """
    undo_history_dockはPlotterApp(各タブ)ではなくMainAppWindow自身が持つ
    ドックのため、項目H-2-3のフォーカス時強調(theme.
    install_dock_focus_highlight())をgui/main_window.py側の呼び出しとは
    別に、MainAppWindow.__init__側でも個別に組み込む必要がある。ここでは
    実際にウィジェットへフォーカスを移し、dockActiveプロパティが立つことで
    組み込み済みであることを確認する。
    """
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    window.undo_history_dock.setVisible(True)
    undo_view = window.undo_history_dock.widget()
    undo_view.setFocus()
    for _ in range(5):
        app.processEvents()

    assert window.undo_history_dock.property("dockActive") is True
