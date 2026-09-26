# tests/test_standard_deviation_consistency.py
"""
「標準偏差」の計算の統一(v1.4.2)。

同じデータでも、画面下部の要約・統計情報ポップアップ・外れ値検出の Z-score は
n で割り、統計値アンカーラベル・反復測定の誤差列は n−1 で割っていた。
測定データは標本なので、すべて標本標準偏差(n−1、ddof=1)に揃える。
"""
import math

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.analysis import calculate_zscore_outliers, sample_standard_deviation
from graphica.core.dataset import Dataset
from graphica.gui.canvas import _compute_stat_label_text
from graphica.gui.main_window import PlotterApp

VALUES = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]  # 母SD=2.0、標本SD≈2.138
SAMPLE_SD = float(np.std(VALUES, ddof=1))


def test_sample_standard_deviation_divides_by_n_minus_1():
    assert sample_standard_deviation(VALUES) == pytest.approx(SAMPLE_SD)
    assert sample_standard_deviation(VALUES) != pytest.approx(2.0)


def test_nan_is_ignored():
    assert sample_standard_deviation(VALUES + [float("nan")]) == pytest.approx(SAMPLE_SD)


@pytest.mark.parametrize("values", [[], [1.0], [float("nan"), 3.0]])
def test_fewer_than_two_values_is_undefined(values):
    assert math.isnan(sample_standard_deviation(values))


def test_zscore_outliers_use_the_sample_sd():
    result = calculate_zscore_outliers(VALUES, threshold=10.0)
    expected = (np.asarray(VALUES) - np.mean(VALUES)) / SAMPLE_SD
    np.testing.assert_allclose(result["z_scores"], expected)


def _dataset():
    df = pd.DataFrame({"x": np.arange(len(VALUES), dtype=float), "y": VALUES})
    return Dataset(name="d", df=df, x_col_name="x", y_col_name="y")


def test_anchor_label_uses_the_sample_sd():
    text = _compute_stat_label_text(_dataset(), "std")
    assert text == f"標準偏差 = {SAMPLE_SD:.4g}"


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.instance().processEvents()
    yield w
    w.close()


def test_summary_and_popup_show_the_same_value_as_the_anchor_label(window):
    window.property_panel.update_stats_summary_label(_dataset())
    expected = f"{SAMPLE_SD:.4g}"
    assert f"標準偏差: {expected}" in window.stats_summary_label.text()
    assert f"SD={expected}" in window.dataset_mini_stats_label.text()


def test_single_point_summary_shows_a_dash_instead_of_zero(window):
    df = pd.DataFrame({"x": [1.0], "y": [3.0]})
    window.property_panel.update_stats_summary_label(Dataset(name="one", df=df, x_col_name="x", y_col_name="y"))
    assert "標準偏差: -" in window.stats_summary_label.text()
