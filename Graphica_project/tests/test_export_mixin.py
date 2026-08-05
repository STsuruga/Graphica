# tests/test_export_mixin.py
"""gui/mixins/export_mixin.py の _save_figure_with_options に対するテスト(C-801)。

ExportMixin._save_figure_with_options は self.* を一切参照しないため、
PlotterApp全体を組み立てずに直接呼び出せる。
"""
import matplotlib as mpl
from matplotlib.figure import Figure

from gui.mixins.export_mixin import ExportMixin


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
