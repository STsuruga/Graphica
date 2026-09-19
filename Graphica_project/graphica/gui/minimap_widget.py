"""グラフの下の小さな全体図。ドラッグで選んだ範囲を range_selected で知らせる(軸に当てるのは呼び出し側)。

メインのキャンバスとは別の Figure なので、redraw_all() では描き直されない。データが変わったら refresh() を呼ぶこと。
"""
import logging

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PySide6.QtCore import Signal

from graphica.core.analysis import calculate_lttb_downsample
from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE

logger = logging.getLogger(__name__)

# 点で描く種類。Line+Scatter は線が主なので含めない
MINIMAP_POINT_PLOT_TYPES = frozenset({'Scatter', 'Density Scatter', COLOR_BY_COLUMN_PLOT_TYPE})

MINIMAP_HEIGHT_PX = 70

# 間引く。SpanSelector の背景は全体を描いた画像で、refresh() のたびに作り直すので、点が多いとドラッグが重くなる。
# 幅が数百 px しかないので、canvas の LTTB より少ない点でよい
MINIMAP_DOWNSAMPLE_THRESHOLD = 2000
MINIMAP_DOWNSAMPLE_TARGET_POINTS = 500

# gui/canvas.py の配色と揃える
DARK_FIGURE_FACECOLOR = '#2b2b2b'
# 周りのパネルと同じ寒色寄りの色味で、少しだけ暗くして一段くぼんだ領域に見せる
DARK_AXES_FACECOLOR = '#0E1114'
DARK_LINE_COLOR = '#8ab4f8'
DARK_SPAN_COLOR = '#8ab4f8'
LIGHT_FIGURE_FACECOLOR = '#ffffff'
LIGHT_AXES_FACECOLOR = '#E3E6EB'
LIGHT_LINE_COLOR = '#1a73e8'
LIGHT_SPAN_COLOR = '#1a73e8'


class MinimapWidget(FigureCanvas):
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


    def _configure_axes_style(self):
        self.ax.set_yticks([])
        self.ax.tick_params(axis='x', labelsize=6)
        for spine in ('top', 'right', 'left'):
            self.ax.spines[spine].set_visible(False)
        self.fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.28)

    def _create_span_selector(self):
        """SpanSelector を作り直す(ax.cla() が選択の矩形も消すので、refresh() のたびに)。

        古いものの接続は切る。matplotlib は cla() でも切らないので、残すと溜まって range_selected が重複して出る。
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
        if xmin == xmax:
            # クリックだけ(ドラッグなし)は選択とみなさない
            return
        self.range_selected.emit(xmin, xmax)

    @staticmethod
    def _downsample_for_overview(x, y):
        """点を減らす。X が昇順なら LTTB、そうでなければ等間隔に間引く(LTTB は昇順が前提)。"""
        n = len(x)
        if n <= MINIMAP_DOWNSAMPLE_THRESHOLD:
            return x, y
        if np.all(np.diff(x) >= 0):
            idx = calculate_lttb_downsample(x, y, MINIMAP_DOWNSAMPLE_TARGET_POINTS)
        else:
            step = max(1, n // MINIMAP_DOWNSAMPLE_TARGET_POINTS)
            idx = np.arange(0, n, step)
        return x[idx], y[idx]


    def refresh(self, datasets, dark_mode=False):
        """各データセットの X/Y を薄い線か点で重ねるだけの簡単な全体図にする。"""
        self.dark_mode = dark_mode
        self.ax.cla()
        self._configure_axes_style()
        self._apply_theme_colors()

        line_color = DARK_LINE_COLOR if dark_mode else LIGHT_LINE_COLOR
        has_data = False
        for ds in datasets:
            # メインと同じく隠した系列は出さない
            if not getattr(ds, 'visible', True):
                continue
            # 2D マップの x/y は測定点の列なので、線にすると意味が無い。描かない
            if getattr(ds, 'data_kind', '1d') == '2d_grid':
                continue
            try:
                x = ds.x_data
                y = ds.y_data
            except Exception:
                logger.debug("ミニマップ用のデータを取り出せません: %s", ds.name, exc_info=True)
                continue
            if x is None or len(x) == 0:
                continue
            try:
                x, y = self._downsample_for_overview(x, y)
                if getattr(ds, 'plot_type', 'Line') in MINIMAP_POINT_PLOT_TYPES:
                    # 点の種類は点で描く(線にするとピーク検出の結果がピーク同士を結ぶ線になる)
                    self.ax.plot(x, y, linestyle='None', marker='o', markersize=1.8,
                                 color=line_color, alpha=0.8)
                else:
                    self.ax.plot(x, y, color=line_color, linewidth=0.7, alpha=0.6)
                has_data = True
            except Exception:
                # 全体図なので、描けなくても止めない
                logger.debug("ミニマップへのデータセット描画に失敗しました", exc_info=True)

        if has_data:
            self.ax.relim()
            self.ax.autoscale_view()

        self._create_span_selector()
        self.draw_idle()
