"""1 つの軸の外観の設定。_AxisStyle を共有する決まった順の手順で、あとの手順は前の手順が作った状態を読む。"""
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import numpy as np
from graphica.core.axis_settings import axis_setting
from graphica.core.unit_conversion import X_AXIS_UNIT_LABELS, X_AXIS_UNIT_NONE, convert_x_axis_unit
from graphica.gui.mathtext_preview import families_for_texts, font_kwargs_for_text
from graphica.gui.rendering.common import (
    DARK_AXES_FACECOLOR, DARK_GRID_COLOR, DARK_LEGEND_EDGECOLOR, DARK_LEGEND_FACECOLOR, LIGHT_AXES_FACECOLOR,
    LIGHT_GRID_COLOR, LIGHT_LEGEND_EDGECOLOR, LIGHT_LEGEND_FACECOLOR, _AxisStyle, _LOG_MINOR_SUBS_PRESETS,
    _apply_legend_order, _apply_tick_decimal_places, _apply_tick_format_mode, _legend_position_from_settings,
    _resolve_tick_lengths, _safe_multiple_locator)
from matplotlib.font_manager import FontProperties


def apply_appearance(canvas, ax, axis_index, settings):
    """その軸に見た目の設定を当てる。matplotlib の状態に依存するので、下の順番は変えない。"""
    secondary_ax = canvas.all_secondary_axes[axis_index]
    ax.set_facecolor(DARK_AXES_FACECOLOR if canvas.dark_mode else LIGHT_AXES_FACECOLOR)

    is_date_x = axis_index < len(canvas.axis_is_date_x) and canvas.axis_is_date_x[axis_index]
    # 文字列カテゴリ軸では、範囲・対数などの数値向けの設定はカテゴリの位置と噛み合わないので使わない
    is_category_x = axis_index < len(canvas.axis_is_category_x) and canvas.axis_is_category_x[axis_index]

    canvas._apply_limits_and_scale(ax, settings, is_category_x)
    canvas._apply_tick_locators(ax, settings, is_date_x, is_category_x)
    style = canvas._axis_text_and_line_style(settings)
    canvas._apply_titles_and_labels(ax, settings, style)
    canvas._apply_spines_and_tick_marks(ax, settings, style)
    canvas._apply_legend(ax, secondary_ax, settings)
    canvas._apply_grid(ax, settings)
    canvas._apply_secondary_y_axis(ax, secondary_ax, settings, style)
    canvas._apply_unit_conversion_x_axis(ax, settings, style, is_date_x, is_category_x)
    canvas._apply_colorbar(ax, axis_index, settings, style)


def apply_axis_range(ax, settings, axis_key, is_category_x=False):
    """設定どおりの範囲を当てる。axis_key は 'x' / 'y' / 'y2'('y2' なら ax は第2Y軸)。描画と範囲のリセットの共通の経路。"""
    which = 'x' if axis_key == 'x' else 'y'
    if (axis_key == 'x' and is_category_x) or axis_setting(settings, f'{axis_key}_autoscale'):
        ax.autoscale(enable=True, axis=which, tight=True)
        return
    min_val, max_val = axis_setting(settings, f'{axis_key}_min'), axis_setting(settings, f'{axis_key}_max')
    if min_val < max_val:
        (ax.set_xlim if which == 'x' else ax.set_ylim)(min_val, max_val)


def apply_limits_and_scale(canvas, ax, settings, is_category_x):
    apply_axis_range(ax, settings, 'x', is_category_x)
    apply_axis_range(ax, settings, 'y')

    if not is_category_x:
        # set_xscale は同じ 'linear' でも Locator/Formatter を既定に戻してしまう。
        # カテゴリ軸では matplotlib が付けたカテゴリ用のものを残したいので呼ばない
        ax.set_xscale('log' if axis_setting(settings, 'x_log') else 'linear')
    ax.xaxis.set_inverted(axis_setting(settings, 'x_invert'))
    ax.set_yscale('log' if axis_setting(settings, 'y_log') else 'linear')
    ax.yaxis.set_inverted(axis_setting(settings, 'y_invert'))


