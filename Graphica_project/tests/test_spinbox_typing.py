"""プロパティのドックのスピンボックスに数値を打ち込む。1文字ごとに反映すると、反映で欄が "0" → "0.00" に
書き直されて小数を打てなかった(線の太さに 0.75 と打つと 0 になる)。"""
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractSpinBox, QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui.main_window import PlotterApp


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.show()
    dataset = Dataset(df=pd.DataFrame({'x': np.arange(5.0), 'y': np.arange(5.0)}), name="d",
                      x_col_name='x', y_col_name='y', plot_type='Line+Scatter')
    w._add_dataset(dataset)
    for _ in range(3):
        QApplication.processEvents()
    yield w
    w.close()


def _type(spin_box, text):
    spin_box.setFocus()
    spin_box.lineEdit().selectAll()
    QTest.keyClicks(spin_box.lineEdit(), text)
    QApplication.processEvents()


@pytest.mark.parametrize("widget, attr", [
    ("ui.linewidth_spinbox", "linewidth"),
    ("ui.markersize_spinbox", "markersize"),
    ("alpha_spinbox", "alpha"),
])
def test_typing_a_decimal_into_a_dataset_property(window, widget, attr):
    owner = window.ui if widget.startswith("ui.") else window
    spin_box = getattr(owner, widget.removeprefix("ui."))
    dataset = window.current_dataset()
    before = getattr(dataset, attr)

    _type(spin_box, "0.75")
    assert spin_box.lineEdit().text() == "0.75"
    assert getattr(dataset, attr) == before

    QTest.keyClick(spin_box.lineEdit(), Qt.Key.Key_Return)
    assert getattr(dataset, attr) == 0.75


def test_arrow_keys_still_apply_at_once(window):
    dataset = window.current_dataset()
    window.ui.linewidth_spinbox.setFocus()
    QTest.keyClick(window.ui.linewidth_spinbox, Qt.Key.Key_Up)
    assert dataset.linewidth == pytest.approx(2.5)


def test_typing_an_axis_range_applies_once_when_finished(window, monkeypatch):
    window.ui.x_autoscale_checkbox.setChecked(False)
    redraws = []
    monkeypatch.setattr(window, '_update_plot_appearance', lambda *a, **k: redraws.append(1))

    _type(window.ui.x_min_spinbox, "-12.5")
    assert redraws == []

    QTest.keyClick(window.ui.x_min_spinbox.lineEdit(), Qt.Key.Key_Return)
    assert redraws == [1]
    assert window.project.all_plot_settings[window.project.active_axis_index]['x_min'] == -12.5


def test_every_spin_box_in_the_properties_dock_waits_for_the_typing_to_finish(window):
    spin_boxes = window.ui.control_dock_widget.findChildren(QAbstractSpinBox)
    assert spin_boxes
    assert [s.objectName() for s in spin_boxes if s.keyboardTracking()] == []
