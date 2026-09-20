"""論文用の LaTeX のコードとキャプションを作る。GUI には依存しない。"""
import re

# 1文字ずつ1回だけ置き換える(順に replace すると、置き換えで生まれた \ まで二重にエスケープしてしまう)
_LATEX_SPECIAL_CHARS = {
    '\\': r'\textbackslash{}',
    '{': r'\{',
    '}': r'\}',
    '$': r'\$',
    '&': r'\&',
    '%': r'\%',
    '#': r'\#',
    '_': r'\_',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
}

DEFAULT_WIDTH = r'\linewidth'


def escape_latex(text: str) -> str:
    if not text:
        return ''
    return ''.join(_LATEX_SPECIAL_CHARS.get(ch, ch) for ch in text)


def sanitize_label(text: str, prefix: str = 'fig:') -> str:
    """タイトルなどから \\label{} に使える文字列を作る(英数字・-・_ だけ残す)。何も残らなければ既定の名前。"""
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '', (text or '').strip().replace(' ', '-'))
    # 日本語だけのタイトルなどで、ハイフンだけの意味の無いラベルにならないように
    if not re.search(r'[A-Za-z0-9]', cleaned):
        return f"{prefix}plot"
    return f"{prefix}{cleaned}"


def generate_latex_figure(image_filename: str, caption: str, label: str, width: str = DEFAULT_WIDTH) -> str:
    """figure 環境一式。image_filename が空なら 'figure.pdf'(後で差し替える前提)、label が空なら \\label 行を省く。"""
    lines = [
        r'\begin{figure}[htbp]',
        r'    \centering',
        f"    \\includegraphics[width={width}]{{{image_filename or 'figure.pdf'}}}",
        f"    \\caption{{{escape_latex(caption)}}}",
    ]
    if label:
        lines.append(f"    \\label{{{label}}}")
    lines.append(r'\end{figure}')
    return '\n'.join(lines)
