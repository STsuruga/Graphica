# gui/task_runner.py
"""
時間のかかる処理を任意の関数として渡し、バックグラウンドスレッドで実行するための
汎用ワーカー(項目C-004: ワーカースレッド基盤)。

gui/workers.py の DataLoadWorker と同じ QThread ベースの設計・エラー規約
(str(例外)のみをシグナルで運ぶ)を踏襲しつつ、特定の処理(ファイル読み込み)
専用ではなく任意の関数を注入できるようにしたもの。DataLoadWorker 自体は
このクラスへ移行しない(既に固まっている closeEvent 連携のリスクを避けるため。
gui/main_window.py の closeEvent には TaskRunner 用のクリーンアップブロックを
別途追加する形にし、重複は許容する)。
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

        # キャンセル済みの場合、succeeded は出さない(呼び出し側がキャンセル後の
        # 結果を誤って適用しないようにするため)。
        if self.isInterruptionRequested():
            return
        self.succeeded.emit(result)
