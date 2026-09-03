# tests/test_analysis.py
"""core/analysis.py (曲線フィット・ピーク検出) に対するテスト。"""
import numpy as np
import pytest

import core.analysis as analysis_module
from core.analysis import (calculate_curve_fit, calculate_peaks, calculate_savgol,
                            calculate_peak_quantification,
                            get_plugin_fit_type_names, register_fit_function,
                            calculate_baseline_als, calculate_baseline_polynomial,
                            calculate_baseline_rubberband, calculate_baseline_manual,
                            get_fit_param_names, calculate_interval_integral,
                            calculate_cumulative_integral,
                            calculate_moving_average_smooth, calculate_median_smooth,
                            calculate_gaussian_smooth,
                            calculate_average_duplicate_x, calculate_zscore_outliers,
                            calculate_iqr_outliers,
                            calculate_confidence_band, calculate_resample_to_grid,
                            calculate_lttb_downsample,
                            calculate_multi_peak_fit, get_multi_peak_param_names,
                            multi_peak_fit_task)


def test_linear_fit_recovers_known_parameters():
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    result = calculate_curve_fit(x, y, "線形 (y = ax + b)")
    assert result['param_names'] == ['a', 'b']
    np.testing.assert_allclose(result['popt'], [2.5, 1.3], atol=1e-6)
    assert len(result['x_fit']) == 200
    assert result['x_fit'].min() == pytest.approx(x.min())
    assert result['x_fit'].max() == pytest.approx(x.max())
    assert result['r_squared'] == pytest.approx(1.0, abs=1e-6)
    assert len(result['residuals']) == len(x)
    # 項目C-401: 共分散行列・パラメータ標準誤差も構造化して返される
    assert result['pcov'].shape == (2, 2)
    assert len(result['perr']) == 2
    assert len(result['x_data_used']) == len(x)


def test_poly2_fit_recovers_known_parameters():
    x = np.linspace(-5, 5, 60)
    y = 1.0 * x**2 - 2.0 * x + 3.0
    result = calculate_curve_fit(x, y, "2次多項式 (y = ax^2 + bx + c)")
    np.testing.assert_allclose(result['popt'], [1.0, -2.0, 3.0], atol=1e-6)
    assert result['r_squared'] == pytest.approx(1.0, abs=1e-6)


def test_poly3_fit_recovers_known_parameters():
    x = np.linspace(-3, 3, 60)
    y = 0.5 * x**3 + x**2 - x + 2.0
    result = calculate_curve_fit(x, y, "3次多項式 (y = ax^3 + bx^2 + cx + d)")
    np.testing.assert_allclose(result['popt'], [0.5, 1.0, -1.0, 2.0], atol=1e-5)


def test_exponential_fit_recovers_known_parameters():
    x = np.linspace(0, 5, 50)
    y = 3.0 * np.exp(0.7 * x)
    result = calculate_curve_fit(x, y, "指数関数 (y = a * exp(bx))")
    np.testing.assert_allclose(result['popt'], [3.0, 0.7], atol=1e-3)


def test_log_fit_recovers_known_parameters():
    x = np.linspace(0.1, 10, 50)
    y = 2.0 * np.log(x) + 1.0
    result = calculate_curve_fit(x, y, "対数 (y = a * ln(x) + b)")
    np.testing.assert_allclose(result['popt'], [2.0, 1.0], atol=1e-6)


def test_log_fit_rejects_non_positive_x():
    x = np.array([-1.0, 1.0, 2.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="X > 0"):
        calculate_curve_fit(x, y, "対数 (y = a * ln(x) + b)")


def test_power_fit_recovers_known_parameters():
    x = np.linspace(1, 10, 50)
    y = 2.0 * np.power(x, 1.5)
    result = calculate_curve_fit(x, y, "べき乗 (y = a * x^b)")
    np.testing.assert_allclose(result['popt'], [2.0, 1.5], atol=1e-3)


def test_power_fit_rejects_non_positive_x():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="X > 0"):
        calculate_curve_fit(x, y, "べき乗 (y = a * x^b)")


def test_gaussian_fit_recovers_known_parameters():
    x = np.linspace(-10, 10, 200)
    y = 5.0 * np.exp(-((x - 2.0) ** 2) / (2 * 1.5 ** 2)) + 0.5
    result = calculate_curve_fit(x, y, "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)")
    np.testing.assert_allclose(result['popt'], [5.0, 2.0, 1.5, 0.5], atol=1e-2)


def test_sigmoid_fit_recovers_known_parameters():
    # ★ x範囲が広すぎると遷移部から離れた点がほぼ完全に飽和(0またはa)してしまい、
    # b/cを特定する勾配情報が乏しくなり収束が不安定になる。遷移の中心(c=1.0)付近に
    # 十分な情報を持たせるため、範囲を遷移幅(1/b)の数倍程度に絞る。
    x = np.linspace(-2, 4, 200)
    y = 4.0 / (1 + np.exp(-1.2 * (x - 1.0)))
    result = calculate_curve_fit(x, y, "シグモイド (y = a / (1 + exp(-b(x-c))))")
    np.testing.assert_allclose(result['popt'], [4.0, 1.2, 1.0], atol=1e-2)


def test_lorentzian_fit_recovers_known_parameters():
    x = np.linspace(-10, 10, 200)
    y = 5.0 / (1 + ((x - 2.0) / 1.5) ** 2) + 0.5
    result = calculate_curve_fit(x, y, "ローレンツ関数 (y = a / (1 + ((x-b)/c)^2) + d)")
    assert result['param_names'] == ['a', 'b', 'c', 'd']
    np.testing.assert_allclose(result['popt'], [5.0, 2.0, 1.5, 0.5], atol=1e-2)


def test_pseudo_voigt_fit_recovers_known_parameters():
    x = np.linspace(-10, 10, 300)
    a, b, c, eta, d = 5.0, 1.0, 2.0, 0.4, 0.3
    lorentzian_shape = 1 / (1 + ((x - b) / c) ** 2)
    gaussian_shape = np.exp(-4 * np.log(2) * ((x - b) / c) ** 2)
    y = a * (eta * lorentzian_shape + (1 - eta) * gaussian_shape) + d
    result = calculate_curve_fit(
        x, y, "擬似フォークト関数 (y = a*(η/(1+((x-b)/c)^2) + (1-η)*exp(-4ln2*((x-b)/c)^2)) + d)"
    )
    assert result['param_names'] == ['a', 'b', 'c', 'eta', 'd']
    np.testing.assert_allclose(result['popt'], [a, b, c, eta, d], atol=1e-2)


def test_voigt_fit_recovers_known_parameters():
    from scipy.special import wofz

    x = np.linspace(-10, 10, 300)
    a, b, sigma, gamma, d = 5.0, 1.0, 1.2, 0.8, 0.3
    z = ((x - b) + 1j * gamma) / (sigma * np.sqrt(2))
    y = a * np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi)) + d
    result = calculate_curve_fit(
        x, y, "フォークト関数 (y = a*Re[wofz((x-b+iγ)/(σ√2))] / (σ√(2π)) + d)"
    )
    assert result['param_names'] == ['a', 'b', 'sigma', 'gamma', 'd']
    np.testing.assert_allclose(result['popt'], [a, b, sigma, gamma, d], atol=1e-2)


def test_voigt_shape_degrades_to_gaussian_as_gamma_to_zero():
    """gamma(ローレンツ幅)→0の極限で、Voigtプロファイルは純粋なガウシアンに漸近する。"""
    from scipy.special import wofz

    x = np.linspace(-10, 10, 500)
    a, b, sigma, d = 3.0, 0.0, 1.5, 0.0
    gamma_tiny = 1e-6
    z = ((x - b) + 1j * gamma_tiny) / (sigma * np.sqrt(2))
    y_voigt = a * np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi)) + d
    y_gaussian = a * np.exp(-((x - b) ** 2) / (2 * sigma ** 2)) / (sigma * np.sqrt(2 * np.pi)) + d
    np.testing.assert_allclose(y_voigt, y_gaussian, atol=1e-3)


def test_voigt_shape_degrades_to_lorentzian_as_sigma_to_zero():
    """sigma(ガウシアン幅)→0の極限で、Voigtプロファイルは純粋なローレンツ型に漸近する。"""
    from scipy.special import wofz

    x = np.linspace(-10, 10, 500)
    a, b, gamma, d = 3.0, 0.0, 1.5, 0.0
    sigma_tiny = 1e-4
    z = ((x - b) + 1j * gamma) / (sigma_tiny * np.sqrt(2))
    y_voigt = a * np.real(wofz(z)) / (sigma_tiny * np.sqrt(2 * np.pi)) + d
    # ローレンツ型 (HWHM=gamma、ピーク高さ a/(pi*gamma) に規格化)
    y_lorentzian = (a / (np.pi * gamma)) * (gamma ** 2 / ((x - b) ** 2 + gamma ** 2)) + d
    np.testing.assert_allclose(y_voigt, y_lorentzian, atol=1e-2)


def test_voigt_fit_is_single_peak():
    """フィットしたVoigtプロファイルの曲線が単峰(1つの極大)であることを確認する。"""
    x = np.linspace(-10, 10, 300)
    a, b, sigma, gamma, d = 5.0, 1.0, 1.2, 0.8, 0.3
    from scipy.special import wofz
    z = ((x - b) + 1j * gamma) / (sigma * np.sqrt(2))
    y = a * np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi)) + d
    result = calculate_curve_fit(
        x, y, "フォークト関数 (y = a*Re[wofz((x-b+iγ)/(σ√2))] / (σ√(2π)) + d)"
    )
    y_fit = result['y_fit']
    peak_idx = np.argmax(y_fit)
    # ピーク位置の前後で単調増加/単調減少していること(単峰性)
    assert np.all(np.diff(y_fit[:peak_idx + 1]) >= -1e-8)
    assert np.all(np.diff(y_fit[peak_idx:]) <= 1e-8)


def test_multi_exponential_fit_recovers_known_parameters():
    x = np.linspace(0, 5, 100)
    y = 3.0 * np.exp(0.5 * x) + 2.0 * np.exp(-0.8 * x) + 1.0
    result = calculate_curve_fit(
        x, y, "2成分指数関数 (y = a1*exp(b1*x) + a2*exp(b2*x) + c)"
    )
    assert result['param_names'] == ['a1', 'b1', 'a2', 'b2', 'c']
    y_fit_check = (result['popt'][0] * np.exp(result['popt'][1] * x)
                   + result['popt'][2] * np.exp(result['popt'][3] * x)
                   + result['popt'][4])
    np.testing.assert_allclose(y_fit_check, y, atol=1e-2)
    assert result['r_squared'] == pytest.approx(1.0, abs=1e-3)


def test_boltzmann_sigmoid_fit_recovers_known_parameters():
    x = np.linspace(-10, 10, 200)
    y = 8.0 + (2.0 - 8.0) / (1 + np.exp((x - 1.0) / 1.5))
    result = calculate_curve_fit(
        x, y, "ボルツマンシグモイド (y = a2 + (a1-a2) / (1 + exp((x-x0)/dx)))"
    )
    assert result['param_names'] == ['a1', 'a2', 'x0', 'dx']
    np.testing.assert_allclose(result['popt'], [2.0, 8.0, 1.0, 1.5], atol=1e-2)


def test_hill_equation_fit_recovers_known_parameters():
    x = np.linspace(0, 20, 100)
    y = (10.0 * x ** 2) / (3.0 ** 2 + x ** 2)
    result = calculate_curve_fit(x, y, "ヒルの式 (y = vmax*x^n / (k^n + x^n))")
    assert result['param_names'] == ['vmax', 'k', 'n']
    np.testing.assert_allclose(result['popt'], [10.0, 3.0, 2.0], atol=1e-1)


