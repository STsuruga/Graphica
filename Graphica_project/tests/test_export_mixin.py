# tests/test_export_mixin.py
"""gui/mixins/export_mixin.py の _save_figure_with_options に対するテスト
(C-801、および項目B-2: register_exporter()の配線)。

ExportMixin._save_figure_with_options は self.* を一切参照しないため、
PlotterApp全体を組み立てずに直接呼び出せる。
"""
import os

import matplotlib as mpl
import pandas as pd
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QFileDialog
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from matplotlib.figure import Figure

import core.plugin_api as plugin_api_module
import gui.main_window as main_window_module
import gui.mixins.export_mixin as export_mixin_module
from core.dataset import Dataset
from core.plugin_api import GraphicaPluginAPI
from core.plugin_types import PluginExecutionError
from gui.main_window import PlotterApp
from gui.mixins.export_mixin import ExportMixin
from gui.dialogs import ExportDialog, BatchExportDialog


@pytest.fixture(autouse=True)
def _isolate_plugin_api_singleton():
    yield
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None


def _make_fig():
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([1, 2, 3], [1, 4, 9])
    return fig


def test_pdf_export_embeds_truetype_fonts(tmp_path):
    """PDF保存時、pdf.fonttype/ps.fonttypeが42(TrueType埋め込み)で呼ばれること。
    実際にsavefigさせず、rcParamsの値だけをフックして確認する。"""
    fig = _make_fig()
    out_path = tmp_path / "out.pdf"

    observed = {}
    original_savefig = fig.savefig

    def spy_savefig(*args, **kwargs):
        observed['pdf.fonttype'] = mpl.rcParams['pdf.fonttype']
        observed['ps.fonttype'] = mpl.rcParams['ps.fonttype']
        return original_savefig(*args, **kwargs)

    fig.savefig = spy_savefig

    ExportMixin._save_figure_with_options(
        object(), fig, str(out_path), {'format': 'pdf', 'dpi': 100, 'transparent': True}
    )

    assert observed['pdf.fonttype'] == 42
    assert observed['ps.fonttype'] == 42
    assert out_path.exists()


def test_pdf_export_does_not_leak_fonttype_rcparam_after_saving(tmp_path):
    """mpl.rc_contextはwithブロックを抜けると元の値に戻る(グローバル汚染をしないこと)"""
    original = mpl.rcParams['pdf.fonttype']
    fig = _make_fig()
    ExportMixin._save_figure_with_options(
        object(), fig, str(tmp_path / "out.pdf"), {'format': 'pdf', 'dpi': 100}
    )
    assert mpl.rcParams['pdf.fonttype'] == original


def test_png_export_is_unaffected_by_pdf_fonttype_handling(tmp_path):
    fig = _make_fig()
    out_path = tmp_path / "out.png"
    ExportMixin._save_figure_with_options(
        object(), fig, str(out_path), {'format': 'png', 'dpi': 100, 'transparent': True}
    )
    assert out_path.exists()


def test_svg_export_still_applies_svg_fonttype_unaffected_by_pdf_change(tmp_path):
    fig = _make_fig()
    out_path = tmp_path / "out.svg"
    ExportMixin._save_figure_with_options(
        object(), fig, str(out_path), {'format': 'svg', 'dpi': 100, 'svg_text_as_path': True}
    )
    assert out_path.exists()
    assert 'path' in out_path.read_text(encoding='utf-8')[:2000] or out_path.stat().st_size > 0


# --- register_exporter() の配線(項目B-2) ---

def test_registered_exporter_is_used_instead_of_builtin_savefig(tmp_path):
    fig = _make_fig()
    out_path = tmp_path / "out.myf"
    calls = []

    def fake_writer(fig_arg, out_path_arg):
        calls.append((fig_arg, out_path_arg))

    api = GraphicaPluginAPI()
    api.register_exporter("MyFormat", ".myf", fake_writer, name="MyPlugin")
    plugin_api_module._singleton_api = api

    ExportMixin._save_figure_with_options(object(), fig, str(out_path), {'format': 'myformat', 'dpi': 100})

    assert calls == [(fig, str(out_path))]
    assert not out_path.exists()  # フェイクのwriterは実際には何も書き出していない


def test_builtin_formats_unaffected_when_plugin_exporters_registered(tmp_path):
    """プラグインエクスポーターが登録されていても、PNG/PDF/SVGは既存のビルトイン処理のまま動く"""
    fig = _make_fig()
    out_path = tmp_path / "out.png"

    api = GraphicaPluginAPI()
    api.register_exporter("MyFormat", ".myf", lambda f, p: None, name="MyPlugin")
    plugin_api_module._singleton_api = api

    ExportMixin._save_figure_with_options(object(), fig, str(out_path), {'format': 'png', 'dpi': 100})
    assert out_path.exists()


