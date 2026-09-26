"""フィットのモデルを固定する: 全種類・プラグインの関数・カスタム数式について、パラメータ名・popt・pcov・R²・残差・
出た警告、失敗するときの例外の型と文言。数値は float.hex で完全一致を見る。
"""
import warnings

import numpy as np
import pytest

import recorder

X = np.linspace(0.5, 10.0, 40)
_RIPPLE = 0.01 * np.sin(7.0 * X)

FIT_TYPES_AND_DATA = {
    "線形 (y = ax + b)": 2.0 * X + 1.0 + _RIPPLE,
    "2次多項式 (y = ax^2 + bx + c)": 0.3 * X ** 2 - X + 2.0 + _RIPPLE,
    "3次多項式 (y = ax^3 + bx^2 + cx + d)": 0.05 * X ** 3 - 0.4 * X ** 2 + X + _RIPPLE,
    "指数関数 (y = a * exp(bx))": 2.0 * np.exp(0.2 * X) + _RIPPLE,
    "対数 (y = a * ln(x) + b)": 3.0 * np.log(X) + 1.0 + _RIPPLE,
    "べき乗 (y = a * x^b)": 1.5 * X ** 1.3 + _RIPPLE,
    "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)": 4.0 * np.exp(-((X - 5.0) ** 2) / (2 * 1.2 ** 2)) + 0.5 + _RIPPLE,
    "ローレンツ関数 (y = a / (1 + ((x-b)/c)^2) + d)": 3.0 / (1 + ((X - 4.0) / 0.8) ** 2) + 0.2 + _RIPPLE,
    "擬似フォークト関数 (y = a*(η/(1+((x-b)/c)^2) + (1-η)*exp(-4ln2*((x-b)/c)^2)) + d)":
        3.0 * (0.4 / (1 + ((X - 6.0) / 1.5) ** 2) + 0.6 * np.exp(-4 * np.log(2) * ((X - 6.0) / 1.5) ** 2)) + 0.1
        + _RIPPLE,
    "フォークト関数 (y = a*Re[wofz((x-b+iγ)/(σ√2))] / (σ√(2π)) + d)":
        3.0 / (1 + ((X - 5.5) / 0.9) ** 2) + 2.0 * np.exp(-((X - 5.5) ** 2) / 2.0) + _RIPPLE,
    # 減衰 2 成分のデータは解が 1 つに決まらず、メモリの並びの違いだけで結果が変わるので、増加と減衰の組にする
    "2成分指数関数 (y = a1*exp(b1*x) + a2*exp(b2*x) + c)": 0.5 * np.exp(0.2 * X) + 3.0 * np.exp(-0.6 * X) + 0.2 + _RIPPLE,
    "ボルツマンシグモイド (y = a2 + (a1-a2) / (1 + exp((x-x0)/dx)))": 5.0 + (1.0 - 5.0) / (1 + np.exp((X - 5.0) / 0.7))
        + _RIPPLE,
    "シグモイド (y = a / (1 + exp(-b(x-c))))": 4.0 / (1 + np.exp(-1.5 * (X - 5.0))) + _RIPPLE,
    "ヒルの式 (y = vmax*x^n / (k^n + x^n))": 6.0 * X ** 2 / (3.0 ** 2 + X ** 2) + _RIPPLE,
}


def _hex(values):
    return [float(v).hex() for v in np.ravel(np.asarray(values, dtype=float))]


def _fit_record(call, *args, **kwargs):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            fit = call(*args, **kwargs)
        except Exception as error:  # 失敗の型と文言も今の挙動として残す
            return {"error": f"{type(error).__name__}: {error}",
                    "warnings": [f"{w.category.__name__}: {w.message}" for w in caught]}
    return {
        "param_names": list(fit["param_names"]),
        "popt": _hex(fit["popt"]),
        "pcov": _hex(fit["pcov"]),
        "perr": _hex(fit["perr"]),
        "r_squared": float(fit["r_squared"]).hex(),
        "residuals": _hex(fit["residuals"]),
        "x_fit": recorder.array_summary(fit["x_fit"]),
        "y_fit": _hex(fit["y_fit"][::20]),
        "fit_func_on_data": _hex(fit["fit_func"](fit["x_data_used"], *fit["popt"])[::5]),
        "keys": sorted(fit),
        "loss": fit["loss"],
        "warnings": [f"{w.category.__name__}: {w.message}" for w in caught],
    }


