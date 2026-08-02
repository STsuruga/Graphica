import logging
import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
import matplotlib.ticker as ticker

logger = logging.getLogger(__name__)

# 目盛り間隔が細かすぎて描画が固まる/処理落ちするのを防ぐための上限。
# (軸範囲 / 間隔) がこれを超える場合は、間隔を自動的に粗くする。
# ★ matplotlib 自体が Locator.MAXTICKS=1000 を超えると警告を出すため、
#   境界の丸め誤差でそこに接触しないよう、余裕を持たせた値にしている。
MAX_TICKS_PER_AXIS = 500


def _safe_multiple_locator(interval, axis_min, axis_max):
    """
    MultipleLocator(interval) を作るが、現在の軸範囲に対して目盛りの本数が
    多すぎる場合は、間隔を MAX_TICKS_PER_AXIS 本相当まで自動的に粗くする。
    """
    axis_range = abs(axis_max - axis_min)
    if axis_range > 0 and interval > 0:
        estimated_ticks = axis_range / interval
        if estimated_ticks > MAX_TICKS_PER_AXIS:
            adjusted_interval = axis_range / MAX_TICKS_PER_AXIS
            logger.warning(
                "目盛り間隔 %.6g は軸範囲に対して細かすぎるため、%.6g に調整しました。",
                interval, adjusted_interval
            )
            interval = adjusted_interval
    return ticker.MultipleLocator(interval)


# --- ダークモード用の配色 ---
DARK_FIGURE_FACECOLOR = '#2b2b2b'
DARK_AXES_FACECOLOR = '#1e1e1e'
DARK_TEXT_COLOR = '#e0e0e0'
LIGHT_FIGURE_FACECOLOR = '#ffffff'
LIGHT_AXES_FACECOLOR = '#ffffff'
LIGHT_TEXT_COLOR = '#000000'


