import re
from typing import Any, Callable
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.integrate import simpson, cumulative_trapezoid, cumulative_simpson
from scipy.interpolate import CubicSpline
from scipy.ndimage import uniform_filter1d, median_filter, gaussian_filter1d
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, peak_widths, savgol_filter, correlate, correlation_lags
from scipy.special import wofz
from scipy.stats import gaussian_kde

from graphica.core.safe_eval import DEFAULT_FUNCTIONS, safe_eval_formula

CURVE_FIT_MAX_ITERATIONS = 5000

# プラグインのフィット関数。{name: {"func": f(x, *params), "params": [...], "p0": list | callable | None}}
_PLUGIN_FIT_FUNCTIONS: dict[str, dict[str, Any]] = {}

# 組み込みのフィットタイプは部分一致で判定するので、プラグイン名がこれらを含むと取り違える。
_BUILTIN_FIT_TYPE_SUBSTRINGS = (
    "カスタム数式", "線形", "2次多項式", "3次多項式", "2成分指数", "指数関数",
    "対数", "べき乗", "ガウシアン", "ローレンツ", "擬似フォークト", "フォークト",
    "ボルツマン", "シグモイド", "ヒル",
)


def register_fit_function(name: str, func: Callable[..., Any], param_names: list[str],
                          p0: list[float] | Callable[..., Any] | None = None) -> None:
    """p0 は初期値のリストか (x_data, y_data) -> list を返す関数。省略時は全て 1.0。"""
    if not name or not name.strip():
        raise ValueError("フィット関数名が空です。")
    if name in _BUILTIN_FIT_TYPE_SUBSTRINGS:
        raise ValueError(f"'{name}' は組み込みのフィットタイプ名と衝突します。")
    if name in _PLUGIN_FIT_FUNCTIONS:
        raise ValueError(f"フィット関数 '{name}' は既に登録されています。")
    if not param_names:
        raise ValueError("param_names が空です。")
    _PLUGIN_FIT_FUNCTIONS[name] = {"func": func, "params": list(param_names), "p0": p0}


def get_plugin_fit_type_names() -> list[str]:
    return list(_PLUGIN_FIT_FUNCTIONS.keys())

_RESERVED_FORMULA_NAMES = set(DEFAULT_FUNCTIONS.keys()) | {'x'}


def _extract_formula_params(formula: str) -> list[str]:
    """x でも既知の関数名でもない識別子を、出現順にパラメータとして取り出す。"""
    params = []
    for name in re.findall(r'[a-zA-Z_][a-zA-Z_0-9]*', formula):
        if name in _RESERVED_FORMULA_NAMES or name in params:
            continue
        params.append(name)
    if not params:
        raise ValueError("数式にフィットパラメータ(x以外の文字)が見つかりません。")
    return params


def _build_custom_fit_func(formula: str, param_names: list[str]) -> Callable[..., Any]:
    def custom_func(x: Any, *params: float) -> Any:
        variables = {'x': x}
        variables.update(zip(param_names, params))
        try:
            return safe_eval_formula(formula, variables)
        except Exception as e:
            raise ValueError(f"数式の評価に失敗しました: {e}") from e
    return custom_func


def get_fit_param_names(fit_type: str, custom_formula: str | None = None) -> list[str]:
    """フィットせずにパラメータ名を返す(フィットの前に入力欄を組み立てるため)。

    判定の順序とパラメータ名は calculate_curve_fit() の分岐と同じにしておくこと。
    """
    if "カスタム数式" in fit_type:
        if not custom_formula or not custom_formula.strip():
            raise ValueError("カスタム数式が入力されていません。")
        return _extract_formula_params(custom_formula)
    elif "線形" in fit_type:
        return ['a', 'b']
    elif "2次多項式" in fit_type:
        return ['a', 'b', 'c']
    elif "3次多項式" in fit_type:
        return ['a', 'b', 'c', 'd']
    elif "2成分指数" in fit_type:
        # "2成分指数関数" は "指数関数" を含むので先に判定する
        return ['a1', 'b1', 'a2', 'b2', 'c']
    elif "指数関数" in fit_type:
        return ['a', 'b']
    elif "対数" in fit_type:
        return ['a', 'b']
    elif "べき乗" in fit_type:
        return ['a', 'b']
    elif "ガウシアン" in fit_type:
        return ['a', 'b', 'c', 'd']
    elif "ローレンツ" in fit_type:
        return ['a', 'b', 'c', 'd']
    elif "擬似フォークト" in fit_type:
        # "擬似フォークト関数" は "フォークト" を含むので先に判定する
        return ['a', 'b', 'c', 'eta', 'd']
    elif "フォークト" in fit_type:
        return ['a', 'b', 'sigma', 'gamma', 'd']
    elif "ボルツマン" in fit_type:
        # "ボルツマンシグモイド" は "シグモイド" を含むので先に判定する
        return ['a1', 'a2', 'x0', 'dx']
    elif "シグモイド" in fit_type:
        return ['a', 'b', 'c']
    elif "ヒル" in fit_type:
        return ['vmax', 'k', 'n']
    elif fit_type in _PLUGIN_FIT_FUNCTIONS:
        return list(_PLUGIN_FIT_FUNCTIONS[fit_type]["params"])
    else:
        raise ValueError(f"不明なフィットタイプ: {fit_type}")


_ROBUST_LOSS_FUNCTIONS = ('linear', 'soft_l1', 'huber')


def _run_curve_fit_with_overrides(fit_func: Callable[..., Any], params_info: list[str], p0: Any, x_data: Any, y_data: Any,
                                   sigma: Any, p0_overrides: dict[str, float] | None, fixed_params: dict[str, float] | None,
                                   bounds: dict[str, tuple[float, float]] | None, fit_type_label: str,
                                   loss: str = 'linear') -> tuple[np.ndarray, np.ndarray]:
    """p0 の上書き・固定・範囲拘束を適用して curve_fit を実行する。

    popt と pcov は固定パラメータも含めたフルサイズで返す(固定分の pcov は 0)。
    """
    if loss not in _ROBUST_LOSS_FUNCTIONS:
        raise ValueError(f"未知の損失関数です(loss): '{loss}' (使用可能: {_ROBUST_LOSS_FUNCTIONS})")
    if len(x_data) < len(params_info):
        raise ValueError(
            f"データ点数 ({len(x_data)}) がフィットに必要なパラメータ数 "
            f"({len(params_info)}) より少ないため、フィッティングできません。"
        )

    p0_overrides = p0_overrides or {}
    fixed_params = fixed_params or {}
    bounds = bounds or {}

    for name_dict, label in (
        (p0_overrides, "p0_overrides"), (fixed_params, "fixed_params"), (bounds, "bounds"),
    ):
        for pname in name_dict:
            if pname not in params_info:
                raise ValueError(
                    f"未知のパラメータ名です({label}): '{pname}' "
                    f"(このフィットタイプのパラメータ: {params_info})"
                )

    if fixed_params and len(fixed_params) >= len(params_info):
        raise ValueError(
            "すべてのパラメータを固定することはできません"
            "(最適化する自由パラメータが1つも残りません)。"
        )

    p0 = list(p0)
    for i, name in enumerate(params_info):
        if name in p0_overrides:
            p0[i] = float(p0_overrides[name])

    free_indices = [i for i, name in enumerate(params_info) if name not in fixed_params]
    fixed_indices = [i for i, name in enumerate(params_info) if name in fixed_params]
    fixed_values = {i: float(fixed_params[params_info[i]]) for i in fixed_indices}

    if fixed_indices:
        # curve_fit には自由パラメータだけを渡し、固定値は関数の中で元の位置に挿し込む
        original_fit_func = fit_func

        def fit_func_for_curve_fit(x: Any, *free_args: float) -> Any:
            full_params: list[float | None] = [None] * len(params_info)
            for i in fixed_indices:
                full_params[i] = fixed_values[i]
            for idx, i in enumerate(free_indices):
                full_params[i] = free_args[idx]
            return original_fit_func(x, *full_params)

        p0_for_curve_fit = [p0[i] for i in free_indices]
    else:
        fit_func_for_curve_fit = fit_func
        p0_for_curve_fit = p0

    curve_fit_kwargs = {
        "p0": p0_for_curve_fit,
        "sigma": sigma,
        "absolute_sigma": sigma is not None,
    }
    if bounds:
        lower, upper = [], []
        for i in free_indices:
            lo, hi = bounds.get(params_info[i], (-np.inf, np.inf))
            lower.append(lo)
            upper.append(hi)
        # bounds は p0 が境界の厳密に内側にあることを要求する(等しいだけで例外)。
        # 「初期値=下限」のような自然な入力で落ちないよう、わずかに内側へずらす。
        for idx in range(len(p0_for_curve_fit)):
            lo, hi = lower[idx], upper[idx]
            val = p0_for_curve_fit[idx]
            if val <= lo or val >= hi:
                span = hi - lo
                nudge = span * 1e-6 if np.isfinite(span) and span > 0 else max(abs(val), 1.0) * 1e-6 or 1e-9
                p0_for_curve_fit[idx] = min(max(val, lo + nudge), hi - nudge)
        curve_fit_kwargs["bounds"] = (lower, upper)
        # bounds 付きは trf 法になり、maxfev ではなく max_nfev しか受け付けない
        curve_fit_kwargs["max_nfev"] = CURVE_FIT_MAX_ITERATIONS
    else:
        curve_fit_kwargs["maxfev"] = CURVE_FIT_MAX_ITERATIONS

    if loss != 'linear':
        # 既定の 'lm' は loss を受け付けないので trf にし、maxfev も max_nfev に付け替える
        curve_fit_kwargs["loss"] = loss
        curve_fit_kwargs.setdefault("method", "trf")
        if "maxfev" in curve_fit_kwargs:
            curve_fit_kwargs["max_nfev"] = curve_fit_kwargs.pop("maxfev")

    try:
        popt_free, pcov_free = curve_fit(fit_func_for_curve_fit, x_data, y_data, **curve_fit_kwargs)
    except RuntimeError as e:
        raise RuntimeError(
            f"フィッティングが収束しませんでした（{fit_type_label}）。データの分布が"
            f"このモデルに適していない可能性があります。詳細: {e}"
        ) from e

    if fixed_indices:
        popt = np.empty(len(params_info))
        for i in fixed_indices:
            popt[i] = fixed_values[i]
        for idx, i in enumerate(free_indices):
            popt[i] = popt_free[idx]

        pcov = np.zeros((len(params_info), len(params_info)))
        for row_idx, i in enumerate(free_indices):
            for col_idx, j in enumerate(free_indices):
                pcov[i, j] = pcov_free[row_idx, col_idx]
    else:
        popt, pcov = popt_free, pcov_free

    return popt, pcov


