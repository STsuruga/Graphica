"""Tabler Icons(MIT)の SVG を QIcon にする。stroke="currentColor" を色に置き換えて描く。"""
import os
from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

from graphica.gui.resources import resource_path

ICONS_DIR = os.path.join("assets", "icons")


def icon(name, color=None, size=16):
    """assets/icons/{name}.svg。color を省くとテーマの text_secondary(呼ぶたびに決まる)。"""
    if color is None:
        from graphica.gui import theme
        color = theme.current_tokens()["text_secondary"]
    # exe では同梱のアイコンが sys._MEIPASS の下にあるので、このファイルの場所ではなく resource_path() で探す
    svg_path = resource_path(os.path.join(ICONS_DIR, f"{name}.svg"))
    return load_svg_icon(svg_path, color=color, size=size)


@lru_cache(maxsize=None)
def _load_svg_text(svg_path):
    with open(svg_path, "r", encoding="utf-8") as f:
        return f.read()


def load_svg_icon(svg_path, color="#4B5157", size=24):
    """ファイルが無ければ空の QIcon(アイコンが無くてもアプリを落とさない)。"""
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