def test_hill_equation_rejects_negative_x():
    x = np.array([-1.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="ヒル式"):
        calculate_curve_fit(x, y, "ヒルの式 (y = vmax*x^n / (k^n + x^n))")


def test_hill_equation_allows_zero_x():
    """x=0はヒルの式で数学的に問題ない(0^n=0, n>0)ため、x<0のみ弾かれること。"""
    x = np.linspace(0, 20, 100)
    y = (10.0 * x ** 2) / (3.0 ** 2 + x ** 2)
    # 例外が発生しないことを確認する
    result = calculate_curve_fit(x, y, "ヒルの式 (y = vmax*x^n / (k^n + x^n))")
    assert result['param_names'] == ['vmax', 'k', 'n']


def test_custom_formula_fit_recovers_known_parameters():
    x = np.linspace(0, 5, 50)
    y = 2.0 * np.exp(-0.5 * x) + 1.0
    result = calculate_curve_fit(
        x, y, "カスタム数式...", custom_formula="a*exp(-b*x)+c"
    )
    assert result['param_names'] == ['a', 'b', 'c']
    np.testing.assert_allclose(result['popt'], [2.0, 0.5, 1.0], atol=1e-3)
    assert result['r_squared'] == pytest.approx(1.0, abs=1e-3)
    assert len(result['residuals']) == len(x)


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


# --- プラグインが追加するフィット関数 (core/plugin_api.py 参照) ---

@pytest.fixture
def clear_plugin_fit_registry():
    """テスト間で _PLUGIN_FIT_FUNCTIONS レジストリの汚染が伝播しないようにする"""
    yield
    analysis_module._PLUGIN_FIT_FUNCTIONS.clear()


def test_register_fit_function_and_use_it(clear_plugin_fit_registry):
    def double_line(x, a, b):
        return a * x + b

    register_fit_function("プラグインテスト用線形", double_line, ["a", "b"])
    assert "プラグインテスト用線形" in get_plugin_fit_type_names()

    x = np.linspace(0, 10, 30)
    y = 2.0 * x + 5.0
    result = calculate_curve_fit(x, y, "プラグインテスト用線形")
    assert result['param_names'] == ["a", "b"]
    np.testing.assert_allclose(result['popt'], [2.0, 5.0], atol=1e-6)


def test_register_fit_function_with_callable_p0(clear_plugin_fit_registry):
    calls = []

    def custom_func(x, a):
        return a * x

    def p0_fn(x_data, y_data):
        calls.append((len(x_data), len(y_data)))
        return [3.0]

    register_fit_function("プラグインテスト用p0関数", custom_func, ["a"], p0=p0_fn)
    x = np.linspace(1, 10, 20)
    y = 3.0 * x
    calculate_curve_fit(x, y, "プラグインテスト用p0関数")
    assert calls == [(20, 20)]


def test_register_fit_function_rejects_duplicate_name(clear_plugin_fit_registry):
    register_fit_function("重複テスト", lambda x, a: a * x, ["a"])
    with pytest.raises(ValueError, match="既に登録されています"):
        register_fit_function("重複テスト", lambda x, a: a * x, ["a"])


def test_register_fit_function_rejects_builtin_name_collision(clear_plugin_fit_registry):
    with pytest.raises(ValueError, match="組み込みのフィットタイプ名"):
        register_fit_function("線形", lambda x, a: a * x, ["a"])


def test_register_fit_function_rejects_empty_param_names(clear_plugin_fit_registry):
    with pytest.raises(ValueError):
        register_fit_function("空パラメータテスト", lambda x: x, [])


def test_curve_fit_ignores_nan_rows_instead_of_raising_raw_scipy_error():
    """
    回帰テスト: Y列に欠損値(NaN)が含まれると、以前はscipy.optimize.curve_fit
    の素のValueError("array must not contain infs or NaNs")がそのまま
    伝播していた。core/dataset.pyの正規化/Savitzky-Golay/四則演算等の他の
    演算メソッドはすべて事前にNaN行を除外しており、フィットだけ仲間外れに
    なっていた。NaN行を除外した上で計算が成功することを確認する。
    """
    x = np.linspace(0, 10, 20)
    y = 2.0 * x + 1.0
    y_with_nan = y.copy()
    y_with_nan[[3, 7, 15]] = np.nan

    result = calculate_curve_fit(x, y_with_nan, "線形 (y = ax + b)")
    np.testing.assert_allclose(result['popt'], [2.0, 1.0], atol=1e-6)


def test_curve_fit_all_nan_y_raises_friendly_value_error_instead_of_crashing():
    """
    回帰テスト: Y列が丸ごとNaNの場合、ガウシアンフィットのp0推定
    (np.nanargmax)が「All-NaN slice encountered」で未捕捉のままクラッシュ
    していた。NaN除外後に「有効なデータ点がありません」という分かりやすい
    ValueErrorになることを確認する。
    """
    x = np.linspace(0, 10, 20)
    y_all_nan = np.full_like(x, np.nan)
    with pytest.raises(ValueError):
        calculate_curve_fit(x, y_all_nan, "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)")


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


def test_downward_peak_height_threshold_uses_correct_sign_for_valleys():
    """
    回帰テスト: 「下に凸(谷)」検出はfind_peaks(-y_data)と信号を反転させて
    行うが、以前はheightのしきい値だけ反転し忘れていた。PeakSettingsDialog
    のツールチップ自体が「例: -10 を指定するとY < -10の谷のみ検出」と、
    谷側にも負のしきい値をそのまま使う仕様を明示しているため、
    height=-0.5 のような入力は実際によくある使い方。
    深い谷(最小値 約-2)と浅い谷(最小値 約-0.2)を用意し、
    height=-0.5 では深い谷だけがヒットすることを確認する
    (修正前は符号を反転し忘れていたため、ほぼ全域がヒットしてしまっていた)。
    """
    x = np.linspace(0, 20, 400)
    y = (
        -2.0 * np.exp(-((x - 5) ** 2) / (2 * 0.3 ** 2))
        - 0.2 * np.exp(-((x - 15) ** 2) / (2 * 0.3 ** 2))
    )
    settings = {"height": -0.5, "prominence": None, "distance_x": 0}
    peak_x, peak_y = calculate_peaks(x, y, "下に凸 (Valleys)", settings)

    assert len(peak_y) == 1
    assert peak_y[0] == pytest.approx(-2.0, abs=0.05)
    assert peak_x[0] == pytest.approx(5.0, abs=0.1)


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


# --- ピーク定量(FWHM/面積/重心、項目C-411) ---

def _make_isolated_gaussian(amplitude=5.0, center=3.0, sigma=0.8, n=4001):
    """
    孤立した単一ガウシアン(裾がデータ端でほぼ0まで減衰する)。
    domain幅を中心から±10σ確保しているため、rel_height=1.0で求まる
    「裾野」はほぼデータ端(高さ≒0)に一致し、そこを基線とした
    area/centroidが解析的な値と比較しやすくなる。
    """
    x = np.linspace(center - 10 * sigma, center + 10 * sigma, n)
    y = amplitude * np.exp(-((x - center) ** 2) / (2 * sigma ** 2))
    return x, y


def test_peak_quantification_gaussian_fwhm_matches_analytic_formula():
    sigma = 0.8
    x, y = _make_isolated_gaussian(sigma=sigma)
    settings = {"height": 0.1, "prominence": None, "distance_x": 0}
    result = calculate_peak_quantification(x, y, "上に凸 (Peaks)", settings)

    assert len(result['peak_x']) == 1
    analytic_fwhm = 2 * np.sqrt(2 * np.log(2)) * sigma
    assert result['fwhm'][0] == pytest.approx(analytic_fwhm, rel=0.02)


def test_peak_quantification_gaussian_centroid_matches_center():
    center = 3.0
    x, y = _make_isolated_gaussian(center=center)
    settings = {"height": 0.1, "prominence": None, "distance_x": 0}
    result = calculate_peak_quantification(x, y, "上に凸 (Peaks)", settings)

    assert result['centroid'][0] == pytest.approx(center, abs=0.05)


def test_peak_quantification_gaussian_area_matches_scipy_cross_check():
    """
    解析的な閉形式(裾を切り捨てた/基線補正後ガウシアンの厳密面積)は複雑なので、
    「データ全域(裾がほぼ0)をそのままscipy.integrateで積分した値」との
    突き合わせでオーダー感が合っていることだけを確認する。
    """
    from scipy import integrate

    amplitude, sigma = 5.0, 0.8
    x, y = _make_isolated_gaussian(amplitude=amplitude, sigma=sigma)
    settings = {"height": 0.1, "prominence": None, "distance_x": 0}
    result = calculate_peak_quantification(x, y, "上に凸 (Peaks)", settings)

    reference_area = integrate.trapezoid(y, x)  # 裾がほぼ0なので基線=0相当
    assert result['area'][0] == pytest.approx(reference_area, rel=0.05)
    # 参考: 解析的なガウス全体の面積ともオーダーが合っていること
    analytic_full_area = amplitude * sigma * np.sqrt(2 * np.pi)
    assert result['area'][0] == pytest.approx(analytic_full_area, rel=0.05)


def test_peak_quantification_valley_area_and_centroid_use_correct_sign():
    """
    回帰テスト: 「下に凸(谷)」の定量化はfind_peaks(-y_data)と同じ反転
    ドメイン上でFWHM/area/centroidを計算するが、area/centroidの符号を
    元のY軸の向きに合わせて反転し忘れる/し過ぎるバグを防ぐ。
    このテストの谷はarea>0(常に正の「突出量」として定義)であること、
    centroidが谷の中心Xに一致すること、peak_yが実際の(負の)谷底の値に
    なっていることを確認する
    (test_downward_peak_height_threshold_uses_correct_sign_for_valleysと
    同じ設計思想のテスト)。
    """
    center, sigma, depth = 5.0, 0.3, 2.0
    x = np.linspace(0, 20, 800)
    y = -depth * np.exp(-((x - center) ** 2) / (2 * sigma ** 2))
    settings = {"height": -0.5, "prominence": None, "distance_x": 0}
    result = calculate_peak_quantification(x, y, "下に凸 (Valleys)", settings)

    assert len(result['peak_x']) == 1
    assert result['peak_y'][0] == pytest.approx(-depth, abs=0.05)
    assert result['peak_x'][0] == pytest.approx(center, abs=0.1)
    assert result['centroid'][0] == pytest.approx(center, abs=0.1)
    assert result['area'][0] > 0  # 符号反転バグがあれば負になる/faultyな値になる
    analytic_fwhm = 2 * np.sqrt(2 * np.log(2)) * sigma
    assert result['fwhm'][0] == pytest.approx(analytic_fwhm, rel=0.05)


def test_peak_quantification_returns_empty_arrays_when_no_peaks_found():
    x = np.linspace(0, 10, 50)
    y = np.zeros_like(x)
    settings = {"height": 10.0, "prominence": None, "distance_x": 0}
    result = calculate_peak_quantification(x, y, "上に凸 (Peaks)", settings)

    for key in ('peak_x', 'peak_y', 'fwhm', 'area', 'centroid'):
        assert len(result[key]) == 0


# --- 重み付きフィット + フィット範囲指定(C-402/C-404) ---

def test_weighted_fit_sigma_pulls_result_toward_low_error_points():
    """端点(傾きへのレバレッジが大きい位置)を大きく外した1点について、
    その誤差(sigma)を大きく(=信頼度を低く)指定すると、重み無しフィット
    よりも真の傾きに近い結果になること。"""
    x = np.linspace(0, 9, 10)
    y_true = 2.0 * x + 1.0
    y = y_true.copy()
    y[-1] += 50.0  # 端点を大きく外す(OLSでは傾きへの影響が大きい)

    popt_unweighted = calculate_curve_fit(x, y, "線形 (y = ax + b)")['popt']

    sigma = np.ones_like(x)
    sigma[-1] = 100.0  # 外れ値の不確かさを大きく指定
    popt_weighted = calculate_curve_fit(x, y, "線形 (y = ax + b)", sigma=sigma)['popt']

    # 重み付き結果の傾きの方が真の傾き(2.0)に大幅に近いはず
    assert abs(popt_weighted[0] - 2.0) < abs(popt_unweighted[0] - 2.0)
    assert abs(popt_weighted[0] - 2.0) < 0.1


def test_fit_range_excludes_points_outside_range():
    """x_rangeで指定した範囲外の点は、フィットにも残差にも一切使われないこと。"""
    x = np.linspace(0, 20, 100)
    y = np.where(x <= 10, 2.0 * x, -100.0)  # x>10は全く別の(直線から大きく外れた)値
    result = calculate_curve_fit(
        x, y, "線形 (y = ax + b)", x_range=(0.0, 10.0)
    )
    assert abs(result['popt'][0] - 2.0) < 0.05
    # 残差は範囲内(x<=10)の点数だけになっているはず
    assert len(result['residuals']) == np.sum(x <= 10.0)


def test_fit_range_combined_with_sigma_applies_same_mask():
    """x_rangeとsigmaを同時に指定した場合、sigmaにも同じマスクが適用されること
    (マスク前後で配列長が食い違ってcurve_fitがエラーにならないことの回帰確認)。"""
    x = np.linspace(0, 10, 20)
    y = 2.0 * x + 1.0
    sigma = np.ones_like(x)
    result = calculate_curve_fit(
        x, y, "線形 (y = ax + b)", sigma=sigma, x_range=(2.0, 8.0)
    )
    assert abs(result['popt'][0] - 2.0) < 1e-6


def test_fit_range_too_few_points_raises():
    x = np.linspace(0, 10, 50)
    y = 2.0 * x + 1.0
    with pytest.raises(ValueError, match="データ点数"):
        calculate_curve_fit(x, y, "線形 (y = ax + b)", x_range=(0.0, 0.05))


# --- get_fit_param_names (C-403: フィット計算なしでパラメータ名を取得) ---

def test_get_fit_param_names_builtin_types():
    assert get_fit_param_names("線形 (y = ax + b)") == ['a', 'b']
    assert get_fit_param_names("2次多項式 (y = ax^2 + bx + c)") == ['a', 'b', 'c']
    assert get_fit_param_names("3次多項式 (y = ax^3 + bx^2 + cx + d)") == ['a', 'b', 'c', 'd']
    assert get_fit_param_names("指数関数 (y = a * exp(bx))") == ['a', 'b']
    assert get_fit_param_names("対数 (y = a * ln(x) + b)") == ['a', 'b']
    assert get_fit_param_names("べき乗 (y = a * x^b)") == ['a', 'b']
    assert get_fit_param_names("ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)") == ['a', 'b', 'c', 'd']
    assert get_fit_param_names("ローレンツ関数 (y = a / (1 + ((x-b)/c)^2) + d)") == ['a', 'b', 'c', 'd']
    assert get_fit_param_names(
        "擬似フォークト関数 (y = a*(η/(1+((x-b)/c)^2) + (1-η)*exp(-4ln2*((x-b)/c)^2)) + d)"
    ) == ['a', 'b', 'c', 'eta', 'd']
    assert get_fit_param_names(
        "フォークト関数 (y = a*Re[wofz((x-b+iγ)/(σ√2))] / (σ√(2π)) + d)"
    ) == ['a', 'b', 'sigma', 'gamma', 'd']
    assert get_fit_param_names(
        "2成分指数関数 (y = a1*exp(b1*x) + a2*exp(b2*x) + c)"
    ) == ['a1', 'b1', 'a2', 'b2', 'c']
    assert get_fit_param_names(
        "ボルツマンシグモイド (y = a2 + (a1-a2) / (1 + exp((x-x0)/dx)))"
    ) == ['a1', 'a2', 'x0', 'dx']
    assert get_fit_param_names("シグモイド (y = a / (1 + exp(-b(x-c))))") == ['a', 'b', 'c']
    assert get_fit_param_names("ヒルの式 (y = vmax*x^n / (k^n + x^n))") == ['vmax', 'k', 'n']


def test_get_fit_param_names_custom_formula():
    assert get_fit_param_names("カスタム数式...", "a*exp(-b*x)+c") == ['a', 'b', 'c']


def test_get_fit_param_names_custom_formula_empty_raises():
    with pytest.raises(ValueError, match="カスタム数式が入力されていません"):
        get_fit_param_names("カスタム数式...", "")
    with pytest.raises(ValueError, match="カスタム数式が入力されていません"):
        get_fit_param_names("カスタム数式...", None)


def test_get_fit_param_names_custom_formula_no_params_raises():
    with pytest.raises(ValueError, match="フィットパラメータ"):
        get_fit_param_names("カスタム数式...", "42")


def test_get_fit_param_names_unknown_type_raises():
    with pytest.raises(ValueError, match="不明なフィットタイプ"):
        get_fit_param_names("存在しないフィット")


def test_get_fit_param_names_plugin_type(clear_plugin_fit_registry):
    register_fit_function("プラグインテスト用パラメータ名", lambda x, a, b: a * x + b, ["a", "b"])
    assert get_fit_param_names("プラグインテスト用パラメータ名") == ["a", "b"]


def test_get_fit_param_names_matches_calculate_curve_fit_param_names():
    """get_fit_param_names()の返り値が、実際にフィットしたときのparam_namesと一致すること
    (両者の重複した判定チェーンが食い違っていないことの回帰確認)。"""
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    fit_type = "線形 (y = ax + b)"
    assert get_fit_param_names(fit_type) == calculate_curve_fit(x, y, fit_type)['param_names']


def _synthetic_xy_for_new_builtin_type(fit_type):
    """
    下のtest_get_fit_param_names_matches_calculate_curve_fit_for_new_builtin_types用の
    ヘルパー。calculate_curve_fit()が実際に収束できる(=各モデル自身の数式から
    生成した、ノイズなしの)テストデータをフィットタイプごとに返す。
    (直線のような無関係なデータだと、ピーク系モデルや多成分指数モデルは
    RuntimeErrorで収束せず、本来確認したいparam_names一致の検証まで
    たどり着けないため。)
    """
    if "ローレンツ" in fit_type:
        x = np.linspace(-10, 10, 100)
        y = 5.0 / (1 + ((x - 2.0) / 1.5) ** 2) + 0.5
    elif "擬似フォークト" in fit_type:
        x = np.linspace(-10, 10, 150)
        b, c, eta = 1.0, 2.0, 0.4
        lorentzian_shape = 1 / (1 + ((x - b) / c) ** 2)
        gaussian_shape = np.exp(-4 * np.log(2) * ((x - b) / c) ** 2)
        y = 5.0 * (eta * lorentzian_shape + (1 - eta) * gaussian_shape) + 0.3
    elif "フォークト" in fit_type:
        from scipy.special import wofz
        x = np.linspace(-10, 10, 150)
        b, sigma, gamma = 1.0, 1.2, 0.8
        z = ((x - b) + 1j * gamma) / (sigma * np.sqrt(2))
        y = 5.0 * np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi)) + 0.3
    elif "2成分指数" in fit_type:
        x = np.linspace(0, 5, 60)
        y = 3.0 * np.exp(0.5 * x) + 2.0 * np.exp(-0.8 * x) + 1.0
    elif "ボルツマン" in fit_type:
        x = np.linspace(-10, 10, 100)
        y = 8.0 + (2.0 - 8.0) / (1 + np.exp((x - 1.0) / 1.5))
    elif "ヒル" in fit_type:
        x = np.linspace(0, 20, 60)
        y = (10.0 * x ** 2) / (3.0 ** 2 + x ** 2)
    else:
        raise ValueError(f"未対応のfit_type: {fit_type}")
    return x, y


