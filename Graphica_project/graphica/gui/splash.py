"""起動画面。重いライブラリ(pandas・scipy・matplotlib)を読む前に出すので、ここでは PySide6 と軽いモジュールだけを使う。"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from graphica.core.i18n import tr
from graphica.core.version import APP_NAME, __version__
from graphica.gui.resources import resource_path
from graphica.gui.theme import DARK_TOKENS, LIGHT_TOKENS

SPLASH_WIDTH = 440
SPLASH_HEIGHT = 220
_ICON_SIZE = 88
_CORNER_RADIUS = 14


def _render_background(dark, device_pixel_ratio):
    colors = DARK_TOKENS if dark else LIGHT_TOKENS
    pixmap = QPixmap(int(SPLASH_WIDTH * device_pixel_ratio), int(SPLASH_HEIGHT * device_pixel_ratio))
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    outline = QPainterPath()
    outline.addRoundedRect(QRectF(0.5, 0.5, SPLASH_WIDTH - 1, SPLASH_HEIGHT - 1), _CORNER_RADIUS, _CORNER_RADIUS)
    painter.fillPath(outline, QColor(colors["surface"]))
    painter.setPen(QColor(colors["border"]))
    painter.drawPath(outline)

    icon_top = 40
    icon = QIcon(resource_path("Graphica.ico")).pixmap(_ICON_SIZE, _ICON_SIZE)
    painter.drawPixmap(32, icon_top, _ICON_SIZE, _ICON_SIZE, icon)

    text_left = 32 + _ICON_SIZE + 24
    name_font = QFont()
    name_font.setPointSize(22)
    name_font.setBold(True)
    painter.setFont(name_font)
    painter.setPen(QColor(colors["text_primary"]))
    painter.drawText(QRectF(text_left, icon_top + 8, SPLASH_WIDTH - text_left - 24, 40),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, APP_NAME)

    version_font = QFont()
    version_font.setPointSize(10)
    painter.setFont(version_font)
    painter.setPen(QColor(colors["text_secondary"]))
    painter.drawText(QRectF(text_left, icon_top + 50, SPLASH_WIDTH - text_left - 24, 24),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     tr("バージョン {version}").format(version=__version__))
    painter.end()
    return pixmap


class StartupSplash(QSplashScreen):
    """アイコン・名前・版と、下に今の段階の文字を出す。最初のウィンドウを出したら finish() で閉じる。"""

    def __init__(self, dark=False):
        app = QApplication.instance()
        ratio = app.devicePixelRatio() if app is not None else 1.0
        super().__init__(_render_background(dark, ratio))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._text_color = QColor((DARK_TOKENS if dark else LIGHT_TOKENS)["text_secondary"])

    def drawContents(self, painter):
        # 既定は端から 5px で文字が枠に近すぎるので、下に余白を取る
        painter.setPen(self._text_color)
        painter.drawText(self.rect().adjusted(24, 0, -24, -22),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, self.message())

    def show_progress(self, text):
        """文字を出して、すぐに描かせる(このあと重い処理でイベントループが止まるので)。"""
        self.showMessage(text, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, self._text_color)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()


def show_startup_splash(dark=False):
    splash = StartupSplash(dark)
    splash.show()
    splash.show_progress(tr("起動しています…"))
    return splash
