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
import os
import re
import time

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings, QPoint
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox

import gui.main_window as main_window_module
import gui.mixins.dataset_mixin as dataset_mixin_module
from gui.main_window import PlotterApp
from gui.dialogs import (
    NormalizeDatasetDialog, PluginParamDialog, FitDialog, PeakSettingsDialog,
    DatasetArithmeticDialog, SavGolDialog, ColumnCalculatorDialog, ColorPaletteDialog,
    NewDatasetDialog, BaselineCorrectionDialog, IntervalIntegralDialog, ResampleDatasetDialog,
)
from core.dataset import Dataset
from core.plugin_types import PluginProcessor, PluginAnalyzer, AnalysisResult
from gui.dataset_style_icon import DATASET_TREE_NAME_COLUMN, DATASET_TREE_VISIBILITY_COLUMN


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


def _pump_events_until_fit_task_done(window, max_iterations=300):
    """
    項目C-004フェーズ1: _on_fit_curve()はTaskRunner(実際の別スレッド)で
    フィット計算を行うようになったため、呼び出し直後は完了していない。
    tests/test_main_window.pyの_pump_events_until_queue_drained()と同じ理由
    (processEvents()だけでなくOS側にスレッドの実行機会を与える短いsleepが必要)
    で、_fit_task_runnerがNoneに戻るまでイベントループを回す。
    """
    app = QApplication.instance()
    for _ in range(max_iterations):
        app.processEvents()
        if window._fit_task_runner is None:
            return
        time.sleep(0.01)
    raise AssertionError("フィット処理が時間内に完了しませんでした")


def _pump_events_until_batch_fit_task_done(window, max_iterations=300):
    """項目C-004フェーズ2: _on_batch_curve_fit()版の_pump_events_until_fit_task_done。"""
    app = QApplication.instance()
    for _ in range(max_iterations):
        app.processEvents()
        if window._batch_fit_task_runner is None:
            return
        time.sleep(0.01)
    raise AssertionError("バッチフィット処理が時間内に完了しませんでした")


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


def _patch_dialog_result(monkeypatch, module_attr_name, base_cls, method_name, value, accepted=True):
    """
    引数無しの exec() + 単一の getter メソッドだけを持つダイアログ用の汎用フェイク。
    DatasetArithmeticDialog.get_settings / SavGolDialog.get_settings /
    ColumnCalculatorDialog.get_formula / ColorPaletteDialog.get_result のように、
    「実ダイアログを構築せず、指定した戻り値を返すgetterを1つ持つ」パターンをまとめる。
    """
    class FakeDialog(base_cls):
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    setattr(FakeDialog, method_name, lambda self: value)
    monkeypatch.setattr(dataset_mixin_module, module_attr_name, FakeDialog)
    return FakeDialog


def _patch_new_dataset_dialog(monkeypatch, name, column_names, row_count, accepted=True):
    class FakeNewDatasetDialog(NewDatasetDialog):
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        def get_dataset_name(self):
            return name

        def get_column_names(self):
            return column_names

        def get_row_count(self):
            return row_count

    monkeypatch.setattr(dataset_mixin_module, "NewDatasetDialog", FakeNewDatasetDialog)


def _patch_fit_dialog(monkeypatch, fit_type, custom_formula=None, use_weighted=False, x_range=None,
                       p0_overrides=None, fixed_params=None, bounds=None, band_type=None):
    """
    FitDialog.get_fit_type (staticmethod) をモーダル表示なしのフェイクに差し替える。
    p0_overrides/fixed_params/bounds(項目C-403)は省略時、実際のFitDialog.get_fit_type
    のキャンセル/未カスタマイズ時と同じ「空dict」を返す(Noneではない)。
    band_type(項目C-405)は省略時None("表示しない"相当)。
    """
    result = (
        fit_type, custom_formula, use_weighted, x_range,
        p0_overrides or {}, fixed_params or {}, bounds or {}, band_type,
    )
    monkeypatch.setattr(
        dataset_mixin_module.FitDialog, "get_fit_type",
        staticmethod(lambda *a, **k: result)
    )


def _patch_peak_dialog(monkeypatch, settings_dict):
    """PeakSettingsDialog.get_peak_settings (staticmethod) をフェイクに差し替える(None=キャンセル)"""
    monkeypatch.setattr(
        dataset_mixin_module.PeakSettingsDialog, "get_peak_settings",
        staticmethod(lambda *a, **k: settings_dict)
    )


def _select_items(window, datasets):
    """
    複数のデータセットをまとめて選択状態にする(先頭をカレントにする)。
    ★ setCurrentItem() は(SelectionModeによっては)呼び出し時点の選択状態を
    そのカレントアイテム1件だけにリセットしてしまうことがあるため、
    必ず setCurrentItem() を先に呼び、そのあとで全アイテムに setSelected(True) を
    掛け直す順序にする(逆順だとカレント化のタイミングで選択が1件に戻る)。
    """
    tree = window.ui.dataset_list_widget
    tree.clearSelection()
    items = [window._get_dataset_tree_item(ds) for ds in datasets]
    tree.setCurrentItem(items[0])
    for item in items:
        item.setSelected(True)
    return items


def _patch_question_yes(monkeypatch, accept=True):
    calls = []

    def fake_question(*args, **kwargs):
        calls.append(args)
        return (QMessageBox.StandardButton.Yes if accept else QMessageBox.StandardButton.No)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
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