def calculate_curve_fit(x_data: Any, y_data: Any, fit_type: str, custom_formula: str | None = None, sigma: Any = None,
                        x_range: tuple[float, float] | None = None, p0_overrides: dict[str, float] | None = None,
                        fixed_params: dict[str, float] | None = None,
                        bounds: dict[str, tuple[float, float]] | None = None, loss: str = 'linear') -> dict[str, Any]:
    """曲線フィット。popt / pcov / perr / x_fit・y_fit / r_squared / residuals などの dict を返す。

    x_range は両端を含み、範囲外の点は p0 の推定にも使わない。sigma は absolute_sigma=True で渡す。
    """
    x_data = np.asarray(x_data)
    y_data = np.asarray(y_data)
    if sigma is not None:
        sigma = np.asarray(sigma)
    if x_range is not None:
        x_min, x_max = x_range
        range_mask = (x_data >= x_min) & (x_data <= x_max)
        x_data, y_data = x_data[range_mask], y_data[range_mask]
        if sigma is not None:
            sigma = sigma[range_mask]

    # NaN が残ると curve_fit は収束失敗ではない ValueError を出し、p0 の推定も落ちる
    nan_mask = np.isnan(x_data) | np.isnan(y_data)
    if sigma is not None:
        nan_mask |= np.isnan(sigma)
    if nan_mask.any():
        x_data, y_data = x_data[~nan_mask], y_data[~nan_mask]
        if sigma is not None:
            sigma = sigma[~nan_mask]

    if len(x_data) == 0:
        raise ValueError("有効なデータ点がありません(すべて欠損値です)。フィッティングできません。")

    def linear_func(x: Any, a: float, b: float) -> Any:
        return a * x + b

    def poly2_func(x: Any, a: float, b: float, c: float) -> Any:
        return a * x**2 + b * x + c

    def poly3_func(x: Any, a: float, b: float, c: float, d: float) -> Any:
        return a * x**3 + b * x**2 + c * x + d

    def exp_func(x: Any, a: float, b: float) -> Any:
        return a * np.exp(b * x)

    def log_func(x: Any, a: float, b: float) -> Any:
        return a * np.log(x) + b

    def power_func(x: Any, a: float, b: float) -> Any:
        return a * np.power(x, b)

    def gaussian_func(x: Any, a: float, b: float, c: float, d: float) -> Any:
        return a * np.exp(-((x - b) ** 2) / (2 * c ** 2)) + d

    def sigmoid_func(x: Any, a: float, b: float, c: float) -> Any:
        return a / (1 + np.exp(-b * (x - c)))

    def multi_exp_func(x: Any, a1: float, b1: float, a2: float, b2: float, c: float) -> Any:
        return a1 * np.exp(b1 * x) + a2 * np.exp(b2 * x) + c

    def lorentzian_func(x: Any, a: float, b: float, c: float, d: float) -> Any:
        return a / (1 + ((x - b) / c) ** 2) + d

    def pseudo_voigt_func(x: Any, a: float, b: float, c: float, eta: float, d: float) -> Any:
        # 共通の中心 b と FWHM c を持つローレンツ型とガウス型を eta で混ぜる
        lorentzian_shape = 1 / (1 + ((x - b) / c) ** 2)
        gaussian_shape = np.exp(-4 * np.log(2) * ((x - b) / c) ** 2)
        return a * (eta * lorentzian_shape + (1 - eta) * gaussian_shape) + d

    def voigt_func(x: Any, a: float, b: float, sigma: float, gamma: float, d: float) -> Any:
        # Faddeeva 関数による Voigt。この正規化で gamma→0 のとき a がピーク高さになる
        z = ((x - b) + 1j * gamma) / (sigma * np.sqrt(2))
        return a * np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi)) + d

    def boltzmann_sigmoid_func(x: Any, a1: float, a2: float, x0: float, dx: float) -> Any:
        return a2 + (a1 - a2) / (1 + np.exp((x - x0) / dx))

    def hill_func(x: Any, vmax: float, k: float, n: float) -> Any:
        return (vmax * np.power(x, n)) / (np.power(k, n) + np.power(x, n))

    def estimate_fwhm(x_arr: Any, y_arr: Any, amplitude: float) -> float:
        """半値を横切る X の幅を FWHM の粗い推定にする(裾の広い形で誤った局所解に落ちないため)。"""
        half_level = np.nanmin(y_arr) + amplitude / 2
        above_half = x_arr[y_arr >= half_level]
        if len(above_half) == 0:
            return (np.nanmax(x_arr) - np.nanmin(x_arr)) / 4 or 1.0
        return (above_half.max() - above_half.min()) or 1.0

    # パラメータ名は get_fit_param_names() と同じにしておくこと
    if "カスタム数式" in fit_type:
        if not custom_formula or not custom_formula.strip():
            raise ValueError("カスタム数式が入力されていません。")
        params_info = _extract_formula_params(custom_formula)
        fit_func = _build_custom_fit_func(custom_formula, params_info)
        # *params 形式ではパラメータ数を推定できないので p0 で数を伝える
        p0 = [1.0] * len(params_info)
    elif "線形" in fit_type:
        fit_func, params_info = linear_func, ['a', 'b']
        p0 = [1.0, 0.0]
    elif "2次多項式" in fit_type:
        fit_func, params_info = poly2_func, ['a', 'b', 'c']
        p0 = [1.0, 1.0, 0.0]
    elif "3次多項式" in fit_type:
        fit_func, params_info = poly3_func, ['a', 'b', 'c', 'd']
        p0 = [1.0, 1.0, 1.0, 0.0]
    elif "2成分指数" in fit_type:
        # "2成分指数関数" は "指数関数" を含むので先に判定する
        fit_func, params_info = multi_exp_func, ['a1', 'b1', 'a2', 'b2', 'c']
        amplitude = (np.nanmax(y_data) - np.nanmin(y_data)) / 2 or 1.0
        x_span = (np.nanmax(x_data) - np.nanmin(x_data)) or 1.0
        # 2成分が同じ初期値だと縮退して収束しないので、符号の違う率から始める
        rate0 = 2.0 / x_span
        p0 = [amplitude, rate0, amplitude, -rate0, np.nanmin(y_data)]
    elif "指数関数" in fit_type:
        fit_func, params_info = exp_func, ['a', 'b']
        amplitude = np.nanmean(np.abs(y_data)) or 1.0
        p0 = [amplitude, 0.01]
    elif "対数" in fit_type:
        if np.any(x_data <= 0):
            raise ValueError("対数フィットは X > 0 のデータにのみ使用できます。")
        fit_func, params_info = log_func, ['a', 'b']
        p0 = [1.0, 0.0]
    elif "べき乗" in fit_type:
        if np.any(x_data <= 0):
            raise ValueError("べき乗フィットは X > 0 のデータにのみ使用できます。")
        fit_func, params_info = power_func, ['a', 'b']
        p0 = [1.0, 1.0]
    elif "ガウシアン" in fit_type:
        fit_func, params_info = gaussian_func, ['a', 'b', 'c', 'd']
        amplitude = (np.nanmax(y_data) - np.nanmin(y_data)) or 1.0
        center = x_data[np.nanargmax(y_data)] if len(x_data) else 0.0
        width = (np.nanmax(x_data) - np.nanmin(x_data)) / 4 or 1.0
        p0 = [amplitude, center, width, np.nanmin(y_data)]
    elif "ローレンツ" in fit_type:
        fit_func, params_info = lorentzian_func, ['a', 'b', 'c', 'd']
        amplitude = (np.nanmax(y_data) - np.nanmin(y_data)) or 1.0
        center = x_data[np.nanargmax(y_data)] if len(x_data) else 0.0
        # c は HWHM なので FWHM の半分
        fwhm0 = estimate_fwhm(x_data, y_data, amplitude)
        p0 = [amplitude, center, fwhm0 / 2, np.nanmin(y_data)]
    elif "擬似フォークト" in fit_type:
        # "擬似フォークト関数" は "フォークト" を含むので先に判定する
        fit_func, params_info = pseudo_voigt_func, ['a', 'b', 'c', 'eta', 'd']
        amplitude = (np.nanmax(y_data) - np.nanmin(y_data)) or 1.0
        center = x_data[np.nanargmax(y_data)] if len(x_data) else 0.0
        # この定義の c は FWHM そのもの
        fwhm0 = estimate_fwhm(x_data, y_data, amplitude)
        p0 = [amplitude, center, fwhm0, 0.5, np.nanmin(y_data)]
    elif "フォークト" in fit_type:
        fit_func, params_info = voigt_func, ['a', 'b', 'sigma', 'gamma', 'd']
        amplitude = (np.nanmax(y_data) - np.nanmin(y_data)) or 1.0
        center = x_data[np.nanargmax(y_data)] if len(x_data) else 0.0
        fwhm0 = estimate_fwhm(x_data, y_data, amplitude)
        # FWHM をガウス成分とローレンツ成分に大まかに割り振る経験的な初期値
        sigma0 = (fwhm0 / 2.355) or 1.0
        gamma0 = (fwhm0 / 4) or 1.0
        # voigt_func の正規化に合わせ、ピーク高さが振幅に近くなるよう a をスケールする
        p0 = [amplitude * sigma0 * np.sqrt(2 * np.pi), center, sigma0, gamma0, np.nanmin(y_data)]
    elif "ボルツマン" in fit_type:
        # "ボルツマンシグモイド" は "シグモイド" を含むので先に判定する
        fit_func, params_info = boltzmann_sigmoid_func, ['a1', 'a2', 'x0', 'dx']
        order = np.argsort(x_data)
        x_sorted, y_sorted = x_data[order], y_data[order]
        y_start = y_sorted[0]
        y_end = y_sorted[-1]
        mid_level = (y_start + y_end) / 2
        # 遷移の中心は Y の中点を最初に横切る X から推定する(X の平均だと局所解に落ちやすい)
        crossing_mask = y_sorted < mid_level if y_start >= y_end else y_sorted > mid_level
        crossing_indices = np.flatnonzero(crossing_mask)
        x0 = x_sorted[crossing_indices[0]] if len(crossing_indices) else np.nanmean(x_data)
        dx0 = (np.nanmax(x_data) - np.nanmin(x_data)) / 10 or 1.0
        p0 = [y_start, y_end, x0, dx0]
    elif "シグモイド" in fit_type:
        fit_func, params_info = sigmoid_func, ['a', 'b', 'c']
        amplitude = np.nanmax(y_data) or 1.0
        p0 = [amplitude, 1.0, np.nanmean(x_data)]
    elif "ヒル" in fit_type:
        if np.any(x_data < 0):
            raise ValueError("ヒル式は X >= 0 のデータにのみ使用できます。")
        fit_func, params_info = hill_func, ['vmax', 'k', 'n']
        vmax0 = np.nanmax(y_data) or 1.0
        positive_x = x_data[x_data > 0]
        k0 = np.nanmedian(positive_x) if len(positive_x) else 1.0
        p0 = [vmax0, k0, 1.0]
    elif fit_type in _PLUGIN_FIT_FUNCTIONS:
        plugin_entry = _PLUGIN_FIT_FUNCTIONS[fit_type]
        fit_func, params_info = plugin_entry["func"], plugin_entry["params"]
        plugin_p0 = plugin_entry["p0"]
        if callable(plugin_p0):
            p0 = list(plugin_p0(x_data, y_data))
        elif plugin_p0 is not None:
            p0 = list(plugin_p0)
        else:
            p0 = [1.0] * len(params_info)
    else:
        raise ValueError(f"不明なフィットタイプ: {fit_type}")

    popt, pcov = _run_curve_fit_with_overrides(
        fit_func, params_info, p0, x_data, y_data, sigma,
        p0_overrides, fixed_params, bounds, fit_type, loss=loss,
    )

    # 退化したフィットでは pcov の対角が負や inf になる。例外にせず nan / inf のまま返す
    perr = np.sqrt(np.diag(pcov))

    x_fit = np.linspace(x_data.min(), x_data.max(), 200)
    y_fit = fit_func(x_fit, *popt)

    residuals = y_data - fit_func(x_data, *popt)
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((y_data - np.mean(y_data)) ** 2)
    r_squared = 1.0 if ss_tot == 0 else 1.0 - (ss_res / ss_tot)

    return {
        'popt': popt,
        'pcov': pcov,
        'perr': perr,
        'param_names': params_info,
        # 信頼帯の計算用。保存はしない(Dataset.fit_result には入れない)
        'fit_func': fit_func,
        'x_fit': x_fit,
        'y_fit': y_fit,
        'r_squared': r_squared,
        'residuals': residuals,
        'x_data_used': x_data,
        'y_data_used': y_data,
        'loss': loss,
    }


