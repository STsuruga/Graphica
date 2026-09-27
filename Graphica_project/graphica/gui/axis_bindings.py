"""軸の設定(core/axis_settings.py のキー)と画面の欄の対応表。欄を 1 つ足すときは表に 1 行足す。

表の順は戻す順。集めた辞書のキーの順は AXIS_SETTING_DEFAULTS の順(保存形式)にそろえる。
"""
from PySide6.QtGui import QFont

from graphica.core.unit_conversion import X_AXIS_UNIT_CHOICES
from graphica.gui.binding import Binding, check, choice, index, item_data, number, shown_text, text
from graphica.gui.canvas import MINOR_TICK_LENGTH_AUTO

_CHANGED = ('_on_axis_setting_changed',)

# 欄を持たず操作から直接書き込まれるキー。集めるときは今の軸の設定から引き継ぐ(辞書は丸ごと入れ替わるので)
CARRIED_AXIS_KEYS = ('annotations', 'legend_order', 'free_rect', 'legend_position')

# 戻す間は信号を止めるが、値は持たない欄
AXIS_BUTTONS = (
    'ui.tick_font_button', 'ui.tick_color_button', 'ui.axis_label_font_button', 'ui.axis_label_color_button',
    'legend_font_button', 'legend_color_button', 'ui.spine_color_button',
)


def qfont_from_family_props(font_props: dict) -> QFont:
    """'family' は候補のリストか、古いプロジェクトでは1つの名前。QFont(list) は無いので setFamilies() を使う。"""
    family = font_props.get('family', 'Sans Serif')
    if isinstance(family, (list, tuple)):
        font = QFont()
        if family:
            font.setFamilies(list(family))
        return font
    return QFont(family)


def _font(key, attribute, size_only_when_given=False):
    """フォントは持ち主の属性に QFont で持つ。凡例は保存にサイズが無ければ QFont の既定のサイズのまま。"""
    def read(owner, _widget):
        return owner._font_props_to_dict(getattr(owner, attribute))

    def write(owner, _widget, props):
        setattr(owner, attribute, qfont_from_family_props(props))
        font = getattr(owner, attribute)
        if not size_only_when_given or 'size' in props:
            font.setPointSize(props.get('size', 10))
        font.setBold(props.get('weight') == 'bold')
        font.setItalic(props.get('style') == 'italic')
    return Binding(key, None, read, write)


def _attribute(key, attribute):
    return Binding(key, None, lambda owner, _w: getattr(owner, attribute),
                   lambda owner, _w, value: setattr(owner, attribute, value))


def _width(key, widget, attribute):
    """線の太さは描画が持ち主の属性から読むので、欄と一緒に属性にも入れる。"""
    def write(owner, spinbox, value):
        setattr(owner, attribute, value)
        spinbox.setValue(getattr(owner, attribute))
    return Binding(key, widget, lambda _o, w: w.value(), write, 'valueChanged', _CHANGED)


def _grid_linestyle(key, widget):
    return Binding(key, widget, lambda owner, w: owner._grid_linestyle_code(w.currentIndex()),
                   lambda owner, w, value: w.setCurrentIndex(owner._grid_linestyle_index(value)),
                   'currentIndexChanged', _CHANGED)


def _minor_tick_length(key, widget):
    """負値(スピンボックスの「自動」)は -1 に正規化して保存する。"""
    def read(_owner, spinbox):
        return spinbox.value() if spinbox.value() >= 0 else -1

    def write(_owner, spinbox, value):
        spinbox.setValue(MINOR_TICK_LENGTH_AUTO if value is None or value < 0 else value)
    return Binding(key, widget, read, write, 'valueChanged', _CHANGED)


def _axis_rows(axis):
    """X と Y で同じ並びの行。autoscale・目盛りの方式・補助目盛りの表示・対数は、見え方を切り替える処理もつなぐ。"""
    ui = f'ui.{axis}'
    return (
        check(f'{axis}_autoscale', f'{ui}_autoscale_checkbox', _CHANGED + (f'_on_{axis}_autoscale_changed',)),
        number(f'{axis}_min', f'{ui}_min_spinbox', _CHANGED),
        number(f'{axis}_max', f'{ui}_max_spinbox', _CHANGED),
        check(f'{axis}_log', f'{ui}_log_checkbox', _CHANGED + (f'_on_{axis}_minor_tick_visibility_changed',)),
        check(f'{axis}_invert', f'{ui}_invert_checkbox', _CHANGED),
        index(f'{axis}_major_tick_mode', f'{ui}_major_tick_mode_combo', _CHANGED + (f'_on_{axis}_tick_mode_changed',)),
        number(f'{axis}_major_tick_interval', f'{ui}_major_tick_interval_spinbox', _CHANGED),
        check(f'{axis}_minor_ticks_visible', f'{ui}_minor_ticks_visible_checkbox',
              _CHANGED + (f'_on_{axis}_minor_tick_visibility_changed',)),
        number(f'{axis}_minor_tick_interval', f'{ui}_minor_tick_interval_spinbox', _CHANGED),
        # 対数軸のときだけ効く
        item_data(f'{axis}_log_minor_subs', f'{axis}_log_minor_subs_combo', _CHANGED),
        check(f'{axis}_log_minor_labels', f'{axis}_log_minor_labels_checkbox', _CHANGED),
        index(f'{axis}_tick_format_mode', f'{axis}_tick_format_combo', _CHANGED),
        number(f'{axis}_tick_decimals', f'{axis}_tick_decimals_spinbox', _CHANGED),
    )