def test_run_plugin_analyzer_replaces_previous_table_dialog(tmp_path, monkeypatch):
    """table結果を2回連続で受け取ると、古いResultDialogを閉じてから新しいものに差し替える(580-581行)"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("orig")
    _add_and_select_dataset(window, ds)

    def fn(dataset, params):
        return AnalysisResult(table="a,b\n1,2\n")

    analyzer = _make_analyzer(fn, name="Peaks")
    window._on_run_plugin_analyzer(analyzer)
    first_dialog = window.plugin_analysis_result_dialog
    assert first_dialog is not None

    window._on_run_plugin_analyzer(analyzer)
    second_dialog = window.plugin_analysis_result_dialog

    assert second_dialog is not None
    assert second_dialog is not first_dialog
    second_dialog.close()


# =============================================================================
# ファイル読み込み (_on_add_dataset)
# =============================================================================

def test_on_add_dataset_calls_load_data_with_chosen_path(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    chosen_path = str(tmp_path / "data.csv")
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (chosen_path, "Data Files"))
    )
    calls = []
    monkeypatch.setattr(window, "load_data", lambda path: calls.append(path))

    window._on_add_dataset()

    assert calls == [chosen_path]


def test_on_add_dataset_cancelled_does_not_call_load_data(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: ("", ""))
    )
    calls = []
    monkeypatch.setattr(window, "load_data", lambda path: calls.append(path))

    window._on_add_dataset()

    assert calls == []


# =============================================================================
# 新規データセット作成 (_on_create_new_dataset)
# =============================================================================

def test_on_create_new_dataset_builds_empty_dataset_with_nan_rows(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(window, "_on_show_data_editor", lambda: None)
    _patch_new_dataset_dialog(monkeypatch, "新データ", ["X", "Y", "Z"], 3)
    before_count = len(window.project.datasets)

    window._on_create_new_dataset()

    assert len(window.project.datasets) == before_count + 1
    ds = window.project.datasets[-1]
    assert ds.name == "新データ"
    assert ds.x_col_name == "X"
    assert ds.y_col_name == "Y"
    assert list(ds.df.columns) == ["X", "Y", "Z"]
    assert len(ds.df) == 3
    assert ds.df.isna().all().all()


def test_on_create_new_dataset_single_column_uses_it_for_both_axes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(window, "_on_show_data_editor", lambda: None)
    _patch_new_dataset_dialog(monkeypatch, "単列", ["Only"], 2)

    window._on_create_new_dataset()

    ds = window.project.datasets[-1]
    assert ds.x_col_name == "Only"
    assert ds.y_col_name == "Only"


def test_on_create_new_dataset_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(window, "_on_show_data_editor", lambda: None)
    _patch_new_dataset_dialog(monkeypatch, "新データ", ["X", "Y"], 3, accepted=False)
    before_count = len(window.project.datasets)

    window._on_create_new_dataset()

    assert len(window.project.datasets) == before_count


# =============================================================================
# データセット検索フィルタ (_on_dataset_search_changed)
# =============================================================================

def test_dataset_search_filters_by_name_and_shows_matching_folder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("Folder")
    ds_in_folder = _make_simple_dataset("apple")
    window.project.datasets.append(ds_in_folder)
    window._add_dataset_list_item(ds_in_folder, folder)
    ds_top = _make_simple_dataset("banana")
    window._add_dataset(ds_top, None, select=False)

    window._on_dataset_search_changed("app")

    assert folder.isHidden() is False
    assert window._get_dataset_tree_item(ds_in_folder).isHidden() is False
    assert window._get_dataset_tree_item(ds_top).isHidden() is True


def test_dataset_search_empty_query_shows_everything(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds_top = _make_simple_dataset("banana")
    window._add_dataset(ds_top, None, select=False)
    window._on_dataset_search_changed("nomatch")
    assert window._get_dataset_tree_item(ds_top).isHidden() is True

    window._on_dataset_search_changed("")

    assert window._get_dataset_tree_item(ds_top).isHidden() is False


def test_dataset_search_folder_with_no_matching_children_is_hidden(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("Folder")
    ds_in_folder = _make_simple_dataset("apple")
    window.project.datasets.append(ds_in_folder)
    window._add_dataset_list_item(ds_in_folder, folder)

    window._on_dataset_search_changed("zzz")

    assert folder.isHidden() is True


# =============================================================================
# 新しいフォルダ (_on_new_folder)
# =============================================================================

def test_on_new_folder_creates_top_level_folder_when_nothing_selected(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("新しいフォルダ", True))
    )
    before = window.ui.dataset_list_widget.topLevelItemCount()

    window._on_new_folder()

    assert window.ui.dataset_list_widget.topLevelItemCount() == before + 1


def test_on_new_folder_creates_child_folder_when_folder_selected(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    parent_folder = window._add_dataset_folder_item("Parent")
    window.ui.dataset_list_widget.setCurrentItem(parent_folder)
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("Child", True))
    )

    window._on_new_folder()

    assert parent_folder.childCount() == 1
    assert parent_folder.child(0).text(0) == "Child"


def test_on_new_folder_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("", False))
    )
    before = window.ui.dataset_list_widget.topLevelItemCount()

    window._on_new_folder()

    assert window.ui.dataset_list_widget.topLevelItemCount() == before


def test_on_new_folder_empty_name_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("", True))
    )
    before = window.ui.dataset_list_widget.topLevelItemCount()

    window._on_new_folder()

    assert window.ui.dataset_list_widget.topLevelItemCount() == before


# =============================================================================
# データセットツリーの右クリックメニュー (_on_dataset_tree_context_menu)
# =============================================================================

class _RecordingMenu(QMenu):
    """実際にモーダル表示せず、addAction()で追加されたテキスト/アクションだけを記録するQMenu"""
    last_instance = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.added_texts = []
        self.actions_by_text = {}
        _RecordingMenu.last_instance = self

    def addAction(self, text):
        action = super().addAction(text)
        self.added_texts.append(text)
        self.actions_by_text[text] = action
        return action

    def exec(self, *args, **kwargs):
        return None


def _patch_recording_menu(monkeypatch):
    monkeypatch.setattr(dataset_mixin_module, "QMenu", _RecordingMenu)


def test_context_menu_no_selection_shows_only_new_folder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    assert _RecordingMenu.last_instance.added_texts == ["新しいフォルダ"]


def test_context_menu_single_dataset_selected_shows_style_and_export_actions(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    texts = _RecordingMenu.last_instance.added_texts
    assert "スタイルをコピー" in texts
    assert "スタイルを貼り付け" in texts
    assert "規格化(ノーマライズ)..." in texts
    assert "Savitzky-Golayフィルタ(平滑化/微分)..." in texts
    assert "データセット間演算..." not in texts
    assert "データ表をファイルに書き出す..." in texts
    assert "削除" in texts


def test_context_menu_two_datasets_selected_shows_arithmetic_and_batch_actions(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    texts = _RecordingMenu.last_instance.added_texts
    assert "データセット間演算..." in texts
    assert "バッチ列計算..." in texts
    assert "バッチカーブフィット..." in texts


def test_context_menu_three_datasets_selected_hides_pairwise_arithmetic(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    texts = _RecordingMenu.last_instance.added_texts
    assert "データセット間演算..." not in texts
    assert "バッチ列計算..." in texts


def test_context_menu_paste_style_disabled_without_copied_style(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    assert window._copied_dataset_style is None
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    action = _RecordingMenu.last_instance.actions_by_text["スタイルを貼り付け"]
    assert action.isEnabled() is False


def test_context_menu_paste_style_enabled_after_copy(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    window._on_copy_dataset_style()
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    action = _RecordingMenu.last_instance.actions_by_text["スタイルを貼り付け"]
    assert action.isEnabled() is True


# =============================================================================
# スタイルのコピー&ペースト (_on_copy_dataset_style / _on_paste_dataset_style)
# =============================================================================

def test_copy_dataset_style_with_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._on_copy_dataset_style()
    assert window._copied_dataset_style is None


def test_copy_dataset_style_captures_style_attrs_by_value(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    ds.color = "#abcdef"
    ds.linestyle = "dashed"
    _add_and_select_dataset(window, ds)

    window._on_copy_dataset_style()

    assert window._copied_dataset_style["color"] == "#abcdef"
    assert window._copied_dataset_style["linestyle"] == "dashed"
    # コピー元を後から変えても、既にコピーした内容には影響しない(値のコピーであること)
    ds.color = "#000000"
    assert window._copied_dataset_style["color"] == "#abcdef"


def test_paste_dataset_style_without_copy_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    window._on_paste_dataset_style()  # 例外なく完了すればOK


def test_paste_dataset_style_without_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    window._on_copy_dataset_style()
    folder = window._add_dataset_folder_item("Folder")
    window.ui.dataset_list_widget.clearSelection()
    folder.setSelected(True)
    window.ui.dataset_list_widget.setCurrentItem(folder)

    window._on_paste_dataset_style()  # 対象データセットが無いので何も起きない


def test_paste_dataset_style_single_dataset_applies_and_is_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    source = _make_simple_dataset("source")
    source.color = "#123456"
    source.linestyle = "dashed"
    _add_and_select_dataset(window, source)
    window._on_copy_dataset_style()

    target = _make_simple_dataset("target")
    original_color = target.color
    _add_and_select_dataset(window, target)

    window._on_paste_dataset_style()

    assert target.color == "#123456"
    assert target.linestyle == "dashed"

    window.undo_stack.undo()
    assert target.color == original_color


def test_paste_dataset_style_batch_uses_single_macro(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    source = _make_simple_dataset("source")
    source.color = "#123456"
    _add_and_select_dataset(window, source)
    window._on_copy_dataset_style()

    targets = [_make_simple_dataset(f"t{i}") for i in range(2)]
    for ds in targets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, targets)

    window._on_paste_dataset_style()

    assert all(ds.color == "#123456" for ds in targets)

    window.undo_stack.undo()
    assert all(ds.color == "#1f77b4" for ds in targets)


# =============================================================================
# データ表の書き出し (_on_export_dataset_data)
# =============================================================================

def test_export_dataset_data_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: calls.append(1) or ("", ""))
    )
    window._on_export_dataset_data()
    assert calls == []


def test_export_single_dataset_csv(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("mydata")
    _add_and_select_dataset(window, ds)
    out_path = str(tmp_path / "out.csv")
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (out_path, "CSV Files (*.csv)"))
    )
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_dataset_data()

    assert os.path.exists(out_path)
    assert len(info_calls) == 1


def test_export_single_dataset_excel_via_filter_appends_extension(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("mydata")
    _add_and_select_dataset(window, ds)
    out_path_no_ext = str(tmp_path / "outbook")
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (out_path_no_ext, "Excel Files (*.xlsx)"))
    )
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_dataset_data()

    assert os.path.exists(out_path_no_ext + ".xlsx")
    assert len(info_calls) == 1


def test_export_single_dataset_cancelled_writes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("mydata")
    _add_and_select_dataset(window, ds)
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: ("", ""))
    )
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_dataset_data()

    assert info_calls == []


def test_export_single_dataset_write_error_shows_warning(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("mydata")
    _add_and_select_dataset(window, ds)
    out_path = str(tmp_path / "out.csv")
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (out_path, "CSV Files (*.csv)"))
    )

    def raiser(self, *a, **k):
        raise IOError("boom")

    monkeypatch.setattr(pd.DataFrame, "to_csv", raiser)
    warnings = _patch_warning_capture(monkeypatch)
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_dataset_data()

    assert len(warnings) == 1
    assert info_calls == []


def test_export_multi_datasets_csv_per_file_with_name_collision(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds1 = _make_simple_dataset("dup")
    ds2 = _make_simple_dataset("dup")
    window._add_dataset(ds1, None, select=False)
    window._add_dataset(ds2, None, select=False)
    _select_items(window, [ds1, ds2])
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("CSV (データセットごとに別ファイル)", True))
    )
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(tmp_path))
    )
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_dataset_data()

    assert (tmp_path / "dup.csv").exists()
    assert (tmp_path / "dup_2.csv").exists()
    assert len(info_calls) == 1


def test_export_multi_datasets_excel_workbook_with_sheet_collision(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds1 = _make_simple_dataset("Dup")
    ds2 = _make_simple_dataset("Dup")
    window._add_dataset(ds1, None, select=False)
    window._add_dataset(ds2, None, select=False)
    _select_items(window, [ds1, ds2])
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("Excel (1ブックにシート分け)", True))
    )
    out_path = str(tmp_path / "book.xlsx")
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (out_path, "Excel Files (*.xlsx)"))
    )
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_dataset_data()

    assert os.path.exists(out_path)
    xls = pd.ExcelFile(out_path)
    assert xls.sheet_names == ["Dup", "Dup_2"]
    assert len(info_calls) == 1


def test_export_multi_datasets_format_choice_cancelled_writes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("CSV (データセットごとに別ファイル)", False))
    )
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_dataset_data()

    assert info_calls == []


def test_export_multi_datasets_csv_dir_cancelled_writes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("CSV (データセットごとに別ファイル)", True))
    )
    monkeypatch.setattr(
        dataset_mixin_module.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: "")
    )
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_dataset_data()

    assert info_calls == []


# =============================================================================
# データセット間演算 (_on_dataset_arithmetic)
# =============================================================================

def test_arithmetic_requires_exactly_two_selected(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)
    info_calls = _patch_info_capture(monkeypatch)

    window._on_dataset_arithmetic()

    assert len(info_calls) == 1
    assert len(window.project.datasets) == before_count


def _make_arith_pair():
    df_a = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [0.0, 10.0, 20.0, 30.0]})
    df_b = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [5.0, 5.0, 5.0, 5.0]})
    ds_a = Dataset(name="A", df=df_a, x_col_name='x', y_col_name='y')
    ds_b = Dataset(name="B", df=df_b, x_col_name='x', y_col_name='y')
    return ds_a, ds_b


def test_arithmetic_a_minus_b_success(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds_a, ds_b = _make_arith_pair()
    window._add_dataset(ds_a, None, select=False)
    window._add_dataset(ds_b, None, select=False)
    _select_items(window, [ds_a, ds_b])
    _patch_dialog_result(
        monkeypatch, "DatasetArithmeticDialog", DatasetArithmeticDialog,
        "get_settings", ("A - B", "diff")
    )
    before_count = len(window.project.datasets)

    window._on_dataset_arithmetic()

    assert len(window.project.datasets) == before_count + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.name == "diff"
    np.testing.assert_allclose(new_ds.y_data, [-5.0, 5.0, 15.0, 25.0])


def test_arithmetic_a_divide_b(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds_a, ds_b = _make_arith_pair()
    window._add_dataset(ds_a, None, select=False)
    window._add_dataset(ds_b, None, select=False)
    _select_items(window, [ds_a, ds_b])
    _patch_dialog_result(
        monkeypatch, "DatasetArithmeticDialog", DatasetArithmeticDialog,
        "get_settings", ("A ÷ B", "ratio")
    )

    window._on_dataset_arithmetic()

    new_ds = window.project.datasets[-1]
    np.testing.assert_allclose(new_ds.y_data, [0.0, 2.0, 4.0, 6.0])


def test_arithmetic_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds_a, ds_b = _make_arith_pair()
    window._add_dataset(ds_a, None, select=False)
    window._add_dataset(ds_b, None, select=False)
    _select_items(window, [ds_a, ds_b])
    _patch_dialog_result(
        monkeypatch, "DatasetArithmeticDialog", DatasetArithmeticDialog,
        "get_settings", ("A - B", "diff"), accepted=False
    )
    before_count = len(window.project.datasets)

    window._on_dataset_arithmetic()

    assert len(window.project.datasets) == before_count


def test_arithmetic_empty_output_name_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds_a, ds_b = _make_arith_pair()
    window._add_dataset(ds_a, None, select=False)
    window._add_dataset(ds_b, None, select=False)
    _select_items(window, [ds_a, ds_b])
    _patch_dialog_result(
        monkeypatch, "DatasetArithmeticDialog", DatasetArithmeticDialog,
        "get_settings", ("A - B", "")
    )
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_dataset_arithmetic()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_arithmetic_all_nan_data_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df_a = pd.DataFrame({'x': [0, 1], 'y': [np.nan, np.nan]})
    df_b = pd.DataFrame({'x': [0, 1], 'y': [1.0, 2.0]})
    ds_a = Dataset(name="A", df=df_a, x_col_name='x', y_col_name='y')
    ds_b = Dataset(name="B", df=df_b, x_col_name='x', y_col_name='y')
    window._add_dataset(ds_a, None, select=False)
    window._add_dataset(ds_b, None, select=False)
    _select_items(window, [ds_a, ds_b])
    _patch_dialog_result(
        monkeypatch, "DatasetArithmeticDialog", DatasetArithmeticDialog,
        "get_settings", ("A - B", "diff")
    )
    warnings = _patch_warning_capture(monkeypatch)

    window._on_dataset_arithmetic()

    assert len(warnings) == 1


def test_arithmetic_non_overlapping_ranges_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df_a = pd.DataFrame({'x': [0, 1], 'y': [1.0, 2.0]})
    df_b = pd.DataFrame({'x': [10, 11], 'y': [1.0, 2.0]})
    ds_a = Dataset(name="A", df=df_a, x_col_name='x', y_col_name='y')
    ds_b = Dataset(name="B", df=df_b, x_col_name='x', y_col_name='y')
    window._add_dataset(ds_a, None, select=False)
    window._add_dataset(ds_b, None, select=False)
    _select_items(window, [ds_a, ds_b])
    _patch_dialog_result(
        monkeypatch, "DatasetArithmeticDialog", DatasetArithmeticDialog,
        "get_settings", ("A - B", "diff")
    )
    warnings = _patch_warning_capture(monkeypatch)

    window._on_dataset_arithmetic()

    assert len(warnings) == 1


# =============================================================================
# 規格化(ノーマライズ)の追加エッジケース (_on_normalize_dataset)
# =============================================================================

def test_normalize_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window._on_normalize_dataset()
    assert len(window.project.datasets) == before_count


def test_normalize_all_nan_data_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2], 'y': [np.nan, np.nan, np.nan]})
    ds = Dataset(name="sample", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    warnings = _patch_warning_capture(monkeypatch)

    window._on_normalize_dataset()

    assert len(warnings) == 1


def test_normalize_empty_output_name_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("sample")
    _add_and_select_dataset(window, ds)
    _patch_normalize_dialog(monkeypatch, NormalizeDatasetDialog.MODE_MAX, None, "")
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_normalize_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


# =============================================================================
# Savitzky-Golayフィルタ (_on_savgol_dataset)
# =============================================================================

def _make_savgol_dataset(n=11):
    x = np.linspace(0, 10, n)
    y = x ** 2
    df = pd.DataFrame({'x': x, 'y': y})
    return Dataset(name="curve", df=df, x_col_name='x', y_col_name='y')


def test_savgol_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window._on_savgol_dataset()
    assert len(window.project.datasets) == before_count


def test_savgol_insufficient_points_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1], 'y': [0.0, 1.0]})
    ds = Dataset(name="curve", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    warnings = _patch_warning_capture(monkeypatch)

    window._on_savgol_dataset()

    assert len(warnings) == 1


def test_savgol_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_savgol_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "SavGolDialog", SavGolDialog, "get_settings",
        (5, 2, 0, "curve_smoothed"), accepted=False
    )
    before_count = len(window.project.datasets)

    window._on_savgol_dataset()

    assert len(window.project.datasets) == before_count


def test_savgol_empty_output_name_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_savgol_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "SavGolDialog", SavGolDialog, "get_settings",
        (5, 2, 0, "")
    )
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_savgol_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_savgol_calculation_error_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_savgol_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "SavGolDialog", SavGolDialog, "get_settings",
        (5, 2, 0, "curve_smoothed")
    )

    def raiser(*a, **k):
        raise ValueError("窓幅が不正です")

    monkeypatch.setattr(dataset_mixin_module, "calculate_savgol", raiser)
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_savgol_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_savgol_success_smoothing_adds_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_savgol_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "SavGolDialog", SavGolDialog, "get_settings",
        (5, 2, 0, "curve_smoothed")
    )
    before_count = len(window.project.datasets)

    window._on_savgol_dataset()

    assert len(window.project.datasets) == before_count + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.name == "curve_smoothed"
    assert len(new_ds.y_data) == len(ds.y_data)


def test_savgol_success_derivative_adds_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_savgol_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "SavGolDialog", SavGolDialog, "get_settings",
        (5, 2, 1, "curve_deriv1")
    )

    window._on_savgol_dataset()

    new_ds = window.project.datasets[-1]
    assert new_ds.name == "curve_deriv1"


# =============================================================================
# ベースライン補正 (_on_baseline_correction_dataset, 項目C-308)
# =============================================================================

def _make_baseline_dataset(n=50):
    x = np.linspace(0, 10, n)
    y = 0.5 * x + 3.0 + np.where(np.abs(x - 5) < 1, 2.0, 0.0)  # 傾いたベースライン+段差(ピーク代わり)
    df = pd.DataFrame({'x': x, 'y': y})
    return Dataset(name="spectrum", df=df, x_col_name='x', y_col_name='y')


def test_baseline_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window._on_baseline_correction_dataset()
    assert len(window.project.datasets) == before_count


def test_baseline_insufficient_points_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1], 'y': [0.0, 1.0]})
    ds = Dataset(name="spectrum", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    warnings = _patch_warning_capture(monkeypatch)

    window._on_baseline_correction_dataset()

    assert len(warnings) == 1


def test_baseline_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("als", {"lam": 1e5, "p": 0.01, "niter": 10}, "spectrum_corrected", False),
        accepted=False,
    )
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(window.project.datasets) == before_count


def test_baseline_empty_output_name_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("als", {"lam": 1e5, "p": 0.01, "niter": 10}, "", False)
    )
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_baseline_calculation_error_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("als", {"lam": 1e5, "p": 0.01, "niter": 10}, "spectrum_corrected", False)
    )

    def raiser(*a, **k):
        raise ValueError("lamは正の値である必要があります")

    monkeypatch.setattr(dataset_mixin_module, "calculate_baseline_als", raiser)
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_baseline_als_success_adds_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("als", {"lam": 1e5, "p": 0.01, "niter": 10}, "spectrum_corrected", False)
    )
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(window.project.datasets) == before_count + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.name == "spectrum_corrected"
    assert len(new_ds.y_data) == len(ds.y_data)


def test_baseline_polynomial_success_adds_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("polynomial", {"degree": 1, "iterations": 10}, "spectrum_poly", False)
    )
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(window.project.datasets) == before_count + 1
    assert window.project.datasets[-1].name == "spectrum_poly"


def test_baseline_rubberband_success_adds_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("rubberband", {}, "spectrum_rubberband", False)
    )
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(window.project.datasets) == before_count + 1
    assert window.project.datasets[-1].name == "spectrum_rubberband"


def test_baseline_manual_success_adds_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("manual", {"anchor_x_text": "0, 10", "method": "linear"}, "spectrum_manual", False)
    )
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(window.project.datasets) == before_count + 1
    assert window.project.datasets[-1].name == "spectrum_manual"


def test_baseline_manual_invalid_anchor_text_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("manual", {"anchor_x_text": "abc, def", "method": "linear"}, "spectrum_manual", False)
    )
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_baseline_add_baseline_curve_checkbox_adds_two_datasets(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("rubberband", {}, "spectrum_rubberband", True)
    )
    before_count = len(window.project.datasets)

    window._on_baseline_correction_dataset()

    assert len(window.project.datasets) == before_count + 2
    names = [d.name for d in window.project.datasets[-2:]]
    assert "spectrum_rubberband" in names
    assert "spectrum_rubberband_baseline" in names


# =============================================================================
# バッチ列計算 (_on_batch_column_calculate)
# =============================================================================

def test_batch_column_calculate_requires_at_least_two_selected(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    info_calls = _patch_info_capture(monkeypatch)

    window._on_batch_column_calculate()

    assert len(info_calls) == 1


def test_batch_column_calculate_dialog_cancelled_changes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_dialog_result(
        monkeypatch, "ColumnCalculatorDialog", ColumnCalculatorDialog,
        "get_formula", ("y2", "y*2"), accepted=False
    )

    window._on_batch_column_calculate()

    assert all("y2" not in ds.df.columns for ds in datasets)


def test_batch_column_calculate_empty_formula_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_dialog_result(
        monkeypatch, "ColumnCalculatorDialog", ColumnCalculatorDialog,
        "get_formula", ("", "")
    )
    warnings = _patch_warning_capture(monkeypatch)

    window._on_batch_column_calculate()

    assert len(warnings) == 1


def test_batch_column_calculate_applies_formula_to_all_selected(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_dialog_result(
        monkeypatch, "ColumnCalculatorDialog", ColumnCalculatorDialog,
        "get_formula", ("y2", "y*2")
    )
    info_calls = _patch_info_capture(monkeypatch)

    window._on_batch_column_calculate()

    for ds in datasets:
        np.testing.assert_allclose(ds.df["y2"].values, ds.df["y"].values * 2)
    assert len(info_calls) == 1


def test_batch_column_calculate_partial_failure_reports_both(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds1 = _make_simple_dataset("ok")
    ds2 = _make_simple_dataset("bad")
    window._add_dataset(ds1, None, select=False)
    window._add_dataset(ds2, None, select=False)
    _select_items(window, [ds1, ds2])
    _patch_dialog_result(
        monkeypatch, "ColumnCalculatorDialog", ColumnCalculatorDialog,
        "get_formula", ("y2", "y*2")
    )

    original = dataset_mixin_module.safe_eval_column_formula

    def flaky(df, formula):
        if df is ds2.df:
            raise ValueError("bad formula")
        return original(df, formula)

    monkeypatch.setattr(dataset_mixin_module, "safe_eval_column_formula", flaky)
    info_calls = _patch_info_capture(monkeypatch)

    window._on_batch_column_calculate()

    assert "y2" in ds1.df.columns
    assert "y2" not in ds2.df.columns
    message = info_calls[0][2]
    assert "失敗" in message
    assert "bad" in message


# =============================================================================
# バッチカーブフィット (_on_batch_curve_fit)
# =============================================================================

def _make_linear_dataset(name, slope=2.0, intercept=1.0, n=10):
    x = np.linspace(0, 9, n)
    y = slope * x + intercept
    df = pd.DataFrame({'x': x, 'y': y})
    return Dataset(name=name, df=df, x_col_name='x', y_col_name='y')


def test_batch_curve_fit_requires_at_least_two_selected(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    info_calls = _patch_info_capture(monkeypatch)

    window._on_batch_curve_fit()

    assert len(info_calls) == 1


def test_batch_curve_fit_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_linear_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_fit_dialog(monkeypatch, None)
    before_count = len(window.project.datasets)

    window._on_batch_curve_fit()

    assert len(window.project.datasets) == before_count


def test_batch_curve_fit_success_adds_fit_dataset_per_selected(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_linear_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    info_calls = _patch_info_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_batch_curve_fit()
    _pump_events_until_batch_fit_task_done(window)

    assert len(window.project.datasets) == before_count + 2
    new_names = {ds.name for ds in window.project.datasets[before_count:]}
    assert new_names == {"Fit (d0)", "Fit (d1)"}
    assert len(info_calls) == 1
    # 項目C-401: バッチフィットでも各結果がfit_resultとして構造化保持されること
    for ds in window.project.datasets[before_count:]:
        assert ds.fit_result is not None
        assert ds.fit_result['fit_type'] == "線形 (y = ax + b)"


def test_batch_curve_fit_partial_failure_reports_both(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ok_ds = _make_linear_dataset("ok")
    bad_ds = _make_linear_dataset("bad")
    bad_ds.df['x'] = bad_ds.df['x'] + 1000  # calculate_curve_fitのフェイクで見分けるための印
    window._add_dataset(ok_ds, None, select=False)
    window._add_dataset(bad_ds, None, select=False)
    _select_items(window, [ok_ds, bad_ds])
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")

    original = dataset_mixin_module.calculate_curve_fit

    def flaky(x_data, y_data, fit_type, **kwargs):
        if len(x_data) and x_data[0] > 500:
            raise RuntimeError("fit failed")
        return original(x_data, y_data, fit_type, **kwargs)

    monkeypatch.setattr(dataset_mixin_module, "calculate_curve_fit", flaky)
    info_calls = _patch_info_capture(monkeypatch)

    window._on_batch_curve_fit()
    _pump_events_until_batch_fit_task_done(window)

    names = {ds.name for ds in window.project.datasets if ds.name.startswith("Fit (")}
    assert names == {"Fit (ok)"}
    message = info_calls[0][2]
    assert "失敗" in message


def test_batch_curve_fit_calls_update_plot_exactly_once_for_n_dataset_batch(tmp_path, monkeypatch):
    """
    項目C-004フェーズ2の主眼: 以前はループ内で_add_dataset()を都度呼んでおり
    N件のフィットでN回のフル再描画が起きていた。バックグラウンドでの一括計算後、
    _update_plot()が(N回ではなく)1回だけ呼ばれることを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_linear_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    _patch_info_capture(monkeypatch)

    update_plot_calls = []
    monkeypatch.setattr(window, "_update_plot", lambda: update_plot_calls.append(1))

    window._on_batch_curve_fit()
    _pump_events_until_batch_fit_task_done(window)

    assert update_plot_calls == [1]


