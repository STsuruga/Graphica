"""
gui/minimap_widget.py

項目83「レンジスライダー(ミニマップ)」: グラフ下部に表示する、全体像の
小さな概観(ミニマップ)。matplotlib.widgets.SpanSelector を使って、
ドラッグで選択した範囲を range_selected シグナルとして通知する。

★ 設計方針(main_window.py 側の実装コメントも参照):
  - メインの MplCanvas (gui/canvas.py) とは完全に別の、小さな独立した
    matplotlib Figure/Axes を持つ FigureCanvasQTAgg のサブクラスにする。
    メインキャンバスの redraw_all() は fig.clf() で Figure を作り直すが、
    このウィジェットは別インスタンスの Figure なので影響を受けない。
    ただし表示中のデータセットが変わった場合は refresh() を呼んで
    明示的に描き直す必要がある(呼び出し側の責務、main_window.py の
    _update_plot() 末尾から _refresh_minimap() 経由で呼ばれる)。
  - このウィジェット自身は「選択範囲を通知する」だけで、実際にメイン
    キャンバスへズーム範囲を適用する処理は持たない(疎結合にするため)。
    適用側は呼び出し元(main_window.py の _on_minimap_range_selected)。
"""
import logging

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PySide6.QtCore import Signal

logger = logging.getLogger(__name__)

# ミニマップの高さ(px)。「小さな概観」であることが一目でわかる程度に抑える。
MINIMAP_HEIGHT_PX = 70

# gui/canvas.py の配色定数と揃える(ダーク/ライト両テーマで浮かないように)
DARK_FIGURE_FACECOLOR = '#2b2b2b'
# ★ 実機フィードバック: 「ミニマップの灰色も他の所の背景と色のテイストを
#   そろえて、同じ色にはしないで少しだけ暗い色にして」。以前はフラットな
#   無彩色グレー(#f2f2f2 / #1e1e1e)で、gui/theme.pyのトークン(寒色寄りの
#   グレー、bg=#F6F7F9/surface_2=#EEF0F3、ダークはbg=#14171A/surface_2=
#   #21262A)と色味が揃っていなかった。同じ色相(寒色寄り、R<G<Bの傾向)を
#   保ちつつ、周囲のパネル背景そのものと同一にはせず、ミニマップが「一段
#   窪んだ」独立領域だと分かる程度にわずかに暗くしている。
DARK_AXES_FACECOLOR = '#0E1114'
DARK_LINE_COLOR = '#8ab4f8'
DARK_SPAN_COLOR = '#8ab4f8'
LIGHT_FIGURE_FACECOLOR = '#ffffff'
LIGHT_AXES_FACECOLOR = '#E3E6EB'
LIGHT_LINE_COLOR = '#1a73e8'
LIGHT_SPAN_COLOR = '#1a73e8'


class MinimapWidget(FigureCanvas):
    """
    グラフ下部の全体像ミニマップ(項目83)。

    refresh(datasets, dark_mode) で現在のデータセットの概観(簡略化した
    折れ線)を描き直し、matplotlib標準の SpanSelector でユーザーがドラッグ
    選択した範囲を range_selected(xmin, xmax) シグナルで通知する。
    """
    range_selected = Signal(float, float)

    def __init__(self, parent=None, dpi=100):
        self.fig = Figure(figsize=(5, 0.7), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setFixedHeight(MINIMAP_HEIGHT_PX)

        self.ax = self.fig.add_subplot(111)
        self.dark_mode = False
        self._span_selector = None

        self._configure_axes_style()
        self._create_span_selector()
        self._apply_theme_colors()

    # --- 内部ヘルパー ---

    def _configure_axes_style(self):
        """概観であることを強調するため、Y軸目盛りなど不要な装飾を消す"""
        self.ax.set_yticks([])
        self.ax.tick_params(axis='x', labelsize=6)
        for spine in ('top', 'right', 'left'):
            self.ax.spines[spine].set_visible(False)
        self.fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.28)

    def _create_span_selector(self):
        """
        SpanSelector を(再)生成する。ax.cla() は既存のSpanSelectorが
        axへ追加していたArtist(選択範囲を示す矩形)も一緒に消してしまうため、
        refresh() で ax.cla() した後は毎回作り直す必要がある。

        ★ バグ修正: 古いSpanSelectorのイベント接続(press/motion/release)を
        切断せずに上書きしていたため、refresh()が呼ばれるたび(データセット
        追加やプロット設定変更のたびに毎回)に前のSpanSelectorがcanvasの
        コールバック登録に生き残ったまま蓄積し、際限なくリークしていた
        (matplotlibはcla()やGCで自動的に接続を切ってくれない)。1回の
        ドラッグ操作のたびに、リークした数だけrange_selectedが重複発火
        したり、ax.cla()で既に消えたArtistをuseblit=Trueの古いSelectorが
        参照し続けて残像(ゴースト矩形)が出たりする実害があった。
        """
        if getattr(self, '_span_selector', None) is not None:
            self._span_selector.disconnect_events()
        span_color = DARK_SPAN_COLOR if self.dark_mode else LIGHT_SPAN_COLOR
        self._span_selector = SpanSelector(
            self.ax,
            self._on_select,
            'horizontal',
            useblit=True,
            props=dict(alpha=0.3, facecolor=span_color),
            interactive=True,
            drag_from_anywhere=True,
        )

    def _apply_theme_colors(self):
        fig_face = DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR
        axes_face = DARK_AXES_FACECOLOR if self.dark_mode else LIGHT_AXES_FACECOLOR
        self.fig.set_facecolor(fig_face)
        self.ax.set_facecolor(axes_face)

    def _on_select(self, xmin, xmax):
        """SpanSelectorのドラッグ選択が確定したときに呼ばれる"""
        if xmin == xmax:
            # クリックのみ(ドラッグなし)は範囲選択とみなさない
            return
        self.range_selected.emit(xmin, xmax)

    # --- 公開API ---

    def refresh(self, datasets, dark_mode=False):
        """
        現在のデータセット一覧をもとに、ミニマップの概観を描き直す。
        ナビゲーション用の補助表示であるため、複雑な描画(エラーバー・
        マーカー種別・二次軸など)は再現せず、各データセットのX/Y値を
        薄い折れ線として重ね描きするだけの簡易表示にとどめる(シンプルさ優先)。
        """
        self.dark_mode = dark_mode
        self.ax.cla()
        self._configure_axes_style()
        self._apply_theme_colors()

        line_color = DARK_LINE_COLOR if dark_mode else LIGHT_LINE_COLOR
        has_data = False
        for ds in datasets:
            # データセットの表示/非表示トグル(項目C-907): メインキャンバスの
            # redraw_all()と同様、非表示のデータセットはミニマップの概観からも除外する
            # (概観に非表示分の線が残ると、メイン表示と食い違って見えるため)。
            if not getattr(ds, 'visible', True):
                continue
            try:
                x = ds.x_data
                y = ds.y_data
            except Exception:
                continue
            if x is None or len(x) == 0:
                continue
            try:
                self.ax.plot(x, y, color=line_color, linewidth=0.7, alpha=0.6)
                has_data = True
            except Exception:
                # 概観表示に失敗しても致命的ではないため、ログのみ残してスキップ
                logger.debug("ミニマップへのデータセット描画に失敗しました", exc_info=True)

        if has_data:
            self.ax.relim()
            self.ax.autoscale_view()

        # cla() で古いSpanSelectorのArtistも消えているため作り直す
        self._create_span_selector()
        self.draw_idle()
