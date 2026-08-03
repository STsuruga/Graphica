# gui/mixins/help_mixin.py
"""
ヘルプメニューから開くリファレンスダイアログをまとめた Mixin。
"""
from gui.dialogs import HelpDialog, CalcHelpDialog, AboutDialog, ShortcutsDialog


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
