"""自由配置のレイアウト: サブプロットをドラッグか数値で好きな位置と大きさに置く。

位置は all_plot_settings[i]['free_rect'] に (left, bottom, width, height)(Figure に対する 0〜1)で持つ。
ドラッグも数値の入力も、ax.set_position() と free_rect への書き込みという同じ経路を通す(食い違わないように)。
"""
import logging
from graphica.core.axis_settings import axis_setting
from graphica.gui.tools.pointer import legend_at

logger = logging.getLogger(__name__)

# 右下の角をつかんでいるとみなす距離
RESIZE_HANDLE_TOLERANCE_PX = 12
MIN_FREE_RECT_SIZE = 0.05


class LayoutEditTool:
    """状態はこのツールが持ち、PlotterApp の同じ名前は窓口(gui/tools/__init__.py)。"""

    # PlotterApp から同じ名前で読み書きできるもの(テスト・メニュー・ほかの mixin が使う)
    EXPOSED_NAMES = (
        '_find_axis_at_point', '_layout_drag_state', '_layout_edit_leave_cid', '_layout_edit_motion_cid',
        '_layout_edit_press_cid', '_layout_edit_release_cid', '_layout_selected_axis_index', '_on_add_free_subplot',
        '_on_free_layout_position_spinbox_changed', '_on_layout_motion', '_on_layout_press', '_on_layout_release',
        '_on_remove_free_subplot', '_on_toggle_free_layout', '_sync_canvas_axes_state_and_side_panels',
        '_sync_free_layout_position_controls', '_toggle_layout_edit_mode', 'layout_edit_mode_enabled',
    )

    def __init__(self, app):
        self._app = app
        self.layout_edit_mode_enabled = False
        self._layout_edit_press_cid = None
        self._layout_edit_motion_cid = None
        self._layout_edit_release_cid = None
        self._layout_edit_leave_cid = None     # ドラッグ中に図の外へ出たとき用
        self._layout_drag_state = None
        # クリックで選んだ軸(ドラッグとは別)。位置と大きさの数値欄の対象
        self._layout_selected_axis_index = None

    def _on_toggle_free_layout(self, checked):
        self._app.project.layout_mode = 'free' if checked else 'grid'

        self._app.subplot_rows_spinbox.setEnabled(not checked)
        self._app.subplot_cols_spinbox.setEnabled(not checked)
        self._app.add_free_subplot_button.setEnabled(checked)
        self._app.remove_free_subplot_button.setEnabled(checked)
        self._app.layout_edit_action.setEnabled(checked)
        # 自由配置には「同じ行・列」が無いので軸の共有は使えない(値は残し、グリッドに戻せばそのまま効く)
        self._app.share_x_checkbox.setEnabled(not checked)
        self._app.share_y_checkbox.setEnabled(not checked)

        if not checked and self._app.layout_edit_action.isChecked():
            self._app.layout_edit_action.setChecked(False)
            self._toggle_layout_edit_mode(False)

        if not checked:
            self._layout_selected_axis_index = None
            self._app.free_layout_position_group.setVisible(False)

        if checked:
            # 矩形をまだ持たないサブプロットには既定の矩形を割り当てる
            for i, settings in enumerate(self._app.project.all_plot_settings):
                if not axis_setting(settings, 'free_rect'):
                    settings['free_rect'] = self._app.canvas._default_free_rect(i)

        self._app._update_plot()

    def _on_add_free_subplot(self):
        """空の Axes を1つ足すだけなので、全体を描き直さず canvas.add_free_axis() で足りる。"""
        default_settings = self._app._gather_settings_from_ui()
        new_settings = default_settings.copy()
        # 注釈などは引き継がない。浅いコピーなので、差し替えないと全部で共有してしまう
        new_settings['annotations'] = []
        new_settings['legend_order'] = []
        index = len(self._app.project.all_plot_settings)
        new_settings['free_rect'] = self._app.canvas._default_free_rect(index)
        self._app.project.all_plot_settings.append(new_settings)

        self._app._update_subplot_combos()
        self._app.canvas.add_free_axis(
            self._app.project.datasets, new_settings, panel_labels_enabled=self._app.project.panel_labels_enabled,
        )
        self._sync_canvas_axes_state_and_side_panels()

    def _on_remove_free_subplot(self):
        """末尾のサブプロットを消す(最低1つは残す)。ほかの番号は変わらないので、全体を描き直さずに済む。"""
        if len(self._app.project.all_plot_settings) <= 1:
            return
        self._app.project.all_plot_settings.pop()
        new_total = len(self._app.project.all_plot_settings)
        self._app.view_navigation.forget_view(new_total)
        if self._app.project.active_axis_index >= new_total:
            self._app.project.active_axis_index = new_total - 1

        # 消えたサブプロットの系列はどこにも描かれなくなるので、新しい末尾に移す
        for dataset in self._app.project.datasets:
            if dataset.subplot_target >= new_total:
                dataset.subplot_target = new_total - 1

        self._app._update_subplot_combos()
        self._app._apply_settings_to_ui_controls(self._app.project.all_plot_settings[self._app.project.active_axis_index])

        self._app.canvas.remove_last_free_axis(self._app.project.datasets)
        new_last_index = new_total - 1
        self._app.canvas.update_single_axis(
            new_last_index, self._app.project.datasets, self._app.project.all_plot_settings[new_last_index],
            rows=0, cols=0, panel_labels_enabled=self._app.project.panel_labels_enabled,
        )
        self._sync_canvas_axes_state_and_side_panels()

        if (self._layout_selected_axis_index is not None and
                self._layout_selected_axis_index >= len(self._app.project.all_plot_settings)):
            self._layout_selected_axis_index = None
        self._sync_free_layout_position_controls()

    def _sync_canvas_axes_state_and_side_panels(self):
        """Axes を足したり消したりした後、_update_plot() がしている UI の同期を、全体を描き直さずに行う。"""
        is_secondary_visible = any(sa is not None for sa in self._app.canvas.all_secondary_axes)
        self._app.tick_direction_y2_label.setVisible(is_secondary_visible)
        self._app.major_tick_direction_y2_combo.setVisible(is_secondary_visible)
        self._app.minor_tick_direction_y2_combo.setVisible(is_secondary_visible)
        self._app.y2_label_text_label.setVisible(is_secondary_visible)
        self._app.y2_label_text_edit.setVisible(is_secondary_visible)

        self._app.all_axes = self._app.canvas.all_axes
        self._app.all_secondary_axes = self._app.canvas.all_secondary_axes

        if hasattr(self._app, 'export_preview_panel'):
            self._app.export_preview_panel.refresh_preview()
        self._app._reapply_editor_row_highlight()
        self._app._refresh_minimap()

    def _toggle_layout_edit_mode(self, checked):
        self.layout_edit_mode_enabled = checked

        if checked:
            self._app._deactivate_other_mouse_modes('layout_edit')

            self._layout_edit_press_cid = self._app.canvas.mpl_connect('button_press_event', self._on_layout_press)
            self._layout_edit_motion_cid = self._app.canvas.mpl_connect('motion_notify_event', self._on_layout_motion)
            self._layout_edit_release_cid = self._app.canvas.mpl_connect('button_release_event', self._on_layout_release)
            # 図の外でボタンを離すと button_release_event が届かず、ボタンを押していないのに動かし続けるので、
            # 図から出た時点で離したことにする
            self._layout_edit_leave_cid = self._app.canvas.mpl_connect('figure_leave_event', self._on_layout_release)
            self._app.statusBar().showMessage(
                "レイアウト編集モード: プロット内部をドラッグで移動、右下端をドラッグでリサイズします", 5000
            )
        else:
            for cid_attr in ('_layout_edit_press_cid', '_layout_edit_motion_cid', '_layout_edit_release_cid',
                              '_layout_edit_leave_cid'):
                cid = getattr(self, cid_attr, None)
                if cid is not None:
                    self._app.canvas.mpl_disconnect(cid)
                    setattr(self, cid_attr, None)
            self._layout_drag_state = None
            self._layout_selected_axis_index = None
            self._app.free_layout_position_group.setVisible(False)

    def _find_axis_at_point(self, x_px, y_px):
        """Figure 内のピクセル座標(原点は左下)にある軸の番号。無ければ None。"""
        for index, ax in enumerate(self._app.canvas.all_axes):
            bbox = ax.bbox
            if bbox.x0 <= x_px <= bbox.x1 and bbox.y0 <= y_px <= bbox.y1:
                return index
        return None

    def _on_layout_press(self, event):
        if not self.layout_edit_mode_enabled or event.x is None or event.y is None:
            return
        if legend_at(self._app.canvas, event) is not None:
            return
        axis_index = self._find_axis_at_point(event.x, event.y)
        if axis_index is None:
            self._layout_selected_axis_index = None
            self._sync_free_layout_position_controls()
            return

        # ドラッグしなくても選択にする(数値の欄に今の矩形を出す)
        self._layout_selected_axis_index = axis_index
        self._sync_free_layout_position_controls()

        ax = self._app.canvas.all_axes[axis_index]
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
        fig_width_px, fig_height_px = self._app.canvas.fig.get_size_inches() * self._app.canvas.fig.dpi
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

        ax = self._app.canvas.all_axes[state['axis_index']]
        ax.set_position([new_left, new_bottom, new_width, new_height])
        self._app.canvas.draw_idle()

        self._sync_free_layout_position_controls()

    def _on_layout_release(self, event):
        """最終的な位置を設定に保存する。"""
        if not self.layout_edit_mode_enabled or self._layout_drag_state is None:
            return

        axis_index = self._layout_drag_state['axis_index']
        self._layout_drag_state = None

        if axis_index >= len(self._app.canvas.all_axes) or axis_index >= len(self._app.project.all_plot_settings):
            return
        ax = self._app.canvas.all_axes[axis_index]
        pos = ax.get_position()
        self._app.project.all_plot_settings[axis_index]['free_rect'] = (pos.x0, pos.y0, pos.width, pos.height)

        self._sync_free_layout_position_controls()

    def _sync_free_layout_position_controls(self):
        """選んだサブプロットの矩形を数値の欄に出す。自由配置でないか、選択が無ければ欄ごと隠す。

        値を入れる間は通知を止める(止めないと _on_free_layout_position_spinbox_changed が呼ばれて循環する)。
        """
        is_free_layout = getattr(self._app.project, 'layout_mode', 'grid') == 'free'
        axis_index = self._layout_selected_axis_index

        if (not is_free_layout or axis_index is None or
                axis_index >= len(self._app.canvas.all_axes)):
            self._app.free_layout_position_group.setVisible(False)
            return

        ax = self._app.canvas.all_axes[axis_index]
        pos = ax.get_position()
        for spinbox, value in (
            (self._app.free_layout_x_spinbox, pos.x0),
            (self._app.free_layout_y_spinbox, pos.y0),
            (self._app.free_layout_width_spinbox, pos.width),
            (self._app.free_layout_height_spinbox, pos.height),
        ):
            spinbox.blockSignals(True)
            spinbox.setValue(value)
            spinbox.blockSignals(False)
        self._app.free_layout_position_group.setVisible(True)

    def _on_free_layout_position_spinbox_changed(self, _value=None):
        """数値の欄から、ドラッグと同じ経路(set_position → draw_idle → free_rect)で更新する。"""
        axis_index = self._layout_selected_axis_index
        if (axis_index is None or
                axis_index >= len(self._app.canvas.all_axes) or
                axis_index >= len(self._app.project.all_plot_settings)):
            return

        new_left = self._app.free_layout_x_spinbox.value()
        new_bottom = self._app.free_layout_y_spinbox.value()
        new_width = max(MIN_FREE_RECT_SIZE, self._app.free_layout_width_spinbox.value())
        new_height = max(MIN_FREE_RECT_SIZE, self._app.free_layout_height_spinbox.value())

        ax = self._app.canvas.all_axes[axis_index]
        ax.set_position([new_left, new_bottom, new_width, new_height])
        self._app.canvas.draw_idle()

        self._app.project.all_plot_settings[axis_index]['free_rect'] = (
            new_left, new_bottom, new_width, new_height
        )
