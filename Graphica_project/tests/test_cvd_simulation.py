# tests/test_cvd_simulation.py
"""core/cvd_simulation.py(項目140、C-803: 色覚多様性対応・CUDシミュレータ)のテスト。"""
import numpy as np
import pytest

from core.cvd_simulation import (
    CVD_MATRICES, CVD_TYPE_LABELS, simulate_rgb_array, simulate_hex_color,
)


def test_cvd_matrices_cover_all_three_types():
    assert set(CVD_MATRICES.keys()) == {'protanopia', 'deuteranopia', 'tritanopia'}


def test_cvd_matrix_rows_sum_to_one():
    """各行の合計が1でないと、白/黒/グレーの明るさが変わってしまう(意図しない変換)。"""
    for cvd_type, matrix in CVD_MATRICES.items():
        row_sums = matrix.sum(axis=1)
        assert np.allclose(row_sums, 1.0), f"{cvd_type}の行の合計が1になっていません"


def test_cvd_type_labels_match_matrix_keys():
    assert set(CVD_TYPE_LABELS.keys()) == set(CVD_MATRICES.keys())


@pytest.mark.parametrize("cvd_type", ["protanopia", "deuteranopia", "tritanopia"])
def test_simulate_rgb_array_preserves_white_and_black(cvd_type):
    white = np.array([255.0, 255.0, 255.0])
    black = np.array([0.0, 0.0, 0.0])
    assert np.allclose(simulate_rgb_array(white, cvd_type), 255.0, atol=1.0)
    assert np.allclose(simulate_rgb_array(black, cvd_type), 0.0, atol=1.0)


def test_simulate_rgb_array_handles_multidimensional_input():
    arr = np.zeros((4, 5, 3))
    arr[..., 0] = 200
    result = simulate_rgb_array(arr, "protanopia")
    assert result.shape == (4, 5, 3)


def test_simulate_hex_color_returns_valid_hex_string():
    result = simulate_hex_color("#ff0000", "protanopia")
    assert result.startswith("#")
    assert len(result) == 7
    int(result[1:], 16)  # 例外にならないこと(有効な16進数)


def test_simulate_hex_color_strips_leading_hash_if_missing():
    with_hash = simulate_hex_color("#00ff00", "deuteranopia")
    without_hash = simulate_hex_color("00ff00", "deuteranopia")
    assert with_hash == without_hash


def test_simulate_rgb_array_rejects_unknown_cvd_type():
    with pytest.raises(ValueError):
        simulate_rgb_array(np.array([1.0, 2.0, 3.0]), "unknown")


def test_simulate_hex_color_rejects_unknown_cvd_type():
    with pytest.raises(ValueError):
        simulate_hex_color("#ff0000", "unknown")
