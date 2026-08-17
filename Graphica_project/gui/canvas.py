import logging
import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Polygon
import matplotlib.ticker as ticker
import matplotlib.dates as mdates

from gui.theme import LIGHT_TOKENS, DARK_TOKENS
from core.analysis import calculate_lttb_downsample
from core.unit_conversion import convert_x_axis_unit, X_AXIS_UNIT_NONE, X_AXIS_UNIT_LABELS

logger = logging.getLogger(__name__)

# 目盛り間隔が細かすぎて描画が固まる/処理落ちするのを防ぐための上限。
# (軸範囲 / 間隔) がこれを超える場合は、間隔を自動的に粗くする。
# ★ matplotlib 自体が Locator.MAXTICKS=1000 を超えると警告を出すため、
#   境界の丸め誤差でそこに接触しないよう、余裕を持たせた値にしている。
MAX_TICKS_PER_AXIS = 500

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


# --- ダーク/ライトモード用の配色(項目H-3) ---
# ★ 以前はここに個別のハードコード値(例: '#2b2b2b')を持っており、
#   gui/theme.py のデザイントークンとは完全に無関係だった(H-0調査で判明した
#   既知の不整合、docs/gui_style_audit.md 3節参照)。値が近いだけで一致しては
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
        # 唯一の入口であるため、ここ1箇所でのフィルタが両方に自動的に効く。
        # getattr既定値Trueは、この機能追加前に保存された.pklファイル由来の
        # Datasetオブジェクト(pickleの__setstate__で補われるはずだが、念のための保険)
        # でも安全に動くようにするため。
        datasets = [ds for ds in datasets if getattr(ds, 'visible', True)]
        self.fig.clf()
        self.all_axes.clear()
        self.all_secondary_axes.clear()
        self.axis_is_date_x.clear()
        self.axis_is_category_x.clear()
        # fig.clf() で古いAxes(とその子Artist)はすべて破棄されるため、
        # 個別にremove()するまでもなく古い注釈Artist/ハイライトArtistの参照も無効になる
        self._annotation_artists.clear()
        self._highlight_artists.clear()
        self.downsample_index_map.clear()
        self._non_pickable_dataset_ids.clear()
        self._axis_2d_mappables.clear()
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
                self._apply_shared_axis_tick_visibility(i, rows, cols, share_x_axis, share_y_axis)

        for index, ax in enumerate(self.all_axes):
            if index < len(all_plot_settings):
                settings = all_plot_settings[index]
            else:
                continue

            # データの描画
            self._draw_data(ax, index, datasets, full_resolution=full_resolution)
            # 外観の適用
            self._apply_appearance(ax, index, settings)
            # 自由なテキスト注釈・矢印の描画
            self._draw_annotations(ax, index, settings)
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
        for dataset_id in [ds.dataset_id for ds in datasets if ds.subplot_target == axis_index]:
            self._highlight_artists.pop(dataset_id, None)
            self.downsample_index_map.pop(dataset_id, None)
            self._non_pickable_dataset_ids.discard(dataset_id)

        visible_datasets = [ds for ds in datasets if getattr(ds, 'visible', True)]
        self._draw_data(ax, axis_index, visible_datasets, full_resolution=full_resolution)
        self._apply_appearance(ax, axis_index, settings)
        self._draw_annotations(ax, axis_index, settings)
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
        rect = settings.get('free_rect') or self._default_free_rect(len(self.all_axes))
        ax = self.fig.add_axes(rect)
        self.all_axes.append(ax)
        self.all_secondary_axes.append(None)
        self.axis_is_date_x.append(False)
        self.axis_is_category_x.append(False)

        axis_index = len(self.all_axes) - 1
        visible_datasets = [ds for ds in datasets if getattr(ds, 'visible', True)]
        self._draw_data(ax, axis_index, visible_datasets)
        self._apply_appearance(ax, axis_index, settings)
        self._draw_annotations(ax, axis_index, settings)
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

        for index, ax in enumerate(self.all_axes):
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
            except ValueError:
                pass

        self.draw()
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
        指定された軸にデータをプロットする。
        full_resolution=True の場合、LTTB表示用ダウンサンプリング(項目C-1001)を
        無視して常に全点描画する(エクスポート時の「フル解像度」オプション用)。
        """
        all_datasets_for_this_axis = [ds for ds in datasets if ds.subplot_target == axis_index]

        # 2Dマップ(項目C-508)は、以下の1D点列前提のロジック(日付/カテゴリ軸判定・
        # ウォーターフォール・LTTBダウンサンプリング・平滑化・plot_type分岐)を
        # 一切経由しない別経路で描画する(x_data/y_dataは長形式の生の列であり、
        # 1D描画にそのまま使うと無意味なため)。ヒートマップは背景として先に描き、
        # 同じ軸に1Dデータ(例: 将来のC-511スライス線)が重なっても見えるようにする。
        datasets_2d = [ds for ds in all_datasets_for_this_axis if ds.data_kind == '2d_grid']
        datasets_for_this_axis = [ds for ds in all_datasets_for_this_axis if ds.data_kind != '2d_grid']
        self._draw_2d_data(ax, axis_index, datasets_2d, full_resolution=full_resolution)

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

        # ウォーターフォールプロット(項目80、項目109で独立したプロット種別から
        # 「積み重ねオプション」に変更): このサブプロット上で waterfall_enabled な
        # データセットだけを対象に、リスト順(datasets_for_this_axisの並び順、
        # waterfall_enabledでないものとは混ぜない)で0始まりの「積み重ねインデックス」を
        # 振る。plot_typeとは独立したフラグなので、Line/Scatter/Line+Scatter/Area/Bar
        # のどの見た目とも組み合わせられる。背景色の塗りつぶしで奥のトレースを隠す
        # (occlusion)ためのベースライン(全ウォーターフォールトレースのY最小値から
        # わずかに余白を取った値)も、ここでまとめて計算しておく。
        waterfall_datasets = [ds for ds in datasets_for_this_axis if ds.waterfall_enabled]
        waterfall_index = {ds.dataset_id: i for i, ds in enumerate(waterfall_datasets)}
        waterfall_count = len(waterfall_datasets)
        waterfall_baseline = 0.0
        if waterfall_count:
            shifted_mins, shifted_maxs = [], []
            for i, wds in enumerate(waterfall_datasets):
                if len(wds.y_data) == 0:
                    continue
                y_shift = i * wds.waterfall_offset_y
                shifted_mins.append(float(np.nanmin(wds.y_data)) + y_shift)
                shifted_maxs.append(float(np.nanmax(wds.y_data)) + y_shift)
            if shifted_mins:
                y_min_all, y_max_all = min(shifted_mins), max(shifted_maxs)
                margin = (y_max_all - y_min_all) * 0.05 if y_max_all > y_min_all else 1.0
                waterfall_baseline = y_min_all - margin

        for ds in datasets_for_this_axis:
            target_ax = secondary_ax if ds.use_secondary_y else ax
            if target_ax is None: continue

            # ウォーターフォール(項目80/109): 有効な場合、以降の描画処理は全て
            # 積み重ねインデックス分だけずらしたX/Yを使う。plot_type別のスタイル
            # (線種・マーカー・塗り等)は各分岐でそのまま個別に選べる。
            # ★ 文字列カテゴリX軸(is_category_x)の場合、ds.x_dataは文字列の
            #   object配列のため数値オフセットを加算するとTypeErrorになる。
            #   Xオフセットは意味を持たない(カテゴリの「ずらし」に相当する演算が
            #   無い)ためスキップし、Yオフセットのみ適用する(同じX位置での
            #   縦方向の積み重ね表示として引き続き使える)。
            waterfall_zorder = None
            plot_kwargs = {}
            if ds.waterfall_enabled:
                w_idx = waterfall_index.get(ds.dataset_id, 0)
                plot_x_data = ds.x_data if is_category_x else ds.x_data + w_idx * ds.waterfall_offset_x
                plot_y_data = ds.y_data + w_idx * ds.waterfall_offset_y
                # 手前(インデックスが小さい)ほど大きいzorderにし、後ろのトレースの
                # 上に重なって描画されるようにする。
                waterfall_zorder = (waterfall_count - w_idx) * 2
                plot_kwargs['zorder'] = waterfall_zorder
            else:
                plot_x_data = ds.x_data
                plot_y_data = ds.y_data

            # 表示用ダウンサンプリング(LTTB、項目C-1001): Lineのみ、かつ点数が
            # 閾値を超える場合のみ、LTTBで代表点を間引いて描画負荷を下げる
            # (Scatter/Line+Scatterはマーカーの疎密自体が情報のため対象外、
            # Bar/Areaは1本ごと/塗り形状の意味が変わるため対象外)。
            # full_resolution=True(エクスポート時の「フル解像度」オプション)が
            # 指定された場合は、点数によらず常に全点描画する。
            # LTTBはXが昇順であることを前提とするアルゴリズムのため、既に昇順の
            # データにのみ適用する(降順/非単調なXはまれなケースとして対象外にし、
            # 従来通り全点描画する — 誤って形状を変えてしまうより安全側に倒す)。
            downsample_indices = None
            if (
                ds.plot_type == 'Line'
                and not full_resolution
                and not is_category_x
                and len(plot_x_data) > LTTB_DOWNSAMPLE_THRESHOLD
                and np.all(np.diff(plot_x_data) >= 0)
            ):
                downsample_indices = calculate_lttb_downsample(
                    plot_x_data, plot_y_data, LTTB_DOWNSAMPLE_TARGET_POINTS
                )
                if len(downsample_indices) < len(plot_x_data):
                    # データカーソル(cursor_mixin.py)が、クリック点のインデックス
                    # (間引き後の配列上)を元のvisible_df上の位置へ変換するために使う。
                    self.downsample_index_map[ds.dataset_id] = downsample_indices
                    plot_x_data = plot_x_data[downsample_indices]
                    plot_y_data = plot_y_data[downsample_indices]
                else:
                    downsample_indices = None

            # ★ 平滑化(CubicSpline)は「線で結んだ曲線」を滑らかにする機能のため、
            # Line/Line+Scatterでのみ意味を持つ。Scatter/Bar/Areaに適用すると、
            # 平滑化した線がマーカー/棒/塗りつぶしを完全に置き換えてしまい
            # (Line+Scatter以外は元データ点を重ね描きする分岐が無いため)、
            # ユーザーが選んだ見た目が丸ごと消えてしまう実害があった(過去の
            # 見落とし)。UIの平滑化チェックボックスも同じ条件で非表示にする
            # (dataset_mixin.pyの_update_smoothing_control_visibility参照、
            # グラデーション機能と同じ「表示制御はUI側、描画側も独立して
            # 適用条件を再チェックする」の二重ガード方針)。数値のX軸でのみ
            # 意味を持つ/計算可能なため、文字列カテゴリ軸の場合もスキップする。
            # ★ データカーソル(cursor_mixin.py)は「artist上のインデックス」を
            #   そのままds.visible_dfの行番号として解釈するため、平滑化された
            #   曲線(元データと1:1に対応しない200点のCubicSpline補間点)を
            #   クリック可能にすると、無関係な行を選択する/範囲外で無反応になる
            #   (過去の見落とし)。CubicSplineが成功して実際に平滑化曲線を
            #   描いた場合のみTrueにし、下のpicker登録箇所でクリック検出を
            #   スキップする(ValueErrorフォールバック時は元データ点のままの
            #   線を描くため、通常通りクリック可能にしてよい)。
            is_smoothed_artist = False
            if (
                ds.smoothing
                and ds.plot_type in ('Line', 'Line+Scatter')
                and len(plot_x_data) > 1
                and not is_category_x
            ):
                sort_indices = np.argsort(plot_x_data)
                x_sorted = plot_x_data[sort_indices]
                y_sorted = plot_y_data[sort_indices]
                # ★ グラデーション(項目79)は平滑化された曲線にも適用できるよう、
                # 平滑化後のx_smooth/y_smoothに対してLineCollectionを作る。
                use_line_gradient = ds.gradient_enabled and ds.gradient_target in ('line', 'both')
                try:
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
                    is_smoothed_artist = True
                    if ds.plot_type == 'Line+Scatter':
                        target_ax.scatter(plot_x_data, plot_y_data, color=ds.color, marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha, **plot_kwargs)
                except ValueError:
                    if use_line_gradient:
                        ds.artist = self._add_gradient_line(
                            target_ax, plot_x_data, plot_y_data, ds.color, ds.gradient_color2,
                            ds.linewidth, ds.alpha, ds.linestyle, label=ds.name
                        )
                    else:
                        (artist,) = target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                        ds.artist = artist
            else:
                # ★ 線ストロークグラデーション(項目79)は 'line'/'both' が
                # 選ばれているときのみ、'Line'/'Line+Scatter' で有効になる。
                use_line_gradient = ds.gradient_enabled and ds.gradient_target in ('line', 'both')
                if ds.plot_type == 'Line':
                    if use_line_gradient:
                        ds.artist = self._add_gradient_line(
                            target_ax, plot_x_data, plot_y_data, ds.color, ds.gradient_color2,
                            ds.linewidth, ds.alpha, ds.linestyle, label=ds.name
                        )
                    else:
                        (artist,) = target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                        ds.artist = artist
                elif ds.plot_type == 'Scatter':
                    artist = target_ax.scatter(plot_x_data, plot_y_data, color=ds.color, marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                    ds.artist = artist
                elif ds.plot_type == 'Line+Scatter':
                    if use_line_gradient:
                        # LineCollectionはマーカーを描けないため、線はグラデーション、
                        # マーカーは別途ds.colorの単色scatterとして重ねて描画する。
                        ds.artist = self._add_gradient_line(
                            target_ax, plot_x_data, plot_y_data, ds.color, ds.gradient_color2,
                            ds.linewidth, ds.alpha, ds.linestyle, label=ds.name
                        )
                        target_ax.scatter(plot_x_data, plot_y_data, color=ds.color, marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha, **plot_kwargs)
                    else:
                        (artist,) = target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, marker=ds.marker, markersize=ds.markersize, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                        ds.artist = artist
                elif ds.plot_type == 'Area':
                    # 塗りつぶし(エリア)プロット: 0を基準線としてY値との間を塗りつぶす。
                    # 輪郭を分かりやすくするため、上端に細い線も重ねて描画する。
                    # ★ グラデーション無効時は従来どおりの描画(回帰防止のため分岐を変えない)。
                    if not ds.gradient_enabled:
                        artist = target_ax.fill_between(plot_x_data, plot_y_data, 0, color=ds.color, alpha=ds.alpha * 0.4, label=ds.name, **plot_kwargs)
                        target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, **plot_kwargs)
                        ds.artist = artist
                    else:
                        use_fill_gradient = ds.gradient_target in ('fill', 'both')
                        use_area_line_gradient = ds.gradient_target in ('line', 'both')
                        if use_fill_gradient:
                            artist = self._add_gradient_fill(target_ax, plot_x_data, plot_y_data, ds.color, ds.gradient_color2, ds.alpha * 0.4)
                        else:
                            artist = target_ax.fill_between(plot_x_data, plot_y_data, 0, color=ds.color, alpha=ds.alpha * 0.4, **plot_kwargs)

                        if use_area_line_gradient:
                            self._add_gradient_line(
                                target_ax, plot_x_data, plot_y_data, ds.color, ds.gradient_color2,
                                ds.linewidth, ds.alpha, ds.linestyle, label=ds.name
                            )
                        else:
                            target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                        ds.artist = artist
                elif ds.plot_type == 'Bar':
                    # 棒グラフ: 文字列カテゴリ軸(項目31)との組み合わせを主な用途として想定。
                    artist = target_ax.bar(plot_x_data, plot_y_data, color=ds.color, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                    ds.artist = artist
                else:
                    # 項目D-2: register_plot_type()でプラグインが追加した未知のplot_type。
                    # 既存5種類の分岐は変更しない増分実装(ウォーターフォール等の追加
                    # オーバーレイはプラグイン描画には自動適用されない、既知の制限)。
                    from core.plugin_api import get_plugin_api
                    api = get_plugin_api()
                    plugin_plot_type = api.get_plot_type(ds.plot_type) if api is not None else None
                    if plugin_plot_type is not None:
                        try:
                            artist = plugin_plot_type.drawer(ds, target_ax, plot_x_data, plot_y_data)
                            if artist is not None:
                                ds.artist = artist
                        except Exception as e:
                            logger.warning(
                                "[plugin:%s] plot_type '%s' の描画に失敗しました: %s",
                                plugin_plot_type.plugin_name, ds.plot_type, e,
                            )
                    else:
                        logger.warning("未知のplot_type '%s' です。Lineとして描画します。", ds.plot_type)
                        (artist,) = target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
                        ds.artist = artist

            # ウォーターフォール(項目80/109): 手前のトレースが奥のトレースを隠すよう、
            # 描画したアーティストの下(waterfall_zorder - 1)に軸背景色のfill_betweenを
            # 敷く(occlusion)。Areaは自身の塗りつぶしと二重になり見た目が煩雑になる
            # ため対象外とする。plot_type分岐の後にまとめて行うことで、どの見た目
            # (Line/Scatter/Line+Scatter/Bar)と組み合わせても同じ処理で済む。
            if ds.waterfall_enabled and ds.plot_type != 'Area' and len(plot_x_data) > 0:
                bg_color = DARK_AXES_FACECOLOR if self.dark_mode else LIGHT_AXES_FACECOLOR
                target_ax.fill_between(
                    plot_x_data, plot_y_data, waterfall_baseline,
                    color=bg_color, alpha=1.0, zorder=waterfall_zorder - 1, linewidth=0,
                )

            # ★ グラフ要素の直接クリック選択(項目35)のため、常にクリック検出を有効にする。
            # (データカーソルモードの ON/OFF とは独立。データカーソル自体のpick_event処理は
            #  cursor_mixin._on_pick 側で cursor_mode_enabled を見て有効/無効を判断している)
            # 平滑化曲線(is_smoothed_artist)は元データと1:1に対応しないため、
            # クリック検出自体を無効のままにする(上記コメント参照)。_non_pickable_dataset_ids
            # にも登録/除外し、cursor_mixin.pyの「データカーソルモード」ON操作(軸内の全
            # Line2D/PathCollectionへ一括でset_picker(5)する別経路)からもこの
            # データセットが除外されるようにする(ここでの判定だけでは、モードON操作で
            # picker が再度有効化されてしまう)。平滑化がOFFに戻された場合に備え、
            # 該当しない場合は明示的にdiscardして古い状態を残さない。
            if is_smoothed_artist:
                self._non_pickable_dataset_ids.add(ds.dataset_id)
            else:
                self._non_pickable_dataset_ids.discard(ds.dataset_id)
            if ds.artist is not None and not is_smoothed_artist:
                self._enable_element_picking(ds.artist)

            # ★ 誤差の表示(X/Y誤差列が設定されている場合のみ描画、項目C-502で
            # 表示形式を選べるようにした)。fmt='none' なので線やマーカーは追加せず、
            # 誤差の縦横棒のみを元データ点(平滑化前、ウォーターフォール有効時は
            # ずらした後)の位置に重ねて描画する。
            if ds.x_err_col_name or ds.y_err_col_name:
                # 項目C-1001: plot_x_data/plot_y_dataがダウンサンプリング済みの
                # 場合、誤差列(ds.x_err_data/ds.y_err_data、常に元データと同じ
                # フルサイズ)もplot_x_data/plot_y_dataと同じ点数に揃える必要がある
                # (揃えないとmatplotlib.errorbar/fill_betweenが長さ不一致で例外になる)。
                # downsample_indicesはplot_x_data/plot_y_dataを間引いたのと同じ
                # インデックス列なので、そのまま使い回せる。
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
                # 誤差バンド(fill_between): X誤差には対応せず、Y誤差の帯のみ描画する
                # (2軸方向の帯は一般的でないため)。
                if ds.error_display in ('band', 'both') and y_err_full is not None:
                    y_arr = np.asarray(plot_y_data)
                    y_err = np.asarray(y_err_full)
                    target_ax.fill_between(
                        plot_x_data, y_arr - y_err, y_arr + y_err,
                        color=ds.color, alpha=ds.alpha * 0.25, linewidth=0,
                    )

            # ★ 曲線フィットの信頼帯・予測帯(項目C-405): gui/mixins/dataset_mixin.py
            # の_on_fit_curve/_on_batch_curve_fitがband_typeを選ばれた場合にのみ
            # dfへ'y_lower'/'y_upper'列を追加しているため、その存在で描画有無を判断する
            # (fit_band_displayはUI上の意図/ラベル用、実際に描画できるかは列の有無で決まる)。
            if ds.fit_band_display and 'y_lower' in ds.df.columns and 'y_upper' in ds.df.columns:
                band_df = ds.visible_df
                target_ax.fill_between(
                    band_df[ds.x_col_name], band_df['y_lower'], band_df['y_upper'],
                    color=ds.color, alpha=ds.alpha * 0.15, linewidth=0,
                )

            # ★ データポイントラベル (各点の脇にY値、または指定列の値を表示)
            # 平滑化が有効な場合でも、ラベルは元のデータ点の位置に表示する
            # (ウォーターフォール有効時はずらした後の位置)。
            # 点数が point_label_max_points を超える場合は、フリーズ防止のため描画しない
            # (ダイアログ側で有効化時に確認ポップアップを出しているが、これは別プロジェクトの
            #  読み込みなど確認を経ないケースも含めて描画時にも必ず効くようにするための保険)。
            # ★ point_label_max_points はLTTB_DOWNSAMPLE_THRESHOLD(20,000)より大きい値に
            #   環境設定で変更できるため、その場合はLTTB間引き済みのplot_x_data/plot_y_data
            #   (間引き後の点数)とラベル値(常にvisible_df基準のフルサイズ)の長さが
            #   ズレ、zip()が短い方に合わせて打ち切られた結果「間引き後のi番目の点」に
            #   「元データi番目の行のラベル値」という無関係な組み合わせが表示される
            #   実害があった(過去の見落とし)。誤差バンド/バーと同じdownsample_indices
            #   を渡してラベル値側も同じ並びに揃える。
            if ds.show_point_labels and len(ds.visible_df) <= self.point_label_max_points:
                self._draw_point_labels(
                    target_ax, ds, x_data=plot_x_data, y_data=plot_y_data,
                    downsample_indices=downsample_indices,
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

        # グリッド線の詳細カスタマイズ(項目82): X軸/Y軸・主目盛/補助目盛をそれぞれ
        # 独立した線種(linestyle)・太さ(linewidth)・透過度(alpha)で描画できるようにする。
        # settings に該当キーが無い場合(この機能追加前に保存されたプロジェクト等)は、
        # 従来の固定値(主目盛: 実線・太さ0.8 / 補助目盛: 破線・太さ0.5、共にalpha=1.0)を
        # そのままデフォルトとして使い、既存プロジェクトの見た目を変えない。
        # 1回の ax.grid() 呼び出しは指定した which/axis の組み合わせにしか効かないため、
        # X/Y × 主/補助 の4通りを個別に呼び分ける。
        if settings.get('grid_visible', False):
            # ★ 項目H-3: グリッド線の色は以前matplotlibの既定値(rcParams、
            #   テーマと無関係な固定の薄灰色)に任せきりだったため、
            #   ダークモードでライトモードと同じ薄灰色が使われ、背景色との
            #   調和が取れていなかった。border_strongトークンを明示的に指定する。
            grid_color = DARK_GRID_COLOR if self.dark_mode else LIGHT_GRID_COLOR
            for grid_axis in ('x', 'y'):
                ax.grid(
                    True, which='major', axis=grid_axis,
                    linestyle=settings.get(f'{grid_axis}_major_grid_linestyle', '-'),
                    linewidth=settings.get(f'{grid_axis}_major_grid_width', 0.8),
                    alpha=settings.get(f'{grid_axis}_major_grid_alpha', 1.0),
                    color=grid_color,
                )
                if settings.get('minor_grid_visible', False):
                    ax.grid(
                        True, which='minor', axis=grid_axis,
                        linestyle=settings.get(f'{grid_axis}_minor_grid_linestyle', '--'),
                        linewidth=settings.get(f'{grid_axis}_minor_grid_width', 0.5),
                        alpha=settings.get(f'{grid_axis}_minor_grid_alpha', 1.0),
                        color=grid_color,
                    )
                else:
                    ax.grid(False, which='minor', axis=grid_axis)
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

        # 単位変換の第2X軸(項目C-602): X軸データの単位と第2X軸に表示したい単位が
        # 共に「なし」以外かつ異なる場合のみ、matplotlibのsecondary_xaxis
        # (functions=(forward, inverse))で上部に変換後の第2X軸を追加する。
        # 日付軸/カテゴリ軸は数値変換の対象外(nm/eV/cm^-1/Hzという物理量の
        # 変換とは無関係)なので何もしない。
        source_unit = settings.get('x_secondary_axis_source_unit', X_AXIS_UNIT_NONE)
        target_unit = settings.get('x_secondary_axis_target_unit', X_AXIS_UNIT_NONE)
        if (not is_date_x and not is_category_x
                and source_unit != X_AXIS_UNIT_NONE and target_unit != X_AXIS_UNIT_NONE
                and source_unit != target_unit
                and np.all(np.isfinite(convert_x_axis_unit(np.array(ax.get_xlim()), source_unit, target_unit)))):
            # ★ X軸範囲の端(0を含む等)がnm<->eV/cm^-1/Hz変換で inf/nan になる
            #   (波長0nmは物理的に無意味)場合、ax.secondary_xaxis()が
            #   「Axis limits cannot be NaN or Inf」で例外を投げグラフ全体の
            #   再描画が失敗する。上のisfinite判定でその組み合わせの時だけ
            #   第2X軸自体を追加しないことで、メインの描画には影響させない。
            def _forward(x, _from=source_unit, _to=target_unit):
                return convert_x_axis_unit(x, _from, _to)

            def _inverse(x, _from=source_unit, _to=target_unit):
                return convert_x_axis_unit(x, _to, _from)

            secondary_x_ax = ax.secondary_xaxis('top', functions=(_forward, _inverse))
            secondary_x_ax.set_xlabel(X_AXIS_UNIT_LABELS.get(target_unit, target_unit),
                                       **label_font_dict, color=label_color)
            for label in secondary_x_ax.get_xticklabels():
                label.set(**tick_font_dict)
                label.set_color(tick_color)
            secondary_x_ax.tick_params(axis='x', which='major', width=tick_width,
                                        color=spine_color, labelcolor=tick_color, direction=major_dir)
            secondary_x_ax.spines['top'].set_linewidth(spine_width)
            secondary_x_ax.spines['top'].set_color(spine_color)

        # カラーバー(項目C-501): このAxesに2Dマップ(項目C-508)が描画されていた
        # 場合のみ意味を持つ。_draw_data()が_axis_2d_mappablesへ登録した
        # QuadMeshを対象に、fig.colorbar()で付ける。位置(location)を指定すると
        # matplotlibが向き(vertical/horizontal)を自動的に決めるため、orientationは
        # 明示的に渡さない(両方渡すと衝突しうる)。
        mappable = self._axis_2d_mappables.get(axis_index)
        if mappable is not None and settings.get('colorbar_enabled', True):
            position = settings.get('colorbar_position', 'right')
            if position not in ('right', 'left', 'top', 'bottom'):
                position = 'right'
            try:
                fraction = float(settings.get('colorbar_width_fraction', 0.05))
            except (TypeError, ValueError):
                fraction = 0.05
            if fraction <= 0:
                fraction = 0.05
            cbar = self.fig.colorbar(mappable, ax=ax, location=position, fraction=fraction, pad=0.04)
            colorbar_label = settings.get('colorbar_label', '')
            if colorbar_label:
                cbar.set_label(colorbar_label, **label_font_dict, color=label_color)
            for tick_label in cbar.ax.get_yticklabels() + cbar.ax.get_xticklabels():
                tick_label.set(**tick_font_dict)
                tick_label.set_color(tick_color)
            cbar.outline.set_edgecolor(spine_color)
            cbar.outline.set_linewidth(spine_width)


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