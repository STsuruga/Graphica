# tests/test_safe_eval.py
"""core/safe_eval.py (C-008: eval/exec排除) のテスト。"""
import numpy as np
import pandas as pd
import pytest

from core.safe_eval import SafeEvalError, safe_eval_column_formula, safe_eval_formula


# --- safe_eval_formula (カーブフィット用: 属性アクセス一切不可) ---

def test_safe_eval_formula_basic_arithmetic():
    assert safe_eval_formula("a + b * 2", {'a': 1.0, 'b': 2.0}) == 5.0


def test_safe_eval_formula_operator_precedence_and_power():
    assert safe_eval_formula("2 + 3 * 4 ** 2", {}) == 50.0


def test_safe_eval_formula_unary_minus():
    assert safe_eval_formula("-a", {'a': 3.0}) == -3.0


def test_safe_eval_formula_uses_default_math_functions():
    x = np.array([0.0, 1.0])
    result = safe_eval_formula("a*exp(-b*x)+c", {'x': x, 'a': 1.0, 'b': 1.0, 'c': 0.0})
    np.testing.assert_allclose(result, 1.0 * np.exp(-1.0 * x))


def test_safe_eval_formula_rejects_unknown_name():
    with pytest.raises(SafeEvalError, match="未定義"):
        safe_eval_formula("a + unknown_name", {'a': 1.0})


def test_safe_eval_formula_rejects_attribute_access():
    """カーブフィット用の評価器は属性アクセス自体を一切許可しない。"""
    with pytest.raises(SafeEvalError, match="属性アクセス"):
        safe_eval_formula("a.bit_length()", {'a': 3})


def test_safe_eval_formula_rejects_dunder_via_attribute():
    with pytest.raises(SafeEvalError):
        safe_eval_formula("a + __import__('os').getcwd().__len__()", {'a': 1.0, '__import__': 1.0})


def test_safe_eval_formula_rejects_lambda():
    with pytest.raises(SafeEvalError):
        safe_eval_formula("(lambda: 1)()", {})


def test_safe_eval_formula_rejects_list_comprehension():
    with pytest.raises(SafeEvalError):
        safe_eval_formula("[x for x in (1,2,3)]", {})


def test_safe_eval_formula_rejects_subscript():
    with pytest.raises(SafeEvalError):
        safe_eval_formula("a[0]", {'a': [1, 2, 3]})


def test_safe_eval_formula_rejects_syntax_error():
    with pytest.raises(SafeEvalError, match="構文"):
        safe_eval_formula("a +", {'a': 1.0})


def test_safe_eval_formula_rejects_string_constant():
    with pytest.raises(SafeEvalError):
        safe_eval_formula("'os'", {})


def test_safe_eval_formula_rejects_double_star_kwargs_expansion():
    """
    回帰テスト: `func(**expr)` のようなキーワード引数展開は、以前は
    kw.arg(Noneになる)をそのまま辞書キーとして使ってしまい、その後の
    関数呼び出しで未捕捉のTypeError("keywords must be strings")が
    そのまま漏れ出ていた。安全な構文だけを許可するのがこのモジュールの
    役目のため、明示的にSafeEvalErrorとして拒否されることを確認する。
    """
    with pytest.raises(SafeEvalError):
        safe_eval_formula("exp(**kw)", {'kw': {'x': 0.0}})


def test_safe_eval_formula_rejects_unwhitelisted_function():
    with pytest.raises(SafeEvalError, match="許可されていない関数"):
        safe_eval_formula("open(1)", {})


def test_safe_eval_error_is_value_error():
    assert issubclass(SafeEvalError, ValueError)


# --- safe_eval_column_formula (列計算用: 許可メソッドのみ属性アクセス可) ---

def _df():
    return pd.DataFrame({'A': [1.0, 2.0, 3.0, 4.0, 5.0], 'B': [10.0, 20.0, 30.0, 40.0, 50.0]})


def test_safe_eval_column_formula_basic_arithmetic():
    result = safe_eval_column_formula(_df(), "A + B * 2")
    pd.testing.assert_series_equal(result, _df()['A'] + _df()['B'] * 2, check_names=False)


def test_safe_eval_column_formula_math_function():
    result = safe_eval_column_formula(_df(), "log(A)")
    np.testing.assert_allclose(result.to_numpy(), np.log(_df()['A'].to_numpy()))


def test_safe_eval_column_formula_allows_whitelisted_method():
    result = safe_eval_column_formula(_df(), "A.cumsum()")
    pd.testing.assert_series_equal(result, _df()['A'].cumsum(), check_names=False)


def test_safe_eval_column_formula_allows_chained_rolling_mean():
    result = safe_eval_column_formula(_df(), "A.rolling(2).mean()")
    pd.testing.assert_series_equal(result, _df()['A'].rolling(2).mean(), check_names=False)


def test_safe_eval_column_formula_allows_normalize_preset_pattern():
    df = _df()
    result = safe_eval_column_formula(df, "(A - A.mean()) / A.std()")
    expected = (df['A'] - df['A'].mean()) / df['A'].std()
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_safe_eval_column_formula_rejects_io_method():
    with pytest.raises(SafeEvalError, match="許可されていない"):
        safe_eval_column_formula(_df(), "A.to_csv('out.csv')")


def test_safe_eval_column_formula_rejects_dunder_attribute():
    with pytest.raises(SafeEvalError):
        safe_eval_column_formula(_df(), "A.__class__")


def test_safe_eval_column_formula_rejects_unknown_column():
    with pytest.raises(SafeEvalError, match="未定義"):
        safe_eval_column_formula(_df(), "C + 1")


def test_safe_eval_column_formula_rejects_apply_with_arbitrary_callable():
    with pytest.raises(SafeEvalError):
        safe_eval_column_formula(_df(), "A.apply(abs)")


# --- 比較・論理演算子(CalcHelpDialogが実際にユーザーへ案内している構文) ---

def test_safe_eval_column_formula_comparison_operator():
    result = safe_eval_column_formula(_df(), "A > 2")
    assert list(result) == [False, False, True, True, True]


def test_safe_eval_column_formula_equality_between_columns():
    df = pd.DataFrame({'A': [1.0, 2.0, 3.0], 'B': [1.0, 5.0, 3.0]})
    result = safe_eval_column_formula(df, "A == B")
    assert list(result) == [True, False, True]


def test_safe_eval_column_formula_and_or_not_match_help_dialog_examples():
    df = pd.DataFrame({'A': [1.0, 6.0, 6.0, -1.0], 'B': [1.0, 1.0, 5.0, 1.0]})
    and_result = safe_eval_column_formula(df, "A > 5 and B < 3")
    assert list(and_result) == [False, True, False, False]

    or_result = safe_eval_column_formula(df, "A < 0 or A > 10")
    assert list(or_result) == [False, False, False, True]

    not_result = safe_eval_column_formula(df, "not (A > 5)")
    assert list(not_result) == [True, False, False, True]


def test_safe_eval_formula_supports_comparison_too():
    """カーブフィット用の評価器でも比較演算子自体は禁止しない(属性アクセスのみ禁止)。"""
    assert safe_eval_formula("a > 1", {'a': 2.0}) is True
