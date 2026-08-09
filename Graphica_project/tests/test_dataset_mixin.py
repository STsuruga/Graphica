# tests/test_dataset_mixin.py
"""
gui/mixins/dataset_mixin.py の DatasetMixin に対する回帰テスト。

現時点では規格化(ノーマライズ)機能 (項目78, _on_normalize_dataset) のみを対象とする。
PlotterApp のインスタンス化パターンは tests/test_main_window.py の
_make_isolated_plotter_app に倣う (QSettingsを一時ファイルにリダイレクトする)。

_on_normalize_dataset はモーダルダイアログ (NormalizeDatasetDialog) を表示するため、
テストでは gui.mixins.dataset_mixin.NormalizeDatasetDialog を、実際の exec() を
呼ばずに設定値を返すだけの軽量なフェイクに差し替える。
"""
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import gui.main_window as main_window_module
import gui.mixins.dataset_mixin as dataset_mixin_module
from gui.main_window import PlotterApp
from gui.dialogs import NormalizeDatasetDialog, PluginParamDialog
from core.dataset import Dataset
from core.plugin_types import PluginProcessor, PluginAnalyzer, AnalysisResult


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _add_and_select_dataset(window, dataset):
    """データセットを追加し、そのままカレントアイテムとして選択された状態にする"""
    window._add_dataset(dataset, None, select=True)
    return dataset


def _patch_normalize_dialog(monkeypatch, mode, reference_x, output_name, accepted=True):
    """
    NormalizeDatasetDialog を、実際にウィジェットを構築したり exec() で
    イベントループをブロックしたりしない軽量なフェイクに差し替える。
    MODE_MAX / MODE_X_VALUE クラス属性は継承でそのまま使えるようにする。
    """
    class FakeNormalizeDialog(NormalizeDatasetDialog):
        def __init__(self, name, x_min=None, x_max=None, parent=None):
            # 実ダイアログの __init__ (QWidget構築) は一切呼ばない
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        def get_settings(self):
            return mode, reference_x, output_name

    monkeypatch.setattr(dataset_mixin_module, "NormalizeDatasetDialog", FakeNormalizeDialog)


def _patch_warning_capture(monkeypatch):
    """QMessageBox.warning の呼び出しを記録するリストを返す"""
    calls = []

    def fake_warning(*args, **kwargs):
        calls.append(args)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(fake_warning))
    return calls


def test_normalize_max_mode_peak_becomes_one(tmp_path, monkeypatch):
    """最大値基準: 規格化後のデータセットでYの最大値が1.0になる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [1.0, 4.0, 2.0, 3.0]})
    dataset = Dataset(name="sample", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, dataset)

    before_count = len(window.project.datasets)
    _patch_normalize_dialog(monkeypatch, NormalizeDatasetDialog.MODE_MAX, None, "sample_normalized")

    window._on_normalize_dataset()

    assert len(window.project.datasets) == before_count + 1
    new_dataset = window.project.datasets[-1]
    assert new_dataset.name == "sample_normalized"
    np.testing.assert_allclose(new_dataset.y_data, np.array([0.25, 1.0, 0.5, 0.75]))
    assert new_dataset.y_data.max() == pytest.approx(1.0)
    # 元のデータセットは変更されていない (非破壊)
    np.testing.assert_allclose(dataset.y_data, np.array([1.0, 4.0, 2.0, 3.0]))


def test_normalize_x_value_mode_interpolates(tmp_path, monkeypatch):
    """特定X値での強度基準: 指定X値でのYを線形補間して基準値とする"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [10.0, 20.0, 30.0, 40.0]})
    dataset = Dataset(name="sample", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, dataset)

    # x=1.5 は 1 と 2 の中間なので、補間値は (20+30)/2 = 25
    _patch_normalize_dialog(
        monkeypatch, NormalizeDatasetDialog.MODE_X_VALUE, 1.5, "sample_normalized"
    )

    window._on_normalize_dataset()

    new_dataset = window.project.datasets[-1]
    np.testing.assert_allclose(new_dataset.y_data, np.array([0.4, 0.8, 1.2, 1.6]))


