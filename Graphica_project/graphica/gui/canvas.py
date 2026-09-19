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
from graphica.gui.plot_type_drawers import BUILTIN_PLOT_TYPE_DRAWERS
from graphica.gui.theme import LIGHT_TOKENS, DARK_TOKENS
from graphica.core.analysis import (calculate_lttb_downsample, calculate_moving_average_smooth,
                           calculate_median_smooth, calculate_gaussian_smooth,
                           sample_standard_deviation)
from graphica.core.unit_conversion import convert_x_axis_unit, X_AXIS_UNIT_NONE, X_AXIS_UNIT_LABELS

# 注釈キャッシュの「まだ一度も描いていない」を表す番兵(改善ボード E-2)。
# None を使うと、キーが None のときに誤って一致してしまう。
_NO_KEY = object()

logger = logging.getLogger(__name__)

# 目盛り間隔が細かすぎて描画が固まる/処理落ちするのを防ぐための上限。
# (軸範囲 / 間隔) がこれを超える場合は、間隔を自動的に粗くする。
# ★ matplotlib 自体が Locator.MAXTICKS=1000 を超えると警告を出すため、
#   境界の丸め誤差でそこに接触しないよう、余裕を持たせた値にしている。
MAX_TICKS_PER_AXIS = 500

# ウォーターフォール(積み重ね)表示の zorder を正規化する範囲(実機フィード
# バック: 「ウォーターフォール適用すると枠とかメモリが隠れる」の対策)。
# matplotlibの既定値は、目盛マーク(tick1line)が約2.01、スパイン(軸の枠線)が
# 2.5。オクルージョン用fill_between・トレース本体のzorderが常にこの範囲
# (WATERFALL_ZORDER_BASE 〜 WATERFALL_ZORDER_TOP)に収まるようにすることで、
# トレース数によらず軸の枠線・目盛より確実に下に描画されるようにする。
WATERFALL_ZORDER_BASE = 0.1
WATERFALL_ZORDER_TOP = 1.9

# ウォーターフォールの斜向/立体風トグル(項目120、C-514)。積み重ねインデックス
# 1つあたりのY振幅の縮小率(Dataset.waterfall_depth_shrink_ratio、ユーザーが
# waterfall_offset_x/yと同じくスピンボックスで指定)が大きすぎると、トレース数が
# 多い場合に振幅が潰れて見づらくなる/反転するため、下限0.2倍(80%縮小)で
# クランプする。
WATERFALL_DEPTH_SHRINK_MIN_SCALE = 0.2


def _waterfall_depth_scale(w_idx, enabled, shrink_ratio):
    """
    ウォーターフォールの斜向/立体風トグル(項目120、C-514)。積み重ね
    インデックスw_idx番目のトレースに掛けるY振幅の倍率を返す。
    無効時(enabled=False、既定)は1.0を返し、従来通り何も変形しない。
    shrink_ratioはDataset.waterfall_depth_shrink_ratio(1ステップあたりの
    縮小率、既定0.03=3%)をそのまま渡す。
    """
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

# 対数軸の補助目盛りの本数制御(項目C-604): x/y_log_minor_subs設定値 ->
# ticker.LogLocator(subs=...)に渡す値。'auto'はLogLocatorが軸の表示範囲
# (何桁分表示されているか)に応じて自動的に間引く既定動作、それ以外は
# 明示的なsubs集合(表示する仮数の桁、例えば'few'の(2,5)なら2,5の位置にのみ
# 補助目盛りを打つ)。
_LOG_MINOR_SUBS_PRESETS = {
    'auto': 'auto',
    'all': (2, 3, 4, 5, 6, 7, 8, 9),
    'few': (2, 5),
    'one': (5,),
}

# 矢印注釈の形状バリエーション(項目C-703): annotation['arrow_style'] ->
# matplotlibのarrowstyle文字列。既定'single'は追加前からの唯一の挙動('->')
# そのものなので、arrow_styleキーを持たない既存の保存済み注釈でも見た目は
# 変わらない。'bracket'は将来のP-402(有意差表示)の描画基盤を意識した選択。
_ARROW_STYLE_MAP = {
    'single': '->',
    'double': '<->',
    'bracket': ']-[',
}

# インセット(拡大図、項目138、C-711)の配置コーナー -> Axes相対座標(左下原点)
# のオフセット。サイズ(幅・高さ)はダイアログ側で選ぶ別パラメータのため、
# ここでは原点位置のみを定義する。
_INSET_CORNER_ORIGINS = {
    '右上': (0.55, 0.55),
    '左上': (0.05, 0.55),
    '右下': (0.55, 0.05),
    '左下': (0.05, 0.05),
}

# データ点ラベル表示(各点の脇にテキストを描画)は、点数が多いと
# ax.annotate() の呼び出し回数がそのまま増えてアプリがフリーズする原因になるため、
# この件数を超えるデータセットには自動的にラベルを描画しない。
# 環境設定ダイアログで変更可能 (main_window.py が起動時/変更時に
# self.point_label_max_points へ反映する)。
DEFAULT_POINT_LABEL_MAX_POINTS = 1000

# 表示用ダウンサンプリング(LTTB、項目C-1001)。1データセットあたりの点数が
# これを超える場合のみ、calculate_lttb_downsample()でLTTB_DOWNSAMPLE_TARGET_POINTS
# 点程度まで間引いて描画する(小〜中規模データセットは今まで通り無加工で描画)。
# ★ Line(連続曲線)にのみ適用する。LTTBは「線で結んだときの見た目の形状」を
#   保つアルゴリズムであり、点の疎密自体が情報であるScatter/Line+Scatterの
#   マーカーに適用すると実際のデータ密度分布が失われるため対象外とする
#   (過去にScatterも対象に含めていたのは設計上の見落としだった)。
LTTB_DOWNSAMPLE_THRESHOLD = 20000
LTTB_DOWNSAMPLE_TARGET_POINTS = 3000

# 2Dマップ(ヒートマップ、項目C-508)の表示用解像度の上限。1軸あたりの点数が
# これを超える場合、pcolormeshに渡す前に均等間引きして描画負荷を抑える
# (LTTB(項目C-1001)と同じく、redraw_all()が画面表示/エクスポート両方の
# 唯一の入口であるため、この間引きはエクスポートにも同様に適用される。
# 既存のLTTBダウンサンプリングも同じ挙動のため、それに倣った)。
GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS = 500

# 領域ハイライト(縦帯/横帯、項目C-701)の既定色・透明度。ann辞書に'color'/'alpha'
# キーが無い(将来の後方互換)場合のフォールバックとして使う。実際に新規作成される
# 領域ハイライトの既定値はgui/mixins/region_highlight_mixin.pyが常に明示的に
# 書き込むため、通常はここまで来ない値だが、両者は同じ値に保つこと。
REGION_HIGHLIGHT_DEFAULT_COLOR = '#F2A72B'
REGION_HIGHLIGHT_DEFAULT_ALPHA = 0.18


