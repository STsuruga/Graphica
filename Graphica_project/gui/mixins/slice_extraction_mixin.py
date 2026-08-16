# gui/mixins/slice_extraction_mixin.py
"""
2Dマップ(ヒートマップ/等高線、項目C-508/C-509)上でのドラッグによる1Dスライス
抽出(項目C-511)。既存のモード切替系Mixin(cursor_mixin.py/annotation_mixin.py/
range_select_mixin.py/peak_placement_mixin.py)と同じ「モードトグル+
mpl_connect('button_press/motion_notify/button_release_event', ...)+
他モードとの相互排他」パターンを踏襲する。

対象となる2Dデータセットは、range_select_mixin.pyの_apply_range_maskと同じ
「カレントデータセットが、ドラッグしたAxes上に実際に描画されているか」という
判定方式を使う(複数の2Dデータセットが同じAxesに重なっている場合の曖昧さを、
「今選択しているものを対象にする」という単純なルールで解消する)。

線分がほぼ水平/垂直ならその軸のスライスとして、斜めならcore/grid_data.pyの
extract_slice()が返す「始点からの距離」を新規データセットのX軸として使う。
"""
import logging

from PySide6.QtWidgets import QMessageBox

from core.dataset import Dataset
from core.grid_data import extract_slice, GridDataError

logger = logging.getLogger(__name__)

# スライス抽出時にサンプリングする点数
SLICE_EXTRACTION_N_POINTS = 200

# 軸の種類(extract_slice()の'axis_kind')ごとの、新規データセットのX軸列名・ラベル
_AXIS_KIND_LABELS = {
    'x': 'X',
    'y': 'Y',
    'distance': '始点からの距離',
}


