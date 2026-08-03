# gui/icon_utils.py
"""
Tabler Icons (MIT license, https://github.com/tabler/tabler-icons) のSVGファイルを
QIconとして読み込むためのヘルパー(GUIモダン化第2弾、項目67・70で使用)。

配布されているSVGはいずれも stroke="currentColor" で描かれているため、Qtの
SVGレンダラーにそのまま渡すと単色(黒)にしかならない。ここでは読み込み時に
currentColor を任意の色に置換してからレンダリングすることで、1つのSVGファイルから
通常時/選択時/ダークモード用など複数のトーンのQIconを作れるようにしている。
"""
import os
from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

ICONS_DIR = os.path.join("assets", "icons")

# ★ resource_path() (gui/main_window.py) と同様、カレントディレクトリ(cwd)に
# 依存せず、このファイル自身の場所を基準にプロジェクトルートを求める。
# これにより、gui/main_window.py を経由しない他のモジュール(data_editor.py、
# dialogs.py 等)からも、cwdに関係なく確実にアイコンを読み込める。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ICON_COLOR = "#3B3F42"


def icon(name, color=DEFAULT_ICON_COLOR, size=16):
    """assets/icons/{name}.svg を統一トーンのQIconとして読み込む共通ヘルパー"""
    svg_path = os.path.join(_PROJECT_ROOT, ICONS_DIR, f"{name}.svg")
    return load_svg_icon(svg_path, color=color, size=size)


@lru_cache(maxsize=None)
def _load_svg_text(svg_path):
    with open(svg_path, "r", encoding="utf-8") as f:
        return f.read()


def load_svg_icon(svg_path, color="#4B5157", size=24):
    """
    svg_path のSVGファイル(stroke="currentColor"形式)を color で塗り替えて
    QIconとして返す。ファイルが存在しない場合は空のQIcon()を返す
    (アイコン読み込み失敗時にアプリ全体が落ちないようにするため)。
    """
    if not os.path.exists(svg_path):
        return QIcon()

    svg_text = _load_svg_text(svg_path).replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))

    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)
