# gui/mixins/help_mixin.py
"""
ヘルプメニューから開くリファレンスダイアログをまとめた Mixin。
"""
import logging
import webbrowser
from datetime import datetime

from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.dialogs import HelpDialog, CalcHelpDialog, AboutDialog, ShortcutsDialog
from gui.task_runner import TaskRunner
from core.diagnostics import build_diagnostic_bundle
from core.update_check import check_for_update
from core.version import __version__

logger = logging.getLogger(__name__)


class HelpMixin:
    def _on_show_about(self):
        """「このソフトについて」メニューがクリックされたときの処理。"""
        dialog = AboutDialog(self)
        dialog.exec()

    def _on_show_help(self):
        """
        「mathtext リファレンス」メニューがクリックされたときの処理。
        ヘルプを見ながらプロットウィンドウも操作できるよう、非モーダル (show) で表示する。
        """
        if getattr(self, 'help_dialog', None) is not None:
            self.help_dialog.close()
            # ★ バグ修正: close()だけではC++オブジェクトは破棄されず、非表示の
            # まま親(self)にぶら下がり続けてリークする(gui/data_editor.pyの
            # DataEditorDialogと同種のバグ、詳細はそちら参照)。
            self.help_dialog.deleteLater()
        self.help_dialog = HelpDialog(self)
        self.help_dialog.show()
        self.help_dialog.raise_()
        self.help_dialog.activateWindow()

    def _on_show_calc_help(self):
        """
        「列計算機能 リファレンス」メニューがクリックされたときの処理。
        ヘルプを見ながらプロットウィンドウも操作できるよう、非モーダル (show) で表示する。
        """
        if getattr(self, 'calc_help_dialog', None) is not None:
            self.calc_help_dialog.close()
            self.calc_help_dialog.deleteLater()  # 理由はHelpDialog側と同じ
        self.calc_help_dialog = CalcHelpDialog(self)
        self.calc_help_dialog.show()
        self.calc_help_dialog.raise_()
        self.calc_help_dialog.activateWindow()

    def _on_show_shortcuts(self):
        """「キーボードショートカット一覧」メニューがクリックされたときの処理。"""
        dialog = ShortcutsDialog(self._collect_menu_actions, self)
        dialog.exec()

    def _on_export_diagnostic_bundle(self):
        """
        「診断情報をエクスポート...」メニューの処理(項目C-1201)。
        バグ報告時に添付できるよう、ログ・環境情報・設定値・プラグイン
        読み込み状況を1つのzipファイルにまとめて書き出す。
        """
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

    # --- アップデート通知(項目161、C-1203) ---
    # 「取得のみ・送信なし」: 公開のGitHub REST APIへの匿名GET1回のみ行い、
    # ユーザーを特定できる情報は一切送信しない。起動時の自動確認(失敗時は
    # 静かに諦める)と、ヘルプメニューからの手動確認(失敗時はエラーを表示する)
    # の2経路があり、いずれもcore.update_check.check_for_updateをTaskRunner
    # (項目C-004)経由でバックグラウンド実行することでUIをブロックしない。

    def _start_startup_update_check(self):
        """起動直後に一度だけ行う自動確認。新版が無い/確認に失敗した場合は何も表示しない。"""
        if self._update_check_task_runner is not None:
            return  # 手動確認と重複しないよう、既に実行中なら何もしない
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
        # 自動確認の失敗(オフライン等)はユーザーに知らせる必要がないため、
        # ログにだけ残して静かに諦める。
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
