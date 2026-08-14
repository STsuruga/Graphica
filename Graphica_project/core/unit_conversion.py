# core/unit_conversion.py
"""X軸の単位変換(項目C-602: 単位変換の第2X軸 nm<->eV<->cm^-1<->Hz)。

波長(nm)以外の3単位(eV/cm^-1/Hz)は、いずれも波長に反比例する量
(value = 定数 / wavelength_nm)であるため、任意の単位ペア間の変換は
「波長(nm)を経由する」ことで統一的に扱える。
"""
import numpy as np

X_AXIS_UNIT_NONE = 'none'
X_AXIS_UNIT_NM = 'nm'
X_AXIS_UNIT_EV = 'eV'
X_AXIS_UNIT_CM1 = 'cm-1'
X_AXIS_UNIT_HZ = 'Hz'

X_AXIS_UNIT_CHOICES = [X_AXIS_UNIT_NONE, X_AXIS_UNIT_NM, X_AXIS_UNIT_EV, X_AXIS_UNIT_CM1, X_AXIS_UNIT_HZ]

X_AXIS_UNIT_LABELS = {
    X_AXIS_UNIT_NONE: 'なし',
    X_AXIS_UNIT_NM: 'nm(波長)',
    X_AXIS_UNIT_EV: 'eV(エネルギー)',
    X_AXIS_UNIT_CM1: 'cm⁻¹(波数)',
    X_AXIS_UNIT_HZ: 'Hz(周波数)',
}

# hc [eV*nm] (CODATA近似)
_EV_NM_CONSTANT = 1239.8419843320025
# 1cm を nm に換算した値(cm^-1 <-> nm の変換定数)
_WAVENUMBER_NM_CONSTANT = 1.0e7
# 光速 [m/s] * 1e9 (Hz <-> nm の変換定数)
_FREQUENCY_NM_CONSTANT = 2.99792458e17

_UNIT_TO_NM_CONSTANT = {
    X_AXIS_UNIT_EV: _EV_NM_CONSTANT,
    X_AXIS_UNIT_CM1: _WAVENUMBER_NM_CONSTANT,
    X_AXIS_UNIT_HZ: _FREQUENCY_NM_CONSTANT,
}


def convert_x_axis_unit(value, from_unit, to_unit):
    """valueをfrom_unitからto_unitへ変換する(nm/eV/cm-1/Hzのみ対応)。

    from_unit == to_unit の場合はそのまま返す。0除算(波長0nm相当)は
    物理的に無意味な入力のため例外にはせず、numpyのinf/nanへフォールバックする
    (ax.secondary_xaxis()に渡すforward/inverse関数として使う都合上、
    警告で埋もれないようdivide/invalidの実行時警告は抑制する)。
    """
    value = np.asarray(value, dtype=float)
    if from_unit == to_unit:
        return value

    with np.errstate(divide='ignore', invalid='ignore'):
        if from_unit == X_AXIS_UNIT_NM:
            wavelength_nm = value
        else:
            wavelength_nm = _UNIT_TO_NM_CONSTANT[from_unit] / value

        if to_unit == X_AXIS_UNIT_NM:
            return wavelength_nm
        return _UNIT_TO_NM_CONSTANT[to_unit] / wavelength_nm
