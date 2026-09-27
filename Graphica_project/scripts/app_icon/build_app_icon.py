"""アプリのアイコン(graphica/Graphica.ico)を、同じフォルダの Graphica.svg から作り直す。

    python scripts/app_icon/build_app_icon.py

ico の各大きさは SVG をその大きさで描き直す(大きい画像を縮めると細い線がつぶれる)。
exe のアイコンとウィンドウのアイコンはこの ico を使い、macOS の .icns は CI がこの ico の最大の画像から作る。
"""
import io
import os
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_SVG = os.path.join(HERE, "Graphica.svg")
TARGET_ICO = os.path.join(HERE, "..", "..", "graphica", "Graphica.ico")
# 24 は Windows の表示倍率 150% の小さいアイコンで使われる
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(renderer, size):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841 QPainter に要る
    renderer = QSvgRenderer(SOURCE_SVG)
    if not renderer.isValid():
        raise SystemExit(f"SVG を読めない: {SOURCE_SVG}")
    frames = [render(renderer, size) for size in SIZES]
    largest = frames[-1]
    largest.save(os.path.normpath(TARGET_ICO), format="ICO", sizes=[(s, s) for s in SIZES],
                 append_images=frames[:-1])
    print(f"{os.path.normpath(TARGET_ICO)}: {', '.join(str(s) for s in SIZES)}")


if __name__ == "__main__":
    main()
