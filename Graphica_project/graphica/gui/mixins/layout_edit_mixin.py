"""自由配置のレイアウト: サブプロットをドラッグか数値で好きな位置と大きさに置く。

位置は all_plot_settings[i]['free_rect'] に (left, bottom, width, height)(Figure に対する 0〜1)で持つ。
ドラッグも数値の入力も、ax.set_position() と free_rect への書き込みという同じ経路を通す(食い違わないように)。
"""
import logging
from graphica.core.axis_settings import axis_setting

logger = logging.getLogger(__name__)

# 右下の角をつかんでいるとみなす距離
RESIZE_HANDLE_TOLERANCE_PX = 12
MIN_FREE_RECT_SIZE = 0.05


class LayoutEditMixin:
    def _on_toggle_free_layout(self, checked):
        self.project.layout_mode = 'free' if checked else 'grid'

        self.subplot_rows_spinbox.setEnabled(not checked)
        self.subplot_cols_spinbox.setEnabled(not checked)
        self.add_free_subplot_button.setEnabled(checked)
        self.remove_free_subplot_button.setEnabled(checked)
        self.layout_edit_action.setEnabled(checked)
        # 自由配置には「同じ行・列」が無いので軸の共有は使えない(値は残し、グリッドに戻せばそのまま効く)
        self.share_x_checkbox.setEnabled(not checked)
        self.share_y_checkbox.setEnabled(not checked)

        if not checked and self.layout_edit_action.isChecked():
            self.layout_edit_action.setChecked(False)
            self._toggle_layout_edit_mode(False)

        if not checked:
            self._layout_selected_axis_index = None
            self.free_layout_position_group.setVisible(False)

        if checked:
            # 矩形をまだ持たないサブプロットには既定の矩形を割り当てる
            for i, settings in enumerate(self.project.all_plot_settings):
                if not axis_setting(settings, 'free_rect'):
                    settings['free_rect'] = self.canvas._default_free_rect(i)

        self._update_plot()

    def _on_add_free_subplot(self):
        """空の Axes を1つ足すだけなので、全体を描き直さず canvas.add_free_axis() で足りる。"""
        default_settings = self._gather_settings_from_ui()
        new_settings = default_settings.copy()
        # 注釈などは引き継がない。浅いコピーなので、差し替えないと全部で共有してしまう
        new_settings['annotations'] = []
        new_settings['legend_order'] = []
        index = len(self.project.all_plot_settings)
        new_settings['free_rect'] = self.canvas._default_free_rect(index)
        self.project.all_plot_settings.append(new_settings)

        self._update_subplot_combos()
        self.canvas.add_free_axis(
            self.project.datasets, new_settings, panel_labels_enabled=self.project.panel_labels_enabled,
        )
        self._sync_canvas_axes_state_and_side_panels()

    def _on_remove_free_subplot(self):
        """末尾のサブプロットを消す(最低1つは残す)。ほかの番号は変わらないので、全体を描き直さずに済む。"""
        if len(self.project.all_plot_settings) <= 1:
            return
        self.project.all_plot_settings.pop()
        new_total = len(self.project.all_plot_settings)
        if self.project.active_axis_index >= new_total:
            self.project.active_axis_index = new_total - 1

        # 消えたサブプロットの系列はどこにも描かれなくなるので、新しい末尾に移す
        for dataset in self.project.datasets:
            if dataset.subplot_target >= new_total:
                dataset.subplot_target = new_total - 1

        self._update_subplot_combos()
        self._apply_settings_to_ui_controls(self.project.all_plot_settings[self.project.active_axis_index])

        self.canvas.remove_last_free_axis(self.project.datasets)
        new_last_index = new_total - 1
        self.canvas.update_single_axis(
            new_last_index, self.project.datasets, self.project.all_plot_settings[new_last_index],
            rows=0, cols=0, panel_labels_enabled=self.project.panel_labels_enabled,
        )
        self._sync_canvas_axes_state_and_side_panels()

        if (self._layout_selected_axis_index is not None and
                self._layout_selected_axis_index >= len(self.project.all_plot_settings)):
            self._layout_selected_axis_index = None
        self._sync_free_layout_position_controls()

    def _sync_canvas_axes_state_and_side_panels(self):
        """Axes を足したり消したりした後、_update_plot() がしている UI の同期を、全体を描き直さずに行う。"""
        is_secondary_visible = any(sa is not None for sa in self.canvas.all_secondary_axes)
        self.tick_direction_y2_label.setVisible(is_secondary_visible)
        self.major_tick_direction_y2_combo.setVisible(is_secondary_visible)
        self.minor_tick_direction_y2_combo.setVisible(is_secondary_visible)
        self.y2_label_text_label.setVisible(is_secondary_visible)
        self.y2_label_text_edit.setVisible(is_secondary_visible)

        self.all_axes = self.canvas.all_axes
        self.all_secondary_axes = self.canvas.all_secondary_axes

        if hasattr(self, 'export_preview_panel'):
            self.export_preview_panel.refresh_preview()
        self._reapply_editor_row_highlight()
        self._refresh_minimap()

    def _toggle_layout_edit_mode(self, checked):
        self.layout_edit_mode_enabled = checked

        if checked:
            self._deactivate_other_mouse_modes('layout_edit')

            self._layout_edit_press_cid = self.canvas.mpl_connect('button_press_event', self._on_layout_press)
            self._layout_edit_motion_cid = self.canvas.mpl_connect('motion_notify_event', self._on_layout_motion)
            self._layout_edit_release_cid = self.canvas.mpl_connect('button_release_event', self._on_layout_release)
            # 図の外でボタンを離すと button_release_event が届かず、ボタンを押していないのに動かし続けるので、
            # 図から出た時点で離したことにする
            self._layout_edit_leave_cid = self.canvas.mpl_connect('figure_leave_event', self._on_layout_release)
            self.statusBar().showMessage(
                "レイアウト編集モード: プロット内部をドラッグで移動、右下端をドラッグでリサイズします", 5000
            )
        else:
            for cid_attr in ('_layout_edit_press_cid', '_layout_edit_motion_cid', '_layout_edit_release_cid',
                              '_layout_edit_leave_cid'):
                cid = getattr(self, cid_attr, None)
                if cid is not None:
                    self.canvas.mpl_disconnect(cid)
                    setattr(self, cid_attr, None)
            self._layout_drag_state = None
            self._layout_selected_axis_index = None
            self.free_layout_position_group.setVisible(False)

    def _find_axis_at_point(self, x_px, y_px):
        """Figure 内のピクセル座標(原点は左下)にある軸の番号。無ければ None。"""
        for index, ax in enumerate(self.canvas.all_axes):
            bbox = ax.bbox
            if bbox.x0 <= x_px <= bbox.x1 and bbox.y0 <= y_px <= bbox.y1:
                return index
        return None

    def _on_layout_press(self, event):
        if not self.layout_edit_mode_enabled or event.x is None or event.y is None:
            return
        axis_index = self._find_axis_at_point(event.x, event.y)
        if axis_index is None:
            self._layout_selected_axis_index = None
            self._sync_free_layout_position_controls()
            return

        # ドラッグしなくても選択にする(数値の欄に今の矩形を出す)
        self._layout_selected_axis_index = axis_index
        self._sync_free_layout_position_controls()

        ax = self.canvas.all_axes[axis_index]
        bbox = ax.bbox
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
            # 右下の角のドラッグは、左上を固定して伸縮する
            new_width = max(MIN_FREE_RECT_SIZE, width + delta_x)
            new_height = max(MIN_FREE_RECT_SIZE, height - delta_y)
            new_left = left
            new_bottom = bottom + height - new_height

        ax = self.canvas.all_axes[state['axis_index']]
        ax.set_position([new_left, new_bottom, new_width, new_height])
        self.canvas.draw_idle()

        self._sync_free_layout_position_controls()

    def _on_layout_release(self, event):
        """最終的な位置を設定に保存する。"""
        if not self.layout_edit_mode_enabled or self._layout_drag_state is None:
            return

        axis_index = self._layout_drag_state['axis_index']
        self._layout_drag_state = None

        if axis_index >= len(self.canvas.all_axes) or axis_index >= len(self.project.all_plot_settings):
            return
        ax = self.canvas.all_axes[axis_index]
        pos = ax.get_position()
        self.project.all_plot_settings[axis_index]['free_rect'] = (pos.x0, pos.y0, pos.width, pos.height)

        self._sync_free_layout_position_controls()

    def _sync_free_layout_position_controls(self):
        """選んだサブプロットの矩形を数値の欄に出す。自由配置でないか、選択が無ければ欄ごと隠す。

        値を入れる間は通知を止める(止めないと _on_free_layout_position_spinbox_changed が呼ばれて循環する)。
        """
        is_free_layout = getattr(self.project, 'layout_mode', 'grid') == 'free'
        axis_index = self._layout_selected_axis_index

        if (not is_free_layout or axis_index is None or
                axis_index >= len(self.canvas.all_axes)):
            self.free_layout_position_group.setVisible(False)
            return

        ax = self.canvas.all_axes[axis_index]
        pos = ax.get_position()
        for spinbox, value in (
            (self.free_layout_x_spinbox, pos.x0),
            (self.free_layout_y_spinbox, pos.y0),
            (self.free_layout_width_spinbox, pos.width),
            (self.free_layout_height_spinbox, pos.height),
        ):
            spinbox.blockSignals(True)
            spinbox.setValue(value)
            spinbox.blockSignals(False)
        self.free_layout_position_group.setVisible(True)

    def _on_free_layout_position_spinbox_changed(self, _value=None):
        """数値の欄から、ドラッグと同じ経路(set_position → draw_idle → free_rect)で更新する。"""
        axis_index = self._layout_selected_axis_index
        if (axis_index is None or
                axis_index >= len(self.canvas.all_axes) or
                axis_index >= len(self.project.all_plot_settings)):
            return

        new_left = self.free_layout_x_spinbox.value()
        new_bottom = self.free_layout_y_spinbox.value()
        new_width = max(MIN_FREE_RECT_SIZE, self.free_layout_width_spinbox.value())
        new_height = max(MIN_FREE_RECT_SIZE, self.free_layout_height_spinbox.value())

        ax = self.canvas.all_axes[axis_index]
        ax.set_position([new_left, new_bottom, new_width, new_height])
        self.canvas.draw_idle()

        self.project.all_plot_settings[axis_index]['free_rect'] = (
            new_left, new_bottom, new_width, new_height
        )
