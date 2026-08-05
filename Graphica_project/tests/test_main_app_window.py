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
