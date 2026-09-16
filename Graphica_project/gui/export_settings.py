# gui/export_settings.py
"""
画像/ベクター書き出し時に一時的に適用する matplotlib の rcParams。

★ 書き出しの経路は4つある(名前を付けてエクスポート、バッチエクスポート、
  エクスポートプレビューの保存、同プレビューのコピー)。以前はそれぞれが
  rc_context の中身を直接書いており、プレビューの保存だけ PDF のフォント
  埋め込み(pdf.fonttype=42)が抜けていた。同じ図でも保存した場所によって
  Illustrator 等で文字を編集できたりできなかったりしたため、ここに1本化する。
"""


def export_rc_params(fmt, svg_text_as_path=False):
    """
    書き出し形式に応じて mpl.rc_context() に渡す辞書を返す。

    - SVG: 目盛りの数字や凡例の文字をテキスト要素(既定、'none')として残すか、
      パス('path'、項目88)に変換するか。
    - PDF: フォントを TrueType(Type 42)として埋め込む(項目C-801)。matplotlib 既定の
      Type 3 だとベクター編集ソフトで文字として選択・編集できない。
    - それ以外(PNG 等のラスタ): 変更なし。

    Args:
        fmt (str): 'svg' / 'pdf' / 'png' など。先頭のドットと大文字小文字は無視する。
        svg_text_as_path (bool): SVG の文字をパスに変換するか。
    """
    fmt = (fmt or '').lower().lstrip('.')
    if fmt == 'svg':
        return {'svg.fonttype': 'path' if svg_text_as_path else 'none'}
    if fmt in ('pdf', 'ps', 'eps'):
        return {'pdf.fonttype': 42, 'ps.fonttype': 42}
    return {}
