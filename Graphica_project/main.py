import sys
import os
import logging
from PySide6.QtWidgets import QApplication

# 複数プロジェクトタブ(項目40)に対応した最上位ウィンドウ。
# 内部で PlotterApp を各タブとして生成する。
from gui.main_app_window import MainAppWindow
from gui.crash_handler import install_crash_handler
from core.version import LOG_FILE_NAME

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

    # 最上位ウィンドウ (複数プロジェクトタブを管理する) のインスタンスを作成して表示
    window = MainAppWindow()
    window.show()

    sys.exit(app.exec())