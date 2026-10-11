"""テーマカラー(利用者が選ぶ1色)から、UI の強調に使う色を計算する。Qt に依存しない。

選んだ色の色相と鮮やかさは保ち、明るさだけを動かして背景とのコントラスト比(WCAG 2)を確保する。
ライトでは暗く、ダークでは明るくする。設定には選んだ色だけを保存し、この計算は毎回行う。
"""
import colorsys
import math
import re

DEFAULT_THEME_COLOR = "#0F4C5C"  # アプリアイコンの背景色

THEME_COLOR_PRESETS = (
    ("アイコン", "#0F4C5C"),
    ("ティール", "#1F7A80"),
    ("インディゴ", "#4F46E5"),
    ("ブルー", "#2563EB"),
    ("パープル", "#7C3AED"),
    ("ローズ", "#E11D48"),
    ("オレンジ", "#F97316"),
    ("イエロー", "#FACC15"),
)

# 強調の色と、強調の色で書く文字に求めるコントラスト比
ACCENT_MIN_CONTRAST = 4.5
LIGHT_TEXT_MIN_CONTRAST = 4.5
DARK_TEXT_MIN_CONTRAST = 7.0
# 塗りの上の文字の候補。白と、ほぼ黒
ON_ACCENT_LIGHT = "#FFFFFF"
ON_ACCENT_DARK = "#0C0E11"
ACCENT_SOFT_ALPHA_LIGHT = 0.12
ACCENT_SOFT_ALPHA_DARK = 0.18

_LIGHTNESS_STEP = 0.01
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def normalize_hex(color: str) -> str:
    """'#rrggbb' の大文字にそろえる。形が違えば ValueError。"""
    match = _HEX_RE.match(color.strip()) if isinstance(color, str) else None
    if not match:
        raise ValueError(f"テーマカラーは #RRGGBB の形で指定する: {color!r}")
    return "#" + match.group(1).upper()


def theme_color_or_default(value) -> str:
    """設定から読んだ値。壊れていたら既定の色にする(設定ファイルの傷で起動できなくならないように)。"""
    try:
        return normalize_hex(value)
    except ValueError:
        return DEFAULT_THEME_COLOR


def _to_rgb(hex_color: str) -> tuple:
    value = normalize_hex(hex_color)[1:]
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _round_half_up(value: float) -> int:
    # 見本(JavaScript の Math.round)と同じ丸め。Python の round() は偶数への丸めで、端で1ずれる
    return int(math.floor(value + 0.5))


def _to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, _round_half_up(v))):02X}" for v in rgb)


def relative_luminance(rgb) -> float:
    def channel(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(rgb_a, rgb_b) -> float:
    a, b = relative_luminance(rgb_a), relative_luminance(rgb_b)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _until_contrast(rgb, background, target, direction):
    """明るさだけを少しずつ動かし、background との比が target に届いた色(丸めた RGB)を返す。"""
    h, lightness, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    current = tuple(int(v) for v in rgb)
    # 判定は丸めた後の色で行う(丸める前に届いていても、丸めで比が 4.4956 のように割ることがある)
    for _ in range(100):
        if contrast_ratio(current, background) >= target:
            break
        lightness = max(0.0, min(1.0, lightness + direction * _LIGHTNESS_STEP))
        current = tuple(_round_half_up(v * 255) for v in colorsys.hls_to_rgb(h, lightness, s))
    return current


def derive_accent(theme_color: str, background: str, dark: bool) -> dict:
    """選んだ色と、その色を置く背景(パネルの面)から、強調の4色を作る。

    Returns:
        accent(塗り・枠)、accent_fg(強調の色で書く文字)、on_accent(塗りの上の文字)、
        accent_soft(選択の背景。QSS の rgba(...))、adjusted(accent が選んだ色から変わったか)。
    """
    chosen = normalize_hex(theme_color)
    bg = _to_rgb(background)
    direction = 1 if dark else -1
    accent = _until_contrast(_to_rgb(chosen), bg, ACCENT_MIN_CONTRAST, direction)
    text_target = DARK_TEXT_MIN_CONTRAST if dark else LIGHT_TEXT_MIN_CONTRAST
    accent_fg = _until_contrast(accent, bg, text_target, direction)
    on_light, on_dark = _to_rgb(ON_ACCENT_LIGHT), _to_rgb(ON_ACCENT_DARK)
    on_accent = (ON_ACCENT_LIGHT if contrast_ratio(accent, on_light) >= contrast_ratio(accent, on_dark)
                 else ON_ACCENT_DARK)
    alpha = ACCENT_SOFT_ALPHA_DARK if dark else ACCENT_SOFT_ALPHA_LIGHT
    accent_hex = _to_hex(accent)
    return {
        "accent": accent_hex,
        "accent_fg": _to_hex(accent_fg),
        "on_accent": on_accent,
        "accent_soft": f"rgba({accent[0]}, {accent[1]}, {accent[2]}, {alpha})",
        "adjusted": accent_hex != chosen,
    }