def _apply_legend_order(lines, labels, order):
    """
    凡例のハンドル/ラベルを、ユーザーが指定した表示順 (order: ラベル文字列のリスト)
    に並べ替える。描画順(=デフォルトの凡例順)と独立して凡例だけの順序を
    指定できるようにするための処理。
    order に無いラベル(新規追加されたデータセット等)は、元の描画順を保った
    まま末尾にまとめて追加する。
    """
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
    欠損値(NaN)の方針設定(項目C-201)を、描画直前のX/Y配列に適用する。
    Dataset.x_data/y_data(フィット・ピーク検出・エクスポート等の他の消費者が使う
    生データ)自体は書き換えない、表示専用の変換。

    'gap'(既定): 何もしない。matplotlibが自然にNaNの箇所で線を切ってくれる、
        この設定導入前からの挙動そのもの。
    'ffill': 直前の非NaN値で埋める(numpy配列のためpandas Seriesを介す)。
        先頭がNaNの場合は埋められる値が無いためNaNのまま残る(pandasのffillと同じ)。
    'drop': XかYどちらかがNaNの行を取り除き、前後の点を直接つないだ連続な線にする。
    未知の値(将来の後方互換のため)は 'gap' と同じく何もしない。
    """
    if policy == 'ffill':
        return (
            pd.Series(x_data).ffill().to_numpy(),
            pd.Series(y_data).ffill().to_numpy(),
        )
    if policy == 'drop':
        # pd.Series.isna() を使う(np.isnanではなく): 日付軸(datetime64)のX値でも
        # dtype変換なしにそのままNaT/NaN判定できるため。
        x_series = pd.Series(x_data)
        y_series = pd.Series(y_data)
        valid = (~x_series.isna()) & (~y_series.isna())
        return x_series[valid].to_numpy(), y_series[valid].to_numpy()
    return x_data, y_data


# 統計値アンカーラベル(項目C-708)の表示見出し。内部キー -> 表示ラベル。
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
    統計値アンカーラベル(項目C-708)の表示文字列を、dataset.y_data/fit_resultから
    その都度計算する。固定テキストではなく毎回の描画で再計算するため、データや
    フィットを更新すると値が自動的に追従する(イラレでの後処理では代替できない、
    このラベルの存在意義そのもの)。
    紐づくdatasetが見つからない(削除された)/値がまだ計算できない場合は、
    例外にせず「何を待っているか」が分かる短いプレースホルダを返す。
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


def _sci_each_formatter():
    """1目盛りごとに指数表記(例: 1.0×10^10)で表示するFuncFormatterを返す(項目62)。"""
    def _fmt(value, pos=None):
        if value == 0:
            return "0"
        exponent = int(np.floor(np.log10(abs(value))))
        mantissa = value / (10 ** exponent)
        if abs(mantissa) >= 9.995:  # 丸めで仮数部が10.0になり桁が繰り上がるケースを補正
            mantissa /= 10
            exponent += 1
        return rf"${mantissa:.1f}\times10^{{{exponent}}}$"
    return ticker.FuncFormatter(_fmt)


def _apply_tick_format_mode(axis, mode):
    """
    目盛りラベルの指数表記モード(項目62)を1つの軸(ax.xaxis または ax.yaxis)に適用する。
    mode: 0=自動(matplotlib既定のまま変更しない) / 1=軸端にまとめて指数表記(×10^n) /
          2=目盛りごとに指数表記(例: 1.0×10^10) / 3=常に小数表記(指数表記にしない)
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
    """
    実機フィードバック: 目盛りの数値を小数点以下何桁まで表示するかを、
    X軸/Y軸それぞれ独立して指定できるようにする。
    decimals が None または負値(既定、「自動」)の場合は何もせず、
    直前に_apply_tick_format_mode()が設定したフォーマッタ(指数表記モード等)
    をそのまま使う。0以上が指定された場合は、指数表記モードの設定に関わらず
    常に"%.{decimals}f"形式の固定小数点表記で上書きする(小数点以下の桁数を
    明示的に指定したいという要求は、指数表記との併用を想定していないため)。
    """
    if decimals is None or decimals < 0:
        return
    axis.set_major_formatter(ticker.FormatStrFormatter(f'%.{decimals}f'))


# 目盛線の長さ(pt、実機フィードバック)。既定値は matplotlib の rcParams
# (xtick.major.size=3.5 / xtick.minor.size=2.0)と同じにしてあり、長さの
# キーを持たない既存プロジェクトの見た目は変わらない。
# ★ 長さは軸サイズに対する倍率ではなく pt の絶対値にしている。文字サイズや
#   線の太さも pt 固定なので、目盛りだけ相対値にすると大きいサイズで
#   エクスポートしたときに「長い目盛りの横に小さい数字」とちぐはぐになり、
#   多パネル図ではパネルの大きさごとに長さが揃わなくなる(ユーザーと合意済み)。
DEFAULT_MAJOR_TICK_LENGTH = AXIS_SETTING_DEFAULTS['major_tick_length']
# 補助目盛の長さが「自動」(負値)のときに主目盛へ掛ける倍率。matplotlib の
# 既定の比率(2.0 / 3.5 ≈ 0.57)をそのまま使う: 主目盛と見分けがつく程度に
# 短く、かつ細い線でも潰れない長さで、既定値どうしの組み合わせが従来の
# 描画と完全に一致する。
MINOR_TICK_LENGTH_RATIO = 2.0 / 3.5
# 補助目盛の長さの「自動」を表す値(設定パネルのスピンボックスの最小値)。
# 判定は「負値なら自動」なので、この値そのものに依存するのは表示側だけ。
MINOR_TICK_LENGTH_AUTO = -0.5


def _resolve_tick_lengths(settings):
    """
    設定から (主目盛の長さ, 補助目盛の長さ) を pt で返す。
    minor_tick_length が未指定または負値なら「自動」とし、
    主目盛の長さ × MINOR_TICK_LENGTH_RATIO を使う。
    """
    major = axis_setting(settings, 'major_tick_length')
    if major is None or major < 0:
        major = DEFAULT_MAJOR_TICK_LENGTH
    minor = axis_setting(settings, 'minor_tick_length')
    if minor is None or minor < 0:
        minor = major * MINOR_TICK_LENGTH_RATIO
    return major, minor


# --- ダーク/ライトモード用の配色(項目H-3) ---
# ★ 以前はここに個別のハードコード値(例: '#2b2b2b')を持っており、
#   gui/theme.py のデザイントークンとは完全に無関係だった(H-0調査で判明した
#   既知の不整合、docs/dev/gui_style_audit.md 3節参照)。値が近いだけで一致しては
#   おらず、Qtの無彩色ではない寒色寄りのグレー(R<G<Bの傾向)とmatplotlib側の
#   純粋な無彩色グレー(R=G=B)がわずかに食い違っていた。gui/theme.pyの
#   トークンを直接参照するよう変更し、今後トークン側を変更すればグラフ側にも
#   自動的に反映されるようにする。
#
# Figure(外側の余白部分)とAxes(実際にデータが描かれる領域)は、
# plot_container(gui/main_window.py)がキャンバスの周囲に6pxのQtレベルの
# 余白を持っており、その背景色は{surface}トークンそのものであるため、
# FigureとAxesの両方を同じ{surface}に揃えることで、Qt側の余白とmatplotlib
# 側の余白の間に色の継ぎ目ができないようにしている(ライトモードは元々
# 両方#ffffffで一致していたため、この設計を踏襲した形)。
DARK_FIGURE_FACECOLOR = DARK_TOKENS['surface']
DARK_AXES_FACECOLOR = DARK_TOKENS['surface']
DARK_TEXT_COLOR = DARK_TOKENS['text_primary']
LIGHT_FIGURE_FACECOLOR = LIGHT_TOKENS['surface']
LIGHT_AXES_FACECOLOR = LIGHT_TOKENS['surface']
LIGHT_TEXT_COLOR = LIGHT_TOKENS['text_primary']

