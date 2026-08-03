import logging
import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
import matplotlib.ticker as ticker
import matplotlib.dates as mdates

logger = logging.getLogger(__name__)

# 目盛り間隔が細かすぎて描画が固まる/処理落ちするのを防ぐための上限。
# (軸範囲 / 間隔) がこれを超える場合は、間隔を自動的に粗くする。
# ★ matplotlib 自体が Locator.MAXTICKS=1000 を超えると警告を出すため、
#   境界の丸め誤差でそこに接触しないよう、余裕を持たせた値にしている。
MAX_TICKS_PER_AXIS = 500


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


# --- ダークモード用の配色 ---
DARK_FIGURE_FACECOLOR = '#2b2b2b'
DARK_AXES_FACECOLOR = '#1e1e1e'
DARK_TEXT_COLOR = '#e0e0e0'
LIGHT_FIGURE_FACECOLOR = '#ffffff'
LIGHT_AXES_FACECOLOR = '#ffffff'
LIGHT_TEXT_COLOR = '#000000'

# 凡例のスタイリング(項目71): 軸の背景と同化して縁が見えなくならないよう、
# ダークモードでは軸背景よりわずかに明るい面色 + 中間グレーの枠線にする。
DARK_LEGEND_FACECOLOR = '#2A2A2A'
DARK_LEGEND_EDGECOLOR = '#4A4A4A'
LIGHT_LEGEND_FACECOLOR = '#FFFFFF'
LIGHT_LEGEND_EDGECOLOR = '#CCCCCC'


