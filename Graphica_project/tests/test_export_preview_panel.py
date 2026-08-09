# tests/test_export_preview_panel.py
"""gui/export_preview_panel.py (ExportPreviewPanel) に対するテスト。

ExportPreviewPanelはmain_windowの実データ(canvas/project/_calculate_size_in_inches)に
依存しているため、標準単体では構築できない。CLAUDE.mdの指示通り、tests/
test_gui_style_regression.pyと同じ「隔離されたQSettingsを使った完全なPlotterAppを
1つ作り、その window.export_preview_panel を使う」パターンを踏襲する。
"""
import matplotlib.figure
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from core.dataset import Dataset


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る
    (tests/test_gui_style_regression.pyの同名ヘルパーと同じパターン)。"""
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


def _make_dataset(name="sample", n_points=6):
    x = np.linspace(0, 10, n_points)
    y = np.sin(x)
    df = pd.DataFrame({"x": x, "y": y})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y")


def _populate_sample_plot(window):
    ds = _make_dataset()
    window.project.datasets.append(ds)
    window._update_plot()


def _process_events():
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()


@pytest.fixture
def window_with_plot(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _populate_sample_plot(window)
    window.export_preview_dock_widget.show()
    _process_events()
    return window


def _capture_message_box(monkeypatch):
    calls = {"warning": [], "information": []}
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a))
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: calls["information"].append(a))
    )
    return calls


# --- _render_preview: 早期returnとプレースホルダー表示 ---

def test_render_preview_returns_early_when_size_non_positive(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel
    monkeypatch.setattr(window_with_plot, "_calculate_size_in_inches", lambda opts: (0, 0))

    panel._current_pixmap = "sentinel"  # 早期returnなら書き換わらないことの目印
    panel._render_preview()

    assert panel._current_pixmap == "sentinel"


def test_render_preview_shows_placeholder_when_pixmap_generation_fails(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel
    monkeypatch.setattr(panel, "_render_full_figure_pixmap", lambda *a, **k: None)

    panel._render_preview()

    assert panel._current_pixmap is None
    assert "プレビューを生成できませんでした" in panel.preview_label.text()


def test_render_preview_success_sets_pixmap_and_clears_placeholder_text(window_with_plot):
    panel = window_with_plot.export_preview_panel

    panel._render_preview()

    assert panel._current_pixmap is not None
    assert not panel._current_pixmap.isNull()
    assert panel.preview_label.text() == ""
    assert panel.preview_label.pixmap() is not None
    assert not panel.preview_label.pixmap().isNull()


# --- resizeEvent: 既存プレビューの再スケール ---

def test_resize_event_rescales_existing_pixmap(window_with_plot):
    panel = window_with_plot.export_preview_panel
    panel._render_preview()
    assert panel._current_pixmap is not None

    panel.resize(panel.width() + 60, panel.height() + 40)
    _process_events()

    pixmap = panel.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()


def test_resize_event_noop_when_no_pixmap_yet(window_with_plot):
    panel = window_with_plot.export_preview_panel
    assert panel._current_pixmap is None

    panel.resize(panel.width() + 60, panel.height() + 40)  # 例外にならない
    _process_events()


# --- _make_temp_canvas_for_full_figure: プロットが無い場合はNone ---

def test_make_temp_canvas_returns_none_for_free_layout_without_plot_settings(window_with_plot):
    panel = window_with_plot.export_preview_panel
    window_with_plot.project.layout_mode = 'free'
    window_with_plot.project.all_plot_settings = []

    result = panel._make_temp_canvas_for_full_figure(4.0, 3.0, 150)

    assert result is None


def test_make_temp_canvas_returns_none_when_grid_dimensions_zero(window_with_plot):
    panel = window_with_plot.export_preview_panel
    window_with_plot.subplot_rows_spinbox.setRange(0, 10)
    window_with_plot.subplot_rows_spinbox.setValue(0)

    result = panel._make_temp_canvas_for_full_figure(4.0, 3.0, 150)

    assert result is None


def test_make_temp_canvas_returns_canvas_for_valid_grid(window_with_plot):
    panel = window_with_plot.export_preview_panel
    canvas = panel._make_temp_canvas_for_full_figure(4.0, 3.0, 100)
    try:
        assert canvas is not None
    finally:
        if canvas is not None:
            canvas.deleteLater()


# --- _render_full_figure_pixmap ---

def test_render_full_figure_pixmap_returns_none_when_no_plot(window_with_plot):
    panel = window_with_plot.export_preview_panel
    window_with_plot.project.layout_mode = 'free'
    window_with_plot.project.all_plot_settings = []

    assert panel._render_full_figure_pixmap(4.0, 3.0, 100) is None


def test_render_full_figure_pixmap_handles_savefig_exception(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel

    def _raise(*a, **k):
        raise RuntimeError("savefigが失敗した(テスト用)")

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", _raise)

    assert panel._render_full_figure_pixmap(4.0, 3.0, 100) is None


# --- _render_full_figure_bytes ---

def test_render_full_figure_bytes_png(window_with_plot):
    panel = window_with_plot.export_preview_panel
    data = panel._render_full_figure_bytes(4.0, 3.0, 100, fmt='png', transparent=True)
    assert data is not None
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_full_figure_bytes_svg_text_as_path_false(window_with_plot):
    panel = window_with_plot.export_preview_panel
    data = panel._render_full_figure_bytes(
        4.0, 3.0, 100, fmt='svg', transparent=False, svg_text_as_path=False
    )
    assert data is not None
    assert b"<svg" in data or b"<?xml" in data


def test_render_full_figure_bytes_svg_text_as_path_true(window_with_plot):
    panel = window_with_plot.export_preview_panel
    data = panel._render_full_figure_bytes(
        4.0, 3.0, 100, fmt='svg', transparent=False, svg_text_as_path=True
    )
    assert data is not None
    assert b"<svg" in data or b"<?xml" in data


def test_render_full_figure_bytes_returns_none_when_no_plot(window_with_plot):
    panel = window_with_plot.export_preview_panel
    window_with_plot.project.layout_mode = 'free'
    window_with_plot.project.all_plot_settings = []

    assert panel._render_full_figure_bytes(4.0, 3.0, 100, fmt='png', transparent=True) is None


def test_render_full_figure_bytes_handles_savefig_exception(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel

    def _raise(*a, **k):
        raise RuntimeError("savefigが失敗した(テスト用)")

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", _raise)

    assert panel._render_full_figure_bytes(4.0, 3.0, 100, fmt='png', transparent=True) is None


# --- _on_copy_clicked ---

def test_on_copy_clicked_warns_when_size_non_positive(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel
    calls = _capture_message_box(monkeypatch)
    monkeypatch.setattr(window_with_plot, "_calculate_size_in_inches", lambda opts: (0, 0))

    panel._on_copy_clicked()

    assert len(calls["warning"]) == 1


def test_on_copy_clicked_png_sets_clipboard_pixmap(window_with_plot):
    panel = window_with_plot.export_preview_panel
    panel.copy_format_combo.setCurrentText("PNG")

    panel._on_copy_clicked()

    pixmap = QApplication.clipboard().pixmap()
    assert pixmap is not None and not pixmap.isNull()


def test_on_copy_clicked_png_none_shows_warning(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel
    panel.copy_format_combo.setCurrentText("PNG")
    calls = _capture_message_box(monkeypatch)
    monkeypatch.setattr(panel, "_render_full_figure_bytes", lambda *a, **k: None)

    panel._on_copy_clicked()

    assert len(calls["warning"]) == 1


def test_on_copy_clicked_svg_sets_clipboard_mime_data(window_with_plot):
    panel = window_with_plot.export_preview_panel
    panel.copy_format_combo.setCurrentText("SVG")

    panel._on_copy_clicked()

    mime_data = QApplication.clipboard().mimeData()
    assert mime_data.hasFormat("image/svg+xml")


def test_on_copy_clicked_svg_none_shows_warning(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel
    panel.copy_format_combo.setCurrentText("SVG")
    calls = _capture_message_box(monkeypatch)
    monkeypatch.setattr(panel, "_render_full_figure_bytes", lambda *a, **k: None)

    panel._on_copy_clicked()

    assert len(calls["warning"]) == 1


# --- _on_save_clicked ---

def test_on_save_clicked_warns_when_free_layout_has_no_plots(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel
    calls = _capture_message_box(monkeypatch)
    dialog_calls = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: dialog_calls.append(1) or ("", ""))
    )
    window_with_plot.project.layout_mode = 'free'
    window_with_plot.project.all_plot_settings = []

    panel._on_save_clicked()

    assert len(calls["warning"]) == 1
    assert dialog_calls == []  # ファイルダイアログすら開かれない


def test_on_save_clicked_warns_when_grid_dimensions_zero(window_with_plot, monkeypatch):
    panel = window_with_plot.export_preview_panel
    calls = _capture_message_box(monkeypatch)
    window_with_plot.subplot_rows_spinbox.setRange(0, 10)
    window_with_plot.subplot_rows_spinbox.setValue(0)

    panel._on_save_clicked()

    assert len(calls["warning"]) == 1


def test_on_save_clicked_cancelled_file_dialog_does_nothing(window_with_plot, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    panel = window_with_plot.export_preview_panel
    panel._on_save_clicked()  # 例外なく終了(保存されない)


def test_on_save_clicked_saves_png_file(window_with_plot, monkeypatch, tmp_path):
    out_path = str(tmp_path / "out.png")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out_path, "")))

    panel = window_with_plot.export_preview_panel
    panel._on_save_clicked()

    import os
    assert os.path.exists(out_path)


def test_on_save_clicked_saves_svg_file_with_text_as_path(window_with_plot, monkeypatch, tmp_path):
    out_path = str(tmp_path / "out.svg")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out_path, "")))
    panel = window_with_plot.export_preview_panel
    panel.svg_text_as_path_checkbox.setChecked(True)

    panel._on_save_clicked()

    import os
    assert os.path.exists(out_path)


def test_on_save_clicked_temp_canvas_none_after_dialog_shows_warning(window_with_plot, monkeypatch, tmp_path):
    """
    最初のガード(レイアウト/行列数チェック)は通過したが、ファイルダイアログの後で
    改めて_make_temp_canvas_for_full_figure()を呼んだ結果Noneだった場合の
    二重チェック分岐を確認する。
    """
    out_path = str(tmp_path / "out.png")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out_path, "")))
    calls = _capture_message_box(monkeypatch)

    panel = window_with_plot.export_preview_panel
    monkeypatch.setattr(panel, "_make_temp_canvas_for_full_figure", lambda *a, **k: None)

    panel._on_save_clicked()

    assert len(calls["warning"]) == 1
    import os
    assert not os.path.exists(out_path)


def test_on_save_clicked_handles_savefig_exception(window_with_plot, monkeypatch, tmp_path):
    out_path = str(tmp_path / "out.png")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out_path, "")))
    calls = _capture_message_box(monkeypatch)

    def _raise(*a, **k):
        raise RuntimeError("savefigが失敗した(テスト用)")

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", _raise)

    panel = window_with_plot.export_preview_panel
    panel._on_save_clicked()

    assert len(calls["warning"]) == 1
    assert "エクスポート中にエラー" in calls["warning"][0][2]
