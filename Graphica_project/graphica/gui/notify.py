"""利用者へのメッセージと問い合わせ(ファイル・文字の入力)の窓口。

Qt の静的メソッドを同じ引数でそのまま呼ぶだけで、文言・題・ボタン・既定のボタン・親・戻り値は呼ぶ側が決める。
呼ぶときにクラスの属性を引くので、テストは QMessageBox などのクラスの属性を差し替えれば、どの画面の通知も記録できる。
crash_handler は例外処理の最中に動くので、ここを通さない(import の順と初期化の失敗を避ける)。
"""
from typing import Any

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox


def information(*args: Any, **kwargs: Any) -> Any:
    return QMessageBox.information(*args, **kwargs)


def warning(*args: Any, **kwargs: Any) -> Any:
    return QMessageBox.warning(*args, **kwargs)


def critical(*args: Any, **kwargs: Any) -> Any:
    return QMessageBox.critical(*args, **kwargs)


def question(*args: Any, **kwargs: Any) -> Any:
    return QMessageBox.question(*args, **kwargs)


def about(*args: Any, **kwargs: Any) -> Any:
    return QMessageBox.about(*args, **kwargs)


def get_open_file_name(*args: Any, **kwargs: Any) -> Any:
    return QFileDialog.getOpenFileName(*args, **kwargs)


def get_open_file_names(*args: Any, **kwargs: Any) -> Any:
    return QFileDialog.getOpenFileNames(*args, **kwargs)


def get_save_file_name(*args: Any, **kwargs: Any) -> Any:
    return QFileDialog.getSaveFileName(*args, **kwargs)


def get_existing_directory(*args: Any, **kwargs: Any) -> Any:
    return QFileDialog.getExistingDirectory(*args, **kwargs)


def get_text(*args: Any, **kwargs: Any) -> Any:
    return QInputDialog.getText(*args, **kwargs)


def get_int(*args: Any, **kwargs: Any) -> Any:
    return QInputDialog.getInt(*args, **kwargs)


def get_double(*args: Any, **kwargs: Any) -> Any:
    return QInputDialog.getDouble(*args, **kwargs)


def get_item(*args: Any, **kwargs: Any) -> Any:
    return QInputDialog.getItem(*args, **kwargs)
