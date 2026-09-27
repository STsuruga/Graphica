"""同梱のリソースの場所。"""
import os
import sys


def resource_path(relative_path):
    """同梱のリソースの絶対パス。凍結時は sys._MEIPASS、ソースからは graphica/ を基準にする。

    カレントディレクトリは使わない(起動の仕方次第でアイコンなどが読めなくなる)。
    """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)