# 多峰分離の成分関数。ベースラインを全成分で共有するので、単峰版と違いオフセットを持たない。

def _gaussian_component(x: Any, a: float, b: float, c: float) -> Any:
    return a * np.exp(-((x - b) ** 2) / (2 * c ** 2))


def _lorentzian_component(x: Any, a: float, b: float, c: float) -> Any:
    return a / (1 + ((x - b) / c) ** 2)


def _pseudo_voigt_component(x: Any, a: float, b: float, c: float, eta: float) -> Any:
    lorentzian_shape = 1 / (1 + ((x - b) / c) ** 2)
    gaussian_shape = np.exp(-4 * np.log(2) * ((x - b) / c) ** 2)
    return a * (eta * lorentzian_shape + (1 - eta) * gaussian_shape)


def _voigt_component(x: Any, a: float, b: float, sigma: float, gamma: float) -> Any:
    z = ((x - b) + 1j * gamma) / (sigma * np.sqrt(2))
    return a * np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi))


def _constant_baseline(x: Any, c: float) -> Any:
    return np.full_like(np.asarray(x, dtype=float), c)


def _linear_baseline(x: Any, m: float, b: float) -> Any:
    return m * np.asarray(x, dtype=float) + b


_MULTI_PEAK_COMPONENT_TYPES: dict[str, dict[str, Any]] = {
    'gaussian': {'label': 'ガウシアン', 'func': _gaussian_component, 'param_names': ['a', 'b', 'c']},
    'lorentzian': {'label': 'ローレンツ', 'func': _lorentzian_component, 'param_names': ['a', 'b', 'c']},
    'pseudo_voigt': {'label': '擬似フォークト', 'func': _pseudo_voigt_component, 'param_names': ['a', 'b', 'c', 'eta']},
    'voigt': {'label': 'フォークト', 'func': _voigt_component, 'param_names': ['a', 'b', 'sigma', 'gamma']},
}


