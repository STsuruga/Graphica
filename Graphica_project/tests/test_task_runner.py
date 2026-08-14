# tests/test_task_runner.py
"""gui/task_runner.py の TaskRunner に対するテスト(項目C-004フェーズ1)。

gui/workers.py の DataLoadWorker と同じ方針: 大半は run() をスレッドを
介さず直接メソッドとして呼ぶ形で検証し(tests/test_workers.py参照)、
closeEvent連携の1本だけ実スレッド(.start())を使う。
"""
import time

import pytest

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


def test_run_does_not_emit_succeeded_when_cancelled_before_finishing(qapp):
    """
    requestInterruption()がrun()完了前に呼ばれた場合、succeededは出さない
    (呼び出し側がキャンセル後の結果を誤って適用しないようにするため)。
    ★ QThread.isInterruptionRequested()はPySide6/Qt内部でrunning状態を
    見ているため、start()を経由しない(run()を素のメソッドとして直接呼ぶ)
    テストでは常にFalseを返してしまい、この挙動を検証できない。このテストだけ
    実スレッド(.start())を使う。"""
    def _slow_task(report_progress=None, is_cancelled=None):
        time.sleep(0.2)
        return 99

    runner = TaskRunner(_slow_task)
    succeeded_calls = []
    runner.succeeded.connect(lambda result: succeeded_calls.append(result))

    runner.start()
    runner.requestInterruption()
    runner.wait()

    assert succeeded_calls == []


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
    ワーカーが片付いていること。gui/main_window.pyのDataLoadWorker用
    closeEventブロックと同型の手順をTaskRunner単体で直接検証する
    (フルのPlotterAppを介さないため、Qt/matplotlibリソース蓄積を避けられる)。
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
