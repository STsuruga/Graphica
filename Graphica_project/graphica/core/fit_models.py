"""曲線フィットのモデルの表。種類の判定・パラメータ名・関数・初期値の推定をここ 1 か所に持つ。

種類は表示名(例「ガウシアン (y = …)」)で渡され、保存ファイルと方法の文章にもそのまま入る。判定は語の部分一致で、
表の順に見る(「2成分指数」を「指数関数」より、「擬似フォークト」を「フォークト」より、「ボルツマン」を
「シグモイド」より先に)。カスタム数式が最初、プラグインの関数(名前の完全一致)が最後。
初期値の式は結果の popt が 1 ビットも変わらないよう、演算の順まで変えないこと。
"""
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import numpy as np
from scipy.special import wofz

from graphica.core.safe_eval import DEFAULT_FUNCTIONS, safe_eval_formula

CUSTOM_FORMULA_KEYWORD = "カスタム数式"
CUSTOM_FORMULA_LABEL = "カスタム数式..."


def is_custom_formula_type(fit_type: str) -> bool:
    return CUSTOM_FORMULA_KEYWORD in fit_type


def _linear(x: Any, a: float, b: float) -> Any:
    return a * x + b


def _poly2(x: Any, a: float, b: float, c: float) -> Any:
    return a * x**2 + b * x + c


def _poly3(x: Any, a: float, b: float, c: float, d: float) -> Any:
    return a * x**3 + b * x**2 + c * x + d


def _exponential(x: Any, a: float, b: float) -> Any:
    return a * np.exp(b * x)


def _logarithmic(x: Any, a: float, b: float) -> Any:
    return a * np.log(x) + b


def _power(x: Any, a: float, b: float) -> Any:
    return a * np.power(x, b)


def _gaussian(x: Any, a: float, b: float, c: float, d: float) -> Any:
    return a * np.exp(-((x - b) ** 2) / (2 * c ** 2)) + d


def _sigmoid(x: Any, a: float, b: float, c: float) -> Any:
    return a / (1 + np.exp(-b * (x - c)))


def _two_exponentials(x: Any, a1: float, b1: float, a2: float, b2: float, c: float) -> Any:
    return a1 * np.exp(b1 * x) + a2 * np.exp(b2 * x) + c


def _lorentzian(x: Any, a: float, b: float, c: float, d: float) -> Any:
    return a / (1 + ((x - b) / c) ** 2) + d


def _pseudo_voigt(x: Any, a: float, b: float, c: float, eta: float, d: float) -> Any:
    # 共通の中心 b と FWHM c を持つローレンツ型とガウス型を eta で混ぜる
    lorentzian_shape = 1 / (1 + ((x - b) / c) ** 2)
    gaussian_shape = np.exp(-4 * np.log(2) * ((x - b) / c) ** 2)
    return a * (eta * lorentzian_shape + (1 - eta) * gaussian_shape) + d


def _voigt(x: Any, a: float, b: float, sigma: float, gamma: float, d: float) -> Any:
    # Faddeeva 関数による Voigt。この正規化で gamma→0 のとき a がピーク高さになる
    z = ((x - b) + 1j * gamma) / (sigma * np.sqrt(2))
    return a * np.real(wofz(z)) / (sigma * np.sqrt(2 * np.pi)) + d


def _boltzmann_sigmoid(x: Any, a1: float, a2: float, x0: float, dx: float) -> Any:
    return a2 + (a1 - a2) / (1 + np.exp((x - x0) / dx))


def _hill(x: Any, vmax: float, k: float, n: float) -> Any:
    return (vmax * np.power(x, n)) / (np.power(k, n) + np.power(x, n))


def _estimate_fwhm(x_arr: Any, y_arr: Any, amplitude: float) -> float:
    """半値を横切る X の幅を FWHM の粗い推定にする(裾の広い形で誤った局所解に落ちないため)。"""
    half_level = np.nanmin(y_arr) + amplitude / 2
    above_half = x_arr[y_arr >= half_level]
    if len(above_half) == 0:
        return (np.nanmax(x_arr) - np.nanmin(x_arr)) / 4 or 1.0
    return (above_half.max() - above_half.min()) or 1.0


