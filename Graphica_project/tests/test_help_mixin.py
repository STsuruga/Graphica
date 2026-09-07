# tests/test_help_mixin.py
"""
gui/mixins/help_mixin.py の HelpMixin に対するテスト。

PlotterApp のインスタンス化パターンは tests/test_main_window.py の
_make_isolated_plotter_app に倣う (QSettingsを一時ファイルにリダイレクトする)。

AboutDialog/ShortcutsDialog はモーダル(exec())で表示されるため、実際の
イベントループを回さないよう exec() を差し替えてテストする(test_main_window.py の
LabelEditDialog.exec 差し替えと同じパターン)。HelpDialog/CalcHelpDialogは
非モーダル(show())なので差し替えは不要。
"""
import zipfile

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import gui.main_window as main_window_module
import gui.mixins.help_mixin as help_mixin_module
from gui.main_window import PlotterApp
from gui.dialogs import AboutDialog, ShortcutsDialog, HelpDialog, CalcHelpDialog
from core.version import __version__


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


# --- _on_show_about ---

def test_on_show_about_opens_about_dialog_modally(tmp_path, monkeypatch):
    """「このソフトについて」メニューで AboutDialog が生成され、exec()で表示されること"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    calls = []

    def fake_exec(self):
        calls.append(self)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AboutDialog, "exec", fake_exec)
    window._on_show_about()

    assert len(calls) == 1
    assert isinstance(calls[0], AboutDialog)


# --- _on_show_help (非モーダル、既存ダイアログの後始末) ---

def test_on_show_help_creates_nonmodal_help_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.help_dialog is None

    window._on_show_help()
    app = QApplication.instance()
    app.processEvents()

    assert isinstance(window.help_dialog, HelpDialog)


def test_on_show_help_replaces_previously_open_dialog(tmp_path, monkeypatch):
    """既にhelp_dialogが開いている状態でもう一度呼ぶと、古いものを閉じて新しく作り直すこと
    (close()だけではC++オブジェクトが破棄されずリークするため、deleteLater()も呼ばれる)"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    window._on_show_help()
    app = QApplication.instance()
    app.processEvents()
    first_dialog = window.help_dialog
    assert first_dialog is not None

    window._on_show_help()
    app.processEvents()
    second_dialog = window.help_dialog

    assert second_dialog is not None
    assert second_dialog is not first_dialog


# --- _on_show_calc_help ---

def test_on_show_calc_help_creates_nonmodal_calc_help_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.calc_help_dialog is None

    window._on_show_calc_help()
    app = QApplication.instance()
    app.processEvents()

    assert isinstance(window.calc_help_dialog, CalcHelpDialog)


def test_on_show_calc_help_replaces_previously_open_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    window._on_show_calc_help()
    app = QApplication.instance()
    app.processEvents()
    first_dialog = window.calc_help_dialog

    window._on_show_calc_help()
    app.processEvents()
    second_dialog = window.calc_help_dialog

    assert second_dialog is not None
    assert second_dialog is not first_dialog


# --- _on_show_shortcuts ---

def test_on_show_shortcuts_opens_shortcuts_dialog_modally(tmp_path, monkeypatch):
    """「キーボードショートカット一覧」メニューで、現在のメニューアクションを
    収集する _collect_menu_actions を渡した ShortcutsDialog が exec()されること"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    calls = []

    def fake_exec(self):
        calls.append(self)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ShortcutsDialog, "exec", fake_exec)
    window._on_show_shortcuts()

    assert len(calls) == 1
    assert isinstance(calls[0], ShortcutsDialog)


# --- _on_export_diagnostic_bundle ---

def test_on_export_diagnostic_bundle_cancelled_does_nothing(tmp_path, monkeypatch):
    """ファイル保存ダイアログでキャンセルした場合、zipは作られず何も起きないこと"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: ("", "")))

    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_export_diagnostic_bundle()

    assert info_calls == []
    assert list(tmp_path.iterdir()) == []


def test_on_export_diagnostic_bundle_writes_real_zip_and_appends_extension(tmp_path, monkeypatch):
    """保存先パスに拡張子.zipが無い場合は補い、build_diagnostic_bundleを実際に
    走らせて中身のあるzipファイルが書き出されること。完了メッセージも表示されること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    out_path_no_ext = str(tmp_path / "diag_bundle")
    monkeypatch.setattr(help_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (out_path_no_ext, "Zip Files (*.zip)")))

    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_export_diagnostic_bundle()

    expected_path = out_path_no_ext + ".zip"
    import os
    assert os.path.exists(expected_path)
    with zipfile.ZipFile(expected_path) as zf:
        names = zf.namelist()
        assert "environment.txt" in names
        assert "plugins.txt" in names
        assert "settings.txt" in names

    assert len(info_calls) == 1


def test_on_export_diagnostic_bundle_reports_error_on_failure(tmp_path, monkeypatch):
    """build_diagnostic_bundleが例外を送出した場合、警告ダイアログが出てクラッシュしないこと"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    out_path = str(tmp_path / "diag_bundle.zip")
    monkeypatch.setattr(help_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (out_path, "Zip Files (*.zip)")))

    def broken_build(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(help_mixin_module, "build_diagnostic_bundle", broken_build)

    warn_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))
    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_export_diagnostic_bundle()

    assert len(warn_calls) == 1
    assert info_calls == []