def test_batch_curve_fit_cancellation_keeps_only_completed_items(tmp_path, monkeypatch):
    """
    キャンセル要求後、完了済みの分だけがデータセットとして追加され、
    未処理分は追加されないこと(バッチの残りをスキップする粒度のキャンセル)。

    タイミング設計: 4件 x 0.2秒/件(計0.8秒)のうち、t=0.35秒でキャンセル要求を
    出す。is_cancelled()チェックは各アイテムのループ先頭(sleep前)にあるため、
    1件目(t=0〜0.2s)は確実に完了・追加され、2件目(t=0.2〜0.4s、要求時点で
    既にsleep中)もそのsleep自体は中断されないため最後まで完了・追加される。
    3件目のチェック(t=0.4s時点)でようやくキャンセルが検知されスキップされる
    ため、「1件目・2件目は追加/3件目・4件目は未追加」という結果が
    (十分なタイミングの余裕を持って)安定的に得られる。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_linear_dataset(f"d{i}") for i in range(4)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    _patch_info_capture(monkeypatch)

    original = dataset_mixin_module.calculate_curve_fit

    def slow(x_data, y_data, fit_type, **kwargs):
        time.sleep(0.2)
        return original(x_data, y_data, fit_type, **kwargs)

    monkeypatch.setattr(dataset_mixin_module, "calculate_curve_fit", slow)
    before_count = len(window.project.datasets)

    window._on_batch_curve_fit()
    runner = window._batch_fit_task_runner
    assert runner is not None

    app = QApplication.instance()
    deadline = time.time() + 0.35
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    runner.requestInterruption()

    _pump_events_until_batch_fit_task_done(window)

    added_count = len(window.project.datasets) - before_count
    assert 0 < added_count < 4


# =============================================================================
# データセット削除 (_on_remove_dataset) / _find_dataset_row
# =============================================================================

def test_remove_dataset_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    window._add_dataset(ds, None, select=False)
    before_count = len(window.project.datasets)

    window._on_remove_dataset()

    assert len(window.project.datasets) == before_count


def test_remove_single_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)

    window._on_remove_dataset()

    assert len(window.project.datasets) == before_count - 1
    assert ds not in window.project.datasets
    assert window.ui.properties_groupbox.isEnabled() is False


def test_remove_folder_removes_contained_datasets(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("Folder")
    ds1 = _make_simple_dataset("d1")
    ds2 = _make_simple_dataset("d2")
    window.project.datasets.extend([ds1, ds2])
    window._add_dataset_list_item(ds1, folder)
    window._add_dataset_list_item(ds2, folder)
    window.ui.dataset_list_widget.clearSelection()
    folder.setSelected(True)
    window.ui.dataset_list_widget.setCurrentItem(folder)
    before_count = len(window.project.datasets)

    window._on_remove_dataset()

    assert len(window.project.datasets) == before_count - 2
    assert window.ui.dataset_list_widget.topLevelItemCount() == 0


def test_remove_folder_and_child_selected_together_no_double_removal(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("Folder")
    ds1 = _make_simple_dataset("d1")
    window.project.datasets.append(ds1)
    item = window._add_dataset_list_item(ds1, folder)
    window.ui.dataset_list_widget.clearSelection()
    folder.setSelected(True)
    item.setSelected(True)
    window.ui.dataset_list_widget.setCurrentItem(folder)
    before_count = len(window.project.datasets)

    window._on_remove_dataset()

    assert len(window.project.datasets) == before_count - 1


def test_remove_multiple_top_level_datasets(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets[:2])
    before_count = len(window.project.datasets)

    window._on_remove_dataset()

    assert len(window.project.datasets) == before_count - 2
    assert datasets[2] in window.project.datasets


def test_find_dataset_row_returns_minus_one_for_unknown_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("never_added")
    assert window._find_dataset_row(ds) == -1


# =============================================================================
# データセットのドラッグ&ドロップ並べ替え (_on_dataset_rows_moved)
# =============================================================================

def test_dataset_rows_moved_same_parent_pushes_undoable_reorder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    app = QApplication.instance()
    datasets = [_make_simple_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    assert [d.name for d in window.project.datasets] == ["d0", "d1", "d2"]

    tree = window.ui.dataset_list_widget
    moved_item = tree.takeTopLevelItem(2)
    tree.insertTopLevelItem(0, moved_item)

    before_undo_count = window.undo_stack.count()
    window._on_dataset_rows_moved(None, 0, 0, None, 0)

    assert [d.name for d in window.project.datasets] == ["d2", "d0", "d1"]
    assert window.undo_stack.count() == before_undo_count + 1

    window.undo_stack.undo()
    assert [d.name for d in window.project.datasets] == ["d0", "d1", "d2"]

    window.undo_stack.redo()
    for _ in range(5):
        app.processEvents()
    assert [d.name for d in window.project.datasets] == ["d2", "d0", "d1"]


def test_dataset_rows_moved_no_actual_change_pushes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    before_undo_count = window.undo_stack.count()

    window._on_dataset_rows_moved(None, 0, 0, None, 0)

    assert window.undo_stack.count() == before_undo_count


def test_dataset_rows_moved_cross_folder_direct_assignment_no_undo(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)

    tree = window.ui.dataset_list_widget
    moved_item = tree.takeTopLevelItem(2)
    tree.insertTopLevelItem(0, moved_item)

    before_undo_count = window.undo_stack.count()
    window._on_dataset_rows_moved(0, 0, 0, 1, 0)  # source_parent != dest_parent

    assert [d.name for d in window.project.datasets] == ["d2", "d0", "d1"]
    assert window.undo_stack.count() == before_undo_count  # Undo非対応の直接反映


def test_dataset_rows_moved_length_mismatch_logs_and_returns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    monkeypatch.setattr(window, "_flatten_dataset_tree", lambda *a, **k: [])
    original_order = list(window.project.datasets)

    window._on_dataset_rows_moved(None, 0, 0, None, 0)

    assert window.project.datasets == original_order


# =============================================================================
# プロパティ変更コマンドの共通ヘルパー (_push_dataset_property_command)
# =============================================================================

def test_push_dataset_property_command_noop_when_values_equal(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    before_count = window.undo_stack.count()

    window._push_dataset_property_command(ds, {'color': ds.color}, {'color': ds.color}, description="x")

    assert window.undo_stack.count() == before_count


# =============================================================================
# 項目C-003フェーズ1: 非構造的プロパティ変更は update_single_axis のみを呼ぶこと
# =============================================================================

def test_non_structural_property_change_uses_update_single_axis_not_full_replot(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    full_replot_calls = []
    single_axis_calls = []
    monkeypatch.setattr(window, '_update_plot', lambda: full_replot_calls.append(1))
    original_update_single_axis = window.canvas.update_single_axis
    monkeypatch.setattr(
        window.canvas, 'update_single_axis',
        lambda *a, **kw: (single_axis_calls.append((a, kw)), original_update_single_axis(*a, **kw))[1]
    )

    window._push_dataset_property_command(ds, {'color': ds.color}, {'color': '#ff0000'}, description="色の変更")

    assert full_replot_calls == []
    assert len(single_axis_calls) == 1
    assert single_axis_calls[0][0][0] == ds.subplot_target


def test_subplot_target_property_change_uses_lightweight_update_for_both_axes(tmp_path, monkeypatch):
    """
    項目C-003フェーズ3a: subplot_targetの変更は「軸の所属自体が変わる」ため
    以前はフルの_update_plot()に振り分けていたが、実際には旧軸(データセットが
    消える側)と新軸(現れる側)の2つのAxesだけで完結するため、
    update_single_axis()を2回(旧軸・新軸それぞれに1回ずつ)呼ぶ軽量パスに
    切り替わった。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_cols_spinbox.setValue(2)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    full_replot_calls = []
    single_axis_calls = []
    monkeypatch.setattr(window, '_update_plot', lambda light=False: full_replot_calls.append(1))
    monkeypatch.setattr(window.canvas, 'update_single_axis', lambda *a, **kw: single_axis_calls.append(a[0]))

    window._push_dataset_property_command(
        ds, {'subplot_target': 0}, {'subplot_target': 1}, description="描画先プロットの変更")

    assert full_replot_calls == []
    assert set(single_axis_calls) == {0, 1}


