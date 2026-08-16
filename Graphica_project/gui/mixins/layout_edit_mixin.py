# gui/mixins/layout_edit_mixin.py
"""
自由配置レイアウト(項目37): 均等グリッドではなく、サブプロットをマウス
ドラッグで自由な位置・サイズに配置できるモードをまとめた Mixin。

各サブプロットの位置は project.all_plot_settings[index]['free_rect'] に
(left, bottom, width, height) の Figure正規化座標(0〜1)として保持される。
「自由配置レイアウト」チェックボックスがONの間は、サブプロット数は
行数×列数ではなく all_plot_settings の要素数そのものになり、
「+ プロット追加」「- プロット削除」ボタンで増減させる。

項目85: 上記のマウスドラッグに加えて、X/Y/幅/高さの数値入力
(free_layout_x/y/width/height_spinbox) でも同じサブプロットの矩形を
編集できるようにしてある。ドラッグ中の状態(_layout_drag_state)とは別に、
「レイアウト編集モードでクリックして選択されているサブプロット」を
_layout_selected_axis_index として保持し、ドラッグ操作・数値入力の
どちらの経路でも最終的に ax.set_position() + all_plot_settings[index]
['free_rect'] への書き込みという同じ1本の状態更新パスを通ることで、
2つの入力手段が食い違わないようにしている。
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
        # 軸共有(項目C-601): 自由配置レイアウトには「同じ行/列」の概念が無く
        # 意味を持たないため、自由配置レイアウト中は操作できないようにする
        # (設定値自体は保持し、グリッドに戻せば元の状態のまま再度使える)。
        self.share_x_checkbox.setEnabled(not checked)
        self.share_y_checkbox.setEnabled(not checked)

        if not checked and self.layout_edit_action.isChecked():
            self.layout_edit_action.setChecked(False)
            self._toggle_layout_edit_mode(False)

        if not checked:
            # グリッドレイアウトに戻したら、数値入力欄の選択状態も解除して隠す
            self._layout_selected_axis_index = None
            self.free_layout_position_group.setVisible(False)

        if checked:
            # グリッド -> 自由配置への切り替え直後、まだ矩形を持たないサブプロットには
            # デフォルトの初期矩形を割り当てる(既に自由配置で編集済みならそれを使う)。
            for i, settings in enumerate(self.project.all_plot_settings):
                if not settings.get('free_rect'):
                    settings['free_rect'] = self.canvas._default_free_rect(i)

        self._update_plot()

    def _on_add_free_subplot(self):
        """
        「+ プロット追加」ボタンの処理。自由配置レイアウトに新しいサブプロットを追加する。

        ★ 項目C-003フェーズ3b: 新規追加は既存のどのAxesにも影響しない
        (常に空の新規Axesを1つ増やすだけ)ため、フルの_update_plot()
        (fig.clf()による全Axes再構築)ではなくcanvas.add_free_axis()
        による軽量な追加で足りる。
        """
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
        self.canvas.add_free_axis(
            self.project.datasets, new_settings, panel_labels_enabled=self.project.panel_labels_enabled,
        )
        self._sync_canvas_axes_state_and_side_panels()

    def _on_remove_free_subplot(self):
        """
        「- プロット削除」ボタンの処理。末尾のサブプロットを削除する(最低1つは残す)。

        ★ 項目C-003フェーズ3b: 削除対象は常に末尾のAxesのみ(他のAxesの
        インデックスは変わらない)。削除された番号に割り当てられていた
        データセットは新しい末尾のサブプロットへ付け替えるため、
        フルの_update_plot()ではなくcanvas.remove_last_free_axis()
        (削除Axesの後片付け)+canvas.update_single_axis()(付け替え先の
        新しい末尾Axesへのデータ反映)の2手順の軽量パスで足りる。
        """
        if len(self.project.all_plot_settings) <= 1:
            return
        self.project.all_plot_settings.pop()
        new_total = len(self.project.all_plot_settings)
        if self.project.active_axis_index >= new_total:
            self.project.active_axis_index = new_total - 1

        # ★ バグ修正: gui/mixins/settings_mixin.py の _on_layout_changed と
        # 同じ理由(削除された番号のサブプロットに割り当てられたままの
        # データセットが、どの軸にも描画されなくなりサイレントに消える)。
        for dataset in self.project.datasets:
            if dataset.subplot_target >= new_total:
                dataset.subplot_target = new_total - 1

        self._update_subplot_combos()
        self._apply_settings_to_ui_controls(self.project.all_plot_settings[self.project.active_axis_index])

        self.canvas.remove_last_free_axis(self.project.datasets)
        # 付け替え先(新しい末尾)のAxesに、移動してきたデータセットを反映する
        new_last_index = new_total - 1
        self.canvas.update_single_axis(
            new_last_index, self.project.datasets, self.project.all_plot_settings[new_last_index],
            rows=0, cols=0, panel_labels_enabled=self.project.panel_labels_enabled,
        )
        self._sync_canvas_axes_state_and_side_panels()

        # 選択中だったサブプロットが削除された場合は選択を解除する
        if (self._layout_selected_axis_index is not None and
                self._layout_selected_axis_index >= len(self.project.all_plot_settings)):
            self._layout_selected_axis_index = None
        self._sync_free_layout_position_controls()

    def _sync_canvas_axes_state_and_side_panels(self):
        """
        canvas.add_free_axis()/remove_last_free_axis()呼び出し後の共通後処理。
        _update_plot()が行っている、Axes構造変更後の付随的なUI同期
        (Y2軸コントロール表示・データカーソル用Axes参照・エクスポート
        プレビュー追従・エディタ行ハイライト再適用・ミニマップ更新)を
        フル再描画を経由せずに揃える。
        """
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
            if getattr(self, 'range_select_mode_enabled', False):
                self.range_select_action.setChecked(False)
                self._toggle_range_select_mode(False)

            self._layout_edit_press_cid = self.canvas.mpl_connect('button_press_event', self._on_layout_press)
            self._layout_edit_motion_cid = self.canvas.mpl_connect('motion_notify_event', self._on_layout_motion)
            self._layout_edit_release_cid = self.canvas.mpl_connect('button_release_event', self._on_layout_release)
            # ★ バグ修正: ドラッグ中にマウスカーソルがアプリウィンドウの外まで
            # 出た状態でボタンを離すと、canvasには button_release_event が
            # 届かず _layout_drag_state が残留したままになっていた(項目86の
            # マルチモニター対応もあり、画面端を越えてドラッグするのは十分
            # 起こりうる)。この状態だとボタンを押していなくてもマウスを
            # 動かすだけで _on_layout_motion が最後に触っていたサブプロット
            # を勝手に動かし続けてしまう(ツールバーへ移動するだけでも発生)、
            # サイレントかつ厄介な「幽霊ドラッグ」バグだった。マウスが
            # figure領域を離れた時点で _on_layout_release と同じ確定処理を
            # 行い、後続のmotionに反応しないようにする。
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
            # レイアウト編集モードを抜けたら、数値入力欄の選択状態も解除して隠す
            self._layout_selected_axis_index = None
            self.free_layout_position_group.setVisible(False)

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
            # プロット外をクリックしたら選択解除(数値入力欄も隠す)
            self._layout_selected_axis_index = None
            self._sync_free_layout_position_controls()
            return

        # クリックされたサブプロットを「選択」状態にする(ドラッグの有無に関わらず)。
        # これにより数値入力欄(X/Y/幅/高さ)が現在の矩形を表示するようになる。
        self._layout_selected_axis_index = axis_index
        self._sync_free_layout_position_controls()

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

        # ドラッグ中の矩形を数値入力欄にもリアルタイムで反映する(選択中サブプロットは
        # ドラッグ中のサブプロットと常に同じなので、無条件に同期して構わない)
        self._sync_free_layout_position_controls()

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

        # 最終的な矩形を数値入力欄にも反映しておく(念のための最終同期)
        self._sync_free_layout_position_controls()

    def _sync_free_layout_position_controls(self):
        """
        項目85: 選択中サブプロット(_layout_selected_axis_index)の現在の矩形を
        X/Y/幅/高さの数値入力欄に反映する。自由配置モードでなかったり、
        サブプロットが選択されていない場合は入力欄ごと隠す。

        マウスドラッグ後や、数値入力自体で書き換えた後にも呼ばれるため、
        「表示されている数値」は常に ax の実際の位置と一致する(=ドラッグと
        数値入力が食い違わない)。setValue() 中に valueChanged が発火して
        _on_free_layout_position_spinbox_changed が呼ばれ無限ループするのを
        防ぐため、blockSignals で一時的にシグナルを止める。
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
        """
        項目85: X/Y/幅/高さのいずれかの数値入力欄が変更されたときの処理。
        選択中サブプロットに対して、マウスドラッグ(_on_layout_release)と全く同じ
        更新パス(ax.set_position() -> canvas.draw_idle() ->
        all_plot_settings[axis_index]['free_rect'] への保存)を通すことで、
        ドラッグと数値入力の状態が食い違わないようにする。
        """
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
