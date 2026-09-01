# gui/mixins/region_highlight_mixin.py
"""
グラフ上への領域ハイライト(項目C-701)。ドラッグでX方向に大きく動かすと
縦帯(axvspan)、Y方向に大きく動かすと横帯(axhspan)を追加する。

既存のテキスト/矢印注釈(gui/mixins/annotation_mixin.py)と同じ
project.all_plot_settings[軸インデックス]['annotations'] リストに
type='vspan'/'hspan'として追加することで、永続化(既にプロジェクト保存の対象)
とUndo/Redo(SetAnnotationsCommand)・実際の描画削除処理(_add_annotation、
AnnotationMixin側で定義済み)をそのまま共有する。データ座標に紐づくため、
データセットを差し替えても(項目C-103の再読み込み等)位置は保たれる。

ドラッグ中のプレビュー描画は、他のモード(範囲選択=RangeSelectMixin、
スライス抽出=SliceExtractionMixin)と同じ「Rectangleパッチを都度作り直す」
パターンを踏襲する(fig.clf()で再描画されるメインキャンバスに対応するため)。
"""
import logging

from matplotlib.patches import Rectangle
from PySide6.QtWidgets import QMessageBox

from core.commands import SetAnnotationsCommand

logger = logging.getLogger(__name__)

# ドラッグとみなす最小移動距離(ピクセル)。これ未満はクリックとみなし何もしない
# (誤クリックで意図しない極小の帯が追加されるのを防ぐ)。
REGION_HIGHLIGHT_DRAG_THRESHOLD_PX = 5
# 右クリックで削除対象とみなす、クリック位置から帯の端までの許容ピクセル距離
# (帯の内側をクリックした場合は距離0とみなすため、実質「帯の外側でも際どい位置」を救う用途)
REGION_HIGHLIGHT_DELETE_TOLERANCE_PX = 10

REGION_HIGHLIGHT_DEFAULT_COLOR = '#F2A72B'
REGION_HIGHLIGHT_DEFAULT_ALPHA = 0.18


class RegionHighlightMixin:
    def _toggle_region_highlight_mode(self, checked):
        """
        「領域ハイライト」ツールバーボタンが押されたときの処理。
        他のクリック/ドラッグ系モードと同時に有効だと同じ操作が競合するため排他にする。
        """
        self.region_highlight_mode_enabled = checked

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
            if getattr(self, 'slice_extraction_mode_enabled', False):
                self.slice_extraction_action.setChecked(False)
                self._toggle_slice_extraction_mode(False)

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
        """ドラッグ中のプレビュー矩形を取り除く。fig.clf()で既に破棄されている
        場合(再描画がドラッグ中に割り込んだ場合)に備えてValueError/
        NotImplementedErrorは無視する(range_select_mixin.pyと同じ防御)。"""
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

        if event.button == 3:  # 右クリック: 既存の領域ハイライトを削除
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
            return  # 別のAxes上、またはAxes外でリリースされた場合は何もしない

        end_x, end_y = event.xdata, event.ydata
        orientation = self._region_highlight_orientation(axes, start_x, start_y, end_x, end_y)
        if orientation is None:
            return  # 動いていない(クリックのみ)は追加とみなさない

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
        """
        ドラッグ開始点から現在位置までのピクセル距離を見て、'vspan'(横方向に
        大きく動いた=縦帯)/'hspan'(縦方向に大きく動いた=横帯)/None(まだ
        ドラッグとみなせるほど動いていない)のいずれかを返す。
        """
        start_px = axes.transData.transform((start_x, start_y))
        current_px = axes.transData.transform((current_x, current_y))
        dx = abs(current_px[0] - start_px[0])
        dy = abs(current_px[1] - start_px[1])
        if max(dx, dy) < REGION_HIGHLIGHT_DRAG_THRESHOLD_PX:
            return None
        return 'vspan' if dx >= dy else 'hspan'

    def _try_delete_region_near(self, event):
        """
        右クリックされた位置を含む領域ハイライトを探し、確認の上で削除する。
        複数の領域が重なっている場合は、リスト内で最後に追加されたもの
        (通常は描画順で最も手前=視覚的に一番上に見えるもの)を対象にする。
        """
        axis_index = self._find_axis_index(event.inaxes)
        if axis_index is None:
            return

        settings = self.project.all_plot_settings[axis_index]
        annotations = settings.get('annotations', [])

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
                target_index = i  # 後で見つかったものほど優先(=リストの後ろ=手前)

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
