"""領域強調モード: X 方向に大きくドラッグすると縦の帯、Y 方向なら横の帯を足す。

帯は注釈と同じ 'annotations' に type='vspan' / 'hspan' で入れるので、保存・Undo・描画は注釈と共有する。
データ座標で持つので、データを読み直しても位置は変わらない。
"""
import logging

from matplotlib.patches import Rectangle
from PySide6.QtWidgets import QMessageBox

from graphica.gui import notify
from graphica.core.axis_settings import axis_setting
from graphica.core.commands import SetAnnotationsCommand
from graphica.gui.tools.pointer import clamped_data_point, legend_at

logger = logging.getLogger(__name__)

# これより動かなければクリック(誤クリックで極小の帯ができないように)
REGION_HIGHLIGHT_DRAG_THRESHOLD_PX = 5

REGION_HIGHLIGHT_DEFAULT_COLOR = '#F2A72B'
REGION_HIGHLIGHT_DEFAULT_ALPHA = 0.18


class RegionHighlightTool:
    """状態はこのツールが持ち、PlotterApp の同じ名前は窓口(gui/tools/__init__.py)。"""

    # PlotterApp から同じ名前で読み書きできるもの(テスト・メニュー・ほかの mixin が使う)
    EXPOSED_NAMES = (
        '_clear_region_highlight_preview', '_on_region_highlight_motion', '_on_region_highlight_press',
        '_on_region_highlight_release', '_region_highlight_axes', '_region_highlight_motion_cid',
        '_region_highlight_orientation', '_region_highlight_press_cid', '_region_highlight_preview_artist',
        '_region_highlight_release_cid', '_region_highlight_start', '_toggle_region_highlight_mode',
        '_try_delete_region_near', 'region_highlight_mode_enabled',
    )

    def __init__(self, app):
        self._app = app
        self.region_highlight_mode_enabled = False
        self._region_highlight_press_cid = None
        self._region_highlight_motion_cid = None
        self._region_highlight_release_cid = None
        self._region_highlight_axes = None
        self._region_highlight_start = None         # (x, y) データ座標
        self._region_highlight_preview_artist = None
        self._region_highlight_background = None    # blit 用に押したときに撮った背景

    def _toggle_region_highlight_mode(self, checked):
        self.region_highlight_mode_enabled = checked

        if checked:
            self._app._deactivate_other_mouse_modes('region_highlight')

            self._region_highlight_press_cid = self._app.canvas.mpl_connect(
                'button_press_event', self._on_region_highlight_press
            )
            self._region_highlight_motion_cid = self._app.canvas.mpl_connect(
                'motion_notify_event', self._on_region_highlight_motion
            )
            self._region_highlight_release_cid = self._app.canvas.mpl_connect(
                'button_release_event', self._on_region_highlight_release
            )
            self._app.statusBar().showMessage(
                "領域ハイライトモード: 横方向にドラッグで縦帯、縦方向にドラッグで横帯を追加"
                "(右クリックで削除)", 5000
            )
        else:
            if getattr(self, '_region_highlight_press_cid', None) is not None:
                self._app.canvas.mpl_disconnect(self._region_highlight_press_cid)
                self._region_highlight_press_cid = None
            if getattr(self, '_region_highlight_motion_cid', None) is not None:
                self._app.canvas.mpl_disconnect(self._region_highlight_motion_cid)
                self._region_highlight_motion_cid = None
            if getattr(self, '_region_highlight_release_cid', None) is not None:
                self._app.canvas.mpl_disconnect(self._region_highlight_release_cid)
                self._region_highlight_release_cid = None
            self._clear_region_highlight_preview()
            self._region_highlight_axes = None
            self._region_highlight_start = None

    def _clear_region_highlight_preview(self):
        """ドラッグ中のプレビューと blit 用の背景を捨てる。描き直しで既に消えていても例外にしない。"""
        artist = getattr(self, '_region_highlight_preview_artist', None)
        if artist is not None:
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
            self._region_highlight_preview_artist = None
            self._app.canvas.draw_idle()
        self._region_highlight_background = None

    def _on_region_highlight_press(self, event):
        if not getattr(self, 'region_highlight_mode_enabled', False):
            return
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        if legend_at(self._app.canvas, event) is not None:
            return

        if event.button == 3:  # 右クリックは削除
            self._try_delete_region_near(event)
            return

        self._region_highlight_axes = event.inaxes
        self._region_highlight_start = (event.xdata, event.ydata)
        # 背景は始めに1回だけ撮り、以降は帯だけを blit で描き直す(毎回全体を描くと系列が多いほど重い)
        self._app.canvas.draw()
        self._region_highlight_background = self._app.canvas.copy_from_bbox(event.inaxes.bbox)

    def _on_region_highlight_motion(self, event):
        axes = getattr(self, '_region_highlight_axes', None)
        if axes is None:
            return
        point = clamped_data_point(axes, event)
        if point is None:
            return

        start_x, start_y = self._region_highlight_start
        current_x, current_y = point
        orientation = self._region_highlight_orientation(axes, start_x, start_y, current_x, current_y)
        if orientation is None:
            return

        xmin, xmax = axes.get_xlim()
        ymin, ymax = axes.get_ylim()
        if orientation == 'vspan':
            x0, x1 = sorted((start_x, current_x))
            bounds = (x0, ymin, x1 - x0, ymax - ymin)
        else:
            y0, y1 = sorted((start_y, current_y))
            bounds = (xmin, y0, xmax - xmin, y1 - y0)

        rect = self._region_highlight_preview_artist
        if rect is None:
            # animated=True の図形は draw() では描かれず blit だけで出る。add_artist なのでデータの範囲にも入らない
            rect = Rectangle(
                bounds[:2], bounds[2], bounds[3],
                facecolor=REGION_HIGHLIGHT_DEFAULT_COLOR, alpha=0.25,
                edgecolor=REGION_HIGHLIGHT_DEFAULT_COLOR, linewidth=1, zorder=100, animated=True,
            )
            axes.add_artist(rect)
            self._region_highlight_preview_artist = rect
        else:
            rect.set_bounds(*bounds)

        background = self._region_highlight_background
        if background is None:
            self._app.canvas.draw_idle()
            return
        self._app.canvas.restore_region(background)
        axes.draw_artist(rect)
        self._app.canvas.blit(axes.bbox)

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

        # 軸の外で離したら、軸の縁で止めた位置までの帯にする
        end_point = clamped_data_point(axes, event)
        if end_point is None:
            return
        end_x, end_y = end_point
        orientation = self._region_highlight_orientation(axes, start_x, start_y, end_x, end_y)
        if orientation is None:
            return  # クリックだけ(ドラッグなし)

        axis_index = self._app._find_axis_index(axes)
        if axis_index is None:
            return

        if orientation == 'vspan':
            value_range = tuple(sorted((float(start_x), float(end_x))))
        else:
            value_range = tuple(sorted((float(start_y), float(end_y))))

        self._app._add_annotation(axis_index, {
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
        axis_index = self._app._find_axis_index(event.inaxes)
        if axis_index is None:
            return

        settings = self._app.project.all_plot_settings[axis_index]
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
        reply = notify.question(
            self._app, "領域ハイライトの削除",
            f"この{label}を削除しますか?\n\n範囲: {lo:.4g} 〜 {hi:.4g}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        new_list = list(annotations)
        del new_list[target_index]

        command = SetAnnotationsCommand(
            self._app.project, axis_index, annotations, new_list,
            self._app._update_plot_appearance, description="領域ハイライトの削除"
        )
        self._app.undo_stack.push(command)