def test_normalize_max_mode_excludes_masked_rows(tmp_path, monkeypatch):
    """
    最大値基準の規格化は masked_row_indices で除外された行を無視する
    (visible_df/x_data/y_dataを経由するため)。マスクされた行が真の最大値を
    持っていても、規格化の基準にはならないことを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [1.0, 100.0, 2.0, 3.0]})
    # インデックス1 (Y=100, 真の最大値) をマスクして除外する
    dataset = Dataset(name="sample", df=df, x_col_name='x', y_col_name='y', masked_row_indices=[1])
    _add_and_select_dataset(window, dataset)

    _patch_normalize_dialog(monkeypatch, NormalizeDatasetDialog.MODE_MAX, None, "sample_normalized")

    window._on_normalize_dataset()

    new_dataset = window.project.datasets[-1]
    # マスク除外後の可視データは y=[1,2,3] なので、最大値は3のはず
    np.testing.assert_allclose(new_dataset.y_data, np.array([1 / 3, 2 / 3, 1.0]))
    assert len(new_dataset.y_data) == 3


def test_normalize_out_of_range_reference_x_warns_and_aborts(tmp_path, monkeypatch):
    """基準X値がデータのX範囲外なら警告を出し、データセットを追加しない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [10.0, 20.0, 30.0, 40.0]})
    dataset = Dataset(name="sample", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, dataset)

    before_count = len(window.project.datasets)
    warnings = _patch_warning_capture(monkeypatch)
    _patch_normalize_dialog(
        monkeypatch, NormalizeDatasetDialog.MODE_X_VALUE, 999.0, "sample_normalized"
    )

    window._on_normalize_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_normalize_near_zero_reference_guards(tmp_path, monkeypatch):
    """基準値が0に近い場合は警告を出し、データセットを追加しない (0除算のガード)"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [0.0, 0.0, 0.0, 0.0]})
    dataset = Dataset(name="sample", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, dataset)

    before_count = len(window.project.datasets)
    warnings = _patch_warning_capture(monkeypatch)
    _patch_normalize_dialog(monkeypatch, NormalizeDatasetDialog.MODE_MAX, None, "sample_normalized")

    window._on_normalize_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_normalize_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    """ダイアログでキャンセルした場合は何も追加されない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [1.0, 4.0, 2.0, 3.0]})
    dataset = Dataset(name="sample", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, dataset)

    before_count = len(window.project.datasets)
    _patch_normalize_dialog(
        monkeypatch, NormalizeDatasetDialog.MODE_MAX, None, "sample_normalized", accepted=False
    )

    window._on_normalize_dataset()

    assert len(window.project.datasets) == before_count


# --- カラーマップから自動配色(項目C-805) ---

def _patch_colormap_choice(monkeypatch, cmap_name, accepted=True):
    """QInputDialog.getItem を、実際にダイアログを表示せず指定の選択結果を返すフェイクに差し替える"""
    def fake_get_item(*args, **kwargs):
        return (cmap_name, accepted)
    monkeypatch.setattr(dataset_mixin_module.QInputDialog, "getItem", staticmethod(fake_get_item))


def _make_simple_dataset(name):
    df = pd.DataFrame({'x': [0, 1, 2], 'y': [1.0, 2.0, 3.0]})
    return Dataset(name=name, df=df, x_col_name='x', y_col_name='y')


def test_colormap_auto_assign_applies_evenly_sampled_colors(tmp_path, monkeypatch):
    import matplotlib as mpl
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    window.ui.dataset_list_widget.selectAll()

    _patch_colormap_choice(monkeypatch, "viridis")
    window._on_auto_assign_colors_from_colormap()

    cmap = mpl.colormaps["viridis"]
    expected = [mpl.colors.to_hex(cmap(p)) for p in (0.0, 0.5, 1.0)]
    assert [ds.color for ds in datasets] == expected


def test_colormap_auto_assign_single_dataset_uses_midpoint_color(tmp_path, monkeypatch):
    import matplotlib as mpl
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("solo")
    _add_and_select_dataset(window, ds)

    _patch_colormap_choice(monkeypatch, "plasma")
    window._on_auto_assign_colors_from_colormap()

    cmap = mpl.colormaps["plasma"]
    assert ds.color == mpl.colors.to_hex(cmap(0.5))


