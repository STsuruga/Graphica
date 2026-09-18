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
from core.app_paths import get_app_data_dir

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
        # ダイアログの表示自体に失敗しても、最低限ログには残るようにする
        logger.exception("クラッシュ案内ダイアログの表示に失敗しました。")


# --- セーフモード起動(項目F-4) ---
#
# gui/main_window.py の _check_autosave_recovery() が使う「clean_exit」
# QSettings追跡(2.1節/2.7節)を、別の目的(プラグイン無効化の提案)で
# 読み取り専用に流用する。書き込み(clean_exitキーのリセット/復元)は
# 引き続き PlotterApp.__init__/closeEvent の既存ロジックだけが行い、
# ここでは一切書き換えない。


def should_prompt_safe_mode(settings):
    """
    前回セッションが正常終了しなかった(clean_exit=False)かどうかを返す。

    settings は QSettings 互換オブジェクト(.value("clean_exit", True, type=bool)
    を持つもの)。main.py の起動シーケンスから、PlotterApp.__init__ が
    clean_exit キーを書き換える(Falseにリセットする)より前に呼ぶこと
    (呼び出し順序を誤ると、既に起動中の自分自身の書き込みを異常終了と
    誤検出してしまう)。
    """
    return not settings.value("clean_exit", True, type=bool)


def prompt_safe_mode_and_apply(settings, parent=None):
    """
    前回異常終了を検出した場合、プラグインを無効化して起動するかを
    QMessageBox.question で尋ね、Yesならcore.plugin_api.set_safe_mode(True)
    を呼ぶ。

    既定ボタンは No (=通常通りプラグインを読み込む) にしている。
    _check_autosave_recovery() の復元確認ダイアログは既定Yes(データ消失を
    避ける方向を既定にする)だが、こちらは逆に「普段使っているプラグインが
    ユーザーの意図なく無効化される」方が驚きが大きいため、あえて安全側
    (=何もしない)をNo側に置く。

    Returns:
        bool: セーフモードを有効化したかどうか。
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

    # プラグインAPI側への依存はここでのみ発生させる(crash_handlerは本来
    # 未処理例外まわりのモジュールだが、既存のclean_exit追跡を持つ
    # main_window.py 側ではなく、main.pyの起動シーケンスから呼びやすい
    # このモジュールに置くほうが自然なため、F-4の実装場所としてここを選んだ)。
    from core.plugin_api import set_safe_mode
    set_safe_mode(True)
    return True
