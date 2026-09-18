"""
組み込みの配色パレット(読み取り専用)と、利用者のパレットの検証。
利用者のパレットは QSettings の custom_color_palettes_json に保存する(gui/mixins/dataset_mixin.py)。
"""

from graphica.core.named_colors import normalize_color

# 出典: Tableau 10、ColorBrewer(Set2/Dark2/Paired、パブリックドメイン)、
# Okabe & Ito (2008) Color Universal Design(1型/2型色覚でも判別しやすい8色)。
BUILTIN_PALETTES = {
    'Okabe-Ito(色覚多様性対応)': [
        '#000000', '#e69f00', '#56b4e9', '#009e73',
        '#f0e442', '#0072b2', '#d55e00', '#cc79a7',
    ],
    'Tableau 10': [
        '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
        '#edc949', '#af7aa1', '#ff9da7', '#9c755f', '#bab0ab',
    ],
    'ColorBrewer Set2': [
        '#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3', '#a6d854',
        '#ffd92f', '#e5c494', '#b3b3b3',
    ],
    'ColorBrewer Dark2': [
        '#1b9e77', '#d95f02', '#7570b3', '#e7298a', '#66a61e',
        '#e6ab02', '#a6761d', '#666666',
    ],
    'ColorBrewer Paired': [
        '#a6cee3', '#1f78b4', '#b2df8a', '#33a02c', '#fb9a99',
        '#e31a1c', '#fdbf6f', '#ff7f00', '#cab2d6', '#6a3d9a',
    ],
}


def normalize_palettes(palettes):
    """利用者のパレット {名前: [色, ...]} を検証し、色を小文字の #rrggbb にしたコピーを返す。"""
    if not isinstance(palettes, dict):
        raise ValueError("パレットは {名前: [色, ...]} の形で渡してください。")
    result = {}
    for name, colors in palettes.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("パレット名が空です。")
        if name in BUILTIN_PALETTES:
            raise ValueError(f"「{name}」は組み込みのパレットと同じ名前です。")
        if not isinstance(colors, (list, tuple)):
            raise ValueError(f"パレット「{name}」の色はリストで渡してください。")
        result[name] = [normalize_color(c) for c in colors]
    return result
