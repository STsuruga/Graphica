"""テーマカラーから強調の色を作る計算(gui/theme_color.py)と、それを当てる theme.py の部分。"""
import random

import pytest
from PySide6.QtGui import QColor, QPalette

from graphica.gui import theme
from graphica.gui.theme_color import (ACCENT_MIN_CONTRAST, DARK_TEXT_MIN_CONTRAST, DEFAULT_THEME_COLOR,
                                      LIGHT_TEXT_MIN_CONTRAST, THEME_COLOR_PRESETS, contrast_ratio,
                                      derive_accent, normalize_hex, theme_color_or_default)

LIGHT_SURFACE = theme.LIGHT_TOKENS["surface"]
DARK_SURFACE = theme.DARK_TOKENS["surface"]


def _rgb(hex_color):
    color = QColor(hex_color)
    return (color.red(), color.green(), color.blue())


# 見本(docs/dev/mockups/gui_redesign/final_lite_advanced.html の JavaScript)が出した色。計画書の表と同じ
@pytest.mark.parametrize("chosen, light_accent, dark_accent, dark_fg", [
    ("#0F4C5C", "#0F4C5C", "#1D91AF", "#24B5DB"),
    ("#2563EB", "#2563EB", "#4A7EEE", "#82A6F3"),
    ("#FACC15", "#8C7103", "#FACC15", "#FACC15"),
    ("#E5E7EB", "#6A758A", "#E5E7EB", "#E5E7EB"),
])
def test_derived_colors_match_the_mockup(chosen, light_accent, dark_accent, dark_fg):
    light = derive_accent(chosen, LIGHT_SURFACE, dark=False)
    dark = derive_accent(chosen, DARK_SURFACE, dark=True)
    assert light["accent"] == light_accent
    assert dark["accent"] == dark_accent
    assert dark["accent_fg"] == dark_fg


def test_the_default_is_the_icon_background_and_unchanged_in_light():
    assert DEFAULT_THEME_COLOR == "#0F4C5C"
    assert THEME_COLOR_PRESETS[0][1] == DEFAULT_THEME_COLOR
    light = derive_accent(DEFAULT_THEME_COLOR, LIGHT_SURFACE, dark=False)
    assert light["accent"] == DEFAULT_THEME_COLOR
    assert light["adjusted"] is False
    assert derive_accent(DEFAULT_THEME_COLOR, DARK_SURFACE, dark=True)["adjusted"] is True


@pytest.mark.parametrize("dark", [False, True])
def test_any_color_reaches_the_contrast_targets(dark):
    surface = DARK_SURFACE if dark else LIGHT_SURFACE
    text_target = DARK_TEXT_MIN_CONTRAST if dark else LIGHT_TEXT_MIN_CONTRAST
    rng = random.Random(20261012)
    colors = [c for _, c in THEME_COLOR_PRESETS] + ["#000000", "#FFFFFF", "#808080"]
    colors += ["#%06X" % rng.randrange(0x1000000) for _ in range(300)]
    for chosen in colors:
        derived = derive_accent(chosen, surface, dark)
        assert contrast_ratio(_rgb(derived["accent"]), _rgb(surface)) >= ACCENT_MIN_CONTRAST, chosen
        assert contrast_ratio(_rgb(derived["accent_fg"]), _rgb(surface)) >= text_target, chosen
        # 塗りの上の文字は、白と黒のうち読みやすい方
        on = _rgb(derived["on_accent"])
        other = _rgb("#0C0E11" if derived["on_accent"] == "#FFFFFF" else "#FFFFFF")
        assert contrast_ratio(_rgb(derived["accent"]), on) >= contrast_ratio(_rgb(derived["accent"]), other)


def test_only_the_lightness_moves():
    """色相は保つ(補正しても「選んだ色」の系統のまま)。"""
    for chosen in ("#FACC15", "#7C3AED", "#E11D48"):
        derived = derive_accent(chosen, LIGHT_SURFACE, dark=False)
        assert abs(QColor(derived["accent"]).hslHueF() - QColor(chosen).hslHueF()) < 0.02


