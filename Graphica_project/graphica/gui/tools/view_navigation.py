"""表示範囲のマウス操作。モードではなく常に有効(モードとぶつかる操作だけ、モードの最中は譲る)。

- 軸の上(目盛りラベルの帯): ホイールでその軸だけ拡大縮小、左ドラッグでその軸の方向に移動、ダブルクリックでその軸をリセット
- プロット内: どのモードも無いときの左ドラッグで矩形ズーム、右クリックで1つ前の矩形ズームの前に戻す、
  ダブルクリックでサブプロットの X・Y・Y2 をリセット、中ボタンのドラッグでパン

計算はピクセル基準にする(データ座標で差を取ると、範囲を変えるたびに基準の座標がずれる。対数・反転の軸もそのまま扱える)。
リセットは描画と同じ apply_axis_range を通すので、設定の最小・最大か、自動なら全体の範囲になる。
"""
import logging
import weakref
from collections import namedtuple

import numpy as np
from matplotlib.transforms import Bbox
from PySide6.QtCore import Qt

from graphica.core.axis_settings import axis_inverted
from graphica.gui import app_settings
from graphica.gui.rendering.appearance import apply_axis_range, range_signature, waterfall_x_shift
from graphica.gui.tools.manager import MOUSE_MODES_BY_NAME
from graphica.gui.tools.pointer import legend_at

logger = logging.getLogger(__name__)

# 軸の上のホイールで、マウスのホイール1段あたりに何倍にするか(環境設定の「拡大の速さ」)
WHEEL_ZOOM_BASES = {'slow': 1.1, 'normal': 1.2, 'fast': 1.4}
# 1回の通知で変わる量の上限(トラックパッドを速く払っても一気に跳ばないように)
MAX_WHEEL_ZOOM_PER_EVENT = 1.5
# Qt の angleDelta でホイールの1段(1/8 度単位で 15 度)
WHEEL_NOTCH_ANGLE = 120
# 目盛りラベルを隠した軸(軸の共有など)でもつかめるよう、帯はプロットの枠から最低これだけ外へ取る
AXIS_BAND_MIN_PX = 15
# 矩形の幅か高さがこれ未満なら、ズームせずクリックとみなす(matplotlib のズームと同じ)
RECT_ZOOM_MIN_PX = 5

# axis_key は 'x' / 'y' / 'y2'。ax は範囲を変える Axes('y2' なら第2Y軸)
AxisBand = namedtuple("AxisBand", "subplot_index axis_key ax bbox")
# ドラッグの始めの変換を固定して持つ(動かしている最中の変換で戻すと、動かした分だけ基準がずれる)
_PanTarget = namedtuple("_PanTarget", "ax which inverse span")

_AXIS_CURSORS = {
    'x': Qt.CursorShape.SizeHorCursor,
    'y': Qt.CursorShape.SizeVerCursor,
    'y2': Qt.CursorShape.SizeVerCursor,
}


