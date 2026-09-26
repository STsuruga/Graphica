"""注釈モード: クリックでテキスト、ドラッグで矢印の注釈を置き、右クリックで消す。

注釈は all_plot_settings[軸]['annotations'] に {'id', 'type', 'text', 'xy', 'xytext', 'color'} で持ち、プロジェクトと一緒に
保存される。矢印は 'arrow_style' と 'arrow_curvature' も持つ(無ければ既定値)。追加と削除は SetAnnotationsCommand で Undo できる。
"""
import uuid
import logging

from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from graphica.core.axis_settings import axis_setting
from graphica.core.commands import SetAnnotationsCommand
from graphica.gui.app_settings import DEFAULT_SNAP_GRID_INTERVAL_PX
from graphica.gui.dialogs import ArrowAnnotationDialog

logger = logging.getLogger(__name__)

# これより動かなければクリック、動けばドラッグ
ANNOTATION_CLICK_THRESHOLD_PX = 5
ANNOTATION_DELETE_TOLERANCE_PX = 15



class AnnotationMixin:
    def _toggle_annotation_mode(self, checked):
        self.annotation_mode_enabled = checked

        if checked:
            self._deactivate_other_mouse_modes('annotation')

            self._annotation_press_cid = self.canvas.mpl_connect(
                'button_press_event', self._on_annotation_press
            )
            self._annotation_release_cid = self.canvas.mpl_connect(
                'button_release_event', self._on_annotation_release
            )
            self.statusBar().showMessage(
                "注釈モード: クリックでテキスト注釈、ドラッグで矢印注釈を追加します(右クリックで削除)", 5000
            )
        else:
            if self._annotation_press_cid is not None:
                self.canvas.mpl_disconnect(self._annotation_press_cid)
                self._annotation_press_cid = None
            if self._annotation_release_cid is not None:
                self.canvas.mpl_disconnect(self._annotation_release_cid)
                self._annotation_release_cid = None
            self._annotation_drag_start = None

    def _snap_point_to_grid(self, ax, x, y):
        """有効なら、データ座標を画面のピクセルに直してグリッドの倍数に丸め、データ座標に戻す(整列は画面上の話なので)。"""
        if not getattr(self, 'snap_to_grid_enabled', False):
            return x, y

        interval = getattr(self, 'snap_grid_interval_px', DEFAULT_SNAP_GRID_INTERVAL_PX)
        if not interval or interval <= 0:
            return x, y

        px, py = ax.transData.transform((x, y))
        snapped_px = round(px / interval) * interval
        snapped_py = round(py / interval) * interval
        data_x, data_y = ax.transData.inverted().transform((snapped_px, snapped_py))
        return data_x, data_y

    def _find_axis_index(self, ax):
        """all_axes / all_secondary_axes での番号。無ければ None。"""
        if ax in self.all_axes:
            return self.all_axes.index(ax)
        if ax in self.all_secondary_axes:
            return self.all_secondary_axes.index(ax)
        return None

    def _on_annotation_press(self, event):
        if not self.annotation_mode_enabled or event.inaxes is None or event.xdata is None:
            return

        if event.button == 3:  # 右クリックは削除
            self._try_delete_annotation_near(event)
            return

        self._annotation_drag_start = (event.inaxes, event.xdata, event.ydata)

    def _on_annotation_release(self, event):
        if not self.annotation_mode_enabled or self._annotation_drag_start is None:
            return

        start_ax, start_x, start_y = self._annotation_drag_start
        self._annotation_drag_start = None

        if event.inaxes is not start_ax or event.xdata is None:
            return

        axis_index = self._find_axis_index(start_ax)
        if axis_index is None:
            return

        end_x, end_y = event.xdata, event.ydata
        start_px = start_ax.transData.transform((start_x, start_y))
        end_px = start_ax.transData.transform((end_x, end_y))
        drag_distance_px = ((end_px[0] - start_px[0]) ** 2 + (end_px[1] - start_px[1]) ** 2) ** 0.5

        if drag_distance_px < ANNOTATION_CLICK_THRESHOLD_PX:
            text, ok = QInputDialog.getText(self, "テキスト注釈の追加", "表示するテキスト:")
            if not ok or not text.strip():
                return
            snapped_x, snapped_y = self._snap_point_to_grid(start_ax, start_x, start_y)
            self._add_annotation(axis_index, {
                'type': 'text', 'text': text.strip(),
                'xy': (snapped_x, snapped_y), 'xytext': (snapped_x, snapped_y),
                'color': '#000000',
            })
        else:
            dialog = ArrowAnnotationDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            text, arrow_style, arrow_curvature = dialog.get_settings()
            snapped_end_x, snapped_end_y = self._snap_point_to_grid(start_ax, end_x, end_y)
            snapped_start_x, snapped_start_y = self._snap_point_to_grid(start_ax, start_x, start_y)
            self._add_annotation(axis_index, {
                'type': 'arrow', 'text': text,
                'xy': (snapped_end_x, snapped_end_y), 'xytext': (snapped_start_x, snapped_start_y),
                'color': '#000000',
                'arrow_style': arrow_style,
                'arrow_curvature': arrow_curvature,
            })

    def _add_annotation(self, axis_index, annotation, description="注釈の追加"):
        """注釈を1つ足す。リストは差し替える(浅いコピーで共有されているリストを書き換えないように)。"""
        annotation = dict(annotation)
        annotation['id'] = uuid.uuid4().hex

        settings = self.project.all_plot_settings[axis_index]
        old_annotations = list(axis_setting(settings, 'annotations'))
        new_annotations = old_annotations + [annotation]

        command = SetAnnotationsCommand(
            self.project, axis_index, old_annotations, new_annotations,
            self._update_plot_appearance, description=description
        )
        self.undo_stack.push(command)

    def _try_delete_annotation_near(self, event):
        axis_index = self._find_axis_index(event.inaxes)
        if axis_index is None:
            return

        settings = self.project.all_plot_settings[axis_index]
        annotations = axis_setting(settings, 'annotations')
        if not annotations:
            return

        ax = event.inaxes
        click_px = ax.transData.transform((event.xdata, event.ydata))

        best_index, best_distance = None, None
        for i, ann in enumerate(annotations):
            ann_type = ann.get('type')
            if ann_type in ('vspan', 'hspan'):
                # 領域の強調は領域強調モードの側で消す
                continue
            if ann_type == 'inset':
                # 拡大図は xy を持たないので、角と大きさ(軸に対する座標)から中心を求めて当たり判定に使う
                from graphica.gui.canvas import _INSET_CORNER_ORIGINS
                x0, y0 = _INSET_CORNER_ORIGINS.get(ann.get('corner', '右上'), (0.55, 0.55))
                size = ann.get('size', 0.4)
                pos = (x0 + size / 2, y0 + size / 2)
                transform = ax.transAxes
            else:
                pos = ann.get('xytext') or ann.get('xy')
                if pos is None:
                    continue
                # 統計値のラベルは軸に対する座標(0〜1)で位置を持つ
                transform = ax.transAxes if ann_type == 'stat' else ax.transData
            pos_px = transform.transform(pos)
            distance = ((pos_px[0] - click_px[0]) ** 2 + (pos_px[1] - click_px[1]) ** 2) ** 0.5
            if best_distance is None or distance < best_distance:
                best_distance, best_index = distance, i

        if best_index is None or best_distance > ANNOTATION_DELETE_TOLERANCE_PX:
            return

        target = annotations[best_index]
        if target.get('type') == 'stat':
            label = "統計値アンカーラベル"
        elif target.get('type') == 'inset':
            label = "インセット(拡大図)"
        else:
            label = target.get('text') or ("矢印注釈" if target.get('type') == 'arrow' else "テキスト注釈")
        reply = QMessageBox.question(
            self, "注釈の削除", f"この注釈を削除しますか?\n\n{label}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        new_list = list(annotations)
        del new_list[best_index]

        command = SetAnnotationsCommand(
            self.project, axis_index, annotations, new_list,
            self._update_plot_appearance, description="注釈の削除"
        )
        self.undo_stack.push(command)