class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)

        # グラフの軸(Axes)の管理も、ウィンドウではなくCanvas側で行う
        self.all_axes = []
        self.all_secondary_axes = []
        # 各軸のX軸データが日時型かどうか (日付軸の目盛りフォーマット自動選択に使用)
        self.axis_is_date_x = []
        # 各軸のX軸データが文字列カテゴリかどうか (数値専用の軸設定を無視するために使用)
        self.axis_is_category_x = []
        self.dark_mode = False # ダークモードが有効かどうか (main_windowから設定される)
        # 自由なテキスト注釈・矢印の描画済みArtistを軸インデックスごとに保持する。
        # update_appearance_only では fig.clf() を行わないため、再描画のたびに
        # 前回分を明示的に削除してから描き直さないと注釈が重複してしまう。
        self._annotation_artists = {}
        # データエディタと連動する「行ハイライト」の描画済みArtistを
        # dataset.dataset_id ごとに保持する (データ⇔グラフの双方向ハイライト機能)
        self._highlight_artists = {}

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

    def redraw_all(self, datasets, rows, cols, all_plot_settings, layout_mode='grid'):
        """メインウィンドウから呼ばれる、全体の再描画メソッド"""
        self.fig.clf()
        self.all_axes.clear()
        self.all_secondary_axes.clear()
        self.axis_is_date_x.clear()
        self.axis_is_category_x.clear()
        # fig.clf() で古いAxes(とその子Artist)はすべて破棄されるため、
        # 個別にremove()するまでもなく古い注釈Artist/ハイライトArtistの参照も無効になる
        self._annotation_artists.clear()
        self._highlight_artists.clear()
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
                rect = all_plot_settings[i].get('free_rect') or self._default_free_rect(i)
                ax = self.fig.add_axes(rect)
                self.all_axes.append(ax)
                self.all_secondary_axes.append(None)
        else:
            for i in range(subplot_count):
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
            # 自由なテキスト注釈・矢印の描画
            self._draw_annotations(ax, index, settings)

            if self.all_secondary_axes[index] is not None:
                is_secondary_visible_global = True

        if not is_free_layout:
            # ★ 自由配置レイアウトでは、各サブプロットの位置・サイズをユーザーが
            # 明示的に指定しているため、tight_layout() で自動再配置すると
            # その指定が上書きされてしまう。そのためグリッドレイアウトのみ適用する。
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
                self._draw_annotations(ax, index, settings)
        try:
            self.fig.tight_layout()
        except ValueError:
            pass
        self.draw()

    def _draw_annotations(self, ax, axis_index, settings):
        """
        settings['annotations'] (テキスト注釈・矢印注釈のリスト) を描画する。
        再描画のたびに、まず前回このAxesに描画した注釈Artistを削除してから
        描き直すことで、update_appearance_only 経由での重複描画を防ぐ。
        """
        for artist in self._annotation_artists.get(axis_index, []):
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass

        new_artists = []
        for ann in settings.get('annotations', []):
            color = self._effective_text_color(ann.get('color', '#000000'))
            text = ann.get('text', '')
            try:
                if ann.get('type') == 'arrow':
                    artist = ax.annotate(
                        text, xy=ann['xy'], xytext=ann['xytext'],
                        arrowprops=dict(arrowstyle='->', color=color),
                        color=color, fontsize=9
                    )
                else:
                    xy = ann.get('xy', (0, 0))
                    artist = ax.text(xy[0], xy[1], text, color=color, fontsize=9)
                new_artists.append(artist)
            except Exception:
                logger.exception("注釈の描画に失敗しました: %s", ann)
        self._annotation_artists[axis_index] = new_artists

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

    def _draw_data(self, ax, axis_index, datasets):
        """指定された軸にデータをプロットする"""
        datasets_for_this_axis = [ds for ds in datasets if ds.subplot_target == axis_index]
        needs_secondary = any(ds.use_secondary_y for ds in datasets_for_this_axis)

        # このプロット(軸)のX軸が日時データかどうかを判定し、目盛りフォーマットの
        # 自動選択(_apply_appearance側)に使えるよう保持しておく。
        # 1つでも日時列を使っているデータセットがあれば、その軸は日付軸として扱う。
        is_date_x = any(
            pd.api.types.is_datetime64_any_dtype(ds.df[ds.x_col_name])
            for ds in datasets_for_this_axis
        )
        while len(self.axis_is_date_x) <= axis_index:
            self.axis_is_date_x.append(False)
        self.axis_is_date_x[axis_index] = is_date_x

        # このプロット(軸)のX軸が文字列カテゴリかどうかを判定する。
        # (日時型は上のis_date_xで既に扱っているため、それ以外の非数値型のみを対象とする)
        is_category_x = (not is_date_x) and any(
            not pd.api.types.is_numeric_dtype(ds.df[ds.x_col_name])
            for ds in datasets_for_this_axis
        )
        while len(self.axis_is_category_x) <= axis_index:
            self.axis_is_category_x.append(False)
        self.axis_is_category_x[axis_index] = is_category_x

        secondary_ax = None
        if needs_secondary:
            secondary_ax = ax.twinx()
            self.all_secondary_axes[axis_index] = secondary_ax

        for ds in datasets_for_this_axis:
            target_ax = secondary_ax if ds.use_secondary_y else ax
            if target_ax is None: continue

            # ★ 平滑化(CubicSpline)は数値のX軸でのみ意味を持つ/計算可能なため、
            # 文字列カテゴリ軸の場合はスキップして通常のプロット経路に進む。
            if ds.smoothing and len(ds.x_data) > 1 and not is_category_x:
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
                elif ds.plot_type == 'Area':
                    # 塗りつぶし(エリア)プロット: 0を基準線としてY値との間を塗りつぶす。
                    # 輪郭を分かりやすくするため、上端に細い線も重ねて描画する。
                    artist = target_ax.fill_between(ds.x_data, ds.y_data, 0, color=ds.color, alpha=ds.alpha * 0.4, label=ds.name)
                    target_ax.plot(ds.x_data, ds.y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha)
                    ds.artist = artist
                elif ds.plot_type == 'Bar':
                    # 棒グラフ: 文字列カテゴリ軸(項目31)との組み合わせを主な用途として想定。
                    artist = target_ax.bar(ds.x_data, ds.y_data, color=ds.color, alpha=ds.alpha, label=ds.name)
                    ds.artist = artist

            # ★ グラフ要素の直接クリック選択(項目35)のため、常にクリック検出を有効にする。
            # (データカーソルモードの ON/OFF とは独立。データカーソル自体のpick_event処理は
            #  cursor_mixin._on_pick 側で cursor_mode_enabled を見て有効/無効を判断している)
            if ds.artist is not None:
                self._enable_element_picking(ds.artist)

            # ★ エラーバー (X/Y誤差列が設定されている場合のみ描画)
            # fmt='none' なので線やマーカーは追加せず、誤差の縦横棒のみを
            # 元データ点 (平滑化前) の位置に重ねて描画する。
            if ds.x_err_col_name or ds.y_err_col_name:
                target_ax.errorbar(
                    ds.x_data, ds.y_data,
                    xerr=ds.x_err_data, yerr=ds.y_err_data,
                    fmt='none', ecolor=ds.color, elinewidth=ds.linewidth, alpha=ds.alpha, capsize=3
                )

            # ★ データポイントラベル (各点の脇にY値、または指定列の値を表示)
            # 平滑化が有効な場合でも、ラベルは元のデータ点の位置に表示する。
            if ds.show_point_labels:
                self._draw_point_labels(target_ax, ds)

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
        artist = ax.scatter(
            x_vals, y_vals, s=160, facecolors='none', edgecolors='#e6194b',
            linewidths=2.0, zorder=15
        )
        self._highlight_artists[dataset.dataset_id] = artist
        self.draw_idle()

    def _draw_point_labels(self, ax, ds):
        """
        データセットの各点の脇に、Y値または指定列の値をテキストとして表示する。
        point_label_col_name が None ならY値そのもの、指定されていればその列の値を使う。
        """
        if ds.point_label_col_name and ds.point_label_col_name in ds.df.columns:
            # ★ x_data/y_dataはvisible_df(マスクされた行を除いたもの)基準のため、
            # 同じ行と対応させるにはこちらもvisible_dfから取得する必要がある。
            label_values = ds.visible_df[ds.point_label_col_name].values
        else:
            label_values = ds.y_data

        for x, y, label_value in zip(ds.x_data, ds.y_data, label_values):
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
                fontsize=8, color=ds.color, alpha=ds.alpha
            )

    def _apply_appearance(self, ax, axis_index, settings):
        """指定された軸に外観設定を適用する"""
        secondary_ax = self.all_secondary_axes[axis_index]

        ax.set_facecolor(DARK_AXES_FACECOLOR if self.dark_mode else LIGHT_AXES_FACECOLOR)

        is_date_x = axis_index < len(self.axis_is_date_x) and self.axis_is_date_x[axis_index]
        # 文字列カテゴリ軸: X最小/最大・対数スケールなど数値専用の設定は意味を持たない
        # (指定してもmatplotlibのカテゴリ位置と噛み合わず表示が壊れる)ため無視する。
        is_category_x = axis_index < len(self.axis_is_category_x) and self.axis_is_category_x[axis_index]

        if is_category_x or settings.get('x_autoscale', True): ax.autoscale(enable=True, axis='x', tight=True)
        else:
            min_val, max_val = settings.get('x_min', 0), settings.get('x_max', 1)
            if min_val < max_val: ax.set_xlim(min_val, max_val)

        if settings.get('y_autoscale', True): ax.autoscale(enable=True, axis='y', tight=True)
        else:
            min_val, max_val = settings.get('y_min', 0), settings.get('y_max', 1)
            if min_val < max_val: ax.set_ylim(min_val, max_val)

        if not is_category_x:
            # ★ 注意: ax.set_xscale() は、たとえ同じ'linear'を指定し直すだけでも
            # matplotlib内部でその軸のLocator/Formatterをスケールの既定値に
            # リセットしてしまう。文字列カテゴリ軸ではbar()/plot()呼び出し時に
            # matplotlib自身が設定したカテゴリ用のLocator/Formatterを保ちたいため、
            # このAxesでは(スケール自体はどのみち常にlinearなので)呼び出さない。
            ax.set_xscale('log' if settings.get('x_log', False) else 'linear')
        ax.xaxis.set_inverted(settings.get('x_invert', False))
        ax.set_yscale('log' if settings.get('y_log', False) else 'linear')
        ax.yaxis.set_inverted(settings.get('y_invert', False))

        x_min_lim, x_max_lim = ax.get_xlim()
        y_min_lim, y_max_lim = ax.get_ylim()

        if is_date_x:
            # 日時データのX軸: 軸範囲に応じて年/月/日/時刻など適切な間隔・表示形式を
            # 自動選択する (手動間隔指定のUI設定はここでは意味を持たないため無視する)。
            date_locator = mdates.AutoDateLocator()
            ax.xaxis.set_major_locator(date_locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(date_locator))
        elif is_category_x:
            # matplotlibがプロット時に自動設定したカテゴリ用のLocator/Formatter
            # (各カテゴリ位置に1つずつラベルを表示) をそのまま使う。数値軸向けの
            # AutoLocator等で上書きすると目盛りラベルが崩れるため触らない。
            pass
        elif settings.get('x_major_tick_mode', 0) == 0: ax.xaxis.set_major_locator(ticker.AutoLocator())
        else:
            interval = settings.get('x_major_tick_interval', 1)
            if interval > 0: ax.xaxis.set_major_locator(_safe_multiple_locator(interval, x_min_lim, x_max_lim))

        if settings.get('y_major_tick_mode', 0) == 0: ax.yaxis.set_major_locator(ticker.AutoLocator())
        else:
            interval = settings.get('y_major_tick_interval', 1)
            if interval > 0: ax.yaxis.set_major_locator(_safe_multiple_locator(interval, y_min_lim, y_max_lim))

        if is_date_x or is_category_x:
            # 日付軸/カテゴリ軸では数値の補助目盛り間隔は意味を持たないため表示しない
            ax.xaxis.set_minor_locator(ticker.NullLocator())
        elif settings.get('x_minor_ticks_visible', False):
            interval = settings.get('x_minor_tick_interval', 0.5)
            if interval > 0: ax.xaxis.set_minor_locator(_safe_multiple_locator(interval, x_min_lim, x_max_lim))
        else: ax.xaxis.set_minor_locator(ticker.NullLocator())

        if settings.get('y_minor_ticks_visible', False):
            interval = settings.get('y_minor_tick_interval', 0.5)
            if interval > 0: ax.yaxis.set_minor_locator(_safe_multiple_locator(interval, y_min_lim, y_max_lim))
        else: ax.yaxis.set_minor_locator(ticker.NullLocator())

        # 目盛りの指数表記フォーマット切り替え(項目62)。日付軸/カテゴリ軸は
        # 専用のFormatterを既に設定済みのため、数値軸のX軸(および常に数値のY軸)のみ適用する。
        if not is_date_x and not is_category_x:
            _apply_tick_format_mode(ax.xaxis, settings.get('x_tick_format_mode', 0))
        _apply_tick_format_mode(ax.yaxis, settings.get('y_tick_format_mode', 0))

        tick_font_dict = settings.get('tick_font', {})
        label_font_dict = settings.get('axis_label_font', {})
        tick_color = self._effective_text_color(settings.get('tick_color', '#000000'))
        label_color = self._effective_text_color(settings.get('axis_label_color', '#000000'))

        ax.set_title(settings.get('title', ''), **label_font_dict, color=label_color)
        ax.set_xlabel(settings.get('x_label', ''), **label_font_dict, color=label_color)
        ax.set_ylabel(settings.get('y_label', ''), **label_font_dict, color=label_color)
        # ★ グラフ要素の直接クリック選択(項目35): タイトルをクリックすると、
        # そのサブプロットを「編集対象のプロット」に切り替えられるようにする。
        ax.title.set_picker(5)

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
                # 凡例の並び順(ドラッグで並べ替え可能): 描画順とは独立に指定できる
                legend_order = settings.get('legend_order')
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
                    # 凡例のダーク/ライトモード対応スタイリング(項目71):
                    # 既定のまま(白背景固定)だとダークモードで浮いて見えるため、
                    # 軸背景と調和する面色・枠線色に合わせる。
                    frame = legend_obj.get_frame()
                    if self.dark_mode:
                        frame.set_facecolor(DARK_LEGEND_FACECOLOR)
                        frame.set_edgecolor(DARK_LEGEND_EDGECOLOR)
                    else:
                        frame.set_facecolor(LIGHT_LEGEND_FACECOLOR)
                        frame.set_edgecolor(LIGHT_LEGEND_EDGECOLOR)
                    frame.set_alpha(0.92)
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