# gui/mixins/annotation_mixin.py
"""
グラフ上の任意の位置にテキスト注釈・矢印注釈を追加できる「注釈モード」をまとめた Mixin。

注釈は project.all_plot_settings[軸インデックス]['annotations'] に
{'id','type'('text'/'arrow'),'text','xy','xytext','color'} の辞書として保持される。
矢印注釈('arrow')は追加で'arrow_style'('single'(既定)/'double'/'bracket'、
項目C-703)・'arrow_curvature'(float、既定0.0で直線)を持つ(gui/canvas.pyの
_draw_annotationsが参照。両キーとも省略時は既定値にフォールバックするため、
これらのキーを持たない既存の保存済み注釈も同じ見た目のまま読み込める)。
all_plot_settings は既にプロジェクト保存(pickle)の対象になっているため、
注釈も自動的にプロジェクトファイルに保存/復元される(追加の永続化コードは不要)。

注釈の追加/削除は SetAnnotationsCommand 経由で self.undo_stack にpushされ、
他のデータセットプロパティ変更などと同様にUndo/Redoで元に戻せる。
"""
import uuid
import logging

from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from core.commands import SetAnnotationsCommand
from gui.dialogs import ArrowAnnotationDialog

logger = logging.getLogger(__name__)

# 「クリック」と「ドラッグ」を区別するためのピクセル距離のしきい値
ANNOTATION_CLICK_THRESHOLD_PX = 5
# 右クリックで削除対象とみなす、注釈位置からの許容ピクセル距離
ANNOTATION_DELETE_TOLERANCE_PX = 15

# スナップ・トゥ・グリッド(項目84)の既定値。既定では無効(=従来どおりの挙動)であり、
# 環境設定ダイアログで有効化するとテキスト/矢印注釈の配置先がピクセル単位の
# グリッドに吸着するようになる。
DEFAULT_SNAP_TO_GRID_ENABLED = False
DEFAULT_SNAP_GRID_INTERVAL_PX = 10


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
            if getattr(self, 'range_select_mode_enabled', False):
                self.range_select_action.setChecked(False)
                self._toggle_range_select_mode(False)
            if getattr(self, 'peak_placement_mode_enabled', False):
                self.peak_placement_action.setChecked(False)
                self._toggle_peak_placement_mode(False)
            if getattr(self, 'slice_extraction_mode_enabled', False):
                self.slice_extraction_action.setChecked(False)
                self._toggle_slice_extraction_mode(False)
            if getattr(self, 'region_highlight_mode_enabled', False):
                self.region_highlight_action.setChecked(False)
                self._toggle_region_highlight_mode(False)

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
        """
        スナップ・トゥ・グリッド(項目84)が有効な場合、データ座標 (x, y) を
        いったんピクセル座標へ変換し、設定されたグリッド間隔(px)の倍数に
        丸めてからデータ座標へ戻す。「ピクセル単位で整列」という要件のため、
        データ空間ではなく画面ピクセル空間でスナップする必要がある。
        無効時は入力をそのまま返す(座標変換を経由しないため、従来の挙動と
        ピクセル単位で完全に一致する)。
        """
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
            snapped_x, snapped_y = self._snap_point_to_grid(start_ax, start_x, start_y)
            self._add_annotation(axis_index, {
                'type': 'text', 'text': text.strip(),
                'xy': (snapped_x, snapped_y), 'xytext': (snapped_x, snapped_y),
                'color': '#000000',
            })
        else:
            # 一定以上動いた = 「ドラッグ」とみなし、矢印注釈を追加する
            # (項目C-703: ラベルに加え、矢印の形状・曲率も選ばせる)
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
        """
        指定した軸の注釈リストに新しい注釈を追加する。
        既存のリストを直接書き換えず新しいリストに差し替えることで、
        _on_layout_changed 等での浅いコピーによる意図しない共有を避ける。
        Undo/Redo可能にするため、変更はSetAnnotationsCommand経由で行う。

        description はUndo/Redoメニューに表示される説明文(既定は手動追加時の
        「注釈の追加」)。項目C-413のフィット結果焼き込みのように、呼び出し元
        (例: dataset_mixin.py)がより具体的な説明文を渡せるようにするための
        任意引数で、既存の呼び出し(手動クリック/ドラッグでの注釈追加)は
        引数を渡さないため挙動は変わらない。
        """
        annotation = dict(annotation)
        annotation['id'] = uuid.uuid4().hex

        settings = self.project.all_plot_settings[axis_index]
        old_annotations = list(settings.get('annotations', []))
        new_annotations = old_annotations + [annotation]

        command = SetAnnotationsCommand(
            self.project, axis_index, old_annotations, new_annotations,
            self._update_plot_appearance, description=description
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
            ann_type = ann.get('type')
            if ann_type in ('vspan', 'hspan'):
                # 領域ハイライト(項目C-701)は 'xy'/'xytext' を持たず、削除は
                # 領域ハイライトモード側(_try_delete_region_near)が担当するため対象外。
                continue
            pos = ann.get('xytext') or ann.get('xy')
            if pos is None:
                continue
            # 統計値アンカーラベル(項目C-708)はAxes相対座標(0〜1)で位置を持つため、
            # データ座標変換(transData)ではなくtransAxesでピクセル位置を求める。
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