def test_colormap_auto_assign_cancelled_leaves_colors_unchanged(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    original_color = ds.color

    _patch_colormap_choice(monkeypatch, "viridis", accepted=False)
    window._on_auto_assign_colors_from_colormap()

    assert ds.color == original_color


def test_colormap_auto_assign_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: calls.append(1) or ("viridis", True))
    )
    window._on_auto_assign_colors_from_colormap()
    assert calls == []  # ダイアログ自体を出さずに早期returnする


# --- register_processor()実行配線 (項目C-1: _on_run_plugin_processor) ---

def _patch_info_capture(monkeypatch):
    calls = []
    monkeypatch.setattr(
        dataset_mixin_module.QMessageBox, "information",
        staticmethod(lambda *a, **k: calls.append(a) or None)
    )
    return calls


def _patch_critical_capture(monkeypatch):
    calls = []
    monkeypatch.setattr(
        dataset_mixin_module.QMessageBox, "critical",
        staticmethod(lambda *a, **k: calls.append(a) or None)
    )
    return calls


def _patch_plugin_param_dialog(monkeypatch, values, accepted=True):
    class FakePluginParamDialog(PluginParamDialog):
        def __init__(self, title, param_schema, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        def get_values(self):
            return values

    monkeypatch.setattr(dataset_mixin_module, "PluginParamDialog", FakePluginParamDialog)


def _make_processor(fn, name="Smooth", category="general", param_schema=None, plugin_name="my_plugin"):
    return PluginProcessor(name=name, fn=fn, category=category,
                            param_schema=list(param_schema or []), plugin_name=plugin_name)


def _make_analyzer(fn, name="Peaks", output_kind="table", param_schema=None, plugin_name="my_plugin"):
    return PluginAnalyzer(name=name, fn=fn, output_kind=output_kind,
                           param_schema=list(param_schema or []), plugin_name=plugin_name)


def test_run_plugin_processor_no_dataset_selected_shows_info_and_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    info_calls = _patch_info_capture(monkeypatch)
    before_count = len(window.project.datasets)

    processor = _make_processor(lambda ds, params: ds)
    window._on_run_plugin_processor(processor)

    assert len(info_calls) == 1
    assert len(window.project.datasets) == before_count


def test_run_plugin_processor_success_adds_dataset_with_source_plugin(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)

    def fn(dataset, params):
        df = dataset.df.copy()
        return Dataset(name="processed", df=df, x_col_name='x', y_col_name='y')

    processor = _make_processor(fn, plugin_name="cool_plugin")
    window._on_run_plugin_processor(processor)

    assert len(window.project.datasets) == before_count + 1
    new_dataset = window.project.datasets[-1]
    assert new_dataset.name == "processed"
    assert new_dataset.source_plugin == "cool_plugin"


def test_run_plugin_processor_success_is_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)

    def fn(dataset, params):
        return Dataset(name="processed", df=dataset.df.copy(), x_col_name='x', y_col_name='y')

    processor = _make_processor(fn)
    window._on_run_plugin_processor(processor)
    assert len(window.project.datasets) == before_count + 1

    window.undo_stack.undo()
    assert len(window.project.datasets) == before_count


def test_run_plugin_processor_passes_param_dialog_values_to_fn(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)

    received = {}

    def fn(dataset, params):
        received.update(params)
        return Dataset(name="processed", df=dataset.df.copy(), x_col_name='x', y_col_name='y')

    _patch_plugin_param_dialog(monkeypatch, {"window": 7})
    processor = _make_processor(fn, param_schema=[{"name": "window", "type": "int"}])
    window._on_run_plugin_processor(processor)

    assert received == {"window": 7}


def test_run_plugin_processor_param_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)

    _patch_plugin_param_dialog(monkeypatch, {"window": 7}, accepted=False)
    processor = _make_processor(
        lambda dataset, params: Dataset(name="processed", df=dataset.df.copy(), x_col_name='x', y_col_name='y'),
        param_schema=[{"name": "window", "type": "int"}],
    )
    window._on_run_plugin_processor(processor)

    assert len(window.project.datasets) == before_count


def test_run_plugin_processor_fn_raises_shows_critical_and_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)
    critical_calls = _patch_critical_capture(monkeypatch)

    def fn(dataset, params):
        raise ValueError("boom")

    processor = _make_processor(fn)
    window._on_run_plugin_processor(processor)

    assert len(critical_calls) == 1
    assert len(window.project.datasets) == before_count


