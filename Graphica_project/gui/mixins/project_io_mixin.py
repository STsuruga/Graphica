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
from gui.mixins.dataset_mixin import STYLE_ATTRS
from core.i18n import tr, get_language

logger = logging.getLogger(__name__)

# オートセーブ間隔として指定できる範囲 (分)
AUTOSAVE_INTERVAL_MIN_BOUNDS = (0, 180)

# 項目C-806: フィギュアテンプレートの現在のスキーマバージョン。
TEMPLATE_FORMAT_VERSION = 1

# all_plot_settings[index]のうち、注釈・凡例の並び順・自由配置の位置は
# サブプロットごとの「内容」寄りで、別のデータセット/プロジェクトへ持ち込む
# 「見た目のスタイル」としては不適切なため、テンプレートの保存/適用対象から除外する
# (保存時は除いて書き出し、適用時は現在のサブプロットが持つ値をそのまま保持する)。
TEMPLATE_EXCLUDED_AXIS_SETTING_KEYS = ('annotations', 'legend_order', 'free_rect')


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

        # プラグイン管理タブ(項目F-2)向けのデータ。
        # gui.main_window はこのMixinを読み込む側(逆方向にimportすると循環
        # importになる)なので、関数内でのローカルimportにする。
        from core.plugin_api import get_loaded_plugin_records, get_plugin_registration_errors
        from gui.main_window import DISABLED_PLUGINS_SETTINGS_KEY, disabled_plugin_names
        current_disabled_plugin_names = disabled_plugin_names(self.settings)

        dlg = PreferencesDialog(
            self.canvas.dark_mode, current_minutes,
            autosave_bounds=AUTOSAVE_INTERVAL_MIN_BOUNDS, parent=self,
            current_language=current_language, autosave_dir=current_autosave_dir,
            point_label_max_points=current_point_label_max,
            snap_to_grid_enabled=current_snap_to_grid,
            snap_grid_interval_px=current_snap_grid_interval,
            plugin_records=get_loaded_plugin_records(),
            plugin_registration_errors=get_plugin_registration_errors(),
            disabled_plugin_names=current_disabled_plugin_names,
        )
        if dlg.exec() != PreferencesDialog.DialogCode.Accepted:
            return

        (new_dark_mode, new_autosave_minutes, new_language,
         new_autosave_dir, new_point_label_max,
         new_snap_to_grid, new_snap_grid_interval) = dlg.get_settings()

        # プラグインの個別ON/OFF(項目F-2): 次回起動時に反映される
        # (今回のロード済みプラグイン一覧をその場で入れ替える仕組みは持たない)。
        new_disabled_plugin_names = dlg.get_disabled_plugin_names()
        if new_disabled_plugin_names != current_disabled_plugin_names:
            self.settings.setValue(DISABLED_PLUGINS_SETTINGS_KEY, list(new_disabled_plugin_names))

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
        現在のプロジェクトの全サブプロットの外観設定+全データセットのスタイルを、
        独立したテンプレートファイル(*.graphica-style)として保存する(項目C-806)。
        データそのもの(df/x_col_name等、識別/データ系フィールド)は含まない。
        注釈・凡例の並び順・自由配置の位置(TEMPLATE_EXCLUDED_AXIS_SETTING_KEYS)は
        サブプロットの「内容」寄りのため対象外(見た目のスタイルのみを対象とする)。
        """
        file_path, _ = QFileDialog.getSaveFileName(
            self, "書式テンプレートを保存", "", "Graphica Style Template (*.graphica-style)"
        )
        if not file_path:
            return
        if not (file_path.endswith('.graphica-style') or file_path.endswith('.json')):
            file_path += '.graphica-style'

        # 保存直前に、現在アクティブな軸のUI状態を all_plot_settings へ反映させておく
        # (_gather_settings_from_ui はUIコントロールの現在値を読むだけで、
        #  自動的には保存されないため)。
        if self.project.active_axis_index < len(self.project.all_plot_settings):
            self.project.all_plot_settings[self.project.active_axis_index] = self._gather_settings_from_ui()

        subplot_styles = [
            {k: v for k, v in settings.items() if k not in TEMPLATE_EXCLUDED_AXIS_SETTING_KEYS}
            for settings in self.project.all_plot_settings
        ]
        dataset_styles = [
            {attr: getattr(ds, attr) for attr in STYLE_ATTRS}
            for ds in self.project.datasets
        ]

        template_data = {
            'format_version': TEMPLATE_FORMAT_VERSION,
            'subplot_styles': subplot_styles,
            'dataset_styles': dataset_styles,
        }

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.warning(self, "保存エラー", f"テンプレートの保存中にエラーが発生しました:\n{e}")
            logger.exception("テンプレートの保存中にエラー")

    def _on_load_plot_template(self):
        """
        書式テンプレートファイル(*.graphica-style、または項目C-806以前の
        *.json形式との後方互換あり)を読み込み、現在のプロジェクトへ適用する。

        新形式(format_versionあり、項目C-806): 保存時の並び順のまま、現在の
        サブプロット数ぶんサイクリックに外観設定を適用する(既存の注釈・
        凡例並び順・自由配置位置はサブプロットごとに保持したまま、それ以外の
        見た目だけ差し替える)。データセットのスタイルも同様にサイクリックに
        適用する(データセット数がテンプレート保存時と異なっていても破綻しない)。
        Undo/Redoには対応しない(旧形式のテンプレート適用も同様に非対応だった
        既存の挙動を踏襲)。

        旧形式(plot_settingsキーのみ): 従来通り「現在アクティブな1サブプロット」
        にのみ適用する(既存の互換動作をそのまま維持)。
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "書式テンプレートを適用", "", "Graphica Style Template (*.graphica-style *.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)

            if 'format_version' in template_data:
                subplot_styles = template_data.get('subplot_styles') or []
                if not subplot_styles:
                    QMessageBox.warning(self, "読込エラー", "有効な書式設定がファイルに含まれていません。")
                    return

                for i, settings in enumerate(self.project.all_plot_settings):
                    style = subplot_styles[i % len(subplot_styles)]
                    merged = dict(settings)
                    for k, v in style.items():
                        if k not in TEMPLATE_EXCLUDED_AXIS_SETTING_KEYS:
                            merged[k] = v
                    self.project.all_plot_settings[i] = merged
                    if i == self.project.active_axis_index:
                        self._apply_settings_to_ui_controls(merged)

                dataset_styles = template_data.get('dataset_styles') or []
                if dataset_styles:
                    for i, dataset in enumerate(self.project.datasets):
                        style = dataset_styles[i % len(dataset_styles)]
                        for attr, value in style.items():
                            setattr(dataset, attr, value)

                self._update_plot()
            else:
                # 旧形式(項目C-806以前): アクティブな1サブプロットのみに適用
                settings = template_data.get('plot_settings', {})
                if not settings:
                    QMessageBox.warning(self, "読込エラー", "有効な書式設定がファイルに含まれていません。")
                    return
                self._apply_settings_to_ui_controls(settings)
                self._on_axis_setting_changed()

        except Exception as e:
            QMessageBox.warning(self, "読込エラー", f"テンプレートの読み込み中にエラーが発生しました:\n{e}")
            logger.exception("テンプレートの読み込み中にエラー")
