"""時間のかかる関数を別スレッドで動かす。"""
import logging
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class TaskRunner(QThread):
    """fn(*args, report_progress, is_cancelled, **kwargs) を別スレッドで動かす。

    report_progress(done, total, message="") と is_cancelled() は必ず渡る(使うかは fn の自由)。fn は Qt に依存させない。
    fn が普通に戻れば、キャンセル中でも succeeded を出す(キャンセル時に途中までの結果を返す使い方のため。
    抑えると succeeded も failed も出ず、呼び出し側が待ち続ける)。
    """
    progress = Signal(int, int, str)   # (done, total, message)
    succeeded = Signal(object)         # fn の戻り値
    failed = Signal(str)               # str(例外)

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
