# gui/mixins/project_io_mixin.py
"""
プロジェクト (.pkl) の保存/読込メニュー、および書式テンプレート (.json) の
保存/読込をまとめた Mixin。
実際のファイルI/Oの主要ロジックは gui/main_window.py の manual_save/manual_load
(pickle) にあり、ここはメニューからの呼び出しとテンプレート機能を担当する。
"""
import json
import logging
from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

logger = logging.getLogger(__name__)

# オートセーブ間隔として指定できる範囲 (分)
AUTOSAVE_INTERVAL_MIN_BOUNDS = (0, 180)


class ProjectIOMixin:
    def _on_save_project(self):
        """プロジェクト保存（JSONからPickle/MVCに変更）"""
        self.manual_save() # 既に定義されている .pkl 用の保存処理を呼ぶ

    def _on_load_project(self):
        """プロジェクト読込（MVC対応）"""
        self.manual_load() # 既に定義されている .pkl 用の読込処理を呼ぶ

    def _on_configure_autosave_interval(self):
        """
        「オートセーブ間隔を設定...」メニューがクリックされたときの処理。
        分単位で間隔を指定でき、0を指定するとオートセーブを無効化する。
        設定は QSettings で永続化され、次回起動時にも復元される。
        """
        current_minutes = (self.autosave_timer.interval() // 60000) if self.autosave_timer.isActive() else 0
        min_minutes, max_minutes = AUTOSAVE_INTERVAL_MIN_BOUNDS
        minutes, ok = QInputDialog.getInt(
            self, "オートセーブ間隔の設定",
            "オートセーブの間隔を分単位で入力してください (0で無効化):",
            current_minutes, min_minutes, max_minutes
        )
        if not ok:
            return

        self.settings.setValue("autosave_interval_min", minutes)
        if minutes <= 0:
            self.autosave_timer.stop()
            self.statusBar().showMessage("オートセーブを無効化しました", 3000)
        else:
            self.autosave_timer.start(minutes * 60 * 1000)
            self.statusBar().showMessage(f"オートセーブ間隔を{minutes}分に設定しました", 3000)

        self._update_autosave_menu_text()

    def _update_autosave_menu_text(self):
        """
        「ファイル」メニューのオートセーブ項目に、現在の状態 (有効/無効・間隔) を
        反映したテキストを設定する。__init__ で一度、設定変更のたびに呼び出す。
        """
        if not self.autosave_timer.isActive():
            self.autosave_interval_action.setText("オートセーブ: 無効(&I)...")
        else:
            minutes = self.autosave_timer.interval() // 60000
            self.autosave_interval_action.setText(f"オートセーブ: {minutes}分間隔(&I)...")

    def _on_save_plot_template(self):
        """
        現在の「アクティブなプロット」の外観設定を
        テンプレートファイル(*.json)として保存する
        """
        file_path, _ = QFileDialog.getSaveFileName(
            self, "書式テンプレートを保存", "", "Plotter Template Files (*.json)"
        )
        if not file_path:
            return

        # 1. 外観設定を「現在アクティブなUI」から収集 (ヘルパーメソッドを使用)
        plot_settings = self._gather_settings_from_ui()

        # 2. テンプレートファイルとして保存 (データは含まない)
        template_data = {
            'plot_settings': plot_settings
        }

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=4)
        except Exception as e:
            QMessageBox.warning(self, "保存エラー", f"テンプレートの保存中にエラーが発生しました:\n{e}")
            logger.exception("テンプレートの保存中にエラー")

    def _on_load_plot_template(self):
        """
        【★ 修正済み ★】
        書式テンプレートをJSONファイルから読み込み、
        「現在アクティブなプロット」に適用する
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "書式テンプレートを適用", "", "Plotter Template Files (*.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)

            # 1. 外観設定をファイルから読み込む
            settings = template_data.get('plot_settings', {})
            if not settings:
                QMessageBox.warning(self, "読込エラー", "有効な書式設定がファイルに含まれていません。")
                return

            # 2. 設定をUIコントロールに適用する (ヘルパーメソッドを使用)
            #    (この時点ではまだ all_plot_settings には保存されていない)
            self._apply_settings_to_ui_controls(settings)

            # 3. 【★ 修正箇所 ★】
            #    _on_axis_setting_changed() を呼び出す。
            #    これにより、UIにロードされた設定が _gather_settings_from_ui() され、
            #    all_plot_settings リストに「保存」され、
            #    _update_plot_appearance() が呼ばれてグラフに「適用」される。
            self._on_axis_setting_changed()

        except Exception as e:
            QMessageBox.warning(self, "読込エラー", f"テンプレートの読み込み中にエラーが発生しました:\n{e}")
            logger.exception("テンプレートの読み込み中にエラー")