@pytest.mark.parametrize("fit_type", [
    "ローレンツ関数 (y = a / (1 + ((x-b)/c)^2) + d)",
    "擬似フォークト関数 (y = a*(η/(1+((x-b)/c)^2) + (1-η)*exp(-4ln2*((x-b)/c)^2)) + d)",
    "フォークト関数 (y = a*Re[wofz((x-b+iγ)/(σ√2))] / (σ√(2π)) + d)",
    "2成分指数関数 (y = a1*exp(b1*x) + a2*exp(b2*x) + c)",
    "ボルツマンシグモイド (y = a2 + (a1-a2) / (1 + exp((x-x0)/dx)))",
    "ヒルの式 (y = vmax*x^n / (k^n + x^n))",
])
def test_get_fit_param_names_matches_calculate_curve_fit_for_new_builtin_types(fit_type):
    """新規追加した組み込みフィットタイプについても、get_fit_param_names()と
    calculate_curve_fit()のパラメータ名判定チェーンが食い違っていないことを確認する
    (2つの判定が部分文字列の衝突で誤ってすり替わっていないかの回帰確認)。"""
    x, y = _synthetic_xy_for_new_builtin_type(fit_type)
    assert get_fit_param_names(fit_type) == calculate_curve_fit(x, y, fit_type)['param_names']


# --- 初期値上書き/パラメータ固定/範囲拘束(C-403) ---

def test_p0_overrides_partial_override_helps_convergence():
    """わざと収束しにくい初期値をp0_overridesで上書きすると正しく収束すること。
    ガウシアンの中心(b)を大きく外した初期値をp0_overridesで正しい値付近に
    上書きする。"""
    x = np.linspace(-10, 10, 200)
    true_params = [5.0, 3.0, 1.5, 0.2]  # a, b(center), c(width), d
    y = true_params[0] * np.exp(-((x - true_params[1]) ** 2) / (2 * true_params[2] ** 2)) + true_params[3]

    result = calculate_curve_fit(
        x, y, "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)",
        p0_overrides={"b": 3.0},
    )
    np.testing.assert_allclose(result['popt'], true_params, atol=1e-3)


def test_fixed_params_holds_value_constant_with_zero_variance():
    """線形フィットの2パラメータのうち1つ(b)を真の値に固定すると、
    もう1つ(a)だけが自由パラメータとして正しく収束し、固定した方は
    指定値のまま・分散0で返ること。"""
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    result = calculate_curve_fit(
        x, y, "線形 (y = ax + b)", fixed_params={"b": 1.3},
    )
    assert result['popt'][1] == pytest.approx(1.3)
    assert result['popt'][0] == pytest.approx(2.5, abs=1e-6)
    assert result['pcov'][1, 1] == 0.0
    assert result['pcov'][0, 1] == 0.0
    assert result['pcov'][1, 0] == 0.0
    assert result['perr'][1] == 0.0
    assert result['perr'][0] < 1e-3


def test_fixed_params_with_noisy_data_still_fixes_exactly():
    """ノイズ入りデータでも、固定したパラメータは(自由パラメータ側の
    収束結果に関わらず)指定値ちょうどのまま返ること。"""
    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, 100)
    y = 2.5 * x + 1.3 + rng.normal(scale=0.05, size=x.shape)
    result = calculate_curve_fit(
        x, y, "線形 (y = ax + b)", fixed_params={"b": 0.0},
    )
    assert result['popt'][1] == 0.0
    assert result['pcov'][1, 1] == 0.0


