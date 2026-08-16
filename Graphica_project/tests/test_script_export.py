# tests/test_script_export.py
"""core/script_export.py の generate_python_script (項目C-1103) に対するテスト。

生成されたコードが実際に実行可能であることを検証するのが最も重要な確認
(構文エラーや存在しないAPI呼び出しは、単なる文字列アサーションでは検知
できないため)。matplotlib.use("Agg")でヘッドレス環境でも安全に実行する。
"""
import ast
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
import pandas as pd
import pytest

from core.dataset import Dataset
from core.script_export import generate_python_script
from models.project import ProjectModel


def _make_project(datasets=None, all_plot_settings=None, rows=1, cols=1, layout_mode='grid'):
    project = ProjectModel()
    project.datasets = datasets or []
    project.all_plot_settings = all_plot_settings if all_plot_settings is not None else [{}] * (rows * cols)
    project.layout_rows = rows
    project.layout_cols = cols
    project.layout_mode = layout_mode
    return project


def _make_dataset(name="d0", plot_type="Line", **overrides):
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]})
    kwargs = dict(name=name, df=df, x_col_name="x", y_col_name="y", plot_type=plot_type)
    kwargs.update(overrides)
    return Dataset(**kwargs)


def _exec_script(script_text):
    """生成スクリプトを実際にexec()し、構文/実行時エラーが無いことを確認する。"""
    plt.close('all')
    namespace = {}
    # plt.show()はheadless環境でブロックしないよう無害化(Aggバックエンドでは
    # 実際には何も表示されないが、念のため明示的にモックする必要はなく、
    # Aggバックエンドのshow()は既にno-op)。
    exec(compile(script_text, '<generated>', 'exec'), namespace)
    return namespace


def test_generated_script_is_valid_python_syntax():
    ds = _make_dataset()
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)
    ast.parse(script)  # SyntaxErrorが出なければOK


def test_generated_script_executes_without_error_for_simple_line_plot():
    ds = _make_dataset(plot_type="Line", color="#ff0000")
    project = _make_project(datasets=[ds], all_plot_settings=[{"title": "My Plot", "x_label": "X", "y_label": "Y"}])
    script = generate_python_script(project)

    _exec_script(script)  # 例外が出なければOK


@pytest.mark.parametrize("plot_type", ["Line", "Scatter", "Line+Scatter", "Area", "Bar"])
def test_generated_script_executes_for_each_builtin_plot_type(plot_type):
    ds = _make_dataset(plot_type=plot_type)
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)

    _exec_script(script)


def test_generated_script_handles_unknown_plugin_plot_type_as_line_with_comment():
    ds = _make_dataset(plot_type="SomePluginPlotType")
    project = _make_project(datasets=[ds])

    script = generate_python_script(project)

    assert "プラグイン依存のため" in script
    _exec_script(script)  # Lineとして代替出力されるため実行は成功する


def test_generated_script_embeds_data_values():
    ds = _make_dataset()
    project = _make_project(datasets=[ds])

    script = generate_python_script(project)

    assert "4.0" in script and "5.0" in script and "6.0" in script


def test_generated_script_handles_nan_values_without_syntax_error():
    df = pd.DataFrame({"x": [1.0, 2.0, float('nan')], "y": [4.0, float('nan'), 6.0]})
    ds = Dataset(name="with_nan", df=df, x_col_name="x", y_col_name="y")
    project = _make_project(datasets=[ds])

    script = generate_python_script(project)

    assert "float('nan')" in script
    _exec_script(script)


def test_generated_script_skips_invisible_datasets():
    ds_visible = _make_dataset(name="visible_ds")
    ds_hidden = _make_dataset(name="hidden_ds")
    ds_hidden.visible = False
    project = _make_project(datasets=[ds_visible, ds_hidden])

    script = generate_python_script(project)

    assert "visible_ds" in script
    assert "hidden_ds" not in script


def test_generated_script_creates_secondary_axis_for_use_secondary_y_datasets():
    ds_primary = _make_dataset(name="primary")
    ds_secondary = _make_dataset(name="secondary", use_secondary_y=True)
    project = _make_project(datasets=[ds_primary, ds_secondary])

    script = generate_python_script(project)

    assert "twinx()" in script
    namespace = _exec_script(script)
    assert "ax0_secondary" in namespace


def test_generated_script_handles_multiple_grid_subplots():
    ds0 = _make_dataset(name="d0", subplot_target=0)
    ds1 = _make_dataset(name="d1", subplot_target=1)
    project = _make_project(
        datasets=[ds0, ds1],
        all_plot_settings=[{"title": "First"}, {"title": "Second"}],
        rows=1, cols=2,
    )

    script = generate_python_script(project)

    namespace = _exec_script(script)
    assert len(namespace['axes']) == 2


def test_generated_script_handles_free_layout():
    ds = _make_dataset(subplot_target=0)
    project = _make_project(
        datasets=[ds],
        all_plot_settings=[{"free_rect": (0.1, 0.1, 0.5, 0.5)}],
        layout_mode='free',
    )

    script = generate_python_script(project)

    assert "fig.add_axes" in script
    _exec_script(script)


