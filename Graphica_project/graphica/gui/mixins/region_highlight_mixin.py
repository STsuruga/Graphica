"""領域強調モード: X 方向に大きくドラッグすると縦の帯、Y 方向なら横の帯を足す。

帯は注釈と同じ 'annotations' に type='vspan' / 'hspan' で入れるので、保存・Undo・描画は注釈と共有する。
データ座標で持つので、データを読み直しても位置は変わらない。
"""
import logging

from matplotlib.patches import Rectangle
from PySide6.QtWidgets import QMessageBox

from graphica.core.axis_settings import axis_setting
from graphica.core.commands import SetAnnotationsCommand

logger = logging.getLogger(__name__)

# これより動かなければクリック(誤クリックで極小の帯ができないように)
REGION_HIGHLIGHT_DRAG_THRESHOLD_PX = 5

REGION_HIGHLIGHT_DEFAULT_COLOR = '#F2A72B'
REGION_HIGHLIGHT_DEFAULT_ALPHA = 0.18


class RegionHighlightMixin:
    def _toggle_region_highlight_mode(self, checked):
        self.region_highlight_mode_enabled = checked

        if checked:
            self._deactivate_other_mouse_modes('region_highlight')

            self._region_highlight_press_cid = self.canvas.mpl_connect(
                'button_press_event', self._on_region_highlight_press
            )
            self._region_highlight_motion_cid = self.canvas.mpl_connect(
                'motion_notify_event', self._on_region_highlight_motion
            )
            self._region_highlight_release_cid = self.canvas.mpl_connect(
                'button_release_event', self._on_region_highlight_release
            )
            self.statusBar().showMessage(
                "領域ハイライトモード: 横方向にドラッグで縦帯、縦方向にドラッグで横帯を追加"
                "(右クリックで削除)", 5000
            )
        else:
            if getattr(self, '_region_highlight_press_cid', None) is not None:
                self.canvas.mpl_disconnect(self._region_highlight_press_cid)
                self._region_highlight_press_cid = None
            if getattr(self, '_region_highlight_motion_cid', None) is not None:
                self.canvas.mpl_disconnect(self._region_highlight_motion_cid)
                self._region_highlight_motion_cid = None
            if getattr(self, '_region_highlight_release_cid', None) is not None:
                self.canvas.mpl_disconnect(self._region_highlight_release_cid)
                self._region_highlight_release_cid = None
            self._clear_region_highlight_preview()
            self._region_highlight_axes = None
            self._region_highlight_start = None

    def _clear_region_highlight_preview(self):
        """ドラッグ中のプレビューを消す。描き直しで既に消えていても例外にしない。"""
        artist = getattr(self, '_region_highlight_preview_artist', None)
        if artist is not None:
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
            self._region_highlight_preview_artist = None
            self.canvas.draw_idle()

    def _on_region_highlight_press(self, event):
        if not getattr(self, 'region_highlight_mode_enabled', False):
            return
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return

        if event.button == 3:  # 右クリックは削除
            self._try_delete_region_near(event)
            return

        self._region_highlight_axes = event.inaxes
        self._region_highlight_start = (event.xdata, event.ydata)

    def _on_region_highlight_motion(self, event):
        axes = getattr(self, '_region_highlight_axes', None)
        if axes is None or event.inaxes is not axes or event.xdata is None or event.ydata is None:
            return

        start_x, start_y = self._region_highlight_start
        orientation = self._region_highlight_orientation(axes, start_x, start_y, event.xdata, event.ydata)
        if orientation is None:
            return

        self._clear_region_highlight_preview()
        xmin, xmax = axes.get_xlim()
        ymin, ymax = axes.get_ylim()
        if orientation == 'vspan':
            x0, x1 = sorted((start_x, event.xdata))
            rect = Rectangle(
                (x0, ymin), x1 - x0, ymax - ymin,
                facecolor=REGION_HIGHLIGHT_DEFAULT_COLOR, alpha=0.25,
                edgecolor=REGION_HIGHLIGHT_DEFAULT_COLOR, linewidth=1, zorder=100,
            )
        else:
            y0, y1 = sorted((start_y, event.ydata))
            rect = Rectangle(
                (xmin, y0), xmax - xmin, y1 - y0,
                facecolor=REGION_HIGHLIGHT_DEFAULT_COLOR, alpha=0.25,
                edgecolor=REGION_HIGHLIGHT_DEFAULT_COLOR, linewidth=1, zorder=100,
            )
        axes.add_patch(rect)
        self._region_highlight_preview_artist = rect
        self.canvas.draw_idle()

    def _on_region_highlight_release(self, event):
        axes = getattr(self, '_region_highlight_axes', None)
        if axes is None:
            return

        self._clear_region_highlight_preview()
        start = self._region_highlight_start
        self._region_highlight_axes = None
        self._region_highlight_start = None
        if start is None:
            return
        start_x, start_y = start

        if event.inaxes is not axes or event.xdata is None or event.ydata is None:
            return  # 別の軸か軸の外で離した

        end_x, end_y = event.xdata, event.ydata
        orientation = self._region_highlight_orientation(axes, start_x, start_y, end_x, end_y)
        if orientation is None:
            return  # クリックだけ(ドラッグなし)

        axis_index = self._find_axis_index(axes)
        if axis_index is None:
            return

        if orientation == 'vspan':
            value_range = tuple(sorted((float(start_x), float(end_x))))
        else:
            value_range = tuple(sorted((float(start_y), float(end_y))))

        self._add_annotation(axis_index, {
            'type': orientation, 'range': value_range,
            'color': REGION_HIGHLIGHT_DEFAULT_COLOR, 'alpha': REGION_HIGHLIGHT_DEFAULT_ALPHA,
        }, description="領域ハイライトの追加")

    def _region_highlight_orientation(self, axes, start_x, start_y, current_x, current_y):
        """'vspan'(横に大きく動いた)/ 'hspan'(縦に大きく動いた)/ None(まだドラッグとみなせない)。"""
        start_px = axes.transData.transform((start_x, start_y))
        current_px = axes.transData.transform((current_x, current_y))
        dx = abs(current_px[0] - start_px[0])
        dy = abs(current_px[1] - start_px[1])
        if max(dx, dy) < REGION_HIGHLIGHT_DRAG_THRESHOLD_PX:
            return None
        return 'vspan' if dx >= dy else 'hspan'

    def _try_delete_region_near(self, event):
        """右クリックした位置の帯を、確認してから消す。重なっていれば最後に足したもの(いちばん手前)。"""
        axis_index = self._find_axis_index(event.inaxes)
        if axis_index is None:
            return

        settings = self.project.all_plot_settings[axis_index]
        annotations = axis_setting(settings, 'annotations')

        target_index = None
        for i, ann in enumerate(annotations):
            ann_type = ann.get('type')
            if ann_type not in ('vspan', 'hspan'):
                continue
            value = event.xdata if ann_type == 'vspan' else event.ydata
            lo, hi = ann.get('range', (None, None))
            if lo is None or hi is None or value is None:
                continue
            if lo <= value <= hi:
                target_index = i  # 後ろのものほど手前

        if target_index is None:
            return

        target = annotations[target_index]
        label = "縦帯" if target.get('type') == 'vspan' else "横帯"
        lo, hi = target.get('range', (None, None))
        reply = QMessageBox.question(
            self, "領域ハイライトの削除",
            f"この{label}を削除しますか?\n\n範囲: {lo:.4g} 〜 {hi:.4g}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        new_list = list(annotations)
        del new_list[target_index]

        command = SetAnnotationsCommand(
            self.project, axis_index, annotations, new_list,
            self._update_plot_appearance, description="領域ハイライトの削除"
        )
        self.undo_stack.push(command)