def calculate_multi_peak_fit(x_data: Any, y_data: Any, component_type: str, initial_guesses: list[dict[str, float]],
                             baseline_type: str = 'constant', x_range: tuple[float, float] | None = None,
                             sigma: Any = None, p0_overrides: dict[str, float] | None = None,
                             fixed_params: dict[str, float] | None = None,
                             bounds: dict[str, tuple[float, float]] | None = None) -> dict[str, Any]:
    """同じ種類の N 成分とベースラインを同時にフィットする。

    initial_guesses は [{'center', 'height', 'width'(FWHM)}, ...]。戻り値は calculate_curve_fit() の
    dict に component_type / n_components / baseline_type / components を足したもの。
    """
    if component_type not in _MULTI_PEAK_COMPONENT_TYPES:
        raise ValueError(f"不明な成分タイプ: {component_type}")
    if not initial_guesses:
        raise ValueError("少なくとも1つのピークの初期値が必要です。")
    if baseline_type not in ('none', 'constant', 'linear'):
        raise ValueError(f"不明なベースラインタイプ: {baseline_type}")

    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)
    if sigma is not None:
        sigma = np.asarray(sigma, dtype=float)
    if x_range is not None:
        x_min, x_max = x_range
        range_mask = (x_data >= x_min) & (x_data <= x_max)
        x_data, y_data = x_data[range_mask], y_data[range_mask]
        if sigma is not None:
            sigma = sigma[range_mask]

    # calculate_curve_fit() と同じ理由で NaN を除く
    nan_mask = np.isnan(x_data) | np.isnan(y_data)
    if sigma is not None:
        nan_mask |= np.isnan(sigma)
    if nan_mask.any():
        x_data, y_data = x_data[~nan_mask], y_data[~nan_mask]
        if sigma is not None:
            sigma = sigma[~nan_mask]

    if len(x_data) == 0:
        raise ValueError("有効なデータ点がありません(すべて欠損値です)。フィッティングできません。")

    component_info = _MULTI_PEAK_COMPONENT_TYPES[component_type]
    component_func = component_info['func']
    component_param_names = component_info['param_names']
    n_component_params = len(component_param_names)
    n_components = len(initial_guesses)

    params_info: list[str] = []
    p0: list[float] = []
    for i, guess in enumerate(initial_guesses, start=1):
        height = float(guess['height'])
        center = float(guess['center'])
        width = float(guess.get('width') or 1.0) or 1.0
        params_info.extend(f"{p}{i}" for p in component_param_names)
        if component_type == 'gaussian':
            p0.extend([height, center, width])
        elif component_type == 'lorentzian':
            # width は FWHM、c は HWHM
            p0.extend([height, center, (width / 2) or 1.0])
        elif component_type == 'pseudo_voigt':
            # この定義の c は FWHM そのもの
            p0.extend([height, center, width, 0.5])
        else:  # voigt
            # 単峰のフォークトと同じ初期値の割り振り
            sigma0 = (width / 2.355) or 1.0
            gamma0 = (width / 4) or 1.0
            amplitude0 = height * sigma0 * np.sqrt(2 * np.pi)
            p0.extend([amplitude0, center, sigma0, gamma0])

    baseline_func: Callable[..., Any] | None
    if baseline_type == 'constant':
        params_info.append('baseline_c')
        p0.append(float(np.nanmin(y_data)))
        baseline_func = _constant_baseline
    elif baseline_type == 'linear':
        params_info.extend(['baseline_m', 'baseline_b'])
        p0.extend([0.0, float(np.nanmin(y_data))])
        baseline_func = _linear_baseline
    else:
        baseline_func = None

    def fit_func(x: Any, *params: float) -> Any:
        total = np.zeros_like(np.asarray(x, dtype=float))
        for i in range(n_components):
            comp_params = params[i * n_component_params:(i + 1) * n_component_params]
            total = total + component_func(x, *comp_params)
        if baseline_func is not None:
            baseline_params = params[n_components * n_component_params:]
            total = total + baseline_func(x, *baseline_params)
        return total

    fit_type_label = f"多峰分離({component_info['label']} x{n_components})"
    popt, pcov = _run_curve_fit_with_overrides(
        fit_func, params_info, p0, x_data, y_data, sigma,
        p0_overrides, fixed_params, bounds, fit_type_label,
    )

    perr = np.sqrt(np.diag(pcov))
    x_fit = np.linspace(x_data.min(), x_data.max(), 200)
    y_fit = fit_func(x_fit, *popt)
    residuals = y_data - fit_func(x_data, *popt)
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((y_data - np.mean(y_data)) ** 2)
    r_squared = 1.0 if ss_tot == 0 else 1.0 - (ss_res / ss_tot)

    components = []
    for i in range(n_components):
        start = i * n_component_params
        end = start + n_component_params
        components.append({
            'type': component_type,
            'param_names': list(params_info[start:end]),
            'params': [float(v) for v in popt[start:end]],
        })

    return {
        'popt': popt,
        'pcov': pcov,
        'perr': perr,
        'param_names': params_info,
        'fit_func': fit_func,
        'x_fit': x_fit,
        'y_fit': y_fit,
        'r_squared': r_squared,
        'residuals': residuals,
        'x_data_used': x_data,
        'y_data_used': y_data,
        'component_type': component_type,
        'n_components': n_components,
        'baseline_type': baseline_type,
        'components': components,
    }


