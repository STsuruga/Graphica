"""データセットのプロパティ(Dataset の属性)とプロパティ欄の対応表。欄を 1 つ足すときは表に 1 行足す。

表の順は選んだデータセットを欄に戻す順。欄から値を読む行(read がある行)は、変わったらその属性だけを
選択中のデータセットすべてに当てる(DatasetPropertyPanel.on_property_changed)。read が無い行は戻すだけで、
変更は専用の処理が受ける(凡例名・色・第 2 Y 軸・描画先・2D・値域)。
"""
from graphica.core.dataset import linestyle_name
from graphica.gui.binding import WATCH, Binding, check, found_text, item_data, number, shown_text

# 誤差列の欄で「誤差列を使わない」を表す選択肢
NO_ERROR_COLUMN_LABEL = "(なし)"
# データ点ラベルの内容の欄で「Y値そのもの」を表す選択肢
POINT_LABEL_Y_VALUE_LABEL = "Y値"

_PANEL = 'property_panel.'


def _linestyle(key, widget):
    """保存値は '--' と 'dashed' のような表記ゆれを含むので表示名に揃えて選ぶ。線を描かない値は選択なしにする
    (直前のデータセットの表示が残って誤解されないように)。"""
    def write(_owner, combo, value):
        shown = linestyle_name(value)
        if shown is None:
            combo.setCurrentIndex(-1)
        else:
            combo.setCurrentText(shown)
    return Binding(key, widget, lambda _o, w: w.currentText(), write, 'currentTextChanged', (WATCH,))


def _marker(key, widget):
    return Binding(key, widget, lambda _o, w: None if w.currentText() == 'None' else w.currentText(),
                   lambda _o, w, v: w.setCurrentText(v if v is not None else 'None'), 'currentTextChanged', (WATCH,))


def _color(key, widget, slot):
    return Binding(key, widget, None, lambda _o, w, v: w.set_color(v), 'colorChanged', (slot,))


def _point_label_column(key, widget):
    """選択肢はデータセットの列なので、戻すたびに作り直す。"""
    def write(_owner, combo, value):
        name, columns = value
        combo.clear()
        combo.addItems([POINT_LABEL_Y_VALUE_LABEL] + columns)
        combo.setCurrentText(name or POINT_LABEL_Y_VALUE_LABEL)

    def read(_owner, combo):
        return None if combo.currentText() == POINT_LABEL_Y_VALUE_LABEL else combo.currentText()
    return Binding(key, widget, read, write, 'currentTextChanged', (WATCH,),
                   load=lambda ds: (ds.point_label_col_name, ds.df.columns.tolist()))


def _value_range(key, widget, empty_value):
    """値域が自動(None)のときは欄に仮の値を入れておく。"""
    return Binding(key, widget, None, lambda _o, w, v: w.setValue(v if v is not None else empty_value),
                   'valueChanged', (_PANEL + 'on_2d_value_range_changed',))


DATASET_PROPERTY_BINDINGS = (
    # textChanged だと1文字ごとに描き直して重いので editingFinished
    Binding('name', 'ui.legend_name_edit', None, lambda _o, w, v: w.setText(v), 'editingFinished',
            (_PANEL + 'on_legend_name_changed',)),
    # 種類によって意味のある欄が変わるので、種類が変わるたびに出し入れし直す
    shown_text('plot_type', 'ui.plot_type_combo',
               (WATCH, _PANEL + 'update_gradient_controls_visibility', _PANEL + 'update_smoothing_control_visibility',
                _PANEL + 'update_error_display_control_items')),
    _linestyle('linestyle', 'ui.linestyle_combo'),
    number('linewidth', 'ui.linewidth_spinbox', (WATCH,)),
    _marker('marker', 'ui.marker_combo'),
    number('markersize', 'ui.markersize_spinbox', (WATCH,)),
    _color('color', 'color_picker_widget', 'colors.on_color_changed'),
    # 平滑化のチェックで手法の欄の有効/無効も切り替える
    check('smoothing', 'ui.smoothing_checkbox', (WATCH, _PANEL + 'update_smoothing_control_visibility')),
    item_data('smoothing_method', 'smoothing_method_combo', (WATCH,)),
    number('alpha', 'alpha_spinbox', (WATCH,)),
    check('gradient_enabled', 'gradient_checkbox', (WATCH, _PANEL + 'update_gradient_controls_visibility'),
          signal='toggled'),
    _color('gradient_color2', 'gradient_color2_picker', 'colors.on_gradient_color2_changed'),
    item_data('gradient_target', 'gradient_target_combo', (WATCH,)),
    check('waterfall_enabled', 'waterfall_checkbox', (WATCH, _PANEL + 'update_waterfall_controls_visibility'),
          signal='toggled'),
    number('waterfall_offset_x', 'waterfall_offset_x_spinbox', (WATCH,)),
    number('waterfall_offset_y', 'waterfall_offset_y_spinbox', (WATCH,)),
    check('waterfall_occlusion_enabled', 'waterfall_occlusion_checkbox', (WATCH,), signal='toggled'),
    check('waterfall_depth_shrink_enabled', 'waterfall_depth_checkbox',
          (WATCH, _PANEL + 'update_waterfall_controls_visibility'), signal='toggled'),
    number('waterfall_depth_shrink_ratio', 'waterfall_depth_ratio_spinbox', (WATCH,)),
    # 点ラベルは上限の説明の更新もするので専用のハンドラ(中で on_property_changed を呼ぶ)
    check('show_point_labels', 'point_labels_checkbox', (_PANEL + 'on_point_labels_toggled',), signal='toggled'),
    _point_label_column('point_label_col_name', 'point_label_col_combo'),
    Binding('use_secondary_y', 'use_secondary_y_checkbox', None, lambda _o, w, v: w.setChecked(v), 'stateChanged',
            (_PANEL + 'on_secondary_y_changed',)),
    Binding('subplot_target', 'subplot_target_combo', None, lambda _o, w, v: w.setCurrentIndex(v),
            'currentIndexChanged', (_PANEL + 'on_subplot_target_changed',)),
    item_data('error_display', 'error_display_combo', (WATCH,)),
    item_data('nan_policy', 'nan_policy_combo', (WATCH,)),
    Binding('data_kind', 'data_2d_checkbox', None, lambda _o, w, v: w.setChecked(v == '2d_grid'), 'toggled',
            (_PANEL + 'on_data_2d_toggled',)),
    found_text('colormap', 'colormap_combo', (WATCH,)),
    item_data('map_display_mode', 'map_display_mode_combo', (WATCH,)),
    number('contour_levels', 'contour_levels_spinbox', (WATCH,)),
    found_text('grid_interp_method', 'grid_interp_method_combo', (WATCH,)),
    Binding('color_range_auto', 'color_range_auto_checkbox', None, lambda _o, w, v: w.setChecked(v), 'toggled',
            (_PANEL + 'on_2d_value_range_changed',), load=lambda ds: ds.vmin is None and ds.vmax is None),
    _value_range('vmin', 'vmin_spinbox', 0.0),
    _value_range('vmax', 'vmax_spinbox', 1.0),
)
