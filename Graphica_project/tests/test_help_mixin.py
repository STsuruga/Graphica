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
from PySide6.QtWidgets import QApplication, QDialog

import graphica.gui.notify as notify_module
import graphica.gui.app_settings as app_settings_module
import graphica.gui.mixins.help_mixin as help_mixin_module
from graphica.gui.main_window import PlotterApp
from graphica.gui.dialogs import AboutDialog, ShortcutsDialog, HelpDialog, CalcHelpDialog
from graphica.core.version import __version__


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
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
    monkeypatch.setattr(notify_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: ("", "")))

    info_calls = []
    monkeypatch.setattr(notify_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_export_diagnostic_bundle()

    assert info_calls == []
    assert list(tmp_path.iterdir()) == []


def test_on_export_diagnostic_bundle_writes_real_zip_and_appends_extension(tmp_path, monkeypatch):
    """保存先パスに拡張子.zipが無い場合は補い、build_diagnostic_bundleを実際に
    走らせて中身のあるzipファイルが書き出されること。完了メッセージも表示されること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    out_path_no_ext = str(tmp_path / "diag_bundle")
    monkeypatch.setattr(notify_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (out_path_no_ext, "Zip Files (*.zip)")))

    info_calls = []
    monkeypatch.setattr(notify_module.QMessageBox, "information",
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
    monkeypatch.setattr(notify_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (out_path, "Zip Files (*.zip)")))

    def broken_build(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(help_mixin_module, "build_diagnostic_bundle", broken_build)

    warn_calls = []
    monkeypatch.setattr(notify_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))
    info_calls = []
    monkeypatch.setattr(notify_module.QMessageBox, "information",
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
    monkeypatch.setattr(notify_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_check_for_update()
    _run_update_check_and_wait(window)

    assert len(info_calls) == 1
    assert __version__ in info_calls[0][2]


def _patch_update_dialog(monkeypatch, choice=None, accepted=True):
    """UpdateDialog の代わり。作られた引数を記録し、choice を押したことにする。"""
    shown = []

    class FakeUpdateDialog:
        def __init__(self, update_info, current_version, install_kind, has_asset, parent=None):
            shown.append({'info': update_info, 'kind': install_kind, 'has_asset': has_asset})
            self.choice = choice

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(help_mixin_module, "UpdateDialog", FakeUpdateDialog)
    return shown



def test_manual_update_check_shows_update_dialog_when_newer_available(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    update_info = {'tag_name': 'v9.9.9', 'html_url': 'https://example.com/releases/v9.9.9', 'name': 'v9.9.9'}
    monkeypatch.setattr(help_mixin_module, "check_for_update", lambda version, **k: update_info)
    shown = _patch_update_dialog(monkeypatch, accepted=False)
    browser_calls = []
    monkeypatch.setattr(help_mixin_module.webbrowser, "open", lambda url: browser_calls.append(url))

    window._on_check_for_update()
    _run_update_check_and_wait(window)

    assert len(shown) == 1
    assert shown[0]['info']['tag_name'] == 'v9.9.9'
    assert browser_calls == []  # あとで、を選んだのでブラウザは開かない


def test_manual_update_check_opens_the_release_page_when_chosen(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    update_info = {'tag_name': 'v9.9.9', 'html_url': 'https://example.com/releases/v9.9.9', 'name': 'v9.9.9'}
    monkeypatch.setattr(help_mixin_module, "check_for_update", lambda version, **k: update_info)
    _patch_update_dialog(monkeypatch, choice='page')
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
    monkeypatch.setattr(notify_module.QMessageBox, "warning",
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
    monkeypatch.setattr(notify_module.QMessageBox, "information",
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
    monkeypatch.setattr(notify_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._start_startup_update_check()
    _run_update_check_and_wait(window)

    assert info_calls == []


def test_startup_update_check_shows_dialog_when_newer_available(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    update_info = {'tag_name': 'v9.9.9', 'html_url': 'https://example.com', 'name': 'v9.9.9'}
    monkeypatch.setattr(help_mixin_module, "check_for_update", lambda version, **k: update_info)
    shown = _patch_update_dialog(monkeypatch, accepted=False)

    window._start_startup_update_check()
    _run_update_check_and_wait(window)

    assert len(shown) == 1


def test_startup_update_check_silently_ignores_failure(tmp_path, monkeypatch):
    """起動時の自動確認は失敗してもエラーダイアログを出さない(オフライン等を想定)。"""
    def _raise(*a, **k):
        raise OSError("offline")

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module, "check_for_update", _raise)
    warn_calls = []
    monkeypatch.setattr(notify_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))
    info_calls = []
    monkeypatch.setattr(notify_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._start_startup_update_check()
    _run_update_check_and_wait(window)

    assert warn_calls == []
    assert info_calls == []


# --- 配布の形ごとの更新の方法 ---

INSTALLER = {'name': 'Graphica-9.9.9-setup.exe', 'url': 'https://example.com/setup.exe', 'size': 10, 'sha256': 'ab'}
WIN_ZIP = {'name': 'Graphica-windows.zip', 'url': 'https://example.com/win.zip', 'size': 10, 'sha256': ''}
UPDATE_INFO = {'tag_name': 'v9.9.9', 'html_url': 'https://example.com/r', 'name': 'v9.9.9', 'body': '- fix',
               'assets': [INSTALLER, WIN_ZIP]}


@pytest.mark.parametrize("kind, has_asset", [
    ('installer', True), ('windows_zip', True), ('macos', False), ('pip', False), ('source', False)])
def test_the_dialog_gets_the_install_kind_and_whether_a_file_exists(tmp_path, monkeypatch, kind, has_asset):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module.updater, "install_kind", lambda: kind)
    shown = _patch_update_dialog(monkeypatch, accepted=False)

    window._show_update_available_dialog(UPDATE_INFO)

    assert shown == [{'info': UPDATE_INFO, 'kind': kind, 'has_asset': has_asset}]


def test_download_choice_opens_the_file_for_the_zip_version(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module.updater, "install_kind", lambda: 'windows_zip')
    _patch_update_dialog(monkeypatch, choice='download')
    opened = []
    monkeypatch.setattr(help_mixin_module.webbrowser, "open", lambda url: opened.append(url))

    window._show_update_available_dialog(UPDATE_INFO)

    assert opened == ['https://example.com/win.zip']


def test_install_choice_downloads_the_installer(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module.updater, "install_kind", lambda: 'installer')
    _patch_update_dialog(monkeypatch, choice='install')
    started = []
    monkeypatch.setattr(window, "_start_update_download", lambda asset: started.append(asset))

    window._show_update_available_dialog(UPDATE_INFO)

    assert started == [INSTALLER]


def _wait_for_download(window):
    app = QApplication.instance()
    for _ in range(100):
        app.processEvents()
        if window._update_download_runner is None:
            break
        window._update_download_runner.wait(100)
        app.processEvents()


def test_downloaded_installer_is_handed_to_the_install_step(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module.updater, "update_download_dir", lambda: str(tmp_path))
    monkeypatch.setattr(help_mixin_module.updater, "download_file",
                        lambda url, dest, size, sha, **k: dest)
    installed = []
    monkeypatch.setattr(window, "_install_downloaded_update", lambda path: installed.append(path))

    window._start_update_download(INSTALLER)
    _wait_for_download(window)

    assert installed == [str(tmp_path / 'Graphica-9.9.9-setup.exe')]


def test_cancelled_download_installs_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module.updater, "update_download_dir", lambda: str(tmp_path))
    monkeypatch.setattr(help_mixin_module.updater, "download_file", lambda *a, **k: None)
    installed = []
    monkeypatch.setattr(window, "_install_downloaded_update", lambda path: installed.append(path))

    window._start_update_download(INSTALLER)
    _wait_for_download(window)

    assert installed == []


def test_failed_download_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(help_mixin_module.updater, "update_download_dir", lambda: str(tmp_path))

    def fail(*a, **k):
        raise ValueError("SHA-256 が一致しません")
    monkeypatch.setattr(help_mixin_module.updater, "download_file", fail)
    warnings = []
    monkeypatch.setattr(notify_module.QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    window._start_update_download(INSTALLER)
    _wait_for_download(window)

    assert len(warnings) == 1 and "SHA-256" in warnings[0][2]


def test_install_closes_graphica_before_starting_the_installer(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    events = []
    monkeypatch.setattr(window, "close", lambda: events.append('close') or True)
    monkeypatch.setattr(help_mixin_module.updater, "launch_installer", lambda path: events.append(('launch', path)))

    window._install_downloaded_update("C:/tmp/setup.exe")

    assert events == ['close', ('launch', "C:/tmp/setup.exe")]


def test_install_is_abandoned_when_closing_is_cancelled(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(window, "close", lambda: False)
    launched = []
    monkeypatch.setattr(help_mixin_module.updater, "launch_installer", lambda path: launched.append(path))
    infos = []
    monkeypatch.setattr(notify_module.QMessageBox, "information", staticmethod(lambda *a, **k: infos.append(a)))

    window._install_downloaded_update("C:/tmp/setup.exe")

    assert launched == []
    assert "C:/tmp/setup.exe" in infos[0][2]
