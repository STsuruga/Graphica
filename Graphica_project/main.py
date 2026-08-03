import sys
import os
import logging

# ★ マルチモニターでDPI(拡大率)が異なる環境(例: メイン100%・サブ125%)で、
#   ボタン等の見た目上の描画位置と実際のクリック判定位置がずれ、「ボタンが
#   反応しない」ように見える既知の問題への対策。
#   Windowsでは、プロセスのDPI認識モード(DPI awareness)はプロセス生成時の
#   マニフェスト設定で一度だけ決まり、後からQt側の設定(HighDpiScaleFactor
#   RoundingPolicy等)で上書きすることはできない。python.exeで直接実行する
#   場合、Pythonインストーラのマニフェストが「System DPI Aware」(モニターご
#   とではなく1つの固定DPI)になっていることが多く、これがモニター間での
#   ジオメトリ不整合の根本原因になり得る。QtやPySide6を一切importする前に、
#   Win32 API で明示的に「Per-Monitor DPI Aware (v2)」を要求することで、
#   実行方法(python.exe直接実行 / .exe化)によらず正しいモード認識を保証する。
if sys.platform == "win32":
    try:
        import ctypes
        # PROCESS_PER_MONITOR_DPI_AWARE = 2 (SetProcessDpiAwareness, shcore.dll)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        # 古いWindows(shcore.dllが無い等)や、既に別の方法でDPI認識モードが
        # 設定済みの場合はエラーになるが、アプリの起動自体は継続してよい。
        pass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QGuiApplication

# 複数プロジェクトタブ(項目40)に対応した最上位ウィンドウ。
# 内部で PlotterApp を各タブとして生成する。
from gui.main_app_window import MainAppWindow
from gui.crash_handler import install_crash_handler
from gui.theme import disable_scroll_value_change
from core.version import LOG_FILE_NAME

# アプリ全体のUIフォント。既定の "MS Shell Dlg 2"(素朴な見た目)ではなく、
# Windows 10/11 の設定アプリ等でも使われている「Yu Gothic UI」を明示的に使う。
# フォントが存在しない環境でも Qt が自動的にフォールバックするよう、
# 優先順にリストで指定する(GUI洗練)。
APP_FONT_FAMILIES = ["Yu Gothic UI", "Meiryo UI", "Segoe UI"]
APP_FONT_POINT_SIZE = 9.5

def _setup_logging():
    """アプリ全体のログ設定。.exe化するとコンソールが見えないため、ファイルにも出力する。"""
    log_path = os.path.join(os.path.abspath("."), LOG_FILE_NAME)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

def main():
    _setup_logging()
    # マルチモニターでDPI(拡大率)が異なる環境(例: メイン100%・サブ125%)で、
    # ボタン等の見た目上の描画位置と実際のクリック判定位置がずれ、「ボタンが
    # 反応しない」ように見える既知のQt/Windowsの問題への対策。
    # PassThroughは実際のスケール係数をそのまま使い、モニター間の切り替え時の
    # 丸め誤差によるジオメトリ不整合を避ける。QApplication生成前に設定する必要がある。
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    # 未処理の例外発生時、ログの場所とオートセーブ復元手順を案内するダイアログを表示する
    install_crash_handler()
    app = QApplication(sys.argv)

    app_font = QFont()
    app_font.setFamilies(APP_FONT_FAMILIES)
    app_font.setPointSizeF(APP_FONT_POINT_SIZE)
    app.setFont(app_font)

    # スクロール操作でスピンボックス/コンボボックスの値が意図せず変わって
    # しまうのを防ぐ(フォーカスしている時だけホイールで値を変更できる)
    disable_scroll_value_change()

    # 最上位ウィンドウ (複数プロジェクトタブを管理する) のインスタンスを作成して表示
    window = MainAppWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()