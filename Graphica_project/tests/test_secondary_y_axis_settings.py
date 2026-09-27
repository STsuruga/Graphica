"""第 2 Y 軸の範囲・対数・反転・目盛りの設定(既定は今までどおりデータに合わせた自動)。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.ticker as ticker  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402

import graphica.gui.app_settings as app_settings_module  # noqa: E402
from graphica.core.axis_settings import AXIS_SETTING_DEFAULTS  # noqa: E402
from graphica.core.dataset import Dataset  # noqa: E402
from graphica.core.script_export import generate_python_script  # noqa: E402
from graphica.models.project import ProjectModel  # noqa: E402


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    from graphica.gui.main_window import PlotterApp

    app = PlotterApp(run_startup_checks=False, tab_id=2)
    app._add_dataset(Dataset(name="left", df=pd.DataFrame({"x": [1, 2, 3], "y": [1.0, 2.0, 3.0]}),
                             x_col_name="x", y_col_name="y"))
    right = Dataset(name="right", df=pd.DataFrame({"x": [1, 2, 3], "y": [10.0, 50.0, 30.0]}),
                    x_col_name="x", y_col_name="y", use_secondary_y=True)
    app._add_dataset(right)
    app._update_plot()
    yield app
    app.close()


def _secondary(window):
    return window.canvas.all_secondary_axes[0]


def test_defaults_keep_the_automatic_tight_range(window):
    assert _secondary(window).get_ylim() == pytest.approx((10.0, 50.0))
    assert _secondary(window).get_yscale() == "linear"
    assert not _secondary(window).yaxis_inverted()
    assert AXIS_SETTING_DEFAULTS["y2_autoscale"] is True


def test_manual_range_log_invert_and_ticks_are_applied(window):
    window.y2_autoscale_checkbox.setChecked(False)
    window.y2_min_spinbox.setValue(5.0)
    window.y2_max_spinbox.setValue(100.0)
    window.y2_log_checkbox.setChecked(True)
    window.y2_invert_checkbox.setChecked(True)
    window._update_plot()
    secondary = _secondary(window)
    assert sorted(secondary.get_ylim()) == pytest.approx([5.0, 100.0])
    assert secondary.get_yscale() == "log"
    assert secondary.yaxis_inverted()

    window.y2_log_checkbox.setChecked(False)
    window.y2_invert_checkbox.setChecked(False)
    window.y2_major_tick_mode_combo.setCurrentIndex(1)
    window.y2_major_tick_interval_spinbox.setValue(25.0)
    window.y2_minor_ticks_visible_checkbox.setChecked(True)
    window.y2_minor_tick_interval_spinbox.setValue(5.0)
    window._update_plot()
    secondary = _secondary(window)
    assert secondary.get_yscale() == "linear"
    assert list(secondary.yaxis.get_major_locator().tick_values(5.0, 100.0))[:3] == pytest.approx([0.0, 25.0, 50.0])
    assert isinstance(secondary.yaxis.get_minor_locator(), ticker.MultipleLocator)


def test_settings_are_saved_per_axis_and_restored(window):
    window.y2_autoscale_checkbox.setChecked(False)
    window.y2_min_spinbox.setValue(0.0)
    window.y2_max_spinbox.setValue(80.0)
    settings = window._gather_settings_from_ui()
    assert (settings["y2_autoscale"], settings["y2_min"], settings["y2_max"]) == (False, 0.0, 80.0)

    window._apply_settings_to_ui_controls(dict(settings, y2_autoscale=True))
    assert window.y2_autoscale_checkbox.isChecked()
    assert not window.y2_min_spinbox.isEnabled()
    window._apply_settings_to_ui_controls(settings)
    assert window.y2_max_spinbox.value() == 80.0 and window.y2_max_spinbox.isEnabled()


def test_turning_autoscale_off_seeds_the_current_range(window):
    window.y2_autoscale_checkbox.setChecked(False)
    assert (window.y2_min_spinbox.value(), window.y2_max_spinbox.value()) == pytest.approx((10.0, 50.0))


def test_interval_fields_follow_the_modes(window):
    assert not window.y2_major_tick_interval_spinbox.isEnabled()
    window.y2_major_tick_mode_combo.setCurrentIndex(1)
    assert window.y2_major_tick_interval_spinbox.isEnabled()
    window.y2_minor_ticks_visible_checkbox.setChecked(True)
    assert window.y2_minor_tick_interval_spinbox.isEnabled()
    window.y2_log_checkbox.setChecked(True)
    assert not window.y2_minor_tick_interval_spinbox.isEnabled()


def test_script_export_writes_the_secondary_axis_settings():
    project = ProjectModel()
    project.datasets = [Dataset(name="r", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x",
                                y_col_name="y", use_secondary_y=True)]
    project.dataset_group_tree = {"name": "", "children": [{"dataset": project.datasets[0]}]}
    project.all_plot_settings = [{"y2_label": "右", "y2_autoscale": False, "y2_min": 0, "y2_max": 9,
                                  "y2_log": True, "y2_invert": True}]
    script = generate_python_script(project)
    assert "ax0_secondary.set_ylabel('右')" in script
    assert "ax0_secondary.set_yscale('log')" in script
    assert "ax0_secondary.set_ylim(0, 9)" in script
    assert "ax0_secondary.invert_yaxis()" in script
