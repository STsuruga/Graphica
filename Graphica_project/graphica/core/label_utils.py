"""列名から軸ラベルを推測する。"""
import re

# 「ラベル (単位)」か「ラベル [単位]」。出力は丸括弧にそろえる
_LABEL_WITH_UNIT_PATTERN = re.compile(r'^(?P<label>.+?)\s*[\(\[](?P<unit>[^()\[\]]+)[\)\]]\s*$')


def infer_axis_label_from_column_name(column_name):
    """列名が「ラベル (単位)」の形ならそのラベルを返す('Wavelength[nm]' -> 'Wavelength (nm)')。

    形が合わなければ None(単位の無い列名にラベルをでっちあげない)。
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
