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
from gui.dialogs import NormalizeDatasetDialog
from core.dataset import Dataset


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