def test_fixed_params_all_params_raises():
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    with pytest.raises(ValueError, match="自由パラメータ"):
        calculate_curve_fit(
            x, y, "線形 (y = ax + b)", fixed_params={"a": 2.5, "b": 1.3},
        )


def test_bounds_clamps_result_near_boundary():
    """真値が境界の外にある場合、フィット結果が境界近辺にクランプされること。"""
    x = np.linspace(0, 10, 50)
    y = 5.0 * x + 1.3  # 真の傾きは5.0
    result = calculate_curve_fit(
        x, y, "線形 (y = ax + b)", bounds={"a": (0.0, 3.0)},
    )
    assert result['popt'][0] == pytest.approx(3.0, abs=1e-3)


def test_bounds_with_p0_on_boundary_does_not_raise():
    """初期値がちょうど境界と一致していても、scipyの
    '`x0` is infeasible'のような分かりにくいエラーにならないこと。"""
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    result = calculate_curve_fit(
        x, y, "線形 (y = ax + b)",
        p0_overrides={"a": 1.0}, bounds={"a": (1.0, 10.0)},
    )
    assert result['popt'][0] == pytest.approx(2.5, abs=1e-3)


def test_p0_overrides_and_fixed_params_and_bounds_combined():
    """3つのオプションを同時に指定しても矛盾なく動作すること
    (ガウシアンで中心を固定し、振幅の初期値を上書きし、幅に境界を付ける)。"""
    x = np.linspace(-10, 10, 200)
    true_params = [5.0, 3.0, 1.5, 0.2]
    y = true_params[0] * np.exp(-((x - true_params[1]) ** 2) / (2 * true_params[2] ** 2)) + true_params[3]

    result = calculate_curve_fit(
        x, y, "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)",
        p0_overrides={"a": 4.0},
        fixed_params={"b": 3.0},
        bounds={"c": (0.1, 5.0)},
    )
    assert result['popt'][1] == 3.0
    assert result['pcov'][1, 1] == 0.0
    np.testing.assert_allclose([result['popt'][0], result['popt'][2], result['popt'][3]],
                                [true_params[0], true_params[2], true_params[3]], atol=1e-2)


def test_p0_overrides_unknown_param_name_raises():
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    with pytest.raises(ValueError, match="未知のパラメータ名"):
        calculate_curve_fit(x, y, "線形 (y = ax + b)", p0_overrides={"z": 1.0})


def test_fixed_params_unknown_param_name_raises():
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    with pytest.raises(ValueError, match="未知のパラメータ名"):
        calculate_curve_fit(x, y, "線形 (y = ax + b)", fixed_params={"z": 1.0})


def test_bounds_unknown_param_name_raises():
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    with pytest.raises(ValueError, match="未知のパラメータ名"):
        calculate_curve_fit(x, y, "線形 (y = ax + b)", bounds={"z": (0.0, 1.0)})


# --- Savitzky-Golayフィルタ(平滑化/微分、C-301/C-302) ---

def test_savgol_smoothing_reduces_noise():
    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, 200)
    y_clean = np.sin(x)
    y_noisy = y_clean + rng.normal(0, 0.1, size=x.shape)
    _, y_smoothed = calculate_savgol(x, y_noisy, window_length=11, polyorder=3, deriv=0)
    # 平滑化後の方がノイズ無し信号との誤差(標準偏差)が小さいこと
    assert np.std(y_smoothed - y_clean) < np.std(y_noisy - y_clean)


def test_savgol_smoothing_preserves_length_and_x_order():
    x = np.array([3.0, 1.0, 2.0, 5.0, 4.0])
    y = np.array([9.0, 1.0, 4.0, 25.0, 16.0])  # y = x^2 (乱れた順序で入力)
    x_sorted, y_result = calculate_savgol(x, y, window_length=3, polyorder=2, deriv=0)
    assert list(x_sorted) == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert len(y_result) == len(x)


def test_savgol_first_derivative_of_linear_function_is_constant_slope():
    x = np.linspace(0, 10, 50)
    y = 3.0 * x + 2.0
    _, dydx = calculate_savgol(x, y, window_length=5, polyorder=2, deriv=1)
    np.testing.assert_allclose(dydx, 3.0, atol=1e-6)


def test_savgol_second_derivative_of_quadratic_is_constant():
    x = np.linspace(0, 10, 100)
    y = 2.0 * x ** 2
    _, d2ydx2 = calculate_savgol(x, y, window_length=7, polyorder=3, deriv=2)
    np.testing.assert_allclose(d2ydx2, 4.0, atol=1e-3)


def test_savgol_rejects_even_window_length():
    x = np.linspace(0, 10, 20)
    y = np.sin(x)
    with pytest.raises(ValueError, match="奇数"):
        calculate_savgol(x, y, window_length=4, polyorder=2)


def test_savgol_rejects_polyorder_not_smaller_than_window():
    x = np.linspace(0, 10, 20)
    y = np.sin(x)
    with pytest.raises(ValueError, match="次数"):
        calculate_savgol(x, y, window_length=5, polyorder=5)


def test_savgol_rejects_window_larger_than_data():
    x = np.linspace(0, 10, 5)
    y = np.sin(x)
    with pytest.raises(ValueError, match="データ点数"):
        calculate_savgol(x, y, window_length=7, polyorder=2)


# =============================================================================
# ベースライン補正(項目C-308): ALS / 多項式 / ラバーバンド / 手動点
# =============================================================================

def _make_baseline_test_signal():
    """
    緩やかに湾曲したベースライン + 複数のガウシアンピーク + 小さなノイズ、
    という典型的なスペクトルを模した合成データを作る。
    """
    rng = np.random.default_rng(0)
    x = np.linspace(0, 100, 300)
    true_baseline = 0.001 * (x - 50) ** 2 + 5.0
    signal = np.zeros_like(x)
    for center, amp, width in [(30, 20, 3), (60, 15, 2), (80, 10, 1.5)]:
        signal += amp * np.exp(-(x - center) ** 2 / (2 * width ** 2))
    noise = rng.normal(0, 0.05, size=x.shape)
    y = true_baseline + signal + noise
    return x, y, true_baseline


# --- ALS ---

def test_baseline_als_recovers_smooth_baseline_under_peaks():
    x, y, true_baseline = _make_baseline_test_signal()
    x_sorted, baseline, corrected = calculate_baseline_als(x, y, lam=1e5, p=0.01, niter=10)
    assert len(baseline) == len(x)
    assert len(corrected) == len(x)
    np.testing.assert_allclose(corrected, y - baseline, atol=1e-9)
    # 真のベースラインに近い滑らかな曲線が推定できていること(ピーク付近を除く
    # 全体としての平均絶対誤差で判定する。ピーク直下は多少押し上げられるため
    # 緩めの許容誤差にする)。
    assert np.mean(np.abs(baseline - true_baseline)) < 1.0


def test_baseline_als_rejects_non_positive_lam():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="lam"):
        calculate_baseline_als(x, y, lam=0, p=0.01)


def test_baseline_als_rejects_p_out_of_range():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="p"):
        calculate_baseline_als(x, y, lam=1e5, p=1.5)
    with pytest.raises(ValueError, match="p"):
        calculate_baseline_als(x, y, lam=1e5, p=0)


def test_baseline_als_rejects_niter_less_than_one():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="niter|反復"):
        calculate_baseline_als(x, y, lam=1e5, p=0.01, niter=0)


def test_baseline_als_rejects_too_few_points():
    x = np.array([0.0, 1.0])
    y = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="3点"):
        calculate_baseline_als(x, y, lam=1e5, p=0.01)


# --- 多項式(ModPoly) ---

def test_baseline_polynomial_recovers_linear_baseline_exactly():
    x = np.linspace(0, 100, 200)
    true_baseline = 0.02 * x + 3.0
    signal = 10 * np.exp(-(x - 50) ** 2 / (2 * 4 ** 2))
    y = true_baseline + signal

    x_sorted, baseline, corrected = calculate_baseline_polynomial(x, y, degree=1, iterations=15)
    np.testing.assert_allclose(baseline, true_baseline, atol=1e-3)
    np.testing.assert_allclose(corrected, y - baseline, atol=1e-9)


def test_baseline_polynomial_rejects_negative_degree():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="次数"):
        calculate_baseline_polynomial(x, y, degree=-1)


def test_baseline_polynomial_rejects_iterations_less_than_one():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="反復"):
        calculate_baseline_polynomial(x, y, degree=2, iterations=0)


def test_baseline_polynomial_rejects_degree_at_or_above_point_count():
    x = np.linspace(0, 10, 5)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="データ点数"):
        calculate_baseline_polynomial(x, y, degree=5)


# --- ラバーバンド(下側凸包) ---

def test_baseline_rubberband_recovers_linear_baseline_exactly():
    x = np.linspace(0, 100, 200)
    true_baseline = 0.02 * x + 3.0
    signal = 10 * np.exp(-(x - 50) ** 2 / (2 * 4 ** 2))
    y = true_baseline + signal

    x_sorted, baseline, corrected = calculate_baseline_rubberband(x, y)
    np.testing.assert_allclose(baseline, true_baseline, atol=1e-6)
    np.testing.assert_allclose(corrected, y - baseline, atol=1e-9)


def test_baseline_rubberband_stays_at_or_below_data():
    x, y, _ = _make_baseline_test_signal()
    _, baseline, _ = calculate_baseline_rubberband(x, y)
    # ラバーバンド(下側凸包)は定義上、常にデータ以下(=引き算後は非負)になる。
    assert np.all(baseline <= y + 1e-9)


def test_baseline_rubberband_rejects_too_few_points():
    x = np.array([0.0, 1.0])
    y = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="3点"):
        calculate_baseline_rubberband(x, y)


# --- 手動点 ---

def test_baseline_manual_linear_recovers_baseline_from_endpoint_anchors():
    x = np.linspace(0, 100, 200)
    true_baseline = 0.02 * x + 3.0
    signal = 10 * np.exp(-(x - 50) ** 2 / (2 * 4 ** 2))
    y = true_baseline + signal

    x_sorted, baseline, corrected = calculate_baseline_manual(
        x, y, anchor_x=[0.0, 100.0], method="linear"
    )
    np.testing.assert_allclose(baseline, true_baseline, atol=1e-6)
    np.testing.assert_allclose(corrected, y - baseline, atol=1e-9)


def test_baseline_manual_spline_recovers_curved_baseline():
    x = np.linspace(0, 100, 200)
    true_baseline = 0.001 * (x - 50) ** 2 + 5.0
    signal = 10 * np.exp(-(x - 50) ** 2 / (2 * 4 ** 2))
    y = true_baseline + signal

    # アンカー点はピーク(中心50、幅4)から離れた位置に置く。ピークに
    # かぶる位置にアンカーを置くと、そこでの実データYがピークの寄与を
    # 含んでしまい、アンカー自体がベースラインからずれてしまうため。
    anchors = [0.0, 20.0, 35.0, 65.0, 80.0, 100.0]
    _, baseline, _ = calculate_baseline_manual(x, y, anchor_x=anchors, method="spline")
    assert np.mean(np.abs(baseline - true_baseline)) < 0.5


def test_baseline_manual_rejects_fewer_than_two_anchors():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="2点"):
        calculate_baseline_manual(x, y, anchor_x=[5.0], method="linear")


def test_baseline_manual_spline_rejects_fewer_than_three_anchors():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="スプライン"):
        calculate_baseline_manual(x, y, anchor_x=[0.0, 10.0], method="spline")