class SliceExtractionMixin:
    def _toggle_slice_extraction_mode(self, checked):
        """「スライス抽出」ツールバーボタンが押されたときの処理。"""
        self.slice_extraction_mode_enabled = checked

        if checked:
            if getattr(self, 'cursor_mode_enabled', False):
                self.cursor_action.setChecked(False)
                self._toggle_cursor_mode(False)
            if getattr(self, 'annotation_mode_enabled', False):
                self.annotation_action.setChecked(False)
                self._toggle_annotation_mode(False)
            if getattr(self, 'range_select_mode_enabled', False):
                self.range_select_action.setChecked(False)
                self._toggle_range_select_mode(False)
            if getattr(self, 'layout_edit_mode_enabled', False):
                self.layout_edit_action.setChecked(False)
                self._toggle_layout_edit_mode(False)
            if getattr(self, 'peak_placement_mode_enabled', False):
                self.peak_placement_action.setChecked(False)
                self._toggle_peak_placement_mode(False)

            self._slice_extraction_press_cid = self.canvas.mpl_connect(
                'button_press_event', self._on_slice_extraction_press
            )
            self._slice_extraction_motion_cid = self.canvas.mpl_connect(
                'motion_notify_event', self._on_slice_extraction_motion
            )
            self._slice_extraction_release_cid = self.canvas.mpl_connect(
                'button_release_event', self._on_slice_extraction_release
            )
            self.statusBar().showMessage(
                "スライス抽出モード: カレントの2Dマップ上でドラッグした線分に沿って"
                "1Dデータセットを抽出します", 5000
            )
        else:
            for attr in ('_slice_extraction_press_cid', '_slice_extraction_motion_cid',
                         '_slice_extraction_release_cid'):
                cid = getattr(self, attr, None)
                if cid is not None:
                    self.canvas.mpl_disconnect(cid)
                    setattr(self, attr, None)
            self._clear_slice_extraction_preview()
            self._slice_extraction_axes = None
            self._slice_extraction_start = None

    def _clear_slice_extraction_preview(self):
        """ドラッグ中のプレビュー線を取り除く。fig.clf()で既に破棄されている
        場合(再描画がドラッグ中に割り込んだ場合)に備えてValueError/
        NotImplementedErrorは無視する(range_select_mixin.pyと同じ防御)。"""
        artist = getattr(self, '_slice_extraction_preview_artist', None)
        if artist is not None:
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
            self._slice_extraction_preview_artist = None
            self.canvas.draw_idle()

    def _on_slice_extraction_press(self, event):
        if not getattr(self, 'slice_extraction_mode_enabled', False):
            return
        if event.button != 1 or event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        self._slice_extraction_axes = event.inaxes
        self._slice_extraction_start = (event.xdata, event.ydata)

    def _on_slice_extraction_motion(self, event):
        axes = getattr(self, '_slice_extraction_axes', None)
        if axes is None or event.inaxes is not axes or event.xdata is None or event.ydata is None:
            return

        self._clear_slice_extraction_preview()
        start = self._slice_extraction_start
        (line,) = axes.plot(
            [start[0], event.xdata], [start[1], event.ydata],
            color='#E4572E', linestyle='--', linewidth=1.5, zorder=100,
        )
        self._slice_extraction_preview_artist = line
        self.canvas.draw_idle()

    def _on_slice_extraction_release(self, event):
        axes = getattr(self, '_slice_extraction_axes', None)
        if axes is None:
            return

        self._clear_slice_extraction_preview()
        start = self._slice_extraction_start
        self._slice_extraction_axes = None
        self._slice_extraction_start = None

        if event.inaxes is not axes or event.xdata is None or event.ydata is None:
            return
        end = (event.xdata, event.ydata)
        if start == end:
            return  # クリックのみ(ドラッグなし)は抽出とみなさない

        self._apply_slice_extraction(axes, start, end)

    def _apply_slice_extraction(self, axes, start, end):
        """
        ドラッグ確定した線分[start, end]から、カレントデータセット(2Dグリッド)の
        1Dスライスを抽出し、新規データセットとして追加する。カレントデータセットが
        2Dグリッドでない、またはこのAxes上に描画されていない場合は、紛らわしい
        誤爆を避けるため何もせず案内を出す(range_select_mixin.pyの
        _apply_range_maskと同じ方針)。
        """
        dataset = self._get_current_dataset()
        if dataset is None or dataset.data_kind != '2d_grid':
            QMessageBox.information(
                self, "スライス抽出", "スライス抽出の対象となる2Dマップのデータセットを選択してください。"
            )
            return

        target_axis = dataset.subplot_target
        if dataset.use_secondary_y:
            expected_axes = (
                self.all_secondary_axes[target_axis]
                if 0 <= target_axis < len(self.all_secondary_axes) else None
            )
        else:
            expected_axes = (
                self.all_axes[target_axis]
                if 0 <= target_axis < len(self.all_axes) else None
            )
        if axes is not expected_axes:
            QMessageBox.information(
                self, "スライス抽出",
                "ドラッグしたサブプロットに、選択中の2Dマップが描画されていません。"
            )
            return

        grid = dataset.z_grid
        if grid is None:
            QMessageBox.warning(self, "スライス抽出", "有効な2Dグリッドデータがありません。")
            return

        try:
            result = extract_slice(
                grid['x_grid'], grid['y_grid'], grid['z_grid'],
                start=start, end=end, n_points=SLICE_EXTRACTION_N_POINTS,
            )
        except GridDataError as e:
            QMessageBox.warning(self, "スライス抽出", f"スライスの抽出に失敗しました:\n{e}")
            return

        self._create_slice_dataset(dataset, start, end, result)

    def _create_slice_dataset(self, source_dataset, start, end, result):
        """
        extract_slice()の結果から新規1Dデータセットを作成し、プロジェクトに追加する
        (_on_fit_curve_succeeded等、他の派生データセット生成箇所と同じパターン)。
        """
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
            provenance=self._build_provenance('2d_slice', params, [source_dataset]),
        )

        self.project.datasets.append(slice_dataset)
        original_item = self._get_dataset_tree_item(source_dataset)
        self._add_dataset_list_item(slice_dataset, original_item.parent() if original_item else None)
        self._update_plot()
        self.statusBar().showMessage(
            f"「{source_dataset.name}」からスライスを抽出しました(X軸: {x_label})", 4000
        )
