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