class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)

        # グラフの軸(Axes)の管理も、ウィンドウではなくCanvas側で行う
        self.all_axes = []
        self.all_secondary_axes = []
        self.dark_mode = False # ダークモードが有効かどうか (main_windowから設定される)

    def _effective_text_color(self, configured_color):
        """
        ダークモード時、設定値がデフォルトの黒 ('#000000') のままだと
        暗い背景で文字が見えなくなるため、白系の色に自動変換する。
        ユーザーが明示的に別の色を選んでいる場合はそれをそのまま尊重する。
        """
        if self.dark_mode and configured_color == '#000000':
            return DARK_TEXT_COLOR
        return configured_color

    def redraw_all(self, datasets, rows, cols, all_plot_settings):
        """メインウィンドウから呼ばれる、全体の再描画メソッド"""
        self.fig.clf()
        self.all_axes.clear()
        self.all_secondary_axes.clear()
        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)

        if rows * cols == 0:
            return False

        is_secondary_visible_global = False

        for i in range(rows * cols):
            ax = self.fig.add_subplot(rows, cols, i + 1)
            self.all_axes.append(ax)
            self.all_secondary_axes.append(None)

        for index, ax in enumerate(self.all_axes):
            if index < len(all_plot_settings):
                settings = all_plot_settings[index]
            else:
                continue

            # データの描画
            self._draw_data(ax, index, datasets)
            # 外観の適用
            self._apply_appearance(ax, index, settings)

            if self.all_secondary_axes[index] is not None:
                is_secondary_visible_global = True

        try:
            self.fig.tight_layout()
        except ValueError:
            pass

        self.draw()
        return is_secondary_visible_global # UI更新用にメインウィンドウへ結果を返す

    def update_appearance_only(self, all_plot_settings):
        """データはそのままに、外観設定だけを適用し直す（軽量版）"""
        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)
        for index, ax in enumerate(self.all_axes):
            if index < len(all_plot_settings):
                settings = all_plot_settings[index]
                self._apply_appearance(ax, index, settings)
        try:
            self.fig.tight_layout()
        except ValueError:
            pass
        self.draw()

    def _draw_data(self, ax, axis_index, datasets):
        """指定された軸にデータをプロットする"""
        datasets_for_this_axis = [ds for ds in datasets if ds.subplot_target == axis_index]
        needs_secondary = any(ds.use_secondary_y for ds in datasets_for_this_axis)
        
        secondary_ax = None
        if needs_secondary:
            secondary_ax = ax.twinx()
            self.all_secondary_axes[axis_index] = secondary_ax

        for ds in datasets_for_this_axis:
            target_ax = secondary_ax if ds.use_secondary_y else ax
            if target_ax is None: continue

            if ds.smoothing and len(ds.x_data) > 1:
                sort_indices = np.argsort(ds.x_data)
                x_sorted = ds.x_data[sort_indices]
                y_sorted = ds.y_data[sort_indices]
                try:
                    f = CubicSpline(x_sorted, y_sorted)
                    x_smooth = np.linspace(x_sorted.min(), x_sorted.max(), 200)
                    y_smooth = f(x_smooth)
                    (artist_line,) = target_ax.plot(x_smooth, y_smooth, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name)
                    ds.artist = artist_line
                    if ds.plot_type == 'Line+Scatter':
                        target_ax.scatter(ds.x_data, ds.y_data, color=ds.color, marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha)
                except ValueError:
                    (artist,) = target_ax.plot(ds.x_data, ds.y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name)
                    ds.artist = artist
            else:
                if ds.plot_type == 'Line':
                    (artist,) = target_ax.plot(ds.x_data, ds.y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name)
                    ds.artist = artist
                elif ds.plot_type == 'Scatter':
                    artist = target_ax.scatter(ds.x_data, ds.y_data, color=ds.color, marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha, label=ds.name)
                    ds.artist = artist
                elif ds.plot_type == 'Line+Scatter':
                    (artist,) = target_ax.plot(ds.x_data, ds.y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, marker=ds.marker, markersize=ds.markersize, alpha=ds.alpha, label=ds.name)
                    ds.artist = artist

            # ★ エラーバー (X/Y誤差列が設定されている場合のみ描画)
            # fmt='none' なので線やマーカーは追加せず、誤差の縦横棒のみを
            # 元データ点 (平滑化前) の位置に重ねて描画する。
            if ds.x_err_col_name or ds.y_err_col_name:
                target_ax.errorbar(
                    ds.x_data, ds.y_data,
                    xerr=ds.x_err_data, yerr=ds.y_err_data,
                    fmt='none', ecolor=ds.color, elinewidth=ds.linewidth, alpha=ds.alpha, capsize=3
                )

    def _apply_appearance(self, ax, axis_index, settings):
        """指定された軸に外観設定を適用する"""
        secondary_ax = self.all_secondary_axes[axis_index]

        ax.set_facecolor(DARK_AXES_FACECOLOR if self.dark_mode else LIGHT_AXES_FACECOLOR)

        if settings.get('x_autoscale', True): ax.autoscale(enable=True, axis='x', tight=True)
        else:
            min_val, max_val = settings.get('x_min', 0), settings.get('x_max', 1)
            if min_val < max_val: ax.set_xlim(min_val, max_val)

        if settings.get('y_autoscale', True): ax.autoscale(enable=True, axis='y', tight=True)
        else:
            min_val, max_val = settings.get('y_min', 0), settings.get('y_max', 1)
            if min_val < max_val: ax.set_ylim(min_val, max_val)

        ax.set_xscale('log' if settings.get('x_log', False) else 'linear')
        ax.xaxis.set_inverted(settings.get('x_invert', False))
        ax.set_yscale('log' if settings.get('y_log', False) else 'linear')
        ax.yaxis.set_inverted(settings.get('y_invert', False))

        x_min_lim, x_max_lim = ax.get_xlim()
        y_min_lim, y_max_lim = ax.get_ylim()

        if settings.get('x_major_tick_mode', 0) == 0: ax.xaxis.set_major_locator(ticker.AutoLocator())
        else:
            interval = settings.get('x_major_tick_interval', 1)
            if interval > 0: ax.xaxis.set_major_locator(_safe_multiple_locator(interval, x_min_lim, x_max_lim))

        if settings.get('y_major_tick_mode', 0) == 0: ax.yaxis.set_major_locator(ticker.AutoLocator())
        else:
            interval = settings.get('y_major_tick_interval', 1)
            if interval > 0: ax.yaxis.set_major_locator(_safe_multiple_locator(interval, y_min_lim, y_max_lim))

        if settings.get('x_minor_ticks_visible', False):
            interval = settings.get('x_minor_tick_interval', 0.5)
            if interval > 0: ax.xaxis.set_minor_locator(_safe_multiple_locator(interval, x_min_lim, x_max_lim))
        else: ax.xaxis.set_minor_locator(ticker.NullLocator())

        if settings.get('y_minor_ticks_visible', False):
            interval = settings.get('y_minor_tick_interval', 0.5)
            if interval > 0: ax.yaxis.set_minor_locator(_safe_multiple_locator(interval, y_min_lim, y_max_lim))
        else: ax.yaxis.set_minor_locator(ticker.NullLocator())

        tick_font_dict = settings.get('tick_font', {})
        label_font_dict = settings.get('axis_label_font', {})
        tick_color = self._effective_text_color(settings.get('tick_color', '#000000'))
        label_color = self._effective_text_color(settings.get('axis_label_color', '#000000'))

        ax.set_title(settings.get('title', ''), **label_font_dict, color=label_color)
        ax.set_xlabel(settings.get('x_label', ''), **label_font_dict, color=label_color)
        ax.set_ylabel(settings.get('y_label', ''), **label_font_dict, color=label_color)

        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set(**tick_font_dict)
            label.set_color(tick_color)

        spine_width = settings.get('spine_width', 1.0)
        spine_color = self._effective_text_color(settings.get('spine_color', '#000000'))
        tick_width = settings.get('tick_width', 0.8)
        major_dir = settings.get('major_tick_direction', 'out')
        minor_dir = settings.get('minor_tick_direction', 'out')

        for spine in ax.spines.values():
            spine.set_linewidth(spine_width)
            spine.set_color(spine_color)

        ax.tick_params(axis='both', which='major', width=tick_width, color=spine_color, labelcolor=tick_color, direction=major_dir)
        ax.tick_params(axis='both', which='minor', width=tick_width * 0.75, color=spine_color, direction=minor_dir)

        if settings.get('legend_visible', True):
            lines_primary, labels_primary = ax.get_legend_handles_labels()
            has_primary_data = bool(lines_primary)
            has_secondary_data = False
            lines_secondary, labels_secondary = [], []
            if secondary_ax:
                lines_secondary, labels_secondary = secondary_ax.get_legend_handles_labels()
                has_secondary_data = bool(lines_secondary)

            if has_primary_data or has_secondary_data:
                loc_code = settings.get('legend_loc', 'best')
                legend_font_dict = settings.get('legend_font', {})
                legend_color = self._effective_text_color(settings.get('legend_color', '#000000'))
                legend_font_prop = FontProperties(
                    family=legend_font_dict.get('family'),
                    size=legend_font_dict.get('size'),
                    weight=legend_font_dict.get('weight'),
                    style=legend_font_dict.get('style')
                )
                legend_obj = None
                if secondary_ax and has_primary_data and has_secondary_data:
                    legend_obj = ax.legend(lines_primary + lines_secondary, labels_primary + labels_secondary, loc=loc_code, prop=legend_font_prop)
                elif has_primary_data:
                    legend_obj = ax.legend(lines_primary, labels_primary, loc=loc_code, prop=legend_font_prop)
                elif secondary_ax and has_secondary_data:
                    legend_obj = secondary_ax.legend(lines_secondary, labels_secondary, loc=loc_code, prop=legend_font_prop)

                if legend_obj:
                    for text in legend_obj.get_texts(): text.set_color(legend_color)
                    try: legend_obj.draggable(True)
                    except AttributeError: pass
            else:
                if ax.get_legend() is not None: ax.get_legend().remove()
                if secondary_ax and secondary_ax.get_legend() is not None: secondary_ax.get_legend().remove()
        else:
            if ax.get_legend() is not None: ax.get_legend().remove()
            if secondary_ax and secondary_ax.get_legend() is not None: secondary_ax.get_legend().remove()

        if settings.get('grid_visible', False):
            ax.grid(True, which='major', linestyle='-', linewidth=0.8)
            if settings.get('minor_grid_visible', False): ax.grid(True, which='minor', linestyle='--', linewidth=0.5)
            else: ax.grid(False, which='minor')
        else:
            ax.grid(False, which='both')

        if secondary_ax:
            secondary_ax.autoscale(enable=True, axis='y', tight=True)
            secondary_ax.set_ylabel(settings.get('y2_label', ''), **label_font_dict, color=label_color)
            major_dir_y2 = settings.get('major_tick_direction_y2', 'out')
            minor_dir_y2 = settings.get('minor_tick_direction_y2', 'out')
            for label in secondary_ax.get_yticklabels():
                label.set(**tick_font_dict)
                label.set_color(tick_color)
            secondary_ax.tick_params(axis='y', which='major', width=tick_width, color=spine_color, labelcolor=tick_color, direction=major_dir_y2)
            secondary_ax.tick_params(axis='y', which='minor', width=tick_width * 0.75, color=spine_color, direction=minor_dir_y2)
            secondary_ax.spines['right'].set_linewidth(spine_width)
            secondary_ax.spines['right'].set_color(spine_color)
            secondary_ax.spines['right'].set_visible(True)
            secondary_ax.spines['left'].set_visible(False)
            secondary_ax.spines['top'].set_visible(False)
            secondary_ax.spines['bottom'].set_visible(False)
            ax.spines['right'].set_visible(False)
        else:
            ax.spines['right'].set_visible(True)
            ax.spines['right'].set_linewidth(spine_width)
            ax.spines['right'].set_color(spine_color)