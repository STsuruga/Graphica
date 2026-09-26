"""ピーク検出と、ピーク位置への自動ラベルのメニューの入口。本体は gui/datasets/operations/peaks.py。"""
from graphica.gui.datasets.operations.peaks import PEAK_OPERATIONS, PEAK_RESULT_WINDOW
from graphica.gui.datasets.operations.runner import OperationState, run_operation


class PeakController:

    def __init__(self, host):
        self._host = host
        self._state = OperationState()

    @property
    def result_dialog(self):
        """結果は非モーダルで出し、グラフと見比べられるようにする。"""
        return self._state.result_windows.get(PEAK_RESULT_WINDOW)

    def find_peaks(self):
        run_operation(PEAK_OPERATIONS["find_peaks"], self._host, self._state)

    def add_peak_labels(self):
        run_operation(PEAK_OPERATIONS["add_peak_labels"], self._host, self._state)
