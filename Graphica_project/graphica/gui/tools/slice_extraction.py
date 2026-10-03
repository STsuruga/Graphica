"""スライス抽出モード: 2D マップの上でドラッグした線分に沿った断面を、新しい1次元のデータセットにする。

対象は今選んでいるデータセット(その軸に描かれていること)。線分がほぼ水平・垂直ならその軸の値、
斜めなら始点からの距離を X にする。
"""
import logging

from matplotlib.lines import Line2D

from graphica.gui import notify
from graphica.core.provenance import build_provenance
from graphica.core.dataset import Dataset
from graphica.core.grid_data import extract_slice, GridDataError
from graphica.gui.tools.pointer import clamped_data_point, legend_at

logger = logging.getLogger(__name__)

SLICE_EXTRACTION_N_POINTS = 200

# extract_slice() の 'axis_kind' ごとの、新しいデータセットの X の列名とラベル
_AXIS_KIND_LABELS = {
    'x': 'X',
    'y': 'Y',
    'distance': '始点からの距離',
}


class SliceExtractionTool:
    """状態はこのツールが持ち、PlotterApp の同じ名前は窓口(gui/tools/__init__.py)。"""

    # PlotterApp から同じ名前で読み書きできるもの(テスト・メニュー・ほかの mixin が使う)
    EXPOSED_NAMES = (
        '_apply_slice_extraction', '_clear_slice_extraction_preview', '_create_slice_dataset',
        '_on_slice_extraction_motion', '_on_slice_extraction_press', '_on_slice_extraction_release',
        '_slice_extraction_axes', '_slice_extraction_motion_cid', '_slice_extraction_press_cid',
        '_slice_extraction_preview_artist', '_slice_extraction_release_cid', '_slice_extraction_start',
        '_toggle_slice_extraction_mode', 'slice_extraction_mode_enabled',
    )

    def __init__(self, app):
        self._app = app
        self.slice_extraction_mode_enabled = False
        self._slice_extraction_press_cid = None
        self._slice_extraction_motion_cid = None
        self._slice_extraction_release_cid = None
        self._slice_extraction_axes = None
        self._slice_extraction_start = None         # (x, y) データ座標
        self._slice_extraction_preview_artist = None
        self._slice_extraction_background = None    # blit 用に押したときに撮った背景

    def _toggle_slice_extraction_mode(self, checked):
        self.slice_extraction_mode_enabled = checked

        if checked:
            self._app._deactivate_other_mouse_modes('slice_extraction')

            self._slice_extraction_press_cid = self._app.canvas.mpl_connect(
                'button_press_event', self._on_slice_extraction_press
            )
            self._slice_extraction_motion_cid = self._app.canvas.mpl_connect(
                'motion_notify_event', self._on_slice_extraction_motion
            )
            self._slice_extraction_release_cid = self._app.canvas.mpl_connect(
                'button_release_event', self._on_slice_extraction_release
            )
            self._app.statusBar().showMessage(
                "スライス抽出モード: カレントの2Dマップ上でドラッグした線分に沿って"
                "1Dデータセットを抽出します", 5000
            )
        else:
            for attr in ('_slice_extraction_press_cid', '_slice_extraction_motion_cid',
                         '_slice_extraction_release_cid'):
                cid = getattr(self, attr, None)
                if cid is not None:
                    self._app.canvas.mpl_disconnect(cid)
                    setattr(self, attr, None)
            self._clear_slice_extraction_preview()
            self._slice_extraction_axes = None
            self._slice_extraction_start = None

    def _clear_slice_extraction_preview(self):
        """ドラッグ中のプレビューと blit 用の背景を捨てる。描き直しで既に消えていても例外にしない。"""
        artist = getattr(self, '_slice_extraction_preview_artist', None)
        if artist is not None:
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
            self._slice_extraction_preview_artist = None
            self._app.canvas.draw_idle()
        self._slice_extraction_background = None

    def _on_slice_extraction_press(self, event):
        if not getattr(self, 'slice_extraction_mode_enabled', False):
            return
        if event.button != 1 or event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        if legend_at(self._app.canvas, event) is not None:
            return
        self._slice_extraction_axes = event.inaxes
        self._slice_extraction_start = (event.xdata, event.ydata)
        # 背景は始めに1回だけ撮り、以降は線分だけを blit で描き直す(毎回全体を描くと系列が多いほど重い)
        self._app.canvas.draw()
        self._slice_extraction_background = self._app.canvas.copy_from_bbox(event.inaxes.bbox)

    def _on_slice_extraction_motion(self, event):
        axes = getattr(self, '_slice_extraction_axes', None)
        if axes is None:
            return
        point = clamped_data_point(axes, event)
        if point is None:
            return

        start = self._slice_extraction_start
        xs, ys = [start[0], point[0]], [start[1], point[1]]
        line = self._slice_extraction_preview_artist
        if line is None:
            # animated=True の線は draw() では描かれず blit だけで出る。add_artist なのでデータの範囲にも入らない
            line = Line2D(xs, ys, color='#E4572E', linestyle='--', linewidth=1.5, zorder=100, animated=True)
            axes.add_artist(line)
            self._slice_extraction_preview_artist = line
        else:
            line.set_data(xs, ys)

        background = self._slice_extraction_background
        if background is None:
            self._app.canvas.draw_idle()
            return
        self._app.canvas.restore_region(background)
        axes.draw_artist(line)
        self._app.canvas.blit(axes.bbox)

    def _on_slice_extraction_release(self, event):
        axes = getattr(self, '_slice_extraction_axes', None)
        if axes is None:
            return

        self._clear_slice_extraction_preview()
        start = self._slice_extraction_start
        self._slice_extraction_axes = None
        self._slice_extraction_start = None

        # 軸の外で離したら、軸の縁で止めた位置を終点にする
        end = clamped_data_point(axes, event)
        if end is None:
            return
        if start == end:
            return  # クリックだけ(ドラッグなし)

        self._apply_slice_extraction(axes, start, end)

    def _apply_slice_extraction(self, axes, start, end):
        """今のデータセットが 2D の格子でないか、この軸に描かれていなければ、何もせず案内を出す。"""
        dataset = self._app._get_current_dataset()
        if dataset is None or dataset.data_kind != '2d_grid':
            notify.information(
                self._app, "スライス抽出", "スライス抽出の対象となる2Dマップのデータセットを選択してください。"
            )
            return

        target_axis = dataset.subplot_target
        if dataset.use_secondary_y:
            expected_axes = (
                self._app.all_secondary_axes[target_axis]
                if 0 <= target_axis < len(self._app.all_secondary_axes) else None
            )
        else:
            expected_axes = (
                self._app.all_axes[target_axis]
                if 0 <= target_axis < len(self._app.all_axes) else None
            )
        if axes is not expected_axes:
            notify.information(
                self._app, "スライス抽出",
                "ドラッグしたサブプロットに、選択中の2Dマップが描画されていません。"
            )
            return

        grid = dataset.z_grid
        if grid is None:
            notify.warning(self._app, "スライス抽出", "有効な2Dグリッドデータがありません。")
            return

        try:
            result = extract_slice(
                grid['x_grid'], grid['y_grid'], grid['z_grid'],
                start=start, end=end, n_points=SLICE_EXTRACTION_N_POINTS,
            )
        except GridDataError as e:
            notify.warning(self._app, "スライス抽出", f"スライスの抽出に失敗しました:\n{e}")
            return

        self._create_slice_dataset(dataset, start, end, result)

    def _create_slice_dataset(self, source_dataset, start, end, result):
        import pandas as pd

        axis_kind = result['axis_kind']
        x_label = _AXIS_KIND_LABELS.get(axis_kind, axis_kind)
        df = pd.DataFrame({'x': result['axis_values'], 'y': result['z_values']})
        params = {
            'start': [float(start[0]), float(start[1])],
            'end': [float(end[0]), float(end[1])],
            'axis_kind': axis_kind,
            'n_points': SLICE_EXTRACTION_N_POINTS,
        }
        slice_dataset = Dataset(
            name=f"Slice ({source_dataset.name})",
            df=df, x_col_name='x', y_col_name='y',
            provenance=build_provenance('2d_slice', params, [source_dataset]),
        )

        original_item = self._app._get_dataset_tree_item(source_dataset)
        folder = original_item.parent() if original_item else None

        def add():
            self._app.dataset_order.append(slice_dataset, folder)
            self._app._update_plot()

        self._app._push_dataset_additions(add, [slice_dataset], "スライスの抽出")
        self._app.statusBar().showMessage(
            f"「{source_dataset.name}」からスライスを抽出しました(X軸: {x_label})", 4000
        )