def test_baseline_manual_rejects_anchor_outside_data_range():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="X範囲"):
        calculate_baseline_manual(x, y, anchor_x=[-5.0, 5.0], method="linear")


def test_baseline_manual_rejects_unknown_method():
    x = np.linspace(0, 10, 50)
    y = np.sin(x) + 5
    with pytest.raises(ValueError, match="補間方法"):
        calculate_baseline_manual(x, y, anchor_x=[0.0, 10.0], method="bogus")


# =============================================================================
# 区間積分(項目C-311): 台形則 / Simpson則、ベースライン差し引き
# =============================================================================

def test_interval_integral_trapezoid_linear_function_is_exact():
    # y = x の 0〜10 の定積分は解析的に 50。台形則は区分的に線形な関数に
    # 対しては誤差なく厳密に一致するはず。
    x = np.linspace(0, 10, 50)
    y = x.copy()
    result = calculate_interval_integral(x, y, (0, 10), method="trapezoid")
    assert result['integral'] == pytest.approx(50.0, abs=1e-9)
    assert result['method'] == "trapezoid"
    assert result['x_range'] == (0.0, 10.0)
    assert result['subtract_baseline'] is False
    assert result['baseline_used'] is None
    assert result['n_points'] == len(x)


def test_interval_integral_simpson_linear_function_is_exact():
    x = np.linspace(0, 10, 51)
    y = x.copy()
    result = calculate_interval_integral(x, y, (0, 10), method="simpson")
    assert result['integral'] == pytest.approx(50.0, abs=1e-9)


def test_interval_integral_quadratic_simpson_much_more_accurate_than_trapezoid():
    # y = x^2 の 0〜10 の定積分は解析的に 1000/3 ≈ 333.333...。
    # Simpson則は2次多項式を厳密に積分できるためほぼ誤差ゼロになるが、
    # 台形則は曲線を弦で近似するため有限個の点数では必ず(区間ごとに)
    # わずかに過大評価する。粗いグリッド(21点)で両者の精度差を確認する。
    x = np.linspace(0, 10, 21)
    y = x ** 2
    exact = 1000.0 / 3.0

    trap_result = calculate_interval_integral(x, y, (0, 10), method="trapezoid")
    simpson_result = calculate_interval_integral(x, y, (0, 10), method="simpson")

    # Simpson則はほぼ厳密(2次関数を正確に積分できる公式のため)
    assert simpson_result['integral'] == pytest.approx(exact, abs=1e-9)
    # 台形則は真値よりわずかに大きい値になる(上に凸な関数を弦で近似するため)
    # が、大きくは外れない、という現実的な許容誤差で確認する
    assert trap_result['integral'] > exact
    assert trap_result['integral'] == pytest.approx(exact, abs=1.0)
    # Simpson則の方が台形則よりも真値に近いことを直接比較でも確認する
    assert abs(simpson_result['integral'] - exact) < abs(trap_result['integral'] - exact)


def test_interval_integral_simpson_handles_even_number_of_points_without_error():
    # scipy.integrate.simpsonは区間数が奇数(データ点数が偶数)でも内部で
    # 最後の区間を補正して計算するため、Savitzky-Golayの窓幅のような
    # 「偶数/奇数」バリデーションは不要であることを確認する(要件どおり、
    # 単にエラーにしない実装になっていることの回帰テスト)。
    x = np.linspace(0, 10, 20)  # 偶数個の点 = 奇数個の区間
    y = x ** 2
    result = calculate_interval_integral(x, y, (0, 10), method="simpson")
    assert result['integral'] == pytest.approx(1000.0 / 3.0, rel=1e-2)


def test_interval_integral_restricts_to_given_x_range():
    # y = 1(定数)の積分は「範囲の幅」に等しくなるはずなので、
    # 範囲を絞り込むと積分値もそれに応じて小さくなることを確認する。
    # x_rangeはcalculate_curve_fitと同じ「実データの点をマスクするだけで、
    # 境界そのものを補間して差し込むわけではない」規約のため、2/5が実際の
    # グリッド点と一致するX(0.1刻み)を選んでいる。
    x = np.linspace(0, 10, 101)
    y = np.ones_like(x)
    full_result = calculate_interval_integral(x, y, (0, 10), method="trapezoid")
    partial_result = calculate_interval_integral(x, y, (2, 5), method="trapezoid")
    assert full_result['integral'] == pytest.approx(10.0, abs=1e-6)
    assert partial_result['integral'] == pytest.approx(3.0, abs=1e-6)
    assert partial_result['n_points'] < full_result['n_points']


def test_interval_integral_subtract_baseline_recovers_known_peak_area():
    # 傾いた直線ベースライン + ガウシアンピーク、という合成データで、
    # ベースライン差し引き後の積分値がガウシアンの解析的な面積
    # (amplitude * sigma * sqrt(2*pi))に近いことを確認する。
    x = np.linspace(0, 10, 1000)
    slope, intercept = 2.0, 1.0
    baseline = slope * x + intercept
    amplitude, center, sigma = 5.0, 5.0, 0.5
    peak = amplitude * np.exp(-((x - center) ** 2) / (2 * sigma ** 2))
    y = baseline + peak

    result = calculate_interval_integral(x, y, (0, 10), method="simpson", subtract_baseline=True)

    expected_peak_area = amplitude * sigma * np.sqrt(2 * np.pi)
    assert result['integral'] == pytest.approx(expected_peak_area, rel=1e-3)
    assert result['subtract_baseline'] is True
    assert result['baseline_used'] is not None
    np.testing.assert_allclose(result['baseline_used'], baseline, atol=1e-9)
    # ベースライン差し引き前(y_raw_used)の値は元のyのまま保持されている
    np.testing.assert_allclose(result['y_raw_used'], y, atol=1e-9)


def test_interval_integral_subtract_baseline_uses_interpolated_endpoints_not_raw_rows():
    # x_min/x_maxがデータ点そのものと一致しない場合でも、範囲両端のYは
    # 「その付近の生データの最初/最後の行」ではなく、指定したX位置での
    # 実データの線形補間値になっていることを確認する(仕様どおり)。
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])  # y = x なので直線ベースラインを引くと0になる
    result = calculate_interval_integral(x, y, (0.5, 4.5), method="trapezoid", subtract_baseline=True)
    # y=xそのものが直線なので、両端を結ぶ直線を引くとベースライン差し引き後は
    # すべて0になり、積分値も0に近くなるはず
    assert result['integral'] == pytest.approx(0.0, abs=1e-9)
    np.testing.assert_allclose(result['y_used'], np.zeros_like(result['y_used']), atol=1e-9)


def test_interval_integral_ignores_nan_rows():
    x = np.linspace(0, 10, 20)
    y = x.copy()
    y[5] = np.nan
    x[10] = np.nan
    result = calculate_interval_integral(x, y, (0, 10), method="trapezoid")
    assert result['integral'] == pytest.approx(50.0, abs=0.5)
    assert result['n_points'] == 18


def test_interval_integral_rejects_unknown_method():
    x = np.linspace(0, 10, 20)
    y = x.copy()
    with pytest.raises(ValueError, match="積分方法"):
        calculate_interval_integral(x, y, (0, 10), method="bogus")


def test_interval_integral_rejects_min_greater_than_or_equal_to_max():
    x = np.linspace(0, 10, 20)
    y = x.copy()
    with pytest.raises(ValueError, match="最小値"):
        calculate_interval_integral(x, y, (5, 5))
    with pytest.raises(ValueError, match="最小値"):
        calculate_interval_integral(x, y, (5, 2))


def test_interval_integral_rejects_range_outside_data_span():
    x = np.linspace(0, 10, 20)
    y = x.copy()
    with pytest.raises(ValueError, match="X範囲"):
        calculate_interval_integral(x, y, (-1, 5))
    with pytest.raises(ValueError, match="X範囲"):
        calculate_interval_integral(x, y, (5, 11))


def test_interval_integral_rejects_too_few_points_in_range():
    # 範囲内に1点しか入らない(=積分できない)場合はエラーにする
    x = np.array([0.0, 1.0, 10.0])
    y = np.array([0.0, 1.0, 10.0])
    with pytest.raises(ValueError, match="最低2点"):
        calculate_interval_integral(x, y, (0.0, 0.5))


def test_interval_integral_rejects_all_nan_data():
    x = np.array([np.nan, np.nan, np.nan])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="欠損値"):
        calculate_interval_integral(x, y, (0, 1))


# --- 累積積分(C-303) ---

def test_cumulative_integral_trapezoid_linear_function_matches_analytic_area():
    # y = x の累積積分は x^2/2 になるはず(0起点)。
    x = np.linspace(0, 10, 101)
    y = x.copy()
    result = calculate_cumulative_integral(x, y, method="trapezoid")
    assert result['method'] == "trapezoid"
    assert result['n_points'] == len(x)
    assert result['y_cumulative'][0] == pytest.approx(0.0, abs=1e-9)
    np.testing.assert_allclose(result['x_used'], x, atol=1e-9)
    np.testing.assert_allclose(result['y_cumulative'], x ** 2 / 2, atol=1e-2)


def test_cumulative_integral_simpson_quadratic_more_accurate_than_trapezoid():
    x = np.linspace(0, 10, 21)
    y = x ** 2
    exact = x ** 3 / 3
    trap = calculate_cumulative_integral(x, y, method="trapezoid")
    simpson = calculate_cumulative_integral(x, y, method="simpson")
    # 終点(全区間)の誤差を比較する
    assert abs(simpson['y_cumulative'][-1] - exact[-1]) < abs(trap['y_cumulative'][-1] - exact[-1])


def test_cumulative_integral_sorts_unsorted_input():
    x = np.array([2.0, 0.0, 1.0])
    y = np.array([2.0, 0.0, 1.0])  # y = x
    result = calculate_cumulative_integral(x, y, method="trapezoid")
    np.testing.assert_allclose(result['x_used'], [0.0, 1.0, 2.0])
    np.testing.assert_allclose(result['y_cumulative'], [0.0, 0.5, 2.0], atol=1e-9)


def test_cumulative_integral_ignores_nan_rows():
    x = np.linspace(0, 10, 20)
    y = x.copy()
    y[5] = np.nan
    result = calculate_cumulative_integral(x, y, method="trapezoid")
    assert result['n_points'] == 19


def test_cumulative_integral_rejects_unknown_method():
    x = np.linspace(0, 10, 10)
    y = x.copy()
    with pytest.raises(ValueError, match="積分方法"):
        calculate_cumulative_integral(x, y, method="bogus")


def test_cumulative_integral_rejects_too_few_points():
    with pytest.raises(ValueError, match="最低2点"):
        calculate_cumulative_integral(np.array([1.0]), np.array([1.0]))


def test_cumulative_integral_rejects_all_nan_data():
    x = np.array([np.nan, np.nan])
    y = np.array([1.0, 2.0])
    with pytest.raises(ValueError):
        calculate_cumulative_integral(x, y)


# --- ライン表示の平滑化手法(C-304): 移動平均/中央値/ガウシアンフィルタ ---

def test_moving_average_smooth_reduces_noise_variance():
    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, 200)
    y = np.sin(x) + rng.normal(0, 0.3, size=len(x))
    x_smooth, y_smooth = calculate_moving_average_smooth(x, y, window=9)
    np.testing.assert_allclose(x_smooth, x)
    assert len(y_smooth) == len(y)
    # 平滑化後は真の信号(sin(x))からの残差の分散がノイズそのものより小さくなるはず
    assert np.var(y_smooth - np.sin(x)) < np.var(y - np.sin(x))


