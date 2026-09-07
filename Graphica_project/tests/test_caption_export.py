# tests/test_caption_export.py
"""core/caption_export.py(項目142、C-807: LaTeX/Word用キャプション自動生成)のテスト。"""
from core.caption_export import escape_latex, sanitize_label, generate_latex_figure


# --- escape_latex ---

def test_escape_latex_escapes_percent_ampersand_underscore():
    assert escape_latex("Y (%) & Test_1") == r"Y (\%) \& Test\_1"


def test_escape_latex_handles_empty_string():
    assert escape_latex("") == ""


def test_escape_latex_handles_none():
    assert escape_latex(None) == ""


def test_escape_latex_escapes_backslash_before_other_chars():
    assert escape_latex("a\\b") == r"a\textbackslash{}b"


# --- sanitize_label ---

def test_sanitize_label_keeps_alphanumeric_and_converts_spaces_to_hyphens():
    assert sanitize_label("Figure 1 Result") == "fig:Figure-1-Result"


def test_sanitize_label_falls_back_when_no_alphanumeric_survives():
    """日本語のみのタイトル等、英数字が1文字も残らない場合は既定名にフォールバック"""
    assert sanitize_label("吸収スペクトル") == "fig:plot"


def test_sanitize_label_falls_back_for_empty_string():
    assert sanitize_label("") == "fig:plot"


def test_sanitize_label_accepts_custom_prefix():
    assert sanitize_label("test", prefix="tab:") == "tab:test"


# --- generate_latex_figure ---

def test_generate_latex_figure_includes_all_parts():
    latex = generate_latex_figure("plot.pdf", "My Caption", "fig:test")
    assert r"\includegraphics[width=\linewidth]{plot.pdf}" in latex
    assert r"\caption{My Caption}" in latex
    assert r"\label{fig:test}" in latex
    assert latex.startswith(r"\begin{figure}[htbp]")
    assert latex.endswith(r"\end{figure}")


def test_generate_latex_figure_omits_label_line_when_empty():
    latex = generate_latex_figure("plot.pdf", "Caption", "")
    assert "\\label" not in latex


def test_generate_latex_figure_uses_placeholder_when_image_name_empty():
    latex = generate_latex_figure("", "Caption", "fig:x")
    assert "{figure.pdf}" in latex


def test_generate_latex_figure_escapes_caption_special_characters():
    latex = generate_latex_figure("plot.pdf", "50% yield & more", "fig:x")
    assert r"\caption{50\% yield \& more}" in latex


def test_generate_latex_figure_respects_custom_width():
    latex = generate_latex_figure("plot.pdf", "Caption", "fig:x", width=r"0.5\linewidth")
    assert r"[width=0.5\linewidth]" in latex