def test_generated_script_applies_axis_limits_when_autoscale_disabled():
    ds = _make_dataset()
    project = _make_project(
        datasets=[ds],
        all_plot_settings=[{"x_autoscale": False, "x_min": 0.0, "x_max": 10.0}],
    )

    script = generate_python_script(project)

    assert "set_xlim(0.0, 10.0)" in script


def test_generated_script_applies_log_scale():
    ds = _make_dataset()
    project = _make_project(datasets=[ds], all_plot_settings=[{"x_log": True, "y_log": True}])

    script = generate_python_script(project)

    assert "set_xscale('log')" in script
    assert "set_yscale('log')" in script


def test_generated_script_has_no_trailing_whitespace_issues_and_is_nonempty():
    project = _make_project(datasets=[])
    script = generate_python_script(project)
    assert script.strip() != ""
    ast.parse(script)


# =============================================================================
# 2Dグリッドデータ(ヒートマップ、項目C-508)
# =============================================================================

def _make_2d_dataset(name="heatmap", **overrides):
    xs, ys = [0.0, 1.0, 2.0], [10.0, 20.0]
    x, y, z = [], [], []
    for yi in ys:
        for xi in xs:
            x.append(xi)
            y.append(yi)
            z.append(xi + yi)
    df = pd.DataFrame({'x': x, 'y': y, 'z': z})
    kwargs = dict(name=name, df=df, x_col_name='x', y_col_name='y',
                  data_kind='2d_grid', z_col_name='z')
    kwargs.update(overrides)
    return Dataset(**kwargs)


def test_generated_script_executes_for_heatmap_dataset():
    ds = _make_2d_dataset()
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)
    ast.parse(script)
    _exec_script(script)  # 例外を投げないこと


def test_generated_script_uses_pcolormesh_and_colormap_for_heatmap():
    ds = _make_2d_dataset(colormap='plasma')
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)
    assert "pcolormesh" in script
    assert "cmap='plasma'" in script


def test_generated_script_does_not_treat_heatmap_as_1d_plot_call():
    """2Dデータセットはplot_type分岐(_emit_dataset_plot_call)を経由しない
    (長形式のx/yをそのままLine描画すると無意味なため)。"""
    ds = _make_2d_dataset(plot_type='Line')
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)
    assert ".plot(x, y" not in script


def test_generated_script_adds_colorbar_by_default_for_heatmap():
    ds = _make_2d_dataset()
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)
    assert "fig.colorbar(" in script


def test_generated_script_omits_colorbar_when_disabled():
    ds = _make_2d_dataset()
    project = _make_project(datasets=[ds], all_plot_settings=[{"colorbar_enabled": False}])
    script = generate_python_script(project)
    assert "fig.colorbar(" not in script


def test_generated_script_applies_colorbar_label_and_position():
    ds = _make_2d_dataset()
    project = _make_project(
        datasets=[ds],
        all_plot_settings=[{"colorbar_label": "強度 (a.u.)", "colorbar_position": "bottom"}],
    )
    script = generate_python_script(project)
    assert "cbar.set_label('強度 (a.u.)')" in script
    assert "location='bottom'" in script
    _exec_script(script)


def test_generated_script_applies_vmin_vmax_for_heatmap():
    ds = _make_2d_dataset(vmin=-5.0, vmax=50.0)
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)
    assert "vmin=-5.0" in script
    assert "vmax=50.0" in script
    _exec_script(script)


def test_generated_script_handles_scattered_heatmap_data():
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 10, size=30)
    y = rng.uniform(0, 10, size=30)
    z = x + y
    df = pd.DataFrame({'x': x, 'y': y, 'z': z})
    ds = Dataset(name="scattered", df=df, x_col_name='x', y_col_name='y',
                 data_kind='2d_grid', z_col_name='z', grid_resolution=[15, 15])
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)
    _exec_script(script)


def test_generated_script_skips_heatmap_with_invalid_grid_without_crashing():
    df = pd.DataFrame({'x': [math.nan, math.nan], 'y': [1.0, 2.0], 'z': [1.0, 2.0]})
    ds = Dataset(name="bad", df=df, x_col_name='x', y_col_name='y',
                 data_kind='2d_grid', z_col_name='z')
    project = _make_project(datasets=[ds])
    script = generate_python_script(project)
    ast.parse(script)
    _exec_script(script)  # 例外を投げないこと
    assert "スキップ" in script


def test_generated_script_handles_mixed_1d_and_2d_datasets_on_same_subplot():
    ds_2d = _make_2d_dataset(subplot_target=0)
    ds_1d = _make_dataset(name="line", subplot_target=0)
    project = _make_project(datasets=[ds_2d, ds_1d])
    script = generate_python_script(project)
    assert "pcolormesh" in script
    assert ".plot(x, y" in script
    _exec_script(script)
