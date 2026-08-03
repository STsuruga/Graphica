# gui/crash_handler.py
"""
未処理の例外(どこでもキャッチされずに上がってきたもの)に対する、
ユーザー向けの案内を担当するモジュール。

.exe化(PyInstaller)するとコンソールが表示されないため、何も対策しないと
未処理の例外が発生した際、ユーザーには「何も起きていないように見えるが操作が
効かない/おかしい」という最悪のUXになってしまう。
sys.excepthook を差し替えることで、通常のログ出力に加えて、ログの場所と
オートセーブ復元の手順を案内するダイアログを表示するようにする。
"""
import sys
import os
import logging
import traceback

from PySide6.QtWidgets import QMessageBox

from core.version import APP_NAME, LOG_FILE_NAME

logger = logging.getLogger(__name__)

_original_excepthook = sys.excepthook


def install_crash_handler():
    """アプリ起動時に一度だけ呼び出し、グローバルな未処理例外ハンドラを差し替える"""
    sys.excepthook = _handle_uncaught_exception


def _handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    """
    sys.excepthook として登録される関数。
    Ctrl+C (KeyboardInterrupt) は通常のシャットダウン操作なので、
    案内ダイアログを出さず元の挙動に任せる。
    """
    if issubclass(exc_type, KeyboardInterrupt):
        _original_excepthook(exc_type, exc_value, exc_traceback)
        return

    logger.critical("未処理の例外が発生しました。", exc_info=(exc_type, exc_value, exc_traceback))

    log_path = os.path.abspath(LOG_FILE_NAME)
    detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

    try:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(f"{APP_NAME} - 予期しないエラー")
        box.setText(
            "予期しないエラーが発生しました。\n\n"
            "これまでの作業内容はオートセーブされている可能性があります。"
            f"このまま{APP_NAME}を再起動すると、自動保存からの復元を提案する画面が表示されます。\n\n"
            f"詳細はログファイルを確認してください:\n{log_path}"
        )
        box.setDetailedText(detail)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()
    except Exception:
        # ダイアログの表示自体に失敗しても、最低限ログには残るようにする
        logger.exception("クラッシュ案内ダイアログの表示に失敗しました。")
