# tests/test_color_by_column_scatter.py
"""
3列目の値による点の色分け(改善ボード D-2、plot_type='Z-Color Scatter')
に対するテスト。

既存の 'Density Scatter' が「点の密度」で色を付けるのに対し、こちらは
z_col_name で選んだ任意の列の値で色を付ける(温度・時間・濃度・深さ等の
測定条件を1枚の散布図に載せる定番の表現)。colormap/vmin/vmax と
カラーバーは2Dマップ(項目C-508/C-501)用の実装をそのまま流用している。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from gui.canvas import MplCanvas
from core.dataset import Dataset, COLOR_BY_COLUMN_PLOT_TYPE


@pytest.fixture
def canvas():
    c = MplCanvas(width=4, height=3, dpi=80)
    yield c
    plt.close(c.fig)


def _df():
    return pd.DataFrame({
        "x": [0.0, 1.0, 2.0, 3.0],
        "y": [0.0, 1.0, 4.0, 9.0],
        "temp": [10.0, 20.0, 30.0, 40.0],
    })


def _make(**kwargs):
    params = dict(
        name="s", df=_df(), x_col_name="x", y_col_name="y",
        plot_type=COLOR_BY_COLUMN_PLOT_TYPE, color='#112233',
        z_col_name="temp", colormap='plasma',
    )
    params.update(kwargs)
    return Dataset(**params)


# --- Dataset.z_data ---

def test_z_data_returns_the_selected_column():
    ds = _make()
    assert list(ds.z_data) == [10.0, 20.0, 30.0, 40.0]


def test_z_data_is_none_when_no_column_selected():
    assert _make(z_col_name=None).z_data is None


def test_z_data_is_none_when_the_column_no_longer_exists():
    assert _make(z_col_name="missing").z_data is None


def test_z_data_honours_the_row_mask():
    """x_data/y_data と同じく visible_df 経由であること。df から直接取ると、
    1行でもマスクした時点で点と色の対応が1つずつずれる。"""
    ds = _make()
    ds.masked_row_indices = [1]
    assert list(ds.z_data) == [10.0, 30.0, 40.0]
    assert len(ds.z_data) == len(ds.x_data)


# --- 描画 ---

def test_points_are_coloured_by_the_column_values(canvas):
    ds = _make()
    canvas.redraw_all([ds], 1, 1, [{}])

    assert ds.artist.get_array().tolist() == [10.0, 20.0, 30.0, 40.0]
    assert ds.artist.get_cmap().name == 'plasma'


def test_colour_values_stay_aligned_with_points_when_rows_are_masked(canvas):
    """回帰テスト: マスクした行の分だけ色がずれないこと。"""
    ds = _make()
    ds.masked_row_indices = [1]
    canvas.redraw_all([ds], 1, 1, [{}])

    offsets = np.asarray(ds.artist.get_offsets())
    assert offsets[:, 0].tolist() == [0.0, 2.0, 3.0]
    assert ds.artist.get_array().tolist() == [10.0, 30.0, 40.0]


def test_vmin_vmax_are_passed_through(canvas):
    ds = _make(vmin=15.0, vmax=35.0)
    canvas.redraw_all([ds], 1, 1, [{}])

    assert ds.artist.norm.vmin == pytest.approx(15.0)
    assert ds.artist.norm.vmax == pytest.approx(35.0)


def test_without_vmin_vmax_the_range_follows_the_data(canvas):
    ds = _make()
    canvas.redraw_all([ds], 1, 1, [{}])

    assert ds.artist.norm.vmin == pytest.approx(10.0)
    assert ds.artist.norm.vmax == pytest.approx(40.0)


def test_falls_back_to_a_single_colour_when_no_z_column(canvas):
    """Z列未選択でもクラッシュせず、通常のScatter(単色)として描かれること
    (Density Scatter が gaussian_kde 失敗時にそうするのと同じ方針)。"""
    ds = _make(z_col_name=None)
    canvas.redraw_all([ds], 1, 1, [{}])

    assert ds.artist is not None
    assert ds.artist.get_array() is None  # 値による配色をしていない


def test_falls_back_when_the_z_column_was_deleted(canvas):
    ds = _make(z_col_name="missing")
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.artist.get_array() is None


def test_marker_and_size_follow_the_dataset_style(canvas):
    ds = _make(markersize=9.0)
    canvas.redraw_all([ds], 1, 1, [{}])
    assert ds.artist.get_sizes()[0] == pytest.approx(81.0)


# --- カラーバー(既存の2Dマップ用経路への相乗り) ---

def test_registers_itself_as_the_colorbar_mappable(canvas):
    ds = _make()
    canvas.redraw_all([ds], 1, 1, [{'colorbar_enabled': True}])

    assert canvas._axis_2d_mappables.get(0) is ds.artist


def test_single_colour_fallback_does_not_register_a_colorbar(canvas):
    ds = _make(z_col_name=None)
    canvas.redraw_all([ds], 1, 1, [{'colorbar_enabled': True}])

    assert canvas._axis_2d_mappables.get(0) is None


def test_a_2d_map_on_the_same_axis_keeps_the_colorbar(canvas):
    """カラーバーは1軸に最大1つ。2Dマップと同居する場合は、既存の挙動を
    変えないよう2Dマップ側を優先する。"""
    grid_df = pd.DataFrame({
        "x": [0, 0, 1, 1], "y": [0, 1, 0, 1], "z": [1.0, 2.0, 3.0, 4.0],
    })
    heatmap = Dataset(name="map", df=grid_df, x_col_name="x", y_col_name="y",
                      plot_type='Line', color='#112233',
                      data_kind='2d_grid', z_col_name="z")
    scatter = _make()

    canvas.redraw_all([heatmap, scatter], 1, 1, [{'colorbar_enabled': True}])

    assert canvas._axis_2d_mappables.get(0) is heatmap.artist
    assert canvas._axis_2d_mappables.get(0) is not scatter.artist


# --- ウォーターフォールとの組み合わせ ---

def test_combines_with_waterfall_offsets(canvas):
    """plot_typeとは独立した積み重ねフラグ(項目80/109)と併用できること。"""
    ds0 = _make(name="a", waterfall_enabled=True, waterfall_offset_x=10.0, waterfall_offset_y=100.0)
    ds1 = _make(name="b", waterfall_enabled=True, waterfall_offset_x=10.0, waterfall_offset_y=100.0)
    canvas.redraw_all([ds0, ds1], 1, 1, [{}])

    offsets = np.asarray(ds1.artist.get_offsets())
    assert offsets[:, 0].tolist() == [10.0, 11.0, 12.0, 13.0]
    # 色は積み重ねの影響を受けない(あくまで列の値)
    assert ds1.artist.get_array().tolist() == [10.0, 20.0, 30.0, 40.0]


# --- プロパティパネルのコントロール表示 ---

def _make_isolated_plotter_app(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    import gui.main_window as main_window_module
    from gui.main_window import PlotterApp

    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 600)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def test_plot_type_is_offered_in_the_combo(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        items = [window.ui.plot_type_combo.itemText(i)
                 for i in range(window.ui.plot_type_combo.count())]
        assert COLOR_BY_COLUMN_PLOT_TYPE in items
    finally:
        window.close()


def test_z_column_and_colormap_controls_appear_for_this_plot_type(tmp_path, monkeypatch):
    """Z列・カラーマップ・値域は2Dマップと共用なので、この1D plot_type でも出す。
    グリッド固有の設定(表示モード・等高線レベル・補間方法)は出さない。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        ds = _make()
        window._add_dataset(ds, select=True)

        assert window.z_col_combo.isVisible()
        assert window.colormap_combo.isVisible()
        assert window.color_range_auto_checkbox.isVisible()
        assert window.vmin_spinbox.isVisible()
        # グリッド固有のものは隠れたまま
        assert not window.map_display_mode_combo.isVisible()
        assert not window.contour_levels_spinbox.isVisible()
        assert not window.grid_interp_method_combo.isVisible()
    finally:
        window.close()


