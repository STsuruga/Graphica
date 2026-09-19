"""組み込みの plot_type の描き方の表(graphica/gui/plot_type_drawers.py)。"""
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.main_window as main_window_module
from graphica.core.dataset import Dataset
from graphica.gui.canvas import MplCanvas
from graphica.gui.main_window import PlotterApp
from graphica.gui.plot_type_drawers import BUILTIN_PLOT_TYPE_DRAWERS


def _make_window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.processEvents()
    return window


def test_every_plot_type_in_the_panel_has_a_drawer(tmp_path, monkeypatch):
    """プラグインの無い状態で種類の欄に並ぶものは、すべて表で描ける(線に置き換わらない)。"""
    window = _make_window(tmp_path, monkeypatch)
    combo = window.ui.plot_type_combo

    offered = {combo.itemText(i) for i in range(combo.count())}

    assert offered == set(BUILTIN_PLOT_TYPE_DRAWERS)


@pytest.mark.parametrize("plot_type", sorted(BUILTIN_PLOT_TYPE_DRAWERS))
def test_each_builtin_plot_type_draws_without_warning(plot_type, caplog):
    df = pd.DataFrame({"x": np.linspace(0, 1, 10), "y": np.linspace(1, 2, 10), "z": np.linspace(0, 5, 10)})
    ds = Dataset(name="d", df=df, x_col_name="x", y_col_name="y", plot_type=plot_type, z_col_name="z")
    canvas = MplCanvas(width=4, height=3, dpi=60)

    canvas.redraw_all([ds], 1, 1, [{}])

    assert ds.artist is not None
    assert "plot_type" not in caplog.text
