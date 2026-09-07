# tests/test_report_export.py
"""core/report_export.py(項目157、C-1104: PDF/HTML実験レポート自動ビルド)のテスト。"""
import pandas as pd
import pytest

from core.dataset import Dataset
from core.report_export import collect_methods_sections, generate_html_report
from models.project import ProjectModel


def _make_dataset(name, provenance=None):
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1.0, 2.0, 3.0]})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y", provenance=provenance)


def _make_provenance(source_ids=None, source_names=None):
    return {
        'operation': 'cumulative_integral',
        'params': {'method': 'trapezoid'},
        'source_dataset_ids': source_ids or [],
        'source_dataset_names': source_names or [],
        'timestamp': '2026-09-08T00:00:00',
    }


# --- collect_methods_sections ---

def test_collect_methods_sections_skips_datasets_without_provenance():
    project = ProjectModel()
    project.datasets.append(_make_dataset("raw"))
    assert collect_methods_sections(project) == []


def test_collect_methods_sections_includes_datasets_with_provenance():
    project = ProjectModel()
    ds = _make_dataset("processed", provenance=_make_provenance())
    project.datasets.append(ds)

    sections = collect_methods_sections(project)

    assert len(sections) == 1
    assert sections[0][0] == "processed"
    assert isinstance(sections[0][1], str)
    assert sections[0][1]  # 空文字列ではない


def test_collect_methods_sections_preserves_dataset_order():
    project = ProjectModel()
    ds1 = _make_dataset("first", provenance=_make_provenance())
    ds2 = _make_dataset("second", provenance=_make_provenance())
    project.datasets.extend([ds1, ds2])

    sections = collect_methods_sections(project)

    assert [name for name, _ in sections] == ["first", "second"]


# --- generate_html_report ---

def test_generate_html_report_embeds_image_as_base64():
    html = generate_html_report(b"fake-png-bytes", [], title="Report")
    assert "data:image/png;base64," in html
    import base64
    assert base64.b64encode(b"fake-png-bytes").decode('ascii') in html


def test_generate_html_report_uses_default_title_when_empty():
    html = generate_html_report(b"x", [], title="")
    assert "実験レポート" in html


def test_generate_html_report_escapes_title_html():
    html = generate_html_report(b"x", [], title="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_generate_html_report_lists_methods_sections():
    html = generate_html_report(b"x", [("ds1", "Method text for ds1")], title="Report")
    assert "ds1" in html
    assert "Method text for ds1" in html


def test_generate_html_report_shows_placeholder_when_no_methods_sections():
    html = generate_html_report(b"x", [], title="Report")
    assert "処理履歴を持つデータセットはありません" in html


def test_generate_html_report_is_valid_minimal_html():
    html = generate_html_report(b"x", [], title="Report")
    assert html.strip().startswith("<!doctype html>")
    assert "<html>" in html
    assert "</html>" in html
