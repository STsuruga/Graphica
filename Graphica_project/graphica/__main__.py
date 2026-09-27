import sys
import os
import logging

# Win32 の SetProcessDpiAwareness() を呼ばないこと。DPI の認識モードはプロセスで1回しか設定できず、
# 先に呼ぶと Qt の設定が失敗して、描画とクリックの位置がずれる。

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QGuiApplication

# ここでは軽いモジュールだけを読む。pandas・scipy・matplotlib を引くもの(main_app_window・plugin_api)は
# 起動画面を出してから main() の中で読む(読み込みに 2〜3 秒かかり、その間に何も出ないと起動に気づけない)
from graphica.gui import app_settings
from graphica.gui.crash_handler import install_crash_handler, prompt_safe_mode_and_apply
from graphica.core.i18n import set_language, tr
from graphica.core.version import LOG_FILE_NAME
from graphica.core.app_paths import get_app_data_dir

# UI のフォント。無ければ Qt が次の候補を使う
APP_FONT_FAMILIES = ["Yu Gothic UI", "Meiryo UI", "Segoe UI"]
APP_FONT_POINT_SIZE = 9.5

def _setup_logging():
    """ログはファイルにも書く(exe ではコンソールが無い)。場所は get_app_data_dir()(Program Files の下には書けない)。"""
    log_path = os.path.join(get_app_data_dir(), LOG_FILE_NAME)
    handlers = [logging.FileHandler(log_path, encoding="utf-8")]
    # コンソールの無い起動(pip の gui-scripts・exe)では sys.stdout が None
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    # グラフのフォントは OS ごとの候補を並べていて、無いものごとに描くたび警告が出てログが膨らむ
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

def _safe_mode_flag_requested(argv):
    """--safe-mode が指定されたか(ウィンドウを作らずにテストできるよう分けてある)。"""
    return "--safe-mode" in argv


def main():
    _setup_logging()
    # 拡大率の違うモニターの間で、描画とクリックの位置がずれないよう、倍率を丸めない。QApplication より前に
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    install_crash_handler()
    app = QApplication(sys.argv)

    app_font = QFont()
    app_font.setFamilies(APP_FONT_FAMILIES)
    app_font.setPointSizeF(APP_FONT_POINT_SIZE)
    app.setFont(app_font)

    settings = app_settings.open_settings()
    # 起動画面の文字の言語。最初のタブも同じ値で設定し直す
    set_language(app_settings.LANGUAGE.read(settings))

    # プラグインは最初のタブを作るときに読むので、その前に決める。尋ねる画面は起動画面より前に出す(後ろに隠れないように)
    safe_mode_requested = _safe_mode_flag_requested(sys.argv)
    if not safe_mode_requested:
        # 前回が異常終了なら、プラグインなしで起動するか尋ねる。clean_exit を書き換えるのは PlotterApp だけ
        prompt_safe_mode_and_apply(settings)

    from graphica.gui.splash import show_startup_splash
    splash = show_startup_splash(dark=app_settings.DARK_MODE.read(settings))

    splash.show_progress(tr("ライブラリを読み込み中…"))
    from graphica.core.plugin_api import set_safe_mode
    from graphica.gui.main_app_window import MainAppWindow
    from graphica.gui.theme import disable_scroll_value_change

    disable_scroll_value_change()
    if safe_mode_requested:
        # 明示的に指定されたので尋ねない
        set_safe_mode(True)

    splash.show_progress(tr("ウィンドウを準備中…"))
    window = MainAppWindow()
    window.show()
    # 復元の確認やようこそ画面は、イベントループが回ってから出るので、その前に閉じる
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()