# tests/test_export_font_settings.py
"""
書き出し時のフォント設定の共有(v1.4.2)。

エクスポートプレビューから PDF を保存すると、メインの「名前を付けてエクスポート」と
違って pdf.fonttype=42(TrueType 埋め込み)が設定されず、Type 3 フォントの PDF に
なっていた。書き出し経路ごとに rc_context の中身を直接書いていたためで、
gui/export_settings.py の export_rc_params に1本化した。
"""
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui.export_settings import export_rc_params
from graphica.gui.main_window import PlotterApp


@pytest.mark.parametrize("fmt", ["pdf", ".pdf", "PDF", "eps", "ps"])
def test_pdf_like_formats_embed_truetype_fonts(fmt):
    assert export_rc_params(fmt) == {"pdf.fonttype": 42, "ps.fonttype": 42}


@pytest.mark.parametrize("as_path, fonttype", [(False, "none"), (True, "path")])
def test_svg_text_mode(as_path, fonttype):
    assert export_rc_params(".svg", as_path) == {"svg.fonttype": fonttype}


@pytest.mark.parametrize("fmt", ["png", ".jpg", "", None])
def test_raster_formats_change_nothing(fmt):
    assert export_rc_params(fmt) == {}


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    x = np.linspace(0, 10, 6)
    w.project.datasets.append(Dataset(name="sample", df=pd.DataFrame({"x": x, "y": np.sin(x)}),
                                      x_col_name="x", y_col_name="y"))
    w._update_plot()
    QApplication.instance().processEvents()
    yield w
    w.close()


def _font_subtypes(pdf_bytes):
    return {kind for kind in (b"/Type3", b"/TrueType", b"/CIDFontType2") if kind in pdf_bytes}


def test_preview_panel_pdf_embeds_truetype_fonts(window, monkeypatch, tmp_path):
    out_path = tmp_path / "preview.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_path), "")))
    window.export_preview_panel._on_save_clicked()
    data = out_path.read_bytes()
    assert b"/Type3" not in data
    assert _font_subtypes(data) & {b"/TrueType", b"/CIDFontType2"}


def test_preview_panel_and_main_export_write_the_same_font_type(window, monkeypatch, tmp_path):
    preview_path = tmp_path / "preview.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(preview_path), "")))
    window.export_preview_panel._on_save_clicked()

    main_path = tmp_path / "main.pdf"
    window._save_figure_with_options(window.canvas.fig, str(main_path),
                                     {"format": "pdf", "dpi": 100, "transparent": True})
    assert _font_subtypes(preview_path.read_bytes()) == _font_subtypes(main_path.read_bytes())