def apply_tick_locators(canvas, ax, settings, is_date_x, is_category_x):
    x_min_lim, x_max_lim = ax.get_xlim()
    y_min_lim, y_max_lim = ax.get_ylim()

    if is_date_x:
        # 日時の軸は範囲に合わせて年・月・日・時刻の間隔と表記を自動で選ぶ(間隔の手動指定は使わない)
        date_locator = mdates.AutoDateLocator()
        ax.xaxis.set_major_locator(date_locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(date_locator))
    elif is_category_x:
        # matplotlib が付けたカテゴリ用の目盛りのまま(数値用で上書きするとラベルが崩れる)
        pass
    elif axis_setting(settings, 'x_major_tick_mode') == 0: ax.xaxis.set_major_locator(ticker.AutoLocator())
    else:
        interval = axis_setting(settings, 'x_major_tick_interval')
        if interval > 0: ax.xaxis.set_major_locator(_safe_multiple_locator(interval, x_min_lim, x_max_lim))

    if axis_setting(settings, 'y_major_tick_mode') == 0: ax.yaxis.set_major_locator(ticker.AutoLocator())
    else:
        interval = axis_setting(settings, 'y_major_tick_interval')
        if interval > 0: ax.yaxis.set_major_locator(_safe_multiple_locator(interval, y_min_lim, y_max_lim))

    if is_date_x or is_category_x:
        ax.xaxis.set_minor_locator(ticker.NullLocator())
    elif axis_setting(settings, 'x_minor_ticks_visible'):
        if axis_setting(settings, 'x_log'):
            # 対数軸は間隔指定の MultipleLocator ではなく LogLocator にする
            subs = _LOG_MINOR_SUBS_PRESETS.get(axis_setting(settings, 'x_log_minor_subs'), 'auto')
            ax.xaxis.set_minor_locator(ticker.LogLocator(base=10.0, subs=subs))
            ax.xaxis.set_minor_formatter(
                ticker.LogFormatterSciNotation(base=10.0, labelOnlyBase=False)
                if axis_setting(settings, 'x_log_minor_labels') else ticker.NullFormatter()
            )
        else:
            interval = axis_setting(settings, 'x_minor_tick_interval')
            if interval > 0: ax.xaxis.set_minor_locator(_safe_multiple_locator(interval, x_min_lim, x_max_lim))
    else: ax.xaxis.set_minor_locator(ticker.NullLocator())

    if axis_setting(settings, 'y_minor_ticks_visible'):
        if axis_setting(settings, 'y_log'):
            subs = _LOG_MINOR_SUBS_PRESETS.get(axis_setting(settings, 'y_log_minor_subs'), 'auto')
            ax.yaxis.set_minor_locator(ticker.LogLocator(base=10.0, subs=subs))
            ax.yaxis.set_minor_formatter(
                ticker.LogFormatterSciNotation(base=10.0, labelOnlyBase=False)
                if axis_setting(settings, 'y_log_minor_labels') else ticker.NullFormatter()
            )
        else:
            interval = axis_setting(settings, 'y_minor_tick_interval')
            if interval > 0: ax.yaxis.set_minor_locator(_safe_multiple_locator(interval, y_min_lim, y_max_lim))
    else: ax.yaxis.set_minor_locator(ticker.NullLocator())

    # 日付・カテゴリの X 軸は専用の表記を付けてあるので、数値の軸だけ
    if not is_date_x and not is_category_x:
        _apply_tick_format_mode(ax.xaxis, axis_setting(settings, 'x_tick_format_mode'))
        _apply_tick_decimal_places(ax.xaxis, axis_setting(settings, 'x_tick_decimals'))
    _apply_tick_format_mode(ax.yaxis, axis_setting(settings, 'y_tick_format_mode'))
    _apply_tick_decimal_places(ax.yaxis, axis_setting(settings, 'y_tick_decimals'))


def axis_text_and_line_style(canvas, settings):
    """文字と線の見た目のうち、軸・第2軸・カラーバーで共通に使うもの(ダークモードの色の読み替え後)。"""
    major_tick_length, minor_tick_length = _resolve_tick_lengths(settings)
    return _AxisStyle(
        tick_font=axis_setting(settings, 'tick_font'),
        label_font=axis_setting(settings, 'axis_label_font'),
        tick_color=canvas._effective_text_color(axis_setting(settings, 'tick_color')),
        label_color=canvas._effective_text_color(axis_setting(settings, 'axis_label_color')),
        spine_width=axis_setting(settings, 'spine_width'),
        spine_color=canvas._effective_text_color(axis_setting(settings, 'spine_color')),
        tick_width=axis_setting(settings, 'tick_width'),
        major_tick_length=major_tick_length,
        minor_tick_length=minor_tick_length,
    )


