import sys
import os
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

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

if __name__ == '__main__':
    _setup_logging()
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