def test_subplot_target_property_change_undo_refreshes_both_axes(tmp_path, monkeypatch):
    """
    SetDatasetPropertiesCommand.on_appliedはredo/undoどちらの後でも同じ
    コールバックが呼ばれる(方向を教えてくれない)ため、undo後もold_values/
    new_valuesの両方から旧軸・新軸を正しく再導出できることを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_cols_spinbox.setValue(2)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    window._push_dataset_property_command(
        ds, {'subplot_target': 0}, {'subplot_target': 1}, description="描画先プロットの変更")
    assert ds.subplot_target == 1

    single_axis_calls = []
    monkeypatch.setattr(window.canvas, 'update_single_axis', lambda *a, **kw: single_axis_calls.append(a[0]))

    window.undo_stack.undo()

    assert ds.subplot_target == 0
    assert set(single_axis_calls) == {0, 1}


def test_use_secondary_y_property_change_uses_lightweight_update_for_current_axis_only(tmp_path, monkeypatch):
    """
    項目C-003フェーズ3a: use_secondary_yの変更は現在のsubplot_target軸1つ
    だけで完結する(twinx()の作成/削除もupdate_single_axis()が既に扱う)ため、
    フルの_update_plot()ではなくupdate_single_axis()を1回だけ呼ぶ。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    full_replot_calls = []
    single_axis_calls = []
    monkeypatch.setattr(window, '_update_plot', lambda light=False: full_replot_calls.append(1))
    monkeypatch.setattr(window.canvas, 'update_single_axis', lambda *a, **kw: single_axis_calls.append(a[0]))

    window._push_dataset_property_command(
        ds, {'use_secondary_y': False}, {'use_secondary_y': True}, description="第2Y軸の変更")

    assert full_replot_calls == []
    assert single_axis_calls == [0]


def test_non_structural_property_change_still_updates_tree_item_and_plot_visually(tmp_path, monkeypatch):
    """スパイを挟まない実経路でも、色変更が実際にグラフへ反映されること
    (update_single_axis経由でも見た目の変更自体は従来通り効くことの確認)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    window._push_dataset_property_command(ds, {'color': ds.color}, {'color': '#00ff00'}, description="色の変更")

    assert ds.color == '#00ff00'
    line = window.canvas.all_axes[0].lines[0]
    assert line.get_color() == '#00ff00'

    window.undo_stack.undo()
    assert ds.color != '#00ff00'


# =============================================================================
# 描画先プロット変更 (_on_subplot_target_changed)
# =============================================================================

def test_subplot_target_changed_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window._on_subplot_target_changed(1)
    assert window.undo_stack.count() == before_count


def test_subplot_target_changed_same_value_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    before_count = window.undo_stack.count()

    window._on_subplot_target_changed(ds.subplot_target)

    assert window.undo_stack.count() == before_count


def test_subplot_target_changed_minus_one_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    before_count = window.undo_stack.count()

    window._on_subplot_target_changed(-1)

    assert window.undo_stack.count() == before_count


def test_subplot_target_changed_updates_and_is_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    assert ds.subplot_target == 0

    window._on_subplot_target_changed(1)

    assert ds.subplot_target == 1
    window.undo_stack.undo()
    assert ds.subplot_target == 0


# =============================================================================
# 凡例名の変更 (_on_legend_name_changed)
# =============================================================================

def test_legend_name_changed_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window.ui.legend_name_edit.setText("new name")
    window._on_legend_name_changed()
    assert window.undo_stack.count() == before_count


def test_legend_name_changed_updates_dataset_and_tree_item(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("old_name")
    _add_and_select_dataset(window, ds)
    window.ui.legend_name_edit.setText("new_name")

    window._on_legend_name_changed()

    assert ds.name == "new_name"
    item = window._get_dataset_tree_item(ds)
    assert item.text(0) == "new_name"

    window.undo_stack.undo()
    assert ds.name == "old_name"
    assert item.text(0) == "old_name"


# =============================================================================
# データ点ラベル表示のトグル (_on_point_labels_toggled)
# =============================================================================

def test_point_labels_toggle_off_skips_confirmation(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    question_calls = _patch_question_yes(monkeypatch)

    window.point_labels_checkbox.setChecked(False)

    assert question_calls == []


def test_point_labels_toggle_on_under_limit_skips_confirmation(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")  # 3点のみ、上限(既定1000)未満
    _add_and_select_dataset(window, ds)
    question_calls = _patch_question_yes(monkeypatch)

    window.point_labels_checkbox.setChecked(True)

    assert question_calls == []
    assert ds.show_point_labels is True


def test_point_labels_toggle_on_over_limit_prompts_and_yes_applies(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': np.arange(1500), 'y': np.arange(1500)})
    ds = Dataset(name="big", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    question_calls = _patch_question_yes(monkeypatch, accept=True)

    window.point_labels_checkbox.setChecked(True)

    assert len(question_calls) == 1
    assert ds.show_point_labels is True


def test_point_labels_toggle_on_over_limit_prompts_and_no_reverts_checkbox(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': np.arange(1500), 'y': np.arange(1500)})
    ds = Dataset(name="big", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    question_calls = _patch_question_yes(monkeypatch, accept=False)

    window.point_labels_checkbox.setChecked(True)

    assert len(question_calls) == 1
    assert window.point_labels_checkbox.isChecked() is False
    assert ds.show_point_labels is False


# =============================================================================
# プロパティ一括変更 (_on_property_changed)
# =============================================================================

def test_property_changed_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window._on_property_changed()
    assert window.undo_stack.count() == before_count


def test_property_changed_unrecognized_sender_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    before_count = window.undo_stack.count()

    window._on_property_changed()  # 直接呼び出しのため sender() は None

    assert window.undo_stack.count() == before_count


def test_property_changed_plot_type_combo_single_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    assert ds.plot_type == "Line"

    window.ui.plot_type_combo.setCurrentText("Scatter")

    assert ds.plot_type == "Scatter"
    window.undo_stack.undo()
    assert ds.plot_type == "Line"


def test_property_changed_marker_none_maps_to_none_attr(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    window.ui.marker_combo.setCurrentText("None")

    assert ds.marker is None


def test_property_changed_linewidth_spinbox_batch_macro(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)

    window.ui.linewidth_spinbox.setValue(3.5)

    assert all(ds.linewidth == 3.5 for ds in datasets)
    window.undo_stack.undo()
    assert all(ds.linewidth == 1.5 for ds in datasets)


def test_property_changed_alpha_spinbox(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    window.alpha_spinbox.setValue(0.5)

    assert ds.alpha == pytest.approx(0.5)


def test_property_changed_gradient_checkbox_and_target_combo(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    ds.plot_type = "Area"
    _add_and_select_dataset(window, ds)

    window.gradient_checkbox.setChecked(True)
    assert ds.gradient_enabled is True

    index = window.gradient_target_combo.findData("fill")
    window.gradient_target_combo.setCurrentIndex(index)
    assert ds.gradient_target == "fill"


def test_property_changed_waterfall_checkbox_and_offsets(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    window.waterfall_checkbox.setChecked(True)
    assert ds.waterfall_enabled is True

    window.waterfall_offset_x_spinbox.setValue(2.0)
    assert ds.waterfall_offset_x == 2.0

    window.waterfall_offset_y_spinbox.setValue(3.0)
    assert ds.waterfall_offset_y == 3.0


def test_property_changed_error_display_combo(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    index = window.error_display_combo.findData("band")
    window.error_display_combo.setCurrentIndex(index)

    assert ds.error_display == "band"


# =============================================================================
# 色変更 (_on_dataset_color_changed / _on_gradient_color2_changed)
# =============================================================================

def test_dataset_color_changed_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window._on_dataset_color_changed("#ff0000")
    assert window.undo_stack.count() == before_count


def test_dataset_color_changed_single_dataset_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    original_color = ds.color
    _add_and_select_dataset(window, ds)

    window._on_dataset_color_changed("#ff0000")

    assert ds.color == "#ff0000"
    window.undo_stack.undo()
    assert ds.color == original_color


def test_dataset_color_changed_batch_macro(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)

    window._on_dataset_color_changed("#00ff00")

    assert all(ds.color == "#00ff00" for ds in datasets)
    window.undo_stack.undo()
    assert all(ds.color == "#1f77b4" for ds in datasets)


def test_gradient_color2_changed_single_dataset_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    window._on_gradient_color2_changed("#123123")

    assert ds.gradient_color2 == "#123123"
    window.undo_stack.undo()
    assert ds.gradient_color2 == "#ffffff"


def test_gradient_color2_changed_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window._on_gradient_color2_changed("#123123")
    assert window.undo_stack.count() == before_count


# =============================================================================
# 自動配色 (_on_auto_assign_colors)
# =============================================================================

def test_auto_assign_colors_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window._on_auto_assign_colors()
    assert window.undo_stack.count() == before_count


def test_auto_assign_colors_single_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    cycle = window._get_active_color_cycle()

    window._on_auto_assign_colors()

    assert ds.color == cycle[0]


def test_auto_assign_colors_batch_cycles_and_is_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    cycle = window._get_active_color_cycle()

    window._on_auto_assign_colors()

    for i, ds in enumerate(datasets):
        assert ds.color == cycle[i % len(cycle)]

    window.undo_stack.undo()
    assert all(ds.color == "#1f77b4" for ds in datasets)


# =============================================================================
# カラーパレット設定
# (_load_color_palettes / _save_color_palettes / _get_active_color_cycle / _on_manage_color_palettes)
# =============================================================================

def test_load_color_palettes_empty_by_default(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window._load_color_palettes() == {}


def test_save_and_load_color_palettes_round_trip(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    palettes = {"my_palette": ["#111111", "#222222"]}

    window._save_color_palettes(palettes)

    assert window._load_color_palettes() == palettes


def test_load_color_palettes_corrupted_json_returns_empty(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.settings.setValue(dataset_mixin_module.COLOR_PALETTES_SETTINGS_KEY, "{not valid json")

    assert window._load_color_palettes() == {}


def test_get_active_color_cycle_default_uses_matplotlib_cycle(tmp_path, monkeypatch):
    import matplotlib as mpl
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    expected = mpl.rcParams['axes.prop_cycle'].by_key()['color']
    assert window._get_active_color_cycle() == expected


def test_get_active_color_cycle_uses_custom_active_palette(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._save_color_palettes({"custom": ["#aaaaaa", "#bbbbbb"]})
    window.settings.setValue(dataset_mixin_module.ACTIVE_PALETTE_SETTINGS_KEY, "custom")

    assert window._get_active_color_cycle() == ["#aaaaaa", "#bbbbbb"]


def test_get_active_color_cycle_falls_back_when_active_palette_missing(tmp_path, monkeypatch):
    import matplotlib as mpl
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.settings.setValue(dataset_mixin_module.ACTIVE_PALETTE_SETTINGS_KEY, "deleted_palette")
    expected = mpl.rcParams['axes.prop_cycle'].by_key()['color']

    assert window._get_active_color_cycle() == expected


def test_manage_color_palettes_saves_result_on_accept(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    new_palettes = {"mine": ["#010101"]}
    _patch_dialog_result(
        monkeypatch, "ColorPaletteDialog", ColorPaletteDialog, "get_result",
        (new_palettes, "mine")
    )

    window._on_manage_color_palettes()

    assert window._load_color_palettes() == new_palettes
    assert window.settings.value(dataset_mixin_module.ACTIVE_PALETTE_SETTINGS_KEY) == "mine"


def test_manage_color_palettes_cancelled_does_not_save(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _patch_dialog_result(
        monkeypatch, "ColorPaletteDialog", ColorPaletteDialog, "get_result",
        ({"mine": ["#010101"]}, "mine"), accepted=False
    )

    window._on_manage_color_palettes()

    assert window._load_color_palettes() == {}


# =============================================================================
# 統計サマリー / フィット情報表示 (_update_ui_state / _update_stats_summary_label)
# =============================================================================

def test_select_dataset_with_fit_info_shows_fit_panel(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    ds.fit_info = "y = 2x + 1\nR^2 = 0.99"
    _add_and_select_dataset(window, ds)

    assert window.fit_info_textedit.toPlainText() == ds.fit_info


def test_select_fit_dataset_refreshes_residual_panel(tmp_path, monkeypatch):
    """項目C-406: fit_resultを持つデータセットを選択すると、残差プロット
    パネルにその残差が反映されること(_update_ui_state経由)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    ds.fit_result = {
        'fit_type': '線形 (y = ax + b)',
        'param_names': ['a', 'b'], 'params': [2.0, 1.0], 'param_errors': [0.1, 0.1],
        'residual_x': [0.0, 1.0, 2.0], 'residuals': [0.1, -0.2, 0.05],
    }
    _add_and_select_dataset(window, ds)

    # ★ residual_dock_widgetは既定で非表示のため、その祖先を含めた
    # isVisible()ではなくisVisibleTo(親)でパネル内部の表示状態だけを見る
    # (ドック自体を開くかどうかはユーザー操作であり、ここで検証したいのは
    # 「開いた場合に中身が正しく切り替わるか」というロジックのみ)。
    assert window.residual_panel.canvas.isVisibleTo(window.residual_panel) is True
    assert window.residual_panel.placeholder_label.isVisibleTo(window.residual_panel) is False


