"""データセットに結びつけて図に重ねる表示: 統計値ラベルと拡大図(インセット)。"""
import numpy as np
from PySide6.QtWidgets import QDialog

from graphica.gui import notify
from graphica.gui.dialogs import InsetDialog

# 表示名 -> 描画側(canvas の _compute_stat_label_text)が解釈するキー
STAT_LABEL_CHOICES = {
    'R²': 'r_squared', 'Y平均': 'mean', 'Y標準偏差': 'std',
    'Y最大値': 'max', 'Y最小値': 'min',
}


class OverlayController:
    """今のデータセットに結びつけて図に重ねる表示(統計値ラベル、拡大図)を足す。"""

    def __init__(self, host):
        self._host = host

    def add_stat_label(self):
        """
        今のデータセットの統計値(R²・平均など)を、その軸の左上から縦に積んで表示する。
        値は描画のたびに計算し直すので、後でフィットし直しても追従する。
        """
        dataset = self._host.current_dataset()
        if dataset is None:
            return

        choice, ok = notify.get_item(
            self._host.parent_widget, "統計値アンカーラベルの追加", "表示する統計値:",
            list(STAT_LABEL_CHOICES.keys()), 0, False
        )
        if not ok:
            return
        stat = STAT_LABEL_CHOICES[choice]

        axis_index = dataset.subplot_target
        existing_stat_count = sum(
            1 for ann in self._host.annotations(axis_index) if ann.get('type') == 'stat'
        )
        xy = (0.05, max(0.95 - 0.07 * existing_stat_count, 0.05))

        self._host.add_annotation(axis_index, {
            'type': 'stat', 'dataset_id': dataset.dataset_id, 'stat': stat,
            'xy': xy, 'color': '#000000',
        }, description="統計値アンカーラベルの追加")

    def add_inset(self):
        """今のデータセットの X 範囲の一部を拡大した小さな図を、その軸に重ねる。"""
        dataset = self._host.current_dataset()
        if dataset is None:
            return

        x_data = np.asarray(dataset.x_data, dtype=float)
        x_data = x_data[~np.isnan(x_data)]
        if len(x_data) < 2:
            notify.warning(self._host.parent_widget, "インセット(拡大図)", "有効なデータ点が不足しています(最低2点必要)。")
            return
        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        span = x_max - x_min
        default_zoom_min = x_min + span * 0.4
        default_zoom_max = x_min + span * 0.6

        dialog = InsetDialog(x_min, x_max, default_zoom_min, default_zoom_max, parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.get_settings()

        axis_index = dataset.subplot_target
        self._host.add_annotation(axis_index, {
            'type': 'inset', 'corner': settings['corner'], 'size': settings['size'],
            'zoom_x_range': settings['zoom_x_range'], 'color': '#000000',
        }, description="インセット(拡大図)の追加")
