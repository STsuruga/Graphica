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
            # 排他制御は登録簿(gui/mixins/mouse_mode_mixin.py の MOUSE_MODES)に
            # 集約している。8つ目のモードを足すときもここは変更不要。
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

        if event.button == 3:  # 右クリック: 最近傍のマーカーを削除
            self._remove_nearest_pending_peak_guess(event)
            return
        if event.button != 1:
            return

        ax = event.inaxes
        x_min, x_max = ax.get_xlim()
        # Xオフセットは平行移動なので、表示座標での幅とデータ座標での幅は等しい
        # (奥行き縮小が掛かるのはY方向のみ)。
        width = abs(x_max - x_min) * PEAK_PLACEMENT_DEFAULT_WIDTH_FRACTION or 1.0

        # ★ 改善ボード A-1: クリック位置(event.xdata/ydata)は表示座標。
        # 初期値は MultiPeakFitDialog を経由してフィット計算へ渡され、そこでは
        # dataset.x_data/y_data(データ座標)と突き合わされるため、ウォーター
        # フォール(積み重ね)有効時にそのまま使うと積み重ね2本目以降で
        # フィットが収束しない/明後日の値に収束する。データ座標へ逆変換する。
        # 仮マーカーはユーザーがクリックした場所(表示座標)に出す必要があるので、
        # 描画にはクリック位置をそのまま使う。
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
        """仮マーカーを「表示座標」に描く(改善ボード A-1)。

        guess は常にデータ座標で保持するが、マーカーはユーザーがクリックした
        位置、つまりトレースが実際に描かれている表示座標に出す必要がある
        (ウォーターフォール無効時は両者が一致する)。
        """
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
        for i, (guess, _line, point) in enumerate(self._pending_peak_markers):
            # ★ 改善ボード A-1: guess はデータ座標で保持しているため、クリック
            # 位置(表示座標)との距離比較には使えない。マーカーが実際に描かれて
            # いる位置を Artist から読み取って比較する(表示座標どうしの比較に
            # なり、ウォーターフォールの有無に関わらず正しく動く)。
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
