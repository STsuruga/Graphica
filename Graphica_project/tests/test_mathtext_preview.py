# tests/test_mathtext_preview.py
"""gui/mathtext_preview.py のテスト(項目H-2-4追加分)。"""
from PySide6.QtGui import QPixmap

from gui.mathtext_preview import render_mathtext_to_pixmap


def test_render_mathtext_to_pixmap_returns_nonempty_pixmap_for_plain_text():
    pixmap = render_mathtext_to_pixmap("タイトルを入力")
    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_render_mathtext_to_pixmap_returns_nonempty_pixmap_for_empty_text():
    # 空文字列でも(プレースホルダ用途で)クラッシュせず、最低限のピクセルを返す
    pixmap = render_mathtext_to_pixmap("")
    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_render_mathtext_to_pixmap_handles_valid_mathtext_syntax():
    pixmap = render_mathtext_to_pixmap(r"$\alpha$ vs time")
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_render_mathtext_to_pixmap_falls_back_to_plain_text_on_broken_mathtext_syntax():
    # $の対応が取れていない壊れたmathtext構文でも例外を投げず、
    # プレーンテキストとして描画し直してピクスマップを返す
    pixmap = render_mathtext_to_pixmap(r"$\alpha$\leftarrow$")
    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_render_mathtext_to_pixmap_wider_for_longer_text():
    short_pixmap = render_mathtext_to_pixmap("A")
    long_pixmap = render_mathtext_to_pixmap("A much longer piece of title text")
    assert long_pixmap.width() > short_pixmap.width()


def test_render_mathtext_to_pixmap_renders_japanese_without_glyph_warning(recwarn):
    render_mathtext_to_pixmap("タイトルを入力")
    glyph_warnings = [
        w for w in recwarn.list if "missing from font" in str(w.message)
    ]
    assert not glyph_warnings
