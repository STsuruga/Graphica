# tests/test_task_runner.py
"""gui/task_runner.py の TaskRunner に対するテスト(項目C-004フェーズ1/2)。

gui/workers.py の DataLoadWorker と同じ方針: 大半は run() をスレッドを
介さず直接メソッドとして呼ぶ形で検証し(tests/test_workers.py参照)、
実スレッド(.start())が必要なテスト(closeEvent連携、キャンセル関連)だけ
個別に使う。実スレッド経由のsucceededシグナルはキュー接続で main スレッドの
イベントループ処理を待つため、wait()の後に必ずapp.processEvents()を挟むこと
(挟まないとシグナルが配送されず、コールバックが呼ばれないまま静かに
テストが失敗する)。
"""
import time

import pytest
from PySide6.QtWidgets import QApplication

from gui.task_runner import TaskRunner


def _ok_task(x, y, report_progress=None, is_cancelled=None):
    if report_progress is not None:
        report_progress(1, 1, "done")
    return x + y


def _failing_task(report_progress=None, is_cancelled=None):
    raise ValueError("boom")


def _cancel_aware_task(report_progress=None, is_cancelled=None):
    # is_cancelled は isInterruptionRequested を渡す規約(呼び出し可能かどうかだけ確認)
    return is_cancelled()


# --- TaskRunner.run() を直接呼ぶテスト(スレッドを介さない) ---

def test_run_emits_succeeded_with_function_return_value(qapp):
    runner = TaskRunner(_ok_task, 2, 3)
    succeeded_calls = []
    failed_calls = []
    runner.succeeded.connect(lambda result: succeeded_calls.append(result))
    runner.failed.connect(lambda msg: failed_calls.append(msg))

    runner.run()

    assert failed_calls == []
    assert succeeded_calls == [5]


def test_run_emits_failed_with_str_of_exception(qapp):
    runner = TaskRunner(_failing_task)
    succeeded_calls = []
    failed_calls = []
    runner.succeeded.connect(lambda result: succeeded_calls.append(result))
    runner.failed.connect(lambda msg: failed_calls.append(msg))

    runner.run()

    assert succeeded_calls == []
    assert len(failed_calls) == 1
    assert "boom" in failed_calls[0]


def test_cancellation_handling_is_entirely_up_to_the_work_function(qapp):
    """
    TaskRunner自身はisInterruptionRequested()を見てsucceeded/failedの発火可否を
    判定しない(fnがキャンセル済みでも正常な値を返せば、その値でsucceededが
    そのまま発火する)。★ この仕様は意図的: 当初はTaskRunner側で
    「isInterruptionRequested()中はsucceededを抑制する」ポリシーを持たせて
    いたが、一括カーブフィット(項目C-004フェーズ2)のように「キャンセル時は
    計算済み分の部分結果をそのまま使いたい」ケースで、正常に返ってきた部分
    結果ごと握りつぶされ、succeeded/failedのどちらも発火せず呼び出し元が
    永遠に完了を待ち続ける実バグを起こしたため、判定をfn側の責任に一本化した。
    ★ QThread.isInterruptionRequested()はPySide6/Qt内部でrunning状態を見ているため、
    start()を経由しない(run()を素のメソッドとして直接呼ぶ)テストでは常にFalseを
    返してしまい、この挙動を検証できない。このテストだけ実スレッド(.start())を使う。
    """
    def _slow_task_that_ignores_cancellation(report_progress=None, is_cancelled=None):
        time.sleep(0.2)
        return 99  # is_cancelled()の状態を見ずに常に正常値を返す

    runner = TaskRunner(_slow_task_that_ignores_cancellation)
    succeeded_calls = []
    runner.succeeded.connect(lambda result: succeeded_calls.append(result))

    runner.start()
    runner.requestInterruption()
    runner.wait()
    QApplication.instance().processEvents()  # キュー配信されたsucceededシグナルを配送する

    assert succeeded_calls == [99]