def apply_titles_and_labels(canvas, ax, settings, style):
    title = axis_setting(settings, 'title')
    ax.set_title(title, **font_kwargs_for_text(title, style.label_font), color=style.label_color)
    # 非表示にしても文字列は消さない(表示に戻したときに打ち直さなくて済むように)
    x_label_text = axis_setting(settings, 'x_label') if axis_setting(settings, 'x_label_visible') else ''
    y_label_text = axis_setting(settings, 'y_label') if axis_setting(settings, 'y_label_visible') else ''
    ax.set_xlabel(x_label_text, **font_kwargs_for_text(x_label_text, style.label_font), color=style.label_color)
    ax.set_ylabel(y_label_text, **font_kwargs_for_text(y_label_text, style.label_font), color=style.label_color)
    # タイトルのクリックで、その軸を編集対象にする
    ax.title.set_picker(5)

    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set(**style.tick_font)
        label.set_color(style.tick_color)


def apply_spines_and_tick_marks(canvas, ax, settings, style):
    for spine in ax.spines.values():
        spine.set_linewidth(style.spine_width)
        spine.set_color(style.spine_color)

    # 表示/非表示は毎回 True/False を明示する。tick_params の値は ax.cla() をまたいで残るので、
    # 隠すときだけ指定すると表示に戻せない。軸の共有で内側の目盛数値を隠すのは呼び出し側が後で行う
    major_dir = axis_setting(settings, 'major_tick_direction')
    minor_dir = axis_setting(settings, 'minor_tick_direction')
    x_ticks_visible = axis_setting(settings, 'x_ticks_visible')
    y_ticks_visible = axis_setting(settings, 'y_ticks_visible')
    x_tick_labels_visible = axis_setting(settings, 'x_tick_labels_visible')
    y_tick_labels_visible = axis_setting(settings, 'y_tick_labels_visible')

    ax.tick_params(axis='x', which='major', width=style.tick_width, length=style.major_tick_length, color=style.spine_color, labelcolor=style.tick_color,
                    direction=major_dir, bottom=x_ticks_visible, labelbottom=x_tick_labels_visible)
    ax.tick_params(axis='x', which='minor', width=style.tick_width * 0.75, length=style.minor_tick_length, color=style.spine_color,
                    direction=minor_dir, bottom=x_ticks_visible, labelbottom=x_tick_labels_visible)
    ax.tick_params(axis='y', which='major', width=style.tick_width, length=style.major_tick_length, color=style.spine_color, labelcolor=style.tick_color,
                    direction=major_dir, left=y_ticks_visible, labelleft=y_tick_labels_visible)
    ax.tick_params(axis='y', which='minor', width=style.tick_width * 0.75, length=style.minor_tick_length, color=style.spine_color,
                    direction=minor_dir, left=y_ticks_visible, labelleft=y_tick_labels_visible)


def apply_legend(canvas, ax, secondary_ax, settings):
    lines_primary, labels_primary, lines_secondary, labels_secondary = [], [], [], []
    if axis_setting(settings, 'legend_visible'):
        lines_primary, labels_primary = ax.get_legend_handles_labels()
        if secondary_ax:
            lines_secondary, labels_secondary = secondary_ax.get_legend_handles_labels()
    has_primary_data = bool(lines_primary)
    has_secondary_data = bool(lines_secondary)
    if not (has_primary_data or has_secondary_data):
        if ax.get_legend() is not None: ax.get_legend().remove()
        if secondary_ax and secondary_ax.get_legend() is not None: secondary_ax.get_legend().remove()
        return

    loc_code = axis_setting(settings, 'legend_loc')
    # ドラッグで動かした位置(軸の左下 (0, 0)・右上 (1, 1) での凡例の左下)があれば、位置の選択より優先する
    dragged_position = _legend_position_from_settings(settings)
    if dragged_position is not None:
        loc_code = dragged_position
    legend_font_dict = axis_setting(settings, 'legend_font')
    legend_color = canvas._effective_text_color(axis_setting(settings, 'legend_color'))
    legend_font_prop = FontProperties(
        family=families_for_texts(labels_primary + labels_secondary, legend_font_dict.get('family')),
        size=legend_font_dict.get('size'),
        weight=legend_font_dict.get('weight'),
        style=legend_font_dict.get('style'),
        stretch=legend_font_dict.get('stretch')
    )
    # 凡例の並びは描画順とは別に指定できる
    legend_order = axis_setting(settings, 'legend_order')
    legend_obj = None
    if secondary_ax and has_primary_data and has_secondary_data:
        combined_lines, combined_labels = _apply_legend_order(
            lines_primary + lines_secondary, labels_primary + labels_secondary, legend_order
        )
        legend_obj = ax.legend(combined_lines, combined_labels, loc=loc_code, prop=legend_font_prop)
    elif has_primary_data:
        ordered_lines, ordered_labels = _apply_legend_order(lines_primary, labels_primary, legend_order)
        legend_obj = ax.legend(ordered_lines, ordered_labels, loc=loc_code, prop=legend_font_prop)
    elif secondary_ax and has_secondary_data:
        ordered_lines, ordered_labels = _apply_legend_order(lines_secondary, labels_secondary, legend_order)
        legend_obj = secondary_ax.legend(ordered_lines, ordered_labels, loc=loc_code, prop=legend_font_prop)

    if legend_obj:
        for text in legend_obj.get_texts(): text.set_color(legend_color)
        frame = legend_obj.get_frame()
        if canvas.dark_mode:
            frame.set_facecolor(DARK_LEGEND_FACECOLOR)
            frame.set_edgecolor(DARK_LEGEND_EDGECOLOR)
        else:
            frame.set_facecolor(LIGHT_LEGEND_FACECOLOR)
            frame.set_edgecolor(LIGHT_LEGEND_EDGECOLOR)
        frame.set_alpha(0.92)
        # 離した位置が legend._loc に入り、PlotterApp がそれを設定へ保存する
        # (matplotlib 3.x に Legend.draggable() は無い)
        legend_obj.set_draggable(True, update='loc')