def test_select_dataset_without_fit_result_shows_residual_placeholder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)

    assert window.residual_panel.placeholder_label.isVisibleTo(window.residual_panel) is True
    assert window.residual_panel.canvas.isVisibleTo(window.residual_panel) is False


def test_deselecting_dataset_resets_residual_panel_to_placeholder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    ds.fit_result = {
        'param_names': ['a'], 'params': [1.0], 'param_errors': [0.1],
        'residual_x': [0.0, 1.0], 'residuals': [0.1, 0.2],
    }
    _add_and_select_dataset(window, ds)
    assert window.residual_panel.canvas.isVisibleTo(window.residual_panel) is True

    window.ui.dataset_list_widget.setCurrentItem(None)

    assert window.residual_panel.placeholder_label.isVisibleTo(window.residual_panel) is True
    assert window.residual_panel.canvas.isVisibleTo(window.residual_panel) is False


def test_residual_dock_widget_exists_and_hidden_by_default(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.residual_dock_widget.isHidden() is True


def test_stats_summary_all_nan_shows_placeholder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2], 'y': [np.nan, np.nan, np.nan]})
    ds = Dataset(name="allnan", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)

    assert window.stats_summary_label.text() == "-"
    assert window.dataset_mini_stats_label.text() == "allnan"


def test_stats_summary_non_numeric_column_shows_placeholder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2], 'y': ["a", "b", "c"]})
    ds = Dataset(name="textcol", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)

    assert window.stats_summary_label.text() == "-"
    assert window.dataset_mini_stats_label.text() == "textcol"


# =============================================================================
# データセット複製 (_on_duplicate_dataset)
# =============================================================================

def test_duplicate_dataset_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window._on_duplicate_dataset()
    assert len(window.project.datasets) == before_count


def test_duplicate_single_dataset_deep_copies_and_renames(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("original")
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)

    window._on_duplicate_dataset()

    assert len(window.project.datasets) == before_count + 1
    copy_ds = window.project.datasets[-1]
    assert copy_ds.name == "original (copy)"
    assert copy_ds is not ds
    assert copy_ds.df is not ds.df

    # 独立性の確認: 複製後に元を変更してもコピーには影響しない
    ds.df.loc[0, 'y'] = 999.0
    assert copy_ds.df.loc[0, 'y'] != 999.0

    # 複製されたアイテムがカレント選択になっている
    assert window._get_current_dataset() is copy_ds


def test_duplicate_dataset_preserves_parent_folder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("Folder")
    ds = _make_simple_dataset("original")
    window.project.datasets.append(ds)
    item = window._add_dataset_list_item(ds, folder)
    window.ui.dataset_list_widget.setCurrentItem(item)
    item.setSelected(True)

    window._on_duplicate_dataset()

    copy_item = window._get_dataset_tree_item(window.project.datasets[-1])
    assert copy_item.parent() is folder


def test_duplicate_multiple_selected_datasets(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    before_count = len(window.project.datasets)

    window._on_duplicate_dataset()

    assert len(window.project.datasets) == before_count + 2
    new_names = {ds.name for ds in window.project.datasets[before_count:]}
    assert new_names == {"d0 (copy)", "d1 (copy)"}


# =============================================================================
# データエディタ表示 (_on_show_data_editor: 早期returnのみ)
# =============================================================================

def test_show_data_editor_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.data_editor_dialog is None
    window._on_show_data_editor()
    assert window.data_editor_dialog is None


# =============================================================================
# プロット列変更 (_on_plot_column_changed)
# =============================================================================

def test_plot_column_changed_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window._on_plot_column_changed()
    assert window.undo_stack.count() == before_count


def test_plot_column_changed_x_only(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2], 'y': [1.0, 2.0, 3.0], 'z': [4.0, 5.0, 6.0]})
    ds = Dataset(name="d0", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)

    window.x_col_combo.setCurrentText('z')

    assert ds.x_col_name == 'z'
    window.undo_stack.undo()
    assert ds.x_col_name == 'x'


def test_plot_column_changed_y_only(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2], 'y': [1.0, 2.0, 3.0], 'z': [4.0, 5.0, 6.0]})
    ds = Dataset(name="d0", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)

    window.y_col_combo.setCurrentText('z')

    assert ds.y_col_name == 'z'


def test_plot_column_changed_both_at_once_single_command(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2], 'y': [1.0, 2.0, 3.0], 'z': [4.0, 5.0, 6.0]})
    ds = Dataset(name="d0", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    before_count = window.undo_stack.count()

    window.x_col_combo.blockSignals(True)
    window.y_col_combo.blockSignals(True)
    window.x_col_combo.setCurrentText('z')
    window.y_col_combo.setCurrentText('x')
    window.x_col_combo.blockSignals(False)
    window.y_col_combo.blockSignals(False)

    window._on_plot_column_changed()

    assert ds.x_col_name == 'z'
    assert ds.y_col_name == 'x'
    assert window.undo_stack.count() == before_count + 1

    window.undo_stack.undo()
    assert ds.x_col_name == 'x'
    assert ds.y_col_name == 'y'


# =============================================================================
# 誤差列変更 (_on_error_column_changed)
# =============================================================================

def test_error_column_changed_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window._on_error_column_changed()
    assert window.undo_stack.count() == before_count


def test_error_column_changed_sets_and_clears_error_columns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2], 'y': [1.0, 2.0, 3.0], 'yerr': [0.1, 0.1, 0.1]})
    ds = Dataset(name="d0", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)

    window.y_err_col_combo.setCurrentText('yerr')

    assert ds.y_err_col_name == 'yerr'

    window.y_err_col_combo.setCurrentText(dataset_mixin_module.NO_ERROR_COLUMN_LABEL)

    assert ds.y_err_col_name is None


# =============================================================================
# データ構造変更の反映 (_on_data_structure_changed)
# =============================================================================

def test_data_structure_changed_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._on_data_structure_changed()  # 例外が出なければOK


def test_data_structure_changed_refreshes_column_combos(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    ds.df['z'] = [7.0, 8.0, 9.0]

    window._on_data_structure_changed()

    items = [window.x_col_combo.itemText(i) for i in range(window.x_col_combo.count())]
    assert 'z' in items


# =============================================================================
# 曲線フィット (_on_fit_curve)
# =============================================================================

def test_fit_curve_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window._on_fit_curve()
    assert len(window.project.datasets) == before_count


def test_fit_curve_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, None)
    before_count = len(window.project.datasets)

    window._on_fit_curve()

    # ダイアログでキャンセルした場合はTaskRunnerが起動する前にreturnするため、
    # ポンピング不要(_fit_task_runnerはNoneのまま)。
    assert window._fit_task_runner is None
    assert len(window.project.datasets) == before_count


