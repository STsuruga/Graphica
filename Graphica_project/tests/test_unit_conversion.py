# tests/test_unit_conversion.py
"""core/unit_conversion.py のX軸単位変換(項目C-602)のテスト。"""
import numpy as np
import pytest

from core.unit_conversion import (
    convert_x_axis_unit,
    X_AXIS_UNIT_NM, X_AXIS_UNIT_EV, X_AXIS_UNIT_CM1, X_AXIS_UNIT_HZ,
    X_AXIS_UNIT_CHOICES, X_AXIS_UNIT_LABELS,
)


def test_same_unit_returns_unchanged():
    result = convert_x_axis_unit([500.0, 600.0], X_AXIS_UNIT_NM, X_AXIS_UNIT_NM)
    np.testing.assert_allclose(result, [500.0, 600.0])


def test_nm_to_ev_known_value():
    # 500nm(可視光)はおよそ2.48eV
    result = convert_x_axis_unit(500.0, X_AXIS_UNIT_NM, X_AXIS_UNIT_EV)
    assert result == pytest.approx(2.4797, abs=1e-3)


def test_ev_to_nm_is_inverse_of_nm_to_ev():
    original = np.array([300.0, 500.0, 800.0])
    ev = convert_x_axis_unit(original, X_AXIS_UNIT_NM, X_AXIS_UNIT_EV)
    back_to_nm = convert_x_axis_unit(ev, X_AXIS_UNIT_EV, X_AXIS_UNIT_NM)
    np.testing.assert_allclose(back_to_nm, original, rtol=1e-9)


def test_nm_to_wavenumber_known_value():
    # 1000nm = 1e4 cm^-1
    result = convert_x_axis_unit(1000.0, X_AXIS_UNIT_NM, X_AXIS_UNIT_CM1)
    assert result == pytest.approx(1.0e4, rel=1e-9)


def test_nm_to_frequency_known_value():
    # 光速 c = 2.99792458e8 m/s、500nmでの周波数は約5.996e14 Hz
    result = convert_x_axis_unit(500.0, X_AXIS_UNIT_NM, X_AXIS_UNIT_HZ)
    assert result == pytest.approx(5.99585e14, rel=1e-4)


def test_conversion_between_two_non_nm_units_round_trips_via_nm():
    original = np.array([1.0, 2.0, 3.0])
    cm1 = convert_x_axis_unit(original, X_AXIS_UNIT_EV, X_AXIS_UNIT_CM1)
    back = convert_x_axis_unit(cm1, X_AXIS_UNIT_CM1, X_AXIS_UNIT_EV)
    np.testing.assert_allclose(back, original, rtol=1e-9)


def test_zero_input_does_not_raise_and_yields_inf_or_nan():
    """波長0nm相当の入力は物理的に無意味だが、例外にはせずinf/nanへフォールバックする
    (matplotlibのsecondary_xaxis forward/inverse関数として使われるため)。"""
    result = convert_x_axis_unit(0.0, X_AXIS_UNIT_EV, X_AXIS_UNIT_NM)
    assert np.isinf(result) or np.isnan(result)


def test_array_input_returns_array_output():
    result = convert_x_axis_unit(np.array([400.0, 500.0, 600.0]), X_AXIS_UNIT_NM, X_AXIS_UNIT_EV)
    assert isinstance(result, np.ndarray)
    assert result.shape == (3,)


def test_unit_choices_and_labels_are_consistent():
    assert set(X_AXIS_UNIT_CHOICES) == set(X_AXIS_UNIT_LABELS.keys())
