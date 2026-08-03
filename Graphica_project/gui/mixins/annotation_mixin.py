# gui/mixins/annotation_mixin.py
"""
グラフ上の任意の位置にテキスト注釈・矢印注釈を追加できる「注釈モード」をまとめた Mixin。

注釈は project.all_plot_settings[軸インデックス]['annotations'] に
{'id','type'('text'/'arrow'),'text','xy','xytext','color'} の辞書として保持される。
all_plot_settings は既にプロジェクト保存(pickle)の対象になっているため、
注釈も自動的にプロジェクトファイルに保存/復元される(追加の永続化コードは不要)。

注釈の追加/削除は SetAnnotationsCommand 経由で self.undo_stack にpushされ、
他のデータセットプロパティ変更などと同様にUndo/Redoで元に戻せる。
"""
import uuid
import logging

from PySide6.QtWidgets import QInputDialog, QMessageBox

from core.commands import SetAnnotationsCommand

logger = logging.getLogger(__name__)

# 「クリック」と「ドラッグ」を区別するためのピクセル距離のしきい値
ANNOTATION_CLICK_THRESHOLD_PX = 5
# 右クリックで削除対象とみなす、注釈位置からの許容ピクセル距離
ANNOTATION_DELETE_TOLERANCE_PX = 15


class AnnotationMixin:
    def _toggle_annotation_mode(self, checked):
        """
        「注釈」ツールバーボタンが押されたときの処理。
        データカーソルモードと同時に有効にすると、同じクリック操作が両方の
        機能に反応してしまい紛らわしいため、排他的にする。
        """
        self.annotation_mode_enabled = checked

        if checked:
            if getattr(self, 'cursor_mode_enabled', False):
                self.cursor_action.setChecked(False)
                self._toggle_cursor_mode(False)

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

    def _find_axis_index(self, ax):
        """指定されたAxesが self.all_axes / self.all_secondary_axes の何番目かを返す(見つからなければNone)"""
        if ax in self.all_axes:
            return self.all_axes.index(ax)
        if ax in self.all_secondary_axes:
            return self.all_secondary_axes.index(ax)
        return None

    def _on_annotation_press(self, event):
        """マウスボタンが押されたときの処理(button_press_event)"""
        if not self.annotation_mode_enabled or event.inaxes is None or event.xdata is None:
            return

        if event.button == 3:  # 右クリック: 既存の注釈を削除
            self._try_delete_annotation_near(event)
            return

        self._annotation_drag_start = (event.inaxes, event.xdata, event.ydata)

    def _on_annotation_release(self, event):
        """マウスボタンが離されたときの処理(button_release_event)"""
        if not self.annotation_mode_enabled or self._annotation_drag_start is None:
            return

        start_ax, start_x, start_y = self._annotation_drag_start
        self._annotation_drag_start = None

        # 別のAxes上でリリースされた、またはAxesの外側でリリースされた場合は何もしない
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
            # ほぼ動いていない = 「クリック」とみなし、テキスト注釈を追加する
            text, ok = QInputDialog.getText(self, "テキスト注釈の追加", "表示するテキスト:")
            if not ok or not text.strip():
                return
            self._add_annotation(axis_index, {
                'type': 'text', 'text': text.strip(),
                'xy': (start_x, start_y), 'xytext': (start_x, start_y),
                'color': '#000000',
            })
        else:
            # 一定以上動いた = 「ドラッグ」とみなし、矢印注釈を追加する
            text, ok = QInputDialog.getText(self, "矢印注釈の追加", "ラベル(空欄可):")
            if not ok:
                return
            self._add_annotation(axis_index, {
                'type': 'arrow', 'text': text.strip(),
                'xy': (end_x, end_y), 'xytext': (start_x, start_y),
                'color': '#000000',
            })

    def _add_annotation(self, axis_index, annotation):
        """
        指定した軸の注釈リストに新しい注釈を追加する。
        既存のリストを直接書き換えず新しいリストに差し替えることで、
        _on_layout_changed 等での浅いコピーによる意図しない共有を避ける。
        Undo/Redo可能にするため、変更はSetAnnotationsCommand経由で行う。
        """
        annotation = dict(annotation)
        annotation['id'] = uuid.uuid4().hex

        settings = self.project.all_plot_settings[axis_index]
        old_annotations = list(settings.get('annotations', []))
        new_annotations = old_annotations + [annotation]

        command = SetAnnotationsCommand(
            self.project, axis_index, old_annotations, new_annotations,
            self._update_plot_appearance, description="注釈の追加"
        )
        self.undo_stack.push(command)

    def _try_delete_annotation_near(self, event):
        """右クリックされた位置に最も近い注釈を探し、確認の上で削除する"""
        axis_index = self._find_axis_index(event.inaxes)
        if axis_index is None:
            return

        settings = self.project.all_plot_settings[axis_index]
        annotations = settings.get('annotations', [])
        if not annotations:
            return

        ax = event.inaxes
        click_px = ax.transData.transform((event.xdata, event.ydata))

        best_index, best_distance = None, None
        for i, ann in enumerate(annotations):
            pos = ann.get('xytext') or ann.get('xy')
            pos_px = ax.transData.transform(pos)
            distance = ((pos_px[0] - click_px[0]) ** 2 + (pos_px[1] - click_px[1]) ** 2) ** 0.5
            if best_distance is None or distance < best_distance:
                best_distance, best_index = distance, i

        if best_index is None or best_distance > ANNOTATION_DELETE_TOLERANCE_PX:
            return

        target = annotations[best_index]
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