def test_fit_curve_success_adds_fit_dataset_and_shows_result(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    before_count = len(window.project.datasets)
    assert window.fit_result_dialog is None

    window._on_fit_curve()
    assert window._fit_task_runner is not None
    assert not window.fit_curve_button.isEnabled()
    _pump_events_until_fit_task_done(window)
    assert window.fit_curve_button.isEnabled()

    assert len(window.project.datasets) == before_count + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.name == "Fit (d0)"
    assert new_ds.fit_info is not None
    assert window.fit_result_dialog is not None

    # 項目C-401: fit_infoの表示文字列だけでなく、後続機能が再利用できる
    # 構造化フィット結果もあわせて保持されていること
    assert new_ds.fit_result is not None
    assert new_ds.fit_result['fit_type'] == "線形 (y = ax + b)"
    assert new_ds.fit_result['param_names'] == ['a', 'b']
    assert len(new_ds.fit_result['params']) == 2
    assert len(new_ds.fit_result['param_errors']) == 2
    assert new_ds.fit_result['weighted'] is False
    assert new_ds.fit_result['x_range'] is None
    assert new_ds.fit_result['source_dataset_id'] == ds.dataset_id
    assert new_ds.fit_result['source_dataset_name'] == "d0"

    parent_item = window._get_dataset_tree_item(ds).parent()
    fit_item_parent = window._get_dataset_tree_item(new_ds).parent()
    assert fit_item_parent == parent_item


def test_fit_curve_replaces_previous_result_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    first = window.fit_result_dialog
    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    second = window.fit_result_dialog

    assert second is not first
    second.close()


def test_fit_curve_with_weighted_and_x_range(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0", n=20)
    ds.df['yerr'] = 0.1
    ds.y_err_col_name = 'yerr'
    _add_and_select_dataset(window, ds)
    x_min = float(ds.x_data.min())
    x_max = float(ds.x_data.max())
    x_range = (x_min + 1, x_max - 1)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)", use_weighted=True, x_range=x_range)

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    new_ds = window.project.datasets[-1]
    assert "重みとして使用" in new_ds.fit_info
    assert "フィット範囲" in new_ds.fit_info
    assert new_ds.fit_result['weighted'] is True
    assert new_ds.fit_result['x_range'] == [x_range[0], x_range[1]]


def test_fit_curve_calculation_error_shows_warning(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")

    def raiser(*a, **k):
        raise RuntimeError("fit failed")

    # ★ 項目C-004フェーズ1: _on_fit_curve()は計算をTaskRunner経由で
    # fit_curve_task(dataset_mixin_module内にimport済み)に委ねるようになった
    # ため、以前のように直接呼んでいたcalculate_curve_fitではなく、実際の
    # 呼び出し対象であるfit_curve_taskをモックする。
    monkeypatch.setattr(dataset_mixin_module, "fit_curve_task", raiser)
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


# --- パラメータの初期値・固定・範囲拘束UI(項目C-403) ---

def test_fit_curve_with_fixed_param_holds_value_and_is_recorded(tmp_path, monkeypatch):
    """FitDialogでbを真の値に固定した場合、aだけが自由パラメータとして
    正しく収束し、fit_result['fixed_params']にprovenanceとして記録されること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0", slope=2.5, intercept=1.3, n=20)
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)", fixed_params={"b": 1.3})

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    new_ds = window.project.datasets[-1]
    a_index = new_ds.fit_result['param_names'].index('a')
    b_index = new_ds.fit_result['param_names'].index('b')
    assert new_ds.fit_result['params'][b_index] == pytest.approx(1.3)
    assert new_ds.fit_result['params'][a_index] == pytest.approx(2.5, abs=1e-6)
    assert new_ds.fit_result['param_errors'][b_index] == 0.0
    assert new_ds.fit_result['fixed_params'] == {"b": 1.3}
    assert "固定" in new_ds.fit_info


def test_fit_curve_with_p0_overrides_and_bounds_recorded(tmp_path, monkeypatch):
    """p0_overrides/boundsもfit_resultにprovenanceとして記録され、
    フィット自体は正常に完了すること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0", slope=2.5, intercept=1.3, n=20)
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(
        monkeypatch, "線形 (y = ax + b)",
        p0_overrides={"a": 1.0}, bounds={"a": (0.0, 10.0)},
    )

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    new_ds = window.project.datasets[-1]
    assert new_ds.fit_result['p0_overrides'] == {"a": 1.0}
    assert new_ds.fit_result['bounds'] == {"a": [0.0, 10.0]}
    a_index = new_ds.fit_result['param_names'].index('a')
    assert new_ds.fit_result['params'][a_index] == pytest.approx(2.5, abs=1e-3)
    assert "範囲拘束" in new_ds.fit_info


def test_fit_curve_without_customization_records_empty_dicts(tmp_path, monkeypatch):
    """C-403のオプションを何も使わなかった場合、fit_result内のp0_overrides/
    fixed_params/boundsはNoneではなく空dictであること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    new_ds = window.project.datasets[-1]
    assert new_ds.fit_result['p0_overrides'] == {}
    assert new_ds.fit_result['fixed_params'] == {}
    assert new_ds.fit_result['bounds'] == {}


def test_fit_curve_with_band_type_adds_band_columns_and_flag(tmp_path, monkeypatch):
    """項目C-405: band_typeを指定すると、フィットデータセットのdfに
    y_lower/y_upper列が追加され、fit_band_displayが設定されること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0", n=20)
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)", band_type="confidence")

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    new_ds = window.project.datasets[-1]
    assert new_ds.fit_band_display == "confidence"
    assert 'y_lower' in new_ds.df.columns
    assert 'y_upper' in new_ds.df.columns
    assert (new_ds.df['y_lower'] <= new_ds.df['y_upper']).all()


def test_fit_curve_without_band_type_adds_no_band_columns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    new_ds = window.project.datasets[-1]
    assert new_ds.fit_band_display is None
    assert 'y_lower' not in new_ds.df.columns
    assert 'y_upper' not in new_ds.df.columns


def test_batch_curve_fit_applies_fixed_params_to_all_datasets(tmp_path, monkeypatch):
    """バッチカーブフィットでも、1回だけ選んだfixed_params設定が選択中の
    全データセットに同じ条件で適用されること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [
        _make_linear_dataset("d0", slope=2.0, intercept=1.3, n=20),
        _make_linear_dataset("d1", slope=5.0, intercept=1.3, n=20),
    ]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)", fixed_params={"b": 1.3})
    _patch_info_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_batch_curve_fit()
    _pump_events_until_batch_fit_task_done(window)

    assert len(window.project.datasets) == before_count + 2
    for new_ds in window.project.datasets[-2:]:
        b_index = new_ds.fit_result['param_names'].index('b')
        assert new_ds.fit_result['params'][b_index] == pytest.approx(1.3)
        assert new_ds.fit_result['param_errors'][b_index] == 0.0
        assert new_ds.fit_result['fixed_params'] == {"b": 1.3}


def test_fit_curve_fixed_params_validation_error_shows_warning(tmp_path, monkeypatch):
    """全パラメータを固定するなど、calculate_curve_fit側のバリデーションに
    ひっかかるケースでも(素の例外ではなく)警告ダイアログで処理されること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(
        monkeypatch, "線形 (y = ax + b)", fixed_params={"a": 2.0, "b": 1.0},
    )
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


# =============================================================================
# フィット結果のエクスポート (_on_export_fit_result / _burn_fit_result_annotation, 項目C-413)
# =============================================================================

def test_context_menu_export_fit_action_disabled_for_plain_dataset(tmp_path, monkeypatch):
    """フィット結果を持たない通常のデータセットでは、メニュー項目はグレーアウトされる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    action = _RecordingMenu.last_instance.actions_by_text["フィット結果のエクスポート..."]
    assert action.isEnabled() is False


def test_context_menu_export_fit_action_enabled_for_fit_dataset(tmp_path, monkeypatch):
    """曲線フィットで生成したデータセット(fit_result保持)を選択中は有効になる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    fit_ds = window.project.datasets[-1]
    _select_items(window, [fit_ds])  # 既存アイテムをカレントにする(再追加しない)
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    action = _RecordingMenu.last_instance.actions_by_text["フィット結果のエクスポート..."]
    assert action.isEnabled() is True


def test_export_fit_result_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._on_export_fit_result()
    assert window.fit_result_dialog is None


def test_export_fit_result_without_fit_result_shows_info_and_no_crash(tmp_path, monkeypatch):
    """fit_resultを持たないデータセットを選択した状態で呼んでも、
    クラッシュせず親切な案内ダイアログが出るだけであること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    info_calls = _patch_info_capture(monkeypatch)

    window._on_export_fit_result()

    assert len(info_calls) == 1
    assert window.fit_result_dialog is None


def test_export_fit_result_reuses_stored_result_without_recompute(tmp_path, monkeypatch):
    """dataset.fit_result (項目C-401で永続化済み) だけから結果を再構成し、
    calculate_curve_fit() を一切呼び出さないこと(再フィットしないことの証明として、
    再度呼ばれたら例外を送出するようにモンキーパッチする)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0", slope=2.0, intercept=1.0, n=20)
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    fit_ds = window.project.datasets[-1]
    original_fit_result = fit_ds.fit_result
    _select_items(window, [fit_ds])

    def raiser(*a, **k):
        raise AssertionError("calculate_curve_fit() が再フィットのため呼び出された(再計算してはいけない)")

    monkeypatch.setattr(dataset_mixin_module, "calculate_curve_fit", raiser)
    _patch_question_yes(monkeypatch, accept=False)  # 注釈焼き込みはこのテストでは対象外

    window._on_export_fit_result()

    assert window.fit_result_dialog is not None
    dialog = window.fit_result_dialog
    assert "線形 (y = ax + b)" in dialog.text_edit.toPlainText()
    for param_name in original_fit_result['param_names']:
        assert param_name in dialog.text_edit.toPlainText()
    assert dialog.csv_data is not None
    assert list(dialog.csv_data['パラメータ']) == original_fit_result['param_names'] + ['R^2']
    np.testing.assert_allclose(
        list(dialog.csv_data['値']), original_fit_result['params'] + [original_fit_result['r_squared']]
    )
    dialog.close()


def test_export_fit_result_declining_annotation_adds_no_annotation(tmp_path, monkeypatch):
    """確認ダイアログで「いいえ」を選んだ場合、注釈は追加されないこと。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    fit_ds = window.project.datasets[-1]
    _select_items(window, [fit_ds])
    axis_index = fit_ds.subplot_target
    before_annotations = list(window.project.all_plot_settings[axis_index].get('annotations', []))
    _patch_question_yes(monkeypatch, accept=False)

    window._on_export_fit_result()
    window.fit_result_dialog.close()

    assert window.project.all_plot_settings[axis_index]['annotations'] == before_annotations


def test_export_fit_result_burns_annotation_undoable(tmp_path, monkeypatch):
    """確認ダイアログで「はい」を選ぶと、既存の注釈システムと同じデータモデル
    (project.all_plot_settings[axis_index]['annotations']) にフィット結果の
    要約テキスト注釈が追加され、Undoで取り消せること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0", slope=2.0, intercept=1.0, n=20)
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    fit_ds = window.project.datasets[-1]
    _select_items(window, [fit_ds])
    axis_index = fit_ds.subplot_target
    before_annotations = list(window.project.all_plot_settings[axis_index].get('annotations', []))
    _patch_question_yes(monkeypatch, accept=True)

    window._on_export_fit_result()
    window.fit_result_dialog.close()

    after_annotations = window.project.all_plot_settings[axis_index]['annotations']
    assert len(after_annotations) == len(before_annotations) + 1
    new_annotation = after_annotations[-1]
    assert new_annotation['type'] == 'text'
    assert "線形 (y = ax + b)" in new_annotation['text']
    assert "R^2" in new_annotation['text']
    for param_name in fit_ds.fit_result['param_names']:
        assert param_name in new_annotation['text']
    # アンカーはフィット曲線データセット自身のデータ点の中央付近であること
    mid_index = len(fit_ds.x_data) // 2
    assert new_annotation['xy'] == (float(fit_ds.x_data[mid_index]), float(fit_ds.y_data[mid_index]))

    # Undo/Redo可能(手動注釈追加と同じSetAnnotationsCommand経由)であること
    window.undo_stack.undo()
    assert window.project.all_plot_settings[axis_index]['annotations'] == before_annotations
    window.undo_stack.redo()
    assert window.project.all_plot_settings[axis_index]['annotations'] == after_annotations


def test_export_fit_result_annotation_anchored_to_correct_subplot(tmp_path, monkeypatch):
    """フィット対象データセットの描画先サブプロット(subplot_target)に
    正しく注釈が積まれること(他のサブプロットの注釈リストは変化しない)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    fit_ds = window.project.datasets[-1]
    assert fit_ds.subplot_target == 0
    _select_items(window, [fit_ds])
    _patch_question_yes(monkeypatch, accept=True)

    window._on_export_fit_result()
    window.fit_result_dialog.close()

    assert len(window.project.all_plot_settings[0]['annotations']) == 1


# =============================================================================
# 第2Y軸使用の切り替え (_on_secondary_y_changed)
# =============================================================================

def test_secondary_y_changed_no_selection_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = window.undo_stack.count()
    window._on_secondary_y_changed()
    assert window.undo_stack.count() == before_count


def test_secondary_y_changed_single_dataset_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    assert ds.use_secondary_y is False

    window.use_secondary_y_checkbox.setChecked(True)

    assert ds.use_secondary_y is True
    window.undo_stack.undo()
    assert ds.use_secondary_y is False


def test_secondary_y_changed_batch_macro(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)

    window.use_secondary_y_checkbox.setChecked(True)

    assert all(ds.use_secondary_y for ds in datasets)
    window.undo_stack.undo()
    assert all(not ds.use_secondary_y for ds in datasets)


# =============================================================================
# データセットの表示/非表示トグル (_on_dataset_tree_item_clicked, 項目C-907)
# =============================================================================

def test_dataset_tree_item_clicked_ignores_non_visibility_column(tmp_path, monkeypatch):
    """目アイコン専用列(DATASET_TREE_VISIBILITY_COLUMN)以外のクリックは無視する
    (名前列のクリックは選択切り替えのためのものであり、表示/非表示とは無関係)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    item = window._get_dataset_tree_item(ds)
    before_count = window.undo_stack.count()

    window._on_dataset_tree_item_clicked(item, DATASET_TREE_NAME_COLUMN)

    assert window.undo_stack.count() == before_count
    assert ds.visible is True


def test_dataset_tree_item_clicked_ignores_folder_items(tmp_path, monkeypatch):
    """フォルダアイテム(UserRoleがNone)には表示/非表示の概念が無いため無視する"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder_item = window._add_dataset_folder_item("folder1")
    before_count = window.undo_stack.count()

    window._on_dataset_tree_item_clicked(folder_item, DATASET_TREE_VISIBILITY_COLUMN)

    assert window.undo_stack.count() == before_count


def test_dataset_tree_item_clicked_toggles_visibility_and_is_undoable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    item = window._get_dataset_tree_item(ds)
    assert ds.visible is True

    window._on_dataset_tree_item_clicked(item, DATASET_TREE_VISIBILITY_COLUMN)
    assert ds.visible is False

    window.undo_stack.undo()
    assert ds.visible is True

    window.undo_stack.redo()
    assert ds.visible is False


def test_dataset_tree_item_clicked_triggers_replot(tmp_path, monkeypatch):
    """
    非表示にした瞬間にグラフから消えて見えるよう、クリック直後に再描画
    (_refresh_after_dataset_property_change経由)が呼ばれること。
    ★ 項目C-003フェーズ1: visibleプロパティの変更は軸の所属を変えないため、
    以前のような完全な_update_plot()ではなく、より軽量な
    canvas.update_single_axis()が呼ばれるようになった(意図した最適化
    そのもの)。そのためモック対象を
    _update_plotからcanvas.update_single_axisに変更する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    item = window._get_dataset_tree_item(ds)

    calls = []
    monkeypatch.setattr(window.canvas, "update_single_axis", lambda *a, **kw: calls.append(True))

    window._on_dataset_tree_item_clicked(item, DATASET_TREE_VISIBILITY_COLUMN)

    assert calls


def test_dataset_tree_item_clicked_actually_hides_dataset_from_next_redraw(tmp_path, monkeypatch):
    """トグル後、実際に_update_plot()を(モックせず)呼ぶと、キャンバス上の
    データセットもcanvas.redraw_all側のvisibleフィルタにより描画から消えること
    (gui/canvas.pyのredraw_all改修との結合を確認する)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("d0")
    _add_and_select_dataset(window, ds)
    item = window._get_dataset_tree_item(ds)
    assert len(window.canvas.all_axes[0].lines) == 1

    window._on_dataset_tree_item_clicked(item, DATASET_TREE_VISIBILITY_COLUMN)

    assert ds.visible is False
    assert len(window.canvas.all_axes[0].lines) == 0


def test_dataset_tree_item_clicked_single_click_with_other_items_selected_affects_only_clicked(tmp_path, monkeypatch):
    """複数選択中でも、選択に含まれないアイテムの目アイコンをクリックした場合は
    そのデータセット1件だけが切り替わり、選択中の他のデータセットには影響しない。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(3)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets[:2])  # 先頭2件だけ選択、3件目は非選択のまま
    item2 = window._get_dataset_tree_item(datasets[2])

    window._on_dataset_tree_item_clicked(item2, DATASET_TREE_VISIBILITY_COLUMN)

    assert datasets[2].visible is False
    assert datasets[0].visible is True
    assert datasets[1].visible is True