# 凡例のスタイリング(項目71/H-3): 軸の背景(surfaceトークン)と同化して縁が
# 見えなくならないよう、軸背景よりわずかに異なる面色(surface_2、他の
# UI要素の「一段乗ったチップ」表現と同じ考え方)+ border_strongトークンの
# 枠線にする。
DARK_LEGEND_FACECOLOR = DARK_TOKENS['surface_2']
DARK_LEGEND_EDGECOLOR = DARK_TOKENS['border_strong']
LIGHT_LEGEND_FACECOLOR = LIGHT_TOKENS['surface_2']
LIGHT_LEGEND_EDGECOLOR = LIGHT_TOKENS['border_strong']

# グリッド線(項目82)の色は従来matplotlibの既定値(rcParams、テーマと無関係な
# 固定の薄灰色)に任せきりだった。border_strongトークンを明示的に指定し、
# 背景色との調和を取る。
DARK_GRID_COLOR = DARK_TOKENS['border_strong']
LIGHT_GRID_COLOR = LIGHT_TOKENS['border_strong']


class _CanvasDrawingMixin:
    """
    MplCanvasの描画ロジック全体(Figure/Axes操作、プレーンなPython状態の初期化)を
    持つmixin。Qt(QWidget)に一切依存しないため、GUIスレッド用のMplCanvas
    (FigureCanvasQTAgg)と、バッチエクスポート用のヘッドレスキャンバス
    (_HeadlessRenderCanvas、FigureCanvasAgg)の両方から共有できる
    (項目C-004フェーズ5a)。
    """

    def _init_drawing_state(self, width, height, dpi):
        self.fig = Figure(figsize=(width, height), dpi=dpi)

        # グラフの軸(Axes)の管理も、ウィンドウではなくCanvas側で行う
        self.all_axes = []
        self.all_secondary_axes = []
        # 各軸のX軸データが日時型かどうか (日付軸の目盛りフォーマット自動選択に使用)
        self.axis_is_date_x = []
        # 各軸のX軸データが文字列カテゴリかどうか (数値専用の軸設定を無視するために使用)
        self.axis_is_category_x = []
        self.dark_mode = False # ダークモードが有効かどうか (main_windowから設定される)
        # データ点ラベルを描画する点数の上限(main_windowから環境設定に基づいて設定される)
        self.point_label_max_points = DEFAULT_POINT_LABEL_MAX_POINTS
        # 自由なテキスト注釈・矢印の描画済みArtistを軸インデックスごとに保持する。
        # update_appearance_only では fig.clf() を行わないため、再描画のたびに
        # 前回分を明示的に削除してから描き直さないと注釈が重複してしまう。
        self._annotation_artists = {}
        # 改善ボード E-2: 直近に描いた注釈の「内容キー」をAxesごとに保持する。
        # update_appearance_only(Axesをclaしない唯一の経路)で、前回と同じ内容なら
        # 全削除→全再生成を丸ごと省くために使う。詳細は _annotation_render_key()。
        self._annotation_render_keys = {}
        # データエディタと連動する「行ハイライト」の描画済みArtistを
        # dataset.dataset_id ごとに保持する (データ⇔グラフの双方向ハイライト機能)
        self._highlight_artists = {}
        # 表示用ダウンサンプリング(項目C-1001)を適用したデータセットについて、
        # 「描画された(間引き後の)配列上のインデックス」→「元のvisible_df上の
        # 位置インデックス」の対応を dataset.dataset_id ごとに保持する。
        # データカーソル(gui/mixins/cursor_mixin.pyの_on_pick)が、クリックされた
        # 点をartist.get_xdata()上のインデックスで特定した後、このマップで
        # 元のvisible_df.indexへ正しく変換するために使う(間引き後は両者が
        # 一致しなくなるため、マップを経由しないと誤った行がハイライトされる)。
        # 間引きが適用されていないデータセットはこの辞書に一切現れない。
        self.downsample_index_map = {}
        # 平滑化(CubicSpline)された曲線を持つデータセット(元データと1:1に対応
        # しない200点の補間点のため、クリックしても正しい行を特定できない)の
        # dataset_idを保持する(downsample_index_mapと同じくdataset_idキーの
        # 辞書/集合にしておくことで、ax.cla()を経て古いArtistが破棄され新しい
        # Artistがメモリ上の同じアドレスに再割り当てされてもidベースの集合の
        # ような取り違えが起きない)。gui/mixins/cursor_mixin.pyの
        # _toggle_cursor_mode()が「データカーソルモード」ON時に軸内の全
        # Line2D/PathCollectionへ一括でset_picker(5)を呼ぶため、_draw_data側の
        # 個別のpicker制御(_enable_element_picking呼び出し判定)だけでは
        # 不十分(モードON操作でpickerが再度有効化されてしまう)。この集合を
        # cursor_mixin.py側でも参照し、該当データセットのArtistへは
        # set_picker(5)を呼ばないようにする(二箇所で同じ判定基準を共有)。
        self._non_pickable_dataset_ids = set()
        # 2Dマップ(項目C-508)の描画結果(pcolormeshのQuadMesh)を軸インデックス
        # ごとに保持する。_apply_appearance()がこれを見てカラーバー(項目C-501)を
        # 付けるかどうかを判断する(_draw_dataとは別メソッドなので、Artist自体を
        # 一時的に受け渡す必要がある)。1軸に2Dデータセットが複数あっても
        # 最後に描画したものだけを保持する(カラーバーは1軸につき最大1つ)。
        self._axis_2d_mappables = {}
        # ウォーターフォール(積み重ね)表示の「データ座標 → 表示座標」変換
        # パラメータを dataset.dataset_id ごとに保持する(改善ボード A-1)。
        # ウォーターフォール有効時、トレースは
        #     表示X = データX + index * offset_x
        #     表示Y = データY * depth_scale + index * offset_y
        # の位置に描かれるため、マウス位置(表示座標)をデータ行に対応づける
        # 側は必ずこの逆変換を通す必要がある。値は
        # {'index': int, 'offset_x': float, 'offset_y': float, 'depth_scale': float}。
        # ウォーターフォール無効のデータセットはこの辞書に一切現れない
        # (= data_to_display/display_to_data が恒等変換になる)。
        self._waterfall_transforms = {}

    # --- ウォーターフォール表示座標 ⇔ データ座標 (改善ボード A-1) ---

    def get_waterfall_transform(self, dataset_or_id):
        """
        指定データセットの現在の積み重ね変換パラメータを返す。
        ウォーターフォールが無効、または未描画の場合は None。

        Args:
            dataset_or_id: Dataset オブジェクト、または dataset_id。
        """
        dataset_id = getattr(dataset_or_id, 'dataset_id', dataset_or_id)
        return self._waterfall_transforms.get(dataset_id)

    def data_to_display(self, dataset_or_id, x, y):
        """
        データ座標(dataset.x_data/y_data と同じ空間)を、実際に描画されている
        表示座標へ変換する。スカラーでも numpy 配列でも同じように使える。

        ウォーターフォールが無効なデータセット、および未描画のデータセットに
        対しては入力をそのまま返す(恒等変換)。
        """
        transform = self.get_waterfall_transform(dataset_or_id)
        if transform is None:
            return x, y
        index = transform['index']
        display_x = x if transform['offset_x'] == 0 else x + index * transform['offset_x']
        display_y = y * transform['depth_scale'] + index * transform['offset_y']
        return display_x, display_y

    def display_to_data(self, dataset_or_id, x, y):
        """
        data_to_display() の逆変換。マウス位置(表示座標)を、データ列と
        突き合わせられるデータ座標へ戻す。

        マウス操作をデータ行へ対応づける処理(範囲選択マスク・データカーソル・
        データエディタ連動ハイライト・ピーク配置)は、必ずこのメソッドを
        経由すること。経由しないと、積み重ね2本目以降で操作が全てずれる。
        """
        transform = self.get_waterfall_transform(dataset_or_id)
        if transform is None:
            return x, y
        index = transform['index']
        data_x = x if transform['offset_x'] == 0 else x - index * transform['offset_x']
        # depth_scale は WATERFALL_DEPTH_SHRINK_MIN_SCALE (0.2) で下限クランプ
        # されているため 0 除算にはならない。
        data_y = (y - index * transform['offset_y']) / transform['depth_scale']
        return data_x, data_y

    def _effective_text_color(self, configured_color):
        """
        ダークモード時、設定値がデフォルトの黒 ('#000000') のままだと
        暗い背景で文字が見えなくなるため、白系の色に自動変換する。
        ユーザーが明示的に別の色を選んでいる場合はそれをそのまま尊重する。
        """
        if self.dark_mode and configured_color == '#000000':
            return DARK_TEXT_COLOR
        return configured_color

    def _default_free_rect(self, index):
        """
        自由配置レイアウト(項目37)で、新しいサブプロットに割り当てる初期の
        (left, bottom, width, height) 正規化座標。互いに少しずつずらして
        重なりを避けつつ、ユーザーが後からドラッグで調整しやすい位置にする。
        """
        offset = 0.04 * (index % 6)
        left = min(0.1 + offset, 0.55)
        bottom = min(0.55 - offset, 0.55) if index % 2 == 0 else min(0.1 + offset, 0.5)
        return (left, max(bottom, 0.08), 0.45, 0.38)

    def _safe_draw(self):
        """
        self.draw()(matplotlibの実際の描画処理)を例外に対して防御的に
        呼び出す共通ヘルパー。実機フィードバック調査(macOSのある環境で、
        目盛りフォント関連の環境依存クラッシュ(LastResortHE-Regular.ttf
        欠落、redraw_all()側のtight_layout()の同種コメント参照)が
        繰り返し発生していた)から派生した対策。

        ★ 重要な違い: draw_idle()経由の遅延描画は、matplotlib自身の
        backend_qt.FigureCanvasQT._draw_idle()内で既に
        `try: self.draw() except Exception: traceback.print_exc()`と
        例外を握りつぶしている(コメント曰く「PyQt5では未捕捉例外が
        致命的になるため」)。この`traceback.print_exc()`は標準エラー出力に
        書くだけで、コンソールを持たないwindowedビルドのexe/appでは
        どこにも出力されず、こちらのlogger(ファイルログ)にも一切残らない。
        一方、redraw_all()/update_appearance_only()/
        update_all_axes_appearance_and_data()が最後に呼ぶself.draw()は
        「直接呼び出し」であり、これ自体には何の防御も無かった――例外が
        起きればログには残るはずだが、呼び出し元によっては見た目上
        「操作しても何も反映されない」ように見えるだけで終わることがある
        (呼び出し元のPySide6のシグナル配送経路によっては、例外が
        クラッシュハンドラまで届かないケースが実際にあり得る)。
        このヘルパーに統一することで、少なくとも自分のloggerには必ず
        記録が残るようにし、次回以降の実機での原因切り分けを容易にする。
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
        メインウィンドウから呼ばれる、全体の再描画メソッド。
        full_resolution=True の場合、LTTB表示用ダウンサンプリング(項目C-1001)を
        無視して常に全点描画する(_draw_data参照。単発/バッチエクスポートの
        「フル解像度」オプションから渡される)。
        """
        # データセットの表示/非表示トグル(項目C-907): visible=Falseのデータセットは
        # 削除せず保持したまま、描画対象から除外する。redraw_all()はメイン画面の
        # 再描画・エクスポート(gui/mixins/export_mixin.pyの単発/バッチ書き出しは
        # いずれもこのメソッド、または本メソッドが最後に描いたself.figを経由する)の
        # 唯一の入口であるため、1箇所でのフィルタが両方に自動的に効く。
        # ★ 改善ボード A-4: そのフィルタ自体は _draw_data() の内部へ移した
        # (このメソッドは非表示のものも含めた全リストをそのまま渡す)。
        # ウォーターフォールの積み重ねインデックスを「非表示のトレースも数に
        # 含めて」採番するには、_draw_data() が非表示のデータセットも受け取る
        # 必要があるため。呼び出し側で先にフィルタすると、その経路でだけ
        # 採番が繰り上がってしまうので絶対にしないこと。
        self.fig.clf()
        self.all_axes.clear()
        self.all_secondary_axes.clear()
        self.axis_is_date_x.clear()
        self.axis_is_category_x.clear()
        # fig.clf() で古いAxes(とその子Artist)はすべて破棄されるため、
        # 個別にremove()するまでもなく古い注釈Artist/ハイライトArtistの参照も無効になる
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
            # 自由配置レイアウト: 均等グリッドではなく、各サブプロットごとに
            # 保存済み(またはデフォルトの)矩形を使って個別に配置する。
            for i in range(subplot_count):
                rect = axis_setting(all_plot_settings[i], 'free_rect') or self._default_free_rect(i)
                ax = self.fig.add_axes(rect)
                self.all_axes.append(ax)
                self.all_secondary_axes.append(None)
        else:
            # 軸共有(項目C-601): 有効な場合、全サブプロットを最初のサブプロット
            # (self.all_axes[0])とsharex/shareyで束ねる(matplotlibのplt.subplots
            # (sharex=True, sharey=True)と同じ「グリッド全体で共通」の挙動。
            # 「同じ行/列のみ共有」ではなく、よりシンプルな全体共有とした)。
            # 内側の目盛りラベル(最下行以外のX軸ラベル・最左列以外のY軸ラベル)は
            # 共有時は冗長なので隠す(目盛り自体は残し、ラベル文字だけ消す)。
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

            # データの描画
            self._draw_data(ax, index, datasets, full_resolution=full_resolution)
            # 外観の適用
            self._apply_appearance(ax, index, settings)
            # ★ 軸共有(項目C-601)による内側の目盛数値抑制は、_apply_appearance()が
            #   目盛/目盛数値の表示状態を常に明示的に設定するようになった後で
            #   最後に適用する必要がある(先に適用すると_apply_appearance()に
            #   上書きされてしまう)。
            if not is_free_layout:
                self._apply_shared_axis_tick_visibility(index, rows, cols, share_x_axis, share_y_axis)
            # 自由なテキスト注釈・矢印・領域ハイライト・統計値アンカーラベルの描画
            self._draw_annotations(ax, index, settings, datasets=datasets, full_resolution=full_resolution)
            # パネルラベルの自動採番(項目C-712): (a)(b)(c)...をサブプロットの
            # 並び順(index)から機械的に計算する(文字自体は保存しない)。
            if panel_labels_enabled:
                self._draw_panel_label(ax, index)

            if self.all_secondary_axes[index] is not None:
                is_secondary_visible_global = True

        if not is_free_layout:
            # ★ 自由配置レイアウトでは、各サブプロットの位置・サイズをユーザーが
            # 明示的に指定しているため、tight_layout() で自動再配置すると
            # その指定が上書きされてしまう。そのためグリッドレイアウトのみ適用する。
            # ★ 実機フィードバック(ログで確認): 環境によってはmatplotlib自体の
            #   インストールが不完全で、フォールバック用フォント
            #   (LastResortHE-Regular.ttf)が欠落しているケースがある。この場合
            #   tight_layout()のラベルbbox計算がFileNotFoundErrorで失敗し、
            #   アプリ全体がクラッシュしていた。Graphica側で修正できる問題では
            #   ないため、レイアウト最適化自体を諦めて描画を続行する
            #   (見た目が多少崩れるだけで、クラッシュよりはるかに良い)。
            try:
                self.fig.tight_layout()
            except (ValueError, FileNotFoundError):
                pass

        self._safe_draw()
        return is_secondary_visible_global # UI更新用にメインウィンドウへ結果を返す

    def update_appearance_only(self, all_plot_settings, datasets=(), rows=1, cols=1,
                                layout_mode='grid', share_x_axis=False, share_y_axis=False):
        """
        データはそのままに、外観設定だけを適用し直す（軽量版）。
        datasets は統計値アンカーラベル(項目C-708)の値再計算にのみ使う
        (_draw_dataは呼ばないため、この経路ではデータそのものは再描画されない)。
        省略時(既定の空タプル)は統計値アンカーラベルが「データセットなし」表示に
        フォールバックするだけで、他の描画には影響しない。
        """
        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)
        is_free_layout = layout_mode == 'free'
        for index, ax in enumerate(self.all_axes):
            if index < len(all_plot_settings):
                settings = all_plot_settings[index]
                self._apply_appearance(ax, index, settings)
                # ★ redraw_all()と同じ理由: 軸共有による内側の目盛数値抑制は
                #   _apply_appearance()の後に適用しないと上書きされてしまう
                #   (実機フィードバック: 目盛表示切替のON/OFFが反映されない
                #   バグの修正に伴い、_apply_appearance()が常に明示的に
                #   表示状態を設定するようになったため)。
                if not is_free_layout:
                    self._apply_shared_axis_tick_visibility(index, rows, cols, share_x_axis, share_y_axis)
                # E-2: この経路は Axes を cla() しないので、内容が変わって
                # いなければ既存の注釈Artistをそのまま使い回せる。
                self._draw_annotations(ax, index, settings, datasets=datasets,
                                       allow_reuse=True)
        try:
            self.fig.tight_layout()
        except (ValueError, FileNotFoundError):
            # ★ FileNotFoundError: 環境依存のフォント欠落によるクラッシュ対策。
            #   redraw_all()側の同名except節のコメント参照。
            pass
        self._safe_draw()

    def _apply_shared_axis_tick_visibility(self, axis_index, rows, cols, share_x_axis, share_y_axis):
        """
        軸共有(項目C-601)有効時、内側の目盛りラベル(最下行以外のX軸ラベル・
        最左列以外のY軸ラベル)を隠す。redraw_all()のAxes構築時、および
        update_single_axis()(ax.cla()がtick_paramsをリセットするため)の
        両方から呼ばれる共通ヘルパー。自由配置レイアウト(cols=0)では
        行/列の概念自体が無いため何もしない。
        """
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
        """
        update_single_axis()の実体(self.draw_idle()を呼ぶ直前まで)。項目C-003
        フェーズ2のupdate_all_axes_appearance_and_data()が全Axes分ループする際、
        Axesごとにdraw_idle()を呼ぶ無駄を避け、Figureレベルのdraw()をループの
        外側で1回だけで済ませられるよう、draw呼び出しを含まない部分を切り出した。
        """
        if axis_index >= len(self.all_axes):
            return

        # twinx()で作られた副軸はax.cla()では消えない別のAxesオブジェクトのため、
        # 明示的にFigureから取り除いてから作り直す(取り除かないと呼ぶたびに
        # 副軸が積み重なる)。
        old_secondary = self.all_secondary_axes[axis_index]
        if old_secondary is not None:
            old_secondary.remove()
            self.all_secondary_axes[axis_index] = None

        ax = self.all_axes[axis_index]
        ax.cla()  # このAxesのartist/凡例だけをクリア。他のAxesは無傷。

        # cla()で古いArtistへの参照はすでに無効なので、remove()を試みず単に破棄する。
        self._annotation_artists.pop(axis_index, None)
        self._annotation_render_keys.pop(axis_index, None)
        for dataset_id in [ds.dataset_id for ds in datasets if ds.subplot_target == axis_index]:
            self._highlight_artists.pop(dataset_id, None)
            self.downsample_index_map.pop(dataset_id, None)
            self._non_pickable_dataset_ids.discard(dataset_id)

        # visible フィルタは _draw_data() の内部で行う(改善ボード A-4、redraw_all参照)
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
        指定した1つのAxesだけを描き直す(項目C-003 フェーズ1)。他のAxes・
        Figure自体は一切触らない(fig.clf()を経由しないため、他のAxesを
        参照しているコード―NavigationToolbarのHomeキャッシュ、他インデックスの
        _annotation_artists/_highlight_artists/downsample_index_map等―への
        影響がない)。1データセットのスタイル変更や(項目C-003フェーズ3a)
        subplot_target/use_secondary_yの変更(旧軸・新軸それぞれに対して
        本メソッドを呼ぶ)専用。Axesの枚数・GridSpec配置自体を変える
        構造的な変更(レイアウト行数/列数変更、自由配置のサブプロット
        追加/削除)は呼び出し側でredraw_all()相当のフル再描画、または
        add_free_axis()/remove_last_free_axis()に振り分けること。
        """
        self._redraw_single_axis_no_draw(
            axis_index, datasets, settings, rows=rows, cols=cols,
            share_x_axis=share_x_axis, share_y_axis=share_y_axis,
            panel_labels_enabled=panel_labels_enabled, full_resolution=full_resolution,
        )
        self.draw_idle()

    def add_free_axis(self, datasets, settings, panel_labels_enabled=False):
        """
        自由配置レイアウトへ、末尾に新しい1つのAxesを追加する(項目C-003
        フェーズ3b)。他のAxes・Figure自体は一切触らない(fig.clf()を
        経由しない)。「+ プロット追加」ボタン(gui/mixins/layout_edit_mixin.py
        の_on_add_free_subplot)専用: 新規追加されるサブプロットは常に
        既存データセットのどれからも参照されない空のAxesのため、他の
        Axesへの影響が構造的に発生しない(update_single_axis()と違い
        「既存Axesの中身を差し替える」のではなく「新しいAxesを1つ増やす」
        操作であることに注意)。
        """
        rect = axis_setting(settings, 'free_rect') or self._default_free_rect(len(self.all_axes))
        ax = self.fig.add_axes(rect)
        self.all_axes.append(ax)
        self.all_secondary_axes.append(None)
        self.axis_is_date_x.append(False)
        self.axis_is_category_x.append(False)

        axis_index = len(self.all_axes) - 1
        # visible フィルタは _draw_data() の内部で行う(改善ボード A-4、redraw_all参照)
        self._draw_data(ax, axis_index, datasets)
        self._apply_appearance(ax, axis_index, settings)
        self._draw_annotations(ax, axis_index, settings, datasets=datasets)
        if panel_labels_enabled:
            self._draw_panel_label(ax, axis_index)

        self.draw_idle()

    def remove_last_free_axis(self, datasets):
        """
        自由配置レイアウトから、末尾の1つのAxesを削除する(項目C-003
        フェーズ3b)。他のAxes・Figure自体は一切触らない。「- プロット削除」
        ボタン(_on_remove_free_subplot)は常に末尾のサブプロットのみを
        削除する仕様のため、削除対象は常にself.all_axesの最後の要素になる
        (途中の要素を削除するケースは無いため、他のAxesのインデックスを
        振り直す必要が生じない)。

        ★ 呼び出し側の責務: 削除されたサブプロットに割り当てられていた
        データセットは、_on_remove_free_subplot側で既に新しい末尾の
        サブプロットへsubplot_targetを付け替え済みであることを前提とする
        (このメソッド自体はAxesオブジェクトの後片付けのみ行い、付け替え後の
        新しい末尾Axesへのデータ再描画は呼び出し側がupdate_single_axis()で
        別途行うこと)。
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
        既存のAxes枚数・GridSpec配置(all_axes/all_secondary_axesの所属)を
        一切変えず、全Axesのデータ・外観だけを軽量に描き直す(項目C-003
        フェーズ2)。パネルラベル表示切替・ダークモード切替のような「全Axesを
        均一に触るが軸の所属自体は変えない」トリガー専用。redraw_all()と異なり
        fig.clf()を経由しないため、Axes数・GridSpec配置自体が変わるケース
        (レイアウト行数/列数変更)には使えない――呼び出し側でこの前提が
        崩れないことを保証すること(subplot_target/use_secondary_yの変更や
        自由配置のサブプロット追加/削除は、項目C-003フェーズ3aでの
        update_single_axis()複数回呼び出し、フェーズ3bでのadd_free_axis()/
        remove_last_free_axis()により、既にAxes単位の軽量パスへ移行済み)。
        update_single_axis()を既存Axes数ぶんループしたのち、redraw_all()が
        1回だけ行っていたFigureレベルの処理(facecolor設定・tight_layout・
        実際のdraw()・is_secondary_visible_globalの再計算)をループの外側で
        まとめて1回だけ行う。
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
            # ★ 自由配置レイアウトでは各サブプロットの位置・サイズをユーザーが
            # 明示的に指定しているため、redraw_all()と同様tight_layout()は
            # グリッドレイアウトのみ適用する。
            try:
                self.fig.tight_layout()
            except (ValueError, FileNotFoundError):
                # ★ FileNotFoundError: 環境依存のフォント欠落によるクラッシュ対策。
                #   redraw_all()側の同名except節のコメント参照。
                pass

        self._safe_draw()
        return is_secondary_visible_global

    def _draw_panel_label(self, ax, index):
        """
        サブプロットの左上に (a)(b)(c)... の連番ラベルを描画する(項目C-712)。
        ラベル文字自体は保存せず、サブプロットの並び順(index)から毎回
        機械的に計算するため、並び替え・追加・削除しても自動的に振り直される。
        """
        label = self._panel_label_for_index(index)
        text_color = DARK_TEXT_COLOR if self.dark_mode else LIGHT_TEXT_COLOR
        ax.text(
            -0.12, 1.08, f"({label})", transform=ax.transAxes,
            fontsize=12, fontweight='bold', color=text_color,
            ha='left', va='top', zorder=10,
        )

    @staticmethod
    def _panel_label_for_index(index):
        """0->a, 1->b, ..., 25->z, 26->aa, 27->ab, ... (Excel列名と同じ方式で26件超にも対応)"""
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
        インセット(拡大図、項目138/C-711)の中に描く点列へ、本体の描画と同じ
        LTTB表示用ダウンサンプリング(項目C-1001)を適用する(改善ボード E-1)。

        インセットは注釈として実装されており、注釈は再描画のたびに全削除→
        全再生成される。そのため間引きを通さないと、大きなデータでインセットを
        1つ置いただけで、再描画のたびに数万〜数十万点を描き直すことになる
        (#138実装時の抜け)。

        本体の_draw_data側と違い、plot_typeによる出し分けは行わない。
        インセット内はplot_typeに関わらず常に単純な折れ線として描く仕様
        (「ズームした概観」を見せる用途と割り切った意図的な簡略化)であり、
        「マーカーの疎密自体が情報だからScatterは対象外」という本体側の理由が
        そもそも当てはまらないため。

        LTTBはXが昇順であることを前提とするアルゴリズムなので、本体側と同じく
        昇順のデータにのみ適用する(降順/非単調なXは全点描画のまま)。

        Args:
            x_data, y_data (np.ndarray): 拡大範囲でフィルタ済みの点列。
            full_resolution (bool): エクスポートの「フル解像度」オプション。
                Trueなら点数によらず全点をそのまま返す。

        Returns:
            (np.ndarray, np.ndarray): 描画に使うx/y(間引き不要ならそのまま)。
        """
        if full_resolution or len(x_data) <= LTTB_DOWNSAMPLE_THRESHOLD:
            return x_data, y_data
        if not np.all(np.diff(x_data) >= 0):
            return x_data, y_data
        indices = calculate_lttb_downsample(x_data, y_data, LTTB_DOWNSAMPLE_TARGET_POINTS)
        return x_data[indices], y_data[indices]

    def _annotation_render_key(self, axis_index, settings, datasets, full_resolution):
        """
        いま描こうとしている注釈の「結果を決める入力すべて」をまとめた文字列を返す
        (改善ボード E-2 のキャッシュキー)。

        ★ グローバル規約「キャッシュのキーには結果に影響する入力を全部含める」に
        従って、注釈リストそのものだけでなく次も含めている:

        - **ダークモード**: テキスト/矢印の色は `_effective_text_color()` を通すので、
          注釈リストが同一でもモードが変われば描画結果が変わる。これを落とすと
          「ダークモードにしたのに注釈の色だけ元のまま」という壊れ方をする。
        - **統計値アンカーラベル(type='stat')の確定テキスト**: この経路は
          `datasets` を「統計値の再計算のため」に受け取る設計で、値が変われば
          表示も変わる。計算結果の文字列そのものをキーに入れることで、
          値が変わったときだけ描き直す。
        - **インセット(type='inset')が参照するデータセットの見た目**:
          色・線幅・不透明度・表示/非表示。

        インセットが描く「データそのもの」はキーに含めない。この関数を使うのは
        `update_appearance_only()` だけで、その経路は `_draw_data()` を呼ばない
        =「データは変わっていない」を前提に本体の描画も省いているため、
        インセットだけ別の前提を置く必要がないから(データが変わる操作は
        `ax.cla()` を伴う別の経路を通り、そこでは再利用しない)。
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
        settings['annotations'] (テキスト注釈・矢印注釈・領域ハイライト・統計値
        アンカーラベルのリスト) を描画する。再描画のたびに、まず前回このAxesに
        描画した注釈Artistを削除してから描き直すことで、update_appearance_only
        経由での重複描画を防ぐ。

        allow_reuse=True(改善ボード E-2): 前回と内容が変わっていなければ、
        全削除→全再生成を丸ごと省いて既存のArtistをそのまま残す。
        **この指定ができるのは `update_appearance_only()` だけ**で、既定はFalse。
        他の3経路(`redraw_all` は `fig.clf()`、`_redraw_single_axis_no_draw` は
        `ax.cla()`、`add_free_axis` は新規Axes)では前回のArtistが既に破棄されて
        いるため、再利用してしまうと注釈が消える。将来の呼び出し元が何も考えずに
        安全側へ倒れるよう、既定をFalseにしてある。

        効くのは主にインセット(拡大図)で、中でデータセットを再プロットするため
        「注釈数×データ点数」のコストが軸の書式をいじるたびにかかっていた
        (E-1 でインセットの間引きは入れたが、毎回作り直す構造自体は残っていた)。

        datasets は統計値アンカーラベル(項目C-708、type='stat')が参照先の
        Datasetを解決するために使う。省略時(None)は全て「データセットなし」
        表示にフォールバックする(既存呼び出し元・テストとの後方互換のため)。

        full_resolution=True の場合、インセット(拡大図)内の描画でも
        LTTB表示用ダウンサンプリング(項目C-1001)を行わず全点描画する
        (_draw_data と同じく、エクスポートの「フル解像度」オプション用)。
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
                    # 矢印のバリエーション拡張(項目C-703): 通常(片矢印)/両矢印/
                    # ブラケットの3種類。arrow_style/arrow_curvatureを持たない
                    # 既存の保存済み注釈は既定値(直線の片矢印)にフォールバックし、
                    # 追加前と全く同じ見た目になる。
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
                    # 領域ハイライト(項目C-701)。色は注釈の文字色(テーマの
                    # 明暗による自動反転、_effective_text_color)とは無関係の
                    # ユーザー指定色をそのまま使うため変換しない。
                    lo, hi = ann.get('range', (0, 0))
                    color = ann.get('color', REGION_HIGHLIGHT_DEFAULT_COLOR)
                    alpha = ann.get('alpha', REGION_HIGHLIGHT_DEFAULT_ALPHA)
                    if ann_type == 'vspan':
                        artist = ax.axvspan(lo, hi, color=color, alpha=alpha, zorder=0.5)
                    else:
                        artist = ax.axhspan(lo, hi, color=color, alpha=alpha, zorder=0.5)
                elif ann_type == 'inset':
                    # インセット(拡大図)+拡大範囲の指示線(項目138、C-711)。
                    # #37自由配置のドラッグ基盤の流用は見送り(既存5モードの
                    # マウス排他機構に7つ目を組み込むリスクに見合わないと判断)、
                    # コーナー位置+サイズのプリセット選択で位置を決める簡略版。
                    # インセット内の描画は、フル機能の_draw_data()を再利用せず、
                    # 対象軸の各データセットのx/yを指定X範囲でそのまま単純な
                    # 折れ線として描く(plot_type/グラデーション等は再現しない、
                    # 「ズームした概観」を見せる用途と割り切った意図的な簡略化)。
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
                    # 統計値アンカーラベル(項目C-708)。Axes相対座標(0〜1、
                    # ax.transAxes)を使うため、データのズーム/パンに関わらず
                    # 常に同じ画面上の位置(既定では左上を起点に縦積み)に留まる。
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
        # 再利用しない経路でもキーは更新しておく。そうしないと、直後の
        # update_appearance_only が必ず1回ぶん無駄に描き直すことになる。
        self._annotation_render_keys[axis_index] = render_key

    def _enable_element_picking(self, artist):
        """
        グラフ要素の直接クリック選択(項目35)のため、Artistをクリック検出可能にする。
        Bar (BarContainer) は単一のArtistではなく Rectangle の集合なので、
        個々のpatchに対して設定する必要がある。
        """
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
        線ストロークグラデーション(項目79): 線を細かいセグメントに分割し、
        各セグメントに開始色(color1)→終端色(color2)を線形補間した色を割り当てる
        LineCollectionとして描画する(matplotlibにはグラデーション線を直接描く
        機能が無いため、これが定番の実現方法)。

        ★ 注意点(オートスケールの落とし穴): ax.plot() と違い、
        ax.add_collection() は呼び出しただけではAxesの表示範囲(view limits)を
        自動的に広げてくれない場合がある。Collection自体は autolim=True が
        既定でdataLim(データ範囲)は更新されるが、実際に軸の見た目の範囲へ
        反映されるのは呼び出し側(_apply_appearance)がautoscaleを適用した
        タイミングになる。取りこぼしが無いよう、ここでも明示的に
        ax.update_datalim() を呼んでデータ範囲を確実に反映させておく。
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        if len(x) < 2:
            # 点が0〜1個だとセグメント(区間)を作れないため、通常の線として描画する
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
        # 各セグメントに、線の始点からの位置(0.0=開始 ～ 1.0=終端)を割り当てる
        lc.set_array(np.linspace(0, 1, len(segments)))
        ax.add_collection(lc)
        # ★ オートスケール対策(上記docstring参照): データ範囲を明示的に反映
        ax.update_datalim(np.column_stack([x, y]))
        return lc

    def _add_gradient_fill(self, ax, x, y, color1, color2, alpha, baseline=0.0):
        """
        塗りグラデーション(項目79): fill_between() が作るのと同じ形状(X/Y値と
        基準線baselineの間の領域)のポリゴンをクリップパスとして使い、
        ax.imshow() で描いたグラデーション画像をその内側だけに見せる
        (matplotlibで「グラデーション塗り」を実現する定番のレシピ)。
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        # 縦方向(下→上)のグラデーション画像。origin='lower' で配列の先頭行が
        # 下端に描かれるため、下端=終端色(color2)・上端=開始色(color1)になるよう
        # 色の並びを反転させておく。
        gradient = np.linspace(0, 1, 256).reshape(-1, 1)
        cmap = LinearSegmentedColormap.from_list('graphica_fill_gradient', [color2, color1])

        x_min, x_max = float(np.nanmin(x)), float(np.nanmax(x))
        y_min = float(min(np.nanmin(y), baseline))
        y_max = float(max(np.nanmax(y), baseline))
        # 全点が同じX(またはY)座標だとimshowのextentが潰れてしまうため、
        # わずかに幅を持たせておく
        if x_min == x_max:
            x_min, x_max = x_min - 0.5, x_max + 0.5
        if y_min == y_max:
            y_min, y_max = y_min - 0.5, y_max + 0.5

        im = ax.imshow(
            gradient, cmap=cmap, aspect='auto', origin='lower',
            extent=(x_min, x_max, y_min, y_max), alpha=alpha, zorder=1,
        )

        # fill_between()と同じ塗り領域(データ点を辿った後、基準線上を逆向きに
        # 戻ってくる多角形)をクリップパスとして使う
        verts = list(zip(x, y)) + [(x[-1], baseline), (x[0], baseline)]
        clip_poly = Polygon(verts, closed=True, transform=ax.transData)
        im.set_clip_path(clip_poly)

        # ★ imshow()はax.plot()と異なりデータ範囲を自動的に広げないため、
        # 塗り領域の範囲を明示的に反映させておく(オートスケール対策)
        ax.update_datalim(np.array([[x_min, y_min], [x_max, y_max]]))
        return im

    # data_kind='2d_grid'データセットのmap_display_modeとして有効な値
    _VALID_MAP_DISPLAY_MODES = ('heatmap', 'contour', 'contour_filled', 'heatmap_contour')

    def _draw_2d_data(self, ax, axis_index, datasets_2d, full_resolution=False):
        """
        2Dマップ(ヒートマップ/等高線、項目C-508/C-509)を描画する。Dataset.z_grid
        (core/dataset.py、core/grid_data.pyのcompute_z_grid()の結果をキャッシュした
        もの)が既に規則格子/補間格子どちらの場合も同じ形の辞書を返すため、
        ここでは区別せずpcolormesh/contour/contourfに渡すだけでよい。imshow
        (規則格子限定・高速)ではなくpcolormeshに統一しているのは、規則格子/
        補間格子のどちらのX/Y間隔にも対応できる(imshowは等間隔前提)ことを
        優先したため(大規模データはGRID_2D_MAX_DISPLAY_POINTS_PER_AXISの
        間引きで対応する)。

        ds.map_display_mode(項目C-509)で描画方式を切り替える:
        'heatmap'(既定、pcolormesh) / 'contour'(線のみ、ds.colorを線色・
        ds.linewidthを太さとして使う) / 'contour_filled'(塗りつぶし等高線、
        ds.colormapで塗る) / 'heatmap_contour'(ヒートマップに等高線を重ね描き)。
        カラーバー用のmappable(_axis_2d_mappables)には、塗りを伴うモード
        (heatmap/contour_filled/heatmap_contour)の場合のみ登録する
        (線のみのcontourは通常カラーバーを付けない慣習に合わせる)。
        """
        self._axis_2d_mappables.pop(axis_index, None)
        for ds in datasets_2d:
            grid = ds.z_grid
            if grid is None:
                continue
            x_grid, y_grid, z_grid = grid['x_grid'], grid['y_grid'], grid['z_grid']

            # 大規模グリッドの表示負荷対策: 1軸あたりの点数が上限を超える場合、
            # 均等間隔で間引く(既存のLTTBダウンサンプリング(項目C-1001)と同じく、
            # redraw_all()が画面表示/エクスポート両方の唯一の入口のため、この
            # 間引きはエクスポートにも同様に適用される)。full_resolution=True
            # (エクスポート時の「フル解像度」オプション、_draw_data参照)が
            # 指定された場合は、Line用LTTBと同様に間引きを無視する。
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
                # ★ label=ds.nameは付けない: QuadMesh/ContourSetは凡例の
                # ハンドルとして非対応で、_apply_appearance()の
                # ax.get_legend_handles_labels()が毎回警告を出してしまう
                # (2Dマップの識別はカラーバー(項目C-501)が担うため、凡例に
                # 載せる必要はない)。
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
                # 不明なカラーマップ名等、matplotlib側が拒否した場合は
                # このデータセットの描画だけをスキップする(他のデータセットや
                # 軸全体を巻き込んでクラッシュさせない)。
                logger.warning("2Dマップの描画に失敗しました(%s): %s", ds.name, e)
                continue

            # ds.artistはカラーバー対象のmappable(塗りを伴うモード)を優先し、
            # 線のみのcontourモードではcontour_set自体を保持する(データカーソル等の
            # 将来的な連動を見据えて、描画されたArtistを必ず何か保持しておく)。
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
        データエディタで選択された行に対応するデータ点を、グラフ上でハイライトする
        (データ⇔グラフの双方向ハイライト機能)。
        master_indices は dataset.df のインデックスラベルのリストで、空リストなら
        そのデータセットのハイライトを消す。

        Args:
            dataset (Dataset): ハイライト対象のデータセット。
            master_indices (list): dataset.df.index のラベルのリスト。
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
            # ★ x_data/y_data は visible_df (マスクされた行を除いたもの) 基準のため、
            # 位置への変換もマスター df.index ではなく visible_df.index で行う必要がある
            # (マスクされている行はそもそもプロットされていないためハイライトも対象外)。
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
        # ★ 改善ボード A-1: x_data/y_data はデータ座標なので、ウォーターフォール
        # (積み重ね)有効時にそのまま描くと、トレース本体とは違う位置(積み重ね
        # のずれが掛かっていない位置)に丸が出てしまう。実際にトレースが描かれて
        # いる表示座標へ変換してからハイライトを打つ。無効時は恒等変換。
        x_vals, y_vals = self.data_to_display(dataset, x_vals, y_vals)
        artist = ax.scatter(
            x_vals, y_vals, s=160, facecolors='none', edgecolors='#e6194b',
            linewidths=2.0, zorder=15
        )
        self._highlight_artists[dataset.dataset_id] = artist
        self.draw_idle()

    def _draw_point_labels(self, ax, ds, x_data=None, y_data=None, downsample_indices=None):
        """
        データセットの各点の脇に、Y値または指定列の値をテキストとして表示する。
        point_label_col_name が None ならY値そのもの、指定されていればその列の値を使う。
        x_data/y_data を明示的に渡すと、そちらを表示位置として使う(ウォーターフォール
        (項目80/109)有効時に、ずらした後の位置にラベルを追従させるため)。
        省略時は ds.x_data/ds.y_data (元の位置) を使う。

        downsample_indices: LTTB表示用ダウンサンプリング(項目C-1001)が適用された
        場合の間引き後→元のvisible_df上の位置への変換配列(_draw_data参照、
        誤差バー/バンドと同じもの)。指定された場合、label_values側も同じ
        インデックスで間引いて揃える(揃えないとzip()が短い方(間引き後の
        x_data/y_data)で打ち切られ、「間引き後のi番目の点」に「元データi番目の
        行のラベル値」という無関係な組み合わせが表示されてしまう)。
        """
        if x_data is None:
            x_data = ds.x_data
        if y_data is None:
            y_data = ds.y_data

        if ds.point_label_col_name and ds.point_label_col_name in ds.df.columns:
            # ★ x_data/y_dataはvisible_df(マスクされた行を除いたもの)基準のため、
            # 同じ行と対応させるにはこちらもvisible_dfから取得する必要がある。
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
                clip_on=True,  # ★ Text/Annotationは既定でclip_on=False。マスク解除で
                # 軸範囲外の点が再表示された際、ラベルだけが枠外にはみ出て
                # SVG/PDF等の出力に残ってしまうのを防ぐため明示的にTrueにする。
                # (マーカー自体はLine2D/PathCollectionの既定clip_on=Trueで元々
                # 軸範囲外なら描画されない — 挙動を揃える)
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
    """
    バッチエクスポート専用のQt非依存キャンバス(項目C-004フェーズ5a)。
    QWidgetのサブクラスではないため、GUIスレッド外(実スレッド)で構築・
    描画しても安全。mpl_connect等のインタラクティブなイベント配線は
    行わない(MplCanvas自体にも存在せず、全てmain_window.py/mixins側で
    外付けされているため対象外)。
    """
    def __init__(self, width=5, height=4, dpi=100):
        self._init_drawing_state(width, height, dpi)
        super().__init__(self.fig)