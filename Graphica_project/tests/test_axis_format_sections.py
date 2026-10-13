"""「軸」タブの「ラベル/書式」の節(gui/builders/axis_format_sections.py)。"""
import pytest
from PySide6.QtWidgets import QApplication

from graphica.gui import theme
from graphica.gui.builders.axis_format_sections import AXIS_FORMAT_SECTIONS
from test_main_window import _make_isolated_plotter_app


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    app = _make_isolated_plotter_app(tmp_path, monkeypatch)
    yield app
    app.close()


def _row_shown(form, widget):
    row, _role = form.getWidgetPosition(widget)
    return form.isRowVisible(row)


def test_the_rows_are_split_into_the_sections(window):
    assert list(window._axis_sections) == [key for key, _title, _rows in AXIS_FORMAT_SECTIONS]
    ticks = window._axis_sections['ticks']['form']
    assert ticks.getWidgetPosition(window.ui.tick_width_label)[0] >= 0
    assert window._axis_sections['grid']['switch'] is window.ui.grid_visible_checkbox
    assert window._axis_sections['colorbar']['switch'] is window.colorbar_enabled_checkbox
    assert window.ui.grid_visible_checkbox.property(theme.TOGGLE_SWITCH_PROPERTY)


def test_grid_details_are_hidden_until_the_grid_is_on(window):
    grid = window._axis_sections['grid']
    window.ui.grid_visible_checkbox.setChecked(False)
    QApplication.processEvents()
    assert grid['body'].isHidden()
    window.ui.grid_visible_checkbox.setChecked(True)
    window.ui.minor_grid_visible_checkbox.setChecked(False)
    QApplication.processEvents()
    assert not grid['body'].isHidden()
    assert _row_shown(grid['form'], window.x_major_grid_style_label)
    assert not _row_shown(grid['form'], window.x_minor_grid_style_label)
    window.ui.minor_grid_visible_checkbox.setChecked(True)
    assert _row_shown(grid['form'], window.x_minor_grid_style_label)


def test_sliders_write_their_spinboxes(window):
    slider = window.spine_width_slider
    slider.slider.setValue(round(2.0 * 10 ** window.ui.spine_width_spinbox.decimals()))
    assert window.ui.spine_width_spinbox.value() == pytest.approx(2.0)
    window.colorbar_position_segments.setCurrentIndex(window.colorbar_position_segments.findData("top"))
    assert window.colorbar_position_combo.currentData() == "top"