@pytest.fixture
def plugin_fits(monkeypatch):
    import graphica.core.analysis as analysis

    monkeypatch.setattr(analysis, "_PLUGIN_FIT_FUNCTIONS", {})

    def double_exp(x, a, k, c):
        return a * np.exp(-k * x) + c

    analysis.register_fit_function("減衰(初期値リスト)", double_exp, ["a", "k", "c"], p0=[2.0, 0.5, 0.0])
    analysis.register_fit_function("減衰(初期値関数)", double_exp, ["a", "k", "c"],
                                   p0=lambda x, y: [float(np.max(y)), 0.3, float(np.min(y))])
    analysis.register_fit_function("減衰(初期値なし)", double_exp, ["a", "k", "c"])
    # K-20: 組み込みの語を含む名前は登録できるが、計算は組み込みのガウシアンになる
    analysis.register_fit_function("二重ガウシアン", lambda x, a, b, c, d, e, f: a + 0 * x, list("abcdef"))
    return analysis


def test_builtin_models(normalizer):
    from graphica.core.analysis import calculate_curve_fit, get_fit_param_names

    record = {}
    for fit_type, y in FIT_TYPES_AND_DATA.items():
        record[fit_type] = {
            "param_names": get_fit_param_names(fit_type),
            "fit": _fit_record(calculate_curve_fit, X, y, fit_type),
            "short_name": _fit_record(calculate_curve_fit, X, y, fit_type.split(" ")[0]),
        }
    recorder.check("fit_models/builtin", record, normalizer)


def test_plugin_and_custom_models(plugin_fits, normalizer):
    analysis = plugin_fits
    y = 3.0 * np.exp(-0.4 * X) + 0.5 + _RIPPLE
    gauss_y = FIT_TYPES_AND_DATA["ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)"]
    record = {"plugin_names": analysis.get_plugin_fit_type_names()}
    for name in analysis.get_plugin_fit_type_names():
        data = gauss_y if name == "二重ガウシアン" else y
        record[name] = {"param_names": analysis.get_fit_param_names(name),
                        "fit": _fit_record(analysis.calculate_curve_fit, X, data, name)}
    for label in ("カスタム数式...", "カスタム数式"):
        record[label] = {
            "param_names": analysis.get_fit_param_names(label, "a*exp(-k*x)+c"),
            "fit": _fit_record(analysis.calculate_curve_fit, X, y, label, custom_formula="a*exp(-k*x)+c"),
        }
    record["param_names_is_fresh_list"] = (
        analysis.get_fit_param_names("線形") is not analysis.get_fit_param_names("線形"))
    fit = analysis.calculate_curve_fit(X, y, "減衰(初期値リスト)")
    record["plugin_param_names_is_registered_list"] = (
        fit["param_names"] is analysis._PLUGIN_FIT_FUNCTIONS["減衰(初期値リスト)"]["params"])
    recorder.check("fit_models/plugin_and_custom", record, normalizer)


def test_fit_options(normalizer):
    from graphica.core.analysis import calculate_curve_fit

    gauss = "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)"
    y = FIT_TYPES_AND_DATA[gauss]
    sigma = 0.05 + 0.01 * X
    y_nan = y.copy()
    y_nan[[3, 17]] = np.nan
    cases = {
        "sigma": lambda: calculate_curve_fit(X, y, gauss, sigma=sigma),
        "x_range": lambda: calculate_curve_fit(X, y, gauss, x_range=(2.0, 8.0)),
        "p0_overrides": lambda: calculate_curve_fit(X, y, gauss, p0_overrides={"b": 4.5}),
        "fixed": lambda: calculate_curve_fit(X, y, gauss, fixed_params={"d": 0.5}),
        "bounds": lambda: calculate_curve_fit(X, y, gauss, bounds={"c": (0.5, 3.0), "b": (5.0, 9.0)}),
        "bounds_and_fixed": lambda: calculate_curve_fit(X, y, gauss, fixed_params={"a": 4.0}, bounds={"c": (0.1, 5.0)}),
        "soft_l1": lambda: calculate_curve_fit(X, y, gauss, loss="soft_l1"),
        "huber_with_bounds": lambda: calculate_curve_fit(X, y, gauss, loss="huber", bounds={"a": (0.0, 10.0)}),
        "nan_rows": lambda: calculate_curve_fit(X, y_nan, gauss),
        "nan_in_sigma": lambda: calculate_curve_fit(X, y, gauss, sigma=np.where(X > 9.5, np.nan, sigma)),
    }
    recorder.check("fit_models/options", {k: _fit_record(v) for k, v in cases.items()}, normalizer,
                   rel_tol=recorder.OPTIMIZER_REL_TOL)