def fit_curve_task(x_data: Any, y_data: Any, fit_type: str, custom_formula: str | None = None, sigma: Any = None,
                   x_range: tuple[float, float] | None = None, p0_overrides: dict[str, float] | None = None,
                   fixed_params: dict[str, float] | None = None,
                   bounds: dict[str, tuple[float, float]] | None = None, loss: str = 'linear',
                   report_progress: Callable[..., Any] | None = None,
                   is_cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """TaskRunner 用。curve_fit は進捗も中断もできないので、report_progress と is_cancelled は受け取るだけ。"""
    return calculate_curve_fit(
        x_data, y_data, fit_type, custom_formula=custom_formula, sigma=sigma, x_range=x_range,
        p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds, loss=loss,
    )


def multi_peak_fit_task(x_data: Any, y_data: Any, component_type: str, initial_guesses: list[dict[str, float]],
                        baseline_type: str = 'constant', x_range: tuple[float, float] | None = None,
                        sigma: Any = None, p0_overrides: dict[str, float] | None = None,
                        fixed_params: dict[str, float] | None = None,
                        bounds: dict[str, tuple[float, float]] | None = None,
                        report_progress: Callable[..., Any] | None = None,
                        is_cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """TaskRunner 用。fit_curve_task() と同じく進捗と中断は受け取るだけ。"""
    return calculate_multi_peak_fit(
        x_data, y_data, component_type, initial_guesses, baseline_type=baseline_type,
        x_range=x_range, sigma=sigma, p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds,
    )


_INTEGRAL_METHODS = ("trapezoid", "simpson")


def _trapezoid_integrate(y: Any, x: Any) -> float:
    """NumPy 2.0 で trapz が trapezoid になった。古い版でも動くようにする。"""
    trapezoid_func = getattr(np, "trapezoid", None)
    if trapezoid_func is None:
        trapezoid_func = np.trapz
    return float(trapezoid_func(y, x))


def calculate_interval_integral(x_data: Any, y_data: Any, x_range: tuple[float, float], method: str = "trapezoid",
                                subtract_baseline: bool = False) -> dict[str, Any]:
    """x_range(両端を含む)で y を x について積分する。

    subtract_baseline は範囲の両端を結ぶ直線を引いてから積分する。両端の Y は、その X 位置で補間した値。
    """
    if method not in _INTEGRAL_METHODS:
        raise ValueError(f"未知の積分方法です: {method}")
    if x_range is None or len(x_range) != 2:
        raise ValueError("積分範囲(x_range)を指定してください。")

    x_min, x_max = float(x_range[0]), float(x_range[1])
    if x_min >= x_max:
        raise ValueError("積分範囲の最小値は最大値より小さい値である必要があります。")

    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)

    # NaN があると積分値が nan になる
    nan_mask = np.isnan(x_data) | np.isnan(y_data)
    if nan_mask.any():
        x_data, y_data = x_data[~nan_mask], y_data[~nan_mask]

    if len(x_data) == 0:
        raise ValueError("有効なデータ点がありません(すべて欠損値です)。積分できません。")

    # trapezoid / simpson は X が単調増加であることを前提にする
    order = np.argsort(x_data)
    x_sorted, y_sorted = x_data[order], y_data[order]

    x_min_data, x_max_data = float(x_sorted[0]), float(x_sorted[-1])
    if x_min < x_min_data or x_max > x_max_data:
        raise ValueError(
            f"積分範囲はデータのX範囲({x_min_data:.6g} 〜 {x_max_data:.6g})内で指定してください。"
        )

    range_mask = (x_sorted >= x_min) & (x_sorted <= x_max)
    x_in, y_in = x_sorted[range_mask], y_sorted[range_mask]

    if len(x_in) < 2:
        raise ValueError(f"積分範囲内に十分なデータ点がありません(最低2点必要、現在{len(x_in)}点)。")

    baseline_used = None
    y_for_integration = y_in
    if subtract_baseline:
        y_at_min = float(np.interp(x_min, x_sorted, y_sorted))
        y_at_max = float(np.interp(x_max, x_sorted, y_sorted))
        baseline_used = y_at_min + (y_at_max - y_at_min) * (x_in - x_min) / (x_max - x_min)
        y_for_integration = y_in - baseline_used

    if method == "trapezoid":
        integral = _trapezoid_integrate(y_for_integration, x_in)
    else:
        integral = float(simpson(y_for_integration, x=x_in))

    return {
        'integral': integral,
        'method': method,
        'x_range': (x_min, x_max),
        'subtract_baseline': subtract_baseline,
        'x_used': x_in,
        'y_used': y_for_integration,
        'y_raw_used': y_in,
        'baseline_used': baseline_used,
        'n_points': len(x_in),
    }


def calculate_cumulative_integral(x_data: Any, y_data: Any, method: str = "trapezoid") -> dict[str, Any]:
    """各点までの累積積分 ∫[x_min, x_i] y dx を返す(先頭は 0)。"""
    if method not in _INTEGRAL_METHODS:
        raise ValueError(f"未知の積分方法です: {method}")

    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)

    nan_mask = np.isnan(x_data) | np.isnan(y_data)
    if nan_mask.any():
        x_data, y_data = x_data[~nan_mask], y_data[~nan_mask]

    if len(x_data) < 2:
        raise ValueError("有効なデータ点が不足しています(最低2点必要です)。")

    order = np.argsort(x_data)
    x_sorted, y_sorted = x_data[order], y_data[order]

    if method == "trapezoid":
        y_cumulative = cumulative_trapezoid(y_sorted, x_sorted, initial=0.0)
    else:
        y_cumulative = cumulative_simpson(y_sorted, x=x_sorted, initial=0.0)

    return {
        'x_used': x_sorted,
        'y_cumulative': y_cumulative,
        'method': method,
        'n_points': len(x_sorted),
    }


