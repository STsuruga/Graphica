"""gui/datasets/peaks.py(ピーク検出と自動ラベル)のテスト。"""
import numpy as np
import pandas as pd

import graphica.gui.datasets.operations.peaks as peaks_module
from graphica.core.dataset import Dataset
from graphica.gui.dialogs import PeakSettingsDialog
from tests.test_dataset_mixin import (
    _add_and_select_dataset, _make_isolated_plotter_app, _patch_info_capture, _patch_warning_capture,
)


def _patch_peak_dialog(monkeypatch, settings_dict):
    """PeakSettingsDialog.get_peak_settings (staticmethod) をフェイクに差し替える(None=キャンセル)"""
    monkeypatch.setattr(
        PeakSettingsDialog, "get_peak_settings",
        staticmethod(lambda *a, **k: settings_dict)
    )


# =============================================================================
# ピーク検出 (PeakController.find_peaks)
# =============================================================================

def _make_peaky_dataset(name="peaky"):
    x = np.linspace(0, 10, 100)
    y = np.sin(x) * 10
    df = pd.DataFrame({'x': x, 'y': y})
    return Dataset(name=name, df=df, x_col_name='x', y_col_name='y')


def test_find_peaks_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    before_count = len(window.project.datasets)
    window.peaks.find_peaks()
    assert len(window.project.datasets) == before_count


def test_find_peaks_too_few_points_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1], 'y': [0.0, 1.0]})
    ds = Dataset(name="d0", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    warnings = _patch_warning_capture(monkeypatch)

    window.peaks.find_peaks()

    assert len(warnings) == 1


def test_find_peaks_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(monkeypatch, None)
    before_count = len(window.project.datasets)

    window.peaks.find_peaks()

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

    monkeypatch.setattr(peaks_module, "calculate_peak_quantification", raiser)
    warnings = _patch_warning_capture(monkeypatch)

    window.peaks.find_peaks()

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

    window.peaks.find_peaks()

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

    window.peaks.find_peaks()

    assert len(window.project.datasets) == before_count + 1
    new_ds = window.project.datasets[-1]
    assert new_ds.marker == 'v'
    assert new_ds.color == 'red'
    assert len(new_ds.df) > 0
    assert window.peaks.result_dialog is not None


def test_find_peaks_result_table_includes_quantification_columns(tmp_path, monkeypatch):
    """項目C-411: 結果ダイアログのCSV用DataFrameにFWHM/面積/重心の列が追加されていること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )

    window.peaks.find_peaks()

    csv_data = window.peaks.result_dialog.csv_data
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

    window.peaks.find_peaks()

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

    window.peaks.find_peaks()
    first = window.peaks.result_dialog
    window.peaks.find_peaks()
    second = window.peaks.result_dialog

    assert second is not first
    second.close()


# =============================================================================
# ピーク位置への自動ラベル (PeakController.add_peak_labels)
# =============================================================================

def test_add_smart_peak_labels_no_current_dataset_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.peaks.add_peak_labels()  # 例外にならないこと
    assert window.undo_stack.count() == 0


def test_add_smart_peak_labels_too_few_points_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.DataFrame({'x': [0, 1], 'y': [0.0, 1.0]})
    ds = Dataset(name="d0", df=df, x_col_name='x', y_col_name='y')
    _add_and_select_dataset(window, ds)
    warnings = _patch_warning_capture(monkeypatch)

    window.peaks.add_peak_labels()

    assert len(warnings) == 1


def test_add_smart_peak_labels_dialog_cancelled_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(monkeypatch, None)

    window.peaks.add_peak_labels()

    assert window.project.all_plot_settings[ds.subplot_target].get('annotations', []) == []


def test_add_smart_peak_labels_calculation_error_warns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )

    def raiser(*a, **k):
        raise ValueError("bad settings")

    monkeypatch.setattr(peaks_module, "calculate_peaks", raiser)
    warnings = _patch_warning_capture(monkeypatch)

    window.peaks.add_peak_labels()

    assert len(warnings) == 1


def test_add_smart_peak_labels_no_peaks_found_shows_info(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 1000.0, "distance_x": 1.0, "prominence": None}
    )
    info_calls = _patch_info_capture(monkeypatch)

    window.peaks.add_peak_labels()

    assert len(info_calls) == 1
    assert window.project.all_plot_settings[ds.subplot_target].get('annotations', []) == []


def test_add_smart_peak_labels_adds_one_annotation_per_peak(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )

    window.peaks.add_peak_labels()

    annotations = window.project.all_plot_settings[ds.subplot_target]['annotations']
    assert len(annotations) > 0
    assert all(a['type'] == 'text' for a in annotations)
    # sin(x)*10のピークはX昇順に単調増加するはずで、テキストはX値の文字列表現
    x_values = [float(a['text']) for a in annotations]
    assert x_values == sorted(x_values)


def test_add_smart_peak_labels_is_undoable_as_single_macro(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_peaky_dataset()
    _add_and_select_dataset(window, ds)
    _patch_peak_dialog(
        monkeypatch,
        {"peak_type": "上に凸 (Peaks)", "height": 0.0, "distance_x": 1.0, "prominence": None}
    )
    before_count = window.undo_stack.count()

    window.peaks.add_peak_labels()

    assert len(window.project.all_plot_settings[ds.subplot_target]['annotations']) > 1
    assert window.undo_stack.count() == before_count + 1  # 1回のUndo単位にまとまる

    window.undo_stack.undo()
    assert window.project.all_plot_settings[ds.subplot_target].get('annotations', []) == []
