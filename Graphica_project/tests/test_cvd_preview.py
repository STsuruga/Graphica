# tests/test_cvd_preview.py
"""gui/cvd_preview.py(項目140、C-803)のQImage変換に対するテスト。"""
from PySide6.QtGui import QImage, QColor

from gui.cvd_preview import simulate_qimage


def _solid_color_image(color_hex, width=4, height=4):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color_hex))
    return image


def test_simulate_qimage_preserves_size(qapp):
    image = _solid_color_image("#ff0000", width=10, height=6)
    result = simulate_qimage(image, "protanopia")
    assert result.width() == 10
    assert result.height() == 6


def test_simulate_qimage_transforms_pixel_color(qapp):
    image = _solid_color_image("#ff0000")
    result = simulate_qimage(image, "deuteranopia")
    pixel_color = result.pixelColor(0, 0)
    # 赤一色は変換後、元の(255,0,0)から変化しているはず
    assert (pixel_color.red(), pixel_color.green(), pixel_color.blue()) != (255, 0, 0)


def test_simulate_qimage_preserves_alpha_channel(qapp):
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 0, 0, 128))
    result = simulate_qimage(image, "tritanopia")
    assert result.pixelColor(0, 0).alpha() == 128


def test_simulate_qimage_does_not_modify_original(qapp):
    image = _solid_color_image("#00ff00")
    original_pixel = image.pixelColor(0, 0)
    simulate_qimage(image, "protanopia")
    assert image.pixelColor(0, 0) == original_pixel


def test_simulate_qimage_white_stays_near_white(qapp):
    image = _solid_color_image("#ffffff")
    result = simulate_qimage(image, "protanopia")
    pixel = result.pixelColor(0, 0)
    assert pixel.red() >= 250 and pixel.green() >= 250 and pixel.blue() >= 250
