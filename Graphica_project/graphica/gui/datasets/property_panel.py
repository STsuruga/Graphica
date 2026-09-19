"""データセットのプロパティ欄: 選んだデータセットの値を欄に映し、欄の変更をデータセットに当てる。"""
import logging
import numpy as np

from graphica.core.analysis import sample_standard_deviation
from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE, linestyle_name
from graphica.core.label_utils import infer_axis_label_from_column_name

logger = logging.getLogger(__name__)

# 誤差列の欄で「誤差列を使わない」を表す選択肢
NO_ERROR_COLUMN_LABEL = "(なし)"
# データ点ラベルの内容の欄で「Y値そのもの」を表す選択肢
POINT_LABEL_Y_VALUE_LABEL = "Y値"


class DatasetPropertyPanel:
    """
    プロパティ欄のウィジェットはタブ(PlotterApp)が持つので、タブを受け取って読み書きする。
    """

    def __init__(self, app):
        self._app = app

    def watch(self, signal, widget):
        """widget が変わったら、その属性だけを選択中のデータセットに当てる。"""
        signal.connect(lambda *_: self.on_property_changed(widget))

    def on_subplot_target_changed(self, index):
        """
        データセットの「描画先プロット」コンボボックスが変更されたときに呼び出されます。

        Args:
            index (int): 新しく選択された描画先の軸インデックス。
        """
        dataset = self._app._get_current_dataset()
        if dataset is None or index == -1:
            return
        if dataset.subplot_target == index:
            return

        # Dataset オブジェクトが持つ描画先インデックスを更新
        # (データが移動するため、外観のみの更新ではなく _update_plot による全体再描画が必要。
        #  これは _refresh_after_dataset_property_change 内で行われる)
        self._app._push_dataset_property_command(
            dataset,
            {'subplot_target': dataset.subplot_target},
            {'subplot_target': index},
            description="描画先プロットの変更"
        )

    def on_dataset_selected(self, current_item, previous_item):
        """
        UIのデータセットリスト (dataset_list_widget) で選択されている項目が
        変更されたときに呼び出されるスロット。

        Args:
            current_item (QTreeWidgetItem): 新しく選択されたアイテム。
            previous_item (QTreeWidgetItem): 以前選択されていたアイテム。
        """
        self.update_ui_state()  # 選んだデータセットのプロパティをパネルに読み込む
        self._app._notify_plugins_selection_changed()

    def on_legend_name_changed(self):
        """
        「凡例名」テキストボックス (legend_name_edit) の編集が完了したときに
        呼び出されるスロット (editingFinished シグナル)。
        """
        dataset = self._app._get_current_dataset()
        if dataset is None:
            return

        new_name = self._app.ui.legend_name_edit.text()

        # Dataset オブジェクトの name 属性を更新 (Undo/Redo可能にする)
        # リスト表示の同期とプロット再描画は _refresh_after_dataset_property_change が行う
        self._app._push_dataset_property_command(
            dataset,
            {'name': dataset.name},
            {'name': new_name},
            description="凡例名の変更"
        )

    def on_point_labels_toggled(self, checked):
        """
        「データ点にラベルを表示」チェックボックスが切り替えられたときの処理(項目105)。

        ★ v1.4.2 で確認ポップアップを廃止した。以前は点数が環境設定の上限を超えると
          「表示しますか?」と確認していたが、「はい」を選んでも描画側
          (MplCanvas._draw_data)が上限でラベルを省くため、何も表示されなかった。
          実測では ax.annotate() 1件あたり約2.5msかかり、しかもプロパティを変える
          たびの再描画で毎回その時間がかかる(1,000点で約2.5秒、20,000点で約68秒、
          GUIスレッドを止める)。上限を超えて描画させると操作不能になりうるため、
          上限超過時は描かないまま、理由をパネルに表示する(update_point_labels_limit_note)。
        """
        self.on_property_changed(self._app.point_labels_checkbox)
        self.update_point_labels_limit_note()

    def update_point_labels_limit_note(self):
        """
        選択中のデータセットのうち、ラベル表示が有効なのに点数が表示上限を超えて
        いるものがあれば、その理由をチェックボックスの下に表示する。
        """
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
        データセットのプロパティ (プロットタイプ、線種、マーカー、平滑化など) の
        UIコントロールが変更されたときに呼び出されるスロット。
        6つの異なるUIコントロールがすべてこのスロットに接続されているため、
        widget(変わったウィジェット)から属性を特定し、
        「そのプロパティだけ」を選択中の(複数可)全データセットに一括適用する。
        (仮に全プロパティを常に一括適用してしまうと、複数選択時に選択されている
        データセット同士でプロパティ値が異なる場合、触っていないプロパティまで
        1つの値に揃えられてしまうため)
        """
        selected_datasets = self._app._get_selected_datasets()
        if not selected_datasets:
            return

        marker_text = self._app.ui.marker_combo.currentText()
        # ウィジェット -> (属性名, 現在のUI値) の対応表
        field_by_widget = {
            self._app.ui.plot_type_combo: ('plot_type', self._app.ui.plot_type_combo.currentText()),
            self._app.ui.linestyle_combo: ('linestyle', self._app.ui.linestyle_combo.currentText()),
            self._app.ui.linewidth_spinbox: ('linewidth', self._app.ui.linewidth_spinbox.value()),
            # ★ UIで "None" が選択されたら、属性には None を設定
            self._app.ui.marker_combo: ('marker', None if marker_text == 'None' else marker_text),
            self._app.ui.markersize_spinbox: ('markersize', self._app.ui.markersize_spinbox.value()),
            self._app.ui.smoothing_checkbox: ('smoothing', self._app.ui.smoothing_checkbox.isChecked()),
            self._app.smoothing_method_combo: ('smoothing_method', self._app.smoothing_method_combo.currentData()),
            self._app.alpha_spinbox: ('alpha', self._app.alpha_spinbox.value()),
            self._app.point_labels_checkbox: ('show_point_labels', self._app.point_labels_checkbox.isChecked()),
            self._app.point_label_col_combo: (
                'point_label_col_name',
                None if self._app.point_label_col_combo.currentText() == POINT_LABEL_Y_VALUE_LABEL
                else self._app.point_label_col_combo.currentText()
            ),
            # プロットへのグラデーション適用(項目79)
            self._app.gradient_checkbox: ('gradient_enabled', self._app.gradient_checkbox.isChecked()),
            self._app.gradient_target_combo: ('gradient_target', self._app.gradient_target_combo.currentData()),
            # ウォーターフォールプロット(項目80、項目109でplot_typeとは独立したフラグに変更)
            self._app.waterfall_checkbox: ('waterfall_enabled', self._app.waterfall_checkbox.isChecked()),
            self._app.waterfall_offset_x_spinbox: ('waterfall_offset_x', self._app.waterfall_offset_x_spinbox.value()),
            self._app.waterfall_offset_y_spinbox: ('waterfall_offset_y', self._app.waterfall_offset_y_spinbox.value()),
            self._app.waterfall_occlusion_checkbox: (
                'waterfall_occlusion_enabled', self._app.waterfall_occlusion_checkbox.isChecked()
            ),
            # 斜向/立体風トグル(項目120、C-514)
            self._app.waterfall_depth_checkbox: (
                'waterfall_depth_shrink_enabled', self._app.waterfall_depth_checkbox.isChecked()
            ),
            self._app.waterfall_depth_ratio_spinbox: (
                'waterfall_depth_shrink_ratio', self._app.waterfall_depth_ratio_spinbox.value()
            ),
            # 誤差の表示形式(項目C-502)
            self._app.error_display_combo: ('error_display', self._app.error_display_combo.currentData()),
            # 欠損値(NaN)の方針設定(項目C-201)
            self._app.nan_policy_combo: ('nan_policy', self._app.nan_policy_combo.currentData()),
            # 2Dグリッドデータ(ヒートマップ、項目C-508)のカラーマップ・補間方法。
            # data_kind/z_col_name/vmin/vmaxはそれぞれ専用ハンドラ
            # (on_data_2d_toggled/on_z_column_changed/on_2d_value_range_changed)
            # が個別に扱うため、ここには含めない。
            self._app.colormap_combo: ('colormap', self._app.colormap_combo.currentText()),
            self._app.grid_interp_method_combo: ('grid_interp_method', self._app.grid_interp_method_combo.currentText()),
            # 2Dマップの表示方式・等高線レベル数(項目C-509)
            self._app.map_display_mode_combo: ('map_display_mode', self._app.map_display_mode_combo.currentData()),
            self._app.contour_levels_spinbox: ('contour_levels', self._app.contour_levels_spinbox.value()),
        }

        changed = field_by_widget.get(widget)
        if changed is None:
            return # 想定外の呼び出し元 (通常は発生しない)
        attr_name, new_value = changed

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
        プロットへのグラデーション適用(項目79)のUIコントロールの表示/非表示を、
        現在選択中データセットの plot_type に応じて更新する。
        - グラデーション自体(チェックボックス・終端色)は 'Line'/'Line+Scatter'/'Area'
          でのみ意味を持つ('Scatter'/'Bar'では線も塗りも無いため隠す)。
        - 対象(線/塗り/両方)コンボは、複数の対象から選べる 'Area' でのみ表示する
          ('Line'/'Line+Scatter' では常に「線」一択のため、コンボを見せる意味がない)。
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
        # C-1: 中身が全部隠れたサブセクションは見出しごと畳む
        self._app._update_property_section_visibility()

    def update_smoothing_control_visibility(self):
        """
        平滑化(CubicSpline)チェックボックスの表示/非表示を、現在選択中データセットの
        plot_type に応じて更新する(_update_gradient_controls_visibilityと同じ
        パターン)。平滑化は「線で結んだ曲線」を滑らかにする機能のため
        'Line'/'Line+Scatter' でのみ意味を持つ。Scatter/Bar/Areaに適用すると、
        平滑化した線がマーカー/棒/塗りつぶしを完全に置き換えてしまう実害が
        あったため、対象外のplot_typeではチェックボックス自体を隠す
        (gui/canvas.pyの_draw_data側でも同じ条件を独立に再チェックしている、
        二重ガード方針)。
        """
        dataset = self._app._get_current_dataset()
        plot_type = dataset.plot_type if dataset is not None else self._app.ui.plot_type_combo.currentText()
        is_smoothable_type = plot_type in ('Line', 'Line+Scatter')
        self._app.ui.smoothing_checkbox.setVisible(is_smoothable_type)
        # 平滑化の手法コンボ(項目C-304)は、平滑化チェックボックス自体が
        # 隠れる場合は当然隠す。表示対象のplot_typeでも、チェックがOFFの間は
        # 手法を選ぶ意味がないため無効化はするが非表示にはしない
        # (見えなくなったり出てきたりでレイアウトが揺れるのを避けるため)。
        self._app.smoothing_method_label.setVisible(is_smoothable_type)
        self._app.smoothing_method_combo.setVisible(is_smoothable_type)
        self._app.smoothing_method_combo.setEnabled(self._app.ui.smoothing_checkbox.isChecked())
        self._app._update_property_section_visibility()

    def update_error_display_control_items(self):
        """
        誤差表示コンボ(エラーバー/誤差バンド/両方)のうち「誤差バンド」
        (fill_betweenによる連続的な帯)を選べるplot_typeを制限する。
        Bar(離散的な棒)には連続的な帯が視覚的に合わず、Areaは自身の
        塗りつぶしと二重に重なって煩雑になるため、これら2種別では
        「誤差バンド」「両方」の項目を無効化する(グラデーション/平滑化と
        同じ「状況に応じて選択肢を制限する」方針だが、コンボ全体ではなく
        個別項目の有効/無効化のため setVisible ではなく QStandardItem の
        setEnabled を使う)。既に保存済みの値は変更しない(選び直しは
        ユーザーに委ねる、_update_gradient_controls_visibilityと同じ方針)。
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
        ウォーターフォールプロット(項目80)のオフセット量スピンボックスの表示/非表示を
        更新する。項目109で「plot_type=='Waterfall'という専用種別」から「どの
        plot_typeとも組み合わせられる独立チェックボックス」に変更したため、
        チェックボックス自体は常に表示し、オフセット量スピンボックスだけを
        チェック状態に応じて表示/非表示にする(update_gradient_controls_visibility の
        「詳細設定はチェック後にだけ見せる」パターンと同じ)。

        ★ 改善ボード A-5: 2Dマップ(data_kind='2d_grid')は gui/canvas.py の
        _draw_data() が描画の手前で1D経路から分離する(_draw_2d_data へ振り分ける)
        ため、ウォーターフォール設定は何の効果も持たない。それでもチェックボックスを
        含む最大6行が表示され続けていたので、2Dのときは丸ごと隠す
        (グラデーション設定を plot_type で出し分けている
        update_gradient_controls_visibility と挙動を揃える)。
        """
        dataset = self._app._get_current_dataset()
        # 2Dマップではウォーターフォールは効かないので、チェックボックスごと隠す。
        # 選択なし(None)の場合は従来どおり表示する(他の 1D 系コントロールと同じ扱い)。
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
        # オクルージョンON/OFF・斜向/立体風トグル(項目120)も、有効時だけ意味を
        # 持つ設定のため同じ条件で表示する
        self._app.waterfall_occlusion_checkbox.setVisible(show_offsets)
        self._app.waterfall_depth_checkbox.setVisible(show_offsets)

        # 縮小率スピンボックスは、さらに奥行き効果トグル自体がONの時だけ
        # 意味を持つ設定のため、_update_gradient_controls_visibilityの
        # 「詳細設定はチェック後にだけ見せる」パターンと同じ2段階の表示条件にする。
        show_depth_ratio = show_offsets and self._app.waterfall_depth_checkbox.isChecked()
        self._app.waterfall_depth_ratio_label.setVisible(show_depth_ratio)
        self._app.waterfall_depth_ratio_spinbox.setVisible(show_depth_ratio)
        self._app._update_property_section_visibility()

    def update_ui_state(self):
        """
        アプリケーションの現在の状態 (主にデータセットの選択状態) に基づいて、
        UIの有効/無効、表示/非表示、および内容を更新する。
        on_dataset_selected や _on_remove_dataset などから呼び出される。
        """

        # 1. サブプロット関連のコンボボックス（選択肢）を更新
        self._app._update_subplot_combos()

        # 2. データセットリストの選択状態を取得
        # ★ フォルダも選択可能なため、「何か選択されているか」(フォルダ含む。主に
        #   削除ボタン用) と「データセットが選択されているか」(色変更等、
        #   データセット固有の操作用) を分けて扱う。
        current_dataset = self._app._get_current_dataset()
        selected_datasets = self._app._get_selected_datasets()
        has_any_selection = bool(self._app.ui.dataset_list_widget.selectedItems())
        has_dataset_selection = bool(selected_datasets)

        # 3. 選択状態に基づいて、UIの有効/無効を一括設定

        # 「データセットプロパティ」の入力欄。★ セクションの開閉トグルは
        # 選択の有無に関わらず常に押せるよう、ここでは無効化しない
        # (詳細は main_window._set_dataset_property_fields_enabled)。
        self._app._set_dataset_property_fields_enabled(has_dataset_selection)

        # データセットリストタブのボタン
        self._app.ui.remove_dataset_button.setEnabled(has_any_selection) # フォルダの削除も許可
        self._app.duplicate_dataset_button.setEnabled(has_dataset_selection)
        self._app.view_edit_data_button.setEnabled(has_dataset_selection)
        self._app.auto_color_button.setEnabled(has_dataset_selection)

        # (フィット/ピークボタン)
        self._app.fit_curve_button.setEnabled(has_dataset_selection)
        self._app.find_peaks_button.setEnabled(has_dataset_selection)

        # プロパティタブ内のコンボボックス (setEnabled(has_dataset_selection) に含まれるが明示)
        self._app.subplot_target_combo.setEnabled(has_dataset_selection)
        self._app.use_secondary_y_checkbox.setEnabled(has_dataset_selection)
        self._app.x_col_combo.setEnabled(has_dataset_selection)
        self._app.y_col_combo.setEnabled(has_dataset_selection)
        self._app.x_err_col_combo.setEnabled(has_dataset_selection)
        self._app.y_err_col_combo.setEnabled(has_dataset_selection)
        self._app.error_display_combo.setEnabled(has_dataset_selection)
        self._app.nan_policy_combo.setEnabled(has_dataset_selection)

        # 4. 【選択中】の場合: 選択された Dataset の内容をUIにロード
        #    (current_dataset は「カレント」アイテムがフォルダの場合や、
        #     何も選択されていない場合は None になる)
        if current_dataset is not None:
            dataset = current_dataset

            # 4b. ★★★ シグナルを一時的にブロック ★★★
            # (これからコードでUIの値をセットするため、シグナルが発火するのを防ぐ)
            self._app.ui.legend_name_edit.blockSignals(True)
            self._app.ui.plot_type_combo.blockSignals(True)
            self._app.color_picker_widget.blockSignals(True)
            self._app.ui.linestyle_combo.blockSignals(True)
            self._app.ui.linewidth_spinbox.blockSignals(True)
            self._app.ui.marker_combo.blockSignals(True)
            self._app.ui.markersize_spinbox.blockSignals(True)
            self._app.ui.smoothing_checkbox.blockSignals(True)
            self._app.smoothing_method_combo.blockSignals(True)
            self._app.alpha_spinbox.blockSignals(True)
            self._app.point_labels_checkbox.blockSignals(True)
            self._app.point_label_col_combo.blockSignals(True)
            self._app.use_secondary_y_checkbox.blockSignals(True)
            self._app.subplot_target_combo.blockSignals(True)
            self._app.gradient_checkbox.blockSignals(True)
            self._app.gradient_color2_picker.blockSignals(True)
            self._app.gradient_target_combo.blockSignals(True)
            self._app.waterfall_checkbox.blockSignals(True)
            self._app.waterfall_offset_x_spinbox.blockSignals(True)
            self._app.waterfall_offset_y_spinbox.blockSignals(True)
            self._app.waterfall_occlusion_checkbox.blockSignals(True)
            self._app.waterfall_depth_checkbox.blockSignals(True)
            self._app.waterfall_depth_ratio_spinbox.blockSignals(True)
            self._app.error_display_combo.blockSignals(True)
            self._app.nan_policy_combo.blockSignals(True)
            self._app.data_2d_checkbox.blockSignals(True)
            self._app.colormap_combo.blockSignals(True)
            self._app.map_display_mode_combo.blockSignals(True)
            self._app.contour_levels_spinbox.blockSignals(True)
            self._app.grid_interp_method_combo.blockSignals(True)
            self._app.color_range_auto_checkbox.blockSignals(True)
            self._app.vmin_spinbox.blockSignals(True)
            self._app.vmax_spinbox.blockSignals(True)

            # 4c. Dataset オブジェクトの値をUIにロード
            self._app.ui.legend_name_edit.setText(dataset.name)
            self._app.ui.plot_type_combo.setCurrentText(dataset.plot_type)
            # 保存値は '--' と 'dashed' のような表記ゆれを含むため、表示名に揃えて選ぶ。
            # 線を描かない値('None')はどの項目にも当たらないので、選択なしにする
            # (直前のデータセットの表示が残って誤解されるのを防ぐ)。
            shown_linestyle = linestyle_name(dataset.linestyle)
            if shown_linestyle is None:
                self._app.ui.linestyle_combo.setCurrentIndex(-1)
            else:
                self._app.ui.linestyle_combo.setCurrentText(shown_linestyle)
            self._app.ui.linewidth_spinbox.setValue(dataset.linewidth)
            self._app.ui.marker_combo.setCurrentText(dataset.marker if dataset.marker is not None else 'None')
            self._app.ui.markersize_spinbox.setValue(dataset.markersize)
            self._app.color_picker_widget.set_color(dataset.color)
            self._app.ui.smoothing_checkbox.setChecked(dataset.smoothing)
            smoothing_method_index = self._app.smoothing_method_combo.findData(dataset.smoothing_method)
            self._app.smoothing_method_combo.setCurrentIndex(smoothing_method_index if smoothing_method_index != -1 else 0)
            self._app.alpha_spinbox.setValue(dataset.alpha)
            self._app.gradient_checkbox.setChecked(dataset.gradient_enabled)
            self._app.gradient_color2_picker.set_color(dataset.gradient_color2)
            gradient_target_index = self._app.gradient_target_combo.findData(dataset.gradient_target)
            self._app.gradient_target_combo.setCurrentIndex(gradient_target_index if gradient_target_index != -1 else 0)
            self._app.waterfall_checkbox.setChecked(dataset.waterfall_enabled)
            self._app.waterfall_offset_x_spinbox.setValue(dataset.waterfall_offset_x)
            self._app.waterfall_offset_y_spinbox.setValue(dataset.waterfall_offset_y)
            self._app.waterfall_occlusion_checkbox.setChecked(dataset.waterfall_occlusion_enabled)
            self._app.waterfall_depth_checkbox.setChecked(dataset.waterfall_depth_shrink_enabled)
            self._app.waterfall_depth_ratio_spinbox.setValue(dataset.waterfall_depth_shrink_ratio)
            self._app.point_labels_checkbox.setChecked(dataset.show_point_labels)
            self._app.point_label_col_combo.clear()
            self._app.point_label_col_combo.addItems([POINT_LABEL_Y_VALUE_LABEL] + dataset.df.columns.tolist())
            self._app.point_label_col_combo.setCurrentText(dataset.point_label_col_name or POINT_LABEL_Y_VALUE_LABEL)
            self._app.use_secondary_y_checkbox.setChecked(dataset.use_secondary_y)
            self._app.subplot_target_combo.setCurrentIndex(dataset.subplot_target)
            error_display_index = self._app.error_display_combo.findData(dataset.error_display)
            self._app.error_display_combo.setCurrentIndex(error_display_index if error_display_index != -1 else 0)
            nan_policy_index = self._app.nan_policy_combo.findData(dataset.nan_policy)
            self._app.nan_policy_combo.setCurrentIndex(nan_policy_index if nan_policy_index != -1 else 0)
            self._app.data_2d_checkbox.setChecked(dataset.data_kind == '2d_grid')
            colormap_index = self._app.colormap_combo.findText(dataset.colormap)
            self._app.colormap_combo.setCurrentIndex(colormap_index if colormap_index != -1 else 0)
            display_mode_index = self._app.map_display_mode_combo.findData(dataset.map_display_mode)
            self._app.map_display_mode_combo.setCurrentIndex(display_mode_index if display_mode_index != -1 else 0)
            self._app.contour_levels_spinbox.setValue(dataset.contour_levels)
            interp_index = self._app.grid_interp_method_combo.findText(dataset.grid_interp_method)
            self._app.grid_interp_method_combo.setCurrentIndex(interp_index if interp_index != -1 else 0)
            is_range_auto = dataset.vmin is None and dataset.vmax is None
            self._app.color_range_auto_checkbox.setChecked(is_range_auto)
            self._app.vmin_spinbox.setValue(dataset.vmin if dataset.vmin is not None else 0.0)
            self._app.vmax_spinbox.setValue(dataset.vmax if dataset.vmax is not None else 1.0)
            self._app.vmin_spinbox.setEnabled(not is_range_auto)
            self._app.vmax_spinbox.setEnabled(not is_range_auto)

            # 4d. ★★★ シグナルを解除 ★★★
            self._app.ui.legend_name_edit.blockSignals(False)
            self._app.ui.plot_type_combo.blockSignals(False)
            self._app.color_picker_widget.blockSignals(False)
            self._app.ui.linestyle_combo.blockSignals(False)
            self._app.ui.linewidth_spinbox.blockSignals(False)
            self._app.ui.marker_combo.blockSignals(False)
            self._app.ui.markersize_spinbox.blockSignals(False)
            self._app.ui.smoothing_checkbox.blockSignals(False)
            self._app.smoothing_method_combo.blockSignals(False)
            self._app.alpha_spinbox.blockSignals(False)
            self._app.point_labels_checkbox.blockSignals(False)
            self._app.point_label_col_combo.blockSignals(False)
            self._app.use_secondary_y_checkbox.blockSignals(False)
            self._app.subplot_target_combo.blockSignals(False)
            self._app.gradient_checkbox.blockSignals(False)
            self._app.gradient_color2_picker.blockSignals(False)
            self._app.gradient_target_combo.blockSignals(False)
            self._app.waterfall_checkbox.blockSignals(False)
            self._app.waterfall_offset_x_spinbox.blockSignals(False)
            self._app.waterfall_offset_y_spinbox.blockSignals(False)
            self._app.waterfall_occlusion_checkbox.blockSignals(False)
            self._app.waterfall_depth_checkbox.blockSignals(False)
            self._app.waterfall_depth_ratio_spinbox.blockSignals(False)
            self._app.error_display_combo.blockSignals(False)
            self._app.nan_policy_combo.blockSignals(False)
            self._app.data_2d_checkbox.blockSignals(False)
            self._app.colormap_combo.blockSignals(False)
            self._app.map_display_mode_combo.blockSignals(False)
            self._app.contour_levels_spinbox.blockSignals(False)
            self._app.grid_interp_method_combo.blockSignals(False)
            self._app.color_range_auto_checkbox.blockSignals(False)
            self._app.vmin_spinbox.blockSignals(False)
            self._app.vmax_spinbox.blockSignals(False)
            self.update_gradient_controls_visibility()
            self.update_waterfall_controls_visibility()
            self.update_smoothing_control_visibility()
            self.update_error_display_control_items()
            self.update_2d_controls_visibility()
            self.update_point_labels_limit_note()

            # 4e. X/Y軸コンボボックスの更新処理 (シグナルブロックを含む)
            self._app.x_col_combo.blockSignals(True)
            self._app.y_col_combo.blockSignals(True)

            all_columns = dataset.df.columns.tolist()
            self._app.x_col_combo.clear()
            self._app.y_col_combo.clear()
            self._app.x_col_combo.addItems(all_columns)
            self._app.y_col_combo.addItems(all_columns)

            # 現在の列名を選択状態にする
            self._app.x_col_combo.setCurrentText(dataset.x_col_name)
            self._app.y_col_combo.setCurrentText(dataset.y_col_name)

            self._app.x_col_combo.blockSignals(False)
            self._app.y_col_combo.blockSignals(False)

            # 4e-2. エラーバー用の誤差列コンボボックス ("(なし)" を先頭に追加)
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

            # 4e-3. Z軸列コンボボックス(2Dグリッドデータ、項目C-508)
            self._app.z_col_combo.blockSignals(True)
            self._app.z_col_combo.clear()
            self._app.z_col_combo.addItems(all_columns)
            if dataset.z_col_name:
                self._app.z_col_combo.setCurrentText(dataset.z_col_name)
            self._app.z_col_combo.blockSignals(False)

            # 4f. フィット情報UIの更新
            if dataset.fit_info:
                self._app.fit_info_label.setVisible(True)
                self._app.fit_info_textedit.setVisible(True)
                self._app.fit_info_textedit.setText(dataset.fit_info)
            else:
                self._app.fit_info_label.setVisible(False)
                self._app.fit_info_textedit.setVisible(False)
                self._app.fit_info_textedit.clear()

            # 4g. 統計サマリー (Y列の件数・平均・標準偏差・最小/最大) の更新
            self.update_stats_summary_label(dataset)

            # 4h. 残差プロットパネルの更新(項目C-406)。dataset.fit_resultが
            # 無ければパネル側がプレースホルダ表示に戻す(再計算はしない)。
            self._app.residual_panel.refresh(dataset)

            # 4i. 処理履歴(provenance)ツリーパネルの更新(項目C-1101)。
            self._app.provenance_panel.refresh(dataset, self._app.project)

        # 5. 【非選択中 (またはフォルダ選択中)】の場合: UIをクリア
        else:
            self._app.x_col_combo.clear()
            self._app.y_col_combo.clear()
            self._app.x_err_col_combo.clear()
            self._app.y_err_col_combo.clear()
            self._app.point_label_col_combo.clear()
            self._app.z_col_combo.clear()
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

    def update_stats_summary_label(self, dataset):
        """
        選択中データセットのY列について、件数・平均・標準偏差・最小/最大の
        要約統計量を計算し、プロパティパネルのラベル(詳細版)と、
        データセットリスト直下のミニ統計ラベル(項目69、1行の簡易版)の
        両方に表示する。NaNは集計から除外する。数値に変換できない列の場合は "-" を表示する。
        """
        try:
            y = np.asarray(dataset.y_data, dtype=float)
            valid = y[~np.isnan(y)]
            if len(valid) == 0:
                self._app.stats_summary_label.setText("-")
                self._app.dataset_mini_stats_label.setText(dataset.name)
                return
            # 標本標準偏差(n−1)。1点しか無いと定義できないので「-」と表示する。
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
        """
        「X軸の列」または「Y軸の列」コンボボックスが変更されたときに呼び出される。
        Dataset オブジェクトの x_col_name / y_col_name を更新し、プロットを再描画する。
        """
        dataset = self._app._get_current_dataset()
        if dataset is None:
            return

        # 新しい列名を取得
        new_x_col = self._app.x_col_combo.currentText()
        new_y_col = self._app.y_col_combo.currentText()

        # 実際に変更がある列だけを old/new_values に含める
        # (コンボボックスが空の場合もあるため、空でないかチェック)
        old_values, new_values = {}, {}
        if new_x_col and new_x_col in dataset.df.columns and new_x_col != dataset.x_col_name:
            old_values['x_col_name'] = dataset.x_col_name
            new_values['x_col_name'] = new_x_col
        if new_y_col and new_y_col in dataset.df.columns and new_y_col != dataset.y_col_name:
            old_values['y_col_name'] = dataset.y_col_name
            new_values['y_col_name'] = new_y_col

        # Undo/Redo可能なコマンドとして発行 (X/Yが同時に変わった場合は1つの操作としてまとめる)
        self._app._push_dataset_property_command(dataset, old_values, new_values, description="プロット列の変更")

        # 列の単位メタデータ → 軸ラベル自動生成(項目127、C-608): 選んだ列名が
        # 「ラベル (単位)」形式に見える場合、このデータセットの描画先(subplot_target)
        # の軸ラベルが「まだ空」であれば自動的に埋める(ユーザーが既に手で入力した
        # ラベルは上書きしない)。ラベル自体はUndo対象に含めない(軸設定のUndoは
        # 別の仕組み(all_plot_settingsのスナップショット)で扱っており、ここに
        # 巻き込むと既存の挙動を変えてしまうため)。
        if 'x_col_name' in new_values:
            self.maybe_autofill_axis_label(dataset.subplot_target, 'x_label', new_values['x_col_name'])
        if 'y_col_name' in new_values:
            self.maybe_autofill_axis_label(dataset.subplot_target, 'y_label', new_values['y_col_name'])

    def maybe_autofill_axis_label(self, subplot_index, label_key, column_name):
        """
        _on_plot_column_changedのヘルパー(項目127、C-608)。指定した軸の
        指定ラベル(x_label/y_label)が空の場合のみ、列名から推測したラベルで
        埋める。編集対象として現在UIに表示中の軸(project.active_axis_index)と
        一致する場合はテキスト欄経由で(既存の_on_axis_setting_changedの保存
        経路にそのまま乗せて)反映し、一致しない場合はall_plot_settingsを
        直接更新してから再描画する(UIに表示されていない軸の設定を、表示中の
        軸のテキスト欄に書き込んでしまう誤動作を避けるため)。
        """
        if subplot_index is None or not (0 <= subplot_index < len(self._app.project.all_plot_settings)):
            return
        inferred = infer_axis_label_from_column_name(column_name)
        if not inferred:
            return
        current_settings = self._app.project.all_plot_settings[subplot_index]
        if current_settings.get(label_key):
            return  # 既存のラベルは上書きしない

        if subplot_index == self._app.project.active_axis_index:
            label_edit = self._app.ui.x_label_text_edit if label_key == 'x_label' else self._app.ui.y_label_text_edit
            if not label_edit.text():
                label_edit.setText(inferred)  # textChanged経由で_on_axis_setting_changedが保存・再描画する
        else:
            current_settings[label_key] = inferred
            self._app._update_plot()

    def on_data_2d_toggled(self, checked):
        """
        「2Dグリッドデータとして扱う」チェックボックス(項目C-508)が切り替えられた
        ときの処理。data_kindを'2d_grid'/'1d'に切り替える。ONにする際、
        z_col_nameが未設定ならX/Y列以外の最初の列を自動選択する(候補が無ければ
        未設定のままにし、ユーザーに手動選択を促す)。
        """
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
        """
        「Z軸の列」コンボボックスが変更されたときに呼び出される
        (_on_plot_column_changedのZ列版)。
        """
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
        """
        「値域を自動」チェックボックス、または値域の最小/最大スピンボックスが
        変更されたときの処理(項目C-508)。自動が有効な間はvmin/vmaxを
        Noneにする(core/dataset.pyのz_gridプロパティ・gui/canvas.pyの
        _draw_2d_dataがNoneの場合は実データの最小/最大値を使う)。
        """
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
        2Dグリッドデータ関連のコントロール(Z列・カラーマップ・補間方法・値域)の
        表示/非表示を、現在選択中データセットのdata_kindに応じて更新する
        (_update_gradient_controls_visibilityと同じパターン)。

        ★ 改善ボード D-2: Z列・カラーマップ・値域の3つは、1Dの
        'Z-Color Scatter'(3列目の値で点を配色する散布図)でも使う
        ため、data_kind='2d_grid' でなくてもこのplot_typeなら表示する。
        残り(表示モード・等高線レベル・グリッド補間方法)はグリッド固有なので
        2Dのときだけ表示する。
        """
        dataset = self._app._get_current_dataset()
        # ★ 選択なし(None)の場合は常に非表示にする(data_2d_checkboxのチェック状態は
        # 直前に選択していたデータセットの値が残ったままなので、それにフォール
        # バックすると選択解除後も2D系コントロールが表示されたままになるバグになる)。
        is_2d = dataset is not None and dataset.data_kind == '2d_grid'
        is_color_by_column = (
            dataset is not None
            and dataset.data_kind != '2d_grid'
            and dataset.plot_type == COLOR_BY_COLUMN_PLOT_TYPE
        )
        # Z列・カラーマップ・値域: 2Dグリッド と 色分け散布図 の共用
        shared_with_color_scatter = is_2d or is_color_by_column
        for widget in (
            self._app.z_col_label, self._app.z_col_combo,
            self._app.colormap_label, self._app.colormap_combo,
            self._app.color_range_auto_checkbox,
            self._app.vmin_label, self._app.vmin_spinbox,
            self._app.vmax_label, self._app.vmax_spinbox,
        ):
            widget.setVisible(shared_with_color_scatter)

        # グリッド固有の設定は2Dのときだけ
        for widget in (
            self._app.map_display_mode_label, self._app.map_display_mode_combo,
            self._app.contour_levels_label, self._app.contour_levels_spinbox,
            self._app.grid_interp_method_label, self._app.grid_interp_method_combo,
        ):
            widget.setVisible(is_2d)

        self._app._update_property_section_visibility()

    def on_error_column_changed(self):
        """
        「X誤差列」または「Y誤差列」コンボボックスが変更されたときに呼び出される。
        Dataset オブジェクトの x_err_col_name / y_err_col_name を更新し、
        エラーバー付きでプロットを再描画する。"(なし)" が選択された場合は
        None (エラーバー非表示) を設定する。
        """
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
        """
        DataEditorDialog から dataChanged シグナルを受け取ったときに呼び出されるスロット。
        データの構造 (値/列/行) が変更された可能性があるため、UIとプロットを更新する。
        """
        if self._app._get_current_dataset() is None:
            return # (通常はエディタが開いている＝選択中のはずだが念のため)

        # ★ UIの状態(主にX/Y列コンボボックス)を最新のDataFrame情報で更新
        self.update_ui_state()
        # ★ プロットを最新のデータで更新
        self._app._update_plot()

    def on_secondary_y_changed(self):
        """
        「第2Y軸 (右側) を使用」チェックボックスが変更されたときの処理。
        複数選択時は選択中の全データセットに一括適用する。
        """
        selected_datasets = self._app._get_selected_datasets()
        if not selected_datasets:
            return

        new_value = self._app.use_secondary_y_checkbox.isChecked()

        # Dataset オブジェクトの use_secondary_y 属性を Undo/Redo可能に更新
        # (軸の割り当てが変わるため、プロット全体の再描画が必要。
        #  これは _refresh_after_dataset_property_change 内で行われる)
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
