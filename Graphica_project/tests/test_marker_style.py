"""マーカーの塗りと枠線(core/marker_style.py)。描画・Python スクリプトの書き出し・プロパティ欄。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.colors import to_rgba
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE, Dataset
from graphica.core.marker_style import (
    line_marker_kwargs, mapped_scatter_marker_kwargs, scatter_marker_kwargs)
from graphica.core.script_export import generate_python_script
from graphica.gui.canvas import MplCanvas
from graphica.gui.datasets.operations.transfer import STYLE_ATTRS
from graphica.gui.main_window import PlotterApp
from graphica.models.project import ProjectModel

RED = '#ff0000'


def _dataset(plot_type='Scatter', **overrides):
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0], "z": [0.0, 1.0, 2.0]})
    kwargs = dict(name="d", df=df, x_col_name="x", y_col_name="y", z_col_name="z", plot_type=plot_type, color=RED)
    kwargs.update(overrides)
    return Dataset(**kwargs)


def _draw(ds):
    canvas = MplCanvas(width=4, height=3, dpi=60)
    canvas.redraw_all([ds], 1, 1, [{}])
    return ds.artist


def _rgba(colors):
    return [tuple(np.round(c, 4)) for c in np.atleast_2d(colors)]


# --- 既定では今までと同じ呼び出し ---

@pytest.mark.parametrize("make_kwargs", [scatter_marker_kwargs, line_marker_kwargs])
def test_defaults_add_no_arguments(make_kwargs):
    assert make_kwargs(_dataset()) == {}


def test_defaults_add_no_arguments_to_mapped_scatter():
    assert mapped_scatter_marker_kwargs(_dataset()) == ({}, False)


def test_old_project_without_marker_fields_loads_the_old_look():
    restored = Dataset.from_dict({k: v for k, v in _dataset().to_dict().items() if not k.startswith('marker_')})
    assert (restored.marker_fill, restored.marker_edge, restored.marker_edge_width) == ('solid', 'same', 1.0)


# --- 描画 ---

def test_hollow_scatter_has_no_fill_and_a_series_colored_edge():
    artist = _draw(_dataset(marker_fill='hollow'))
    assert len(artist.get_facecolors()) == 0
    assert _rgba(artist.get_edgecolors()) == _rgba(to_rgba(RED))


def test_custom_fill_edge_color_and_width():
    artist = _draw(_dataset(marker_fill='color', marker_face_color='#00ff00',
                            marker_edge='color', marker_edge_color='#000000', marker_edge_width=2.5))
    assert _rgba(artist.get_facecolors()) == _rgba(to_rgba('#00ff00'))
    assert _rgba(artist.get_edgecolors()) == _rgba(to_rgba('#000000'))
    assert list(artist.get_linewidths()) == [2.5]


def test_hollow_does_not_erase_line_only_markers():
    """+ や × は塗りの色で線を引くので、白抜きにしても消えない。枠線の色を指定すればその色で引く。"""
    artist = _draw(_dataset(marker='+', marker_fill='hollow', marker_edge='color', marker_edge_color='#0000ff'))
    assert _rgba(artist.get_facecolors()) == _rgba(to_rgba('#0000ff'))


def test_line_and_scatter_markers():
    artist = _draw(_dataset(plot_type='Line+Scatter', marker_fill='hollow',
                            marker_edge='color', marker_edge_color='#000000', marker_edge_width=2.0))
    assert artist.get_markerfacecolor() == 'none'
    assert artist.get_markeredgecolor() == '#000000'
    assert artist.get_markeredgewidth() == 2.0
    assert artist.get_color() == RED


def test_hollow_color_by_column_keeps_the_colormap_on_the_edges():
    artist = _draw(_dataset(plot_type=COLOR_BY_COLUMN_PLOT_TYPE, marker_fill='hollow'))
    artist.figure.canvas.draw()
    assert len(artist.get_facecolors()) == 0
    assert len({tuple(c) for c in artist.get_edgecolors()}) == 3


def test_color_by_column_ignores_custom_fill_color():
    """塗りは色の対応が受け持つ。"""
    artist = _draw(_dataset(plot_type=COLOR_BY_COLUMN_PLOT_TYPE, marker_fill='color', marker_face_color='#00ff00'))
    artist.figure.canvas.draw()
    assert len({tuple(c) for c in artist.get_facecolors()}) == 3


# --- Python スクリプトの書き出しが画面と同じ見た目になる ---

def _script_artist(ds):
    project = ProjectModel()
    project.datasets = [ds]
    project.all_plot_settings = [{}]
    plt.close('all')
    namespace = {}
    exec(compile(generate_python_script(project), '<generated>', 'exec'), namespace)
    ax = plt.gcf().axes[0]
    artists = ax.collections or ax.lines
    artist = artists[0]
    plt.gcf().canvas.draw()
    return artist


@pytest.mark.parametrize("overrides", [
    dict(marker_fill='hollow'),
    dict(marker_fill='color', marker_face_color='#00ff00', marker_edge='color', marker_edge_color='#000000',
         marker_edge_width=3.0),
    dict(marker='x', marker_edge='color', marker_edge_color='#0000ff', marker_edge_width=2.0),
    dict(plot_type=COLOR_BY_COLUMN_PLOT_TYPE, marker_fill='hollow'),
    dict(plot_type=COLOR_BY_COLUMN_PLOT_TYPE, marker_fill='hollow', marker_edge='color', marker_edge_color='#000000'),
])
def test_script_export_matches_the_screen_for_scatter(overrides):
    screen = _draw(_dataset(**overrides))
    screen.figure.canvas.draw()
    script = _script_artist(_dataset(**overrides))
    assert _rgba(script.get_facecolors()) == _rgba(screen.get_facecolors())
    assert _rgba(script.get_edgecolors()) == _rgba(screen.get_edgecolors())
    assert list(script.get_linewidths()) == list(screen.get_linewidths())


def test_script_export_matches_the_screen_for_line_and_scatter():
    overrides = dict(plot_type='Line+Scatter', marker_fill='color', marker_face_color='#00ff00',
                     marker_edge='color', marker_edge_color='#000000', marker_edge_width=2.0)
    screen = _draw(_dataset(**overrides))
    script = _script_artist(_dataset(**overrides))
    for getter in ('get_markerfacecolor', 'get_markeredgecolor', 'get_markeredgewidth'):
        assert getattr(script, getter)() == getattr(screen, getter)()


def test_script_export_is_unchanged_for_default_markers():
    project = ProjectModel()
    project.datasets = [_dataset()]
    project.all_plot_settings = [{}]
    script = generate_python_script(project)
    assert "axes[0].scatter(x, y, marker='o', s=6.0 ** 2, color='#ff0000', alpha=1.0, label='d')" in script


# --- プロパティ欄 ---

@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.show()
    QApplication.processEvents()
    yield w
    w.close()


def _add(window, **overrides):
    ds = _dataset(**overrides)
    window._add_dataset(ds)
    for _ in range(3):
        QApplication.processEvents()
    return ds


def _shown(widget):
    return not widget.isHidden()


def test_marker_rows_follow_the_plot_type_and_choices(window):
    ds = _add(window, plot_type='Line')
    assert not _shown(window.marker_fill_combo) and not _shown(window.marker_edge_width_spinbox)

    window.ui.plot_type_combo.setCurrentText('Scatter')
    assert ds.plot_type == 'Scatter'
    assert _shown(window.marker_fill_combo) and _shown(window.marker_edge_width_spinbox)
    assert not _shown(window.marker_face_color_picker) and not _shown(window.marker_edge_color_picker)

    window.marker_fill_combo.setCurrentIndex(window.marker_fill_combo.findData('color'))
    window.marker_edge_combo.setCurrentIndex(window.marker_edge_combo.findData('color'))
    assert _shown(window.marker_face_color_picker) and _shown(window.marker_edge_color_picker)

    window.ui.marker_combo.setCurrentIndex(window.ui.marker_combo.findData('+'))
    assert not _shown(window.marker_fill_combo) and not _shown(window.marker_face_color_picker)
    assert _shown(window.marker_edge_combo)


def test_custom_fill_color_cannot_be_chosen_for_color_by_column(window):
    _add(window, plot_type=COLOR_BY_COLUMN_PLOT_TYPE)
    combo = window.marker_fill_combo
    assert not combo.model().item(combo.findData('color')).isEnabled()
    assert combo.model().item(combo.findData('hollow')).isEnabled()


def test_editing_the_marker_rows_changes_the_dataset_with_undo(window):
    ds = _add(window)
    window.marker_fill_combo.setCurrentIndex(window.marker_fill_combo.findData('hollow'))
    window.marker_edge_width_spinbox.setValue(2.5)
    window.marker_edge_color_picker._apply_color_name('#123456')
    assert (ds.marker_fill, ds.marker_edge_width, ds.marker_edge_color) == ('hollow', 2.5, '#123456')

    for _ in range(3):
        window.undo_stack.undo()
    assert (ds.marker_fill, ds.marker_edge_width, ds.marker_edge_color) == ('solid', 1.0, '#000000')


def test_selecting_a_dataset_shows_its_marker_style(window):
    _add(window, marker='*', marker_fill='color', marker_face_color='#00ff00', marker_edge_width=0.5)
    assert window.ui.marker_combo.currentData() == '*'
    assert window.marker_fill_combo.currentData() == 'color'
    assert window.marker_face_color_picker.color_name() == '#00ff00'
    assert window.marker_edge_width_spinbox.value() == 0.5


def test_style_copy_and_templates_carry_the_marker_style():
    assert {'marker_fill', 'marker_face_color', 'marker_edge', 'marker_edge_color',
            'marker_edge_width'} <= set(STYLE_ATTRS)


@pytest.mark.parametrize("plot_type, shown", [
    ('Line', False), ('Area', False), ('Bar', False), ('Step', False),
    ('Scatter', True), ('Line+Scatter', True), (COLOR_BY_COLUMN_PLOT_TYPE, True),
])
def test_marker_shape_and_size_rows_only_for_types_that_draw_markers(window, plot_type, shown):
    _add(window, plot_type=plot_type)
    for widget in (window.ui.marker_combo, window.ui.markersize_spinbox, window.marker_edge_width_spinbox):
        assert _shown(widget) is shown


def test_plugin_plot_types_keep_the_marker_rows(window):
    """プラグインの種類はマーカーを使うかもしれない。"""
    _add(window, plot_type='SomePluginType')
    assert _shown(window.ui.marker_combo) and _shown(window.marker_fill_combo)


def test_marker_choices_show_names_and_keep_the_saved_symbols(window):
    combo = window.ui.marker_combo
    assert (combo.itemText(0), combo.itemData(0)) == ("円", 'o')
    assert combo.itemText(combo.findData('None')) == "なし"

    ds = _add(window)
    combo.setCurrentIndex(combo.findData('p'))
    assert ds.marker == 'p'
    combo.setCurrentIndex(combo.findData('None'))
    assert ds.marker is None


def test_a_marker_symbol_missing_from_the_choices_is_shown_and_kept(window):
    """手で書いたファイルやプラグインの記号を、選択肢に無いからと別の形にしない。"""
    ds = _add(window, marker='8')
    combo = window.ui.marker_combo
    assert combo.currentData() == '8'
    assert ds.marker == '8'