class ViewNavigationTool:

    def __init__(self, app):
        self._app = app
        self._pan = None            # {'button', 'start', 'targets', 'subplot_index', 'axis_keys'}
        self._rect_zoom = None      # {'subplot_index', 'start', 'bbox'}
        # サブプロットの主の Axes → 矩形ズームの前の範囲の列。描き直しで Axes が作り直されたら一緒に消える
        self._zoom_history = weakref.WeakKeyDictionary()
        self._bands = None
        self._bands_key = None
        self._cursor_shape = None

    def connect(self):
        canvas = self._app.canvas
        canvas.mpl_connect('scroll_event', self.on_scroll)
        canvas.mpl_connect('button_press_event', self.on_press)
        canvas.mpl_connect('motion_notify_event', self.on_motion)
        canvas.mpl_connect('button_release_event', self.on_release)
        # 帯は目盛りラベルの大きさで変わるので、描くたびに測り直す
        canvas.mpl_connect('draw_event', self._invalidate_bands)

    # --- サブプロットと軸の帯 ---

    def _subplot_axes(self, index):
        canvas = self._app.canvas
        secondary_axes = canvas.all_secondary_axes
        secondary = secondary_axes[index] if index < len(secondary_axes) else None
        return canvas.all_axes[index], secondary

    def subplot_index_of(self, ax):
        canvas = self._app.canvas
        for index, primary in enumerate(canvas.all_axes):
            if ax is primary:
                return index
        for index, secondary in enumerate(canvas.all_secondary_axes):
            if secondary is not None and ax is secondary:
                return index
        return None

    def _invalidate_bands(self, _event=None):
        self._bands = None
        # サブプロットが減ったら、もう無い番号の範囲は捨てる(あとで同じ番号が増えたときに古い範囲が出ないように)
        overrides = self._app.canvas.view_overrides
        for index in [i for i in overrides if i >= len(self._app.canvas.all_axes)]:
            del overrides[index]

    # --- マウスで変えた範囲を、描き直しても保つ(当て直すのは rendering/appearance.apply_view_override) ---

    def remember_view(self, subplot_index, axis_keys):
        settings_list = self._app.project.all_plot_settings
        if subplot_index >= len(settings_list) or subplot_index >= len(self._app.canvas.all_axes):
            return
        primary, secondary = self._subplot_axes(subplot_index)
        entry = self._app.canvas.view_overrides.setdefault(subplot_index, {})
        for axis_key in axis_keys:
            ax = secondary if axis_key == 'y2' else primary
            if ax is None:
                continue
            limits = ax.get_xlim() if axis_key == 'x' else ax.get_ylim()
            entry[axis_key] = (tuple(float(v) for v in limits), range_signature(settings_list[subplot_index], axis_key))
        self._view_changed()

    def forget_view(self, subplot_index, axis_keys=('x', 'y', 'y2')):
        entry = self._app.canvas.view_overrides.get(subplot_index)
        if entry is None:
            return
        for axis_key in axis_keys:
            entry.pop(axis_key, None)
        if not entry:
            del self._app.canvas.view_overrides[subplot_index]
        self._view_changed()

    def forget_all_views(self):
        self._app.canvas.view_overrides.clear()
        self._view_changed()

    def _view_changed(self):
        """書き出しのプレビューは表示中の範囲で描くので、範囲が変わったら描き直させる(見えていなければ何もしない)。"""
        panel = getattr(self._app, 'export_preview_panel', None)
        if panel is not None:
            panel.refresh_preview()

    def remember_x_of_every_subplot(self):
        """ミニマップは全部の軸の X を変えるので、全部のサブプロットの X を覚える。"""
        for index in range(len(self._app.canvas.all_axes)):
            self.remember_view(index, ['x'])

    def axis_bands(self):
        canvas = self._app.canvas
        key = tuple(
            (id(ax), tuple(ax.bbox.bounds)) for ax in list(canvas.all_axes) + list(canvas.all_secondary_axes)
            if ax is not None
        )
        if self._bands is None or self._bands_key != key:
            self._bands = self._measure_bands()
            self._bands_key = key
        return self._bands

    def _measure_bands(self):
        canvas = self._app.canvas
        renderer = canvas.get_renderer()
        bands = []
        for index, ax in enumerate(canvas.all_axes):
            if not ax.get_visible():
                continue
            _, secondary = self._subplot_axes(index)
            box = ax.bbox
            bands.append(AxisBand(index, 'x', ax, _outer_band(box, ax.xaxis, renderer, 'x')))
            bands.append(AxisBand(index, 'y', ax, _outer_band(box, ax.yaxis, renderer, 'y')))
            if secondary is not None:
                bands.append(AxisBand(index, 'y2', secondary, _outer_band(box, secondary.yaxis, renderer, 'y')))
        return bands

    def axis_band_at(self, x, y):
        """プロットの外の (x, y)(Figure のピクセル、原点は左下)にある軸の帯。無ければ None。"""
        if x is None or y is None:
            return None
        for band in self.axis_bands():
            if band.bbox.contains(x, y):
                return band
        return None

    # --- 範囲の計算 ---

    @staticmethod
    def _pixel_span(ax, which):
        box = ax.bbox
        return (box.x0, box.x1) if which == 'x' else (box.y0, box.y1)

    @staticmethod
    def _set_limits_from_pixels(ax, which, pixels, inverse):
        """ピクセルの (始め, 終わり) を inverse でデータ座標に戻して範囲にする。枠の始め側が範囲の始め側なので反転もそのまま残る。"""
        box = ax.bbox
        if which == 'x':
            points = [(p, box.y0) for p in pixels]
        else:
            points = [(box.x0, p) for p in pixels]
        values = inverse.transform(points)[:, 0 if which == 'x' else 1]
        if not np.all(np.isfinite(values)) or values[0] == values[1]:
            return False
        if which == 'x':
            ax.set_xlim(values[0], values[1])
        else:
            ax.set_ylim(values[0], values[1])
        return True

    def zoom_axis(self, band, center_px, scale):
        """band の軸を、ピクセル位置 center_px を中心に scale 倍(1 未満で拡大)にする。"""
        which = 'x' if band.axis_key == 'x' else 'y'
        p0, p1 = self._pixel_span(band.ax, which)
        pixels = (center_px + (p0 - center_px) * scale, center_px + (p1 - center_px) * scale)
        if not self._set_limits_from_pixels(band.ax, which, pixels, band.ax.transData.inverted()):
            return False
        self.remember_view(band.subplot_index, [band.axis_key])
        return True

    def reset_axis(self, subplot_index, axis_key):
        """設定どおりの範囲(最小・最大を決めていればそれ、自動なら全体)に戻す。"""
        settings_list = self._app.project.all_plot_settings
        if subplot_index >= len(settings_list):
            return
        primary, secondary = self._subplot_axes(subplot_index)
        ax = secondary if axis_key == 'y2' else primary
        if ax is None:
            return
        settings = settings_list[subplot_index]
        is_category_x = self._app.canvas.axis_is_category_x
        shift = waterfall_x_shift(self._app.canvas, subplot_index) if axis_key == 'x' else (0.0, 0.0)
        apply_axis_range(ax, settings, axis_key,
                         subplot_index < len(is_category_x) and is_category_x[subplot_index], shift)
        # set_xlim/set_ylim は反転を解くので、設定どおりに戻す
        (ax.xaxis if axis_key == 'x' else ax.yaxis).set_inverted(axis_inverted(settings, axis_key))
        self.forget_view(subplot_index, [axis_key])

    def reset_subplot(self, subplot_index):
        _, secondary = self._subplot_axes(subplot_index)
        for axis_key in ('x', 'y', 'y2') if secondary is not None else ('x', 'y'):
            self.reset_axis(subplot_index, axis_key)
        primary, _ = self._subplot_axes(subplot_index)
        self._zoom_history.pop(primary, None)

    def _snapshot(self, subplot_index):
        primary, secondary = self._subplot_axes(subplot_index)
        return {
            'x': primary.get_xlim(),
            'y': primary.get_ylim(),
            'y2': secondary.get_ylim() if secondary is not None else None,
            # 戻したときに「設定どおりの範囲」だったのか「マウスで変えた範囲」だったのかも戻すため
            'overrides': dict(self._app.canvas.view_overrides.get(subplot_index, {})),
        }

    def zoom_to_rect(self, subplot_index, start, end):
        """ピクセルの2点で囲んだ範囲にする。幅か高さが RECT_ZOOM_MIN_PX 未満なら何もしない。ズームしたら True。"""
        (x0, y0), (x1, y1) = start, end
        if abs(x1 - x0) < RECT_ZOOM_MIN_PX or abs(y1 - y0) < RECT_ZOOM_MIN_PX:
            return False
        primary, secondary = self._subplot_axes(subplot_index)
        before = self._snapshot(subplot_index)
        xs, ys = sorted((x0, x1)), sorted((y0, y1))
        self._set_limits_from_pixels(primary, 'x', xs, primary.transData.inverted())
        self._set_limits_from_pixels(primary, 'y', ys, primary.transData.inverted())
        if secondary is not None:
            self._set_limits_from_pixels(secondary, 'y', ys, secondary.transData.inverted())
        self._zoom_history.setdefault(primary, []).append(before)
        self.remember_view(subplot_index, ['x', 'y', 'y2'])
        return True

    def zoom_back(self, subplot_index):
        """1つ前の矩形ズームの前の範囲に戻す。戻せたら True。"""
        primary, secondary = self._subplot_axes(subplot_index)
        history = self._zoom_history.get(primary)
        if not history:
            return False
        limits = history.pop()
        primary.set_xlim(limits['x'])
        primary.set_ylim(limits['y'])
        if secondary is not None and limits['y2'] is not None:
            secondary.set_ylim(limits['y2'])
        if limits['overrides']:
            self._app.canvas.view_overrides[subplot_index] = dict(limits['overrides'])
        else:
            self._app.canvas.view_overrides.pop(subplot_index, None)
        self._view_changed()
        return True

    def _start_pan(self, button, event, targets, subplot_index, axis_keys):
        frozen = [
            _PanTarget(ax, which, ax.transData.inverted().frozen(), self._pixel_span(ax, which))
            for ax, which in targets
        ]
        self._pan = {'button': button, 'start': (event.x, event.y), 'targets': frozen,
                     'subplot_index': subplot_index, 'axis_keys': axis_keys}

    def _pan_to(self, event):
        start_x, start_y = self._pan['start']
        for target in self._pan['targets']:
            delta = (event.x - start_x) if target.which == 'x' else (event.y - start_y)
            p0, p1 = target.span
            self._set_limits_from_pixels(target.ax, target.which, (p0 - delta, p1 - delta), target.inverse)

    # --- モードとの譲り合い ---

    def _active_mode(self):
        name = self._app._active_mouse_mode()
        return MOUSE_MODES_BY_NAME.get(name) if name else None

    # --- イベント ---

    def on_scroll(self, event):
        if event.inaxes is not None:
            return
        band = self.axis_band_at(event.x, event.y)
        if band is None:
            return
        notches = wheel_notches(event)
        if not notches:
            return
        base = WHEEL_ZOOM_BASES.get(app_settings.WHEEL_ZOOM_SPEED.read(self._app.settings), WHEEL_ZOOM_BASES['normal'])
        scale = min(max(base ** (-notches), 1 / MAX_WHEEL_ZOOM_PER_EVENT), MAX_WHEEL_ZOOM_PER_EVENT)
        center = event.x if band.axis_key == 'x' else event.y
        if self.zoom_axis(band, center, scale):
            self._app.canvas.draw_idle()

    def on_press(self, event):
        if self._pan is not None or self._rect_zoom is not None:
            return
        if event.inaxes is None:
            self._on_press_outside_plot(event)
            return
        index = self.subplot_index_of(event.inaxes)
        if index is None:
            return
        primary, secondary = self._subplot_axes(index)
        mode = self._active_mode()

        if event.button == 2:
            targets = [(primary, 'x'), (primary, 'y')] + ([(secondary, 'y')] if secondary is not None else [])
            self._start_pan(2, event, targets, index, ['x', 'y', 'y2'])
        elif event.button == 3:
            if (mode is None or not mode.uses_right_click) and self.zoom_back(index):
                self._app.canvas.draw_idle()
        elif event.button == 1:
            if legend_at(self._app.canvas, event) is not None:
                return
            if event.dblclick:
                if mode is None or not mode.uses_left_click:
                    self.reset_subplot(index)
                    self._app.canvas.draw_idle()
            elif mode is None:
                self._rect_zoom = {'subplot_index': index, 'start': (event.x, event.y), 'bbox': primary.bbox}

    def _on_press_outside_plot(self, event):
        if event.button != 1:
            return
        band = self.axis_band_at(event.x, event.y)
        if band is None:
            self._start_rect_zoom_from_margin(event)
            return
        # 枠の外へドラッグした凡例が帯に重なっていれば、凡例のドラッグに譲る
        if legend_at(self._app.canvas, event) is not None:
            return
        if event.dblclick:
            self.reset_axis(band.subplot_index, band.axis_key)
            self._app.canvas.draw_idle()
            return
        self._start_pan(1, event, [(band.ax, 'x' if band.axis_key == 'x' else 'y')],
                        band.subplot_index, [band.axis_key])

    def _start_rect_zoom_from_margin(self, event):
        """軸の帯の外の余白から、いちばん近いサブプロットの矩形ズームを、その縁に合わせた位置から始める(縁ぴったりまで囲めるように)。"""
        if event.dblclick or event.x is None or event.y is None or self._active_mode() is not None:
            return
        if legend_at(self._app.canvas, event) is not None:
            return
        nearest = None
        for index, ax in enumerate(self._app.canvas.all_axes):
            if not ax.get_visible():
                continue
            box = ax.bbox
            dx = max(box.x0 - event.x, 0, event.x - box.x1)
            dy = max(box.y0 - event.y, 0, event.y - box.y1)
            distance = dx * dx + dy * dy
            if nearest is None or distance < nearest[0]:
                nearest = (distance, index, box)
        if nearest is None:
            return
        _, index, box = nearest
        start = (min(max(event.x, box.x0), box.x1), min(max(event.y, box.y0), box.y1))
        self._rect_zoom = {'subplot_index': index, 'start': start, 'bbox': box}

    def on_motion(self, event):
        if self._pan is not None:
            if event.x is not None and event.y is not None:
                self._pan_to(event)
                self._app.canvas.draw_idle()
            return
        if self._rect_zoom is not None:
            if event.x is not None and event.y is not None:
                self._draw_rubberband(self._rect_zoom['start'], self._clamp_to_plot(event))
            return
        band = self.axis_band_at(event.x, event.y) if event.inaxes is None else None
        self._set_cursor(_AXIS_CURSORS[band.axis_key] if band is not None else None)

    def on_release(self, event):
        if self._pan is not None:
            if event.button == self._pan['button']:
                state, self._pan = self._pan, None
                self.remember_view(state['subplot_index'], state['axis_keys'])
            return
        if self._rect_zoom is not None and event.button == 1:
            state, self._rect_zoom = self._rect_zoom, None
            self._remove_rubberband()
            if event.x is None or event.y is None:
                return
            if self.zoom_to_rect(state['subplot_index'], state['start'], self._clamp_to_plot(event, state['bbox'])):
                self._app.canvas.draw_idle()

    # --- 表示 ---

    def _clamp_to_plot(self, event, bbox=None):
        box = bbox if bbox is not None else self._rect_zoom['bbox']
        return (min(max(event.x, box.x0), box.x1), min(max(event.y, box.y0), box.y1))

    def _draw_rubberband(self, start, end):
        canvas = self._app.canvas
        # Qt の座標は原点が左上(matplotlib の NavigationToolbar2QT.draw_rubberband と同じ変換)
        height = canvas.figure.bbox.height
        x0, y0 = start
        x1, y1 = end
        y0, y1 = height - y0, height - y1
        canvas.drawRectangle([int(v) for v in (x0, y0, x1 - x0, y1 - y0)])

    def _remove_rubberband(self):
        self._app.canvas.drawRectangle(None)

    def _set_cursor(self, shape):
        if shape == self._cursor_shape:
            return
        canvas = self._app.canvas
        if shape is None:
            canvas.unsetCursor()
        else:
            canvas.setCursor(shape)
        self._cursor_shape = shape