def _p0_linear(x: Any, y: Any) -> list[Any]:
    return [1.0, 0.0]


def _p0_poly2(x: Any, y: Any) -> list[Any]:
    return [1.0, 1.0, 0.0]


def _p0_poly3(x: Any, y: Any) -> list[Any]:
    return [1.0, 1.0, 1.0, 0.0]


def _p0_two_exponentials(x: Any, y: Any) -> list[Any]:
    amplitude = (np.nanmax(y) - np.nanmin(y)) / 2 or 1.0
    x_span = (np.nanmax(x) - np.nanmin(x)) or 1.0
    # 2成分が同じ初期値だと縮退して収束しないので、符号の違う率から始める
    rate0 = 2.0 / x_span
    return [amplitude, rate0, amplitude, -rate0, np.nanmin(y)]


def _p0_exponential(x: Any, y: Any) -> list[Any]:
    amplitude = np.nanmean(np.abs(y)) or 1.0
    return [amplitude, 0.01]


def _p0_logarithmic(x: Any, y: Any) -> list[Any]:
    return [1.0, 0.0]


def _p0_power(x: Any, y: Any) -> list[Any]:
    return [1.0, 1.0]


def _peak_amplitude_and_center(x: Any, y: Any) -> tuple[Any, Any]:
    amplitude = (np.nanmax(y) - np.nanmin(y)) or 1.0
    center = x[np.nanargmax(y)] if len(x) else 0.0
    return amplitude, center


def _p0_gaussian(x: Any, y: Any) -> list[Any]:
    amplitude, center = _peak_amplitude_and_center(x, y)
    width = (np.nanmax(x) - np.nanmin(x)) / 4 or 1.0
    return [amplitude, center, width, np.nanmin(y)]


def _p0_lorentzian(x: Any, y: Any) -> list[Any]:
    amplitude, center = _peak_amplitude_and_center(x, y)
    # c は HWHM なので FWHM の半分
    fwhm0 = _estimate_fwhm(x, y, amplitude)
    return [amplitude, center, fwhm0 / 2, np.nanmin(y)]


def _p0_pseudo_voigt(x: Any, y: Any) -> list[Any]:
    amplitude, center = _peak_amplitude_and_center(x, y)
    # この定義の c は FWHM そのもの
    fwhm0 = _estimate_fwhm(x, y, amplitude)
    return [amplitude, center, fwhm0, 0.5, np.nanmin(y)]


def _p0_voigt(x: Any, y: Any) -> list[Any]:
    amplitude, center = _peak_amplitude_and_center(x, y)
    fwhm0 = _estimate_fwhm(x, y, amplitude)
    # FWHM をガウス成分とローレンツ成分に大まかに割り振る経験的な初期値
    sigma0 = (fwhm0 / 2.355) or 1.0
    gamma0 = (fwhm0 / 4) or 1.0
    # _voigt の正規化に合わせ、ピーク高さが振幅に近くなるよう a をスケールする
    return [amplitude * sigma0 * np.sqrt(2 * np.pi), center, sigma0, gamma0, np.nanmin(y)]


def _p0_boltzmann_sigmoid(x: Any, y: Any) -> list[Any]:
    order = np.argsort(x)
    x_sorted, y_sorted = x[order], y[order]
    y_start = y_sorted[0]
    y_end = y_sorted[-1]
    mid_level = (y_start + y_end) / 2
    # 遷移の中心は Y の中点を最初に横切る X から推定する(X の平均だと局所解に落ちやすい)
    crossing_mask = y_sorted < mid_level if y_start >= y_end else y_sorted > mid_level
    crossing_indices = np.flatnonzero(crossing_mask)
    x0 = x_sorted[crossing_indices[0]] if len(crossing_indices) else np.nanmean(x)
    dx0 = (np.nanmax(x) - np.nanmin(x)) / 10 or 1.0
    return [y_start, y_end, x0, dx0]


def _p0_sigmoid(x: Any, y: Any) -> list[Any]:
    amplitude = np.nanmax(y) or 1.0
    return [amplitude, 1.0, np.nanmean(x)]


