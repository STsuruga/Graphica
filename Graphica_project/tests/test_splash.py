"""起動画面(gui/splash.py)と、起動の入口が重いライブラリを起動画面より前に読まないこと。"""
import subprocess
import sys

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from graphica.gui.splash import SPLASH_HEIGHT, SPLASH_WIDTH, StartupSplash
from graphica.gui.theme import DARK_TOKENS, LIGHT_TOKENS


def _center_color(splash):
    image = splash.pixmap().toImage()
    return QColor(image.pixel(image.width() // 2, image.height() - 8))


def test_splash_follows_dark_mode(qapp):
    light = StartupSplash(dark=False)
    dark = StartupSplash(dark=True)
    try:
        assert _center_color(light).name() == QColor(LIGHT_TOKENS["surface"]).name()
        assert _center_color(dark).name() == QColor(DARK_TOKENS["surface"]).name()
        assert light.pixmap().deviceIndependentSize().width() == SPLASH_WIDTH
        assert light.pixmap().deviceIndependentSize().height() == SPLASH_HEIGHT
    finally:
        light.deleteLater()
        dark.deleteLater()


def test_progress_text_is_shown_and_finish_closes_it(qapp):
    from PySide6.QtWidgets import QWidget

    splash = StartupSplash()
    splash.show()
    splash.show_progress("ライブラリを読み込み中…")
    assert splash.message() == "ライブラリを読み込み中…"

    window = QWidget()
    window.show()
    splash.finish(window)
    QApplication.processEvents()
    assert not splash.isVisible()
    window.close()


def test_the_entry_point_does_not_import_heavy_libraries_before_the_splash():
    """起動の入口を import しただけでは、pandas・scipy・matplotlib と画面の本体を読まない。"""
    code = ("import sys, graphica.__main__; "
            "print(','.join(m for m in ('pandas', 'scipy', 'matplotlib', 'graphica.gui.main_app_window', "
            "'graphica.core.plugin_api') if m in sys.modules))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_the_splash_module_itself_is_light():
    code = ("import sys, graphica.gui.splash; "
            "print(','.join(m for m in ('pandas', 'scipy', 'matplotlib') if m in sys.modules))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
