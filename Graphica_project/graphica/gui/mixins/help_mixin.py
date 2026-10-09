"""ヘルプメニュー(リファレンス、診断情報、アップデートの確認)。"""
import logging
import os
import webbrowser
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QProgressDialog

from graphica.core.i18n import tr
from graphica.gui import dialog_dirs, notify, updater
from graphica.gui.dialogs import HelpDialog, CalcHelpDialog, AboutDialog, ShortcutsDialog, UpdateDialog
from graphica.gui.task_runner import TaskRunner
from graphica.core.diagnostics import build_diagnostic_bundle
from graphica.core.update_check import check_for_update, pick_asset
from graphica.core.version import __version__

logger = logging.getLogger(__name__)


class HelpMixin:
    def _on_show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()

    def _on_show_help(self):
        """プロットを操作しながら見られるよう、非モーダルで開く。"""
        if getattr(self, 'help_dialog', None) is not None:
            self.help_dialog.close()
            # close() だけでは C++ のオブジェクトが残ってリークする
            self.help_dialog.deleteLater()
        self.help_dialog = HelpDialog(self)
        self.help_dialog.show()
        self.help_dialog.raise_()
        self.help_dialog.activateWindow()

    def _on_show_calc_help(self):
        """プロットを操作しながら見られるよう、非モーダルで開く。"""
        if getattr(self, 'calc_help_dialog', None) is not None:
            self.calc_help_dialog.close()
            self.calc_help_dialog.deleteLater()
        self.calc_help_dialog = CalcHelpDialog(self)
        self.calc_help_dialog.show()
        self.calc_help_dialog.raise_()
        self.calc_help_dialog.activateWindow()

    def _on_show_shortcuts(self):
        dialog = ShortcutsDialog(self._collect_menu_actions, self)
        dialog.exec()

    def _on_export_diagnostic_bundle(self):
        """ログ・環境・設定・プラグインの状態を1つの zip にする(不具合の報告用)。"""
        default_name = f"graphica_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        file_path, _ = dialog_dirs.get_save_file_name(
            self, dialog_dirs.OTHER, "診断情報をエクスポート", default_name, "Zip Files (*.zip)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith('.zip'):
            file_path += '.zip'

        settings_dict = {key: self.settings.value(key) for key in self.settings.allKeys()}
        try:
            build_diagnostic_bundle(file_path, settings_dict=settings_dict)
        except Exception as e:
            logger.exception("診断情報のエクスポートに失敗しました。")
            notify.warning(self, "エクスポートエラー", f"診断情報のエクスポート中にエラーが発生しました:\n{e}")
            return

        notify.information(self, "エクスポート完了", f"診断情報を書き出しました:\n{file_path}")

    # アップデートの確認は公開 API への匿名の GET 1回だけで、何も送らない。起動時は失敗しても黙り、手動では知らせる

    def _start_startup_update_check(self):
        """新しい版が無いか失敗したら何も出さない。"""
        if self._update_check_task_runner is not None:
            return  # 手動の確認が動いている
        runner = TaskRunner(check_for_update, __version__, parent=self)
        runner.succeeded.connect(self._on_startup_update_check_succeeded)
        runner.failed.connect(self._on_startup_update_check_failed)
        self._update_check_task_runner = runner
        runner.start()

    def _on_startup_update_check_succeeded(self, update_info):
        self._update_check_task_runner = None
        if update_info is not None:
            self._show_update_available_dialog(update_info)

    def _on_startup_update_check_failed(self, _message):
        logger.info("起動時のアップデート確認に失敗しました(オフライン等の可能性): %s", _message)
        self._update_check_task_runner = None

    def _on_check_for_update(self):
        """「アップデートを確認...」メニューの処理。手動確認は失敗時もエラーを表示する。"""
        if self._update_check_task_runner is not None:
            notify.information(self, "アップデートの確認", "確認中です。完了までお待ちください。")
            return
        runner = TaskRunner(check_for_update, __version__, parent=self)
        runner.succeeded.connect(self._on_manual_update_check_succeeded)
        runner.failed.connect(self._on_manual_update_check_failed)
        self._update_check_task_runner = runner
        runner.start()

    def _on_manual_update_check_succeeded(self, update_info):
        self._update_check_task_runner = None
        if update_info is not None:
            self._show_update_available_dialog(update_info)
        else:
            notify.information(self, "アップデートの確認", f"お使いのバージョン({__version__})は最新です。")

    def _on_manual_update_check_failed(self, message):
        self._update_check_task_runner = None
        logger.warning("アップデート確認に失敗しました: %s", message)
        notify.warning(
            self, "アップデートの確認",
            f"アップデート情報の取得に失敗しました。ネットワーク接続を確認してください。\n\n{message}"
        )

    def _show_update_available_dialog(self, update_info):
        """新しいバージョンが見つかった場合の通知(起動時自動確認・手動確認で共通)。配布の形に合った更新の方法を出す。"""
        kind = updater.install_kind()
        asset = pick_asset(update_info, kind)
        dialog = UpdateDialog(update_info, __version__, kind, asset is not None, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.choice == 'install' and asset is not None:
            self._start_update_download(asset)
        elif dialog.choice == 'download' and asset is not None:
            webbrowser.open(asset['url'])
        elif dialog.choice == 'page':
            webbrowser.open(update_info.get('html_url', ''))

    # --- アプリの中での更新(Windows のインストーラー版) ---

    def _start_update_download(self, asset):
        if self._update_download_runner is not None:
            notify.information(self, tr("アップデート"), tr("ダウンロード中です。完了までお待ちください。"))
            return
        dest_path = os.path.join(updater.update_download_dir(), asset['name'])
        progress = QProgressDialog(tr("新しいバージョンをダウンロードしています..."), tr("キャンセル"),
                                   0, max(asset.get('size', 0) // 1024, 1), self)
        progress.setWindowTitle(tr("アップデート"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        runner = TaskRunner(updater.download_file, asset['url'], dest_path,
                            asset.get('size', 0), asset.get('sha256', ''), parent=self)
        runner.progress.connect(lambda done, total, _message: self._on_update_download_progress(progress, done, total))
        progress.canceled.connect(runner.requestInterruption)
        runner.succeeded.connect(lambda path: self._on_update_downloaded(path, progress))
        runner.failed.connect(lambda message: self._on_update_download_failed(message, progress))
        self._update_download_runner = runner
        runner.start()

    @staticmethod
    def _on_update_download_progress(progress, done_kb, total_kb):
        if total_kb > 0 and progress.maximum() != total_kb:
            progress.setMaximum(total_kb)
        progress.setValue(min(done_kb, progress.maximum()))

    def _on_update_downloaded(self, installer_path, progress):
        self._update_download_runner = None
        progress.close()
        if installer_path is None:
            return  # キャンセル
        self._install_downloaded_update(installer_path)

    def _on_update_download_failed(self, message, progress):
        self._update_download_runner = None
        progress.close()
        logger.warning("アップデートのダウンロードに失敗しました: %s", message)
        notify.warning(self, tr("アップデート"),
                       tr("新しいバージョンをダウンロードできませんでした。\n\n{message}").format(message=message))

    def _install_downloaded_update(self, installer_path):
        """Graphica を閉じてから(未保存の確認もここ)インストーラーを起動する。閉じるのをやめたら更新もしない。

        先にインストーラーを起動すると、閉じるのをやめたときにインストーラーが Graphica を強制的に閉じてしまう。
        """
        if not self.window().close():
            notify.information(
                self, tr("アップデート"),
                tr("Graphica を閉じなかったので、更新を取りやめました。ダウンロードしたインストーラーは次の場所にあります:\n{path}")
                .format(path=installer_path))
            return
        try:
            updater.launch_installer(installer_path)
        except OSError as e:
            logger.exception("インストーラーを起動できませんでした")
            notify.critical(None, tr("アップデート"),
                            tr("インストーラーを起動できませんでした。次のファイルを手で実行してください:\n{path}\n\n{error}")
                            .format(path=installer_path, error=e))
