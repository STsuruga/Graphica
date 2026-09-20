"""未処理の例外で、ログの場所とオートセーブからの復元の手順を案内する(exe ではコンソールが無く、何も見えない)。"""
import sys
import os
import logging
import traceback

from PySide6.QtWidgets import QMessageBox

from graphica.core.version import APP_NAME, LOG_FILE_NAME
from graphica.core.app_paths import get_app_data_dir

logger = logging.getLogger(__name__)

_original_excepthook = sys.excepthook


def install_crash_handler():
    sys.excepthook = _handle_uncaught_exception


def _handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    """Ctrl+C(KeyboardInterrupt)は普通の終了なので案内しない。"""
    if issubclass(exc_type, KeyboardInterrupt):
        _original_excepthook(exc_type, exc_value, exc_traceback)
        return

    logger.critical("未処理の例外が発生しました。", exc_info=(exc_type, exc_value, exc_traceback))

    log_path = os.path.join(get_app_data_dir(), LOG_FILE_NAME)
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
        logger.exception("クラッシュ案内ダイアログの表示に失敗しました。")


# セーフモードで起動するかの確認。clean_exit を読むだけで、書き換えるのは PlotterApp だけ


def should_prompt_safe_mode(settings):
    """前回が正常に終わらなかったか。PlotterApp が clean_exit を False にする前に呼ぶこと(後だと自分を異常終了と見誤る)。"""
    return not settings.value("clean_exit", True, type=bool)


def prompt_safe_mode_and_apply(settings, parent=None):
    """前回が異常終了なら、プラグインなしで起動するか尋ねる。セーフモードにしたら True。

    既定のボタンは「いいえ」(いつものプラグインが知らないうちに無効になる方が驚く)。
    """
    if not should_prompt_safe_mode(settings):
        return False

    reply = QMessageBox.question(
        parent, f"{APP_NAME} - セーフモード起動",
        "前回異常終了を検出しました。プラグインを無効にして起動しますか?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return False

    from graphica.core.plugin_api import set_safe_mode
    set_safe_mode(True)
    return True
