"""曲線フィット(単発・一括・多峰分離)と、フィット結果の再表示・注釈への焼き込みのメニューの入口。

本体は gui/datasets/operations/fitting.py。計算は裏で動き、終わったら結果を足す。
"""
from graphica.gui.datasets.operations.fitting import (BATCH_FIT_RUNNER, FIT_RESULT_WINDOW, FIT_RUNNER,
                                                      FITTING_OPERATIONS, MULTI_PEAK_FIT_RUNNER, RUNNER_NAMES,
                                                      burn_operation, stop_runner)
from graphica.gui.datasets.operations.runner import OperationState, run_operation


class FittingController:

    def __init__(self, host):
        self._host = host
        self._state = OperationState()

    @property
    def result_dialog(self):
        """結果は非モーダルで出し、グラフと見比べられるようにする。"""
        return self._state.result_windows.get(FIT_RESULT_WINDOW)

    @property
    def fit_runner(self):
        return self._state.runners.get(FIT_RUNNER)

    @fit_runner.setter
    def fit_runner(self, runner):
        self._state.runners[FIT_RUNNER] = runner

    @property
    def batch_fit_runner(self):
        return self._state.runners.get(BATCH_FIT_RUNNER)

    @batch_fit_runner.setter
    def batch_fit_runner(self, runner):
        self._state.runners[BATCH_FIT_RUNNER] = runner

    @property
    def multi_peak_fit_runner(self):
        return self._state.runners.get(MULTI_PEAK_FIT_RUNNER)

    @multi_peak_fit_runner.setter
    def multi_peak_fit_runner(self, runner):
        self._state.runners[MULTI_PEAK_FIT_RUNNER] = runner

    def shutdown(self):
        """タブを閉じる前に、実行中の計算を待って片付ける(curve_fit 自体は中断できない)。"""
        for name in RUNNER_NAMES:
            runner = self._state.runners.get(name)
            if runner is not None:
                stop_runner(runner)
                self._state.runners[name] = None

    def _run(self, operation):
        run_operation(operation, self._host, self._state)

    def fit_current_dataset(self):
        self._run(FITTING_OPERATIONS["fit_current_dataset"])

    def batch_fit_selected(self):
        self._run(FITTING_OPERATIONS["batch_fit_selected"])

    def multi_peak_fit_current_dataset(self):
        self._run(FITTING_OPERATIONS["multi_peak_fit_current_dataset"])

    def show_fit_result(self):
        self._run(FITTING_OPERATIONS["show_fit_result"])

    def burn_fit_result_annotation(self, dataset, fit_result):
        self._run(burn_operation(dataset, fit_result))
