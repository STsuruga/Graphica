import json
import logging
from typing import NamedTuple
import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from mpl_toolkits.axes_grid1.inset_locator import mark_inset
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Polygon
import matplotlib.ticker as ticker
import matplotlib.dates as mdates

from graphica.core.axis_settings import AXIS_SETTING_DEFAULTS, axis_setting
from graphica.gui.app_settings import DEFAULT_POINT_LABEL_MAX_POINTS
from graphica.gui.plot_type_drawers import BUILTIN_PLOT_TYPE_DRAWERS
from graphica.gui.theme import LIGHT_TOKENS, DARK_TOKENS
from graphica.core.analysis import (calculate_lttb_downsample, calculate_moving_average_smooth,
                           calculate_median_smooth, calculate_gaussian_smooth,
                           sample_standard_deviation)
from graphica.core.unit_conversion import convert_x_axis_unit, X_AXIS_UNIT_NONE, X_AXIS_UNIT_LABELS

# 注釈を「まだ一度も描いていない」を表す番兵。None だとキーが None のときに一致してしまう
_NO_KEY = object()

logger = logging.getLogger(__name__)

# 目盛りの本数の上限(細かすぎる間隔で描画が固まらないように)。matplotlib の MAXTICKS=1000 に丸め誤差で届かない値
MAX_TICKS_PER_AXIS = 500

# ウォーターフォールのトレースと背景の zorder の範囲。目盛(約2.01)と枠線(2.5)より下に収めて、隠さないようにする
WATERFALL_ZORDER_BASE = 0.1
WATERFALL_ZORDER_TOP = 1.9

# 立体風の縮小の下限。段が多いと振幅が潰れる・反転するので 0.2 倍で止める
WATERFALL_DEPTH_SHRINK_MIN_SCALE = 0.2


def _waterfall_depth_scale(w_idx, enabled, shrink_ratio):
    """段 w_idx のトレースの Y に掛ける倍率。奥ほど縮めて立体風にする(無効なら 1.0)。"""
    if not enabled:
        return 1.0
    return max(WATERFALL_DEPTH_SHRINK_MIN_SCALE, 1.0 - shrink_ratio * w_idx)


class _WaterfallLayout(NamedTuple):
    index: dict      # dataset_id -> 段(0 が一番手前)
    count: int
    baseline: float  # 奥のトレースを隠す背景を敷く下端


def _waterfall_layout(datasets):
    """
    ウォーターフォールを有効にしたデータセットに、並び順で段を振る。非表示のものも数に入れる
    (隠しても後ろの段が繰り上がって図が変わらないように)。下端は、ずらした後の全トレースの最小値から少し下。
    """
    waterfall_datasets = [ds for ds in datasets if ds.waterfall_enabled]
    baseline = 0.0
    shifted_mins, shifted_maxs = [], []
    for i, wds in enumerate(waterfall_datasets):
        if len(wds.y_data) == 0:
            continue
        depth_scale = _waterfall_depth_scale(
            i, wds.waterfall_depth_shrink_enabled, wds.waterfall_depth_shrink_ratio)
        y_shift = i * wds.waterfall_offset_y
        shifted_mins.append(float(np.nanmin(wds.y_data)) * depth_scale + y_shift)
        shifted_maxs.append(float(np.nanmax(wds.y_data)) * depth_scale + y_shift)
    if shifted_mins:
        y_min_all, y_max_all = min(shifted_mins), max(shifted_maxs)
        margin = (y_max_all - y_min_all) * 0.05 if y_max_all > y_min_all else 1.0
        baseline = y_min_all - margin
    return _WaterfallLayout(
        {ds.dataset_id: i for i, ds in enumerate(waterfall_datasets)}, len(waterfall_datasets), baseline)


class _AxisStyle(NamedTuple):
    tick_font: dict
    label_font: dict
    tick_color: str
    label_color: str
    spine_width: float
    spine_color: str
    tick_width: float
    major_tick_length: float
    minor_tick_length: float

# 対数軸の補助目盛りの設定値 -> LogLocator の subs(補助目盛りを打つ仮数)。'auto' は表示の桁数に応じて間引く
_LOG_MINOR_SUBS_PRESETS = {
    'auto': 'auto',
    'all': (2, 3, 4, 5, 6, 7, 8, 9),
    'few': (2, 5),
    'one': (5,),
}

# 矢印注釈の形 -> matplotlib の arrowstyle。キーの無い古い注釈は 'single'
_ARROW_STYLE_MAP = {
    'single': '->',
    'double': '<->',
    'bracket': ']-[',
}

# 拡大図の置き場所 -> 軸の中での左下の位置(軸に対する割合)
_INSET_CORNER_ORIGINS = {
    '右上': (0.55, 0.55),
    '左上': (0.05, 0.55),
    '右下': (0.55, 0.05),
    '左下': (0.05, 0.05),
}

# 'Line' の点がこれを超えたら、表示では LTTB で約 TARGET 点に間引く(線の形を保つ方法なので、点の疎密が情報の散布図には使わない)
LTTB_DOWNSAMPLE_THRESHOLD = 20000
LTTB_DOWNSAMPLE_TARGET_POINTS = 3000

# 2Dマップの1軸あたりの点数の上限。超えたら均等に間引く(エクスポートにも効く)
GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS = 500

# 領域ハイライトに色・透明度が無いときの値。region_highlight_mixin.py が書き込む既定値と揃えておく
REGION_HIGHLIGHT_DEFAULT_COLOR = '#F2A72B'
REGION_HIGHLIGHT_DEFAULT_ALPHA = 0.18


def _apply_legend_order(lines, labels, order):
    """凡例を order(ラベルの並び)の順にする。order に無いラベルは元の順のまま最後に付ける。"""
    if not order:
        return lines, labels
    order_index = {name: i for i, name in enumerate(order)}
    indices = sorted(
        range(len(labels)),
        key=lambda i: (0, order_index[labels[i]]) if labels[i] in order_index else (1, i)
    )
    return [lines[i] for i in indices], [labels[i] for i in indices]


def _apply_nan_policy(x_data, y_data, policy):
    """
    欠損値の方針を描く直前の点列に当てる(データ自体は変えない)。
    'gap' は何もしない(matplotlib が NaN で線を切る)。'ffill' は直前の値で埋める(先頭の NaN は残る)。
    'drop' は X か Y が欠けた点を除いて前後をつなぐ。知らない値は 'gap' と同じ。
    """
    if policy == 'ffill':
        return (
            pd.Series(x_data).ffill().to_numpy(),
            pd.Series(y_data).ffill().to_numpy(),
        )
    if policy == 'drop':
        # np.isnan は日時(datetime64)を扱えないので pandas で判定する
        x_series = pd.Series(x_data)
        y_series = pd.Series(y_data)
        valid = (~x_series.isna()) & (~y_series.isna())
        return x_series[valid].to_numpy(), y_series[valid].to_numpy()
    return x_data, y_data


# 統計値ラベルの見出し
STAT_LABEL_TITLES = {
    'r_squared': 'R²',
    'mean': '平均',
    'std': '標準偏差',
    'max': '最大値',
    'min': '最小値',
}


def _legend_position_from_settings(settings):
    """
    settings['legend_position'](ドラッグで動かした凡例の位置、[x, y])を
    legend の loc に渡せるタプルにする。未設定・壊れた値は None。
    """
    position = axis_setting(settings, 'legend_position')
    if not isinstance(position, (list, tuple)) or len(position) != 2:
        return None
    try:
        x, y = float(position[0]), float(position[1])
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(x) and np.isfinite(y)):
        return None
    return (x, y)


def _compute_stat_label_text(dataset, stat):
    """
    統計値ラベルの文字列を、描くたびにデータとフィット結果から計算する(データを変えると追従する)。
    データセットが消えた・まだ計算できないときは、何を待っているかが分かる文字列にする。
    """
    title = STAT_LABEL_TITLES.get(stat, stat)
    if dataset is None:
        return f"{title} = (データセットなし)"

    if stat == 'r_squared':
        fit_result = dataset.fit_result
        if not fit_result or fit_result.get('r_squared') is None:
            return f"{title} = (フィット未実行)"
        return f"{title} = {fit_result['r_squared']:.4g}"

    y = np.asarray(dataset.y_data, dtype=float)
    y = y[~np.isnan(y)]
    if len(y) == 0:
        return f"{title} = (データなし)"
    if stat == 'mean':
        value = np.mean(y)
    elif stat == 'std':
        if len(y) < 2:
            return f"{title} = (データ不足)"
        value = sample_standard_deviation(y)
    elif stat == 'max':
        value = np.max(y)
    elif stat == 'min':
        value = np.min(y)
    else:
        return f"{title} = (未対応の統計値)"
    return f"{title} = {value:.4g}"


