"""ピーク検出と、ピーク位置への自動ラベルの本体。"""
import logging

import numpy as np
import pandas as pd

from graphica.core.analysis import assign_peak_label_levels, calculate_peak_quantification, calculate_peaks
from graphica.core.dataset import Dataset
from graphica.gui.datasets.operations.runner import Operation
from graphica.gui.dialogs import PeakSettingsDialog, ResultDialog

logger = logging.getLogger(__name__)

_DEFAULT_PEAK_TYPE = "上に凸 (Peaks)"
PEAK_RESULT_WINDOW = "peaks"


def _ask_settings(op, dataset):
    """点数の確認と設定ダイアログ。"""
    if len(dataset.x_data) < 3:
        op.stop_with_warning("データ点数が少なすぎます (最低3点必要)。")
    settings = PeakSettingsDialog.get_peak_settings(op.parent)
    if settings is None:
        op.stop()
    return settings


def _detect(op, compute):
    # 検出の失敗は想定外のものも含めて知らせる(文字の X 列などで計算の途中から例外が出る)
    try:
        return compute()
    except Exception as e:
        logger.exception("ピーク検出に失敗しました")
        op.stop_with_warning(f"エラーが発生しました:\n{e}", title="ピーク検出エラー")


def find_peaks(op):
    """現在のデータセットのピーク(または谷)を探し、位置のデータセットと定量結果の表を出す。"""
    source = op.current_dataset()
    settings = _ask_settings(op, source)
    peak_type = settings.get("peak_type", _DEFAULT_PEAK_TYPE)

    quant = _detect(op, lambda: calculate_peak_quantification(source.x_data, source.y_data, peak_type, settings))

    peak_x, peak_y = quant['peak_x'], quant['peak_y']
    fwhm, area, centroid = quant['fwhm'], quant['area'], quant['centroid']
    if len(peak_x) == 0:
        op.stop_with_information(f"指定された条件で {peak_type} は見つかりませんでした。")

    is_valley = "下に凸" in peak_type
    op.host.add_derived_dataset(Dataset(
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
    op.show_result_window(PEAK_RESULT_WINDOW, lambda: ResultDialog("ピーク検出完了", text, op.parent, csv_data=table))


def add_peak_labels(op):
    """
    検出した各ピークの位置に X 値のラベルを付ける。近いピークは段を分けて縦にずらし、重ならないようにする。
    ずらす幅は軸の Y 表示幅に対する比率なので、スケールの違うデータでも見た目の間隔がそろう。
    """
    dataset = op.current_dataset()
    settings = _ask_settings(op, dataset)
    peak_type = settings.get("peak_type", _DEFAULT_PEAK_TYPE)

    peak_x, peak_y = _detect(op, lambda: calculate_peaks(dataset.x_data, dataset.y_data, peak_type, settings))
    if len(peak_x) == 0:
        op.stop_with_information(f"指定された条件で {peak_type} は見つかりませんでした。")

    order = np.argsort(peak_x)
    peak_x, peak_y = peak_x[order], peak_y[order]
    axis_index = dataset.subplot_target
    y_span = op.host.axis_y_span(axis_index)
    if y_span is None:
        y_span = 1.0
    x_span = float(np.max(peak_x) - np.min(peak_x)) if len(peak_x) > 1 else 0.0
    levels = assign_peak_label_levels(peak_x, x_span)

    with op.host.undo_macro(f"{op.title}追加 ({len(peak_x)}件)", enabled=len(peak_x) > 1):
        for x, y, level in zip(peak_x, peak_y, levels):
            op.host.add_annotation(axis_index, {
                'type': 'text', 'text': f"{x:.4g}",
                'xy': (float(x), float(y + y_span * (0.06 + 0.05 * level))), 'color': '#000000',
            }, description=f"{op.title}追加")


PEAK_OPERATIONS = {
    "find_peaks": Operation("ピーク検出", find_peaks),
    "add_peak_labels": Operation("ピーク位置への自動ラベル", add_peak_labels),
}
