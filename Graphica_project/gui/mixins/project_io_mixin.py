# gui/mixins/project_io_mixin.py
"""
プロジェクト (.graphica/.pkl) の保存/読込メニュー、および書式テンプレート (.json) の
保存/読込をまとめた Mixin。
実際のファイルI/Oの主要ロジックは gui/main_window.py の manual_save/manual_load
(拡張子に応じてJSON/pickleを振り分け) にあり、ここはメニューからの呼び出しと
テンプレート機能を担当する。
"""
import json
import logging
from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

from gui.dialogs import PreferencesDialog
from gui.canvas import DEFAULT_POINT_LABEL_MAX_POINTS
from gui.mixins.annotation_mixin import DEFAULT_SNAP_TO_GRID_ENABLED, DEFAULT_SNAP_GRID_INTERVAL_PX
from core.i18n import tr, get_language

logger = logging.getLogger(__name__)

# オートセーブ間隔として指定できる範囲 (分)
AUTOSAVE_INTERVAL_MIN_BOUNDS = (0, 180)


class ProjectIOMixin:
    def _on_save_project(self):
        """プロジェクト保存（MVC対応）"""
        self.manual_save() # 既に定義されている保存処理を呼ぶ(拡張子でJSON/pickleを振り分け)

    def _on_load_project(self):
        """プロジェクト読込（MVC対応）"""
        self.manual_load() # 既に定義されている読込処理を呼ぶ(拡張子でJSON/pickleを振り分け)

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

        self._apply_autosave_interval(minutes)

    def _apply_autosave_interval(self, minutes):
        """
        オートセーブ間隔 (分) を実際に適用し、設定を永続化する。
        「オートセーブ間隔を設定...」メニューと環境設定ダイアログの両方から呼ばれる。
        """
        self.settings.setValue("autosave_interval_min", minutes)
        if minutes <= 0:
            self.autosave_timer.stop()
            self.statusBar().showMessage("オートセーブを無効化しました", 3000)
        else:
            self.autosave_timer.start(minutes * 60 * 1000)
            self.statusBar().showMessage(f"オートセーブ間隔を{minutes}分に設定しました", 3000)

        self._update_autosave_menu_text()

    def _on_show_preferences(self):
        """
        「編集」メニューの「環境設定...」がクリックされたときの処理。
        ダークモード・オートセーブ間隔をまとめた1つのダイアログで変更できるようにする。
        """
        current_minutes = (self.autosave_timer.interval() // 60000) if self.autosave_timer.isActive() else 0
        current_language = self.settings.value("language", get_language())
        current_autosave_dir = self.settings.value("autosave_dir", "", type=str)
        current_point_label_max = self.settings.value(
            "point_label_max_points", DEFAULT_POINT_LABEL_MAX_POINTS, type=int)
        current_snap_to_grid = self.settings.value(
            "snap_to_grid_enabled", DEFAULT_SNAP_TO_GRID_ENABLED, type=bool)
        current_snap_grid_interval = self.settings.value(
            "snap_grid_interval_px", DEFAULT_SNAP_GRID_INTERVAL_PX, type=int)
        dlg = PreferencesDialog(
            self.canvas.dark_mode, current_minutes,
            autosave_bounds=AUTOSAVE_INTERVAL_MIN_BOUNDS, parent=self,
            current_language=current_language, autosave_dir=current_autosave_dir,
            point_label_max_points=current_point_label_max,
            snap_to_grid_enabled=current_snap_to_grid,
            snap_grid_interval_px=current_snap_grid_interval
        )
        if dlg.exec() != PreferencesDialog.DialogCode.Accepted:
            return

        (new_dark_mode, new_autosave_minutes, new_language,
         new_autosave_dir, new_point_label_max,
         new_snap_to_grid, new_snap_grid_interval) = dlg.get_settings()

        # オートセーブの保存先フォルダ(項目: 環境設定からオートセーブ保存先を指定可能に)
        if new_autosave_dir != current_autosave_dir:
            self.settings.setValue("autosave_dir", new_autosave_dir)
            self._update_autosave_path()

        # ダークモードの切り替えは、ツールバー等のチェック状態も含めて一貫性を
        # 保つため、既存の View メニューのチェック可能アクション経由で行う。
        # setChecked() が値の変化時に toggled シグナルを発火し、
        # _on_toggle_dark_mode が実際の適用(パレット/設定保存/再描画)を行う。
        if new_dark_mode != self.canvas.dark_mode:
            self.dark_mode_action.setChecked(new_dark_mode)

        if new_autosave_minutes != current_minutes:
            self._apply_autosave_interval(new_autosave_minutes)

        # データ点ラベルの表示上限(項目105): 変更されたら即座にキャンバスへ反映し、
        # 現在表示中のグラフにも(上限を超えるデータセットがあれば)反映されるよう再描画する
        if new_point_label_max != current_point_label_max:
            self.settings.setValue("point_label_max_points", new_point_label_max)
            self.canvas.point_label_max_points = new_point_label_max
            self._update_plot()

        # スナップ・トゥ・グリッド(項目84): 注釈モードのドラッグ確定時に参照される
        # self.snap_to_grid_enabled / self.snap_grid_interval_px をここで即座に更新する。
        if new_snap_to_grid != current_snap_to_grid:
            self.settings.setValue("snap_to_grid_enabled", new_snap_to_grid)
            self.snap_to_grid_enabled = new_snap_to_grid
        if new_snap_grid_interval != current_snap_grid_interval:
            self.settings.setValue("snap_grid_interval_px", new_snap_grid_interval)
            self.snap_grid_interval_px = new_snap_grid_interval

        # UIの多言語対応(項目41): 実行中のウィジェットをその場で再翻訳する仕組みは
        # 持たないため、設定の保存のみ行い、反映は次回起動時になる旨を案内する。
        if new_language != current_language:
            self.settings.setValue("language", new_language)
            QMessageBox.information(
                self, tr("表示言語の変更"),
                tr("表示言語の変更は、次回起動時に反映されます。")
            )

    def _update_autosave_menu_text(self):
        """
        「ファイル」メニューのオートセーブ項目に、現在の状態 (有効/無効・間隔) を
        反映したテキストを設定する。__init__ で一度、設定変更のたびに呼び出す。
        """
        if not self.autosave_timer.isActive():
            self.autosave_interval_action.setText(tr("オートセーブ: 無効(&I)..."))
        else:
            minutes = self.autosave_timer.interval() // 60000
            self.autosave_interval_action.setText(tr("オートセーブ: {minutes}分間隔(&I)...").format(minutes=minutes))

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
