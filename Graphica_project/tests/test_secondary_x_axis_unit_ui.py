# tests/test_secondary_x_axis_unit_ui.py
"""単位変換の第2X軸(項目C-602)のUI配線(コンボボックス <-> all_plot_settings)テスト。

PlotterApp のインスタンス化パターンは tests/test_main_window.py と同じ
(QSettingsを一時ファイルにリダイレクトする)。
"""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from core.unit_conversion import X_AXIS_UNIT_CHOICES


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 700)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def test_secondary_x_axis_unit_combos_default_to_none(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert X_AXIS_UNIT_CHOICES[window.x_secondary_axis_source_unit_combo.currentIndex()] == 'none'
    assert X_AXIS_UNIT_CHOICES[window.x_secondary_axis_target_unit_combo.currentIndex()] == 'none'
    settings = window.project.all_plot_settings[window.project.active_axis_index]
    assert settings.get('x_secondary_axis_source_unit', 'none') == 'none'
    assert settings.get('x_secondary_axis_target_unit', 'none') == 'none'


def test_changing_unit_combos_updates_active_plot_settings(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    window.x_secondary_axis_source_unit_combo.setCurrentIndex(X_AXIS_UNIT_CHOICES.index('nm'))
    window.x_secondary_axis_target_unit_combo.setCurrentIndex(X_AXIS_UNIT_CHOICES.index('eV'))

    settings = window.project.all_plot_settings[window.project.active_axis_index]
    assert settings['x_secondary_axis_source_unit'] == 'nm'
    assert settings['x_secondary_axis_target_unit'] == 'eV'


def test_switching_active_axis_restores_its_own_unit_settings(tmp_path, monkeypatch):
    """サブプロットごとに独立した設定であること(2つ目のプロットに切り替えたら
    UIも2つ目の設定を反映すること)を確認する。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_cols_spinbox.setValue(2)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    window.active_axis_combo.setCurrentIndex(0)
    window.x_secondary_axis_source_unit_combo.setCurrentIndex(X_AXIS_UNIT_CHOICES.index('nm'))
    window.x_secondary_axis_target_unit_combo.setCurrentIndex(X_AXIS_UNIT_CHOICES.index('Hz'))

    window.active_axis_combo.setCurrentIndex(1)
    assert X_AXIS_UNIT_CHOICES[window.x_secondary_axis_source_unit_combo.currentIndex()] == 'none'
    assert X_AXIS_UNIT_CHOICES[window.x_secondary_axis_target_unit_combo.currentIndex()] == 'none'

    window.active_axis_combo.setCurrentIndex(0)
    assert X_AXIS_UNIT_CHOICES[window.x_secondary_axis_source_unit_combo.currentIndex()] == 'nm'
    assert X_AXIS_UNIT_CHOICES[window.x_secondary_axis_target_unit_combo.currentIndex()] == 'Hz'
