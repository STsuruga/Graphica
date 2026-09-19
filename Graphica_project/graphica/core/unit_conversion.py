"""X 軸の単位の変換(nm / eV / cm^-1 / Hz)。nm 以外は波長に反比例するので、どの組も nm を経由して変換する。"""
import numpy as np
from typing import Any

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

# hc [eV·nm]
_EV_NM_CONSTANT = 1239.8419843320025
_WAVENUMBER_NM_CONSTANT = 1.0e7
# 光速 [m/s] × 1e9
_FREQUENCY_NM_CONSTANT = 2.99792458e17

_UNIT_TO_NM_CONSTANT = {
    X_AXIS_UNIT_EV: _EV_NM_CONSTANT,
    X_AXIS_UNIT_CM1: _WAVENUMBER_NM_CONSTANT,
    X_AXIS_UNIT_HZ: _FREQUENCY_NM_CONSTANT,
}


def convert_x_axis_unit(value: Any, from_unit: str, to_unit: str) -> Any:
    """from_unit から to_unit へ変換する。

    波長 0 は例外にせず inf / nan にする(secondary_xaxis の関数に使うので、ゼロ除算の警告も抑える)。
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