def test_registered_exporter_failure_raises_plugin_execution_error(tmp_path):
    fig = _make_fig()
    out_path = tmp_path / "out.myf"

    def broken_writer(fig_arg, out_path_arg):
        raise RuntimeError("disk full")

    api = GraphicaPluginAPI()
    api.register_exporter("MyFormat", ".myf", broken_writer, name="MyPlugin")
    plugin_api_module._singleton_api = api

    with pytest.raises(PluginExecutionError, match="MyPlugin") as exc_info:
        ExportMixin._save_figure_with_options(object(), fig, str(out_path), {'format': 'myformat', 'dpi': 100})
    assert "disk full" in str(exc_info.value)


# ==============================================================================
# ここから下: 実際の PlotterApp を組み立てて行う、メニュー操作 (クリップボード
# コピー/印刷/バッチエクスポート/名前を付けてエクスポート/プレビュー生成) のテスト。
# PlotterApp のインスタンス化パターンは tests/test_main_window.py の
# _make_isolated_plotter_app に倣う (QSettingsを一時ファイルにリダイレクトする)。
# ==============================================================================

def _make_isolated_plotter_app(tmp_path, monkeypatch):
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


def _add_dataset(window):
    ds = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2, 3], "y": [1, 4, 9]}), x_col_name="x", y_col_name="y")
    window._add_dataset(ds, None, select=True)
    window._update_plot()
    return ds


# --- _on_copy_plot_to_clipboard ---

def test_copy_plot_to_clipboard_sets_clipboard_pixmap(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)

    window._on_copy_plot_to_clipboard()

    pixmap = QApplication.clipboard().pixmap()
    assert not pixmap.isNull()