def wheel_notches(event):
    """ホイールの動きを「マウスのホイール何段分か」で返す(上で正)。指を離した後の慣性の分は 0。

    matplotlib の step は、OS がピクセル単位の量を渡すとき(macOS のトラックパッドや Magic Mouse)はピクセル数になり、
    1回で何十にもなる。Qt の angleDelta はどの OS でも渡されるので、そちらを段の数に直す。
    """
    gui_event = getattr(event, 'guiEvent', None)
    if gui_event is None or not hasattr(gui_event, 'angleDelta'):
        return event.step
    if hasattr(gui_event, 'phase') and gui_event.phase() == Qt.ScrollPhase.ScrollMomentum:
        return 0.0
    return gui_event.angleDelta().y() / WHEEL_NOTCH_ANGLE


def _outer_band(box, axis, renderer, which):
    """プロットの枠の外側の、axis の目盛りラベル(と軸ラベル)がある帯。帯の長さはプロットの枠の辺に合わせる。"""
    try:
        tight = axis.get_tightbbox(renderer)
    except (ValueError, RuntimeError):
        logger.debug("軸の大きさを測れませんでした", exc_info=True)
        tight = None
    label_side = axis.get_label_position()
    if which == 'x':
        if label_side == 'top':
            outer = max(box.y1 + AXIS_BAND_MIN_PX, tight.y1 if tight is not None else -np.inf)
            return Bbox.from_extents(box.x0, box.y1, box.x1, outer)
        outer = min(box.y0 - AXIS_BAND_MIN_PX, tight.y0 if tight is not None else np.inf)
        return Bbox.from_extents(box.x0, outer, box.x1, box.y0)
    if label_side == 'right':
        outer = max(box.x1 + AXIS_BAND_MIN_PX, tight.x1 if tight is not None else -np.inf)
        return Bbox.from_extents(box.x1, box.y0, outer, box.y1)
    outer = min(box.x0 - AXIS_BAND_MIN_PX, tight.x0 if tight is not None else np.inf)
    return Bbox.from_extents(outer, box.y0, box.x0, box.y1)
