"""範囲選択モード: X の範囲をドラッグで選び、その範囲の点を今のデータセットのマスクに加える。

SpanSelector は Axes に束縛されるので、Axes を作り直す redraw_all() のたびに作り直すことになる。ほかのモードと同じく
キャンバス全体の button_press / motion / release で event.inaxes を読む。
"""
import logging

from matplotlib.patches import Rectangle
from PySide6.QtWidgets import QMessageBox

from graphica.core.commands import SetMaskedRowsCommand

logger = logging.getLogger(__name__)


class RangeSelectMixin:
    def _toggle_range_select_mode(self, checked):
        self.range_select_mode_enabled = checked

        if checked:
            self._deactivate_other_mouse_modes('range_select')

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
        """ドラッグ中のプレビューの矩形と、blit 用の背景を捨てる。描き直しで既に消えていても例外にしない。"""
        artist = getattr(self, '_range_select_preview_artist', None)
        if artist is not None:
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
            self._range_select_preview_artist = None
            self.canvas.draw_idle()
        self._range_select_background = None

    def _on_range_select_press(self, event):
        if not getattr(self, 'range_select_mode_enabled', False):
            return
        if event.button != 1 or event.inaxes is None or event.xdata is None:
            return
        self._range_select_axes = event.inaxes
        self._range_select_start_x = event.xdata
        # 始めに1回だけ背景を撮り、以降は選択の矩形だけを blit で描き直す(毎回全体を描くと系列が多いほど重い)
        self.canvas.draw()
        self._range_select_background = self.canvas.copy_from_bbox(event.inaxes.bbox)

    def _on_range_select_motion(self, event):
        axes = getattr(self, '_range_select_axes', None)
        if axes is None or event.inaxes is not axes or event.xdata is None:
            return

        x0, x1 = sorted((self._range_select_start_x, event.xdata))
        ymin, ymax = axes.get_ylim()

        rect = getattr(self, '_range_select_preview_artist', None)
        if rect is None:
            # animated=True の Artist は draw() では描かれず、blit だけで出る。矩形は最初に1回作り、座標だけ変える
            rect = Rectangle(
                (x0, ymin), x1 - x0, ymax - ymin,
                facecolor='#3948B3', alpha=0.15, edgecolor='#3948B3',
                linewidth=1, zorder=100, animated=True,
            )
            axes.add_patch(rect)
            self._range_select_preview_artist = rect
        else:
            rect.set_bounds(x0, ymin, x1 - x0, ymax - ymin)

        background = getattr(self, '_range_select_background', None)
        if background is None:
            # 背景が撮れていなければ全体を描き直す
            self.canvas.draw_idle()
            return

        self.canvas.restore_region(background)
        axes.draw_artist(rect)
        self.canvas.blit(axes.bbox)

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
            return  # クリックだけ(ドラッグなし)は選択とみなさない

        x_min, x_max = sorted((start_x, end_x))
        self._apply_range_mask(axes, x_min, x_max)

    def _apply_range_mask(self, axes, x_min, x_max):
        """[x_min, x_max] の点をマスクに加える。今のデータセットがこの軸に描かれていなければ、何もせず案内を出す。"""
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

        # ドラッグの x はウォーターフォールのずらしが掛かった表示座標なので、データ座標に戻して比べる
        data_x_min, _ = self.canvas.display_to_data(dataset, x_min, 0.0)
        data_x_max, _ = self.canvas.display_to_data(dataset, x_max, 0.0)

        x_data = dataset.x_data
        visible_index = dataset.visible_df.index
        in_range_mask = (x_data >= data_x_min) & (x_data <= data_x_max)
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