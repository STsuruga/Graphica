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
            # 排他制御は登録簿(gui/mixins/mouse_mode_mixin.py の MOUSE_MODES)に
            # 集約している。8つ目のモードを足すときもここは変更不要。
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
        """ドラッグ中のプレビュー矩形を取り除く。fig.clf()で既に破棄されて
        いる場合(再描画がドラッグ中に割り込んだ場合)に備えてValueError/
        NotImplementedErrorは無視する(gui/canvas.pyのset_highlighted_points
        と同じ防御)。ブリッティング用にキャプチャしていた背景(_range_select_
        background)もここで一緒に破棄する。"""
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
        # ブリッティング(項目154、C-1002)によるドラッグ追従の高速化: ドラッグ
        # 開始時点の見た目(データセット等、選択矩形以外の全て)を1回だけ
        # ビットマップとしてキャプチャしておく。以降のmotionイベントでは
        # 図全体を再描画(draw_idle、データセット数が多いほど重い)せず、
        # このキャプチャを復元してから選択矩形だけを描き直す(blit)。
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
            # ★ animated=True: 通常のdraw()/draw_idle()の描画対象から外れ、
            #   下のblit()を通じてのみ画面に反映される(matplotlibのブリッティング
            #   の基本パターン)。既存矩形が無い最初のmotionイベントでのみ作成し、
            #   以降は同じ矩形の座標だけを更新する(_clear_range_select_previewとは
            #   異なり、motionのたびに削除・再作成はしない)。
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
            # 背景キャプチャに失敗していた場合(例: 何らかの理由でpress直後に
            # Axesが再生成された等)は、安全側として従来通りの全体再描画にフォールバックする。
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

        # ★ 改善ボード A-1: ウォーターフォール(積み重ね)有効時、トレースは
        # 表示X = データX + index * offset_x の位置に描かれている。ドラッグで
        # 得られる x_min/x_max は「表示座標」なので、生の dataset.x_data と
        # 直接比較すると積み重ね2本目以降で意図と違う行がマスクされる
        # (あるいは1件もマスクされない)。データ座標へ逆変換してから比較する。
        # Xオフセットは平行移動なので x_min <= x_max の大小関係は保たれる。
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