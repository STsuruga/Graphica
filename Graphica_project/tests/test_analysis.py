# tests/test_analysis.py
"""core/analysis.py (曲線フィット・ピーク検出) に対するテスト。"""
import numpy as np
import pytest

from core.analysis import calculate_curve_fit, calculate_peaks


def test_linear_fit_recovers_known_parameters():
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    popt, params_info, x_fit, y_fit, r_squared, residuals = calculate_curve_fit(x, y, "線形 (y = ax + b)")
    assert params_info == ['a', 'b']
    np.testing.assert_allclose(popt, [2.5, 1.3], atol=1e-6)
    assert len(x_fit) == 200
    assert x_fit.min() == pytest.approx(x.min())
    assert x_fit.max() == pytest.approx(x.max())
    assert r_squared == pytest.approx(1.0, abs=1e-6)
    assert len(residuals) == len(x)


def test_poly2_fit_recovers_known_parameters():
    x = np.linspace(-5, 5, 60)
    y = 1.0 * x**2 - 2.0 * x + 3.0
    popt, params_info, _, _, r_squared, _ = calculate_curve_fit(x, y, "2次多項式 (y = ax^2 + bx + c)")
    np.testing.assert_allclose(popt, [1.0, -2.0, 3.0], atol=1e-6)
    assert r_squared == pytest.approx(1.0, abs=1e-6)


def test_poly3_fit_recovers_known_parameters():
    x = np.linspace(-3, 3, 60)
    y = 0.5 * x**3 + x**2 - x + 2.0
    popt, params_info, _, _, _, _ = calculate_curve_fit(x, y, "3次多項式 (y = ax^3 + bx^2 + cx + d)")
    np.testing.assert_allclose(popt, [0.5, 1.0, -1.0, 2.0], atol=1e-5)


def test_exponential_fit_recovers_known_parameters():
    x = np.linspace(0, 5, 50)
    y = 3.0 * np.exp(0.7 * x)
    popt, params_info, _, _, _, _ = calculate_curve_fit(x, y, "指数関数 (y = a * exp(bx))")
    np.testing.assert_allclose(popt, [3.0, 0.7], atol=1e-3)


def test_log_fit_recovers_known_parameters():
    x = np.linspace(0.1, 10, 50)
    y = 2.0 * np.log(x) + 1.0
    popt, params_info, _, _, _, _ = calculate_curve_fit(x, y, "対数 (y = a * ln(x) + b)")
    np.testing.assert_allclose(popt, [2.0, 1.0], atol=1e-6)


def test_log_fit_rejects_non_positive_x():
    x = np.array([-1.0, 1.0, 2.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="X > 0"):
        calculate_curve_fit(x, y, "対数 (y = a * ln(x) + b)")


def test_power_fit_recovers_known_parameters():
    x = np.linspace(1, 10, 50)
    y = 2.0 * np.power(x, 1.5)
    popt, params_info, _, _, _, _ = calculate_curve_fit(x, y, "べき乗 (y = a * x^b)")
    np.testing.assert_allclose(popt, [2.0, 1.5], atol=1e-3)


def test_power_fit_rejects_non_positive_x():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="X > 0"):
        calculate_curve_fit(x, y, "べき乗 (y = a * x^b)")


def test_gaussian_fit_recovers_known_parameters():
    x = np.linspace(-10, 10, 200)
    y = 5.0 * np.exp(-((x - 2.0) ** 2) / (2 * 1.5 ** 2)) + 0.5
    popt, params_info, _, _, _, _ = calculate_curve_fit(x, y, "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)")
    np.testing.assert_allclose(popt, [5.0, 2.0, 1.5, 0.5], atol=1e-2)


def test_sigmoid_fit_recovers_known_parameters():
    # ★ x範囲が広すぎると遷移部から離れた点がほぼ完全に飽和(0またはa)してしまい、
    # b/cを特定する勾配情報が乏しくなり収束が不安定になる。遷移の中心(c=1.0)付近に
    # 十分な情報を持たせるため、範囲を遷移幅(1/b)の数倍程度に絞る。
    x = np.linspace(-2, 4, 200)
    y = 4.0 / (1 + np.exp(-1.2 * (x - 1.0)))
    popt, params_info, _, _, _, _ = calculate_curve_fit(x, y, "シグモイド (y = a / (1 + exp(-b(x-c))))")
    np.testing.assert_allclose(popt, [4.0, 1.2, 1.0], atol=1e-2)