def apply_grid(canvas, ax, settings):
    """ax.grid() は指定した which/axis にしか効かないので、X/Y × 主/補助 を個別に呼ぶ。"""
    if not axis_setting(settings, 'grid_visible'):
        ax.grid(False, which='both')
        return
    grid_color = DARK_GRID_COLOR if canvas.dark_mode else LIGHT_GRID_COLOR
    for grid_axis in ('x', 'y'):
        ax.grid(
            True, which='major', axis=grid_axis,
            linestyle=axis_setting(settings, f'{grid_axis}_major_grid_linestyle'),
            linewidth=axis_setting(settings, f'{grid_axis}_major_grid_width'),
            alpha=axis_setting(settings, f'{grid_axis}_major_grid_alpha'),
            color=grid_color,
        )
        if axis_setting(settings, 'minor_grid_visible'):
            ax.grid(
                True, which='minor', axis=grid_axis,
                linestyle=axis_setting(settings, f'{grid_axis}_minor_grid_linestyle'),
                linewidth=axis_setting(settings, f'{grid_axis}_minor_grid_width'),
                alpha=axis_setting(settings, f'{grid_axis}_minor_grid_alpha'),
                color=grid_color,
            )
        else:
            ax.grid(False, which='minor', axis=grid_axis)


def _apply_secondary_y_limits_and_ticks(secondary_ax, settings):
    """主の Y 軸と同じ手順(範囲 → 対数 → 反転 → 目盛り)。既定(自動・線形・目盛り自動)では何も上書きしない。"""
    apply_axis_range(secondary_ax, settings, 'y2')
    is_log = axis_setting(settings, 'y2_log')
    # set_yscale は同じ値でも目盛りの Locator を既定に戻すので、変わるときだけ呼ぶ
    if secondary_ax.get_yscale() != ('log' if is_log else 'linear'):
        secondary_ax.set_yscale('log' if is_log else 'linear')
    secondary_ax.yaxis.set_inverted(axis_setting(settings, 'y2_invert'))

    y_min_lim, y_max_lim = secondary_ax.get_ylim()
    if axis_setting(settings, 'y2_major_tick_mode') == 1:
        interval = axis_setting(settings, 'y2_major_tick_interval')
        if interval > 0 and not is_log:
            secondary_ax.yaxis.set_major_locator(_safe_multiple_locator(interval, y_min_lim, y_max_lim))
    if axis_setting(settings, 'y2_minor_ticks_visible'):
        if is_log:
            secondary_ax.yaxis.set_minor_locator(ticker.LogLocator(base=10.0, subs='auto'))
        else:
            interval = axis_setting(settings, 'y2_minor_tick_interval')
            if interval > 0:
                secondary_ax.yaxis.set_minor_locator(_safe_multiple_locator(interval, y_min_lim, y_max_lim))
    elif not is_log:
        secondary_ax.yaxis.set_minor_locator(ticker.NullLocator())