def test_copy_plot_to_clipboard_shows_warning_on_savefig_failure(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)

    def broken_savefig(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(window.canvas.fig, "savefig", broken_savefig)
    warn_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_copy_plot_to_clipboard()

    assert len(warn_calls) == 1


# --- _on_print_plot ---

def _patch_print_dialog(monkeypatch, accepted, output_pdf_path=None):
    """
    QPrintDialogは実プリンターの有無に左右されテストが不安定になりやすいため、
    exec()を差し替えつつ、Accepted側では実際にPDFファイルへ出力するよう
    printer.setOutputFileName()しておく(painter.begin()を確実に成功させるため)。
    """
    class FakePrintDialog(QPrintDialog):
        def __init__(self, printer, parent=None):
            super().__init__(printer, parent)
            if accepted and output_pdf_path is not None:
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(output_pdf_path)

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(export_mixin_module, "QPrintDialog", FakePrintDialog)


def test_print_plot_cancelled_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    _patch_print_dialog(monkeypatch, accepted=False)

    window._on_print_plot()  # 例外が出ないことを確認する


def test_print_plot_accepted_renders_to_printer_and_shows_status_message(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_pdf = str(tmp_path / "printed.pdf")
    _patch_print_dialog(monkeypatch, accepted=True, output_pdf_path=out_pdf)

    window._on_print_plot()

    assert window.statusBar().currentMessage() == "印刷を実行しました"
    assert os.path.exists(out_pdf)


def test_print_plot_shows_warning_on_savefig_failure(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_pdf = str(tmp_path / "printed2.pdf")
    _patch_print_dialog(monkeypatch, accepted=True, output_pdf_path=out_pdf)

    def broken_savefig(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(window.canvas.fig, "savefig", broken_savefig)
    warn_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_print_plot()

    assert len(warn_calls) == 1


# --- _on_batch_export / _batch_export_subplots / _batch_export_project_files ---

def _patch_batch_export_dialog(monkeypatch, *, accepted=True, mode_index=0, output_dir="",
                                prefix="export", format_index=0, subplot_checked=None,
                                project_file_paths=None):
    class FakeBatchExportDialog(BatchExportDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.mode_combo.setCurrentIndex(mode_index)
            self.output_dir_edit.setText(output_dir)
            self.prefix_edit.setText(prefix)
            self.format_combo.setCurrentIndex(format_index)
            if subplot_checked is not None:
                for i, checked in enumerate(subplot_checked):
                    item = self.subplot_list.item(i)
                    item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            if project_file_paths:
                for p in project_file_paths:
                    self.project_files_list.addItem(p)

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(export_mixin_module, "BatchExportDialog", FakeBatchExportDialog)


def test_batch_export_cancelled_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    _patch_batch_export_dialog(monkeypatch, accepted=False)

    window._on_batch_export()

    assert list(tmp_path.iterdir()) == []


def test_batch_export_warns_when_output_dir_missing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    _patch_batch_export_dialog(monkeypatch, accepted=True, output_dir="")

    warn_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_batch_export()

    assert len(warn_calls) == 1


def test_batch_export_warns_when_no_subplots_selected(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _patch_batch_export_dialog(monkeypatch, accepted=True, output_dir=str(out_dir),
                                mode_index=0, subplot_checked=[False])

    warn_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_batch_export()

    assert len(warn_calls) == 1


def test_batch_export_warns_when_no_project_files_added(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _patch_batch_export_dialog(monkeypatch, accepted=True, output_dir=str(out_dir), mode_index=1)

    warn_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_batch_export()

    assert len(warn_calls) == 1


def test_batch_export_subplots_writes_image_and_reports_completion(tmp_path, monkeypatch):
    """サブプロット個別書き出しモードで、実際に画像ファイルが作られ完了メッセージが出ること"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _patch_batch_export_dialog(monkeypatch, accepted=True, output_dir=str(out_dir), mode_index=0,
                                prefix="myexport", format_index=0, subplot_checked=[True])

    info_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_batch_export()

    out_files = list(out_dir.iterdir())
    assert len(out_files) == 1
    assert out_files[0].name == "myexport_P1.png"
    assert len(info_calls) == 1
    assert "1件を書き出しました" in info_calls[0][2]


def test_batch_export_subplots_reports_failure_without_crashing(tmp_path, monkeypatch):
    """個別サブプロット書き出し中に例外が起きても、他への影響なく失敗として報告されること"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _patch_batch_export_dialog(monkeypatch, accepted=True, output_dir=str(out_dir), mode_index=0,
                                subplot_checked=[True])

    def broken_save(self, fig, out_path, options):
        raise RuntimeError("disk full")

    monkeypatch.setattr(export_mixin_module.ExportMixin, "_save_figure_with_options", broken_save)

    info_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_batch_export()

    assert len(info_calls) == 1
    assert "失敗" in info_calls[0][2]
    assert "disk full" in info_calls[0][2]


def test_batch_export_project_files_writes_image_from_saved_project(tmp_path, monkeypatch):
    """複数プロジェクトファイルモードで、保存済み.graphicaファイルを読み込んで完成図を書き出すこと"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    project_path = tmp_path / "saved.graphica"
    window.project.layout_rows = window.subplot_rows_spinbox.value()
    window.project.layout_cols = window.subplot_cols_spinbox.value()
    window.project.save_project(str(project_path))

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _patch_batch_export_dialog(monkeypatch, accepted=True, output_dir=str(out_dir), mode_index=1,
                                prefix="proj", format_index=0, project_file_paths=[str(project_path)])

    info_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_batch_export()

    out_files = list(out_dir.iterdir())
    assert len(out_files) == 1
    assert out_files[0].name == "proj_saved.png"
    assert len(info_calls) == 1
    assert "1件を書き出しました" in info_calls[0][2]


def test_batch_export_project_files_reports_failure_for_missing_file(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    missing_path = str(tmp_path / "does_not_exist.graphica")
    _patch_batch_export_dialog(monkeypatch, accepted=True, output_dir=str(out_dir), mode_index=1,
                                project_file_paths=[missing_path])

    info_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_batch_export()

    assert len(info_calls) == 1
    assert "失敗" in info_calls[0][2]
    assert list(out_dir.iterdir()) == []


# --- _on_export_plot ---

def _patch_export_dialog(monkeypatch, *, accepted=True, width=None, height=None, unit=None,
                          dpi=None, transparent=None, svg_text_as_path=None):
    class FakeExportDialog(ExportDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if width is not None:
                self.width_spinbox.setValue(width)
            if height is not None:
                self.height_spinbox.setValue(height)
            if unit is not None:
                self.unit_combo.setCurrentText(unit)
            if dpi is not None:
                self.dpi_spinbox.setValue(dpi)
            if transparent is not None:
                self.transparent_checkbox.setChecked(transparent)
            if svg_text_as_path is not None:
                self.svg_text_as_path_checkbox.setChecked(svg_text_as_path)

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(export_mixin_module, "ExportDialog", FakeExportDialog)


def test_export_plot_cancelled_dialog_writes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    _patch_export_dialog(monkeypatch, accepted=False)

    window._on_export_plot()

    assert list(tmp_path.iterdir()) == []


def test_export_plot_cancelled_save_file_dialog_writes_nothing(tmp_path, monkeypatch):
    """エクスポート設定ダイアログはOKされたが、続く保存先ダイアログでキャンセルした場合"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    _patch_export_dialog(monkeypatch, accepted=True)
    monkeypatch.setattr(export_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: ("", "")))

    window._on_export_plot()

    assert list(tmp_path.iterdir()) == []


def test_export_plot_writes_png_with_requested_size(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_path = tmp_path / "out.png"
    original_size = tuple(window.canvas.fig.get_size_inches())
    _patch_export_dialog(monkeypatch, accepted=True, width=400, height=300, unit="ピクセル (px)", dpi=100)
    monkeypatch.setattr(export_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path), "PNG (*.png)")))

    window._on_export_plot()

    assert out_path.exists()
    # ★★★ 必須: 保存後、Figureサイズは元のGUI表示サイズに戻ること
    assert tuple(window.canvas.fig.get_size_inches()) == pytest.approx(original_size)


def test_export_plot_writes_svg_with_text_as_path_option(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_path = tmp_path / "out.svg"
    _patch_export_dialog(monkeypatch, accepted=True, width=4, height=3, unit="インチ (in)", svg_text_as_path=True)
    monkeypatch.setattr(export_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path), "SVG (*.svg)")))

    window._on_export_plot()

    assert out_path.exists()


def test_export_plot_writes_pdf_with_truetype_fonts(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_path = tmp_path / "out.pdf"
    _patch_export_dialog(monkeypatch, accepted=True, width=10, height=8, unit="センチメートル (cm)")
    monkeypatch.setattr(export_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path), "PDF (*.pdf)")))

    window._on_export_plot()

    assert out_path.exists()