def _grid_rows(axis, which):
    name = f'{axis}_{which}_grid'
    return (
        _grid_linestyle(f'{name}_linestyle', f'{name}_linestyle_combo'),
        number(f'{name}_width', f'{name}_width_spinbox', _CHANGED),
        number(f'{name}_alpha', f'{name}_alpha_spinbox', _CHANGED),
    )


AXIS_BINDINGS = (
    text('title', 'ui.title_text_edit', _CHANGED),
    text('x_label', 'ui.x_label_text_edit', _CHANGED),
    text('y_label', 'ui.y_label_text_edit', _CHANGED),
    check('x_label_visible', 'x_label_visible_checkbox', _CHANGED),
    check('y_label_visible', 'y_label_visible_checkbox', _CHANGED),
    text('y2_label', 'y2_label_text_edit', _CHANGED),

    *_axis_rows('x'),
    choice('x_secondary_axis_source_unit', 'x_secondary_axis_source_unit_combo', X_AXIS_UNIT_CHOICES, _CHANGED),
    choice('x_secondary_axis_target_unit', 'x_secondary_axis_target_unit_combo', X_AXIS_UNIT_CHOICES, _CHANGED),

    *_axis_rows('y'),

    check('legend_visible', 'ui.legend_visible_checkbox', _CHANGED + ('_on_legend_visibility_changed',)),
    # ドラッグした位置を消してから書き戻すので、ほかの欄と違う処理につなぐ
    shown_text('legend_loc', 'legend_loc_combo', ('_on_legend_loc_changed',)),
    # グリッドのチェックは補助グリッドと詳細の欄の有効/無効も切り替える
    check('grid_visible', 'ui.grid_visible_checkbox', _CHANGED + ('_on_grid_visibility_changed',)),
    check('minor_grid_visible', 'ui.minor_grid_visible_checkbox', _CHANGED + ('_on_grid_visibility_changed',)),

    *_grid_rows('x', 'major'),
    *_grid_rows('x', 'minor'),
    *_grid_rows('y', 'major'),
    *_grid_rows('y', 'minor'),
    shown_text('major_tick_direction', 'major_tick_direction_combo', _CHANGED),
    shown_text('minor_tick_direction', 'minor_tick_direction_combo', _CHANGED),
    shown_text('major_tick_direction_y2', 'major_tick_direction_y2_combo', _CHANGED),
    shown_text('minor_tick_direction_y2', 'minor_tick_direction_y2_combo', _CHANGED),
    check('x_ticks_visible', 'x_ticks_visible_checkbox', _CHANGED),
    check('x_tick_labels_visible', 'x_tick_labels_visible_checkbox', _CHANGED),
    check('y_ticks_visible', 'y_ticks_visible_checkbox', _CHANGED),
    check('y_tick_labels_visible', 'y_tick_labels_visible_checkbox', _CHANGED),

    _font('tick_font', '_tick_font'),
    _font('axis_label_font', '_axis_label_font'),
    _font('legend_font', '_legend_font', size_only_when_given=True),
    _attribute('tick_color', '_tick_color'),
    _width('tick_width', 'ui.tick_width_spinbox', '_tick_width'),
    number('major_tick_length', 'major_tick_length_spinbox', _CHANGED),
    _minor_tick_length('minor_tick_length', 'minor_tick_length_spinbox'),
    _attribute('axis_label_color', '_axis_label_color'),
    _attribute('legend_color', '_legend_color'),
    _width('spine_width', 'ui.spine_width_spinbox', '_spine_width'),
    _attribute('spine_color', '_spine_color'),

    # 2Dマップが無い軸では効かない
    check('colorbar_enabled', 'colorbar_enabled_checkbox', _CHANGED),
    item_data('colorbar_position', 'colorbar_position_combo', _CHANGED),
    number('colorbar_width_fraction', 'colorbar_width_spinbox', _CHANGED),
    text('colorbar_label', 'colorbar_label_edit', _CHANGED),
)