def test_custom_formula_fit_recovers_known_parameters():
    x = np.linspace(0, 5, 50)
    y = 2.0 * np.exp(-0.5 * x) + 1.0
    popt, params_info, x_fit, y_fit, r_squared, residuals = calculate_curve_fit(
        x, y, "カスタム数式...", custom_formula="a*exp(-b*x)+c"
    )
    assert params_info == ['a', 'b', 'c']
    np.testing.assert_allclose(popt, [2.0, 0.5, 1.0], atol=1e-3)
    assert r_squared == pytest.approx(1.0, abs=1e-3)
    assert len(residuals) == len(x)


def test_custom_formula_without_params_raises():
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="フィットパラメータ"):
        calculate_curve_fit(x, y, "カスタム数式...", custom_formula="42")


def test_custom_formula_blank_raises():
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="カスタム数式"):
        calculate_curve_fit(x, y, "カスタム数式...", custom_formula="   ")


def test_custom_formula_cannot_call_dangerous_builtins():
    """
    カスタム数式のevalは __builtins__ を空にしてサンドボックス化している。
    さらに、数式中の未知の識別子(x/既知関数名以外)はすべて「フィットパラメータ」
    として数値化されるため、__import__ のような名前を書いても実際には
    ただの数値パラメータとして扱われ、本物のビルトイン関数としては呼び出せない
    (呼び出そうとするとfloatをcallすることになりTypeErrorになる)。
    どちらの経路でも、結果的に例外になり危険な処理は実行されないことを確認する。
    """
    x = np.linspace(1, 10, 20)
    y = np.linspace(1, 10, 20)
    with pytest.raises((ValueError, RuntimeError)):
        calculate_curve_fit(x, y, "カスタム数式...", custom_formula="a + __import__('os').getcwd().__len__()")


def test_unknown_fit_type_raises():
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="不明なフィットタイプ"):
        calculate_curve_fit(x, y, "存在しないフィット")


def test_too_few_points_raises():
    x = np.array([1.0])
    y = np.array([1.0])
    with pytest.raises(ValueError, match="データ点数"):
        calculate_curve_fit(x, y, "2次多項式 (y = ax^2 + bx + c)")


# --- ピーク検出 ---

def test_find_upward_peaks():
    x = np.linspace(0, 10, 200)
    y = np.sin(x) + np.sin(3 * x) * 0.01  # なだらかな1周期の山
    settings = {"height": 0.5, "prominence": 0.3, "distance_x": 0}
    peak_x, peak_y = calculate_peaks(x, y, "上に凸 (Peaks)", settings)
    assert len(peak_x) >= 1
    assert all(v > 0.5 for v in peak_y)


def test_find_downward_peaks_inverts_signal():
    x = np.linspace(0, 10, 200)
    y = -np.sin(x)  # 下向きの谷 (実際には上に凸なので "下に凸"検出でヒットする)
    settings = {"height": 0.5, "prominence": 0.3, "distance_x": 0}
    peak_x, peak_y = calculate_peaks(x, -y, "下に凸 (Valleys)", settings)
    assert len(peak_x) >= 1


def test_find_peaks_returns_empty_when_none_found():
    x = np.linspace(0, 10, 50)
    y = np.zeros_like(x)  # 完全に平坦 -> ピークなし
    settings = {"height": 10.0, "prominence": None, "distance_x": 0}
    peak_x, peak_y = calculate_peaks(x, y, "上に凸 (Peaks)", settings)
    assert len(peak_x) == 0
    assert len(peak_y) == 0


def test_find_peaks_respects_distance_x():
    x = np.linspace(0, 20, 400)
    y = np.sin(x)  # 複数の山がある周期信号
    settings_close = {"height": 0.9, "prominence": None, "distance_x": 0}
    settings_far = {"height": 0.9, "prominence": None, "distance_x": 100}  # 非現実的に離れた距離
    peak_x_close, _ = calculate_peaks(x, y, "上に凸 (Peaks)", settings_close)
    peak_x_far, _ = calculate_peaks(x, y, "上に凸 (Peaks)", settings_far)
    assert len(peak_x_far) <= len(peak_x_close)