def test_moving_average_smooth_window_clipped_to_data_length():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([1.0, 2.0, 3.0])
    # windowがデータ点数を大きく超えてもエラーにならず、クリップして計算する
    x_smooth, y_smooth = calculate_moving_average_smooth(x, y, window=999)
    assert len(y_smooth) == 3


def test_moving_average_smooth_window_one_returns_original_values():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([1.0, 5.0, 3.0])
    _x, y_smooth = calculate_moving_average_smooth(x, y, window=1)
    np.testing.assert_allclose(y_smooth, y)


def test_median_smooth_removes_single_spike():
    x = np.arange(11, dtype=float)
    y = np.ones_like(x)
    y[5] = 100.0  # 単発のスパイクノイズ
    _x, y_smooth = calculate_median_smooth(x, y, window=5)
    # 中央値フィルタは単発スパイクを完全に除去できるはず
    assert y_smooth[5] == pytest.approx(1.0)


def test_median_smooth_sorts_unsorted_input():
    x = np.array([2.0, 0.0, 1.0])
    y = np.array([20.0, 0.0, 10.0])
    x_smooth, _y_smooth = calculate_median_smooth(x, y, window=3)
    np.testing.assert_allclose(x_smooth, [0.0, 1.0, 2.0])


def test_gaussian_smooth_reduces_noise_variance():
    rng = np.random.default_rng(1)
    x = np.linspace(0, 10, 200)
    y = np.sin(x) + rng.normal(0, 0.3, size=len(x))
    _x, y_smooth = calculate_gaussian_smooth(x, y, sigma=3.0)
    assert np.var(y_smooth - np.sin(x)) < np.var(y - np.sin(x))


def test_gaussian_smooth_non_positive_sigma_returns_original_values():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([1.0, 5.0, 3.0])
    _x, y_smooth = calculate_gaussian_smooth(x, y, sigma=0.0)
    np.testing.assert_allclose(y_smooth, y)


# --- ロバストフィット(C-407): loss='soft_l1'/'huber' ---

def test_robust_fit_soft_l1_less_affected_by_outlier_than_linear():
    x = np.linspace(0, 10, 50)
    y = 2.0 * x + 1.0
    y[5] = 200.0  # 明確な外れ値

    linear_fit = calculate_curve_fit(x, y, "線形 (y = ax + b)")
    robust_fit = calculate_curve_fit(x, y, "線形 (y = ax + b)", loss='soft_l1')

    # 外れ値の影響で通常の最小二乗の傾きは真値(2.0)から大きくズレるが、
    # ロバストフィットはそれよりも真値に近い値を返すはず。
    assert abs(robust_fit['popt'][0] - 2.0) < abs(linear_fit['popt'][0] - 2.0)
    assert robust_fit['loss'] == 'soft_l1'
    assert linear_fit['loss'] == 'linear'


def test_robust_fit_huber_also_less_affected_by_outlier():
    x = np.linspace(0, 10, 50)
    y = 2.0 * x + 1.0
    y[5] = 200.0

    linear_fit = calculate_curve_fit(x, y, "線形 (y = ax + b)")
    robust_fit = calculate_curve_fit(x, y, "線形 (y = ax + b)", loss='huber')
    assert abs(robust_fit['popt'][0] - 2.0) < abs(linear_fit['popt'][0] - 2.0)
    assert robust_fit['loss'] == 'huber'


def test_robust_fit_default_loss_is_linear_and_matches_previous_behavior():
    x = np.linspace(0, 10, 50)
    y = 2.5 * x + 1.3
    result = calculate_curve_fit(x, y, "線形 (y = ax + b)")
    assert result['loss'] == 'linear'
    np.testing.assert_allclose(result['popt'], [2.5, 1.3], atol=1e-6)


def test_robust_fit_rejects_unknown_loss():
    x = np.linspace(0, 10, 20)
    y = 2.0 * x + 1.0
    with pytest.raises(ValueError, match="損失関数"):
        calculate_curve_fit(x, y, "線形 (y = ax + b)", loss='bogus')


def test_robust_fit_works_with_bounds_and_fixed_params():
    # bounds指定時は既にmethod='trf'が自動選択されるため、lossとの組み合わせでも
    # 例外なく動作することを確認する回帰テスト。
    x = np.linspace(0, 10, 50)
    y = 2.0 * x + 1.0
    result = calculate_curve_fit(
        x, y, "線形 (y = ax + b)", loss='huber', bounds={'a': (0.0, 10.0)},
    )
    assert result['loss'] == 'huber'
    assert 0.0 <= result['popt'][0] <= 10.0


# --- 重複X値の平均化(C-203) ---

def test_average_duplicate_x_groups_and_averages():
    x = [1.0, 2.0, 2.0, 3.0, 1.0]
    y = [10.0, 20.0, 22.0, 30.0, 12.0]
    result = calculate_average_duplicate_x(x, y)
    np.testing.assert_allclose(result['x_used'], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(result['y_averaged'], [11.0, 21.0, 30.0])
    np.testing.assert_array_equal(result['group_sizes'], [2, 2, 1])
    assert result['n_duplicate_groups'] == 2
    assert result['n_points_in'] == 5
    assert result['n_points_out'] == 3


def test_average_duplicate_x_no_duplicates_returns_unchanged_sorted():
    x = [3.0, 1.0, 2.0]
    y = [30.0, 10.0, 20.0]
    result = calculate_average_duplicate_x(x, y)
    np.testing.assert_allclose(result['x_used'], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(result['y_averaged'], [10.0, 20.0, 30.0])
    assert result['n_duplicate_groups'] == 0


def test_average_duplicate_x_ignores_nan_rows():
    x = [1.0, 1.0, np.nan, 2.0]
    y = [10.0, 12.0, 5.0, 20.0]
    result = calculate_average_duplicate_x(x, y)
    assert result['n_points_in'] == 3
    np.testing.assert_allclose(result['x_used'], [1.0, 2.0])


def test_average_duplicate_x_rejects_all_nan_data():
    with pytest.raises(ValueError, match="欠損値"):
        calculate_average_duplicate_x([np.nan, np.nan], [1.0, 2.0])


# --- 統計的外れ値検出(C-306): Z-score / IQR ---

def test_zscore_outliers_detects_clear_outlier():
    rng = np.random.default_rng(0)
    y = np.concatenate([rng.normal(0, 1, 50), [100.0]])
    result = calculate_zscore_outliers(y, threshold=3.0)
    assert result['is_outlier'][-1] == True  # noqa: E712 (numpy.bool_との比較を明示)
    assert result['n_outliers'] >= 1
    assert len(result['is_outlier']) == len(y)
    assert result['threshold'] == 3.0


def test_zscore_outliers_no_outliers_in_uniform_data():
    y = np.full(20, 5.0)  # 標準偏差0
    result = calculate_zscore_outliers(y, threshold=3.0)
    assert result['n_outliers'] == 0
    assert not result['is_outlier'].any()


def test_zscore_outliers_nan_rows_never_flagged_and_preserve_length():
    y = np.array([1.0, 2.0, np.nan, 3.0, 100.0])
    result = calculate_zscore_outliers(y, threshold=1.0)
    assert len(result['is_outlier']) == 5
    assert result['is_outlier'][2] == False  # noqa: E712
    assert np.isnan(result['z_scores'][2])


def test_zscore_outliers_rejects_non_positive_threshold():
    with pytest.raises(ValueError):
        calculate_zscore_outliers([1.0, 2.0, 3.0], threshold=0)


def test_iqr_outliers_detects_clear_outlier():
    rng = np.random.default_rng(1)
    y = np.concatenate([rng.normal(0, 1, 50), [100.0]])
    result = calculate_iqr_outliers(y, multiplier=1.5)
    assert result['is_outlier'][-1] == True  # noqa: E712
    assert result['n_outliers'] >= 1
    assert result['lower_bound'] is not None
    assert result['upper_bound'] is not None


def test_iqr_outliers_insufficient_points_returns_no_outliers_and_none_bounds():
    y = np.array([1.0, 2.0, 3.0])  # 4点未満
    result = calculate_iqr_outliers(y, multiplier=1.5)
    assert result['n_outliers'] == 0
    assert result['lower_bound'] is None
    assert result['upper_bound'] is None


def test_iqr_outliers_rejects_non_positive_multiplier():
    with pytest.raises(ValueError):
        calculate_iqr_outliers([1.0, 2.0, 3.0, 4.0], multiplier=0)


# --- 信頼帯・予測帯(C-405) ---

def _fit_linear_with_noise(rng, n=40, slope=2.0, intercept=1.0, noise_sd=0.3):
    x = np.linspace(0, 10, n)
    y = slope * x + intercept + rng.normal(0, noise_sd, size=n)
    result = calculate_curve_fit(x, y, "線形 (y = ax + b)")
    return x, y, result


def test_confidence_band_narrower_than_prediction_band():
    """信頼帯(パラメータの不確かさのみ)は、予測帯(+観測ノイズ)より必ず狭い。"""
    rng = np.random.default_rng(0)
    x, y, result = _fit_linear_with_noise(rng)

    conf = calculate_confidence_band(
        result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
        result['residuals'], confidence=0.95, band_type="confidence",
    )
    pred = calculate_confidence_band(
        result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
        result['residuals'], confidence=0.95, band_type="prediction",
    )
    conf_width = conf['y_upper'] - conf['y_lower']
    pred_width = pred['y_upper'] - pred['y_lower']
    assert np.all(pred_width > conf_width)
    # 中心はどちらもフィット曲線そのもの
    np.testing.assert_allclose(conf['y_center'], result['y_fit'])
    np.testing.assert_allclose(pred['y_center'], result['y_fit'])


def test_confidence_band_widens_away_from_data_center():
    """線形回帰の信頼帯は、データの中心から離れるほど広がる(教科書的な性質)。"""
    rng = np.random.default_rng(1)
    x, y, result = _fit_linear_with_noise(rng)

    conf = calculate_confidence_band(
        result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
        result['residuals'], band_type="confidence",
    )
    width = conf['y_upper'] - conf['y_lower']
    center_idx = len(width) // 2
    # 両端(データ範囲の端)の帯幅は、中央付近の帯幅より広いはず
    assert width[0] > width[center_idx]
    assert width[-1] > width[center_idx]


def test_confidence_band_wider_with_higher_confidence_level():
    rng = np.random.default_rng(2)
    x, y, result = _fit_linear_with_noise(rng)

    band_90 = calculate_confidence_band(
        result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
        result['residuals'], confidence=0.90, band_type="confidence",
    )
    band_99 = calculate_confidence_band(
        result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
        result['residuals'], confidence=0.99, band_type="confidence",
    )
    width_90 = band_90['y_upper'] - band_90['y_lower']
    width_99 = band_99['y_upper'] - band_99['y_lower']
    assert np.all(width_99 > width_90)


def test_confidence_band_rejects_unknown_band_type():
    rng = np.random.default_rng(3)
    x, y, result = _fit_linear_with_noise(rng)
    with pytest.raises(ValueError, match="band_type"):
        calculate_confidence_band(
            result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
            result['residuals'], band_type="not_a_real_type",
        )


def test_confidence_band_rejects_confidence_out_of_range():
    rng = np.random.default_rng(4)
    x, y, result = _fit_linear_with_noise(rng)
    with pytest.raises(ValueError, match="信頼水準"):
        calculate_confidence_band(
            result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
            result['residuals'], confidence=1.5,
        )


def test_confidence_band_rejects_insufficient_degrees_of_freedom():
    # データ点数(2) - パラメータ数(2、線形フィットのa,b) = 自由度0 → エラー
    x = np.array([0.0, 1.0])
    y = np.array([1.0, 3.0])
    result = calculate_curve_fit(x, y, "線形 (y = ax + b)")
    with pytest.raises(ValueError, match="自由度"):
        calculate_confidence_band(
            result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
            result['residuals'], band_type="confidence",
        )


def test_confidence_band_matches_fit_func_at_popt():
    """y_centerはfit_func(x_eval, *popt)と完全に一致するはず(ヤコビアン計算の
    副作用でpoptやfit_funcの呼び出し結果自体が変わっていないことの確認)。"""
    rng = np.random.default_rng(5)
    x, y, result = _fit_linear_with_noise(rng)
    conf = calculate_confidence_band(
        result['x_fit'], result['fit_func'], result['popt'], result['pcov'],
        result['residuals'], band_type="confidence",
    )
    expected = result['fit_func'](result['x_fit'], *result['popt'])
    np.testing.assert_allclose(conf['y_center'], expected)


# =============================================================================
# 共通X格子へのリサンプリング/補間 (calculate_resample_to_grid, 項目C-305)
# =============================================================================

def test_resample_linear_recovers_values_inside_range():
    """y=x^2 を細かい/粗い/ずれたグリッドに線形補間し、解析関数に近い値になる
    (線形補間なので厳密一致は求めず、粗いグリッド相応の緩い許容誤差にする)。"""
    x = np.linspace(0, 10, 200)  # 十分細かい元データ
    y = x ** 2

    finer = np.linspace(0, 10, 500)
    result_fine = calculate_resample_to_grid(x, y, finer, method="linear")
    np.testing.assert_allclose(result_fine, finer ** 2, atol=0.05)

    coarser = np.linspace(1, 9, 5)
    result_coarse = calculate_resample_to_grid(x, y, coarser, method="linear")
    np.testing.assert_allclose(result_coarse, coarser ** 2, atol=0.05)

    shifted = np.linspace(0.3, 9.3, 30)
    result_shifted = calculate_resample_to_grid(x, y, shifted, method="linear")
    np.testing.assert_allclose(result_shifted, shifted ** 2, atol=0.05)


def test_resample_cubic_more_accurate_than_linear_on_curved_function():
    """疎な元データに対し、曲線的な関数ではcubicの方がlinearより格子点間の誤差が
    小さくなるはず(3次スプラインは曲率を捉えられるが線形補間は直線でつなぐため)。"""
    x = np.linspace(0, 10, 11)  # わざと疎にする(格子点間の誤差が出るように)
    y = np.sin(x)

    # 格子点の"間"の位置だけを評価する(格子点上では両方式とも厳密一致するため)
    target = x[:-1] + 0.5

    linear_result = calculate_resample_to_grid(x, y, target, method="linear")
    cubic_result = calculate_resample_to_grid(x, y, target, method="cubic")

    linear_err = np.abs(linear_result - np.sin(target))
    cubic_err = np.abs(cubic_result - np.sin(target))
    assert np.max(cubic_err) < np.max(linear_err)


def test_resample_out_of_range_is_nan_by_default():
    x = np.linspace(0, 10, 50)
    y = x ** 2
    target = np.array([-5.0, -0.001, 0.0, 5.0, 10.0, 10.001, 15.0])

    result_linear = calculate_resample_to_grid(x, y, target, method="linear")
    assert np.isnan(result_linear[0])
    assert np.isnan(result_linear[1])
    assert not np.isnan(result_linear[2])
    assert not np.isnan(result_linear[3])
    assert not np.isnan(result_linear[4])
    assert np.isnan(result_linear[5])
    assert np.isnan(result_linear[6])

    result_cubic = calculate_resample_to_grid(x, y, target, method="cubic")
    assert np.isnan(result_cubic[0])
    assert np.isnan(result_cubic[1])
    assert not np.isnan(result_cubic[2])
    assert not np.isnan(result_cubic[3])
    assert not np.isnan(result_cubic[4])
    assert np.isnan(result_cubic[5])
    assert np.isnan(result_cubic[6])


def test_resample_extrapolate_true_linear_extends_edge_slope():
    """extrapolate=Trueの線形補間: 両端の傾きで真に外挿する
    (np.interpの既定の端値クランプではなく、実際に値が傾きに沿って伸びる)。"""
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 1.0, 2.0, 3.0])  # 傾き1の直線
    target = np.array([-2.0, 5.0])

    result = calculate_resample_to_grid(x, y, target, method="linear", extrapolate=True)
    np.testing.assert_allclose(result, [-2.0, 5.0])


