"""ピーク検出と、ピーク位置への自動ラベル。"""
import logging

import numpy as np
import pandas as pd

from graphica.gui import notify
from graphica.core.analysis import assign_peak_label_levels, calculate_peak_quantification, calculate_peaks
from graphica.core.dataset import Dataset
from graphica.gui.dialogs import PeakSettingsDialog, ResultDialog

logger = logging.getLogger(__name__)

_DEFAULT_PEAK_TYPE = "上に凸 (Peaks)"


class PeakController:

    def __init__(self, host):
        self._host = host
        self.result_dialog = None  # 結果は非モーダルで出し、グラフと見比べられるようにする

    def _ask_settings(self, dataset, title):
        """点数の確認と設定ダイアログ。続けられないときは None。"""
        if len(dataset.x_data) < 3:
            notify.warning(self._host.parent_widget, title, "データ点数が少なすぎます (最低3点必要)。")
            return None
        return PeakSettingsDialog.get_peak_settings(self._host.parent_widget)

    def _warn_failure(self, error):
        logger.exception("ピーク検出に失敗しました")
        notify.warning(self._host.parent_widget, "ピーク検出エラー", f"エラーが発生しました:\n{error}")

    def find_peaks(self):
        """現在のデータセットのピーク(または谷)を探し、位置のデータセットと定量結果の表を出す。"""
        source = self._host.current_dataset()
        if source is None:
            return
        settings = self._ask_settings(source, "ピーク検出")
        if settings is None:
            return
        peak_type = settings.get("peak_type", _DEFAULT_PEAK_TYPE)

        try:
            quant = calculate_peak_quantification(source.x_data, source.y_data, peak_type, settings)
        except Exception as e:
            self._warn_failure(e)
            return

        peak_x, peak_y = quant['peak_x'], quant['peak_y']
        fwhm, area, centroid = quant['fwhm'], quant['area'], quant['centroid']
        if len(peak_x) == 0:
            notify.information(self._host.parent_widget, "ピーク検出",
                                    f"指定された条件で {peak_type} は見つかりませんでした。")
            return

        is_valley = "下に凸" in peak_type
        self._host.add_derived_dataset(Dataset(
            name=f"{peak_type.split(' ')[0]} ({source.name})",
            df=pd.DataFrame({'peak_x': peak_x, 'peak_y': peak_y}),
            x_col_name='peak_x', y_col_name='peak_y',
            plot_type='Scatter', color='blue' if is_valley else 'red', linestyle='None',
            marker='^' if is_valley else 'v', markersize=8,
            use_secondary_y=source.use_secondary_y,
            subplot_target=source.subplot_target,
        ), source)

        order = np.argsort(peak_x)
        text = (
            f"検出された {peak_type} ({len(peak_x)}個):\n"
            "  X座標\t\tY座標\t\tFWHM\t\t面積\t\t重心X\n" + "-" * 70 + "\n"
        )
        for i in order:
            text += (f"  {peak_x[i]:.4g}\t\t{peak_y[i]:.4g}\t\t{fwhm[i]:.4g}"
                     f"\t\t{area[i]:.4g}\t\t{centroid[i]:.4g}\n")
        table = pd.DataFrame({
            'X座標': peak_x[order], 'Y座標': peak_y[order], 'FWHM': fwhm[order],
            '面積': area[order], '重心X': centroid[order],
        })
        if self.result_dialog is not None:
            self.result_dialog.close()
        self.result_dialog = ResultDialog("ピーク検出完了", text, self._host.parent_widget, csv_data=table)
        self.result_dialog.show()

    def add_peak_labels(self):
        """
        検出した各ピークの位置に X 値のラベルを付ける。近いピークは段を分けて縦にずらし、重ならないようにする。
        ずらす幅は軸の Y 表示幅に対する比率なので、スケールの違うデータでも見た目の間隔がそろう。
        """
        title = "ピーク位置への自動ラベル"
        dataset = self._host.current_dataset()
        if dataset is None:
            return
        settings = self._ask_settings(dataset, title)
        if settings is None:
            return
        peak_type = settings.get("peak_type", _DEFAULT_PEAK_TYPE)

        try:
            peak_x, peak_y = calculate_peaks(dataset.x_data, dataset.y_data, peak_type, settings)
        except Exception as e:
            self._warn_failure(e)
            return
        if len(peak_x) == 0:
            notify.information(self._host.parent_widget, title,
                                    f"指定された条件で {peak_type} は見つかりませんでした。")
            return

        order = np.argsort(peak_x)
        peak_x, peak_y = peak_x[order], peak_y[order]
        axis_index = dataset.subplot_target
        y_span = self._host.axis_y_span(axis_index)
        if y_span is None:
            y_span = 1.0
        x_span = float(np.max(peak_x) - np.min(peak_x)) if len(peak_x) > 1 else 0.0
        levels = assign_peak_label_levels(peak_x, x_span)

        with self._host.undo_macro(f"{title}追加 ({len(peak_x)}件)", enabled=len(peak_x) > 1):
            for x, y, level in zip(peak_x, peak_y, levels):
                self._host.add_annotation(axis_index, {
                    'type': 'text', 'text': f"{x:.4g}",
                    'xy': (float(x), float(y + y_span * (0.06 + 0.05 * level))), 'color': '#000000',
                }, description=f"{title}追加")
