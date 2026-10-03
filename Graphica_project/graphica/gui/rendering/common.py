"""描画で共有する定数と補助(色・目盛り・ウォーターフォールの並び・統計ラベルなど)。canvas からも同じ名前で読める。"""
import logging
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
from graphica.core.analysis import sample_standard_deviation
from graphica.core.axis_settings import AXIS_SETTING_DEFAULTS, axis_setting
from graphica.gui.theme import DARK_TOKENS, LIGHT_TOKENS
from typing import NamedTuple

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


# 軸の位置(図に対する割合)がこれより動かなければ収まったとみなす。1500 画素の図で 0.0002 画素
_LAYOUT_SETTLED_TOLERANCE = 1e-7
_LAYOUT_MAX_PASSES = 15


def fit_tight_layout(fig):
    """tight_layout を、軸の位置が動かなくなるまで繰り返す。

    tight_layout は今の配置から計算し直すので、注釈や目盛りの文字がはみ出す図では 1 回で収まらず、
    描くたびに少しずつ動く(描いた回数で見た目が変わる)。例外はそのまま上げる。
    """
    def positions():
        return [bound for ax in fig.axes for bound in ax.get_position().bounds]

    before = positions()
    for _ in range(_LAYOUT_MAX_PASSES):
        fig.tight_layout()
        after = positions()
        if len(after) == len(before) and all(abs(a - b) <= _LAYOUT_SETTLED_TOLERANCE
                                             for a, b in zip(after, before)):
            return
        before = after


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


class _SafeMultipleLocator(ticker.MultipleLocator):
    """間隔 interval の目盛り。その時の表示範囲で MAX_TICKS_PER_AXIS 本を超えるなら、その本数まで粗くする。

    範囲は描いた後もマウスの拡大・縮小や移動で変わるので、目盛りを作るたびに見る(範囲を戻せば設定の間隔に戻る)。
    """

    def __init__(self, interval):
        super().__init__(interval)
        self._interval = interval

    def tick_values(self, vmin, vmax):
        span = abs(vmax - vmin)
        if span > 0 and span / self._interval > MAX_TICKS_PER_AXIS:
            return ticker.MultipleLocator(span / MAX_TICKS_PER_AXIS).tick_values(vmin, vmax)
        return super().tick_values(vmin, vmax)


def _safe_multiple_locator(interval, axis_min, axis_max):
    """間隔 interval の目盛り(_SafeMultipleLocator)。今の範囲で細かすぎるなら、粗くして描くことをログに残す。"""
    axis_range = abs(axis_max - axis_min)
    if axis_range > 0 and interval > 0 and axis_range / interval > MAX_TICKS_PER_AXIS:
        logger.warning(
            "目盛り間隔 %.6g は軸範囲に対して細かすぎるため、%.6g に調整しました。",
            interval, axis_range / MAX_TICKS_PER_AXIS
        )
    return _SafeMultipleLocator(interval)


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
