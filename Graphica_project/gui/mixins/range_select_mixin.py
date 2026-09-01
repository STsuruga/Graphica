# gui/mixins/range_select_mixin.py
"""
グラフ上での範囲選択(項目C-909)。既存の「クリックでデータセットを選択」
(項目35)と「行のマスク」(項目36、core/commands.pyのSetMaskedRowsCommand)を
橋渡しする機能: プロット上でXの範囲をドラッグ選択すると、その範囲に入る
カレントデータセットのデータ点を、非破壊マスク(masked_row_indices)として
除外する。

★ 設計方針: matplotlib.widgets.SpanSelectorは使わない。SpanSelectorは
特定のAxesインスタンスに束縛されるステートフルなウィジェットだが、この
アプリのメインキャンバス(gui/canvas.py)はredraw_all()のたびにfig.clf()で
Axesを作り直す(項目C-003で解消予定の既知の制約)ため、SpanSelectorを
使うと再描画のたびに作り直す必要がある(gui/minimap_widget.pyは専用の
小さな独立Figureで、fig.clf()されないため問題にならない — メインキャンバス
とは事情が異なる)。代わりに、他のモード(データカーソル/注釈/自由配置編集、
いずれもcanvas全体に1回だけ接続したbutton_press/motion/release_eventで
event.inaxesを都度読む方式)と同じパターンを踏襲することで、Axes再生成の
影響を受けない。
"""
import logging

from matplotlib.patches import Rectangle
from PySide6.QtWidgets import QMessageBox

from core.commands import SetMaskedRowsCommand

logger = logging.getLogger(__name__)


class RangeSelectMixin:
    def _toggle_range_select_mode(self, checked):
        """
        「範囲選択」ツールバーボタンが押されたときの処理。
        他のクリック/ドラッグ系モード(データカーソル/注釈/自由配置編集)と
        同時に有効だと同じ操作が競合するため排他にする。
        """
        self.range_select_mode_enabled = checked

        if checked:
            if getattr(self, 'cursor_mode_enabled', False):
                self.cursor_action.setChecked(False)
                self._toggle_cursor_mode(False)
            if getattr(self, 'annotation_mode_enabled', False):
                self.annotation_action.setChecked(False)
                self._toggle_annotation_mode(False)
            if getattr(self, 'layout_edit_mode_enabled', False):
                self.layout_edit_action.setChecked(False)
                self._toggle_layout_edit_mode(False)
            if getattr(self, 'peak_placement_mode_enabled', False):
                self.peak_placement_action.setChecked(False)
                self._toggle_peak_placement_mode(False)
            if getattr(self, 'slice_extraction_mode_enabled', False):
                self.slice_extraction_action.setChecked(False)
                self._toggle_slice_extraction_mode(False)
            if getattr(self, 'region_highlight_mode_enabled', False):
                self.region_highlight_action.setChecked(False)
                self._toggle_region_highlight_mode(False)

            self._range_select_press_cid = self.canvas.mpl_connect(
                'button_press_event', self._on_range_select_press
            )
            self._range_select_motion_cid = self.canvas.mpl_connect(
                'motion_notify_event', self._on_range_select_motion
            )
            self._range_select_release_cid = self.canvas.mpl_connect(
                'button_release_event', self._on_range_select_release
            )
            self.statusBar().showMessage(
                "範囲選択モード: カレントデータセット上でドラッグした範囲を"
                "マスク(除外)します", 5000
            )
        else:
            if getattr(self, '_range_select_press_cid', None) is not None:
                self.canvas.mpl_disconnect(self._range_select_press_cid)
                self._range_select_press_cid = None
            if getattr(self, '_range_select_motion_cid', None) is not None:
                self.canvas.mpl_disconnect(self._range_select_motion_cid)
                self._range_select_motion_cid = None
            if getattr(self, '_range_select_release_cid', None) is not None:
                self.canvas.mpl_disconnect(self._range_select_release_cid)
                self._range_select_release_cid = None
            self._clear_range_select_preview()
            self._range_select_axes = None
            self._range_select_start_x = None

    def _clear_range_select_preview(self):
        """ドラッグ中のプレビュー矩形を取り除く。fig.clf()で既に破棄されて
        いる場合(再描画がドラッグ中に割り込んだ場合)に備えてValueError/
        NotImplementedErrorは無視する(gui/canvas.pyのset_highlighted_points
        と同じ防御)。"""
        artist = getattr(self, '_range_select_preview_artist', None)
        if artist is not None:
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
            self._range_select_preview_artist = None
            self.canvas.draw_idle()

    def _on_range_select_press(self, event):
        if not getattr(self, 'range_select_mode_enabled', False):
            return
        if event.button != 1 or event.inaxes is None or event.xdata is None:
            return
        self._range_select_axes = event.inaxes
        self._range_select_start_x = event.xdata

    def _on_range_select_motion(self, event):
        axes = getattr(self, '_range_select_axes', None)
        if axes is None or event.inaxes is not axes or event.xdata is None:
            return

        self._clear_range_select_preview()
        x0, x1 = sorted((self._range_select_start_x, event.xdata))
        ymin, ymax = axes.get_ylim()
        rect = Rectangle(
            (x0, ymin), x1 - x0, ymax - ymin,
            facecolor='#3948B3', alpha=0.15, edgecolor='#3948B3',
            linewidth=1, zorder=100,
        )
        axes.add_patch(rect)
        self._range_select_preview_artist = rect
        self.canvas.draw_idle()

    def _on_range_select_release(self, event):
        axes = getattr(self, '_range_select_axes', None)
        if axes is None:
            return

        self._clear_range_select_preview()
        start_x = self._range_select_start_x
        self._range_select_axes = None
        self._range_select_start_x = None

        end_x = event.xdata if (event.inaxes is axes and event.xdata is not None) else None
        if end_x is None or start_x is None or start_x == end_x:
            return  # クリックのみ(ドラッグなし)は範囲選択とみなさない

        x_min, x_max = sorted((start_x, end_x))
        self._apply_range_mask(axes, x_min, x_max)

    def _apply_range_mask(self, axes, x_min, x_max):
        """
        ドラッグ確定した範囲[x_min, x_max]を、カレントデータセットの
        マスク(項目36、非破壊)へ追加する。カレントデータセットがこの
        Axes上に描画されていない(別のサブプロットを選択中、または第2Y軸/
        主軸の食い違い)場合は、紛らわしい誤爆を避けるため何もせず案内を出す。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            QMessageBox.information(self, "範囲選択", "マスク対象のデータセットを選択してください。")
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
                self, "範囲選択",
                "ドラッグしたサブプロットに、選択中のデータセットが描画されていません。"
            )
            return

        x_data = dataset.x_data
        visible_index = dataset.visible_df.index
        in_range_mask = (x_data >= x_min) & (x_data <= x_max)
        newly_masked = [int(idx) for idx, flag in zip(visible_index, in_range_mask) if flag]
        if not newly_masked:
            return

        old_masked = list(dataset.masked_row_indices)
        new_masked = sorted(set(old_masked) | set(newly_masked))
        if new_masked == old_masked:
            return

        command = SetMaskedRowsCommand(
            dataset, old_masked, new_masked,
            description=f"範囲選択でのマスク({len(newly_masked)}件)",
        )
        self.undo_stack.push(command)
        self._update_plot()
        self.statusBar().showMessage(
            f"「{dataset.name}」の{len(newly_masked)}点をマスクしました", 3000
        )