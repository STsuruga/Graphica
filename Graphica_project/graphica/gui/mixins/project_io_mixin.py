"""プロジェクトの保存と読み込みのメニュー、書式テンプレート、環境設定、設定の書き出しと読み込み。"""
import json
import logging
from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

from graphica.gui.dialogs import PreferencesDialog
from graphica.gui.canvas import DEFAULT_POINT_LABEL_MAX_POINTS
from graphica.gui.mixins.annotation_mixin import DEFAULT_SNAP_TO_GRID_ENABLED, DEFAULT_SNAP_GRID_INTERVAL_PX
from graphica.gui.datasets.transfer import STYLE_ATTRS
from graphica.core.i18n import tr, get_language

logger = logging.getLogger(__name__)

AUTOSAVE_INTERVAL_MIN_BOUNDS = (0, 180)

TEMPLATE_FORMAT_VERSION = 1

# 書き出す QSettings のキー (キー, 型, 既定値)。ウィンドウの状態や最近使ったファイルなど、
# その環境だけの項目は入れない(別の PC に持ち込んでも意味が無いか害になる)
SETTINGS_EXPORT_FORMAT_VERSION = 1
SETTINGS_EXPORT_SPEC = (
    ("language", str, ""),
    ("dark_mode", bool, False),
    ("autosave_interval_min", int, 5),
    ("point_label_max_points", int, DEFAULT_POINT_LABEL_MAX_POINTS),
    ("snap_to_grid_enabled", bool, DEFAULT_SNAP_TO_GRID_ENABLED),
    ("snap_grid_interval_px", int, DEFAULT_SNAP_GRID_INTERVAL_PX),
    ("custom_color_palettes_json", str, ""),
    ("active_color_palette", str, ""),
    ("quick_access_pinned_actions", list, []),
    ("disabled_plugins", list, []),
)

# サブプロットの中身に近いもの。テンプレートでは保存も適用もしない(適用先の値を残す)
TEMPLATE_EXCLUDED_AXIS_SETTING_KEYS = ('annotations', 'legend_order', 'free_rect')