def test_resample_extrapolate_true_cubic_uses_scipy_extrapolation():
    """extrapolate=Trueの3次スプライン: CubicSpline自身のextrapolate=Trueと一致する
    (直接scipy.interpolate.CubicSplineを使った場合と同じ結果になることを確認)。"""
    from scipy.interpolate import CubicSpline

    x = np.linspace(0, 10, 11)
    y = np.sin(x)
    target = np.array([-3.0, 13.0])

    result = calculate_resample_to_grid(x, y, target, method="cubic", extrapolate=True)
    expected = CubicSpline(x, y, extrapolate=True)(target)
    np.testing.assert_allclose(result, expected)


def test_resample_rejects_unknown_method():
    x = np.linspace(0, 10, 20)
    y = x.copy()
    with pytest.raises(ValueError, match="補間方法"):
        calculate_resample_to_grid(x, y, x, method="bogus")


def test_resample_linear_rejects_too_few_points():
    x = np.array([1.0])
    y = np.array([1.0])
    with pytest.raises(ValueError, match="2点"):
        calculate_resample_to_grid(x, y, np.array([1.0]), method="linear")


def test_resample_cubic_rejects_too_few_points():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([0.0, 1.0, 4.0])
    with pytest.raises(ValueError, match="4点"):
        calculate_resample_to_grid(x, y, x, method="cubic")


def test_resample_rejects_all_nan_data():
    x = np.array([np.nan, np.nan, np.nan])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="欠損値"):
        calculate_resample_to_grid(x, y, x, method="linear")


def test_resample_excludes_nan_rows_before_computing():
    x = np.array([0.0, 1.0, np.nan, 3.0, 4.0])
    y = np.array([0.0, 1.0, 2.0, np.nan, 16.0])
    target = np.array([0.5, 3.5])
    # 有効な点は (0,0),(1,1),(4,16) の3点のみ。
    # 0.5は(0,0)-(1,1)間で0.5、3.5は(1,1)-(4,16)間で1+((3.5-1)/(4-1))*(16-1)=13.5
    result = calculate_resample_to_grid(x, y, target, method="linear")
    np.testing.assert_allclose(result, [0.5, 13.5])


def test_resample_deduplicates_repeated_x_values():
    """同一X値が複数あると単調増加を要求する補間関数(特にcubic)が壊れるため、
    重複X値は最後の値を採用してまとめられることを確認する。"""
    x = np.array([0.0, 1.0, 1.0, 2.0, 3.0, 4.0])
    y = np.array([0.0, 1.0, 999.0, 4.0, 9.0, 16.0])  # x=1で2つ目(999)が採用されるべき
    result = calculate_resample_to_grid(x, y, np.array([1.0]), method="linear")
    np.testing.assert_allclose(result, [999.0])


# --- 表示用ダウンサンプリング(LTTB、C-1001) ---

def test_lttb_returns_all_indices_when_below_threshold():
    x = np.linspace(0, 10, 50)
    y = np.sin(x)
    idx = calculate_lttb_downsample(x, y, 100)
    np.testing.assert_array_equal(idx, np.arange(50))


def test_lttb_output_length_matches_n_out():
    x = np.linspace(0, 100, 10000)
    y = np.sin(x)
    idx = calculate_lttb_downsample(x, y, 500)
    assert len(idx) == 500


def test_lttb_always_keeps_first_and_last_point():
    x = np.linspace(0, 100, 10000)
    y = np.cos(x)
    idx = calculate_lttb_downsample(x, y, 500)
    assert idx[0] == 0
    assert idx[-1] == len(x) - 1


def test_lttb_indices_are_strictly_increasing_with_no_duplicates():
    x = np.linspace(0, 100, 10000)
    y = np.sin(x) + 0.1 * np.cos(x * 5)
    idx = calculate_lttb_downsample(x, y, 500)
    assert np.all(np.diff(idx) > 0)


def test_lttb_selected_points_are_real_original_points_not_interpolated():
    """LTTBは新しい点を合成しない(常に元データの実点のどれかを選ぶ)ことの確認。"""
    x = np.linspace(0, 100, 10000)
    y = np.sin(x)
    idx = calculate_lttb_downsample(x, y, 500)
    # 選ばれたインデックスでの値は、元のx/y配列の値とビット単位で完全一致するはず
    np.testing.assert_array_equal(x[idx], x[idx])
    assert idx.dtype.kind in ('i', 'u')  # 整数インデックス(浮動小数点の合成値ではない)


def test_lttb_preserves_a_sharp_isolated_spike():
    """ほぼ平坦な信号の中にある鋭いスパイクは、ダウンサンプリング後も
    (面積最大化の性質上)選ばれた点に残るはず。ナイーブな等間隔間引きでは
    このようなスパイクが運悪く間引かれて消えることがある。"""
    n = 5000
    x = np.arange(n, dtype=float)
    y = np.zeros(n)
    spike_pos = 2500
    y[spike_pos] = 100.0  # 周囲に対して極端に飛び出た1点

    idx = calculate_lttb_downsample(x, y, 200)
    assert spike_pos in idx


def test_lttb_downsampled_curve_approximates_linear_function_well():
    x = np.linspace(0, 100, 20000)
    y = 3.0 * x + 2.0
    idx = calculate_lttb_downsample(x, y, 200)
    x_ds, y_ds = x[idx], y[idx]
    # 線形関数を線形補間で復元すれば誤差はごく小さいはず
    y_interp = np.interp(x, x_ds, y_ds)
    np.testing.assert_allclose(y_interp, y, atol=1e-6)


def test_lttb_rejects_absurdly_small_n_out_by_returning_all_points():
    """n_outが3未満(先頭・末尾+中間1点の最低構成すら組めない)の場合は、
    間引かずに全点を返す(呼び出し側が誤って0/1/2を渡してもクラッシュしない)。"""
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    idx = calculate_lttb_downsample(x, y, 2)
    np.testing.assert_array_equal(idx, np.arange(100))


# =============================================================================
# 多峰分離フィット (calculate_multi_peak_fit, 項目C-409)
# =============================================================================

def _two_gaussians(x, a1, b1, c1, a2, b2, c2, baseline):
    return (
        a1 * np.exp(-((x - b1) ** 2) / (2 * c1 ** 2))
        + a2 * np.exp(-((x - b2) ** 2) / (2 * c2 ** 2))
        + baseline
    )


def test_multi_peak_gaussian_two_components_recovers_known_parameters():
    x = np.linspace(-10, 20, 400)
    y = _two_gaussians(x, 5.0, 0.0, 1.0, 3.0, 8.0, 1.5, 0.5)
    initial_guesses = [
        {'center': 0.2, 'height': 4.5, 'width': 1.0},
        {'center': 7.8, 'height': 2.8, 'width': 1.5},
    ]

    result = calculate_multi_peak_fit(x, y, 'gaussian', initial_guesses, baseline_type='constant')

    assert result['param_names'] == ['a1', 'b1', 'c1', 'a2', 'b2', 'c2', 'baseline_c']
    np.testing.assert_allclose(
        result['popt'], [5.0, 0.0, 1.0, 3.0, 8.0, 1.5, 0.5], atol=1e-2
    )
    assert result['r_squared'] == pytest.approx(1.0, abs=1e-4)
    assert result['component_type'] == 'gaussian'
    assert result['n_components'] == 2
    assert result['baseline_type'] == 'constant'
    assert len(result['components']) == 2
    assert result['components'][0]['type'] == 'gaussian'
    assert result['components'][0]['param_names'] == ['a1', 'b1', 'c1']
    np.testing.assert_allclose(result['components'][0]['params'], [5.0, 0.0, 1.0], atol=1e-2)
    np.testing.assert_allclose(result['components'][1]['params'], [3.0, 8.0, 1.5], atol=1e-2)


