"""注釈モード: クリックでテキスト、ドラッグで矢印の注釈を置き、右クリックのメニューで色を変える・消す。

注釈は all_plot_settings[軸]['annotations'] に {'id', 'type', 'text', 'xy', 'xytext', 'color'} で持ち、プロジェクトと一緒に
保存される。矢印は 'arrow_style' と 'arrow_curvature' も持つ(無ければ既定値)。追加と削除は SetAnnotationsCommand で Undo できる。
"""
import uuid
import logging

from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import QDialog, QMenu, QMessageBox

from graphica.gui import app_settings, notify
from graphica.core.axis_settings import axis_setting
from graphica.core.commands import SetAnnotationsCommand
from graphica.gui.app_settings import DEFAULT_SNAP_GRID_INTERVAL_PX
from graphica.gui.color_history import get_color_with_history
from graphica.gui.dialogs import ArrowAnnotationDialog, TextAnnotationDialog
from graphica.gui.tools.pointer import clamped_data_point, legend_at

logger = logging.getLogger(__name__)

# これより動かなければクリック、動けばドラッグ
ANNOTATION_CLICK_THRESHOLD_PX = 5
ANNOTATION_DELETE_TOLERANCE_PX = 15


class AnnotationTool:
    """状態はこのツールが持ち、PlotterApp の同じ名前は窓口(gui/tools/__init__.py)。"""

    # PlotterApp から同じ名前で読み書きできるもの(テスト・メニュー・ほかの mixin が使う)
    EXPOSED_NAMES = (
        '_add_annotation', '_annotation_drag_start', '_annotation_press_cid', '_annotation_release_cid',
        '_change_annotation_color', '_choose_annotation_action', '_confirm_and_delete_annotation',
        '_find_annotation_near', '_find_axis_index', '_on_annotation_context_menu', '_on_annotation_press',
        '_on_annotation_release', '_snap_point_to_grid', '_toggle_annotation_mode', '_try_delete_annotation_near',
        'annotation_mode_enabled',
        'snap_grid_interval_px', 'snap_to_grid_enabled',
    )

    def __init__(self, app):
        self._app = app
        self.annotation_mode_enabled = False
        self._annotation_press_cid = None
        self._annotation_release_cid = None
        self._annotation_drag_start = None     # (ax, x, y)
        self.snap_to_grid_enabled = app_settings.SNAP_TO_GRID_ENABLED.read(self._app.settings)
        self.snap_grid_interval_px = app_settings.SNAP_GRID_INTERVAL_PX.read(self._app.settings)

    def _toggle_annotation_mode(self, checked):
        self.annotation_mode_enabled = checked

        if checked:
            self._app._deactivate_other_mouse_modes('annotation')

            self._annotation_press_cid = self._app.canvas.mpl_connect(
                'button_press_event', self._on_annotation_press
            )
            self._annotation_release_cid = self._app.canvas.mpl_connect(
                'button_release_event', self._on_annotation_release
            )
            self._app.statusBar().showMessage(
                "注釈モード: クリックでテキスト注釈、ドラッグで矢印注釈を追加します(右クリックで色の変更・削除)", 5000
            )
        else:
            if self._annotation_press_cid is not None:
                self._app.canvas.mpl_disconnect(self._annotation_press_cid)
                self._annotation_press_cid = None
            if self._annotation_release_cid is not None:
                self._app.canvas.mpl_disconnect(self._annotation_release_cid)
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
        if ax in self._app.all_axes:
            return self._app.all_axes.index(ax)
        if ax in self._app.all_secondary_axes:
            return self._app.all_secondary_axes.index(ax)
        return None

    def _on_annotation_press(self, event):
        if not self.annotation_mode_enabled or event.inaxes is None or event.xdata is None:
            return
        if legend_at(self._app.canvas, event) is not None:
            return

        if event.button == 3:  # 右クリックは色の変更と削除のメニュー
            self._on_annotation_context_menu(event)
            return

        self._annotation_drag_start = (event.inaxes, event.xdata, event.ydata)

    def _on_annotation_release(self, event):
        if not self.annotation_mode_enabled or self._annotation_drag_start is None:
            return

        start_ax, start_x, start_y = self._annotation_drag_start
        self._annotation_drag_start = None

        # 軸の外で離したら、軸の縁で止めた位置を矢印の先にする
        end_point = clamped_data_point(start_ax, event)
        if end_point is None:
            return

        axis_index = self._find_axis_index(start_ax)
        if axis_index is None:
            return

        end_x, end_y = end_point
        start_px = start_ax.transData.transform((start_x, start_y))
        end_px = start_ax.transData.transform((end_x, end_y))
        drag_distance_px = ((end_px[0] - start_px[0]) ** 2 + (end_px[1] - start_px[1]) ** 2) ** 0.5

        if drag_distance_px < ANNOTATION_CLICK_THRESHOLD_PX:
            dialog = TextAnnotationDialog(self._app, settings=self._app.settings)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            text = dialog.get_text()
            if not text:
                return
            snapped_x, snapped_y = self._snap_point_to_grid(start_ax, start_x, start_y)
            self._add_annotation(axis_index, {
                'type': 'text', 'text': text,
                'xy': (snapped_x, snapped_y), 'xytext': (snapped_x, snapped_y),
                'color': dialog.color(),
            })
        else:
            dialog = ArrowAnnotationDialog(self._app, settings=self._app.settings)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            text, arrow_style, arrow_curvature = dialog.get_settings()
            snapped_end_x, snapped_end_y = self._snap_point_to_grid(start_ax, end_x, end_y)
            snapped_start_x, snapped_start_y = self._snap_point_to_grid(start_ax, start_x, start_y)
            self._add_annotation(axis_index, {
                'type': 'arrow', 'text': text,
                'xy': (snapped_end_x, snapped_end_y), 'xytext': (snapped_start_x, snapped_start_y),
                'color': dialog.color(),
                'arrow_style': arrow_style,
                'arrow_curvature': arrow_curvature,
            })

    def _add_annotation(self, axis_index, annotation, description="注釈の追加"):
        """注釈を1つ足す。リストは差し替える(浅いコピーで共有されているリストを書き換えないように)。"""
        annotation = dict(annotation)
        annotation['id'] = uuid.uuid4().hex

        settings = self._app.project.all_plot_settings[axis_index]
        old_annotations = list(axis_setting(settings, 'annotations'))
        new_annotations = old_annotations + [annotation]

        command = SetAnnotationsCommand(
            self._app.project, axis_index, old_annotations, new_annotations,
            self._app._update_plot_appearance, description=description
        )
        self._app.undo_stack.push(command)

    def _on_annotation_context_menu(self, event):
        found = self._find_annotation_near(event)
        if found is None:
            return
        axis_index, annotations, index = found
        choice = self._choose_annotation_action(annotations[index])
        if choice == 'color':
            self._change_annotation_color(axis_index, annotations, index)
        elif choice == 'delete':
            self._confirm_and_delete_annotation(axis_index, annotations, index)

    def _choose_annotation_action(self, annotation):
        """右クリックのメニューを出し、'color'・'delete'・None(閉じた)を返す。色を持てるのは文字と矢印だけ。"""
        menu = QMenu(self._app)
        color_action = menu.addAction("色を変更...") if annotation.get('type') in ('text', 'arrow') else None
        delete_action = menu.addAction("削除...")
        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return None
        if color_action is not None and chosen is color_action:
            return 'color'
        if chosen is delete_action:
            return 'delete'
        return None

    def _change_annotation_color(self, axis_index, annotations, index):
        current = annotations[index].get('color', '#000000')
        color = get_color_with_history(self._app.settings, self._app, initial=QColor(current))
        if not color.isValid() or color.name() == QColor(current).name():
            return
        new_list = list(annotations)
        new_list[index] = dict(annotations[index], color=color.name())
        command = SetAnnotationsCommand(
            self._app.project, axis_index, annotations, new_list,
            self._app._update_plot_appearance, description="注釈の色の変更"
        )
        self._app.undo_stack.push(command)

    def _try_delete_annotation_near(self, event):
        found = self._find_annotation_near(event)
        if found is not None:
            self._confirm_and_delete_annotation(*found)

    def _find_annotation_near(self, event):
        """クリックした位置のいちばん近い注釈の (軸の番号, その軸の注釈, 番号)。近くに無ければ None。"""
        axis_index = self._find_axis_index(event.inaxes)
        if axis_index is None:
            return None

        settings = self._app.project.all_plot_settings[axis_index]
        annotations = axis_setting(settings, 'annotations')
        if not annotations:
            return None

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
            return None
        return axis_index, annotations, best_index

    def _confirm_and_delete_annotation(self, axis_index, annotations, best_index):
        target = annotations[best_index]
        if target.get('type') == 'stat':
            label = "統計値アンカーラベル"
        elif target.get('type') == 'inset':
            label = "インセット(拡大図)"
        else:
            label = target.get('text') or ("矢印注釈" if target.get('type') == 'arrow' else "テキスト注釈")
        reply = notify.question(
            self._app, "注釈の削除", f"この注釈を削除しますか?\n\n{label}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        new_list = list(annotations)
        del new_list[best_index]

        command = SetAnnotationsCommand(
            self._app.project, axis_index, annotations, new_list,
            self._app._update_plot_appearance, description="注釈の削除"
        )
        self._app.undo_stack.push(command)
