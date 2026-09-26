"""データセットのデータ処理のメニューの入口。本体は gui/datasets/operations/processing.py の操作の表。"""
from graphica.gui.datasets.operations.processing import (INTEGRAL_RESULT_WINDOW, OUTLIER_RESULT_WINDOW,
                                                          PROCESSING_OPERATIONS)
from graphica.gui.datasets.operations.runner import OperationState, run_operation


class ProcessingController:
    """現在のデータセット(または選択中の複数)から新しいデータセットを作る、または行を除外する処理。"""

    def __init__(self, host):
        self._host = host
        self._state = OperationState()

    @property
    def integral_result_dialog(self):
        return self._state.result_windows.get(INTEGRAL_RESULT_WINDOW)

    @property
    def outlier_result_dialog(self):
        return self._state.result_windows.get(OUTLIER_RESULT_WINDOW)

    def _run(self, name):
        run_operation(PROCESSING_OPERATIONS[name], self._host, self._state)

    def arithmetic(self):
        self._run("arithmetic")

    def align_selected(self):
        self._run("align")

    def mean_and_sd_of_selected(self):
        self._run("mean_and_sd")

    def normalize(self):
        self._run("normalize")

    def savgol_smooth(self):
        self._run("savgol_smooth")

    def baseline_correction(self):
        self._run("baseline_correction")

    def interval_integral(self):
        self._run("interval_integral")

    def cumulative_integral(self):
        self._run("cumulative_integral")

    def split_by_column(self):
        self._run("split_by_column")

    def resample(self):
        self._run("resample")

    def histogram_or_kde(self):
        self._run("histogram_or_kde")

    def detect_duplicate_x(self):
        self._run("detect_duplicate_x")

    def filter_rows(self):
        self._run("filter_rows")

    def detect_outliers(self):
        self._run("detect_outliers")

    def batch_column_calculate(self):
        self._run("batch_column_calculate")
