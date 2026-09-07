# tests/test_color_palettes.py
"""core/color_palettes.py(項目141、C-804: 論文向けカラーパレットマネージャー)のテスト。"""
import re

from core.color_palettes import BUILTIN_PALETTES

_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


def test_builtin_palettes_is_non_empty():
    assert len(BUILTIN_PALETTES) >= 1


def test_builtin_palettes_names_do_not_collide_with_default():
    assert "Matplotlib既定" not in BUILTIN_PALETTES


def test_every_builtin_palette_has_at_least_two_valid_hex_colors():
    for name, colors in BUILTIN_PALETTES.items():
        assert len(colors) >= 2, f"{name} has too few colors"
        for color in colors:
            assert _HEX_COLOR_RE.match(color), f"{name} has an invalid color: {color}"


def test_every_builtin_palette_has_no_duplicate_colors():
    for name, colors in BUILTIN_PALETTES.items():
        assert len(colors) == len(set(colors)), f"{name} has duplicate colors"


def test_includes_okabe_ito_cud_safe_palette():
    """項目140(C-803): 色覚多様性対応(CUD)パレットが組み込みで選べること。"""
    matching = [name for name in BUILTIN_PALETTES if "Okabe-Ito" in name]
    assert len(matching) == 1
    assert len(BUILTIN_PALETTES[matching[0]]) == 8