def _safe_multiple_locator(interval, axis_min, axis_max):
    """間隔 interval の MultipleLocator。今の範囲で目盛りが多すぎるなら MAX_TICKS_PER_AXIS 本相当まで粗くする。"""
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


def _sci_each_formatter():
    """目盛りごとに指数で書く(例: 1.0×10^10)。"""
    def _fmt(value, pos=None):
        if value == 0:
            return "0"
        exponent = int(np.floor(np.log10(abs(value))))
        mantissa = value / (10 ** exponent)
        if abs(mantissa) >= 9.995:  # 丸めると 10.0 になるので桁を上げる
            mantissa /= 10
            exponent += 1
        return rf"${mantissa:.1f}\times10^{{{exponent}}}$"
    return ticker.FuncFormatter(_fmt)


def _apply_tick_format_mode(axis, mode):
    """
    mode: 0=自動(matplotlib のまま) / 1=指数を軸端にまとめる(×10^n) /
          2=目盛りごとに指数 / 3=常に小数で書く
    """
    if mode == 1:
        formatter = ticker.ScalarFormatter(useMathText=True)
        formatter.set_powerlimits((0, 0))
        axis.set_major_formatter(formatter)
    elif mode == 2:
        axis.set_major_formatter(_sci_each_formatter())
    elif mode == 3:
        formatter = ticker.ScalarFormatter(useOffset=False, useMathText=True)
        formatter.set_scientific(False)
        axis.set_major_formatter(formatter)


def _apply_tick_decimal_places(axis, decimals):
    """小数点以下の桁数を指定したら、指数表記の設定より優先して固定小数点で書く。負値・None は自動(何もしない)。"""
    if decimals is None or decimals < 0:
        return
    axis.set_major_formatter(ticker.FormatStrFormatter(f'%.{decimals}f'))


# 目盛線の長さは軸の大きさに対する割合ではなく pt。文字や線の太さも pt なので、割合にすると
# 大きく書き出したときや多パネル図で目盛りだけ長さがちぐはぐになる
DEFAULT_MAJOR_TICK_LENGTH = AXIS_SETTING_DEFAULTS['major_tick_length']
# 補助目盛が「自動」のときの主目盛に対する長さ(matplotlib の既定 2.0 / 3.5 と同じ)
MINOR_TICK_LENGTH_RATIO = 2.0 / 3.5
# 欄で補助目盛の長さ「自動」を表す値。判定は「負値なら自動」なので、この値に頼るのは欄だけ
MINOR_TICK_LENGTH_AUTO = -0.5


def _resolve_tick_lengths(settings):
    """(主目盛, 補助目盛) の長さを pt で返す。補助目盛が未指定・負値なら主目盛 × MINOR_TICK_LENGTH_RATIO。"""
    major = axis_setting(settings, 'major_tick_length')
    if major is None or major < 0:
        major = DEFAULT_MAJOR_TICK_LENGTH
    minor = axis_setting(settings, 'minor_tick_length')
    if minor is None or minor < 0:
        minor = major * MINOR_TICK_LENGTH_RATIO
    return major, minor


# グラフの配色は gui/theme.py のトークンから取る。Figure も Axes も surface にするのは、キャンバスを囲む
# Qt 側の余白(surface)との間に色の継ぎ目を作らないため
DARK_FIGURE_FACECOLOR = DARK_TOKENS['surface']
DARK_AXES_FACECOLOR = DARK_TOKENS['surface']
DARK_TEXT_COLOR = DARK_TOKENS['text_primary']
LIGHT_FIGURE_FACECOLOR = LIGHT_TOKENS['surface']
LIGHT_AXES_FACECOLOR = LIGHT_TOKENS['surface']
LIGHT_TEXT_COLOR = LIGHT_TOKENS['text_primary']

# 凡例は軸の背景と同化しないよう、一段違う面色と濃い枠線にする
DARK_LEGEND_FACECOLOR = DARK_TOKENS['surface_2']
DARK_LEGEND_EDGECOLOR = DARK_TOKENS['border_strong']
LIGHT_LEGEND_FACECOLOR = LIGHT_TOKENS['surface_2']
LIGHT_LEGEND_EDGECOLOR = LIGHT_TOKENS['border_strong']

DARK_GRID_COLOR = DARK_TOKENS['border_strong']
LIGHT_GRID_COLOR = LIGHT_TOKENS['border_strong']


