# tests/test_icon_utils.py
"""gui/icon_utils.py (Tabler Icons SVGのQIcon読み込み) に対するテスト。"""
import os

from gui.icon_utils import load_svg_icon, icon, ICONS_DIR, _PROJECT_ROOT


def test_load_svg_icon_existing_file_returns_non_null_icon():
    svg_path = os.path.join(_PROJECT_ROOT, ICONS_DIR, "pointer.svg")
    result = load_svg_icon(svg_path)
    assert not result.isNull()


def test_load_svg_icon_missing_file_returns_null_icon():
    """アイコン読み込み失敗時にアプリ全体が落ちないよう、空のQIconにフォールバックする"""
    result = load_svg_icon("/does/not/exist/nowhere.svg")
    assert result.isNull()


def test_load_svg_icon_respects_requested_pixel_size():
    svg_path = os.path.join(_PROJECT_ROOT, ICONS_DIR, "pointer.svg")
    result = load_svg_icon(svg_path, size=32)
    pixmap = result.pixmap(32, 32)
    assert pixmap.width() == 32 and pixmap.height() == 32


def test_icon_helper_resolves_by_name_regardless_of_cwd(tmp_path, monkeypatch):
    """resource_path()と同じ理由(cwd非依存)で、icon()もcwdに関係なく解決できること"""
    monkeypatch.chdir(tmp_path)
    result = icon("trash")
    assert not result.isNull()


def test_icon_helper_unknown_name_returns_null_icon():
    result = icon("this-icon-does-not-exist")
    assert result.isNull()


# --- 項目H-4(アイコンセットの見直し): 色を省略した場合、現在のテーマから
#     動的に解決する(以前は固定のダークグレー'#3B3F42'で、ダークモードの
#     ボタン背景に対してほぼ同化して見えなくなっていた、実機で確認) ---

def _sample_stroke_pixel_color(pixmap):
    """
    アイコンpixmapの中央付近から、透明でない(=線が描かれている)ピクセルの
    色を1つ拾う。線画アイコンは中心が空白のことが多いため、複数箇所を
    試して最初に見つかった不透明ピクセルを返す。
    """
    image = pixmap.toImage()
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 0:
                return pixel
    return None


def test_icon_without_explicit_color_uses_light_theme_text_secondary(qapp):
    from gui import theme

    theme.apply_theme(qapp, dark=False)
    result = icon("pointer", size=24)
    color = _sample_stroke_pixel_color(result.pixmap(24, 24))
    assert color is not None
    expected = theme.LIGHT_TOKENS["text_secondary"]
    from PySide6.QtGui import QColor
    assert (color.red(), color.green(), color.blue()) == (
        QColor(expected).red(), QColor(expected).green(), QColor(expected).blue(),
    )


def test_icon_without_explicit_color_uses_dark_theme_text_secondary(qapp):
    from gui import theme
    from PySide6.QtGui import QColor

    theme.apply_theme(qapp, dark=True)
    result = icon("pointer", size=24)
    color = _sample_stroke_pixel_color(result.pixmap(24, 24))
    assert color is not None
    expected = theme.DARK_TOKENS["text_secondary"]
    assert (color.red(), color.green(), color.blue()) == (
        QColor(expected).red(), QColor(expected).green(), QColor(expected).blue(),
    )
    theme.apply_theme(qapp, dark=False)  # 他のテストに影響しないよう戻す


def test_icon_explicit_color_overrides_theme_default(qapp):
    from gui import theme
    from PySide6.QtGui import QColor

    theme.apply_theme(qapp, dark=False)
    result = icon("pointer", color="#e6194b", size=24)
    color = _sample_stroke_pixel_color(result.pixmap(24, 24))
    assert color is not None
    assert (color.red(), color.green(), color.blue()) == (
        QColor("#e6194b").red(), QColor("#e6194b").green(), QColor("#e6194b").blue(),
    )
