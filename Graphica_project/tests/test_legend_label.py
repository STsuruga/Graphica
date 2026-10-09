"""凡例の表示名(データセット名を変えずに凡例だけ変える)と「凡例に表示しない」(#111)。"""
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset, legend_text
from graphica.core.script_export import generate_python_script
from graphica.gui.main_window import PlotterApp
from graphica.models.project import ProjectModel


def _ds(name="sample", **kwargs):
    return Dataset(name=name, df=pd.DataFrame({"x": [1, 2, 3], "y": [1, 4, 9]}), x_col_name="x", y_col_name="y",
                   **kwargs)


def test_legend_text_defaults_to_the_dataset_name():
    assert legend_text(_ds()) == "sample"


def test_legend_label_overrides_the_name():
    assert legend_text(_ds(legend_label="Sample A (25 °C)")) == "Sample A (25 °C)"


def test_hidden_datasets_get_matplotlibs_nolegend_label():
    assert legend_text(_ds(legend_label="x", hide_from_legend=True)) == "_nolegend_"


def test_old_projects_without_the_fields_keep_the_name():
    restored = Dataset.from_dict({k: v for k, v in _ds().to_dict().items()
                                  if k not in ('legend_label', 'hide_from_legend')})
    assert (restored.legend_label, restored.hide_from_legend) == ("", False)
    assert legend_text(restored) == "sample"


def test_the_exported_script_uses_the_legend_label():
    project = ProjectModel()
    project.datasets = [_ds(legend_label="Override")]
    project.all_plot_settings = [{}]
    script = generate_python_script(project)
    assert "label='Override'" in script
    assert "label='sample'" not in script


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.show()
    QApplication.instance().processEvents()
    yield w
    w.close()


def _legend_texts(window):
    legend = window.canvas.all_axes[0].get_legend()
    return [t.get_text() for t in legend.get_texts()] if legend is not None else []


@pytest.mark.parametrize("plot_type", ["Line", "Scatter", "Line+Scatter", "Area", "Bar", "Step"])
def test_the_legend_shows_the_label_for_every_plot_type(window, plot_type):
    window._add_dataset(_ds(legend_label="Shown", plot_type=plot_type), None)
    window._update_plot()
    assert _legend_texts(window) == ["Shown"]


def test_hidden_dataset_is_left_out_of_the_legend(window):
    window._add_dataset(_ds("a"), None)
    window._add_dataset(_ds("b", hide_from_legend=True), None)
    window._update_plot()
    assert _legend_texts(window) == ["a"]


def test_the_panel_edits_the_legend_label_and_keeps_the_name(window):
    ds = _ds()
    window._add_dataset(ds, None, select=True)
    window.legend_label_edit.setText("  New label  ")
    window.legend_label_edit.editingFinished.emit()
    assert ds.legend_label == "New label"
    assert ds.name == "sample"
    assert _legend_texts(window) == ["New label"]


def test_the_panel_hides_from_the_legend_and_can_undo(window):
    ds = _ds()
    window._add_dataset(ds, None, select=True)
    window.hide_from_legend_checkbox.setChecked(True)
    assert ds.hide_from_legend is True
    window.undo_stack.undo()
    assert ds.hide_from_legend is False


def test_selecting_a_dataset_restores_its_legend_fields(window):
    first, second = _ds("a", legend_label="A label"), _ds("b", hide_from_legend=True)
    window._add_dataset(first, None)
    window._add_dataset(second, None)
    tree = window.ui.dataset_list_widget
    tree.setCurrentItem(window._get_dataset_tree_item(first))
    assert window.legend_label_edit.text() == "A label"
    assert not window.hide_from_legend_checkbox.isChecked()
    tree.setCurrentItem(window._get_dataset_tree_item(second))
    assert window.legend_label_edit.text() == ""
    assert window.hide_from_legend_checkbox.isChecked()
