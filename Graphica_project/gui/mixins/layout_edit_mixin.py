# gui/mixins/layout_edit_mixin.py
"""
自由配置レイアウト(項目37): 均等グリッドではなく、サブプロットをマウス
ドラッグで自由な位置・サイズに配置できるモードをまとめた Mixin。

各サブプロットの位置は project.all_plot_settings[index]['free_rect'] に
(left, bottom, width, height) の Figure正規化座標(0〜1)として保持される。
「自由配置レイアウト」チェックボックスがONの間は、サブプロット数は
行数×列数ではなく all_plot_settings の要素数そのものになり、
「+ プロット追加」「- プロット削除」ボタンで増減させる。
"""
import logging

logger = logging.getLogger(__name__)

# 右下端をドラッグしていると判定する許容ピクセル距離 (リサイズハンドル)
RESIZE_HANDLE_TOLERANCE_PX = 12
# ドラッグでサブプロットが潰れすぎないようにする最小サイズ (Figure正規化座標)
MIN_FREE_RECT_SIZE = 0.05


class LayoutEditMixin:
    def _on_toggle_free_layout(self, checked):
        """「自由配置レイアウト」チェックボックスが変更されたときの処理。"""
        self.project.layout_mode = 'free' if checked else 'grid'

        self.subplot_rows_spinbox.setEnabled(not checked)
        self.subplot_cols_spinbox.setEnabled(not checked)
        self.add_free_subplot_button.setEnabled(checked)
        self.remove_free_subplot_button.setEnabled(checked)
        self.layout_edit_action.setEnabled(checked)

        if not checked and self.layout_edit_action.isChecked():
            self.layout_edit_action.setChecked(False)
            self._toggle_layout_edit_mode(False)

        if checked:
            # グリッド -> 自由配置への切り替え直後、まだ矩形を持たないサブプロットには
            # デフォルトの初期矩形を割り当てる(既に自由配置で編集済みならそれを使う)。
            for i, settings in enumerate(self.project.all_plot_settings):
                if not settings.get('free_rect'):
                    settings['free_rect'] = self.canvas._default_free_rect(i)

        self._update_plot()

    def _on_add_free_subplot(self):
        """「+ プロット追加」ボタンの処理。自由配置レイアウトに新しいサブプロットを追加する。"""
        default_settings = self._gather_settings_from_ui()
        new_settings = default_settings.copy()
        # ★ 新しいサブプロットは注釈・凡例順・配置矩形を空/デフォルトから始める
        # (.copy()は浅いコピーのため、明示的に差し替えないと全プロットで共有されてしまう)
        new_settings['annotations'] = []
        new_settings['legend_order'] = []
        index = len(self.project.all_plot_settings)
        new_settings['free_rect'] = self.canvas._default_free_rect(index)
        self.project.all_plot_settings.append(new_settings)

        self._update_subplot_combos()
        self._update_plot()

    def _on_remove_free_subplot(self):
        """「- プロット削除」ボタンの処理。末尾のサブプロットを削除する(最低1つは残す)。"""
        if len(self.project.all_plot_settings) <= 1:
            return
        self.project.all_plot_settings.pop()
        if self.project.active_axis_index >= len(self.project.all_plot_settings):
            self.project.active_axis_index = len(self.project.all_plot_settings) - 1

        self._update_subplot_combos()
        self._apply_settings_to_ui_controls(self.project.all_plot_settings[self.project.active_axis_index])
        self._update_plot()

    def _toggle_layout_edit_mode(self, checked):
        """
        「レイアウト編集」ツールバーボタンが押されたときの処理。
        データカーソル/注釈モードと同時に有効だと同じクリックが競合するため排他にする。
        """
        self.layout_edit_mode_enabled = checked

        if checked:
            if getattr(self, 'cursor_mode_enabled', False):
                self.cursor_action.setChecked(False)
                self._toggle_cursor_mode(False)
            if getattr(self, 'annotation_mode_enabled', False):
                self.annotation_action.setChecked(False)
                self._toggle_annotation_mode(False)

            self._layout_edit_press_cid = self.canvas.mpl_connect('button_press_event', self._on_layout_press)
            self._layout_edit_motion_cid = self.canvas.mpl_connect('motion_notify_event', self._on_layout_motion)
            self._layout_edit_release_cid = self.canvas.mpl_connect('button_release_event', self._on_layout_release)
            self.statusBar().showMessage(
                "レイアウト編集モード: プロット内部をドラッグで移動、右下端をドラッグでリサイズします", 5000
            )
        else:
            for cid_attr in ('_layout_edit_press_cid', '_layout_edit_motion_cid', '_layout_edit_release_cid'):
                cid = getattr(self, cid_attr, None)
                if cid is not None:
                    self.canvas.mpl_disconnect(cid)
                    setattr(self, cid_attr, None)
            self._layout_drag_state = None

    def _find_axis_at_point(self, x_px, y_px):
        """指定されたピクセル座標(Figure内、原点は左下)に該当する軸のインデックスを返す(無ければNone)"""
        for index, ax in enumerate(self.canvas.all_axes):
            bbox = ax.bbox
            if bbox.x0 <= x_px <= bbox.x1 and bbox.y0 <= y_px <= bbox.y1:
                return index
        return None

    def _on_layout_press(self, event):
        """レイアウト編集モードでマウスボタンが押されたときの処理"""
        if not self.layout_edit_mode_enabled or event.x is None or event.y is None:
            return
        axis_index = self._find_axis_at_point(event.x, event.y)
        if axis_index is None:
            return

        ax = self.canvas.all_axes[axis_index]
        bbox = ax.bbox
        # 右下端(リサイズハンドル)付近かどうかを判定する
        near_corner = (
            abs(event.x - bbox.x1) <= RESIZE_HANDLE_TOLERANCE_PX and
            abs(event.y - bbox.y0) <= RESIZE_HANDLE_TOLERANCE_PX
        )
        pos = ax.get_position()
        self._layout_drag_state = {
            'axis_index': axis_index,
            'mode': 'resize' if near_corner else 'move',
            'start_mouse': (event.x, event.y),
            'start_rect': (pos.x0, pos.y0, pos.width, pos.height),
        }

    def _on_layout_motion(self, event):
        """レイアウト編集モードでマウスが動いたときの処理(ドラッグ中のみサブプロットを動かす)"""
        if not self.layout_edit_mode_enabled or self._layout_drag_state is None:
            return
        if event.x is None or event.y is None:
            return

        state = self._layout_drag_state
        fig_width_px, fig_height_px = self.canvas.fig.get_size_inches() * self.canvas.fig.dpi
        if fig_width_px <= 0 or fig_height_px <= 0:
            return

        delta_x = (event.x - state['start_mouse'][0]) / fig_width_px
        delta_y = (event.y - state['start_mouse'][1]) / fig_height_px
        left, bottom, width, height = state['start_rect']

        if state['mode'] == 'move':
            new_left = left + delta_x
            new_bottom = bottom + delta_y
            new_width, new_height = width, height
        else:
            # リサイズ (右下端をドラッグ、左上角を基点として固定したまま伸縮させる)
            new_width = max(MIN_FREE_RECT_SIZE, width + delta_x)
            new_height = max(MIN_FREE_RECT_SIZE, height - delta_y)
            new_left = left
            new_bottom = bottom + height - new_height

        ax = self.canvas.all_axes[state['axis_index']]
        ax.set_position([new_left, new_bottom, new_width, new_height])
        self.canvas.draw_idle()

    def _on_layout_release(self, event):
        """レイアウト編集モードでマウスボタンが離されたときの処理。最終的な位置を設定に保存する"""
        if not self.layout_edit_mode_enabled or self._layout_drag_state is None:
            return

        axis_index = self._layout_drag_state['axis_index']
        self._layout_drag_state = None

        if axis_index >= len(self.canvas.all_axes) or axis_index >= len(self.project.all_plot_settings):
            return
        ax = self.canvas.all_axes[axis_index]
        pos = ax.get_position()
        self.project.all_plot_settings[axis_index]['free_rect'] = (pos.x0, pos.y0, pos.width, pos.height)
