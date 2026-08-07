import sys
import os
import logging

# ★ DPI認識モードはQt6が内部で自動的にPer-Monitor-V2として設定するため、
#   ここでWin32 APIのSetProcessDpiAwareness()を明示的に呼んではいけない。
#   1プロセスにつきDPI認識モードは1回しか設定できず、先にこちらで設定すると
#   Qt自身の(より新しく正しい)SetProcessDpiAwarenessContext()呼び出しが
#   アクセス拒否で失敗し、Qtの座標計算がV1相当の意図しないモードのまま動作して
#   しまう。これが描画位置とクリック判定位置がずれる不具合の原因だった。

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QGuiApplication

# 複数プロジェクトタブ(項目40)に対応した最上位ウィンドウ。
# 内部で PlotterApp を各タブとして生成する。
from gui.main_app_window import MainAppWindow
from gui.crash_handler import install_crash_handler, prompt_safe_mode_and_apply
from gui.theme import disable_scroll_value_change
from core.version import LOG_FILE_NAME
from core.app_paths import get_app_data_dir
from core.plugin_api import set_safe_mode

# アプリ全体のUIフォント。既定の "MS Shell Dlg 2"(素朴な見た目)ではなく、
# Windows 10/11 の設定アプリ等でも使われている「Yu Gothic UI」を明示的に使う。
# フォントが存在しない環境でも Qt が自動的にフォールバックするよう、
# 優先順にリストで指定する(GUI洗練)。
APP_FONT_FAMILIES = ["Yu Gothic UI", "Meiryo UI", "Segoe UI"]
APP_FONT_POINT_SIZE = 9.5

def _setup_logging():
    """
    アプリ全体のログ設定。.exe化するとコンソールが見えないため、ファイルにも出力する。
    出力先は %LOCALAPPDATA%\\Graphica (get_app_data_dir()) に固定する。
    カレントディレクトリ相対だと、Program Files 配下にインストールされた
    exeでは書き込み権限エラーになりうるため。
    """
    log_path = os.path.join(get_app_data_dir(), LOG_FILE_NAME)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

def _safe_mode_flag_requested(argv):
    """
    起動オプション --safe-mode が指定されているかどうかを返す(項目F-4)。
    main() 本体から切り出したのは、QApplication/ウィンドウを実際に構築せずに
    単体でテストできるようにするため(main.py はこれまでテストが無かった)。
    """
    return "--safe-mode" in argv


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

    # セーフモード起動(項目F-4)。プラグインの読み込みは最初のタブの
    # PlotterApp.__init__ の中で(load_plugins_once()経由で)行われるため、
    # MainAppWindow() を構築するより前に確定させておく必要がある。
    if _safe_mode_flag_requested(sys.argv):
        # コマンドラインで明示的に指定された場合は、ユーザーの意図が明らかなので
        # 確認ダイアログは出さない。
        set_safe_mode(True)
    else:
        # 前回異常終了していた場合のみ、プラグインを無効にして起動するかを尋ねる。
        # これは読み取り専用の確認であり、clean_exitキー自体の書き換え
        # (次回起動時の判定用リセット/復元)は引き続きPlotterApp側の
        # 既存ロジックのみが行う。
        prompt_safe_mode_and_apply(QSettings("Graphica", "Graphica"))

    # 最上位ウィンドウ (複数プロジェクトタブを管理する) のインスタンスを作成して表示
    window = MainAppWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()