class _CanvasDrawingMixin:
    """
    描画の本体。Qt に依存しないので、画面用の MplCanvas(FigureCanvasQTAgg)と
    一括エクスポート用の _HeadlessRenderCanvas(FigureCanvasAgg)の両方が使う。
    """

    def _init_drawing_state(self, width, height, dpi):
        self.fig = Figure(figsize=(width, height), dpi=dpi)

        self.all_axes = []
        self.all_secondary_axes = []
        # 軸ごとに、X が日時か(目盛りの付け方)・文字列カテゴリか(数値向けの設定を使わない)
        self.axis_is_date_x = []
        self.axis_is_category_x = []
        self.dark_mode = False
        self.point_label_max_points = DEFAULT_POINT_LABEL_MAX_POINTS
        # 軸ごとの描画済みの注釈。update_appearance_only は fig.clf() しないので、消してから描き直す
        self._annotation_artists = {}
        # 軸ごとに直近に描いた注釈の内容。同じなら描き直しを省く(_annotation_render_key)
        self._annotation_render_keys = {}
        # データエディタと連動する行のハイライト(dataset_id ごと)
        self._highlight_artists = {}
        # 間引いたデータセットの「描いた点の添字 -> visible_df の位置」(dataset_id ごと)。
        # データカーソルがクリックした点を正しい行に戻すのに使う。間引いていなければ入らない
        self.downsample_index_map = {}
        # 平滑化した曲線のデータセット。点が元の行と対応しないのでクリックで選ばせない。
        # データカーソルモードの一括 set_picker(cursor_mixin.py)もこれを見て除く
        self._non_pickable_dataset_ids = set()
        # 軸ごとのカラーバーの対象(2Dマップか値で色分けした散布図)。_apply_appearance に渡すため
        self._axis_2d_mappables = {}
        # ウォーターフォールの変換(dataset_id ごと)。トレースは
        #     表示X = データX + index * offset_x
        #     表示Y = データY * depth_scale + index * offset_y
        # に描かれるので、マウス位置をデータの行に対応づける側は逆変換(display_to_data)を通す。
        # 値は {'index', 'offset_x', 'offset_y', 'depth_scale'}。ウォーターフォールでなければ入らない
        self._waterfall_transforms = {}

    # --- ウォーターフォールの表示座標 ⇔ データ座標 ---

    def get_waterfall_transform(self, dataset_or_id):
        """
        データセットの今のウォーターフォール変換。無効または未描画なら None。

        Args:
            dataset_or_id: Dataset オブジェクト、または dataset_id。
        """
        dataset_id = getattr(dataset_or_id, 'dataset_id', dataset_or_id)
        return self._waterfall_transforms.get(dataset_id)

    def data_to_display(self, dataset_or_id, x, y):
        """データ座標(dataset.x_data/y_data と同じ)を、描かれている位置へ変換する。スカラーでも配列でもよい。ウォーターフォールでなければそのまま返す。"""
        transform = self.get_waterfall_transform(dataset_or_id)
        if transform is None:
            return x, y
        index = transform['index']
        display_x = x if transform['offset_x'] == 0 else x + index * transform['offset_x']
        display_y = y * transform['depth_scale'] + index * transform['offset_y']
        return display_x, display_y

    def display_to_data(self, dataset_or_id, x, y):
        """
        data_to_display() の逆。マウス位置をデータの行に対応づける処理(範囲選択・データカーソル・
        エディタ連動のハイライト・ピーク配置)は必ずこれを通す。通さないと積み重ねの2本目以降で位置がずれる。
        """
        transform = self.get_waterfall_transform(dataset_or_id)
        if transform is None:
            return x, y
        index = transform['index']
        data_x = x if transform['offset_x'] == 0 else x - index * transform['offset_x']
        # depth_scale は 0.2 以上に抑えてあるので 0 で割ることはない
        data_y = (y - index * transform['offset_y']) / transform['depth_scale']
        return data_x, data_y

    def _effective_text_color(self, configured_color):
        """ダークモードで既定の黒のままだと見えないので明るい色にする。利用者が選んだ別の色はそのまま。"""
        if self.dark_mode and configured_color == '#000000':
            return DARK_TEXT_COLOR
        return configured_color

    def _default_free_rect(self, index):
        """自由配置で新しい軸に割り当てる初期の (left, bottom, width, height)。少しずつずらして重ならないようにする。"""
        offset = 0.04 * (index % 6)
        left = min(0.1 + offset, 0.55)
        bottom = min(0.55 - offset, 0.55) if index % 2 == 0 else min(0.1 + offset, 0.5)
        return (left, max(bottom, 0.08), 0.45, 0.38)

    def _safe_draw(self):
        """
        self.draw() の失敗をログに残す。直接の draw() は例外を投げても、呼び出し元のシグナルの経路によっては
        どこにも記録されず「何も反映されない」だけになる(draw_idle 側は matplotlib が標準エラーに出すだけで、
        画面版の exe ではそれも見えない)。
        """
        try:
            self.draw()
        except Exception:
            logger.exception(
                "Figureの描画(self.draw())に失敗しました。"
                "グラフの表示が更新されていない可能性があります。"
            )

    def redraw_all(self, datasets, rows, cols, all_plot_settings, layout_mode='grid', panel_labels_enabled=False,
                    share_x_axis=False, share_y_axis=False, full_resolution=False):
        """
        Figure を作り直して全部の軸を描く。full_resolution=True なら間引かない(エクスポートの「フル解像度」)。
        非表示のデータセットも含めて _draw_data に渡すこと(ウォーターフォールの段の振り方のため。_draw_data 参照)。
        """
        self.fig.clf()
        self.all_axes.clear()
        self.all_secondary_axes.clear()
        self.axis_is_date_x.clear()
        self.axis_is_category_x.clear()
        # fig.clf() で古い artist はすべて消えるので、参照を捨てるだけでよい
        self._annotation_artists.clear()
        self._annotation_render_keys.clear()
        self._highlight_artists.clear()
        self.downsample_index_map.clear()
        self._non_pickable_dataset_ids.clear()
        self._axis_2d_mappables.clear()
        self._waterfall_transforms.clear()
        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)

        is_free_layout = layout_mode == 'free'
        subplot_count = len(all_plot_settings) if is_free_layout else rows * cols
        if subplot_count == 0:
            return False

        is_secondary_visible_global = False

        if is_free_layout:
            for i in range(subplot_count):
                rect = axis_setting(all_plot_settings[i], 'free_rect') or self._default_free_rect(i)
                ax = self.fig.add_axes(rect)
                self.all_axes.append(ax)
                self.all_secondary_axes.append(None)
        else:
            # 軸の共有は、行・列ごとではなく全部の軸を最初の軸に束ねる
            for i in range(subplot_count):
                share_x_target = self.all_axes[0] if (share_x_axis and self.all_axes) else None
                share_y_target = self.all_axes[0] if (share_y_axis and self.all_axes) else None
                ax = self.fig.add_subplot(rows, cols, i + 1, sharex=share_x_target, sharey=share_y_target)
                self.all_axes.append(ax)
                self.all_secondary_axes.append(None)

        for index, ax in enumerate(self.all_axes):
            if index < len(all_plot_settings):
                settings = all_plot_settings[index]
            else:
                continue

            self._draw_data(ax, index, datasets, full_resolution=full_resolution)
            self._apply_appearance(ax, index, settings)
            # _apply_appearance が目盛数値の表示を毎回設定し直すので、共有で隠すのはその後
            if not is_free_layout:
                self._apply_shared_axis_tick_visibility(index, rows, cols, share_x_axis, share_y_axis)
            self._draw_annotations(ax, index, settings, datasets=datasets, full_resolution=full_resolution)
            if panel_labels_enabled:
                self._draw_panel_label(ax, index)

            if self.all_secondary_axes[index] is not None:
                is_secondary_visible_global = True

        if not is_free_layout:
            # 自由配置は利用者が決めた位置を tight_layout が上書きするので、グリッドだけ。
            # matplotlib の予備フォント(LastResortHE)が欠けた環境では FileNotFoundError になるので、配置を諦めて続ける
            try:
                self.fig.tight_layout()
            except (ValueError, FileNotFoundError):
                pass

        self._safe_draw()
        return is_secondary_visible_global

    def update_appearance_only(self, all_plot_settings, datasets=(), rows=1, cols=1,
                                layout_mode='grid', share_x_axis=False, share_y_axis=False):
        """
        データはそのままで見た目の設定だけを当て直す。datasets は統計値ラベルの計算にだけ使う
        (省略すると統計値ラベルが「データセットなし」になるだけ)。
        """
        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)
        is_free_layout = layout_mode == 'free'
        for index, ax in enumerate(self.all_axes):
            if index < len(all_plot_settings):
                settings = all_plot_settings[index]
                self._apply_appearance(ax, index, settings)
                # redraw_all と同じく、共有で隠すのは _apply_appearance の後
                if not is_free_layout:
                    self._apply_shared_axis_tick_visibility(index, rows, cols, share_x_axis, share_y_axis)
                # この経路だけ軸を cla() しないので、内容が同じなら注釈を使い回せる
                self._draw_annotations(ax, index, settings, datasets=datasets,
                                       allow_reuse=True)
        try:
            self.fig.tight_layout()
        except (ValueError, FileNotFoundError):
            # フォントが欠けた環境の対策(redraw_all 参照)
            pass
        self._safe_draw()

    def _apply_shared_axis_tick_visibility(self, axis_index, rows, cols, share_x_axis, share_y_axis):
        """軸の共有が有効なら、内側の目盛数値(最下行以外の X・最左列以外の Y)を隠す。自由配置(cols=0)では何もしない。"""
        if cols <= 0:
            return
        row_idx, col_idx = divmod(axis_index, cols)
        ax = self.all_axes[axis_index]
        if share_x_axis and row_idx != rows - 1:
            ax.tick_params(labelbottom=False)
        if share_y_axis and col_idx != 0:
            ax.tick_params(labelleft=False)

    def _redraw_single_axis_no_draw(self, axis_index, datasets, settings, rows=1, cols=1,
                                     share_x_axis=False, share_y_axis=False, panel_labels_enabled=False,
                                     full_resolution=False):
        """update_single_axis() の、draw を呼ぶ手前まで(全軸をまとめて描き直すときに draw を1回で済ませるため)。"""
        if axis_index >= len(self.all_axes):
            return

        # twinx() の第2軸は cla() では消えないので、取り除かないと呼ぶたびに積み重なる
        old_secondary = self.all_secondary_axes[axis_index]
        if old_secondary is not None:
            old_secondary.remove()
            self.all_secondary_axes[axis_index] = None

        ax = self.all_axes[axis_index]
        ax.cla()

        # cla() で古い artist は消えているので、参照を捨てるだけ
        self._annotation_artists.pop(axis_index, None)
        self._annotation_render_keys.pop(axis_index, None)
        for dataset_id in [ds.dataset_id for ds in datasets if ds.subplot_target == axis_index]:
            self._highlight_artists.pop(dataset_id, None)
            self.downsample_index_map.pop(dataset_id, None)
            self._non_pickable_dataset_ids.discard(dataset_id)

        self._draw_data(ax, axis_index, datasets, full_resolution=full_resolution)
        self._apply_appearance(ax, axis_index, settings)
        self._draw_annotations(ax, axis_index, settings, datasets=datasets, full_resolution=full_resolution)
        if panel_labels_enabled:
            self._draw_panel_label(ax, axis_index)

        self._apply_shared_axis_tick_visibility(axis_index, rows, cols, share_x_axis, share_y_axis)

    def update_single_axis(self, axis_index, datasets, settings, rows=1, cols=1,
                            share_x_axis=False, share_y_axis=False, panel_labels_enabled=False,
                            full_resolution=False):
        """
        1つの軸だけを描き直す。Figure とほかの軸には触らない。データセットの見た目や描画先・第2Y軸の変更用
        (描画先の変更は旧・新の軸それぞれで呼ぶ)。軸の数や配置が変わるときは redraw_all() か
        add_free_axis()/remove_last_free_axis() を使う。
        """
        self._redraw_single_axis_no_draw(
            axis_index, datasets, settings, rows=rows, cols=cols,
            share_x_axis=share_x_axis, share_y_axis=share_y_axis,
            panel_labels_enabled=panel_labels_enabled, full_resolution=full_resolution,
        )
        self.draw_idle()

    def add_free_axis(self, datasets, settings, panel_labels_enabled=False):
        """自由配置の末尾に軸を1つ足す(ほかの軸には触らない)。足す軸はどのデータセットからも参照されていない。"""
        rect = axis_setting(settings, 'free_rect') or self._default_free_rect(len(self.all_axes))
        ax = self.fig.add_axes(rect)
        self.all_axes.append(ax)
        self.all_secondary_axes.append(None)
        self.axis_is_date_x.append(False)
        self.axis_is_category_x.append(False)

        axis_index = len(self.all_axes) - 1
        self._draw_data(ax, axis_index, datasets)
        self._apply_appearance(ax, axis_index, settings)
        self._draw_annotations(ax, axis_index, settings, datasets=datasets)
        if panel_labels_enabled:
            self._draw_panel_label(ax, axis_index)

        self.draw_idle()

    def remove_last_free_axis(self, datasets):
        """
        自由配置の末尾の軸を消す(ほかの軸には触らない)。消す軸のデータセットは、呼び出し側が先に
        新しい末尾の軸へ付け替え、描き直しも update_single_axis() で行うこと。
        """
        if not self.all_axes:
            return
        removed_index = len(self.all_axes) - 1

        secondary = self.all_secondary_axes[removed_index]
        if secondary is not None:
            secondary.remove()
        self.all_axes[removed_index].remove()

        self.all_axes.pop()
        self.all_secondary_axes.pop()
        if removed_index < len(self.axis_is_date_x):
            self.axis_is_date_x.pop()
        if removed_index < len(self.axis_is_category_x):
            self.axis_is_category_x.pop()

        self._annotation_artists.pop(removed_index, None)
        self._annotation_render_keys.pop(removed_index, None)
        for dataset_id in [ds.dataset_id for ds in datasets if ds.subplot_target == removed_index]:
            self._highlight_artists.pop(dataset_id, None)
            self.downsample_index_map.pop(dataset_id, None)
            self._non_pickable_dataset_ids.discard(dataset_id)

        self.draw_idle()

    def update_all_axes_appearance_and_data(self, datasets, rows, cols, all_plot_settings, layout_mode='grid',
                                             panel_labels_enabled=False, share_x_axis=False, share_y_axis=False,
                                             full_resolution=False):
        """
        軸の数と配置を変えずに、全部の軸のデータと見た目を描き直す(パネルラベルやダークモードの切り替え用)。
        fig.clf() しないので、軸の数や配置が変わるときには使えない。draw などの Figure 全体の処理は最後に1回だけ。
        """
        is_free_layout = layout_mode == 'free'
        is_secondary_visible_global = False

        for index in range(len(self.all_axes)):
            if index >= len(all_plot_settings):
                continue
            settings = all_plot_settings[index]
            self._redraw_single_axis_no_draw(
                index, datasets, settings, rows=rows, cols=cols,
                share_x_axis=share_x_axis, share_y_axis=share_y_axis,
                panel_labels_enabled=panel_labels_enabled, full_resolution=full_resolution,
            )
            if self.all_secondary_axes[index] is not None:
                is_secondary_visible_global = True

        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)
        if not is_free_layout:
            # 自由配置には tight_layout を掛けない・フォントが欠けた環境の対策(redraw_all 参照)
            try:
                self.fig.tight_layout()
            except (ValueError, FileNotFoundError):
                pass

        self._safe_draw()
        return is_secondary_visible_global

    def _draw_panel_label(self, ax, index):
        """軸の左上に (a)(b)(c)… を描く。文字は保存せず並び順から毎回決めるので、並べ替えても振り直される。"""
        label = self._panel_label_for_index(index)
        text_color = DARK_TEXT_COLOR if self.dark_mode else LIGHT_TEXT_COLOR
        ax.text(
            -0.12, 1.08, f"({label})", transform=ax.transAxes,
            fontsize=12, fontweight='bold', color=text_color,
            ha='left', va='top', zorder=10,
        )

    @staticmethod
    def _panel_label_for_index(index):
        """0->a, …, 25->z, 26->aa, 27->ab, …(Excel の列名と同じ)"""
        letters = []
        n = index
        while True:
            n, remainder = divmod(n, 26)
            letters.append(chr(ord('a') + remainder))
            if n == 0:
                break
            n -= 1
        return ''.join(reversed(letters))

    def _downsample_for_inset(self, x_data, y_data, full_resolution=False):
        """
        拡大図の点列を本体と同じく LTTB で間引く(注釈は描き直しのたびに作り直すので、大きなデータで重くなる)。
        拡大図は種類に関わらず線で描くので、散布図を除く本体の条件は当てはまらない。X が昇順のときだけ間引く。
        """
        if full_resolution or len(x_data) <= LTTB_DOWNSAMPLE_THRESHOLD:
            return x_data, y_data
        if not np.all(np.diff(x_data) >= 0):
            return x_data, y_data
        indices = calculate_lttb_downsample(x_data, y_data, LTTB_DOWNSAMPLE_TARGET_POINTS)
        return x_data[indices], y_data[indices]

    def _annotation_render_key(self, axis_index, settings, datasets, full_resolution):
        """
        注釈の描き直しを省くかどうかのキー。描いた結果に影響するものを全部入れる:
        ダークモード(色が変わる)、統計値ラベルの計算後の文字列、拡大図が描くデータセットの色・線幅・透明度・表示。
        拡大図のデータそのものは入れない。これを使う update_appearance_only はデータが変わっていない前提の経路
        (データが変わる操作は cla() する別の経路を通り、そこでは使い回さない)。
        """
        annotations = axis_setting(settings, 'annotations')
        parts = [bool(self.dark_mode), bool(full_resolution), len(annotations)]
        if not annotations:
            return json.dumps(parts, default=str)

        datasets_by_id = {ds.dataset_id: ds for ds in (datasets or ())}
        for ann in annotations:
            parts.append(json.dumps(ann, sort_keys=True, default=str))
            ann_type = ann.get('type')
            if ann_type == 'stat':
                dataset = datasets_by_id.get(ann.get('dataset_id'))
                parts.append(_compute_stat_label_text(dataset, ann.get('stat')))
            elif ann_type == 'inset':
                for target_ds in (datasets or ()):
                    if target_ds.subplot_target != axis_index or not target_ds.visible:
                        continue
                    parts.append((target_ds.dataset_id, target_ds.color,
                                  target_ds.linewidth, target_ds.alpha))
        return json.dumps(parts, default=str)

    def _draw_annotations(self, ax, axis_index, settings, datasets=None, full_resolution=False,
                          allow_reuse=False):
        """
        軸の注釈(テキスト・矢印・領域ハイライト・統計値ラベル・拡大図)を、前回の分を消してから描く。

        allow_reuse=True なら、内容が前回と同じとき描き直しを省く(拡大図はデータを描き直すので重い)。
        使ってよいのは update_appearance_only() だけ。ほかの経路は前回の artist が既に消えている
        (fig.clf() / ax.cla() / 新しい軸)ので、使い回すと注釈が消える。既定は False。
        datasets は統計値ラベルと拡大図が使う(省略すると「データセットなし」)。
        """
        render_key = self._annotation_render_key(axis_index, settings, datasets, full_resolution)
        if allow_reuse and self._annotation_render_keys.get(axis_index, _NO_KEY) == render_key:
            return

        for artist in self._annotation_artists.get(axis_index, []):
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass

        datasets_by_id = {ds.dataset_id: ds for ds in (datasets or ())}

        new_artists = []
        for ann in axis_setting(settings, 'annotations'):
            ann_type = ann.get('type')
            text = ann.get('text', '')
            try:
                if ann_type == 'arrow':
                    color = self._effective_text_color(ann.get('color', '#000000'))
                    arrowstyle = _ARROW_STYLE_MAP.get(ann.get('arrow_style', 'single'), '->')
                    curvature = ann.get('arrow_curvature', 0.0)
                    arrow_props = dict(arrowstyle=arrowstyle, color=color)
                    if curvature:
                        arrow_props['connectionstyle'] = f'arc3,rad={curvature}'
                    artist = ax.annotate(
                        text, xy=ann['xy'], xytext=ann['xytext'],
                        arrowprops=arrow_props,
                        color=color, fontsize=9
                    )
                elif ann_type in ('vspan', 'hspan'):
                    # 利用者が選んだ色をそのまま使う(ダークモードの読み替えはしない)
                    lo, hi = ann.get('range', (0, 0))
                    color = ann.get('color', REGION_HIGHLIGHT_DEFAULT_COLOR)
                    alpha = ann.get('alpha', REGION_HIGHLIGHT_DEFAULT_ALPHA)
                    if ann_type == 'vspan':
                        artist = ax.axvspan(lo, hi, color=color, alpha=alpha, zorder=0.5)
                    else:
                        artist = ax.axhspan(lo, hi, color=color, alpha=alpha, zorder=0.5)
                elif ann_type == 'inset':
                    # 拡大図は、種類やグラデーションは再現せず、範囲内の点を線で結ぶだけの概観
                    x0, y0 = _INSET_CORNER_ORIGINS.get(ann.get('corner', '右上'), (0.55, 0.55))
                    size = ann.get('size', 0.4)
                    x_min, x_max = ann.get('zoom_x_range', (0, 1))
                    color = self._effective_text_color(ann.get('color', '#000000'))
                    inset_ax = ax.inset_axes((x0, y0, size, size))
                    for target_ds in (datasets or ()):
                        if target_ds.subplot_target != axis_index or not target_ds.visible:
                            continue
                        tx = np.asarray(target_ds.x_data, dtype=float)
                        ty = np.asarray(target_ds.y_data, dtype=float)
                        in_range = (tx >= x_min) & (tx <= x_max)
                        if in_range.any():
                            inset_x, inset_y = self._downsample_for_inset(
                                tx[in_range], ty[in_range], full_resolution=full_resolution
                            )
                            inset_ax.plot(inset_x, inset_y, color=target_ds.color,
                                          linewidth=target_ds.linewidth, alpha=target_ds.alpha)
                    inset_ax.set_xlim(x_min, x_max)
                    inset_ax.tick_params(labelsize=7)
                    pp, p1, p2 = mark_inset(ax, inset_ax, loc1=ann.get('loc1', 2), loc2=ann.get('loc2', 4),
                                            fc="none", ec=color)
                    new_artists.extend([inset_ax, pp, p1, p2])
                    artist = None
                elif ann_type == 'stat':
                    # 軸に対する位置なので、拡大・移動しても同じ場所に留まる
                    color = self._effective_text_color(ann.get('color', '#000000'))
                    xy = ann.get('xy', (0.05, 0.95))
                    dataset = datasets_by_id.get(ann.get('dataset_id'))
                    label_text = _compute_stat_label_text(dataset, ann.get('stat'))
                    artist = ax.text(
                        xy[0], xy[1], label_text, transform=ax.transAxes,
                        color=color, fontsize=9, va='top', ha='left', zorder=10,
                    )
                else:
                    color = self._effective_text_color(ann.get('color', '#000000'))
                    xy = ann.get('xy', (0, 0))
                    artist = ax.text(xy[0], xy[1], text, color=color, fontsize=9)
                if artist is not None:
                    new_artists.append(artist)
            except Exception:
                logger.exception("注釈の描画に失敗しました: %s", ann)
        self._annotation_artists[axis_index] = new_artists
        # 使い回さない経路でもキーは更新する(直後の update_appearance_only が無駄に描き直さないように)
        self._annotation_render_keys[axis_index] = render_key

    def _enable_element_picking(self, artist):
        """クリックで選べるようにする。棒グラフは Rectangle の集まりなので、1本ずつ設定する。"""
        try:
            if hasattr(artist, 'patches'):  # BarContainer
                for patch in artist.patches:
                    patch.set_picker(5)
            else:
                artist.set_picker(5)
        except AttributeError:
            pass

    def _add_gradient_line(self, ax, x, y, color1, color2, linewidth, alpha, linestyle, label=None):
        """
        線を区間に分けて、始点の色から終点の色へ変わる LineCollection として描く。
        add_collection は軸の表示範囲を広げないことがあるので、データ範囲を明示的に足しておく。
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        if len(x) < 2:
            # 区間が作れないので普通の線にする
            (line,) = ax.plot(x, y, color=color1, linestyle=linestyle, linewidth=linewidth, alpha=alpha, label=label)
            return line

        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)

        cmap = LinearSegmentedColormap.from_list('graphica_line_gradient', [color1, color2])
        lc = LineCollection(
            segments, cmap=cmap, norm=Normalize(0, 1),
            linewidths=linewidth, linestyles=linestyle, alpha=alpha, label=label,
            zorder=2,
        )
        # 区間ごとに始点からの位置(0〜1)を割り当てる
        lc.set_array(np.linspace(0, 1, len(segments)))
        ax.add_collection(lc)
        ax.update_datalim(np.column_stack([x, y]))
        return lc

    def _add_gradient_fill(self, ax, x, y, color1, color2, alpha, baseline=0.0):
        """fill_between と同じ形の多角形で、imshow のグラデーション画像を切り抜いて塗る。"""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        # origin='lower' で先頭行が下端になるので、上端が color1 になるよう色を逆に並べる
        gradient = np.linspace(0, 1, 256).reshape(-1, 1)
        cmap = LinearSegmentedColormap.from_list('graphica_fill_gradient', [color2, color1])

        x_min, x_max = float(np.nanmin(x)), float(np.nanmax(x))
        y_min = float(min(np.nanmin(y), baseline))
        y_max = float(max(np.nanmax(y), baseline))
        # 全点が同じ座標だと extent が潰れるので幅を持たせる
        if x_min == x_max:
            x_min, x_max = x_min - 0.5, x_max + 0.5
        if y_min == y_max:
            y_min, y_max = y_min - 0.5, y_max + 0.5

        im = ax.imshow(
            gradient, cmap=cmap, aspect='auto', origin='lower',
            extent=(x_min, x_max, y_min, y_max), alpha=alpha, zorder=1,
        )

        verts = list(zip(x, y)) + [(x[-1], baseline), (x[0], baseline)]
        clip_poly = Polygon(verts, closed=True, transform=ax.transData)
        im.set_clip_path(clip_poly)

        # imshow は軸の範囲を広げないので、明示的に足す
        ax.update_datalim(np.array([[x_min, y_min], [x_max, y_max]]))
        return im

    _VALID_MAP_DISPLAY_MODES = ('heatmap', 'contour', 'contour_filled', 'heatmap_contour')

    def _draw_2d_data(self, ax, axis_index, datasets_2d, full_resolution=False):
        """
        2Dマップを描く。規則格子でも補間した格子でも同じ形の z_grid なので、等間隔を前提にする imshow ではなく
        pcolormesh を使う。map_display_mode: 'heatmap' / 'contour'(線だけ、色と太さはデータセットの線) /
        'contour_filled' / 'heatmap_contour'。カラーバーの対象は塗りのある方式だけ(線だけの等高線には付けない慣習)。
        """
        self._axis_2d_mappables.pop(axis_index, None)
        for ds in datasets_2d:
            grid = ds.z_grid
            if grid is None:
                continue
            x_grid, y_grid, z_grid = grid['x_grid'], grid['y_grid'], grid['z_grid']

            if not full_resolution and len(x_grid) > GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS:
                step = int(np.ceil(len(x_grid) / GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS))
                x_grid = x_grid[::step]
                z_grid = z_grid[:, ::step]
            if not full_resolution and len(y_grid) > GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS:
                step = int(np.ceil(len(y_grid) / GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS))
                y_grid = y_grid[::step]
                z_grid = z_grid[::step, :]

            vmin = ds.vmin if ds.vmin is not None else (
                float(np.nanmin(z_grid)) if np.any(~np.isnan(z_grid)) else None
            )
            vmax = ds.vmax if ds.vmax is not None else (
                float(np.nanmax(z_grid)) if np.any(~np.isnan(z_grid)) else None
            )

            mode = ds.map_display_mode if ds.map_display_mode in self._VALID_MAP_DISPLAY_MODES else 'heatmap'

            try:
                mappable = None
                contour_set = None
                # label は付けない。QuadMesh/ContourSet は凡例に載らず、凡例を作るたびに警告が出る
                if mode in ('heatmap', 'heatmap_contour'):
                    mappable = ax.pcolormesh(
                        x_grid, y_grid, z_grid, cmap=ds.colormap, vmin=vmin, vmax=vmax,
                        shading='auto', alpha=ds.alpha,
                    )
                elif mode == 'contour_filled':
                    mappable = ax.contourf(
                        x_grid, y_grid, z_grid, levels=ds.contour_levels, cmap=ds.colormap,
                        vmin=vmin, vmax=vmax, alpha=ds.alpha,
                    )
                if mode in ('contour', 'heatmap_contour'):
                    contour_set = ax.contour(
                        x_grid, y_grid, z_grid, levels=ds.contour_levels, colors=ds.color,
                        alpha=ds.alpha, linewidths=ds.linewidth,
                    )
            except ValueError as e:
                # 知らないカラーマップ名など。このデータセットだけ飛ばす
                logger.warning("2Dマップの描画に失敗しました(%s): %s", ds.name, e)
                continue

            ds.artist = mappable if mappable is not None else contour_set
            if mappable is not None:
                self._axis_2d_mappables[axis_index] = mappable

    def _draw_data(self, ax, axis_index, datasets, full_resolution=False):
        """
        その軸のデータセットを描く。full_resolution=True なら表示用の間引きをしない(エクスポートの「フル解像度」)。

        呼び出し側は非表示のデータセットも含めた全件を渡す。ウォーターフォールの段は非表示のものも数に入れて
        振る(1本隠しても後ろの段が繰り上がらないように)ので、ここで絞る。
        """
        on_this_axis = [ds for ds in datasets if ds.subplot_target == axis_index]
        # 2Dマップは長形式の生の列を持つので、1D の経路(軸の種類の判定・ウォーターフォール・間引きなど)を通さない
        datasets_2d = [ds for ds in on_this_axis if ds.data_kind == '2d_grid' and getattr(ds, 'visible', True)]
        datasets_1d_all = [ds for ds in on_this_axis if ds.data_kind != '2d_grid']
        shown_1d = [ds for ds in datasets_1d_all if getattr(ds, 'visible', True)]
        # 背景として先に描き、1D のデータが上に重なるようにする
        self._draw_2d_data(ax, axis_index, datasets_2d, full_resolution=full_resolution)

        # ウォーターフォールの変換は描くたびに登録し直す
        for ds in on_this_axis:
            self._waterfall_transforms.pop(ds.dataset_id, None)

        needs_secondary = any(ds.use_secondary_y for ds in shown_1d)
        is_category_x = self._record_x_axis_kind(axis_index, shown_1d)

        secondary_ax = None
        if needs_secondary:
            secondary_ax = ax.twinx()
            self.all_secondary_axes[axis_index] = secondary_ax

        waterfall = _waterfall_layout(datasets_1d_all)
        for ds in shown_1d:
            target_ax = secondary_ax if ds.use_secondary_y else ax
            if target_ax is None:
                continue
            self._draw_1d_dataset(target_ax, axis_index, ds, waterfall, is_category_x, full_resolution)

    def _record_x_axis_kind(self, axis_index, datasets):
        """X 軸が日時か文字列カテゴリかを記録する(目盛りの付け方に使う)。カテゴリなら True を返す。"""
        is_date_x = any(pd.api.types.is_datetime64_any_dtype(ds.df[ds.x_col_name]) for ds in datasets)
        while len(self.axis_is_date_x) <= axis_index:
            self.axis_is_date_x.append(False)
        self.axis_is_date_x[axis_index] = is_date_x

        is_category_x = (not is_date_x) and any(
            not pd.api.types.is_numeric_dtype(ds.df[ds.x_col_name]) for ds in datasets
        )
        while len(self.axis_is_category_x) <= axis_index:
            self.axis_is_category_x.append(False)
        self.axis_is_category_x[axis_index] = is_category_x
        return is_category_x

    def _draw_1d_dataset(self, target_ax, axis_index, ds, waterfall, is_category_x, full_resolution):
        plot_x_data, plot_y_data, plot_kwargs, occlusion_zorder = self._waterfall_shifted_points(
            ds, waterfall, is_category_x)

        # カテゴリ軸は下で文字列にするので対象外。
        # 'drop' は配列を短くするため、大量データで間引きと併用するとデータカーソルの行の対応がずれうる(既知の制約)。
        if not is_category_x and ds.nan_policy != 'gap':
            plot_x_data, plot_y_data = _apply_nan_policy(plot_x_data, plot_y_data, ds.nan_policy)

        if is_category_x:
            # matplotlib のカテゴリ軸は全要素が文字列でないと例外になる(数値や NaN が混ざった列)
            plot_x_data = np.array([v if isinstance(v, str) else str(v) for v in plot_x_data])

        plot_x_data, plot_y_data, downsample_indices = self._downsample_for_display(
            ds, plot_x_data, plot_y_data, is_category_x, full_resolution)

        # 平滑化は線で結ぶ種別だけ(ほかの種別では平滑化した線がマーカー・棒・塗りを置き換えてしまう)
        is_smoothed_artist = False
        if (ds.smoothing and ds.plot_type in ('Line', 'Line+Scatter')
                and len(plot_x_data) > 1 and not is_category_x):
            is_smoothed_artist = self._draw_smoothed(target_ax, ds, plot_x_data, plot_y_data, plot_kwargs)
        else:
            ds.artist = self._draw_plot_type(target_ax, axis_index, ds, plot_x_data, plot_y_data, plot_kwargs)

        # 手前のトレースが奥を隠すよう、トレースの下に軸の背景色を敷く。面は自分の塗りと重なるので除く
        if (ds.waterfall_enabled and ds.waterfall_occlusion_enabled
                and ds.plot_type != 'Area' and len(plot_x_data) > 0):
            bg_color = DARK_AXES_FACECOLOR if self.dark_mode else LIGHT_AXES_FACECOLOR
            target_ax.fill_between(
                plot_x_data, plot_y_data, waterfall.baseline,
                color=bg_color, alpha=1.0, zorder=occlusion_zorder, linewidth=0,
            )

        # 平滑化した曲線の点は元の行と対応しないので、クリックで選べないようにする。
        # データカーソルモードの一括 set_picker からも外すため、_non_pickable_dataset_ids にも入れる
        if is_smoothed_artist:
            self._non_pickable_dataset_ids.add(ds.dataset_id)
        else:
            self._non_pickable_dataset_ids.discard(ds.dataset_id)
        if ds.artist is not None and not is_smoothed_artist:
            self._enable_element_picking(ds.artist)

        self._draw_error_display(target_ax, ds, plot_x_data, plot_y_data, downsample_indices)

        # 曲線フィットの信頼帯・予測帯。帯の列があるときだけ描ける
        if ds.fit_band_display and 'y_lower' in ds.df.columns and 'y_upper' in ds.df.columns:
            band_df = ds.visible_df
            target_ax.fill_between(
                band_df[ds.x_col_name], band_df['y_lower'], band_df['y_upper'],
                color=ds.color, alpha=ds.alpha * 0.15, linewidth=0,
            )

        # 点数が上限を超えると描画で GUI が止まるので描かない。
        # ラベルの値は間引く前の並びなので、点と同じ downsample_indices で揃える
        if ds.show_point_labels and len(ds.visible_df) <= self.point_label_max_points:
            self._draw_point_labels(
                target_ax, ds, x_data=plot_x_data, y_data=plot_y_data,
                downsample_indices=downsample_indices,
            )

    def _waterfall_shifted_points(self, ds, waterfall, is_category_x):
        """
        描く点列 (x, y, plot_kwargs, 背景を敷く zorder)。ウォーターフォールなら段の分だけずらし、
        逆変換(display_to_data)用に変換を記録する。カテゴリ軸では X はずらせないので Y だけずらす。
        """
        if not ds.waterfall_enabled:
            return ds.x_data, ds.y_data, {}, None
        w_idx = waterfall.index.get(ds.dataset_id, 0)
        depth_scale = _waterfall_depth_scale(
            w_idx, ds.waterfall_depth_shrink_enabled, ds.waterfall_depth_shrink_ratio)
        self._waterfall_transforms[ds.dataset_id] = {
            'index': w_idx,
            'offset_x': 0.0 if is_category_x else ds.waterfall_offset_x,
            'offset_y': ds.waterfall_offset_y,
            'depth_scale': depth_scale,
        }
        plot_x_data = ds.x_data if is_category_x else ds.x_data + w_idx * ds.waterfall_offset_x
        plot_y_data = ds.y_data * depth_scale + w_idx * ds.waterfall_offset_y
        # 手前(段が小さい)ほど上に重ねる。段の数によらず枠線・目盛(zorder 2.01〜2.5)より下に収める
        step = (WATERFALL_ZORDER_TOP - WATERFALL_ZORDER_BASE) / (waterfall.count + 1)
        zorder = WATERFALL_ZORDER_BASE + (waterfall.count - w_idx) * step
        return plot_x_data, plot_y_data, {'zorder': zorder}, zorder - step / 2

    def _downsample_for_display(self, ds, plot_x_data, plot_y_data, is_category_x, full_resolution):
        """
        点が多い 'Line' だけ LTTB で間引く(散布図などは点の疎密自体が情報)。X が昇順でないと
        LTTB が形を変えてしまうので、そのときは間引かない。戻り値の3つ目は間引きに使った添字(無ければ None)。
        """
        if not (ds.plot_type == 'Line' and not full_resolution and not is_category_x
                and len(plot_x_data) > LTTB_DOWNSAMPLE_THRESHOLD
                and np.all(np.diff(plot_x_data) >= 0)):
            return plot_x_data, plot_y_data, None
        indices = calculate_lttb_downsample(plot_x_data, plot_y_data, LTTB_DOWNSAMPLE_TARGET_POINTS)
        if len(indices) >= len(plot_x_data):
            return plot_x_data, plot_y_data, None
        # データカーソルが、間引いた後の添字を visible_df の行に戻すのに使う
        self.downsample_index_map[ds.dataset_id] = indices
        return plot_x_data[indices], plot_y_data[indices], indices

    def _draw_smoothed(self, target_ax, ds, plot_x_data, plot_y_data, plot_kwargs):
        """平滑化した曲線を描く。平滑化できなければ元の点のまま線で結び、False を返す。"""
        sort_indices = np.argsort(plot_x_data)
        x_sorted = plot_x_data[sort_indices]
        y_sorted = plot_y_data[sort_indices]
        use_line_gradient = ds.gradient_enabled and ds.gradient_target in ('line', 'both')
        smoothing_method = getattr(ds, 'smoothing_method', 'cubic_spline')
        try:
            # cubic_spline は200点に補間して滑らかにする。ほかはノイズを減らすのが目的なので点数はそのまま
            if smoothing_method == 'moving_average':
                x_smooth, y_smooth = calculate_moving_average_smooth(x_sorted, y_sorted)
            elif smoothing_method == 'median':
                x_smooth, y_smooth = calculate_median_smooth(x_sorted, y_sorted)
            elif smoothing_method == 'gaussian':
                x_smooth, y_smooth = calculate_gaussian_smooth(x_sorted, y_sorted)
            else:
                f = CubicSpline(x_sorted, y_sorted)
                x_smooth = np.linspace(x_sorted.min(), x_sorted.max(), 200)
                y_smooth = f(x_smooth)
            if use_line_gradient:
                ds.artist = self._add_gradient_line(
                    target_ax, x_smooth, y_smooth, ds.color, ds.gradient_color2,
                    ds.linewidth, ds.alpha, ds.linestyle, label=ds.name
                )
            else:
                (artist_line,) = target_ax.plot(x_smooth, y_smooth, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                ds.artist = artist_line
            if ds.plot_type == 'Line+Scatter':
                target_ax.scatter(plot_x_data, plot_y_data, color=ds.color, marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha, **plot_kwargs)
            return True
        except ValueError:
            if use_line_gradient:
                ds.artist = self._add_gradient_line(
                    target_ax, plot_x_data, plot_y_data, ds.color, ds.gradient_color2,
                    ds.linewidth, ds.alpha, ds.linestyle, label=ds.name
                )
            else:
                (artist,) = target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                ds.artist = artist
            return False

    def _draw_plot_type(self, target_ax, axis_index, ds, plot_x_data, plot_y_data, plot_kwargs):
        """
        plot_type の描画関数で描き、ds.artist にするものを返す。組み込みに無ければプラグインの種類を探し、
        それも無ければ線で描く。プラグインの描画にはウォーターフォールの zorder などは渡らない(既知の制限)。
        """
        drawer = BUILTIN_PLOT_TYPE_DRAWERS.get(ds.plot_type)
        if drawer is not None:
            return drawer(self, target_ax, ds, plot_x_data, plot_y_data, plot_kwargs, axis_index)

        from graphica.core.plugin_api import get_plugin_api
        api = get_plugin_api()
        plugin_plot_type = api.get_plot_type(ds.plot_type) if api is not None else None
        if plugin_plot_type is None:
            logger.warning("未知のplot_type '%s' です。Lineとして描画します。", ds.plot_type)
            (artist,) = target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
            return artist
        try:
            artist = plugin_plot_type.drawer(ds, target_ax, plot_x_data, plot_y_data)
        except Exception as e:
            logger.warning(
                "[plugin:%s] plot_type '%s' の描画に失敗しました: %s",
                plugin_plot_type.plugin_name, ds.plot_type, e,
            )
            return ds.artist
        return artist if artist is not None else ds.artist

    def _draw_error_display(self, target_ax, ds, plot_x_data, plot_y_data, downsample_indices):
        """誤差棒と誤差の帯を、描いた点(ずらし・間引きの後)の位置に重ねる。帯は Y の誤差だけ。"""
        if not (ds.x_err_col_name or ds.y_err_col_name):
            return
        # 誤差列は間引く前の長さなので、点と同じ添字で揃える(揃えないと長さ違いで例外)
        x_err = ds.x_err_data
        y_err_full = ds.y_err_data
        if downsample_indices is not None:
            if x_err is not None:
                x_err = x_err[downsample_indices]
            if y_err_full is not None:
                y_err_full = y_err_full[downsample_indices]

        if ds.error_display in ('bar', 'both'):
            target_ax.errorbar(
                plot_x_data, plot_y_data,
                xerr=x_err, yerr=y_err_full,
                fmt='none', ecolor=ds.color, elinewidth=ds.linewidth, alpha=ds.alpha, capsize=3
            )
        if ds.error_display in ('band', 'both') and y_err_full is not None:
            y_arr = np.asarray(plot_y_data)
            y_err = np.asarray(y_err_full)
            target_ax.fill_between(
                plot_x_data, y_arr - y_err, y_arr + y_err,
                color=ds.color, alpha=ds.alpha * 0.25, linewidth=0,
            )

    def set_highlighted_points(self, dataset, master_indices):
        """
        データエディタで選んだ行の点をグラフ上で丸く囲む。

        Args:
            dataset (Dataset): 対象のデータセット。
            master_indices (list): dataset.df.index のラベル。空ならこのデータセットのハイライトを消す。
        """
        old_artist = self._highlight_artists.pop(dataset.dataset_id, None)
        if old_artist is not None:
            try:
                old_artist.remove()
            except (ValueError, NotImplementedError):
                pass

        if not master_indices:
            self.draw_idle()
            return

        axis_index = dataset.subplot_target
        if axis_index >= len(self.all_axes):
            self.draw_idle()
            return

        if dataset.use_secondary_y and axis_index < len(self.all_secondary_axes) \
                and self.all_secondary_axes[axis_index] is not None:
            ax = self.all_secondary_axes[axis_index]
        else:
            ax = self.all_axes[axis_index]

        try:
            # x_data/y_data は visible_df の並びなので、位置も visible_df.index で引く(除外した行は描かれていない)
            visible_index = dataset.visible_df.index
            positions = [visible_index.get_loc(idx) for idx in master_indices if idx in visible_index]
        except Exception:
            logger.exception("ハイライト対象の行インデックス変換に失敗しました。")
            positions = []

        if not positions:
            self.draw_idle()
            return

        x_vals = dataset.x_data[positions]
        y_vals = dataset.y_data[positions]
        # ウォーターフォールでずらした位置に合わせる
        x_vals, y_vals = self.data_to_display(dataset, x_vals, y_vals)
        artist = ax.scatter(
            x_vals, y_vals, s=160, facecolors='none', edgecolors='#e6194b',
            linewidths=2.0, zorder=15
        )
        self._highlight_artists[dataset.dataset_id] = artist
        self.draw_idle()

    def _draw_point_labels(self, ax, ds, x_data=None, y_data=None, downsample_indices=None):
        """
        各点の脇に Y 値(point_label_col_name があればその列の値)を書く。
        x_data/y_data を渡せばその位置に書く(ウォーターフォールでずらした位置)。
        downsample_indices は点の間引きに使った添字で、ラベルの値も同じく間引く
        (揃えないと zip が短い方で切れ、点と無関係な行のラベルが付く)。
        """
        if x_data is None:
            x_data = ds.x_data
        if y_data is None:
            y_data = ds.y_data

        if ds.point_label_col_name and ds.point_label_col_name in ds.df.columns:
            # 点と同じ行になるよう visible_df から取る
            label_values = ds.visible_df[ds.point_label_col_name].values
        else:
            label_values = ds.y_data
        if downsample_indices is not None:
            label_values = label_values[downsample_indices]

        for x, y, label_value in zip(x_data, y_data, label_values):
            if pd.isna(x) or pd.isna(y):
                continue
            if isinstance(label_value, (int, float, np.floating, np.integer)) and not isinstance(label_value, bool):
                text = f"{label_value:.4g}" if not pd.isna(label_value) else ""
            else:
                text = "" if pd.isna(label_value) else str(label_value)
            if not text:
                continue
            ax.annotate(
                text, (x, y), textcoords="offset points", xytext=(5, 5),
                fontsize=8, color=ds.color, alpha=ds.alpha,
                # Text の既定は clip_on=False で、範囲外の点のラベルだけが枠の外に残り SVG/PDF に出てしまう
                clip_on=True,
            )

    def _apply_appearance(self, ax, axis_index, settings):
        """その軸に見た目の設定を当てる。matplotlib の状態に依存するので、下の順番は変えない。"""
        secondary_ax = self.all_secondary_axes[axis_index]
        ax.set_facecolor(DARK_AXES_FACECOLOR if self.dark_mode else LIGHT_AXES_FACECOLOR)

        is_date_x = axis_index < len(self.axis_is_date_x) and self.axis_is_date_x[axis_index]
        # 文字列カテゴリ軸では、範囲・対数などの数値向けの設定はカテゴリの位置と噛み合わないので使わない
        is_category_x = axis_index < len(self.axis_is_category_x) and self.axis_is_category_x[axis_index]

        self._apply_limits_and_scale(ax, settings, is_category_x)
        self._apply_tick_locators(ax, settings, is_date_x, is_category_x)
        style = self._axis_text_and_line_style(settings)
        self._apply_titles_and_labels(ax, settings, style)
        self._apply_spines_and_tick_marks(ax, settings, style)
        self._apply_legend(ax, secondary_ax, settings)
        self._apply_grid(ax, settings)
        self._apply_secondary_y_axis(ax, secondary_ax, settings, style)
        self._apply_unit_conversion_x_axis(ax, settings, style, is_date_x, is_category_x)
        self._apply_colorbar(ax, axis_index, settings, style)

    def _apply_limits_and_scale(self, ax, settings, is_category_x):
        if is_category_x or axis_setting(settings, 'x_autoscale'): ax.autoscale(enable=True, axis='x', tight=True)
        else:
            min_val, max_val = axis_setting(settings, 'x_min'), axis_setting(settings, 'x_max')
            if min_val < max_val: ax.set_xlim(min_val, max_val)

        if axis_setting(settings, 'y_autoscale'): ax.autoscale(enable=True, axis='y', tight=True)
        else:
            min_val, max_val = axis_setting(settings, 'y_min'), axis_setting(settings, 'y_max')
            if min_val < max_val: ax.set_ylim(min_val, max_val)

        if not is_category_x:
            # set_xscale は同じ 'linear' でも Locator/Formatter を既定に戻してしまう。
            # カテゴリ軸では matplotlib が付けたカテゴリ用のものを残したいので呼ばない
            ax.set_xscale('log' if axis_setting(settings, 'x_log') else 'linear')
        ax.xaxis.set_inverted(axis_setting(settings, 'x_invert'))
        ax.set_yscale('log' if axis_setting(settings, 'y_log') else 'linear')
        ax.yaxis.set_inverted(axis_setting(settings, 'y_invert'))

    def _apply_tick_locators(self, ax, settings, is_date_x, is_category_x):
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

    def _axis_text_and_line_style(self, settings):
        """文字と線の見た目のうち、軸・第2軸・カラーバーで共通に使うもの(ダークモードの色の読み替え後)。"""
        major_tick_length, minor_tick_length = _resolve_tick_lengths(settings)
        return _AxisStyle(
            tick_font=axis_setting(settings, 'tick_font'),
            label_font=axis_setting(settings, 'axis_label_font'),
            tick_color=self._effective_text_color(axis_setting(settings, 'tick_color')),
            label_color=self._effective_text_color(axis_setting(settings, 'axis_label_color')),
            spine_width=axis_setting(settings, 'spine_width'),
            spine_color=self._effective_text_color(axis_setting(settings, 'spine_color')),
            tick_width=axis_setting(settings, 'tick_width'),
            major_tick_length=major_tick_length,
            minor_tick_length=minor_tick_length,
        )

    def _apply_titles_and_labels(self, ax, settings, style):
        ax.set_title(axis_setting(settings, 'title'), **style.label_font, color=style.label_color)
        # 非表示にしても文字列は消さない(表示に戻したときに打ち直さなくて済むように)
        x_label_text = axis_setting(settings, 'x_label') if axis_setting(settings, 'x_label_visible') else ''
        y_label_text = axis_setting(settings, 'y_label') if axis_setting(settings, 'y_label_visible') else ''
        ax.set_xlabel(x_label_text, **style.label_font, color=style.label_color)
        ax.set_ylabel(y_label_text, **style.label_font, color=style.label_color)
        # タイトルのクリックで、その軸を編集対象にする
        ax.title.set_picker(5)

        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set(**style.tick_font)
            label.set_color(style.tick_color)

    def _apply_spines_and_tick_marks(self, ax, settings, style):
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

    def _apply_legend(self, ax, secondary_ax, settings):
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
        legend_color = self._effective_text_color(axis_setting(settings, 'legend_color'))
        legend_font_prop = FontProperties(
            family=legend_font_dict.get('family'),
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
            if self.dark_mode:
                frame.set_facecolor(DARK_LEGEND_FACECOLOR)
                frame.set_edgecolor(DARK_LEGEND_EDGECOLOR)
            else:
                frame.set_facecolor(LIGHT_LEGEND_FACECOLOR)
                frame.set_edgecolor(LIGHT_LEGEND_EDGECOLOR)
            frame.set_alpha(0.92)
            # 離した位置が legend._loc に入り、PlotterApp がそれを設定へ保存する
            # (matplotlib 3.x に Legend.draggable() は無い)
            legend_obj.set_draggable(True, update='loc')

    def _apply_grid(self, ax, settings):
        """ax.grid() は指定した which/axis にしか効かないので、X/Y × 主/補助 を個別に呼ぶ。"""
        if not axis_setting(settings, 'grid_visible'):
            ax.grid(False, which='both')
            return
        grid_color = DARK_GRID_COLOR if self.dark_mode else LIGHT_GRID_COLOR
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

    def _apply_secondary_y_axis(self, ax, secondary_ax, settings, style):
        """第2Y軸があれば右の枠線と目盛りを第2Y軸に任せ、無ければ主軸の右の枠線を出す。"""
        if not secondary_ax:
            ax.spines['right'].set_visible(True)
            ax.spines['right'].set_linewidth(style.spine_width)
            ax.spines['right'].set_color(style.spine_color)
            return
        secondary_ax.autoscale(enable=True, axis='y', tight=True)
        secondary_ax.set_ylabel(axis_setting(settings, 'y2_label'), **style.label_font, color=style.label_color)
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

    def _apply_unit_conversion_x_axis(self, ax, settings, style, is_date_x, is_category_x):
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

    def _apply_colorbar(self, ax, axis_index, settings, style):
        """
        2Dマップ(または値で色分けした散布図)がこの軸にあればカラーバーを付ける。
        location を渡すと向きは matplotlib が決めるので、orientation は渡さない(衝突しうる)。
        """
        mappable = self._axis_2d_mappables.get(axis_index)
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
        cbar = self.fig.colorbar(mappable, ax=ax, location=position, fraction=fraction, pad=0.04)
        colorbar_label = axis_setting(settings, 'colorbar_label')
        if colorbar_label:
            cbar.set_label(colorbar_label, **style.label_font, color=style.label_color)
        for tick_label in cbar.ax.get_yticklabels() + cbar.ax.get_xticklabels():
            tick_label.set(**style.tick_font)
            tick_label.set_color(style.tick_color)
        cbar.outline.set_edgecolor(style.spine_color)
        cbar.outline.set_linewidth(style.spine_width)


class MplCanvas(FigureCanvas, _CanvasDrawingMixin):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self._init_drawing_state(width, height, dpi)
        super().__init__(self.fig)
        self.setParent(parent)


class _HeadlessRenderCanvas(FigureCanvasAgg, _CanvasDrawingMixin):
    """一括エクスポート用の Qt に依存しないキャンバス。QWidget ではないので GUI スレッドの外で描いてよい。"""
    def __init__(self, width=5, height=4, dpi=100):
        self._init_drawing_state(width, height, dpi)
        super().__init__(self.fig)