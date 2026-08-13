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
                            get_fit_param_names, calculate_interval_integral)


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
    assert get_fit_param_names("シグモイド (y = a / (1 + exp(-b(x-c))))") == ['a', 'b', 'c']


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