def test_run_plugin_processor_fn_returns_wrong_type_shows_critical(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)
    critical_calls = _patch_critical_capture(monkeypatch)

    processor = _make_processor(lambda dataset, params: "not a dataset")
    window._on_run_plugin_processor(processor)

    assert len(critical_calls) == 1
    assert len(window.project.datasets) == before_count


# --- register_analyzer()実行配線 (項目C-2: _on_run_plugin_analyzer) ---

def test_run_plugin_analyzer_no_dataset_selected_shows_info(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    info_calls = _patch_info_capture(monkeypatch)

    analyzer = _make_analyzer(lambda ds, params: AnalysisResult())
    window._on_run_plugin_analyzer(analyzer)

    assert len(info_calls) == 1


def test_run_plugin_analyzer_fn_raises_shows_critical(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    critical_calls = _patch_critical_capture(monkeypatch)

    def fn(dataset, params):
        raise RuntimeError("boom")

    analyzer = _make_analyzer(fn)
    window._on_run_plugin_analyzer(analyzer)

    assert len(critical_calls) == 1


def test_run_plugin_analyzer_fn_returns_wrong_type_shows_critical(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    critical_calls = _patch_critical_capture(monkeypatch)

    analyzer = _make_analyzer(lambda dataset, params: None)
    window._on_run_plugin_analyzer(analyzer)

    assert len(critical_calls) == 1


def test_run_plugin_analyzer_new_datasets_added_with_source_plugin_and_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)

    def fn(dataset, params):
        new_ds = Dataset(name="derived", df=dataset.df.copy(), x_col_name='x', y_col_name='y')
        return AnalysisResult(new_datasets=[new_ds])

    analyzer = _make_analyzer(fn, plugin_name="cool_plugin")
    window._on_run_plugin_analyzer(analyzer)

    assert len(window.project.datasets) == before_count + 1
    new_dataset = window.project.datasets[-1]
    assert new_dataset.name == "derived"
    assert new_dataset.source_plugin == "cool_plugin"

    window.undo_stack.undo()
    assert len(window.project.datasets) == before_count


def test_run_plugin_analyzer_annotations_appended_to_active_plot_settings(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    active_index = window.project.active_axis_index
    before_annotations = list(window.project.all_plot_settings[active_index].get('annotations', []))

    new_annotation = {'id': 'peak1', 'type': 'text', 'text': 'peak', 'xy': (1, 2), 'xytext': (1, 2), 'color': '#000000'}

    def fn(dataset, params):
        return AnalysisResult(annotations=[new_annotation])

    analyzer = _make_analyzer(fn)
    window._on_run_plugin_analyzer(analyzer)

    assert window.project.all_plot_settings[active_index]['annotations'] == before_annotations + [new_annotation]


def test_run_plugin_analyzer_table_shown_in_result_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    assert window.plugin_analysis_result_dialog is None

    def fn(dataset, params):
        return AnalysisResult(table="a,b\n1,2\n")

    analyzer = _make_analyzer(fn, name="Peaks")
    window._on_run_plugin_analyzer(analyzer)

    assert window.plugin_analysis_result_dialog is not None
    window.plugin_analysis_result_dialog.close()


def test_run_plugin_analyzer_passes_param_dialog_values_to_fn(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)

    received = {}

    def fn(dataset, params):
        received.update(params)
        return AnalysisResult()

    _patch_plugin_param_dialog(monkeypatch, {"threshold": 0.5})
    analyzer = _make_analyzer(fn, param_schema=[{"name": "threshold", "type": "float"}])
    window._on_run_plugin_analyzer(analyzer)

    assert received == {"threshold": 0.5}


def test_run_plugin_analyzer_param_dialog_cancelled_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)

    calls = []

    def fn(dataset, params):
        calls.append(1)
        return AnalysisResult()

    _patch_plugin_param_dialog(monkeypatch, {"threshold": 0.5}, accepted=False)
    analyzer = _make_analyzer(fn, param_schema=[{"name": "threshold", "type": "float"}])
    window._on_run_plugin_analyzer(analyzer)

    assert calls == []
    assert len(window.project.datasets) == before_count
