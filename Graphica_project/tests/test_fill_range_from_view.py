"""「表示中の範囲を入れる」(X軸・Y軸・第2Y軸のタブ。panels/axis_settings.fill_range_from_view)。"""
import numpy as np
import pandas as pd
import pytest

from graphica.core.dataset import Dataset
from test_main_window import _make_isolated_plotter_app


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    app = _make_isolated_plotter_app(tmp_path, monkeypatch)
    x = np.linspace(0.0, 10.0, 21)
    app._add_dataset(Dataset(name="a", df=pd.DataFrame({"x": x, "y": x * 2.0}), x_col_name="x", y_col_name="y"))
    app._update_plot()
    yield app
    app.close()


def _settings(window):
    return window.project.all_plot_settings[window.project.active_axis_index]


def test_the_shown_x_range_becomes_the_manual_range(window):
    window.canvas.all_axes[0].set_xlim(2.0, 5.0)  # マウスで拡大したのと同じ
    window.x_view_range_button.click()
    assert not window.ui.x_autoscale_checkbox.isChecked()
    assert window.ui.x_min_spinbox.isEnabled()
    assert (window.ui.x_min_spinbox.value(), window.ui.x_max_spinbox.value()) == pytest.approx((2.0, 5.0))
    settings = _settings(window)
    assert settings['x_autoscale'] is False
    assert (settings['x_min'], settings['x_max']) == pytest.approx((2.0, 5.0))
    assert tuple(window.canvas.all_axes[0].get_xlim()) == pytest.approx((2.0, 5.0))


def test_an_inverted_axis_keeps_the_smaller_value_as_the_minimum(window):
    window.ui.y_invert_checkbox.setChecked(True)
    window.canvas.all_axes[0].set_ylim(8.0, 3.0)
    window.y_view_range_button.click()
    assert (window.ui.y_min_spinbox.value(), window.ui.y_max_spinbox.value()) == pytest.approx((3.0, 8.0))
    assert tuple(window.canvas.all_axes[0].get_ylim()) == pytest.approx((8.0, 3.0))


def test_the_secondary_y_axis_has_its_own_button(window):
    dataset = window.project.datasets[0]
    dataset.use_secondary_y = True
    window._update_plot()
    secondary = window.canvas.all_secondary_axes[0]
    secondary.set_ylim(4.0, 12.0)
    window.y2_view_range_button.click()
    assert not window.y2_autoscale_checkbox.isChecked()
    assert (window.y2_min_spinbox.value(), window.y2_max_spinbox.value()) == pytest.approx((4.0, 12.0))
    assert _settings(window)['y2_autoscale'] is False