def _p0_hill(x: Any, y: Any) -> list[Any]:
    vmax0 = np.nanmax(y) or 1.0
    positive_x = x[x > 0]
    k0 = np.nanmedian(positive_x) if len(positive_x) else 1.0
    return [vmax0, k0, 1.0]


def _require_positive_x(message: str) -> Callable[[Any], None]:
    def check(x: Any) -> None:
        if np.any(x <= 0):
            raise ValueError(message)
    return check


def _require_non_negative_x(x: Any) -> None:
    if np.any(x < 0):
        raise ValueError("ヒル式は X >= 0 のデータにのみ使用できます。")


@dataclass(frozen=True)
class FitModel:
    keyword: str               # 種類の名前にこの語が含まれればこのモデル
    menu_label: str            # ダイアログの選択肢(= 保存される fit_type)
    param_names: tuple[str, ...]
    func: Callable[..., Any]
    initial_guess: Callable[[Any, Any], list[Any]]
    check_data: Callable[[Any], None] | None = None   # 使えないデータなら ValueError


# 判定の順。ダイアログの並びは MENU_ORDER。
BUILTIN_FIT_MODELS: tuple[FitModel, ...] = (
    FitModel("線形", "線形 (y = ax + b)", ("a", "b"), _linear, _p0_linear),
    FitModel("2次多項式", "2次多項式 (y = ax^2 + bx + c)", ("a", "b", "c"), _poly2, _p0_poly2),
    FitModel("3次多項式", "3次多項式 (y = ax^3 + bx^2 + cx + d)", ("a", "b", "c", "d"), _poly3, _p0_poly3),
    FitModel("2成分指数", "2成分指数関数 (y = a1*exp(b1*x) + a2*exp(b2*x) + c)", ("a1", "b1", "a2", "b2", "c"),
             _two_exponentials, _p0_two_exponentials),
    FitModel("指数関数", "指数関数 (y = a * exp(bx))", ("a", "b"), _exponential, _p0_exponential),
    FitModel("対数", "対数 (y = a * ln(x) + b)", ("a", "b"), _logarithmic, _p0_logarithmic,
             _require_positive_x("対数フィットは X > 0 のデータにのみ使用できます。")),
    FitModel("べき乗", "べき乗 (y = a * x^b)", ("a", "b"), _power, _p0_power,
             _require_positive_x("べき乗フィットは X > 0 のデータにのみ使用できます。")),
    FitModel("ガウシアン", "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)", ("a", "b", "c", "d"),
             _gaussian, _p0_gaussian),
    FitModel("ローレンツ", "ローレンツ関数 (y = a / (1 + ((x-b)/c)^2) + d)", ("a", "b", "c", "d"),
             _lorentzian, _p0_lorentzian),
    FitModel("擬似フォークト", "擬似フォークト関数 (y = a*(η/(1+((x-b)/c)^2) + (1-η)*exp(-4ln2*((x-b)/c)^2)) + d)",
             ("a", "b", "c", "eta", "d"), _pseudo_voigt, _p0_pseudo_voigt),
    FitModel("フォークト", "フォークト関数 (y = a*Re[wofz((x-b+iγ)/(σ√2))] / (σ√(2π)) + d)",
             ("a", "b", "sigma", "gamma", "d"), _voigt, _p0_voigt),
    FitModel("ボルツマン", "ボルツマンシグモイド (y = a2 + (a1-a2) / (1 + exp((x-x0)/dx)))",
             ("a1", "a2", "x0", "dx"), _boltzmann_sigmoid, _p0_boltzmann_sigmoid),
    FitModel("シグモイド", "シグモイド (y = a / (1 + exp(-b(x-c))))", ("a", "b", "c"), _sigmoid, _p0_sigmoid),
    FitModel("ヒル", "ヒルの式 (y = vmax*x^n / (k^n + x^n))", ("vmax", "k", "n"), _hill, _p0_hill,
             _require_non_negative_x),
)

MENU_ORDER: tuple[str, ...] = (
    "線形", "2次多項式", "3次多項式", "指数関数", "対数", "べき乗", "ガウシアン", "ローレンツ",
    "擬似フォークト", "フォークト", "2成分指数", "ボルツマン", "シグモイド", "ヒル",
)

