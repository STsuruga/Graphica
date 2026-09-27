"""プロジェクトの保存と読み込みのメニュー、書式テンプレート、環境設定、設定の書き出しと読み込み。"""
import json
import logging

from graphica.gui import notify
from graphica.gui import app_settings
from graphica.gui.dialogs import PreferencesDialog
from graphica.gui.datasets.operations.transfer import STYLE_ATTRS
from graphica.core.i18n import tr, get_language

logger = logging.getLogger(__name__)

AUTOSAVE_INTERVAL_MIN_BOUNDS = (0, 180)

TEMPLATE_FORMAT_VERSION = 1

# 書き出すキーは app_settings.EXPORTED_SETTINGS。ウィンドウの状態や最近使ったファイルなど、
# その環境だけの項目は入れない(別の PC に持ち込んでも意味が無いか害になる)
SETTINGS_EXPORT_FORMAT_VERSION = 1

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
        minutes, ok = notify.get_int(
            self, "オートセーブ間隔の設定",
            "オートセーブの間隔を分単位で入力してください (0で無効化):",
            current_minutes, min_minutes, max_minutes
        )
        if not ok:
            return

        self._apply_autosave_interval(minutes)

    def _apply_autosave_interval(self, minutes):
        """メニューと環境設定の両方から呼ばれる。"""
        app_settings.AUTOSAVE_INTERVAL_MIN.write(self.settings, minutes)
        if minutes <= 0:
            self.autosave_timer.stop()
            self.statusBar().showMessage("オートセーブを無効化しました", 3000)
        else:
            self.autosave_timer.start(minutes * 60 * 1000)
            self.statusBar().showMessage(f"オートセーブ間隔を{minutes}分に設定しました", 3000)

        self._update_autosave_menu_text()

    def _on_show_preferences(self):
        current_minutes = (self.autosave_timer.interval() // 60000) if self.autosave_timer.isActive() else 0
        # 言語だけは、未設定なら今の表示言語を既定にする
        current_language = app_settings.LANGUAGE.read(self.settings, default=get_language())
        current_autosave_dir = app_settings.AUTOSAVE_DIR.read(self.settings)
        current_point_label_max = app_settings.POINT_LABEL_MAX_POINTS.read(self.settings)
        current_snap_to_grid = app_settings.SNAP_TO_GRID_ENABLED.read(self.settings)
        current_snap_grid_interval = app_settings.SNAP_GRID_INTERVAL_PX.read(self.settings)

        # main_window がこの mixin を import しているので、関数の中で import する
        from graphica.core.plugin_api import get_loaded_plugin_records, get_plugin_registration_errors
        current_disabled_plugin_names = app_settings.disabled_plugin_names(self.settings)

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
            app_settings.DISABLED_PLUGINS.write(self.settings, list(new_disabled_plugin_names))

        if new_autosave_dir != current_autosave_dir:
            app_settings.AUTOSAVE_DIR.write(self.settings, new_autosave_dir)
            self._update_autosave_path()

        # 表示メニューのチェック経由で切り替える(toggled から _on_toggle_dark_mode が適用し、チェックの状態も揃う)
        if new_dark_mode != self.canvas.dark_mode:
            self.dark_mode_action.setChecked(new_dark_mode)

        if new_autosave_minutes != current_minutes:
            self._apply_autosave_interval(new_autosave_minutes)

        if new_point_label_max != current_point_label_max:
            app_settings.POINT_LABEL_MAX_POINTS.write(self.settings, new_point_label_max)
            self.canvas.point_label_max_points = new_point_label_max
            self._update_plot()
            self.property_panel.update_point_labels_limit_note()

        if new_snap_to_grid != current_snap_to_grid:
            app_settings.SNAP_TO_GRID_ENABLED.write(self.settings, new_snap_to_grid)
            self.snap_to_grid_enabled = new_snap_to_grid
        if new_snap_grid_interval != current_snap_grid_interval:
            app_settings.SNAP_GRID_INTERVAL_PX.write(self.settings, new_snap_grid_interval)
            self.snap_grid_interval_px = new_snap_grid_interval

        # 作った画面をその場で訳し直す仕組みは無いので、次の起動からと知らせる
        if new_language != current_language:
            app_settings.LANGUAGE.write(self.settings, new_language)
            notify.information(
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
        file_path, _ = notify.get_save_file_name(
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
            notify.warning(self, "保存エラー", f"テンプレートの保存中にエラーが発生しました:\n{e}")
            logger.exception("テンプレートの保存中にエラー")

    def _on_load_plot_template(self):
        """書式テンプレートを今のプロジェクトに当てる。Undo はできない。

        新しい形式(format_version あり)は、保存した順にサブプロットとデータセットへ繰り返し当てる(数が違ってもよい)。
        古い .json(plot_settings だけ)は今の軸だけに当てる。
        """
        file_path, _ = notify.get_open_file_name(
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
                    notify.warning(self, "読込エラー", "有効な書式設定がファイルに含まれていません。")
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
                    notify.warning(self, "読込エラー", "有効な書式設定がファイルに含まれていません。")
                    return
                self._apply_settings_to_ui_controls(settings)
                self._on_axis_setting_changed()

        except Exception as e:
            notify.warning(self, "読込エラー", f"テンプレートの読み込み中にエラーが発生しました:\n{e}")
            logger.exception("テンプレートの読み込み中にエラー")

    def _on_export_settings(self):
        """app_settings.EXPORTED_SETTINGS のキーだけを JSON に書き出す(別の PC や研究室での共有用)。"""
        file_path, _ = notify.get_save_file_name(
            self, "設定・スタイルをエクスポート", "graphica_settings.json", "JSON Files (*.json)"
        )
        if not file_path:
            return
        if not file_path.endswith('.json'):
            file_path += '.json'

        exported = {setting.key: setting.read_for_export(self.settings) for setting in app_settings.EXPORTED_SETTINGS}

        payload = {'format_version': SETTINGS_EXPORT_FORMAT_VERSION, 'settings': exported}
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
            notify.information(self, "設定・スタイルをエクスポート", f"エクスポートしました:\n{file_path}")
        except Exception as e:
            notify.warning(self, "保存エラー", f"設定のエクスポート中にエラーが発生しました:\n{e}")
            logger.exception("設定のエクスポート中にエラー")

    def _on_import_settings(self):
        """書き出した JSON から app_settings.EXPORTED_SETTINGS のキーだけを QSettings に入れる(未知のキーは無視)。

        言語・ダークモード・パレットなどをその場で当て直すと影響が広いので、次の起動から効くと知らせる。
        """
        file_path, _ = notify.get_open_file_name(
            self, "設定・スタイルをインポート", "", "JSON Files (*.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            notify.warning(self, "設定・スタイルをインポート", f"ファイルの読み込みに失敗しました:\n{e}")
            logger.exception("設定のインポート中にエラー")
            return

        data = payload.get('settings') if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            # 手で書いた設定ファイルも読めるよう、settings キーが無くてもよい
            data = payload if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            notify.warning(self, "設定・スタイルをインポート", "対応していないファイル形式です。")
            return

        valid_keys = {setting.key for setting in app_settings.EXPORTED_SETTINGS}
        imported_count = 0
        for key, value in data.items():
            if key not in valid_keys:
                continue
            self.settings.setValue(key, value)
            imported_count += 1

        if imported_count == 0:
            notify.information(self, "設定・スタイルをインポート", "インポート対象の設定が見つかりませんでした。")
            return

        notify.information(
            self, "設定・スタイルをインポート",
            f"{imported_count}件の設定を反映しました。\n"
            "表示言語など一部の設定は、次回起動時に反映されます。"
        )