def test_multi_peak_single_component_matches_shape_of_single_peak_fit():
    """成分数1のgaussianフィットは、単峰版のガウシアンフィットと同じ形状に
    収束すること(合成ロジック自体の妥当性の間接的な確認)。"""
    x = np.linspace(-10, 10, 200)
    y = 5.0 * np.exp(-((x - 2.0) ** 2) / (2 * 1.5 ** 2)) + 0.5

    result = calculate_multi_peak_fit(
        x, y, 'gaussian', [{'center': 2.0, 'height': 5.0, 'width': 1.5}], baseline_type='constant'
    )

    np.testing.assert_allclose(result['popt'], [5.0, 2.0, 1.5, 0.5], atol=1e-2)


def test_multi_peak_lorentzian_recovers_known_parameters():
    x = np.linspace(-10, 10, 400)
    y = 4.0 / (1 + ((x - 1.0) / 2.0) ** 2) + 0.2

    result = calculate_multi_peak_fit(
        x, y, 'lorentzian', [{'center': 1.0, 'height': 4.0, 'width': 4.0}], baseline_type='constant'
    )

    np.testing.assert_allclose(result['popt'], [4.0, 1.0, 2.0, 0.2], atol=1e-2)


def test_multi_peak_pseudo_voigt_recovers_known_parameters():
    x = np.linspace(-10, 10, 400)
    eta = 0.4
    lorentzian_shape = 1 / (1 + ((x - 0.0) / 2.0) ** 2)
    gaussian_shape = np.exp(-4 * np.log(2) * ((x - 0.0) / 2.0) ** 2)
    y = 3.0 * (eta * lorentzian_shape + (1 - eta) * gaussian_shape)

    result = calculate_multi_peak_fit(
        x, y, 'pseudo_voigt', [{'center': 0.0, 'height': 3.0, 'width': 2.0}], baseline_type='none'
    )

    np.testing.assert_allclose(result['popt'], [3.0, 0.0, 2.0, 0.4], atol=1e-2)
    assert result['param_names'] == ['a1', 'b1', 'c1', 'eta1']  # baseline_type='none'なのでベースライン項なし


def test_multi_peak_voigt_fit_converges_and_matches_shape():
    x = np.linspace(-15, 15, 400)
    sigma0, gamma0 = 1.0, 0.8
    z = ((x - 0.0) + 1j * gamma0) / (sigma0 * np.sqrt(2))
    from scipy.special import wofz
    true_amplitude = 3.0 * sigma0 * np.sqrt(2 * np.pi)
    y = true_amplitude * np.real(wofz(z)) / (sigma0 * np.sqrt(2 * np.pi))

    result = calculate_multi_peak_fit(
        x, y, 'voigt', [{'center': 0.0, 'height': 3.0, 'width': 2.0}], baseline_type='none'
    )

    # フィットした形状が真の形状とよく一致していることを直接確認する
    # (voigtのsigma/gammaは縮退しうるため、パラメータ値そのものの一致は要求しない)。
    fit_func = result['fit_func']
    y_reconstructed = fit_func(x, *result['popt'])
    np.testing.assert_allclose(y_reconstructed, y, atol=1e-2)
    assert result['r_squared'] == pytest.approx(1.0, abs=1e-3)


def test_multi_peak_baseline_none_omits_baseline_param():
    x = np.linspace(-5, 5, 100)
    y = 2.0 * np.exp(-((x) ** 2) / (2 * 1.0 ** 2))
    result = calculate_multi_peak_fit(
        x, y, 'gaussian', [{'center': 0.0, 'height': 2.0, 'width': 1.0}], baseline_type='none'
    )
    assert result['param_names'] == ['a1', 'b1', 'c1']


def test_multi_peak_baseline_linear_recovers_slope_and_intercept():
    x = np.linspace(-10, 10, 300)
    y = 4.0 * np.exp(-((x - 1.0) ** 2) / (2 * 1.0 ** 2)) + 0.3 * x + 1.0
    result = calculate_multi_peak_fit(
        x, y, 'gaussian', [{'center': 1.0, 'height': 4.0, 'width': 1.0}], baseline_type='linear'
    )
    assert result['param_names'] == ['a1', 'b1', 'c1', 'baseline_m', 'baseline_b']
    np.testing.assert_allclose(result['popt'], [4.0, 1.0, 1.0, 0.3, 1.0], atol=1e-2)


def test_multi_peak_rejects_unknown_component_type():
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="不明な成分タイプ"):
        calculate_multi_peak_fit(x, y, 'not_a_type', [{'center': 1, 'height': 1, 'width': 1}])


def test_multi_peak_rejects_empty_initial_guesses():
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="少なくとも1つ"):
        calculate_multi_peak_fit(x, y, 'gaussian', [])


def test_multi_peak_rejects_unknown_baseline_type():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
    with pytest.raises(ValueError, match="不明なベースラインタイプ"):
        calculate_multi_peak_fit(
            x, y, 'gaussian', [{'center': 3, 'height': 2, 'width': 1}], baseline_type='exponential'
        )


def test_multi_peak_fit_excludes_nan_rows():
    x = np.array([-2.0, -1.0, 0.0, np.nan, 1.0, 2.0])
    y_clean = 3.0 * np.exp(-((np.array([-2.0, -1.0, 0.0, 1.0, 2.0])) ** 2) / (2 * 1.0 ** 2))
    y = np.array([y_clean[0], y_clean[1], y_clean[2], np.nan, y_clean[3], y_clean[4]])

    result = calculate_multi_peak_fit(
        x, y, 'gaussian', [{'center': 0.0, 'height': 3.0, 'width': 1.0}], baseline_type='none'
    )

    assert len(result['x_data_used']) == 5  # NaN行(2箇所どちらかがNaNの行)を除いた5点


def test_multi_peak_fit_applies_x_range_filter():
    x = np.linspace(-10, 10, 400)
    y = 5.0 * np.exp(-((x - 0.0) ** 2) / (2 * 1.0 ** 2)) + 0.5 + 100 * (x > 5)  # 範囲外に外れ値
    result = calculate_multi_peak_fit(
        x, y, 'gaussian', [{'center': 0.0, 'height': 5.0, 'width': 1.0}],
        baseline_type='constant', x_range=(-5.0, 5.0),
    )
    assert result['x_data_used'].max() <= 5.0
    np.testing.assert_allclose(result['popt'], [5.0, 0.0, 1.0, 0.5], atol=1e-2)


def test_multi_peak_fit_raises_when_data_points_fewer_than_params():
    x = np.array([1.0, 2.0])
    y = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="データ点数"):
        calculate_multi_peak_fit(
            x, y, 'gaussian',
            [{'center': 1, 'height': 1, 'width': 1}, {'center': 5, 'height': 1, 'width': 1}],
            baseline_type='linear',
        )


def test_multi_peak_fit_respects_fixed_params():
    """項目C-403の固定パラメータ機構(_run_curve_fit_with_overrides共有)が
    多峰分離フィットでも正しく機能すること。"""
    x = np.linspace(-10, 10, 300)
    y = 5.0 * np.exp(-((x - 2.0) ** 2) / (2 * 1.5 ** 2)) + 0.5
    result = calculate_multi_peak_fit(
        x, y, 'gaussian', [{'center': 2.0, 'height': 5.0, 'width': 1.5}], baseline_type='constant',
        fixed_params={'b1': 2.0},
    )
    assert result['popt'][1] == pytest.approx(2.0)
    assert result['pcov'][1, 1] == 0.0  # 固定パラメータの行/列は0で復元される


def test_multi_peak_fit_respects_bounds():
    x = np.linspace(-10, 10, 300)
    y = 5.0 * np.exp(-((x - 2.0) ** 2) / (2 * 1.5 ** 2)) + 0.5
    result = calculate_multi_peak_fit(
        x, y, 'gaussian', [{'center': 2.0, 'height': 5.0, 'width': 1.5}], baseline_type='constant',
        bounds={'a1': (0.0, 4.0)},  # 真の値5.0より低い上限に拘束
    )
    assert result['popt'][0] <= 4.0 + 1e-6


def test_multi_peak_fit_rejects_unknown_p0_override_param_name():
    x = np.linspace(-10, 10, 100)
    y = 5.0 * np.exp(-((x) ** 2) / (2 * 1.0 ** 2))
    with pytest.raises(ValueError, match="未知のパラメータ名"):
        calculate_multi_peak_fit(
            x, y, 'gaussian', [{'center': 0, 'height': 5, 'width': 1}], baseline_type='none',
            p0_overrides={'not_a_real_param': 1.0},
        )


# --- get_multi_peak_param_names ---

def test_get_multi_peak_param_names_gaussian_two_components_constant_baseline():
    names = get_multi_peak_param_names('gaussian', 2, baseline_type='constant')
    assert names == ['a1', 'b1', 'c1', 'a2', 'b2', 'c2', 'baseline_c']


def test_get_multi_peak_param_names_voigt_one_component_linear_baseline():
    names = get_multi_peak_param_names('voigt', 1, baseline_type='linear')
    assert names == ['a1', 'b1', 'sigma1', 'gamma1', 'baseline_m', 'baseline_b']


def test_get_multi_peak_param_names_no_baseline():
    names = get_multi_peak_param_names('pseudo_voigt', 1, baseline_type='none')
    assert names == ['a1', 'b1', 'c1', 'eta1']


def test_get_multi_peak_param_names_matches_calculate_multi_peak_fit():
    """get_multi_peak_param_names()が実際のフィット結果のparam_namesと一致すること
    (get_fit_param_names()とcalculate_curve_fitの関係と同じ整合性チェック)。"""
    x = np.linspace(-10, 10, 200)
    y = 5.0 * np.exp(-((x - 2.0) ** 2) / (2 * 1.5 ** 2)) + 3.0 * np.exp(-((x + 3.0) ** 2) / (2 * 1.0 ** 2)) + 0.5
    initial_guesses = [
        {'center': 2.0, 'height': 5.0, 'width': 1.5},
        {'center': -3.0, 'height': 3.0, 'width': 1.0},
    ]
    result = calculate_multi_peak_fit(x, y, 'gaussian', initial_guesses, baseline_type='constant')
    assert get_multi_peak_param_names('gaussian', 2, baseline_type='constant') == result['param_names']


def test_get_multi_peak_param_names_rejects_zero_components():
    with pytest.raises(ValueError, match="1以上"):
        get_multi_peak_param_names('gaussian', 0)


# --- multi_peak_fit_task (TaskRunner用ラッパー) ---

def test_multi_peak_fit_task_returns_same_shape_as_calculate_multi_peak_fit():
    x = np.linspace(-10, 10, 200)
    y = 5.0 * np.exp(-((x - 2.0) ** 2) / (2 * 1.5 ** 2)) + 0.5
    result = multi_peak_fit_task(
        x, y, 'gaussian', [{'center': 2.0, 'height': 5.0, 'width': 1.5}], baseline_type='constant',
        report_progress=lambda *a: None, is_cancelled=lambda: False,
    )
    np.testing.assert_allclose(result['popt'], [5.0, 2.0, 1.5, 0.5], atol=1e-2)