def _peak_detection_signal_and_kwargs(x_data: Any, y_data: Any, peak_type: str,
                                      settings: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    """calculate_peaks と calculate_peak_quantification の共通の前処理。

    谷は -y_data で探すので height も符号を反転する(利用者は谷でも「Y < -10」を -10 と入力する)。
    height=None は高さで絞らない。
    """
    y_data_to_find = y_data
    height = settings["height"]

    if "下に凸" in peak_type:
        y_data_to_find = -y_data
        if height is not None:
            height = -height

    kwargs = {"height": height}

    if settings["prominence"] is not None:
        kwargs["prominence"] = settings["prominence"]

    if len(x_data) > 1 and settings["distance_x"] > 0:
        sorted_x = np.sort(x_data)
        avg_x_diff = np.mean(np.diff(sorted_x))
        if avg_x_diff > 0:
            kwargs["distance"] = max(1, int(np.ceil(settings["distance_x"] / avg_x_diff)))
        else:
            kwargs["distance"] = 1
    else:
        kwargs["distance"] = 1

    return y_data_to_find, kwargs


def calculate_peaks(x_data: Any, y_data: Any, peak_type: str, settings: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    y_data_to_find, kwargs = _peak_detection_signal_and_kwargs(x_data, y_data, peak_type, settings)

    peak_indices, _ = find_peaks(y_data_to_find, **kwargs)

    if len(peak_indices) == 0:
        return np.array([]), np.array([])

    return x_data[peak_indices], y_data[peak_indices]


def calculate_peak_quantification(x_data: Any, y_data: Any, peak_type: str, settings: dict[str, Any]) -> dict[str, Any]:
    """ピーク/谷の位置に加え、FWHM・面積・重心を返す。

    谷は反転した信号の上で計算するので、面積は谷でも正の値(検出方向への突出量)になる。
    ローカル基線は peak_widths(rel_height=1.0) の左右の裾を結ぶ直線(裾の高さが違う
    非対称なピークでも面積と重心が定まる)。重心の重みは生の Y ではなく基線からの高さ
    (大きなオフセットの上のピークで重心が引っ張られない)。x_data の並びがそのまま
    ピークの前後関係になるので、ソートは呼び出し側で行う。
    """
    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)

    y_signal, kwargs = _peak_detection_signal_and_kwargs(x_data, y_data, peak_type, settings)
    peak_indices, _ = find_peaks(y_signal, **kwargs)

    empty = np.array([])
    if len(peak_indices) == 0:
        return {'peak_x': empty, 'peak_y': empty, 'fwhm': empty, 'area': empty, 'centroid': empty}

    idx_axis = np.arange(len(x_data))

    # 幅はインデックス単位で出るので、x_data に補間して X の単位にする(等間隔でなくてよい)
    _, _, left_ips_half, right_ips_half = peak_widths(y_signal, peak_indices, rel_height=0.5)
    x_left_half = np.interp(left_ips_half, idx_axis, x_data)
    x_right_half = np.interp(right_ips_half, idx_axis, x_data)
    fwhm = x_right_half - x_left_half

    # rel_height=1.0 は prominence を測った高さでの幅、つまりピークの裾
    _, _, left_ips_full, right_ips_full = peak_widths(y_signal, peak_indices, rel_height=1.0)

    area = np.empty(len(peak_indices))
    centroid = np.empty(len(peak_indices))

    for i, pk in enumerate(peak_indices):
        li, ri = left_ips_full[i], right_ips_full[i]

        x_left = np.interp(li, idx_axis, x_data)
        x_right = np.interp(ri, idx_axis, x_data)
        y_left = np.interp(li, idx_axis, y_signal)
        y_right = np.interp(ri, idx_axis, y_signal)

        li_idx, ri_idx = int(np.floor(li)), int(np.ceil(ri))
        inner_idx = np.arange(max(li_idx, 0), min(ri_idx, len(x_data) - 1) + 1)
        xs_inner, ys_inner = x_data[inner_idx], y_signal[inner_idx]
        inner_mask = (xs_inner >= x_left) & (xs_inner <= x_right)
        xs_inner, ys_inner = xs_inner[inner_mask], ys_inner[inner_mask]

        xs = np.concatenate(([x_left], xs_inner, [x_right]))
        ys = np.concatenate(([y_left], ys_inner, [y_right]))
        xs, unique_order = np.unique(xs, return_index=True)
        ys = ys[unique_order]

        baseline = np.interp(xs, [x_left, x_right], [y_left, y_right])
        y_above = ys - baseline

        area[i] = np.trapezoid(y_above, xs)

        weights = np.clip(y_above, 0, None)
        total_weight = np.sum(weights)
        if total_weight > 0:
            centroid[i] = np.sum(xs * weights) / total_weight
        else:
            centroid[i] = x_data[pk]

    return {
        'peak_x': x_data[peak_indices],
        'peak_y': y_data[peak_indices],
        'fwhm': fwhm,
        'area': area,
        'centroid': centroid,
    }


def calculate_savgol(x_data: Any, y_data: Any, window_length: int, polyorder: int,
                     deriv: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Savitzky-Golay による平滑化(deriv=0)または微分(deriv=1, 2)。

    delta に X の間隔の中央値を渡すので、微分は dy/dx の大きさになる(X がほぼ等間隔である前提)。
    """
    if window_length % 2 == 0:
        raise ValueError("窓幅(window_length)は奇数である必要があります。")
    if polyorder >= window_length:
        raise ValueError("多項式の次数は窓幅より小さくする必要があります。")
    if window_length > len(y_data):
        raise ValueError(f"窓幅({window_length})がデータ点数({len(y_data)})を超えています。")

    order = np.argsort(x_data)
    x_sorted, y_sorted = x_data[order], y_data[order]
    diffs = np.diff(x_sorted)
    dx = float(np.median(diffs)) if len(diffs) > 0 and np.median(diffs) > 0 else 1.0

    y_result = savgol_filter(y_sorted, window_length, polyorder, deriv=deriv, delta=dx)
    return x_sorted, y_result


# 線の平滑化(Dataset.smoothing_method)。描画用で元データは変えない。
# どれも X でソートして実データ点のまま返す(CubicSpline と違い点を補間で増やさない)。

def calculate_moving_average_smooth(x_data: Any, y_data: Any, window: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """window は点数。データ点数を超えたら切り詰める。端は端の値を延長する。"""
    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)
    order = np.argsort(x_data)
    x_sorted, y_sorted = x_data[order], y_data[order]

    n = len(y_sorted)
    w = max(1, min(int(window), n)) if n > 0 else 1
    if w <= 1:
        return x_sorted, y_sorted.copy()
    return x_sorted, uniform_filter1d(y_sorted, size=w, mode='nearest')


def calculate_median_smooth(x_data: Any, y_data: Any, window: int = 5) -> tuple[np.ndarray, np.ndarray]:
    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)
    order = np.argsort(x_data)
    x_sorted, y_sorted = x_data[order], y_data[order]

    n = len(y_sorted)
    w = max(1, min(int(window), n)) if n > 0 else 1
    if w <= 1:
        return x_sorted, y_sorted.copy()
    return x_sorted, median_filter(y_sorted, size=w, mode='nearest')


def calculate_gaussian_smooth(x_data: Any, y_data: Any, sigma: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """sigma はデータ点のインデックス単位(X の間隔ではない)。"""
    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)
    order = np.argsort(x_data)
    x_sorted, y_sorted = x_data[order], y_data[order]

    if len(y_sorted) < 2 or sigma <= 0:
        return x_sorted, y_sorted.copy()
    return x_sorted, gaussian_filter1d(y_sorted, sigma=float(sigma), mode='nearest')


# ベースライン補正。どの手法も (ソート済みの x, ベースライン, 差し引いた y) を返す。

def _sort_xy_for_baseline(x_data: Any, y_data: Any) -> tuple[np.ndarray, np.ndarray]:
    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)
    order = np.argsort(x_data)
    return x_data[order], y_data[order]


def calculate_baseline_als(x_data: Any, y_data: Any, lam: float = 1e5, p: float = 0.01,
                           niter: int = 10) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Asymmetric Least Squares (Eilers & Boelens 2005)。

    lam が大きいほど滑らか、p が小さいほどピークを避けて下側を通る(目安 0.001〜0.1)。
    """
    if lam <= 0:
        raise ValueError("lam(平滑化パラメータ)は正の値である必要があります。")
    if not (0 < p < 1):
        raise ValueError("p(非対称重み)は0より大きく1より小さい値である必要があります。")
    if niter < 1:
        raise ValueError("反復回数(niter)は1以上である必要があります。")

    x_sorted, y_sorted = _sort_xy_for_baseline(x_data, y_data)
    n_points = len(y_sorted)
    if n_points < 3:
        raise ValueError(f"ALSベースライン補正には少なくとも3点のデータが必要です(現在{n_points}点)。")

    # 2階差分の二乗和へのペナルティ
    diff_matrix = sparse.diags([1, -2, 1], [0, -1, -2], shape=(n_points, n_points - 2))
    penalty = lam * (diff_matrix @ diff_matrix.transpose())

    weights = np.ones(n_points)
    baseline = y_sorted.copy()
    for _ in range(niter):
        weight_matrix = sparse.diags(weights, 0, shape=(n_points, n_points))
        baseline = spsolve((weight_matrix + penalty).tocsc(), weights * y_sorted)
        weights = p * (y_sorted > baseline) + (1 - p) * (y_sorted <= baseline)

    return x_sorted, baseline, y_sorted - baseline


def calculate_baseline_polynomial(x_data: Any, y_data: Any, degree: int = 3,
                                  iterations: int = 10) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """反復多項式フィット(Lieber & Mahadevan-Jansen 2003 の ModPoly)。

    フィット曲線を上回る点をフィット値で置き換えて再フィットし、ピークを少しずつ削る。
    """
    if degree < 0:
        raise ValueError("多項式の次数は0以上である必要があります。")
    if iterations < 1:
        raise ValueError("反復回数(iterations)は1以上である必要があります。")

    x_sorted, y_sorted = _sort_xy_for_baseline(x_data, y_data)
    if degree >= len(y_sorted):
        raise ValueError(f"多項式の次数({degree})がデータ点数({len(y_sorted)})以上です。")

    work_y = y_sorted.copy()
    baseline = work_y
    for _ in range(iterations):
        coeffs = np.polyfit(x_sorted, work_y, degree)
        baseline = np.polyval(coeffs, x_sorted)
        work_y = np.minimum(work_y, baseline)

    return x_sorted, baseline, y_sorted - baseline


def calculate_baseline_rubberband(x_data: Any, y_data: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ラバーバンド法。下側凸包の頂点を区分線形でつないだものをベースラインにする。"""
    x_sorted, y_sorted = _sort_xy_for_baseline(x_data, y_data)
    n_points = len(x_sorted)
    if n_points < 3:
        raise ValueError(f"ラバーバンド法には少なくとも3点のデータが必要です(現在{n_points}点)。")

    # Andrew の monotone chain の下側だけ
    hull_indices: list[int] = []
    for i in range(n_points):
        while len(hull_indices) >= 2:
            o, a = hull_indices[-2], hull_indices[-1]
            cross = ((x_sorted[a] - x_sorted[o]) * (y_sorted[i] - y_sorted[o])
                     - (y_sorted[a] - y_sorted[o]) * (x_sorted[i] - x_sorted[o]))
            if cross <= 0:
                hull_indices.pop()
            else:
                break
        hull_indices.append(i)

    x_hull = x_sorted[hull_indices]
    y_hull = y_sorted[hull_indices]
    baseline = np.interp(x_sorted, x_hull, y_hull)

    return x_sorted, baseline, y_sorted - baseline


def calculate_baseline_manual(x_data: Any, y_data: Any, anchor_x: Any,
                              method: str = "linear") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """指定した X 位置でデータを補間した点を、線形("linear")か 3 次スプライン("spline")で結ぶ。"""
    if method not in ("linear", "spline"):
        raise ValueError(f"未知の補間方法です: {method}")

    x_sorted, y_sorted = _sort_xy_for_baseline(x_data, y_data)

    anchor_x = np.unique(np.asarray(anchor_x, dtype=float))
    if len(anchor_x) < 2:
        raise ValueError("アンカー点は重複しない値で2点以上指定してください。")
    if method == "spline" and len(anchor_x) < 3:
        raise ValueError("スプライン補間には3点以上のアンカー点が必要です。")

    x_min, x_max = x_sorted[0], x_sorted[-1]
    if anchor_x[0] < x_min or anchor_x[-1] > x_max:
        raise ValueError(
            f"アンカー点はデータのX範囲({x_min:.6g} 〜 {x_max:.6g})内で指定してください。"
        )

    anchor_y = np.interp(anchor_x, x_sorted, y_sorted)

    if method == "linear":
        baseline = np.interp(x_sorted, anchor_x, anchor_y)
    else:
        baseline = CubicSpline(anchor_x, anchor_y)(x_sorted)

    return x_sorted, baseline, y_sorted - baseline


def calculate_confidence_band(x_eval: Any, fit_func: Callable[..., Any], popt: Any, pcov: Any, residuals: Any,
                              confidence: float = 0.95, band_type: str = "confidence") -> dict[str, Any]:
    """非線形回帰の信頼帯・予測帯をデルタ法(線形化)で近似する。

    各点で J(x) @ pcov @ J(x).T を分散とする。予測帯はさらに残差の平均二乗誤差を足す。
    固定パラメータは pcov の行と列が 0 なので不確かさに寄与しない。
    """
    if band_type not in ("confidence", "prediction"):
        raise ValueError(f"未知のband_typeです: {band_type}")
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence(信頼水準)は0より大きく1より小さい値である必要があります。")

    x_eval = np.asarray(x_eval, dtype=float)
    popt = np.asarray(popt, dtype=float)
    pcov = np.asarray(pcov, dtype=float)
    residuals = np.asarray(residuals, dtype=float)

    n_params = len(popt)
    n_data = len(residuals)
    dof = n_data - n_params
    if dof < 1:
        raise ValueError(
            f"自由度(データ点数{n_data} - パラメータ数{n_params})が1未満のため、"
            "信頼帯・予測帯を計算できません。"
        )

    from scipy.stats import t as _t_dist
    t_value = _t_dist.ppf(1.0 - (1.0 - confidence) / 2.0, dof)

    y_center = fit_func(x_eval, *popt)
    jacobian = np.empty((len(x_eval), n_params))
    for i in range(n_params):
        # 刻みはパラメータの大きさに比例させる(極端な値でも数値誤差が出にくい)
        step = max(abs(popt[i]), 1.0) * 1e-6
        popt_plus, popt_minus = popt.copy(), popt.copy()
        popt_plus[i] += step
        popt_minus[i] -= step
        jacobian[:, i] = (fit_func(x_eval, *popt_plus) - fit_func(x_eval, *popt_minus)) / (2 * step)

    # diag(J @ pcov @ J.T) だけを求める
    var_yhat = np.einsum('ij,jk,ik->i', jacobian, pcov, jacobian)
    # 数値誤差でわずかに負になることがある
    var_yhat = np.clip(var_yhat, 0.0, None)

    if band_type == "prediction":
        mse = np.sum(residuals ** 2) / dof
        variance = var_yhat + mse
    else:
        variance = var_yhat

    margin = t_value * np.sqrt(variance)

    return {
        'y_center': y_center,
        'y_lower': y_center - margin,
        'y_upper': y_center + margin,
        'confidence': confidence,
        'band_type': band_type,
    }


def calculate_resample_to_grid(x_data: Any, y_data: Any, target_x: Any, method: str = "linear",
                               extrapolate: bool = False) -> np.ndarray:
    """(x_data, y_data) を target_x の格子に補間する。

    extrapolate=False(既定)は元の X の範囲外を NaN にする。True のとき "linear" は両端の傾きで
    外挿する(np.interp は端の値で止めるだけで外挿しない)。
    """
    if method not in ("linear", "cubic"):
        raise ValueError(f"未知の補間方法です: {method}")

    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)
    target_x = np.asarray(target_x, dtype=float)

    nan_mask = np.isnan(x_data) | np.isnan(y_data)
    if nan_mask.any():
        x_data, y_data = x_data[~nan_mask], y_data[~nan_mask]

    if len(x_data) == 0:
        raise ValueError("有効なデータ点がありません(すべて欠損値です)。リサンプリングできません。")

    order = np.argsort(x_data)
    x_sorted, y_sorted = x_data[order], y_data[order]
    # 補間は X が厳密に単調増加であることを要求するので、同じ X は最後の値を残してまとめる。
    # np.unique は最初の出現を返すので、反転してから除く。
    x_rev, y_rev = x_sorted[::-1], y_sorted[::-1]
    x_sorted, rev_unique_indices = np.unique(x_rev, return_index=True)
    y_sorted = y_rev[rev_unique_indices]

    n_points = len(x_sorted)
    if method == "linear" and n_points < 2:
        raise ValueError(f"線形補間には少なくとも2点のデータが必要です(現在{n_points}点)。")
    if method == "cubic" and n_points < 4:
        raise ValueError(f"3次スプライン補間には少なくとも4点のデータが必要です(現在{n_points}点)。")

    x_min, x_max = x_sorted[0], x_sorted[-1]

    if method == "linear":
        if extrapolate:
            # np.interp は範囲外を端の値で止めるだけなので、両端の傾きで外挿する
            result = np.interp(target_x, x_sorted, y_sorted)
            below = target_x < x_min
            if below.any():
                slope = (y_sorted[1] - y_sorted[0]) / (x_sorted[1] - x_sorted[0])
                result[below] = y_sorted[0] + slope * (target_x[below] - x_min)
            above = target_x > x_max
            if above.any():
                slope = (y_sorted[-1] - y_sorted[-2]) / (x_sorted[-1] - x_sorted[-2])
                result[above] = y_sorted[-1] + slope * (target_x[above] - x_max)
        else:
            result = np.interp(target_x, x_sorted, y_sorted)
            out_of_range = (target_x < x_min) | (target_x > x_max)
            result = result.astype(float)
            result[out_of_range] = np.nan
    else:
        spline = CubicSpline(x_sorted, y_sorted, extrapolate=extrapolate)
        result = spline(target_x)
        if not extrapolate:
            out_of_range = (target_x < x_min) | (target_x > x_max)
            result = np.asarray(result, dtype=float)
            result[out_of_range] = np.nan

    return result


def calculate_average_duplicate_x(x_data: Any, y_data: Any) -> dict[str, Any]:
    """同じ X の行の Y を平均する。重複の「除去」は index ラベルが要るので呼び出し側で行う。"""
    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)

    nan_mask = np.isnan(x_data) | np.isnan(y_data)
    if nan_mask.any():
        x_data, y_data = x_data[~nan_mask], y_data[~nan_mask]

    if len(x_data) == 0:
        raise ValueError("有効なデータ点がありません(すべて欠損値です)。")

    order = np.argsort(x_data, kind='stable')
    x_sorted, y_sorted = x_data[order], y_data[order]

    unique_x, inverse, counts = np.unique(x_sorted, return_inverse=True, return_counts=True)
    # NumPy の版によって inverse の形が (N,) か (N, 1) になる
    inverse = np.asarray(inverse).reshape(-1)
    sums = np.zeros(len(unique_x))
    np.add.at(sums, inverse, y_sorted)
    y_averaged = sums / counts

    return {
        'x_used': unique_x,
        'y_averaged': y_averaged,
        'group_sizes': counts,
        'n_duplicate_groups': int(np.sum(counts > 1)),
        'n_points_in': len(x_sorted),
        'n_points_out': len(unique_x),
    }


# 外れ値の検出。マスクへの適用は利用者が選ぶので、ここでは検出だけ。
# is_outlier は入力と同じ長さと並び(NaN は False)。visible_df.index[is_outlier] でそのまま引けるように。

def sample_standard_deviation(values: Any) -> float:
    """標本標準偏差(n−1 で割る)。有効な値が 2 未満なら NaN。

    アプリ内の「標準偏差」はすべてこれで計算する。場所によって n と n−1 が混ざると同じデータで値が違って見える。
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size < 2:
        return float('nan')
    return float(np.std(arr, ddof=1))


def calculate_zscore_outliers(y_data: Any, threshold: float = 3.0) -> dict[str, Any]:
    if threshold <= 0:
        raise ValueError("しきい値は正の値である必要があります。")

    y = np.asarray(y_data, dtype=float)
    is_outlier = np.zeros(len(y), dtype=bool)
    z_scores = np.full(len(y), np.nan)
    valid = ~np.isnan(y)

    if valid.sum() >= 2:
        mean = np.mean(y[valid])
        std = sample_standard_deviation(y[valid])
        if std > 0:
            z_scores[valid] = (y[valid] - mean) / std
            is_outlier[valid] = np.abs(z_scores[valid]) > threshold

    return {
        'is_outlier': is_outlier,
        'z_scores': z_scores,
        'threshold': threshold,
        'n_outliers': int(np.sum(is_outlier)),
    }


def calculate_iqr_outliers(y_data: Any, multiplier: float = 1.5) -> dict[str, Any]:
    """[Q1 - multiplier*IQR, Q3 + multiplier*IQR] の外を外れ値とする。"""
    if multiplier <= 0:
        raise ValueError("係数は正の値である必要があります。")

    y = np.asarray(y_data, dtype=float)
    is_outlier = np.zeros(len(y), dtype=bool)
    valid = ~np.isnan(y)
    lower_bound = upper_bound = None

    if valid.sum() >= 4:
        q1, q3 = np.percentile(y[valid], [25, 75])
        iqr = q3 - q1
        lower_bound = float(q1 - multiplier * iqr)
        upper_bound = float(q3 + multiplier * iqr)
        is_outlier[valid] = (y[valid] < lower_bound) | (y[valid] > upper_bound)

    return {
        'is_outlier': is_outlier,
        'lower_bound': lower_bound,
        'upper_bound': upper_bound,
        'multiplier': multiplier,
        'n_outliers': int(np.sum(is_outlier)),
    }


def calculate_lttb_downsample(x_data: Any, y_data: Any, n_out: int) -> np.ndarray:
    """Largest-Triangle-Three-Buckets(Steinarsson 2013)による表示用の間引き。

    x_data はソート済みであること。選んだ点のインデックス(先頭と末尾を含む昇順)を返すので、
    同じインデックスを誤差などほかの配列にも使える。n_out 以下なら間引かない。
    """
    n = len(x_data)
    if n_out < 3 or n <= n_out:
        return np.arange(n)

    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)

    selected = np.empty(n_out, dtype=np.int64)
    selected[0] = 0
    selected[-1] = n - 1

    bucket_edges = np.linspace(1, n - 1, n_out - 1).astype(np.int64)
    a = 0
    for i in range(n_out - 2):
        bucket_start, bucket_end = bucket_edges[i], bucket_edges[i + 1]
        if bucket_end <= bucket_start:
            bucket_end = bucket_start + 1
        next_start = bucket_end
        next_end = bucket_edges[i + 2] if i + 2 < len(bucket_edges) else n
        if next_end <= next_start:
            next_end = min(next_start + 1, n)
        avg_x = np.mean(x_data[next_start:next_end])
        avg_y = np.mean(y_data[next_start:next_end])

        cand_x = x_data[bucket_start:bucket_end]
        cand_y = y_data[bucket_start:bucket_end]
        ax_, ay_ = x_data[a], y_data[a]
        areas = np.abs(
            (ax_ - avg_x) * (cand_y - ay_) - (ax_ - cand_x) * (avg_y - ay_)
        )
        best_local = np.argmax(areas)
        chosen = bucket_start + best_local
        selected[i + 1] = chosen
        a = chosen

    return selected


def calculate_histogram(data: Any, bins: Any = 'auto', density: bool = False) -> dict[str, Any]:
    """ビン中心と度数(density=True なら確率密度)を返す。"""
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    if len(data) == 0:
        raise ValueError("有効なデータ点がありません(すべて欠損値です)。")
    counts, bin_edges = np.histogram(data, bins=bins, density=density)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    return {
        'bin_centers': bin_centers,
        'bin_edges': bin_edges,
        'counts': counts,
        'n_points_used': len(data),
    }


def calculate_kde(data: Any, n_points: int = 200, bw_method: Any = None) -> dict[str, Any]:
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    if len(data) < 2:
        raise ValueError("カーネル密度推定には少なくとも2点の有効なデータが必要です。")
    try:
        kde = gaussian_kde(data, bw_method=bw_method)
        x_grid = np.linspace(data.min(), data.max(), n_points)
        density = kde(x_grid)
    except np.linalg.LinAlgError:
        raise ValueError("データにばらつきが無いため、カーネル密度推定を計算できません。") from None
    return {'x_grid': x_grid, 'density': density, 'n_points_used': len(data)}


def calculate_error_propagation(operation: str, value_a: Any, error_a: Any, value_b: Any, error_b: Any) -> np.ndarray:
    """独立な誤差を仮定した誤差伝播。

    除算は、分子がゼロのときに NaN にならないよう、比ではなく分母で割る形の式にしている。
    """
    a = np.asarray(value_a, dtype=float)
    ea = np.asarray(error_a, dtype=float)
    b = np.asarray(value_b, dtype=float)
    eb = np.asarray(error_b, dtype=float)

    if operation in ("A - B", "B - A", "A + B"):
        return np.sqrt(ea ** 2 + eb ** 2)
    if operation == "A × B":
        return np.sqrt((ea * b) ** 2 + (eb * a) ** 2)
    with np.errstate(divide='ignore', invalid='ignore'):
        if operation == "A ÷ B":
            return np.sqrt((ea / b) ** 2 + (a * eb / b ** 2) ** 2)
        else:
            return np.sqrt((eb / a) ** 2 + (b * ea / a ** 2) ** 2)


# 共通グリッドの点数の上限(大きいデータでフリーズしないため)
_XCORR_MAX_GRID_POINTS = 20000


def calculate_cross_correlation_alignment(x_a: Any, y_a: Any, x_b: Any, y_b: Any) -> dict[str, float]:
    """B を A に重ねるための X のシフト量(x_b + shift)を相互相関のピークから求める。

    両者の範囲全体を覆う等間隔グリッドに補間し(範囲外は 0)、平均を引いてから相関を取る。
    """
    x_a = np.asarray(x_a, dtype=float)
    y_a = np.asarray(y_a, dtype=float)
    x_b = np.asarray(x_b, dtype=float)
    y_b = np.asarray(y_b, dtype=float)

    valid_a = ~(np.isnan(x_a) | np.isnan(y_a))
    valid_b = ~(np.isnan(x_b) | np.isnan(y_b))
    x_a, y_a = x_a[valid_a], y_a[valid_a]
    x_b, y_b = x_b[valid_b], y_b[valid_b]
    if len(x_a) < 2 or len(x_b) < 2:
        raise ValueError("有効なデータ点が不足しています(それぞれ最低2点必要です)。")

    order_a = np.argsort(x_a)
    x_a, y_a = x_a[order_a], y_a[order_a]
    order_b = np.argsort(x_b)
    x_b, y_b = x_b[order_b], y_b[order_b]

    step_a = np.median(np.diff(x_a))
    step_b = np.median(np.diff(x_b))
    candidates = [s for s in (step_a, step_b) if s and s > 0]
    if not candidates:
        raise ValueError("X間隔を推定できません(Xの値が一定、または重複しています)。")
    step = min(candidates)

    lo = min(x_a.min(), x_b.min())
    hi = max(x_a.max(), x_b.max())
    n_points = int(np.ceil((hi - lo) / step)) + 1
    if n_points > _XCORR_MAX_GRID_POINTS:
        step = (hi - lo) / _XCORR_MAX_GRID_POINTS
        n_points = _XCORR_MAX_GRID_POINTS + 1
    grid = np.linspace(lo, hi, n_points)

    # 範囲外を含む全体で平均を引くので中心化は厳密でないが、ピーク位置を探すには足りる
    sig_a = np.interp(grid, x_a, y_a, left=0.0, right=0.0)
    sig_b = np.interp(grid, x_b, y_b, left=0.0, right=0.0)
    sig_a = sig_a - sig_a.mean()
    sig_b = sig_b - sig_b.mean()

    corr = correlate(sig_a, sig_b, mode='full')
    lags = correlation_lags(len(sig_a), len(sig_b), mode='full')
    best_idx = int(np.argmax(corr))
    shift = float(lags[best_idx] * step)

    return {'shift': shift, 'grid_step': float(step), 'correlation_peak': float(corr[best_idx])}


def assign_peak_label_levels(peak_x_values: Any, x_axis_span: float, proximity_ratio: float = 0.05,
                             max_levels: int = 4) -> list[int]:
    """X が近いピークのラベルに互い違いの段番号を割り当てる(ずらす量は呼び出し側で決める)。"""
    peak_x_values = list(peak_x_values)
    if x_axis_span <= 0 or not peak_x_values:
        return [0] * len(peak_x_values)

    threshold = x_axis_span * proximity_ratio
    levels = []
    prev_x = None
    current_level = 0
    for x in peak_x_values:
        if prev_x is not None and abs(x - prev_x) < threshold:
            current_level = (current_level + 1) % max_levels
        else:
            current_level = 0
        levels.append(current_level)
        prev_x = x
    return levels


def split_dataframe_by_column(df: Any, split_col: str) -> dict[str, Any]:
    """区分列の値ごとに DataFrame を分ける(long 形式のデータ)。

    グループはファイル中の初出順(測定順などの並びに意味があることが多い)。
    区分列が NaN の行は除き、その数を n_dropped で返す。各グループの index は 0 から振り直す。
    """
    if split_col not in df.columns:
        raise ValueError(f"列 '{split_col}' がデータに存在しません。")

    values = df[split_col]
    keep = values.notna()
    n_dropped = int((~keep).sum())
    filtered = df[keep]

    groups = []
    for label, sub_df in filtered.groupby(split_col, sort=False, observed=True):
        groups.append((_format_group_label(label), sub_df.reset_index(drop=True)))

    return {'groups': groups, 'n_dropped': n_dropped, 'n_groups': len(groups)}


def _format_group_label(value: Any) -> str:
    """numpy のスカラは str() すると 'np.float64(1.5)' になるので、Python の型にしてから文字列にする。"""
    if hasattr(value, 'item'):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
