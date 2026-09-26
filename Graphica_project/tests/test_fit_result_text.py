"""フィット結果の文に、パラメータの標準誤差を「値 ± 誤差」で出す(K-6)。"""
import graphica.gui.datasets.fitting as fitting_module


def _fit_result(**overrides):
    result = {
        'fit_type': "線形 (y = ax + b)", 'custom_formula': None,
        'param_names': ['a', 'b'], 'params': [1.23456, -0.5], 'param_errors': [0.032, 0.0041],
        'r_squared': 0.998, 'weighted': False, 'x_range': None, 'fixed_params': None, 'bounds': None,
        'loss': 'linear',
    }
    result.update(overrides)
    return result


def test_each_parameter_shows_its_standard_error():
    text = fitting_module.format_fit_result_text(_fit_result())
    assert "  a =  1.2346e+00 ± 3.2e-02\n" in text
    assert "  b = -5.0000e-01 ± 4.1e-03\n" in text


def test_fixed_parameters_have_no_error():
    text = fitting_module.format_fit_result_text(_fit_result(fixed_params={'b': -0.5}, param_errors=[0.032, 0.0]))
    assert "  a =  1.2346e+00 ± 3.2e-02\n" in text
    assert "  b = -5.0000e-01\n" in text


def test_results_saved_without_errors_keep_the_old_lines():
    result = _fit_result()
    del result['param_errors']
    text = fitting_module.format_fit_result_text(result)
    assert "  a =  1.2346e+00\n" in text


def test_undetermined_errors_are_shown_as_they_are():
    text = fitting_module.format_fit_result_text(_fit_result(param_errors=[float('inf'), float('nan')]))
    assert "  a =  1.2346e+00 ± inf\n" in text
    assert "  b = -5.0000e-01 ± nan\n" in text


def test_multi_peak_text_shows_errors():
    text = fitting_module.multi_peak_summary_text("ガウシアン", 1, ['a1', 'b1'], [2.0, 5.0], [0.1, 0.02], 0.99)
    assert text == ("[多峰分離(ガウシアン x1)] のフィッティング結果:\n"
                    "  a1 =  2.0000e+00 ± 1.0e-01\n  b1 =  5.0000e+00 ± 2.0e-02\n  R^2 =  0.99000\n")