def test_dataset_tree_item_clicked_multi_selection_toggles_all_selected_as_batch(tmp_path, monkeypatch):
    """選択中のアイテムの目アイコンをクリックした場合は、選択中の全データセットへ
    一括で適用され(第2Y軸使用の一括切替と同じbeginMacro/endMacroパターン)、
    Undo1回で全部元に戻る。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_simple_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    items = _select_items(window, datasets)
    undo_count_before = window.undo_stack.count()

    window._on_dataset_tree_item_clicked(items[0], DATASET_TREE_VISIBILITY_COLUMN)

    assert all(ds.visible is False for ds in datasets)
    # バッチはbeginMacro/endMacroで1件のUndo操作にまとまる
    assert window.undo_stack.count() == undo_count_before + 1

    window.undo_stack.undo()
    assert all(ds.visible is True for ds in datasets)


# =============================================================================
# ピーク検出 (_on_find_peaks)
# =============================================================================

def _make_peaky_dataset(name="peaky"):
    x = np.linspace(0, 10, 100)
    y = np.sin(x) * 10
    df = pd.DataFrame({'x': x, 'y': y})
    return Dataset(name=name, df=df, x_col_name='x', y_col_name='y')


def test_find_peaks_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window._on_find_peaks()
    assert len(window.project.datasets) == before_count


def test_find_peaks_too_few_points_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1], 'y': [0.0, 1.0]})
    ds = Dataset(name="d0", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    warnings = _patch_warning_capture(monkeypatch)

    window._on_find_peaks()

    assert len(warnings) == 1


def test_find_peaks_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(monkeypatch, None)
    before_count = len(window.project.datasets)

    window._on_find_peaks()

    assert len(window.project.datasets) == before_count


def test_find_peaks_calculation_error_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )

    def raiser(*a, **k):
        raise ValueError("bad settings")

    monkeypatch.setattr(dataset_mixin_module, "calculate_peak_quantification", raiser)
    warnings = _patch_warning_capture(monkeypatch)

    window._on_find_peaks()

    assert len(warnings) == 1


def test_find_peaks_no_peaks_found_shows_info(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 1000.0, "distance_x": 1.0, "prominence": None}
    )
    info_calls = _patch_info_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_find_peaks()

    assert len(info_calls) == 1
    assert len(window.project.datasets) == before_count


def test_find_peaks_success_upward_adds_dataset_with_expected_style(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )
    before_count = len(window.project.datasets)

    window._on_find_peaks()

    assert len(window.project.datasets) == before_count + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.marker == 'v'
    assert new_ds.color == 'red'
    assert len(new_ds.df) > 0
    assert window.peak_result_dialog is not None


def test_find_peaks_result_table_includes_quantification_columns(tmp_path, monkeypatch):
    """項目C-411: 結果ダイアログのCSV用DataFrameにFWHM/面積/重心の列が追加されていること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )

    window._on_find_peaks()

    csv_data = window.peak_result_dialog.csv_data
    assert list(csv_data.columns) == ['X座標', 'Y座標', 'FWHM', '面積', '重心X']
    assert len(csv_data) > 0
    assert (csv_data['FWHM'] > 0).all()
    assert (csv_data['面積'] > 0).all()


def test_find_peaks_success_downward_uses_valley_style(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "下に凸 (Valleys)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )

    window._on_find_peaks()

    new_ds = window.project.datasets[-1]
    assert new_ds.marker == '^'
    assert new_ds.color == 'blue'


def test_find_peaks_replaces_previous_result_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )

    window._on_find_peaks()
    first = window.peak_result_dialog
    window._on_find_peaks()
    second = window.peak_result_dialog

    assert second is not first
    second.close()


# =============================================================================
# 区間積分 (_on_interval_integral_dataset, 項目C-311)
# =============================================================================

def _make_integral_dataset(n=50):
    x = np.linspace(0, 10, n)
    y = x.copy()  # y = x なので 0〜10 の積分は解析的に50とわかる(検証しやすいデータ)
    df = pd.DataFrame({'x': x, 'y': y})
    return Dataset(name="line", df=df, x_col_name='x', y_col_name='y')


def test_interval_integral_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._on_interval_integral_dataset()
    assert window.integral_result_dialog is None


def test_interval_integral_insufficient_points_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [1.0], 'y': [1.0]})
    ds = Dataset(name="d0", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    warnings = _patch_warning_capture(monkeypatch)

    window._on_interval_integral_dataset()

    assert len(warnings) == 1
    assert window.integral_result_dialog is None


def test_interval_integral_dialog_cancelled_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_integral_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "IntervalIntegralDialog", IntervalIntegralDialog, "get_settings",
        ("trapezoid", (0.0, 10.0), False), accepted=False
    )

    window._on_interval_integral_dataset()

    assert window.integral_result_dialog is None


def test_interval_integral_calculation_error_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_integral_dataset()
    _add_and_select_dataset(window, ds)
    # 範囲がデータのX範囲(0〜10)の外にあるため、calculate_interval_integralが
    # ValueErrorを送出するはず
    _patch_dialog_result(
        monkeypatch, "IntervalIntegralDialog", IntervalIntegralDialog, "get_settings",
        ("trapezoid", (-5.0, 20.0), False)
    )
    warnings = _patch_warning_capture(monkeypatch)

    window._on_interval_integral_dataset()

    assert len(warnings) == 1
    assert window.integral_result_dialog is None


def test_interval_integral_trapezoid_success_shows_result_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_integral_dataset()
    _add_and_select_dataset(window, ds)
    before_count = len(window.project.datasets)
    _patch_dialog_result(
        monkeypatch, "IntervalIntegralDialog", IntervalIntegralDialog, "get_settings",
        ("trapezoid", (0.0, 10.0), False)
    )

    window._on_interval_integral_dataset()

    # スカラー結果のみを返す機能のため、_on_savgol_dataset等と異なり
    # 新しいデータセットは追加されない
    assert len(window.project.datasets) == before_count
    assert window.integral_result_dialog is not None
    result_text = window.integral_result_dialog.text_edit.toPlainText()
    assert "50" in result_text
    assert "台形則" in result_text
    window.integral_result_dialog.close()


def test_interval_integral_simpson_success_shows_result_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_integral_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "IntervalIntegralDialog", IntervalIntegralDialog, "get_settings",
        ("simpson", (0.0, 10.0), False)
    )

    window._on_interval_integral_dataset()

    assert window.integral_result_dialog is not None
    result_text = window.integral_result_dialog.text_edit.toPlainText()
    assert "Simpson" in result_text
    window.integral_result_dialog.close()


def test_interval_integral_result_csv_data_has_expected_columns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_integral_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "IntervalIntegralDialog", IntervalIntegralDialog, "get_settings",
        ("trapezoid", (0.0, 10.0), False)
    )

    window._on_interval_integral_dataset()

    csv_data = window.integral_result_dialog.csv_data
    assert list(csv_data.columns) == ['X', 'Y(元データ)', 'Y(積分に使用)']
    assert len(csv_data) > 0
    window.integral_result_dialog.close()


def test_interval_integral_subtract_baseline_option_reflected_in_result(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    x = np.linspace(0, 10, 200)
    slope_bg = 2 * x + 1
    peak = 5 * np.exp(-((x - 5) ** 2) / (2 * 0.5 ** 2))
    df = pd.DataFrame({'x': x, 'y': slope_bg + peak})
    ds = Dataset(name="peak_on_slope", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "IntervalIntegralDialog", IntervalIntegralDialog, "get_settings",
        ("simpson", (0.0, 10.0), True)
    )

    window._on_interval_integral_dataset()

    result_text = window.integral_result_dialog.text_edit.toPlainText()
    assert "ベースライン差し引き: あり" in result_text
    expected_peak_area = 5 * 0.5 * np.sqrt(2 * np.pi)
    match = re.search(r"積分値\s*=\s*([\-0-9.eE+]+)", result_text)
    assert match is not None
    assert float(match.group(1)) == pytest.approx(expected_peak_area, rel=1e-2)
    window.integral_result_dialog.close()


def test_interval_integral_no_baseline_option_reflected_in_result(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_integral_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "IntervalIntegralDialog", IntervalIntegralDialog, "get_settings",
        ("trapezoid", (0.0, 10.0), False)
    )

    window._on_interval_integral_dataset()

    result_text = window.integral_result_dialog.text_edit.toPlainText()
    assert "ベースライン差し引き: なし" in result_text
    window.integral_result_dialog.close()


def test_interval_integral_replaces_previous_result_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_integral_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "IntervalIntegralDialog", IntervalIntegralDialog, "get_settings",
        ("trapezoid", (0.0, 10.0), False)
    )

    window._on_interval_integral_dataset()
    first = window.integral_result_dialog
    window._on_interval_integral_dataset()
    second = window.integral_result_dialog

    assert second is not first
    second.close()


# =============================================================================
# 共通X格子へのリサンプリング/補間 (_on_resample_dataset, 項目C-305)
# =============================================================================

def _make_resample_dataset(name="source", n=30):
    x = np.linspace(0, 10, n)
    y = x ** 2
    df = pd.DataFrame({'x': x, 'y': y})
    return Dataset(name=name, df=df, x_col_name='x', y_col_name='y')


def test_resample_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window._on_resample_dataset()
    assert len(window.project.datasets) == before_count


def test_resample_insufficient_points_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0], 'y': [0.0]})
    ds = Dataset(name="curve", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    warnings = _patch_warning_capture(monkeypatch)

    window._on_resample_dataset()

    assert len(warnings) == 1


def test_resample_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("linspace", {"start": 0.0, "stop": 10.0, "num_points": 20}, "linear", False, "source_resampled"),
        accepted=False
    )
    before_count = len(window.project.datasets)

    window._on_resample_dataset()

    assert len(window.project.datasets) == before_count


def test_resample_empty_output_name_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("linspace", {"start": 0.0, "stop": 10.0, "num_points": 20}, "linear", False, "")
    )
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_resample_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_resample_linspace_success_adds_dataset(tmp_path, monkeypatch):
    """等間隔グリッド(linspace方式)への線形補間で新しいデータセットが追加される"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("linspace", {"start": 2.0, "stop": 8.0, "num_points": 7}, "linear", False, "source_resampled")
    )
    before_count = len(window.project.datasets)

    window._on_resample_dataset()

    assert len(window.project.datasets) == before_count + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.name == "source_resampled"
    assert len(new_ds.x_data) == 7
    np.testing.assert_allclose(new_ds.x_data, np.linspace(2.0, 8.0, 7))
    # 元のデータセットは変更されていない(非破壊)
    np.testing.assert_allclose(ds.y_data, np.linspace(0, 10, 30) ** 2)


def test_resample_linspace_same_start_stop_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("linspace", {"start": 5.0, "stop": 5.0, "num_points": 10}, "linear", False, "source_resampled")
    )
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_resample_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_resample_onto_other_dataset_grid(tmp_path, monkeypatch):
    """「他のデータセットのX格子」を選ぶと、そのデータセットのX値がそのまま
    出力データセットのXとして使われる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    source = _make_resample_dataset(name="source")
    _add_and_select_dataset(window, source)
    target_x = np.array([1.0, 3.0, 5.0, 7.0])
    target_df = pd.DataFrame({'x': target_x, 'y': np.zeros(4)})
    target = Dataset(name="target_grid", df=target_df, x_col_name='x', y_col_name='y')
    window._add_dataset(target, None, select=False)
    # カレントを再びsourceに戻す(target追加でカレントが移っていないことを確認しつつ明示的に選び直す)
    _add_and_select_dataset(window, source)

    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("dataset", {"dataset_name": "target_grid"}, "linear", False, "source_on_target_grid")
    )

    window._on_resample_dataset()

    new_ds = window.project.datasets[-1]
    assert new_ds.name == "source_on_target_grid"
    np.testing.assert_allclose(new_ds.x_data, target_x)
    np.testing.assert_allclose(new_ds.y_data, target_x ** 2, atol=0.05)


def test_resample_missing_target_dataset_warns(tmp_path, monkeypatch):
    """コンボが無効化されている等でdataset_nameが選ばれていない(空/存在しない)場合は警告する"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("dataset", {"dataset_name": ""}, "linear", False, "source_resampled")
    )
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_resample_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_resample_calculation_error_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("linspace", {"start": 0.0, "stop": 10.0, "num_points": 20}, "cubic", False, "source_resampled")
    )

    def raiser(*a, **k):
        raise ValueError("3次スプライン補間には少なくとも4点のデータが必要です")

    monkeypatch.setattr(dataset_mixin_module, "calculate_resample_to_grid", raiser)
    warnings = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_resample_dataset()

    assert len(warnings) == 1
    assert len(window.project.datasets) == before_count


def test_resample_cubic_extrapolate_success(tmp_path, monkeypatch):
    """cubic + extrapolate=True の組み合わせも正常に動作する"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("linspace", {"start": -2.0, "stop": 12.0, "num_points": 10}, "cubic", True, "source_extrapolated")
    )

    window._on_resample_dataset()

    new_ds = window.project.datasets[-1]
    assert len(new_ds.y_data) == 10
    assert not np.isnan(new_ds.y_data).any()


# =============================================================================
# provenance記録 (項目C-1101): 派生データセット生成時にDataset.provenanceが
# 正しく設定されること
# =============================================================================

def test_arithmetic_records_provenance_with_both_source_datasets(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds_a, ds_b = _make_arith_pair()
    window._add_dataset(ds_a, None, select=False)
    window._add_dataset(ds_b, None, select=False)
    _select_items(window, [ds_a, ds_b])
    _patch_dialog_result(
        monkeypatch, "DatasetArithmeticDialog", DatasetArithmeticDialog,
        "get_settings", ("A - B", "diff")
    )

    window._on_dataset_arithmetic()

    prov = window.project.datasets[-1].provenance
    assert prov is not None
    assert prov['operation'] == 'arithmetic'
    assert set(prov['source_dataset_ids']) == {ds_a.dataset_id, ds_b.dataset_id}
    assert set(prov['source_dataset_names']) == {ds_a.name, ds_b.name}
    assert prov['params'] == {'operation_symbol': 'A - B'}
    assert prov['timestamp']


def test_normalize_records_provenance_with_source_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1, 2, 3], 'y': [1.0, 4.0, 2.0, 3.0]})
    dataset = Dataset(name="sample", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, dataset)
    _patch_normalize_dialog(monkeypatch, NormalizeDatasetDialog.MODE_MAX, None, "sample_normalized")

    window._on_normalize_dataset()

    prov = window.project.datasets[-1].provenance
    assert prov['operation'] == 'normalize'
    assert prov['source_dataset_ids'] == [dataset.dataset_id]
    assert prov['source_dataset_names'] == [dataset.name]
    assert prov['params']['mode'] == NormalizeDatasetDialog.MODE_MAX


