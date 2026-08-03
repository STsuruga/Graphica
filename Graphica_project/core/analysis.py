# core/analysis.py
import re
import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

CURVE_FIT_MAX_ITERATIONS = 5000

# --- カスタム数式で使用可能な関数・定数 (evalに渡す安全な名前空間) ---
# 任意コード実行を防ぐため、__builtins__ を空にした上でこれらのみを許可する。
_SAFE_FORMULA_NAMESPACE = {
    'exp': np.exp, 'log': np.log, 'log10': np.log10, 'sqrt': np.sqrt,
    'sin': np.sin, 'cos': np.cos, 'tan': np.tan, 'abs': np.abs,
    'pi': np.pi, 'e': np.e,
}
_RESERVED_FORMULA_NAMES = set(_SAFE_FORMULA_NAMESPACE.keys()) | {'x'}


def _extract_formula_params(formula):
    """
    数式文字列 (例: "a*exp(-b*x)+c") から、xでも既知の関数名でもない
    識別子を「フィットパラメータ」として、出現順を保ったまま抽出する。
    """
    params = []
    for name in re.findall(r'[a-zA-Z_][a-zA-Z_0-9]*', formula):
        if name in _RESERVED_FORMULA_NAMES or name in params:
            continue
        params.append(name)
    if not params:
        raise ValueError("数式にフィットパラメータ(x以外の文字)が見つかりません。")
    return params


def _build_custom_fit_func(formula, param_names):
    """数式文字列から、curve_fit に渡せる関数 f(x, *params) を作る。"""
    def custom_func(x, *params):
        local_ns = dict(_SAFE_FORMULA_NAMESPACE)
        local_ns['x'] = x
        local_ns.update(zip(param_names, params))
        try:
            return eval(formula, {"__builtins__": {}}, local_ns)
        except Exception as e:
            raise ValueError(f"数式の評価に失敗しました: {e}") from e
    return custom_func


def calculate_curve_fit(x_data, y_data, fit_type, custom_formula=None):
    """曲線フィットの計算を行い、パラメータとフィット曲線のデータを返す"""
    def linear_func(x, a, b):
        return a * x + b

    def poly2_func(x, a, b, c):
        return a * x**2 + b * x + c

    def poly3_func(x, a, b, c, d):
        return a * x**3 + b * x**2 + c * x + d

    def exp_func(x, a, b):
        return a * np.exp(b * x)

    def log_func(x, a, b):
        return a * np.log(x) + b

    def power_func(x, a, b):
        return a * np.power(x, b)

    def gaussian_func(x, a, b, c, d):
        return a * np.exp(-((x - b) ** 2) / (2 * c ** 2)) + d

    def sigmoid_func(x, a, b, c):
        return a / (1 + np.exp(-b * (x - c)))

    if "カスタム数式" in fit_type:
        if not custom_formula or not custom_formula.strip():
            raise ValueError("カスタム数式が入力されていません。")
        params_info = _extract_formula_params(custom_formula)
        fit_func = _build_custom_fit_func(custom_formula, params_info)
        # *params 形式の関数はscipyがパラメータ数を自動推定できないため、明示的に指定する
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
    elif "指数関数" in fit_type:
        fit_func, params_info = exp_func, ['a', 'b']
        # y の符号に合わせた初期振幅で収束しやすくする
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
    elif "シグモイド" in fit_type:
        fit_func, params_info = sigmoid_func, ['a', 'b', 'c']
        amplitude = np.nanmax(y_data) or 1.0
        p0 = [amplitude, 1.0, np.nanmean(x_data)]
    else:
        raise ValueError(f"不明なフィットタイプ: {fit_type}")

    if len(x_data) < len(params_info):
        raise ValueError(
            f"データ点数 ({len(x_data)}) がフィットに必要なパラメータ数 "
            f"({len(params_info)}) より少ないため、フィッティングできません。"
        )

    # 最適化の実行 (収束しないケースに備え、初期値と最大反復回数を指定)
    try:
        popt, _ = curve_fit(fit_func, x_data, y_data, p0=p0, maxfev=CURVE_FIT_MAX_ITERATIONS)
    except RuntimeError as e:
        raise RuntimeError(
            f"フィッティングが収束しませんでした（{fit_type}）。データの分布が"
            f"このモデルに適していない可能性があります。詳細: {e}"
        ) from e

    # 滑らかなフィット曲線用データ (200点) を生成
    x_fit = np.linspace(x_data.min(), x_data.max(), 200)
    y_fit = fit_func(x_fit, *popt)

    # 当てはまりの良し悪しを判断するための決定係数(R²)と残差
    residuals = y_data - fit_func(x_data, *popt)
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((y_data - np.mean(y_data)) ** 2)
    r_squared = 1.0 if ss_tot == 0 else 1.0 - (ss_res / ss_tot)

    return popt, params_info, x_fit, y_fit, r_squared, residuals


def calculate_peaks(x_data, y_data, peak_type, settings):
    """ピーク/谷検出の計算を行い、該当するX,Y座標を返す"""
    y_data_to_find = y_data
    kwargs = {"height": settings["height"]}

    if "下に凸" in peak_type:
        y_data_to_find = -y_data 

    if settings["prominence"] is not None:
        kwargs["prominence"] = settings["prominence"]

    # X軸距離をインデックス数に変換
    if len(x_data) > 1 and settings["distance_x"] > 0:
        sorted_x = np.sort(x_data)
        avg_x_diff = np.mean(np.diff(sorted_x))
        if avg_x_diff > 0:
            kwargs["distance"] = max(1, int(np.ceil(settings["distance_x"] / avg_x_diff)))
        else:
            kwargs["distance"] = 1
    else:
        kwargs["distance"] = 1

    peak_indices, _ = find_peaks(y_data_to_find, **kwargs)
    
    if len(peak_indices) == 0:
        return np.array([]), np.array([])

    return x_data[peak_indices], y_data[peak_indices]