def test_fit_failures(plugin_fits, normalizer):
    analysis = plugin_fits
    y = FIT_TYPES_AND_DATA["線形 (y = ax + b)"]
    negative_x = X - 5.0
    flat = np.ones_like(X)
    cases = {
        "log_nonpositive_x": lambda: analysis.calculate_curve_fit(negative_x, y, "対数"),
        "power_nonpositive_x": lambda: analysis.calculate_curve_fit(negative_x, y, "べき乗"),
        "hill_negative_x": lambda: analysis.calculate_curve_fit(negative_x, y, "ヒルの式"),
        "hill_zero_x_allowed": lambda: analysis.calculate_curve_fit(X - 0.5, y, "ヒルの式"),
        "custom_empty": lambda: analysis.calculate_curve_fit(X, y, "カスタム数式...", custom_formula="  "),
        "custom_none": lambda: analysis.calculate_curve_fit(X, y, "カスタム数式..."),
        "custom_no_params": lambda: analysis.calculate_curve_fit(X, y, "カスタム数式", custom_formula="x*2+sin(x)"),
        "custom_bad_formula": lambda: analysis.calculate_curve_fit(X, y, "カスタム数式", custom_formula="a*undefined_fn(x)"),
        "unknown": lambda: analysis.calculate_curve_fit(X, y, "存在しないモデル"),
        "too_few_points": lambda: analysis.calculate_curve_fit(X[:3], y[:3], "3次多項式"),
        "all_nan": lambda: analysis.calculate_curve_fit(X, np.full_like(X, np.nan), "線形"),
        "no_convergence": lambda: analysis.calculate_curve_fit(X, np.sin(40 * X), "ボルツマンシグモイド"),
        "fix_everything": lambda: analysis.calculate_curve_fit(X, y, "線形", fixed_params={"a": 1.0, "b": 0.0}),
        "unknown_param": lambda: analysis.calculate_curve_fit(X, y, "線形", p0_overrides={"z": 1.0}),
        "unknown_loss": lambda: analysis.calculate_curve_fit(X, y, "線形", loss="cauchy"),
        "flat_sigmoid": lambda: analysis.calculate_curve_fit(X, flat, "シグモイド"),
        "flat_gaussian": lambda: analysis.calculate_curve_fit(X, flat, "ガウシアン"),
    }
    record = {k: _fit_record(v) for k, v in cases.items()}
    # 収束しない当てはめの数値は CPU や BLAS で下位ビットが揺れるので、結果の形だけを残す
    unstable = record["no_convergence"]
    record["no_convergence"] = {
        "param_names": unstable["param_names"],
        "perr": unstable["perr"],
        "poor_fit": float.fromhex(unstable["r_squared"]) < 0.1,
        "keys": unstable["keys"],
        "loss": unstable["loss"],
        "warnings": sorted(set(unstable["warnings"])),
    }

    def param_names(*args):
        try:
            return analysis.get_fit_param_names(*args)
        except Exception as error:
            return f"{type(error).__name__}: {error}"

    record["param_names"] = {
        "custom_empty": param_names("カスタム数式...", ""),
        "custom_no_params": param_names("カスタム数式", "x+1"),
        "unknown": param_names("存在しないモデル"),
        "plugin_exact_only": param_names("減衰"),
    }

    def register(*args, **kwargs):
        try:
            analysis.register_fit_function(*args, **kwargs)
            return "ok"
        except Exception as error:
            return f"{type(error).__name__}: {error}"

    record["register"] = {
        "empty_name": register("  ", lambda x, a: a * x, ["a"]),
        "builtin_name": register("ガウシアン", lambda x, a: a * x, ["a"]),
        "duplicate": register("減衰(初期値リスト)", lambda x, a: a * x, ["a"]),
        "no_params": register("新しい関数", lambda x: x, []),
    }
    recorder.check("fit_models/failures", record, normalizer)
