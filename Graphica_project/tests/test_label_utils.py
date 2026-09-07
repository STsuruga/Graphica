# tests/test_label_utils.py
"""core/label_utils.py (項目127、C-608: 列の単位メタデータ→軸ラベル自動生成) のテスト。"""
from core.label_utils import infer_axis_label_from_column_name


def test_infers_label_from_parentheses_format():
    assert infer_axis_label_from_column_name("X (nm)") == "X (nm)"


def test_infers_label_and_normalizes_brackets_to_parentheses():
    assert infer_axis_label_from_column_name("Wavelength [nm]") == "Wavelength (nm)"


def test_infers_label_with_no_space_before_bracket():
    assert infer_axis_label_from_column_name("T(K)") == "T (K)"


def test_returns_none_for_plain_column_name_without_unit():
    assert infer_axis_label_from_column_name("x") is None
    assert infer_axis_label_from_column_name("column1") is None


def test_returns_none_for_empty_parentheses():
    assert infer_axis_label_from_column_name("X ()") is None


def test_returns_none_for_non_string_input():
    assert infer_axis_label_from_column_name(None) is None
    assert infer_axis_label_from_column_name(42) is None


def test_strips_surrounding_whitespace():
    assert infer_axis_label_from_column_name("  Intensity (a.u.)  ") == "Intensity (a.u.)"
