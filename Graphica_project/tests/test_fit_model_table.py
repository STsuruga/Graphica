"""フィットのモデルの表と、保存用の安定した ID(K-25)。"""
import numpy as np
import pytest

import graphica.core.analysis as analysis_module
from graphica.core import fit_models


@pytest.fixture
def plugin_fits(monkeypatch):
    monkeypatch.setattr(analysis_module, "_PLUGIN_FIT_FUNCTIONS", {})
    analysis_module.register_fit_function("減衰", lambda x, a, k: a * np.exp(-k * x), ["a", "k"], p0=[1.0, 0.5])
    return analysis_module


def test_every_builtin_model_has_a_unique_id():
    ids = [m.model_id for m in fit_models.BUILTIN_FIT_MODELS]
    assert all(ids) and len(set(ids)) == len(ids)
    assert fit_models.CUSTOM_FORMULA_MODEL_ID not in ids


def test_ids_are_stable():
    # 保存ファイルに入るので、一度決めた ID は変えない
    assert [m.model_id for m in fit_models.BUILTIN_FIT_MODELS] == [
        "linear", "poly2", "poly3", "two_exponentials", "exponential", "logarithmic", "power", "gaussian",
        "lorentzian", "pseudo_voigt", "voigt", "boltzmann_sigmoid", "sigmoid", "hill",
    ]


@pytest.mark.parametrize("model", fit_models.BUILTIN_FIT_MODELS, ids=lambda m: m.model_id)
def test_label_and_id_resolve_to_the_same_model(plugin_fits, model):
    assert plugin_fits.get_fit_model_id(model.menu_label) == model.model_id
    assert plugin_fits.get_fit_param_names("名前を変えた", model_id=model.model_id) == list(model.param_names)


def test_custom_and_plugin_ids(plugin_fits):
    assert plugin_fits.get_fit_model_id("カスタム数式...") == "custom_formula"
    assert plugin_fits.get_fit_model_id("減衰") == "plugin:減衰"
    assert plugin_fits.get_fit_model_id("存在しないモデル") is None
    assert plugin_fits.get_fit_param_names("?", "a*x+c", model_id="custom_formula") == ["a", "c"]
    assert plugin_fits.get_fit_param_names("?", model_id="plugin:減衰") == ["a", "k"]


def test_the_id_wins_over_the_label(plugin_fits):
    x = np.linspace(0.5, 10, 30)
    y = 3.0 * np.exp(-((x - 5.0) ** 2) / 2.0) + 0.5
    by_id = plugin_fits.calculate_curve_fit(x, y, "線形 (y = ax + b)", model_id="gaussian")
    by_label = plugin_fits.calculate_curve_fit(x, y, "ガウシアン")
    assert by_id["param_names"] == ["a", "b", "c", "d"]
    np.testing.assert_array_equal(by_id["popt"], by_label["popt"])


def test_an_unknown_id_falls_back_to_the_label(plugin_fits):
    assert plugin_fits.get_fit_param_names("線形", model_id="removed_model") == ["a", "b"]
    assert plugin_fits.get_fit_param_names("線形", model_id="plugin:登録されていない") == ["a", "b"]


def test_display_label_comes_from_the_id_when_known():
    gaussian = next(m for m in fit_models.BUILTIN_FIT_MODELS if m.model_id == "gaussian")
    assert fit_models.fit_type_label({"fit_type": "古い表示名", "fit_model_id": "gaussian"}) == gaussian.menu_label
    assert fit_models.fit_type_label({"fit_type": "古い表示名"}) == "古い表示名"
    assert fit_models.fit_type_label({"fit_type": "減衰", "fit_model_id": "plugin:減衰"}) == "減衰"
    assert fit_models.fit_type_label({}) is None


def test_fit_result_records_the_model_id():
    from graphica.core.dataset import Dataset
    from graphica.gui.datasets.fitting import build_fit_result_dict, format_fit_result_text
    import pandas as pd

    x = np.linspace(0, 10, 20)
    source = Dataset(df=pd.DataFrame({"x": x, "y": 2 * x + 1}), name="s", x_col_name="x", y_col_name="y")
    fit = analysis_module.calculate_curve_fit(x, 2 * x + 1, "線形 (y = ax + b)")
    result = build_fit_result_dict("線形 (y = ax + b)", None, fit, False, None, source)
    assert result["fit_model_id"] == "linear"
    assert list(result)[:2] == ["fit_type", "fit_model_id"]
    result["fit_type"] = "古い表示名"
    assert format_fit_result_text(result).startswith("[線形 (y = ax + b)] ")