def test_savgol_records_provenance_with_filter_params(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_savgol_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "SavGolDialog", SavGolDialog, "get_settings",
        (5, 2, 0, "curve_smoothed")
    )

    window._on_savgol_dataset()

    prov = window.project.datasets[-1].provenance
    assert prov['operation'] == 'savgol'
    assert prov['source_dataset_ids'] == [ds.dataset_id]
    assert prov['params'] == {'window_length': 5, 'polyorder': 2, 'deriv': 0}


def test_baseline_correction_records_provenance_with_method_in_operation_name(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_baseline_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "BaselineCorrectionDialog", BaselineCorrectionDialog, "get_settings",
        ("rubberband", {}, "corrected", False)
    )

    window._on_baseline_correction_dataset()

    prov = window.project.datasets[-1].provenance
    assert prov['operation'] == 'baseline_rubberband'
    assert prov['source_dataset_ids'] == [ds.dataset_id]


def test_resample_records_provenance_with_source_and_target_dataset_for_dataset_mode(tmp_path, monkeypatch):
    """リサンプリング先が「他のデータセット」の場合、source_dataset_idsに
    リサンプリング元(カレント)とリサンプリング先(target)の両方が入ること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset(name="source")
    target = _make_resample_dataset(name="target")
    window._add_dataset(ds, None, select=False)
    window._add_dataset(target, None, select=False)
    window.ui.dataset_list_widget.setCurrentItem(window._get_dataset_tree_item(ds))
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("dataset", {"dataset_name": "target"}, "linear", False, "resampled")
    )

    window._on_resample_dataset()

    prov = window.project.datasets[-1].provenance
    assert prov['operation'] == 'resample'
    assert set(prov['source_dataset_ids']) == {ds.dataset_id, target.dataset_id}
    assert prov['params']['source'] == 'dataset'


def test_resample_records_provenance_with_only_source_dataset_for_linspace_mode(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_resample_dataset()
    _add_and_select_dataset(window, ds)
    _patch_dialog_result(
        monkeypatch, "ResampleDatasetDialog", ResampleDatasetDialog, "get_settings",
        ("linspace", {"start": 0.0, "stop": 10.0, "num_points": 20}, "linear", False, "resampled")
    )

    window._on_resample_dataset()

    prov = window.project.datasets[-1].provenance
    assert prov['source_dataset_ids'] == [ds.dataset_id]


def test_fit_curve_records_provenance_reusing_fit_result_as_params(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")

    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)

    new_ds = window.project.datasets[-1]
    prov = new_ds.provenance
    assert prov['operation'] == 'curve_fit'
    assert prov['source_dataset_ids'] == [ds.dataset_id]
    assert prov['params'] is new_ds.fit_result


def test_batch_curve_fit_records_provenance_per_result(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    datasets = [_make_linear_dataset(f"d{i}") for i in range(2)]
    for ds in datasets:
        window._add_dataset(ds, None, select=False)
    _select_items(window, datasets)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    _patch_info_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_batch_curve_fit()
    _pump_events_until_batch_fit_task_done(window)

    new_datasets = window.project.datasets[before_count:]
    assert len(new_datasets) == 2
    for original, fit_ds in zip(datasets, new_datasets):
        assert fit_ds.provenance['operation'] == 'batch_curve_fit'
        assert fit_ds.provenance['source_dataset_ids'] == [original.dataset_id]


# =============================================================================
# 「方法」文のコピー (_on_copy_methods_text, 項目C-1102)
# =============================================================================

def test_copy_methods_text_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    QApplication.clipboard().setText("")
    window._on_copy_methods_text()
    assert QApplication.clipboard().text() == ""


def test_copy_methods_text_dataset_without_provenance_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("raw")
    _add_and_select_dataset(window, ds)
    QApplication.clipboard().setText("")

    window._on_copy_methods_text()

    assert QApplication.clipboard().text() == ""


def test_copy_methods_text_copies_generated_text_to_clipboard(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    fit_ds = window.project.datasets[-1]
    window.ui.dataset_list_widget.setCurrentItem(window._get_dataset_tree_item(fit_ds))

    window._on_copy_methods_text()

    clipboard_text = QApplication.clipboard().text()
    assert "d0" in clipboard_text
    assert "カーブフィット" in clipboard_text


def test_context_menu_copy_methods_text_action_disabled_without_provenance(tmp_path, monkeypatch):
    """処理履歴(provenance)を持たない元データでは、メニュー項目はグレーアウトされる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_simple_dataset("raw")
    _add_and_select_dataset(window, ds)
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    action = _RecordingMenu.last_instance.actions_by_text["「方法」文をコピー..."]
    assert action.isEnabled() is False


def test_context_menu_copy_methods_text_action_enabled_for_derived_dataset(tmp_path, monkeypatch):
    """provenanceを持つ派生データセット(フィット結果等)を選択中は有効になる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_linear_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_fit_dialog(monkeypatch, "線形 (y = ax + b)")
    window._on_fit_curve()
    _pump_events_until_fit_task_done(window)
    fit_ds = window.project.datasets[-1]
    _select_items(window, [fit_ds])
    _patch_recording_menu(monkeypatch)

    window._on_dataset_tree_context_menu(QPoint(0, 0))

    action = _RecordingMenu.last_instance.actions_by_text["「方法」文をコピー..."]
    assert action.isEnabled() is True


# =============================================================================
# 多峰分離フィット (_on_multi_peak_fit、項目C-409/C-410)
# =============================================================================

def _make_two_gaussian_dataset(name, n=200):
    x = np.linspace(-10, 20, n)
    y = (
        5.0 * np.exp(-((x - 0.0) ** 2) / (2 * 1.0 ** 2))
        + 3.0 * np.exp(-((x - 8.0) ** 2) / (2 * 1.5 ** 2))
        + 0.5
    )
    df = pd.DataFrame({'x': x, 'y': y})
    return Dataset(name=name, df=df, x_col_name='x', y_col_name='y')


def _patch_multi_peak_fit_dialog(monkeypatch, component_type, baseline_type='constant', initial_guesses=None):
    """
    MultiPeakFitDialog.get_multi_peak_fit_settings (staticmethod) をモーダル表示
    なしのフェイクに差し替える(_patch_fit_dialogの多峰版)。component_type=None
    はダイアログでキャンセルした場合を表す。
    """
    result = (component_type, baseline_type, initial_guesses) if component_type is not None \
        else (None, None, None)
    monkeypatch.setattr(
        dataset_mixin_module.MultiPeakFitDialog, "get_multi_peak_fit_settings",
        staticmethod(lambda *a, **k: result)
    )


def _pump_events_until_multi_peak_fit_task_done(window, max_iterations=300):
    """_pump_events_until_fit_task_doneの多峰版。"""
    app = QApplication.instance()
    for _ in range(max_iterations):
        app.processEvents()
        if window._multi_peak_fit_task_runner is None:
            return
        time.sleep(0.01)
    raise AssertionError("多峰分離フィット処理が時間内に完了しませんでした")


def test_multi_peak_fit_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window._on_multi_peak_fit()
    assert len(window.project.datasets) == before_count


def test_multi_peak_fit_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_two_gaussian_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_multi_peak_fit_dialog(monkeypatch, None)
    before_count = len(window.project.datasets)

    window._on_multi_peak_fit()

    assert window._multi_peak_fit_task_runner is None
    assert len(window.project.datasets) == before_count


def test_multi_peak_fit_success_adds_fit_dataset_and_shows_result(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_two_gaussian_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_multi_peak_fit_dialog(
        monkeypatch, "gaussian", baseline_type="constant",
        initial_guesses=[
            {'center': 0.2, 'height': 4.5, 'width': 1.0},
            {'center': 7.8, 'height': 2.8, 'width': 1.5},
        ],
    )
    before_count = len(window.project.datasets)
    assert window.fit_result_dialog is None

    window._on_multi_peak_fit()
    assert window._multi_peak_fit_task_runner is not None
    assert not window.multi_peak_fit_button.isEnabled()
    _pump_events_until_multi_peak_fit_task_done(window)
    assert window.multi_peak_fit_button.isEnabled()

    assert len(window.project.datasets) == before_count + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.name == "MultiPeakFit (d0)"
    assert new_ds.fit_info is not None
    assert window.fit_result_dialog is not None

    assert new_ds.fit_result is not None
    assert new_ds.fit_result['fit_type'] == 'multi_peak'
    assert new_ds.fit_result['component_type'] == 'gaussian'
    assert new_ds.fit_result['n_components'] == 2
    assert new_ds.fit_result['baseline_type'] == 'constant'
    assert new_ds.fit_result['param_names'] == ['a1', 'b1', 'c1', 'a2', 'b2', 'c2', 'baseline_c']
    assert len(new_ds.fit_result['params']) == 7
    assert new_ds.fit_result['r_squared'] == pytest.approx(1.0, abs=1e-3)
    assert len(new_ds.fit_result['components']) == 2
    assert new_ds.fit_result['source_dataset_id'] == ds.dataset_id
    assert new_ds.fit_result['source_dataset_name'] == "d0"


def test_multi_peak_fit_records_provenance_reusing_fit_result_as_params(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_two_gaussian_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_multi_peak_fit_dialog(
        monkeypatch, "gaussian", baseline_type="constant",
        initial_guesses=[{'center': 0.0, 'height': 5.0, 'width': 1.0}, {'center': 8.0, 'height': 3.0, 'width': 1.5}],
    )

    window._on_multi_peak_fit()
    _pump_events_until_multi_peak_fit_task_done(window)

    new_ds = window.project.datasets[-1]
    prov = new_ds.provenance
    assert prov['operation'] == 'multi_peak_fit'
    assert prov['source_dataset_ids'] == [ds.dataset_id]
    assert prov['params'] is new_ds.fit_result


def test_multi_peak_fit_methods_text_uses_component_type_and_count(tmp_path, monkeypatch):
    """項目C-1102: describe_operation()がprovenance['params']から
    component_type/n_componentsをそのまま参照できること(キー名の整合性確認)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_two_gaussian_dataset("d0")
    _add_and_select_dataset(window, ds)
    _patch_multi_peak_fit_dialog(
        monkeypatch, "gaussian", baseline_type="constant",
        initial_guesses=[{'center': 0.0, 'height': 5.0, 'width': 1.0}, {'center': 8.0, 'height': 3.0, 'width': 1.5}],
    )
    window._on_multi_peak_fit()
    _pump_events_until_multi_peak_fit_task_done(window)
    fit_ds = window.project.datasets[-1]
    window.ui.dataset_list_widget.setCurrentItem(window._get_dataset_tree_item(fit_ds))

    window._on_copy_methods_text()

    clipboard_text = QApplication.clipboard().text()
    assert "多峰分離フィット" in clipboard_text
    assert "gaussian x2" in clipboard_text


def test_multi_peak_fit_passes_and_clears_pending_peak_guesses(tmp_path, monkeypatch):
    """項目C-410: ピーク配置クリックモードで集めたself._pending_peak_guessesが
    ダイアログへ引き継がれ、ダイアログを閉じた後はクリアされること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_two_gaussian_dataset("d0")
    _add_and_select_dataset(window, ds)
    window._pending_peak_guesses = [{'center': 0.0, 'height': 5.0, 'width': 1.0}]
    window.peak_placement_mode_enabled = True
    window.peak_placement_action.setChecked(True)

    seen_kwargs = {}

    def fake_get_settings(*args, **kwargs):
        seen_kwargs.update(kwargs)
        return None, None, None  # キャンセル

    monkeypatch.setattr(
        dataset_mixin_module.MultiPeakFitDialog, "get_multi_peak_fit_settings",
        staticmethod(fake_get_settings)
    )

    window._on_multi_peak_fit()

    assert seen_kwargs['initial_guesses'] == [{'center': 0.0, 'height': 5.0, 'width': 1.0}]
    assert window._pending_peak_guesses == []
    assert window.peak_placement_mode_enabled is False
    assert window.peak_placement_action.isChecked() is False


def test_multi_peak_fit_calculation_error_shows_warning(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_two_gaussian_dataset("d0")
    _add_and_select_dataset(window, ds)
    # 不明な成分タイプを直接指定してcalculate_multi_peak_fit()側でValueErrorを
    # 起こす(_on_fit_curveのcalculation_error系テストと同じ、ダイアログの
    # 入力検証をバイパスしてバックグラウンド側のエラーハンドリングだけを狙う)。
    _patch_multi_peak_fit_dialog(
        monkeypatch, "not_a_real_component_type", baseline_type="constant",
        initial_guesses=[{'center': 0.0, 'height': 5.0, 'width': 1.0}],
    )
    warn_calls = _patch_warning_capture(monkeypatch)
    before_count = len(window.project.datasets)

    window._on_multi_peak_fit()
    _pump_events_until_multi_peak_fit_task_done(window)

    assert len(window.project.datasets) == before_count
    assert len(warn_calls) == 1
    assert window.multi_peak_fit_button.isEnabled()


def test_multi_peak_fit_busy_shows_info_when_already_running(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_two_gaussian_dataset("d0")
    _add_and_select_dataset(window, ds)
    info_calls = _patch_info_capture(monkeypatch)
    window._multi_peak_fit_task_runner = object()  # 実行中を模擬

    window._on_multi_peak_fit()

    assert len(info_calls) == 1
    window._multi_peak_fit_task_runner = None  # 後始末(他テストへの影響防止)