# =============================================================================
# アップデート通知(_on_check_for_update / _start_startup_update_check, 項目161、C-1203)
# =============================================================================

def _run_update_check_and_wait(window):
    """TaskRunnerは実スレッドで動くため、start()後にwait()+processEvents()で
    シグナル配送を待つ(tests/test_task_runner.pyと同じ同期パターン)。"""
    app = QApplication.instance()
    for _ in range(50):
        app.processEvents()
        if window._update_check_task_runner is None:
            break
        window._update_check_task_runner.wait(200)
        app.processEvents()


def test_manual_update_check_shows_info_when_already_latest(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module, "check_for_update", lambda version, **k: None)
    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_check_for_update()
    _run_update_check_and_wait(window)

    assert len(info_calls) == 1
    assert __version__ in info_calls[0][2]


def test_manual_update_check_shows_update_dialog_when_newer_available(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    update_info = {'tag_name': 'v9.9.9', 'html_url': 'https://example.com/releases/v9.9.9', 'name': 'v9.9.9'}
    monkeypatch.setattr(help_mixin_module, "check_for_update", lambda version, **k: update_info)
    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a) or QMessageBox.StandardButton.No))
    browser_calls = []
    monkeypatch.setattr(help_mixin_module.webbrowser, "open", lambda url: browser_calls.append(url))

    window._on_check_for_update()
    _run_update_check_and_wait(window)

    assert len(info_calls) == 1
    assert 'v9.9.9' in info_calls[0][2]
    assert browser_calls == []  # Noを選んだのでブラウザは開かない


def test_manual_update_check_opens_browser_when_user_accepts(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    update_info = {'tag_name': 'v9.9.9', 'html_url': 'https://example.com/releases/v9.9.9', 'name': 'v9.9.9'}
    monkeypatch.setattr(help_mixin_module, "check_for_update", lambda version, **k: update_info)
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    browser_calls = []
    monkeypatch.setattr(help_mixin_module.webbrowser, "open", lambda url: browser_calls.append(url))

    window._on_check_for_update()
    _run_update_check_and_wait(window)

    assert browser_calls == ['https://example.com/releases/v9.9.9']


def test_manual_update_check_shows_warning_on_failure(tmp_path, monkeypatch):
    def _raise(*a, **k):
        raise OSError("network down")

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module, "check_for_update", _raise)
    warn_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_check_for_update()
    _run_update_check_and_wait(window)

    assert len(warn_calls) == 1


def test_manual_update_check_ignores_concurrent_second_call(tmp_path, monkeypatch):
    """確認中に再度メニューを選んでも、二重にTaskRunnerを起動しない。"""
    import time

    def _slow_check(version, **k):
        time.sleep(0.2)
        return None

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module, "check_for_update", _slow_check)
    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_check_for_update()
    first_runner = window._update_check_task_runner
    window._on_check_for_update()  # 実行中の2回目呼び出し

    assert window._update_check_task_runner is first_runner  # 新しいrunnerには差し替わらない
    _run_update_check_and_wait(window)
    assert len(info_calls) == 2  # 「確認中です」+ 完了時の「最新です」


def test_startup_update_check_shows_nothing_when_already_latest(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module, "check_for_update", lambda version, **k: None)
    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._start_startup_update_check()
    _run_update_check_and_wait(window)

    assert info_calls == []


def test_startup_update_check_shows_dialog_when_newer_available(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    update_info = {'tag_name': 'v9.9.9', 'html_url': 'https://example.com', 'name': 'v9.9.9'}
    monkeypatch.setattr(help_mixin_module, "check_for_update", lambda version, **k: update_info)
    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a) or QMessageBox.StandardButton.No))

    window._start_startup_update_check()
    _run_update_check_and_wait(window)

    assert len(info_calls) == 1


def test_startup_update_check_silently_ignores_failure(tmp_path, monkeypatch):
    """起動時の自動確認は失敗してもエラーダイアログを出さない(オフライン等を想定)。"""
    def _raise(*a, **k):
        raise OSError("offline")

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module, "check_for_update", _raise)
    warn_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))
    info_calls = []
    monkeypatch.setattr(help_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._start_startup_update_check()
    _run_update_check_and_wait(window)

    assert warn_calls == []
    assert info_calls == []
