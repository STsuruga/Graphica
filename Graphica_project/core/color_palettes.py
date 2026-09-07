# core/color_palettes.py
"""
論文向けカラーパレットマネージャー(項目141、C-804)。

既存のカスタムパレット永続化(QSettings、gui/mixins/dataset_mixin.pyの
COLOR_PALETTES_SETTINGS_KEY)に相乗りする形で、ユーザーが自分で作らなくても
選べる「よく知られた」カテゴリカルパレットをいくつか組み込みで用意する。
いずれも読み取り専用(既存の「Matplotlib既定」と同じ扱い)で、名前変更・削除・
色の追加/削除の対象にはしない。
"""

# 出典: Tableau 10(Tableauの既定カテゴリカルパレット)、
# ColorBrewer(https://colorbrewer2.org/)の定性(qualitative)パレット3種
# (Set2/Dark2/Paired、いずれもパブリックドメインとして配布)。
BUILTIN_PALETTES = {
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
