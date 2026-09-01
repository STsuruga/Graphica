# gui/mixins/peak_placement_mixin.py
"""
グラフクリックによる多峰分離フィット(項目C-409、core/analysis.pyの
calculate_multi_peak_fit)の初期値配置モード(項目C-410)をまとめたMixin。

他のクリック/ドラッグ系モード(データカーソル/注釈/範囲選択/自由配置編集)と
同じ「モードトグル+mpl_connect('button_press_event', ...)+他モードとの
相互排他」パターンを踏襲する(gui/mixins/range_select_mixin.py参照)。

左クリックでピーク位置(中心X・高さY)を1つ`self._pending_peak_guesses`に
追加し、キャンバス上に仮マーカー(縦線+点)を描く。右クリックで直近に追加した
ものではなく、クリック位置に最も近い既存の仮マーカーを削除する(注釈モードの
右クリック削除と同じ「最近傍」方式)。

`self._pending_peak_guesses` は [{'center': float, 'height': float,
'width': float}, ...] の形で、gui/dialogs.py の MultiPeakFitDialog の
initial_guesses引数へそのまま渡せる(gui/mixins/dataset_mixin.pyの
_on_multi_peak_fit()が仲介する)。ダイアログを開いた時点で現在の内容を
引き継ぐ設計であり、ダイアログ側でさらに編集・追加・削除できるため、
ダイアログを閉じた後(OK/Cancelいずれでも)は本モード側のペンディング状態を
クリアする(_clear_pending_peak_guesses)。

★ 仮マーカーはaxes.axvline/axes.plotで直接描画し、range_select_mixin.pyの
プレビュー矩形と同じ理由(メインキャンバスはredraw_all()のたびにfig.clf()で
Axesを作り直すため、Artist参照が再描画をまたいで有効である保証はない)で、
削除時にValueError/NotImplementedErrorを無視する。
"""
import logging

logger = logging.getLogger(__name__)

# クリック位置の「高さ」を仮の幅(FWHM)推定に変換する係数
# (表示中のX軸範囲に対する割合。ユーザーはMultiPeakFitDialogのテーブルで
# 後から自由に上書きできるため、大まかな初期値であれば十分)。
PEAK_PLACEMENT_DEFAULT_WIDTH_FRACTION = 0.05
# 右クリックで削除対象とみなす、マーカー位置からの許容ピクセル距離
PEAK_PLACEMENT_DELETE_TOLERANCE_PX = 15


class PeakPlacementMixin:
    def _toggle_peak_placement_mode(self, checked):
        """「ピーク配置」ツールバーボタンが押されたときの処理。"""
        self.peak_placement_mode_enabled = checked

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
            if getattr(self, 'layout_edit_mode_enabled', False):
                self.layout_edit_action.setChecked(False)
                self._toggle_layout_edit_mode(False)
            if getattr(self, 'slice_extraction_mode_enabled', False):
                self.slice_extraction_action.setChecked(False)
                self._toggle_slice_extraction_mode(False)
            if getattr(self, 'region_highlight_mode_enabled', False):
                self.region_highlight_action.setChecked(False)
                self._toggle_region_highlight_mode(False)

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

        if event.button == 3:  # 右クリック: 最近傍のマーカーを削除
            self._remove_nearest_pending_peak_guess(event)
            return
        if event.button != 1:
            return

        ax = event.inaxes
        x_min, x_max = ax.get_xlim()
        width = abs(x_max - x_min) * PEAK_PLACEMENT_DEFAULT_WIDTH_FRACTION or 1.0

        guess = {'center': float(event.xdata), 'height': float(event.ydata), 'width': float(width)}
        self._pending_peak_guesses.append(guess)
        self._draw_pending_peak_marker(ax, guess)
        self.statusBar().showMessage(
            f"ピーク初期値を追加しました({len(self._pending_peak_guesses)}件、"
            f"X={guess['center']:.4g}, Y={guess['height']:.4g})", 3000
        )

    def _draw_pending_peak_marker(self, ax, guess):
        line = ax.axvline(guess['center'], color='#E4572E', linestyle=':', linewidth=1, zorder=100)
        point, = ax.plot(
            [guess['center']], [guess['height']],
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
        for i, (guess, _line, _point) in enumerate(self._pending_peak_markers):
            pos_px = ax.transData.transform((guess['center'], guess['height']))
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
        """MultiPeakFitDialogを閉じた後(OK/Cancelいずれでも)に呼ばれる、
        ペンディング状態(仮マーカー含む)の一括クリア。"""
        for _guess, line, point in self._pending_peak_markers:
            for artist in (line, point):
                try:
                    artist.remove()
                except (ValueError, NotImplementedError):
                    pass
        self._pending_peak_markers = []
        self._pending_peak_guesses = []
        self.canvas.draw_idle()
