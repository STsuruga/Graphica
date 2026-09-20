"""ピーク配置モード: 左クリックで多峰分離の初期値を置き、右クリックで近いものを消す。

_pending_peak_guesses は [{'center', 'height', 'width'}, ...] で、MultiPeakFitDialog の initial_guesses にそのまま渡す。
ダイアログを閉じたら(OK でもキャンセルでも)消す。仮のマーカーは redraw_all() で消えていることがあるので、
消すときの例外は無視する。
"""
import logging

logger = logging.getLogger(__name__)

# 仮の幅は表示中の X の範囲に対する割合(ダイアログで直せるので大まかでよい)
PEAK_PLACEMENT_DEFAULT_WIDTH_FRACTION = 0.05
PEAK_PLACEMENT_DELETE_TOLERANCE_PX = 15


class PeakPlacementMixin:
    def _toggle_peak_placement_mode(self, checked):
        self.peak_placement_mode_enabled = checked

        if checked:
            self._deactivate_other_mouse_modes('peak_placement')

            self._peak_placement_press_cid = self.canvas.mpl_connect(
                'button_press_event', self._on_peak_placement_press
            )
            self.statusBar().showMessage(
                "ピーク配置モード: クリックで多峰分離フィットの初期値(中心・高さ)を追加、"
                "右クリックで直近のマーカーを削除します", 5000
            )
        else:
            if getattr(self, '_peak_placement_press_cid', None) is not None:
                self.canvas.mpl_disconnect(self._peak_placement_press_cid)
                self._peak_placement_press_cid = None

    def _on_peak_placement_press(self, event):
        if not getattr(self, 'peak_placement_mode_enabled', False):
            return
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return

        if event.button == 3:  # 右クリックは近いマーカーを消す
            self._remove_nearest_pending_peak_guess(event)
            return
        if event.button != 1:
            return

        ax = event.inaxes
        x_min, x_max = ax.get_xlim()
        # X のずらしは平行移動なので、幅は表示座標でもデータ座標でも同じ
        width = abs(x_max - x_min) * PEAK_PLACEMENT_DEFAULT_WIDTH_FRACTION or 1.0

        # 初期値はフィットでデータ座標と突き合わされるので、クリック位置(表示座標)をデータ座標に戻す。
        # マーカーはクリックした場所に出す
        dataset = self._get_current_dataset()
        data_x, data_y = self.canvas.display_to_data(
            dataset, float(event.xdata), float(event.ydata)
        ) if dataset is not None else (float(event.xdata), float(event.ydata))

        guess = {'center': float(data_x), 'height': float(data_y), 'width': float(width)}
        self._pending_peak_guesses.append(guess)
        self._draw_pending_peak_marker(ax, guess, float(event.xdata), float(event.ydata))
        self.statusBar().showMessage(
            f"ピーク初期値を追加しました({len(self._pending_peak_guesses)}件、"
            f"X={guess['center']:.4g}, Y={guess['height']:.4g})", 3000
        )

    def _draw_pending_peak_marker(self, ax, guess, display_x, display_y):
        """マーカーは表示座標に描く(guess はデータ座標で持つ)。"""
        line = ax.axvline(display_x, color='#E4572E', linestyle=':', linewidth=1, zorder=100)
        point, = ax.plot(
            [display_x], [display_y],
            marker='x', color='#E4572E', markersize=8, zorder=101, linestyle='None',
        )
        self._pending_peak_markers.append((guess, line, point))
        self.canvas.draw_idle()

    def _remove_nearest_pending_peak_guess(self, event):
        if not self._pending_peak_guesses:
            return

        ax = event.inaxes
        click_px = ax.transData.transform((event.xdata, event.ydata))

        best_i, best_distance = None, None
        for i, (_guess, _line, point) in enumerate(self._pending_peak_markers):
            # guess はデータ座標なので、描いたマーカーの位置(表示座標)で比べる
            marker_x = point.get_xdata()[0]
            marker_y = point.get_ydata()[0]
            pos_px = ax.transData.transform((marker_x, marker_y))
            distance = ((pos_px[0] - click_px[0]) ** 2 + (pos_px[1] - click_px[1]) ** 2) ** 0.5
            if best_distance is None or distance < best_distance:
                best_distance, best_i = distance, i

        if best_i is None or best_distance > PEAK_PLACEMENT_DELETE_TOLERANCE_PX:
            return

        guess, line, point = self._pending_peak_markers.pop(best_i)
        self._pending_peak_guesses.remove(guess)
        for artist in (line, point):
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
        self.canvas.draw_idle()

    def _clear_pending_peak_guesses(self):
        """ダイアログを閉じたら(OK でもキャンセルでも)仮のマーカーごと消す。"""
        for _guess, line, point in self._pending_peak_markers:
            for artist in (line, point):
                try:
                    artist.remove()
                except (ValueError, NotImplementedError):
                    pass
        self._pending_peak_markers = []
        self._pending_peak_guesses = []
        self.canvas.draw_idle()
