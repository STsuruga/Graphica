# core/label_utils.py
"""
列名から軸ラベルを推測するための小さなヘルパー(項目127、C-608:
列の単位メタデータ → 軸ラベル自動生成)。GUI状態を一切持たない純粋関数のみを置く。
"""
import re

# 「ラベル (単位)」/「ラベル [単位]」形式(例: 'X (nm)', 'Wavelength [nm]',
# 'T(K)')にマッチする。単位側は丸括弧・角括弧のどちらも受け付け、出力は
# 丸括弧に正規化する。
_LABEL_WITH_UNIT_PATTERN = re.compile(r'^(?P<label>.+?)\s*[\(\[](?P<unit>[^()\[\]]+)[\)\]]\s*$')


def infer_axis_label_from_column_name(column_name):
    """
    列名が「ラベル (単位)」形式に見える場合、軸ラベルとしてそのまま使える
    文字列を返す。該当しない場合はNone(数値専用の列名や単位の無い列名に
    ラベルをでっちあげてしまわないよう、パターンに一致しない限り何も返さない)。

    Args:
        column_name (str): データフレームの列名。

    Returns:
        str | None: 例 'X (nm)' -> 'X (nm)'、'Wavelength[nm]' -> 'Wavelength (nm)'、
            'x' -> None(単位が無いため)。
    """
    if not isinstance(column_name, str):
        return None
    match = _LABEL_WITH_UNIT_PATTERN.match(column_name.strip())
    if not match:
        return None
    label, unit = match.group('label').strip(), match.group('unit').strip()
    if not label or not unit:
        return None
    return f"{label} ({unit})"
