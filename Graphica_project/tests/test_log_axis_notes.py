"""gui/log_axis_notes.py: 対数軸で表示されない 0 以下の値を、対数のチェックの下で知らせる。"""
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui.log_axis_notes import log_note_text
from graphica.gui.main_window import PlotterApp


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.resize(1100, 700)
    w.show()
    QApplication.instance().processEvents()
    yield w
    w.close()


def _add(window, x, y, **kwargs):
    ds = Dataset(name=kwargs.pop("name", "d"), df=pd.DataFrame({"x": x, "y": y}),
                 x_col_name="x", y_col_name="y", **kwargs)
    window.project.datasets.append(ds)
    return ds


def _set(window, **settings):
    window.project.all_plot_settings[0].update(settings)
    window._update_plot()
    window.canvas.draw()


def test_note_text():
    assert log_note_text(0, False) == ""
    assert log_note_text(1234, False) == "0 以下の値の点が 1,234 個あり、対数軸では表示されません。"
    assert log_note_text(0, True) == "最小値が 0 以下なので、対数軸では無視されます。"
    assert log_note_text(2, True).count("\n") == 1


def test_y_log_with_zeros_shows_the_count(window):
    _add(window, [1, 2, 3, 4], [0, -1, 5, 10])
    _set(window, y_log=True)
    assert not window.y_log_note.isHidden()
    assert "2 個" in window.y_log_note.text()
    assert window.x_log_note.isHidden()


def test_note_disappears_when_log_is_turned_off(window):
    _add(window, [1, 2], [0, 5])
    _set(window, y_log=True)
    _set(window, y_log=False)
    assert window.y_log_note.isHidden()


def test_positive_data_needs_no_note(window):
    _add(window, [1, 2], [3, 5])
    _set(window, x_log=True, y_log=True)
    assert window.x_log_note.isHidden()
    assert window.y_log_note.isHidden()


def test_x_log_counts_x_values(window):
    _add(window, [0, 1, 2], [3, 4, 5])
    _set(window, x_log=True)
    assert "1 個" in window.x_log_note.text()


def test_manual_minimum_at_or_below_zero_is_reported(window):
    _add(window, [1, 2], [3, 5])
    _set(window, y_log=True, y_autoscale=False, y_min=0, y_max=10)
    assert "最小値" in window.y_log_note.text()


def test_secondary_axis_counts_only_its_datasets(window):
    _add(window, [1, 2, 3], [0, 0, 5], name="primary")
    _add(window, [1, 2, 3], [-1, 2, 5], name="secondary", use_secondary_y=True)
    _set(window, y2_log=True)
    assert "1 個" in window.y2_log_note.text()
    assert window.y_log_note.isHidden()


def test_hidden_datasets_and_other_subplots_are_not_counted(window):
    _add(window, [1, 2], [0, 5], name="hidden", visible=False)
    _add(window, [1, 2], [0, 5], name="elsewhere", subplot_target=1)
    _set(window, y_log=True)
    assert window.y_log_note.isHidden()


def test_waterfall_counts_the_shifted_values(window):
    """ずらした後に正なら表示されるので数えない。"""
    _add(window, [1, 2], [0, 1], name="a", waterfall_enabled=True, waterfall_offset_y=10,
         waterfall_offset_mode='absolute')
    _set(window, y_log=True)
    assert window.y_log_note.isHidden()


def test_category_x_values_are_not_counted(window):
    _add(window, ["a", "b"], [1, 2])
    _set(window, x_log=True)
    assert window.x_log_note.isHidden()


def test_switching_the_active_subplot_updates_the_note(window):
    window.subplot_rows_spinbox.setValue(1)
    window.subplot_cols_spinbox.setValue(2)
    _add(window, [1, 2], [0, 5], name="right", subplot_target=1)
    window.project.all_plot_settings[1]['y_log'] = True
    window._update_plot()
    window.canvas.draw()
    assert window.y_log_note.isHidden()  # 表示中はプロット 1

    window.active_axis_combo.setCurrentIndex(1)

    assert "1 個" in window.y_log_note.text()
    assert not window.y_log_note.isHidden()


def test_large_counts_use_separators(window):
    _add(window, np.arange(1, 1501), np.zeros(1500))
    _set(window, y_log=True)
    assert "1,500 個" in window.y_log_note.text()
