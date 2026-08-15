# gui/task_runner.py
"""
時間のかかる処理を任意の関数として渡し、バックグラウンドスレッドで実行するための
汎用ワーカー(項目C-004: ワーカースレッド基盤)。

当初は gui/workers.py のファイル読み込み専用ワーカー(DataLoadWorker、QThread
サブクラス)と同じ設計・エラー規約(str(例外)のみをシグナルで運ぶ)を踏襲しつつ、
特定の処理専用ではなく任意の関数を注入できるよう一般化したクラスとして導入した。
既に固まっている closeEvent 連携のリスクを避けるため当初は DataLoadWorker 自体を
このクラスへ移行しない方針だったが、項目C-004フェーズ4でこの移行を実施済み
(gui/workers.py の load_data_file_task が実際の注入対象、gui/main_window.py の
closeEvent には他のTaskRunnerと同型のクリーンアップブロックが並ぶ)。
DataLoadWorkerクラス自体は削除済み。
"""
import logging
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class TaskRunner(QThread):
    """
    任意の関数 fn(*args, report_progress, is_cancelled, **kwargs) をバックグラウンド
    スレッドで実行する。report_progress(done, total, message="") / is_cancelled() -> bool
    の2つはキーワード引数として常に渡されるが、使うかどうかは fn 側の自由
    (単発フィットのように中断不能な処理では単に無視してよい)。

    fn は core/ 側のプレーンな関数を想定しており、Qt に依存させない
    (report_progress/is_cancelled はただの callable として渡すだけなので、
    fn 自身が PySide6 をimportする必要はない)。

    ★ キャンセル時に何を結果として扱うか(何も返さない/計算済み分だけの
    部分結果を返す等)はfn自身の責任とし、TaskRunner側では一切判定・介入
    しない。fn が例外を投げずに正常return した場合は、isInterruptionRequested()
    の状態に関わらず常にsucceededをそのまま出す(fn自身がis_cancelled()を
    見て早期returnし、部分結果を返すという使い方を妨げないため)。
    当初は「isInterruptionRequested()中ならsucceededを抑制する」という
    ポリシーをTaskRunner側に持たせていたが、これだと一括カーブフィット
    (項目C-004フェーズ2)のような「キャンセル時は完了済み分の部分結果を
    そのまま使いたい」ケースで、正常に返ってきた部分結果ごと握りつぶされ、
    succeeded/failedのどちらも発火せず呼び出し元が永遠に完了を待ち続ける
    実バグを起こした(tests/test_dataset_mixin.pyのバッチフィットキャンセル
    テストで発覚)。
    """
    progress = Signal(int, int, str)   # (done, total, message)
    succeeded = Signal(object)         # fn() の戻り値をそのまま渡す
    failed = Signal(str)               # str(例外) — DataLoadWorkerと同じ規約

    def __init__(self, fn, *args, parent=None, **kwargs):
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        def _report_progress(done, total, message=""):
            self.progress.emit(done, total, message)

        try:
            result = self._fn(
                *self._args,
                report_progress=_report_progress,
                is_cancelled=self.isInterruptionRequested,
                **self._kwargs,
            )
        except Exception as e:
            logger.exception("バックグラウンドタスクが失敗しました")
            self.failed.emit(str(e))
            return

        self.succeeded.emit(result)
