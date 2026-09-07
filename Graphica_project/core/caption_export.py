# core/caption_export.py
"""
LaTeX/Word用キャプション・埋め込みコード自動生成(項目142、C-807)。
GUIに一切依存しない純粋関数のみを置く(gui/dialogs.pyのCaptionGeneratorDialogが
ライブプレビューのために毎回呼び出す想定)。
"""
import re

# LaTeXの特殊文字エスケープ表(\\は最初に処理しないと、他の置換で生成した
# バックスラッシュまで二重にエスケープしてしまうため、呼び出し側は
# 文字ごとに1回だけ変換するループで処理する(下のescape_latex参照)。
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


def escape_latex(text):
    """LaTeXのキャプション等に埋め込む前に特殊文字をエスケープする。"""
    if not text:
        return ''
    return ''.join(_LATEX_SPECIAL_CHARS.get(ch, ch) for ch in text)


def sanitize_label(text, prefix='fig:'):
    """
    任意の文字列(通常はグラフのタイトル)から、LaTeXの\\label{}として安全な
    文字列を作る。英数字・ハイフン・アンダースコア以外は捨てる(空白はハイフンに
    変換してから捨てる)。結果が空になる場合は既定名にフォールバックする。
    """
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '', (text or '').strip().replace(' ', '-'))
    # 英数字を1文字も含まない場合(日本語のみのタイトル等)は、ハイフンの羅列のような
    # 意味の無いラベルにしないため既定名にフォールバックする。
    if not re.search(r'[A-Za-z0-9]', cleaned):
        return f"{prefix}plot"
    return f"{prefix}{cleaned}"


def generate_latex_figure(image_filename, caption, label, width=DEFAULT_WIDTH):
    """
    \\includegraphics一式(figure環境)を生成する。

    Args:
        image_filename (str): 画像ファイル名(パスの一部でも可)。空なら
            プレースホルダ'figure.pdf'を使う(ユーザーが後から差し替える前提)。
        caption (str): 図のキャプション(LaTeX特殊文字は自動的にエスケープする)。
        label (str): \\label{}に使う文字列(空ならlabel行自体を省略する)。
        width (str): \\includegraphicsのwidthオプション(既定'\\linewidth')。

    Returns:
        str: 複数行のLaTeXコード。
    """
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
