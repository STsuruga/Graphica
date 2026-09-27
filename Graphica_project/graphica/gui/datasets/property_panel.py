"""データセットのプロパティ欄: 選んだデータセットの値を欄に映し、欄の変更をデータセットに当てる。"""
import logging
import numpy as np

from graphica.core.analysis import sample_standard_deviation
from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE
from graphica.core.label_utils import infer_axis_label_from_column_name
from graphica.gui.binding import Binder
from graphica.gui.dataset_bindings import DATASET_PROPERTY_BINDINGS, NO_ERROR_COLUMN_LABEL

logger = logging.getLogger(__name__)


class DatasetPropertyPanel:
    """プロパティ欄のウィジェットはタブ(PlotterApp)が持つので、タブを受け取って読み書きする。"""

    def __init__(self, app):
        self._app = app
        self._binder = Binder(app, DATASET_PROPERTY_BINDINGS)

    def connect_signals(self):
        """表(gui/dataset_bindings.py)の欄の変更をつなぐ。"""
        self._binder.connect(watch=self.watch)

    def watch(self, signal, widget):
        """widget が変わったら、その属性だけを選択中のデータセットに当てる。"""
        signal.connect(lambda *_: self.on_property_changed(widget))

    def on_subplot_target_changed(self, index):
        dataset = self._app._get_current_dataset()
        if dataset is None or index == -1:
            return
        if dataset.subplot_target == index:
            return

        self._app._push_dataset_property_command(
            dataset,
            {'subplot_target': dataset.subplot_target},
            {'subplot_target': index},
            description="描画先プロットの変更"
        )

    def on_dataset_selected(self, current_item, previous_item):
        self.update_ui_state()
        self._app._notify_plugins_selection_changed()

    def on_legend_name_changed(self):
        dataset = self._app._get_current_dataset()
        if dataset is None:
            return

        new_name = self._app.ui.legend_name_edit.text()

        self._app._push_dataset_property_command(
            dataset,
            {'name': dataset.name},
            {'name': new_name},
            description="凡例名の変更"
        )

    def on_point_labels_toggled(self, checked):
        """
        点数が上限を超えるデータセットには、ラベルを描かずに理由を欄に出す(update_point_labels_limit_note)。
        ラベル1件の描画に約2.5msかかり、上限を超えて描かせると再描画のたびに GUI が長く止まるため。
        """
        self.on_property_changed(self._app.point_labels_checkbox)
        self.update_point_labels_limit_note()

    def update_point_labels_limit_note(self):
        """ラベル表示が有効なのに点数が上限を超えるデータセットがあれば、その理由をチェックボックスの下に出す。"""
        note = getattr(self._app, 'point_labels_limit_note', None)
        if note is None:
            return
        max_points = self._app.canvas.point_label_max_points
        over_limit = [ds for ds in self._app._get_selected_datasets()
                      if ds.show_point_labels and len(ds.visible_df) > max_points]
        if not over_limit:
            note.setVisible(False)
            return
        largest = max(len(ds.visible_df) for ds in over_limit)
        note.setText(
            f"点数({largest:,}件)が表示上限({max_points:,}件)を超えているため、"
            "ラベルは表示されません。上限は「環境設定」で変更できますが、"
            "点数が多いと描画に時間がかかります(1,000件で約2秒)。"
        )
        note.setVisible(True)

    def on_property_changed(self, widget=None):
        """
        widget が表す属性だけを、選択中のデータセットすべてに当てる。
        全属性をまとめて当てると、複数選択のとき触っていない属性まで1つの値に揃ってしまう。
        """
        selected_datasets = self._app._get_selected_datasets()
        if not selected_datasets:
            return

        binding = self._binder.binding_for(widget)
        if binding is None:
            return
        attr_name, new_value = binding.key, self._binder.read(binding)

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self._app.undo_stack.beginMacro(f"プロパティの一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._app._push_dataset_property_command(
                dataset, {attr_name: getattr(dataset, attr_name)}, {attr_name: new_value},
                description="プロパティ変更"
            )
        if is_batch:
            self._app.undo_stack.endMacro()

    def update_gradient_controls_visibility(self):
        """
        グラデーションは線か塗りのある種別('Line'/'Line+Scatter'/'Area')でだけ出す。
        対象(線/塗り/両方)を選べるのは 'Area' だけなので、その欄は 'Area' のときだけ出す。
        """
        dataset = self._app._get_current_dataset()
        plot_type = dataset.plot_type if dataset is not None else self._app.ui.plot_type_combo.currentText()
        supports_gradient = plot_type in ('Line', 'Line+Scatter', 'Area')

        self._app.gradient_checkbox.setVisible(supports_gradient)

        show_detail = supports_gradient and self._app.gradient_checkbox.isChecked()
        self._app.gradient_color2_label.setVisible(show_detail)
        self._app.gradient_color2_picker.setVisible(show_detail)

        show_target_combo = show_detail and plot_type == 'Area'
        self._app.gradient_target_label.setVisible(show_target_combo)
        self._app.gradient_target_combo.setVisible(show_target_combo)
        self._app._update_property_section_visibility()

    def update_smoothing_control_visibility(self):
        """
        平滑化は線で結ぶ種別('Line'/'Line+Scatter')でだけ出す。ほかの種別では平滑化した線が
        マーカー・棒・塗りを置き換えてしまう(描画側も同じ条件で確かめている)。
        """
        dataset = self._app._get_current_dataset()
        plot_type = dataset.plot_type if dataset is not None else self._app.ui.plot_type_combo.currentText()
        is_smoothable_type = plot_type in ('Line', 'Line+Scatter')
        self._app.ui.smoothing_checkbox.setVisible(is_smoothable_type)
        # 手法の欄はチェックが外れている間も隠さず無効にする(出たり消えたりで配置が揺れないように)
        self._app.smoothing_method_label.setVisible(is_smoothable_type)
        self._app.smoothing_method_combo.setVisible(is_smoothable_type)
        self._app.smoothing_method_combo.setEnabled(self._app.ui.smoothing_checkbox.isChecked())
        self._app._update_property_section_visibility()

    def update_error_display_control_items(self):
        """
        棒と面では誤差の帯が合わない(面は塗りと重なる)ので、「誤差バンド」「両方」を選べなくする。
        保存済みの値は変えない。
        """
        dataset = self._app._get_current_dataset()
        plot_type = dataset.plot_type if dataset is not None else self._app.ui.plot_type_combo.currentText()
        band_ok = plot_type not in ('Bar', 'Area')
        model = self._app.error_display_combo.model()
        for value in ('band', 'both'):
            index = self._app.error_display_combo.findData(value)
            if index != -1:
                model.item(index).setEnabled(band_ok)

    def update_waterfall_controls_visibility(self):
        """
        オフセットなどの詳細はウォーターフォールを有効にしたときだけ出す。
        2Dマップは描画でウォーターフォールの経路を通らないので、チェックボックスごと隠す。
        """
        dataset = self._app._get_current_dataset()
        is_2d = dataset is not None and dataset.data_kind == '2d_grid'
        if is_2d:
            for widget in (
                self._app.waterfall_checkbox,
                self._app.waterfall_offset_x_label, self._app.waterfall_offset_x_spinbox,
                self._app.waterfall_offset_y_label, self._app.waterfall_offset_y_spinbox,
                self._app.waterfall_occlusion_checkbox, self._app.waterfall_depth_checkbox,
                self._app.waterfall_depth_ratio_label, self._app.waterfall_depth_ratio_spinbox,
            ):
                widget.setVisible(False)
            self._app._update_property_section_visibility()
            return

        self._app.waterfall_checkbox.setVisible(True)
        show_offsets = self._app.waterfall_checkbox.isChecked()

        self._app.waterfall_offset_x_label.setVisible(show_offsets)
        self._app.waterfall_offset_x_spinbox.setVisible(show_offsets)
        self._app.waterfall_offset_y_label.setVisible(show_offsets)
        self._app.waterfall_offset_y_spinbox.setVisible(show_offsets)
        self._app.waterfall_occlusion_checkbox.setVisible(show_offsets)
        self._app.waterfall_depth_checkbox.setVisible(show_offsets)

        show_depth_ratio = show_offsets and self._app.waterfall_depth_checkbox.isChecked()
        self._app.waterfall_depth_ratio_label.setVisible(show_depth_ratio)
        self._app.waterfall_depth_ratio_spinbox.setVisible(show_depth_ratio)
        self._app._update_property_section_visibility()

    def update_ui_state(self):
        """選択に合わせて欄の有効/無効と中身を更新する(何も選ばれていなければ空にする)。"""
        self._app._update_subplot_combos()

        # フォルダも選べるので、「何か選ばれているか」(削除用)と「データセットが選ばれているか」を分ける
        current_dataset = self._app._get_current_dataset()
        selected_datasets = self._app._get_selected_datasets()
        has_any_selection = bool(self._app.ui.dataset_list_widget.selectedItems())
        has_dataset_selection = bool(selected_datasets)

        # 節の開閉ボタンは選択が無くても押せるよう、入力欄だけを無効にする
        self._app._set_dataset_property_fields_enabled(has_dataset_selection)

        self._app.ui.remove_dataset_button.setEnabled(has_any_selection)
        self._app.duplicate_dataset_button.setEnabled(has_dataset_selection)
        self._app.view_edit_data_button.setEnabled(has_dataset_selection)
        self._app.auto_color_button.setEnabled(has_dataset_selection)

        self._app.fit_curve_button.setEnabled(has_dataset_selection)
        self._app.find_peaks_button.setEnabled(has_dataset_selection)

        self._app.subplot_target_combo.setEnabled(has_dataset_selection)
        self._app.use_secondary_y_checkbox.setEnabled(has_dataset_selection)
        self._app.x_col_combo.setEnabled(has_dataset_selection)
        self._app.y_col_combo.setEnabled(has_dataset_selection)
        self._app.x_err_col_combo.setEnabled(has_dataset_selection)
        self._app.y_err_col_combo.setEnabled(has_dataset_selection)
        self._app.error_display_combo.setEnabled(has_dataset_selection)
        self._app.nan_policy_combo.setEnabled(has_dataset_selection)

        # current_dataset はカレントがフォルダのときや選択が無いときは None
        if current_dataset is not None:
            dataset = current_dataset

            # 欄に値を入れる間は、変更の通知でデータセットを書き換えないようにする
            self._binder.block_signals(True)
            self._binder.restore(dataset, getattr)
            is_range_auto = dataset.vmin is None and dataset.vmax is None
            self._app.vmin_spinbox.setEnabled(not is_range_auto)
            self._app.vmax_spinbox.setEnabled(not is_range_auto)
            self._binder.block_signals(False)
            self.update_gradient_controls_visibility()
            self.update_waterfall_controls_visibility()
            self.update_smoothing_control_visibility()
            self.update_error_display_control_items()
            self.update_2d_controls_visibility()
            self.update_point_labels_limit_note()

            self._app.x_col_combo.blockSignals(True)
            self._app.y_col_combo.blockSignals(True)

            all_columns = dataset.df.columns.tolist()
            self._app.x_col_combo.clear()
            self._app.y_col_combo.clear()
            self._app.x_col_combo.addItems(all_columns)
            self._app.y_col_combo.addItems(all_columns)

            self._app.x_col_combo.setCurrentText(dataset.x_col_name)
            self._app.y_col_combo.setCurrentText(dataset.y_col_name)

            self._app.x_col_combo.blockSignals(False)
            self._app.y_col_combo.blockSignals(False)

            self._app.x_err_col_combo.blockSignals(True)
            self._app.y_err_col_combo.blockSignals(True)

            self._app.x_err_col_combo.clear()
            self._app.y_err_col_combo.clear()
            self._app.x_err_col_combo.addItems([NO_ERROR_COLUMN_LABEL] + all_columns)
            self._app.y_err_col_combo.addItems([NO_ERROR_COLUMN_LABEL] + all_columns)
            self._app.x_err_col_combo.setCurrentText(dataset.x_err_col_name or NO_ERROR_COLUMN_LABEL)
            self._app.y_err_col_combo.setCurrentText(dataset.y_err_col_name or NO_ERROR_COLUMN_LABEL)

            self._app.x_err_col_combo.blockSignals(False)
            self._app.y_err_col_combo.blockSignals(False)

            self._app.z_col_combo.blockSignals(True)
            self._app.z_col_combo.clear()
            self._app.z_col_combo.addItems(all_columns)
            if dataset.z_col_name:
                self._app.z_col_combo.setCurrentText(dataset.z_col_name)
            self._app.z_col_combo.blockSignals(False)

            if dataset.fit_info:
                self._app.fit_info_label.setVisible(True)
                self._app.fit_info_textedit.setVisible(True)
                self._app.fit_info_textedit.setText(dataset.fit_info)
            else:
                self._app.fit_info_label.setVisible(False)
                self._app.fit_info_textedit.setVisible(False)
                self._app.fit_info_textedit.clear()

            self.update_stats_summary_label(dataset)

            self._app.residual_panel.refresh(dataset)

            self._app.provenance_panel.refresh(dataset, self._app.project)

        else:
            # 空にするのは表示だけ。信号を出すと、フォルダを今の項目にしたままデータセットを選んでいるとき
            # 点ラベルの列が空の文字としてデータセットに書き込まれる
            column_combos = (self._app.x_col_combo, self._app.y_col_combo, self._app.x_err_col_combo,
                             self._app.y_err_col_combo, self._app.point_label_col_combo, self._app.z_col_combo)
            for combo in column_combos:
                combo.blockSignals(True)
                combo.clear()
                combo.blockSignals(False)
            self.update_2d_controls_visibility()

            self._app.fit_info_label.setVisible(False)
            self._app.fit_info_textedit.setVisible(False)
            self._app.fit_info_textedit.clear()
            self._app.residual_panel.refresh(None)
            self._app.provenance_panel.refresh(None, self._app.project)

            self._app.gradient_checkbox.setVisible(False)
            self._app.gradient_color2_label.setVisible(False)
            self._app.gradient_color2_picker.setVisible(False)
            self._app.gradient_target_label.setVisible(False)
            self._app.gradient_target_combo.setVisible(False)

            self._app.waterfall_checkbox.setVisible(False)
            self._app.waterfall_offset_x_label.setVisible(False)
            self._app.waterfall_offset_x_spinbox.setVisible(False)
            self._app.waterfall_offset_y_label.setVisible(False)
            self._app.waterfall_offset_y_spinbox.setVisible(False)
            self._app.waterfall_occlusion_checkbox.setVisible(False)
            self._app.waterfall_depth_checkbox.setVisible(False)
            self._app.waterfall_depth_ratio_label.setVisible(False)
            self._app.waterfall_depth_ratio_spinbox.setVisible(False)

            self._app.stats_summary_label.setText("-")
            self._app.dataset_mini_stats_label.setText("-")
            # 行を隠したあとで見出しもそろえる(起動直後もこの経路を通る)
            self._app._update_property_section_visibility()

    def update_stats_summary_label(self, dataset):
        """Y の件数・平均・標準偏差・最小・最大を、プロパティ欄とデータセット一覧の下の1行に出す(NaN は除く)。"""
        try:
            y = np.asarray(dataset.y_data, dtype=float)
            valid = y[~np.isnan(y)]
            if len(valid) == 0:
                self._app.stats_summary_label.setText("-")
                self._app.dataset_mini_stats_label.setText(dataset.name)
                return
            # 標本標準偏差(n−1)。1点では定義できないので「-」
            std = sample_standard_deviation(valid)
            std_text = "-" if np.isnan(std) else f"{std:.4g}"
            self._app.stats_summary_label.setText(
                f"件数: {len(valid)}   平均: {np.mean(valid):.4g}   "
                f"標準偏差: {std_text}   最小: {np.min(valid):.4g}   最大: {np.max(valid):.4g}"
            )
            self._app.dataset_mini_stats_label.setText(
                f"{dataset.name} 〈n={len(valid)}, 平均={np.mean(valid):.4g}, "
                f"SD={std_text}〉"
            )
        except (TypeError, ValueError):
            self._app.stats_summary_label.setText("-")
            self._app.dataset_mini_stats_label.setText(dataset.name)

    def on_plot_column_changed(self):
        dataset = self._app._get_current_dataset()
        if dataset is None:
            return

        new_x_col = self._app.x_col_combo.currentText()
        new_y_col = self._app.y_col_combo.currentText()

        # 変わった列だけを含める(欄が空のこともある)
        old_values, new_values = {}, {}
        if new_x_col and new_x_col in dataset.df.columns and new_x_col != dataset.x_col_name:
            old_values['x_col_name'] = dataset.x_col_name
            new_values['x_col_name'] = new_x_col
        if new_y_col and new_y_col in dataset.df.columns and new_y_col != dataset.y_col_name:
            old_values['y_col_name'] = dataset.y_col_name
            new_values['y_col_name'] = new_y_col

        self._app._push_dataset_property_command(dataset, old_values, new_values, description="プロット列の変更")

        # 描画先の軸ラベルが空なら列名から埋める。軸の設定は Undo の仕組みが別なので Undo には含めない。
        if 'x_col_name' in new_values:
            self.maybe_autofill_axis_label(dataset.subplot_target, 'x_label', new_values['x_col_name'])
        if 'y_col_name' in new_values:
            self.maybe_autofill_axis_label(dataset.subplot_target, 'y_label', new_values['y_col_name'])

    def maybe_autofill_axis_label(self, subplot_index, label_key, column_name):
        """
        その軸のラベルが空のときだけ、列名から推し量ったラベルで埋める。
        今表示している軸なら欄に書き込み(保存と再描画は欄の変更の経路に任せる)、そうでなければ設定を直接書き換える
        (表示していない軸のラベルを、表示中の軸の欄に書いてしまわないように)。
        """
        if subplot_index is None or not (0 <= subplot_index < len(self._app.project.all_plot_settings)):
            return
        inferred = infer_axis_label_from_column_name(column_name)
        if not inferred:
            return
        current_settings = self._app.project.all_plot_settings[subplot_index]
        if current_settings.get(label_key):
            return

        if subplot_index == self._app.project.active_axis_index:
            label_edit = self._app.ui.x_label_text_edit if label_key == 'x_label' else self._app.ui.y_label_text_edit
            if not label_edit.text():
                label_edit.setText(inferred)
        else:
            current_settings[label_key] = inferred
            self._app._update_plot()

    def on_data_2d_toggled(self, checked):
        """2Dマップとして扱うかを切り替える。Z 列が未設定なら X/Y 以外の最初の列を選んでおく。"""
        dataset = self._app._get_current_dataset()
        if dataset is None:
            return
        new_data_kind = '2d_grid' if checked else '1d'
        if dataset.data_kind == new_data_kind:
            self.update_2d_controls_visibility()
            return

        old_values = {'data_kind': dataset.data_kind}
        new_values = {'data_kind': new_data_kind}
        if new_data_kind == '2d_grid' and not dataset.z_col_name:
            candidates = [
                c for c in dataset.df.columns
                if c not in (dataset.x_col_name, dataset.y_col_name)
            ]
            if candidates:
                old_values['z_col_name'] = dataset.z_col_name
                new_values['z_col_name'] = candidates[0]

        self._app._push_dataset_property_command(dataset, old_values, new_values, description="2Dグリッドデータの切り替え")
        self.update_2d_controls_visibility()

    def on_z_column_changed(self):
        dataset = self._app._get_current_dataset()
        if dataset is None:
            return
        new_z_col = self._app.z_col_combo.currentText()
        if not new_z_col or new_z_col not in dataset.df.columns or new_z_col == dataset.z_col_name:
            return
        self._app._push_dataset_property_command(
            dataset, {'z_col_name': dataset.z_col_name}, {'z_col_name': new_z_col},
            description="Z軸列の変更"
        )

    def on_2d_value_range_changed(self):
        """値域を自動にしている間は vmin/vmax を None にする(描画時に実データの範囲を使う)。"""
        dataset = self._app._get_current_dataset()
        if dataset is None:
            return
        is_auto = self._app.color_range_auto_checkbox.isChecked()
        self._app.vmin_spinbox.setEnabled(not is_auto)
        self._app.vmax_spinbox.setEnabled(not is_auto)

        new_vmin = None if is_auto else self._app.vmin_spinbox.value()
        new_vmax = None if is_auto else self._app.vmax_spinbox.value()
        if new_vmin == dataset.vmin and new_vmax == dataset.vmax:
            return
        self._app._push_dataset_property_command(
            dataset,
            {'vmin': dataset.vmin, 'vmax': dataset.vmax},
            {'vmin': new_vmin, 'vmax': new_vmax},
            description="値域の変更"
        )

    def update_2d_controls_visibility(self):
        """
        Z 列・カラーマップ・値域は、2Dマップと、3列目の値で点を色分けする散布図の両方で使う。
        表示方式・等高線・補間方法は2Dマップだけ。
        """
        dataset = self._app._get_current_dataset()
        # 選択が無いときは隠す(2Dのチェックには前に選んでいたデータセットの値が残っている)
        is_2d = dataset is not None and dataset.data_kind == '2d_grid'
        is_color_by_column = (
            dataset is not None
            and dataset.data_kind != '2d_grid'
            and dataset.plot_type == COLOR_BY_COLUMN_PLOT_TYPE
        )
        shared_with_color_scatter = is_2d or is_color_by_column
        for widget in (
            self._app.z_col_label, self._app.z_col_combo,
            self._app.colormap_label, self._app.colormap_combo,
            self._app.color_range_auto_checkbox,
            self._app.vmin_label, self._app.vmin_spinbox,
            self._app.vmax_label, self._app.vmax_spinbox,
        ):
            widget.setVisible(shared_with_color_scatter)

        for widget in (
            self._app.map_display_mode_label, self._app.map_display_mode_combo,
            self._app.contour_levels_label, self._app.contour_levels_spinbox,
            self._app.grid_interp_method_label, self._app.grid_interp_method_combo,
        ):
            widget.setVisible(is_2d)

        self._app._update_property_section_visibility()

    def on_error_column_changed(self):
        dataset = self._app._get_current_dataset()
        if dataset is None:
            return

        new_x_err = self._app.x_err_col_combo.currentText()
        new_y_err = self._app.y_err_col_combo.currentText()
        new_x_err_col = None if (not new_x_err or new_x_err == NO_ERROR_COLUMN_LABEL) else new_x_err
        new_y_err_col = None if (not new_y_err or new_y_err == NO_ERROR_COLUMN_LABEL) else new_y_err

        old_values, new_values = {}, {}
        if new_x_err_col != dataset.x_err_col_name:
            old_values['x_err_col_name'] = dataset.x_err_col_name
            new_values['x_err_col_name'] = new_x_err_col
        if new_y_err_col != dataset.y_err_col_name:
            old_values['y_err_col_name'] = dataset.y_err_col_name
            new_values['y_err_col_name'] = new_y_err_col

        self._app._push_dataset_property_command(dataset, old_values, new_values, description="誤差列(エラーバー)の変更")

    def on_data_structure_changed(self):
        """データエディタでデータが変わったら、列の選択肢と描画を作り直す。"""
        if self._app._get_current_dataset() is None:
            return

        self.update_ui_state()
        self._app._update_plot()

    def on_secondary_y_changed(self):
        selected_datasets = self._app._get_selected_datasets()
        if not selected_datasets:
            return

        new_value = self._app.use_secondary_y_checkbox.isChecked()

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self._app.undo_stack.beginMacro(f"第2Y軸使用の一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._app._push_dataset_property_command(
                dataset,
                {'use_secondary_y': dataset.use_secondary_y},
                {'use_secondary_y': new_value},
                description="第2Y軸使用の変更"
            )
        if is_batch:
            self._app.undo_stack.endMacro()