# プラグインの関数名がこれらと同じだと取り違えるので、登録を断る(部分一致は断らない: K-20)
RESERVED_FIT_TYPE_NAMES: tuple[str, ...] = (CUSTOM_FORMULA_KEYWORD,) + tuple(m.keyword for m in BUILTIN_FIT_MODELS)


def builtin_menu_labels() -> list[str]:
    by_keyword = {m.keyword: m for m in BUILTIN_FIT_MODELS}
    return [by_keyword[keyword].menu_label for keyword in MENU_ORDER]


_RESERVED_FORMULA_NAMES = set(DEFAULT_FUNCTIONS.keys()) | {'x'}


def extract_formula_params(formula: str) -> list[str]:
    """x でも既知の関数名でもない識別子を、出現順にパラメータとして取り出す。"""
    params = []
    for name in re.findall(r'[a-zA-Z_][a-zA-Z_0-9]*', formula):
        if name in _RESERVED_FORMULA_NAMES or name in params:
            continue
        params.append(name)
    if not params:
        raise ValueError("数式にフィットパラメータ(x以外の文字)が見つかりません。")
    return params


def build_custom_fit_func(formula: str, param_names: list[str]) -> Callable[..., Any]:
    def custom_func(x: Any, *params: float) -> Any:
        variables = {'x': x}
        variables.update(zip(param_names, params))
        try:
            return safe_eval_formula(formula, variables)
        except Exception as e:
            raise ValueError(f"数式の評価に失敗しました: {e}") from e
    return custom_func


@dataclass
class ResolvedFitModel:
    """種類の名前から決まったモデル。param_names はプラグインのときは登録されたリストそのもの。"""
    param_names: list[str]
    func: Callable[..., Any]
    initial_guess: Callable[[Any, Any], list[Any]]
    check_data: Callable[[Any], None] | None = None


def _custom_formula_or_raise(custom_formula: str | None) -> str:
    if not custom_formula or not custom_formula.strip():
        raise ValueError("カスタム数式が入力されていません。")
    return custom_formula


def resolve_fit_param_names(fit_type: str, custom_formula: str | None,
                            plugin_functions: Mapping[str, dict[str, Any]]) -> list[str]:
    """パラメータ名だけを決める(カスタム数式の関数は作らない)。"""
    if is_custom_formula_type(fit_type):
        return extract_formula_params(_custom_formula_or_raise(custom_formula))
    for model in BUILTIN_FIT_MODELS:
        if model.keyword in fit_type:
            return list(model.param_names)
    if fit_type in plugin_functions:
        return list(plugin_functions[fit_type]["params"])
    raise ValueError(f"不明なフィットタイプ: {fit_type}")


def resolve_fit_model(fit_type: str, custom_formula: str | None,
                      plugin_functions: Mapping[str, dict[str, Any]]) -> ResolvedFitModel:
    if is_custom_formula_type(fit_type):
        params = extract_formula_params(_custom_formula_or_raise(custom_formula))
        # *params 形式ではパラメータ数を推定できないので p0 で数を伝える
        return ResolvedFitModel(params, build_custom_fit_func(custom_formula or "", params),
                                lambda x, y: [1.0] * len(params))
    for model in BUILTIN_FIT_MODELS:
        if model.keyword in fit_type:
            return ResolvedFitModel(list(model.param_names), model.func, model.initial_guess, model.check_data)
    if fit_type in plugin_functions:
        entry = plugin_functions[fit_type]
        return ResolvedFitModel(entry["params"], entry["func"], _plugin_initial_guess(entry))
    raise ValueError(f"不明なフィットタイプ: {fit_type}")


def _plugin_initial_guess(entry: dict[str, Any]) -> Callable[[Any, Any], list[Any]]:
    def initial_guess(x: Any, y: Any) -> list[Any]:
        plugin_p0 = entry["p0"]
        if callable(plugin_p0):
            return list(plugin_p0(x, y))
        if plugin_p0 is not None:
            return list(plugin_p0)
        return [1.0] * len(entry["params"])
    return initial_guess