class ProjectIOMixin:
    def _on_save_project(self):
        self.manual_save()

    def _on_save_project_as(self):
        self.manual_save_as()

    def _on_load_project(self):
        self.manual_load()

    def _on_configure_autosave_interval(self):
        """0 分で無効。"""
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
        """メニューと環境設定の両方から呼ばれる。"""
        self.settings.setValue("autosave_interval_min", minutes)
        if minutes <= 0:
            self.autosave_timer.stop()
            self.statusBar().showMessage("オートセーブを無効化しました", 3000)
        else:
            self.autosave_timer.start(minutes * 60 * 1000)
            self.statusBar().showMessage(f"オートセーブ間隔を{minutes}分に設定しました", 3000)

        self._update_autosave_menu_text()

    def _on_show_preferences(self):
        current_minutes = (self.autosave_timer.interval() // 60000) if self.autosave_timer.isActive() else 0
        current_language = self.settings.value("language", get_language())
        current_autosave_dir = self.settings.value("autosave_dir", "", type=str)
        current_point_label_max = self.settings.value(
            "point_label_max_points", DEFAULT_POINT_LABEL_MAX_POINTS, type=int)
        current_snap_to_grid = self.settings.value(
            "snap_to_grid_enabled", DEFAULT_SNAP_TO_GRID_ENABLED, type=bool)
        current_snap_grid_interval = self.settings.value(
            "snap_grid_interval_px", DEFAULT_SNAP_GRID_INTERVAL_PX, type=int)

        # main_window がこの mixin を import しているので、関数の中で import する
        from graphica.core.plugin_api import get_loaded_plugin_records, get_plugin_registration_errors
        from graphica.gui.main_window import DISABLED_PLUGINS_SETTINGS_KEY, disabled_plugin_names
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

        # 次の起動から効く(読み込んだプラグインをその場で入れ替える仕組みは無い)
        new_disabled_plugin_names = dlg.get_disabled_plugin_names()
        if new_disabled_plugin_names != current_disabled_plugin_names:
            self.settings.setValue(DISABLED_PLUGINS_SETTINGS_KEY, list(new_disabled_plugin_names))

        if new_autosave_dir != current_autosave_dir:
            self.settings.setValue("autosave_dir", new_autosave_dir)
            self._update_autosave_path()

        # 表示メニューのチェック経由で切り替える(toggled から _on_toggle_dark_mode が適用し、チェックの状態も揃う)
        if new_dark_mode != self.canvas.dark_mode:
            self.dark_mode_action.setChecked(new_dark_mode)

        if new_autosave_minutes != current_minutes:
            self._apply_autosave_interval(new_autosave_minutes)

        if new_point_label_max != current_point_label_max:
            self.settings.setValue("point_label_max_points", new_point_label_max)
            self.canvas.point_label_max_points = new_point_label_max
            self._update_plot()
            self.property_panel.update_point_labels_limit_note()

        if new_snap_to_grid != current_snap_to_grid:
            self.settings.setValue("snap_to_grid_enabled", new_snap_to_grid)
            self.snap_to_grid_enabled = new_snap_to_grid
        if new_snap_grid_interval != current_snap_grid_interval:
            self.settings.setValue("snap_grid_interval_px", new_snap_grid_interval)
            self.snap_grid_interval_px = new_snap_grid_interval

        # 作った画面をその場で訳し直す仕組みは無いので、次の起動からと知らせる
        if new_language != current_language:
            self.settings.setValue("language", new_language)
            QMessageBox.information(
                self, tr("表示言語の変更"),
                tr("表示言語の変更は、次回起動時に反映されます。")
            )

    def _update_autosave_menu_text(self):
        if not self.autosave_timer.isActive():
            self.autosave_interval_action.setText(tr("オートセーブ: 無効(&I)..."))
        else:
            minutes = self.autosave_timer.interval() // 60000
            self.autosave_interval_action.setText(tr("オートセーブ: {minutes}分間隔(&I)...").format(minutes=minutes))

    def _on_save_plot_template(self):
        """全サブプロットの見た目と全データセットのスタイルを *.graphica-style に保存する(データは含めない)。"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "書式テンプレートを保存", "", "Graphica Style Template (*.graphica-style)"
        )
        if not file_path:
            return
        if not (file_path.endswith('.graphica-style') or file_path.endswith('.json')):
            file_path += '.graphica-style'

        # 今の軸の欄の値はまだ all_plot_settings に入っていない
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
        """書式テンプレートを今のプロジェクトに当てる。Undo はできない。

        新しい形式(format_version あり)は、保存した順にサブプロットとデータセットへ繰り返し当てる(数が違ってもよい)。
        古い .json(plot_settings だけ)は今の軸だけに当てる。
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
                # 古い形式: 今の軸だけ
                settings = template_data.get('plot_settings', {})
                if not settings:
                    QMessageBox.warning(self, "読込エラー", "有効な書式設定がファイルに含まれていません。")
                    return
                self._apply_settings_to_ui_controls(settings)
                self._on_axis_setting_changed()

        except Exception as e:
            QMessageBox.warning(self, "読込エラー", f"テンプレートの読み込み中にエラーが発生しました:\n{e}")
            logger.exception("テンプレートの読み込み中にエラー")

    def _on_export_settings(self):
        """SETTINGS_EXPORT_SPEC のキーだけを JSON に書き出す(別の PC や研究室での共有用)。"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "設定・スタイルをエクスポート", "graphica_settings.json", "JSON Files (*.json)"
        )
        if not file_path:
            return
        if not file_path.endswith('.json'):
            file_path += '.json'

        exported = {}
        for key, value_type, default in SETTINGS_EXPORT_SPEC:
            if value_type is list:
                value = self.settings.value(key, default)
                # 要素が1つのリストを文字列で返すことがある
                if isinstance(value, str):
                    value = [value] if value else []
            else:
                value = self.settings.value(key, default, type=value_type)
            exported[key] = value

        payload = {'format_version': SETTINGS_EXPORT_FORMAT_VERSION, 'settings': exported}
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "設定・スタイルをエクスポート", f"エクスポートしました:\n{file_path}")
        except Exception as e:
            QMessageBox.warning(self, "保存エラー", f"設定のエクスポート中にエラーが発生しました:\n{e}")
            logger.exception("設定のエクスポート中にエラー")

    def _on_import_settings(self):
        """書き出した JSON から SETTINGS_EXPORT_SPEC のキーだけを QSettings に入れる(未知のキーは無視)。

        言語・ダークモード・パレットなどをその場で当て直すと影響が広いので、次の起動から効くと知らせる。
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "設定・スタイルをインポート", "", "JSON Files (*.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "設定・スタイルをインポート", f"ファイルの読み込みに失敗しました:\n{e}")
            logger.exception("設定のインポート中にエラー")
            return

        data = payload.get('settings') if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            # 手で書いた設定ファイルも読めるよう、settings キーが無くてもよい
            data = payload if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            QMessageBox.warning(self, "設定・スタイルをインポート", "対応していないファイル形式です。")
            return

        valid_keys = {key for key, _value_type, _default in SETTINGS_EXPORT_SPEC}
        imported_count = 0
        for key, value in data.items():
            if key not in valid_keys:
                continue
            self.settings.setValue(key, value)
            imported_count += 1

        if imported_count == 0:
            QMessageBox.information(self, "設定・スタイルをインポート", "インポート対象の設定が見つかりませんでした。")
            return

        QMessageBox.information(
            self, "設定・スタイルをインポート",
            f"{imported_count}件の設定を反映しました。\n"
            "表示言語など一部の設定は、次回起動時に反映されます。"
        )
