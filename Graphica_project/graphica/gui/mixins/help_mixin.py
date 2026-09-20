"""ヘルプメニュー(リファレンス、診断情報、アップデートの確認)。"""
import logging
import webbrowser
from datetime import datetime

from PySide6.QtWidgets import QFileDialog, QMessageBox

from graphica.gui.dialogs import HelpDialog, CalcHelpDialog, AboutDialog, ShortcutsDialog
from graphica.gui.task_runner import TaskRunner
from graphica.core.diagnostics import build_diagnostic_bundle
from graphica.core.update_check import check_for_update
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
        file_path, _ = QFileDialog.getSaveFileName(
            self, "診断情報をエクスポート", default_name, "Zip Files (*.zip)"
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
            QMessageBox.warning(self, "エクスポートエラー", f"診断情報のエクスポート中にエラーが発生しました:\n{e}")
            return

        QMessageBox.information(self, "エクスポート完了", f"診断情報を書き出しました:\n{file_path}")

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
            QMessageBox.information(self, "アップデートの確認", "確認中です。完了までお待ちください。")
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
            QMessageBox.information(self, "アップデートの確認", f"お使いのバージョン({__version__})は最新です。")

    def _on_manual_update_check_failed(self, message):
        self._update_check_task_runner = None
        logger.warning("アップデート確認に失敗しました: %s", message)
        QMessageBox.warning(
            self, "アップデートの確認",
            f"アップデート情報の取得に失敗しました。ネットワーク接続を確認してください。\n\n{message}"
        )

    def _show_update_available_dialog(self, update_info):
        """新しいバージョンが見つかった場合の通知(起動時自動確認・手動確認で共通)。"""
        tag = update_info.get('tag_name', '')
        html_url = update_info.get('html_url', '')
        reply = QMessageBox.information(
            self, "新しいバージョンがあります",
            f"新しいバージョン({tag})が公開されています。現在のバージョン: {__version__}\n\n"
            "ダウンロードページを開きますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            webbrowser.open(html_url)