def test_z_column_controls_stay_hidden_for_a_plain_scatter(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        ds = _make(plot_type='Scatter')
        window._add_dataset(ds, select=True)

        assert not window.z_col_combo.isVisible()
        assert not window.colormap_combo.isVisible()
        assert not window.vmin_spinbox.isVisible()
    finally:
        window.close()


def test_2d_grid_dataset_still_shows_every_grid_control(tmp_path, monkeypatch):
    """既存の2Dマップ側の表示が、今回の分岐追加で減っていないこと。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        grid_df = pd.DataFrame({
            "x": [0, 0, 1, 1], "y": [0, 1, 0, 1], "z": [1.0, 2.0, 3.0, 4.0],
        })
        ds = Dataset(name="map", df=grid_df, x_col_name="x", y_col_name="y",
                     plot_type='Line', color='#112233',
                     data_kind='2d_grid', z_col_name="z")
        window._add_dataset(ds, select=True)

        assert window.z_col_combo.isVisible()
        assert window.colormap_combo.isVisible()
        assert window.map_display_mode_combo.isVisible()
        assert window.contour_levels_spinbox.isVisible()
        assert window.grid_interp_method_combo.isVisible()
    finally:
        window.close()


# --- スタンドアロンスクリプト書き出し ---

def _generate_script(datasets, settings):
    from models.project import ProjectModel
    from core.script_export import generate_python_script

    project = ProjectModel()
    project.datasets = list(datasets)
    project.all_plot_settings = list(settings)
    project.layout_rows, project.layout_cols = 1, 1
    return generate_python_script(project)


def test_script_export_reproduces_the_colour_mapping():
    """Density Scatter は gaussian_kde 依存のため Line へ代替出力されるが、
    こちらは純粋な matplotlib 呼び出しなのでそのまま再現できる。"""
    src = _generate_script([_make()], [{'colorbar_enabled': True}])

    assert "z = np.array([10.0, 20.0, 30.0, 40.0])" in src
    assert "c=z" in src
    assert "cmap='plasma'" in src
    # 先頭の定型コメント(「未対応のplot_typeはLineとして代替出力されます」)は
    # 常に入るため、データセットごとの代替出力コメントが出ていないことで判定する。
    assert "はプラグイン依存のため、Lineとして代替出力しています" not in src


def test_script_export_emits_a_colorbar():
    src = _generate_script([_make()], [{'colorbar_enabled': True}])
    assert "fig.colorbar(scatter_mesh0" in src


def test_script_export_falls_back_to_plain_scatter_without_a_z_column():
    src = _generate_script([_make(z_col_name=None)], [{}])
    assert "c=z" not in src
    assert ".scatter(x, y, marker=" in src


def test_script_export_lets_a_2d_map_keep_the_colorbar():
    """同じ軸に2Dマップがある場合、カラーバーは2Dマップ側に付ける
    (gui/canvas.py 側の優先順位と揃える)。"""
    grid_df = pd.DataFrame({
        "x": [0, 0, 1, 1], "y": [0, 1, 0, 1], "z": [1.0, 2.0, 3.0, 4.0],
    })
    heatmap = Dataset(name="map", df=grid_df, x_col_name="x", y_col_name="y",
                      plot_type='Line', color='#112233',
                      data_kind='2d_grid', z_col_name="z")
    src = _generate_script([_make(), heatmap], [{'colorbar_enabled': True}])

    assert "fig.colorbar(mesh0" in src
    assert "scatter_mesh0" not in src


def test_generated_script_actually_runs(tmp_path):
    """生成したスクリプトが単体で実行できること(構文・API誤りの検出)。"""
    import subprocess
    import sys

    src = _generate_script([_make()], [{'colorbar_enabled': True, 'colorbar_label': 'Temp'}])
    script = tmp_path / "out.py"
    script.write_text(
        "import matplotlib\nmatplotlib.use('Agg')\n" + src.replace("plt.show()", ""),
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(script)], capture_output=True,
                            text=True, timeout=180)
    assert result.returncode == 0, result.stderr
