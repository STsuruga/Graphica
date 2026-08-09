# gui/mixins/help_mixin.py
"""
ヘルプメニューから開くリファレンスダイアログをまとめた Mixin。
"""
import logging
from datetime import datetime

from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.dialogs import HelpDialog, CalcHelpDialog, AboutDialog, ShortcutsDialog
from core.diagnostics import build_diagnostic_bundle

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