def test_work_function_can_return_partial_result_when_cancelled(qapp):
    """
    fn自身がis_cancelled()を見て早期に部分結果を返すパターン(一括カーブ
    フィットが実際に使う形)が、正しくsucceededとして呼び出し元に届くこと。
    """
    def _task_checking_cancellation(report_progress=None, is_cancelled=None):
        completed = []
        for i in range(5):
            if is_cancelled():
                break
            time.sleep(0.05)
            completed.append(i)
        return completed

    runner = TaskRunner(_task_checking_cancellation)
    succeeded_calls = []
    runner.succeeded.connect(lambda result: succeeded_calls.append(result))

    runner.start()
    time.sleep(0.12)  # 2〜3件が終わるくらいで割り込む
    runner.requestInterruption()
    runner.wait()
    QApplication.instance().processEvents()  # キュー配信されたsucceededシグナルを配送する

    assert succeeded_calls
    assert 0 < len(succeeded_calls[0]) < 5


def test_fn_receives_report_progress_and_is_cancelled_kwargs(qapp):
    runner = TaskRunner(_cancel_aware_task)
    succeeded_calls = []
    runner.succeeded.connect(lambda result: succeeded_calls.append(result))

    runner.run()

    assert succeeded_calls == [False]  # requestInterruption()していないのでFalse


def test_progress_signal_forwards_report_progress_calls(qapp):
    runner = TaskRunner(_ok_task, 4, 5)
    progress_calls = []
    runner.progress.connect(lambda done, total, message: progress_calls.append((done, total, message)))

    runner.run()

    assert progress_calls == [(1, 1, "done")]


# --- 実スレッド(.start())を使うテスト: closeEvent連携の検証 ---

def test_close_event_waits_for_in_flight_fit_task_runner_instead_of_crashing(qapp):
    """
    C-003/C-004どちらの回帰でもない基礎的な確認: 実行中のTaskRunnerを
    closeEvent相当の後始末(シグナル切断→requestInterruption→wait→
    deleteLater)にかけても、プロセスがクラッシュせず、待機後に
    ワーカーが片付いていること。gui/main_window.pyの各TaskRunner用
    closeEventブロック(_fit_task_runner/_batch_fit_task_runner/
    _data_load_task_runner/_batch_export_task_runner、いずれも同型)と
    同じ手順をTaskRunner単体で直接検証する(フルのPlotterAppを介さないため、
    Qt/matplotlibリソース蓄積を避けられる)。
    """
    def _slow_task(report_progress=None, is_cancelled=None):
        time.sleep(0.3)
        return 42

    runner = TaskRunner(_slow_task)
    succeeded_calls = []
    runner.succeeded.connect(lambda result: succeeded_calls.append(result))

    runner.start()
    assert runner.isRunning()

    # main_window.py の closeEvent と同じ手順
    try:
        runner.succeeded.disconnect()
    except (RuntimeError, TypeError):
        pass
    runner.requestInterruption()
    runner.wait()
    runner.deleteLater()

    assert not runner.isRunning()
    # disconnect済みのため、バックグラウンドで完了していてもスロットは呼ばれない
    assert succeeded_calls == []


def test_close_event_waits_for_in_flight_data_load_task_runner_instead_of_crashing(qapp, tmp_path, monkeypatch):
    """
    項目C-004フェーズ4: load_data_file_task()を実際に注入したTaskRunnerでも、
    上のテストと同じclose_event相当の後始末が安全に完了すること
    (gui/main_window.pyのPlotterAppを介さない、load_data_file_task単体の
    スレッド安全性の確認)。
    """
    import gui.workers as workers_module
    from gui.workers import load_data_file_task

    csv_path = tmp_path / "slow.csv"
    csv_path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")

    original_read_data_file = workers_module.read_data_file

    def _slow_read_data_file(file_path):
        time.sleep(0.3)
        return original_read_data_file(file_path)

    monkeypatch.setattr(workers_module, "read_data_file", _slow_read_data_file)

    runner = TaskRunner(load_data_file_task, str(csv_path))
    succeeded_calls = []
    runner.succeeded.connect(lambda df: succeeded_calls.append(df))

    runner.start()
    assert runner.isRunning()

    try:
        runner.succeeded.disconnect()
    except (RuntimeError, TypeError):
        pass
    runner.requestInterruption()
    runner.wait()
    runner.deleteLater()

    assert not runner.isRunning()
    assert succeeded_calls == []