def apply_secondary_y_axis(canvas, ax, secondary_ax, settings, style):
    """第2Y軸があれば右の枠線と目盛りを第2Y軸に任せ、無ければ主軸の右の枠線を出す。"""
    if not secondary_ax:
        ax.spines['right'].set_visible(True)
        ax.spines['right'].set_linewidth(style.spine_width)
        ax.spines['right'].set_color(style.spine_color)
        return
    _apply_secondary_y_limits_and_ticks(secondary_ax, settings)
    y2_label = axis_setting(settings, 'y2_label')
    secondary_ax.set_ylabel(y2_label, **font_kwargs_for_text(y2_label, style.label_font), color=style.label_color)
    major_dir_y2 = axis_setting(settings, 'major_tick_direction_y2')
    minor_dir_y2 = axis_setting(settings, 'minor_tick_direction_y2')
    for label in secondary_ax.get_yticklabels():
        label.set(**style.tick_font)
        label.set_color(style.tick_color)
    secondary_ax.tick_params(axis='y', which='major', width=style.tick_width, length=style.major_tick_length, color=style.spine_color, labelcolor=style.tick_color, direction=major_dir_y2)
    secondary_ax.tick_params(axis='y', which='minor', width=style.tick_width * 0.75, length=style.minor_tick_length, color=style.spine_color, direction=minor_dir_y2)
    secondary_ax.spines['right'].set_linewidth(style.spine_width)
    secondary_ax.spines['right'].set_color(style.spine_color)
    secondary_ax.spines['right'].set_visible(True)
    secondary_ax.spines['left'].set_visible(False)
    secondary_ax.spines['top'].set_visible(False)
    secondary_ax.spines['bottom'].set_visible(False)
    ax.spines['right'].set_visible(False)


def apply_unit_conversion_x_axis(canvas, ax, settings, style, is_date_x, is_category_x):
    """X の単位と表示したい単位が別々に選ばれていれば、上に単位を変換した第2X軸を付ける(数値の軸だけ)。"""
    source_unit = axis_setting(settings, 'x_secondary_axis_source_unit')
    target_unit = axis_setting(settings, 'x_secondary_axis_target_unit')
    # 範囲の端が変換で inf/nan になる(波長 0nm など)と secondary_xaxis が例外を出し、描画全体が失敗する
    if not (not is_date_x and not is_category_x
            and source_unit != X_AXIS_UNIT_NONE and target_unit != X_AXIS_UNIT_NONE
            and source_unit != target_unit
            and np.all(np.isfinite(convert_x_axis_unit(np.array(ax.get_xlim()), source_unit, target_unit)))):
        return

    def _forward(x, _from=source_unit, _to=target_unit):
        return convert_x_axis_unit(x, _from, _to)

    def _inverse(x, _from=source_unit, _to=target_unit):
        return convert_x_axis_unit(x, _to, _from)

    secondary_x_ax = ax.secondary_xaxis('top', functions=(_forward, _inverse))
    # 逆数の変換では値域が極端に広がり、既定の AutoLocator が千本を超える目盛りを作ろうとする
    secondary_x_ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=8))
    secondary_x_ax.set_xlabel(X_AXIS_UNIT_LABELS.get(target_unit, target_unit),
                               **style.label_font, color=style.label_color)
    for label in secondary_x_ax.get_xticklabels():
        label.set(**style.tick_font)
        label.set_color(style.tick_color)
    secondary_x_ax.tick_params(axis='x', which='major', width=style.tick_width, length=style.major_tick_length,
                                color=style.spine_color, labelcolor=style.tick_color,
                                direction=axis_setting(settings, 'major_tick_direction'))
    secondary_x_ax.spines['top'].set_linewidth(style.spine_width)
    secondary_x_ax.spines['top'].set_color(style.spine_color)


def apply_colorbar(canvas, ax, axis_index, settings, style):
    """
    2Dマップ(または値で色分けした散布図)がこの軸にあればカラーバーを付ける。
    location を渡すと向きは matplotlib が決めるので、orientation は渡さない(衝突しうる)。
    """
    mappable = canvas._axis_2d_mappables.get(axis_index)
    if mappable is None or not axis_setting(settings, 'colorbar_enabled'):
        return
    position = axis_setting(settings, 'colorbar_position')
    if position not in ('right', 'left', 'top', 'bottom'):
        position = 'right'
    try:
        fraction = float(axis_setting(settings, 'colorbar_width_fraction'))
    except (TypeError, ValueError):
        fraction = 0.05
    if fraction <= 0:
        fraction = 0.05
    cbar = canvas.fig.colorbar(mappable, ax=ax, location=position, fraction=fraction, pad=0.04)
    colorbar_label = axis_setting(settings, 'colorbar_label')
    if colorbar_label:
        cbar.set_label(colorbar_label, **font_kwargs_for_text(colorbar_label, style.label_font), color=style.label_color)
    for tick_label in cbar.ax.get_yticklabels() + cbar.ax.get_xticklabels():
        tick_label.set(**style.tick_font)
        tick_label.set_color(style.tick_color)
    cbar.outline.set_edgecolor(style.spine_color)
    cbar.outline.set_linewidth(style.spine_width)