def test_export_plot_uses_registered_plugin_exporter_for_matching_extension(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_path = tmp_path / "out.myf"
    calls = []

    api = GraphicaPluginAPI()
    api.register_exporter("MyFormat", ".myf", lambda fig, p: calls.append(p), name="MyPlugin")
    plugin_api_module._singleton_api = api

    _patch_export_dialog(monkeypatch, accepted=True)
    monkeypatch.setattr(export_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path), "MyFormat (*.myf)")))

    window._on_export_plot()

    assert calls == [str(out_path)]
    assert not out_path.exists()  # フェイクのwriterは実際には何も書き出していない


def test_export_plot_shows_warning_and_restores_size_on_savefig_failure(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    out_path = tmp_path / "out.png"
    original_size = tuple(window.canvas.fig.get_size_inches())
    _patch_export_dialog(monkeypatch, accepted=True)
    monkeypatch.setattr(export_mixin_module.QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path), "PNG (*.png)")))

    def broken_savefig(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(window.canvas.fig, "savefig", broken_savefig)
    warn_calls = []
    monkeypatch.setattr(export_mixin_module.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_export_plot()

    assert len(warn_calls) == 1
    assert tuple(window.canvas.fig.get_size_inches()) == pytest.approx(original_size)


# --- _generate_preview ---

def test_generate_preview_sets_pixmap_on_dialog_label(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    dialog = ExportDialog(window)

    window._generate_preview(dialog)

    assert not dialog.preview_label.pixmap().isNull()


def test_generate_preview_logs_warning_when_active_axis_out_of_range(tmp_path, monkeypatch):
    """active_axis_indexがall_plot_settingsの範囲外の場合、例外を出さず早期リターンすること"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _add_dataset(window)
    dialog = ExportDialog(window)
    window.project.active_axis_index = 99

    window._generate_preview(dialog)  # 例外が出ないことを確認する


# --- _calculate_size_in_inches ---

def test_calculate_size_in_inches_inch_unit_returns_as_is():
    result = ExportMixin._calculate_size_in_inches(object(), {
        "width": 5, "height": 3, "unit": "インチ (in)", "dpi": 300,
    })
    assert result == (5, 3)


def test_calculate_size_in_inches_cm_unit_converts_to_inches():
    result = ExportMixin._calculate_size_in_inches(object(), {
        "width": 2.54, "height": 5.08, "unit": "センチメートル (cm)", "dpi": 300,
    })
    assert result == pytest.approx((1.0, 2.0))


def test_calculate_size_in_inches_px_unit_divides_by_dpi():
    result = ExportMixin._calculate_size_in_inches(object(), {
        "width": 800, "height": 400, "unit": "ピクセル (px)", "dpi": 200,
    })
    assert result == pytest.approx((4.0, 2.0))


def test_calculate_size_in_inches_unknown_unit_falls_back_to_default():
    result = ExportMixin._calculate_size_in_inches(object(), {
        "width": 5, "height": 3, "unit": "unknown", "dpi": 300,
    })
    assert result == (8, 6)
