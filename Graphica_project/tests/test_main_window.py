# tests/test_main_window.py
"""
gui/main_window.py (PlotterApp) の統合的なGUI挙動に対する、最小限の回帰テスト。

PlotterApp のインスタンス化にはQApplicationが必要(conftest.pyのqappフィクスチャで用意)。
QSettingsは実際のレジストリ/iniファイルを汚染しないよう、一時ファイルにリダイレクトする。
"""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QToolButton

import gui.main_window as main_window_module
from gui.main_window import PlotterApp


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def test_properties_dock_has_no_horizontal_scrollbar(tmp_path, monkeypatch):
    """
    バグ回帰テスト: 「データセットのプロパティ」「プロットのプロパティ」を
    折りたたみ可能にした際(項目102)、縦スクロールバー分の幅を差し引いた
    ビューポート幅に対して中身がわずかにはみ出し、意図しない横スクロールバーが
    常時表示されてしまっていた。CONTROL_DOCK_WIDTHの拡幅とレイアウト余白の
    圧縮で解消済み。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    scroll_area = window.ui.control_dock_widget.widget()

    assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll_area.horizontalScrollBar().maximum() == 0
    # 中身の最小幅は、スクロールバー分を差し引いたビューポート幅に収まっているべき
    assert scroll_area.widget().minimumSizeHint().width() <= scroll_area.viewport().width()


def test_properties_dock_vertical_scroll_still_works_after_collapse(tmp_path, monkeypatch):
    """
    折りたたみアコーディオン(項目102)のトグル後も、縦スクロールバーの範囲が
    正しく再計算されることを確認する(横スクロールバー修正の副作用がないことの確認)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    scroll_area = window.ui.control_dock_widget.widget()
    vbar = scroll_area.verticalScrollBar()
    max_before = vbar.maximum()
    assert max_before > 0

    toggle_buttons = [
        b for b in window.ui.control_dock_widget.findChildren(QToolButton)
        if b.objectName() == "collapsible_section_toggle"
    ]
    assert len(toggle_buttons) == 2
    toggle_buttons[0].setChecked(False)

    app = QApplication.instance()
    for _ in range(10):
        app.processEvents()

    assert vbar.maximum() < max_before
