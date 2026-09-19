"""
1つの軸の設定(保存形式は文字列キーの辞書)のキーと既定値。

キーを持たない古いプロジェクトは、画面に戻すときも描画するときもここの既定値で読む。
既定値を変えると既存のプロジェクトの見た目が変わるので、変えるときは保存形式の移行として扱う。
"""
import copy

from graphica.core.unit_conversion import X_AXIS_UNIT_NONE

AXIS_SETTING_DEFAULTS = {
    'title': '',
    'x_label': '',
    'y_label': '',
    'x_label_visible': True,
    'y_label_visible': True,
    'y2_label': '',

    'x_autoscale': True,
    'x_min': 0,
    'x_max': 1,
    'x_log': False,
    'x_invert': False,
    'x_major_tick_mode': 0,
    'x_major_tick_interval': 1,
    'x_minor_ticks_visible': False,
    'x_minor_tick_interval': 0.5,
    'x_log_minor_subs': 'auto',
    'x_log_minor_labels': False,
    'x_tick_format_mode': 0,
    'x_tick_decimals': -1,
    'x_secondary_axis_source_unit': X_AXIS_UNIT_NONE,
    'x_secondary_axis_target_unit': X_AXIS_UNIT_NONE,

    'y_autoscale': True,
    'y_min': 0,
    'y_max': 1,
    'y_log': False,
    'y_invert': False,
    'y_major_tick_mode': 0,
    'y_major_tick_interval': 1,
    'y_minor_ticks_visible': False,
    'y_minor_tick_interval': 0.5,
    'y_log_minor_subs': 'auto',
    'y_log_minor_labels': False,
    'y_tick_format_mode': 0,
    'y_tick_decimals': -1,

    'legend_visible': True,
    'legend_loc': 'best',
    'grid_visible': False,
    'minor_grid_visible': False,
    'x_major_grid_linestyle': '-',
    'x_major_grid_width': 0.8,
    'x_major_grid_alpha': 1.0,
    'x_minor_grid_linestyle': '--',
    'x_minor_grid_width': 0.5,
    'x_minor_grid_alpha': 1.0,
    'y_major_grid_linestyle': '-',
    'y_major_grid_width': 0.8,
    'y_major_grid_alpha': 1.0,
    'y_minor_grid_linestyle': '--',
    'y_minor_grid_width': 0.5,
    'y_minor_grid_alpha': 1.0,
    'major_tick_direction': 'out',
    'minor_tick_direction': 'out',
    'major_tick_direction_y2': 'out',
    'minor_tick_direction_y2': 'out',
    'x_ticks_visible': True,
    'x_tick_labels_visible': True,
    'y_ticks_visible': True,
    'y_tick_labels_visible': True,

    # フォントは {family, size, weight, style}。空なら画面側・描画側の既定のフォント
    'tick_font': {},
    'tick_color': '#000000',
    'tick_width': 0.8,
    # matplotlib の既定(xtick.major.size)と同じ。-1(負値)の補助目盛は「主目盛から自動」
    'major_tick_length': 3.5,
    'minor_tick_length': -1,
    'axis_label_font': {},
    'axis_label_color': '#000000',
    'legend_font': {},
    'legend_color': '#000000',
    'spine_width': 1.0,
    'spine_color': '#000000',

    'colorbar_enabled': True,
    'colorbar_position': 'right',
    'colorbar_width_fraction': 0.05,
    'colorbar_label': '',

    # 画面の欄を持たず、操作から直接書き込まれるもの
    'annotations': [],
    'legend_order': [],
    'free_rect': None,
    'legend_position': None,
}

# 軸ごとに分ける前の共通キー。新しいキーが無いプロジェクトでは、その値を X/Y 両方に使う。
LEGACY_FALLBACK_KEYS = {
    'x_ticks_visible': 'ticks_visible',
    'y_ticks_visible': 'ticks_visible',
    'x_tick_labels_visible': 'tick_labels_visible',
    'y_tick_labels_visible': 'tick_labels_visible',
}


def axis_setting(settings, key):
    """settings の key の値。無ければ(古いキーがあればその値、それも無ければ)既定値。"""
    if key in settings:
        return settings[key]
    legacy_key = LEGACY_FALLBACK_KEYS.get(key)
    if legacy_key is not None and legacy_key in settings:
        return settings[legacy_key]
    # 既定値のリストや辞書を呼び出し側が書き換えても、既定値が変わらないように
    return copy.deepcopy(AXIS_SETTING_DEFAULTS[key])