def test_accent_soft_is_a_translucent_accent():
    light = derive_accent("#2563EB", LIGHT_SURFACE, dark=False)
    assert light["accent_soft"] == "rgba(37, 99, 235, 0.12)"
    dark = derive_accent("#2563EB", DARK_SURFACE, dark=True)
    r, g, b = _rgb(dark["accent"])
    assert dark["accent_soft"] == f"rgba({r}, {g}, {b}, 0.18)"


@pytest.mark.parametrize("value, expected", [
    ("#0f4c5c", "#0F4C5C"), ("0F4C5C", "#0F4C5C"), (" #abcdef ", "#ABCDEF"),
])
def test_normalize_hex(value, expected):
    assert normalize_hex(value) == expected


@pytest.mark.parametrize("value", ["", "#12345", "red", None, 0x123456, "#GGGGGG"])
def test_a_broken_setting_falls_back_to_the_default(value):
    assert theme_color_or_default(value) == DEFAULT_THEME_COLOR
    if isinstance(value, str):
        with pytest.raises(ValueError):
            normalize_hex(value)


# --- theme.py への当て方 ---

def test_default_color_reuses_the_module_tokens():
    assert theme.tokens_for(False) is theme.LIGHT_TOKENS
    assert theme.tokens_for(True, "#0f4c5c") is theme.DARK_TOKENS
    custom = theme.tokens_for(False, "#E11D48")
    assert custom is not theme.LIGHT_TOKENS
    assert custom["accent"] == derive_accent("#E11D48", LIGHT_SURFACE, dark=False)["accent"]
    # 地の色は明暗だけで決まる
    assert custom["bg"] == theme.LIGHT_TOKENS["bg"]


@pytest.fixture
def default_theme_after(qapp):
    yield qapp
    theme.apply_theme(qapp, dark=False, theme_color=DEFAULT_THEME_COLOR)


def test_apply_theme_with_a_color_changes_the_stylesheet_and_palette(default_theme_after):
    app = default_theme_after
    theme.apply_theme(app, dark=False, theme_color=DEFAULT_THEME_COLOR)
    theme.apply_theme(app, dark=False, theme_color="#E11D48")
    tokens = theme.current_tokens()
    assert theme.current_theme_color() == "#E11D48"
    assert tokens["accent"] in app.styleSheet()
    assert app.palette().color(QPalette.ColorRole.Highlight).name().upper() == tokens["accent"]


def test_switching_light_and_dark_keeps_the_chosen_color(default_theme_after):
    app = default_theme_after
    theme.apply_theme(app, dark=False, theme_color="#7C3AED")
    theme.apply_theme(app, dark=True)
    assert theme.current_theme_color() == "#7C3AED"
    assert theme.current_tokens()["accent"] == derive_accent("#7C3AED", DARK_SURFACE, dark=True)["accent"]


def test_same_mode_with_a_new_color_is_not_skipped(default_theme_after, monkeypatch):
    """省く条件に色も入っている(明暗だけだと、色を変えても当て直されない)。"""
    app = default_theme_after
    theme.apply_theme(app, dark=False, theme_color=DEFAULT_THEME_COLOR)
    calls = []
    monkeypatch.setattr(app, "setStyleSheet", lambda qss: calls.append(qss))
    theme.apply_theme(app, dark=False, theme_color=DEFAULT_THEME_COLOR)
    assert calls == []
    theme.apply_theme(app, dark=False, theme_color="#2563EB")
    assert len(calls) == 1


@pytest.mark.parametrize("dark", [False, True])
def test_palette_comes_from_the_tokens(dark):
    tokens = theme.DARK_TOKENS if dark else theme.LIGHT_TOKENS
    palette = theme.build_palette(tokens)
    expected = {"Window": "bg", "Base": "surface", "Text": "text_primary", "Highlight": "accent",
                "HighlightedText": "on_accent", "Mid": "border_strong", "PlaceholderText": "text_muted"}
    for role, key in expected.items():
        assert palette.color(getattr(QPalette.ColorRole, role)).name().upper() == tokens[key].upper(), role
