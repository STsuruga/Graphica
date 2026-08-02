import sys
import os
import logging
from PySide6.QtWidgets import QApplication

# 自分で分割した PlotterApp をインポート
from gui.main_window import PlotterApp

def _setup_logging():
    """アプリ全体のログ設定。.exe化するとコンソールが見えないため、ファイルにも出力する。"""
    log_path = os.path.join(os.path.abspath("."), "graphica.log")
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
    app = QApplication(sys.argv)
    
    # メインウィンドウのインスタンスを作成して表示
    window = PlotterApp()
    window.show()
    
    sys.exit(app.exec())