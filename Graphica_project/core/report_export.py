# core/report_export.py
"""
PDF/HTML実験レポート自動ビルド(項目157、C-1104)。
既存のprovenance記録(C-1101)・「方法」文の自動生成(C-1102、
core/methods_text.py)の出力先として、それらをグラフ画像とまとめた
1つのレポートを組み立てる。GUIに一切依存しない純粋関数のみを置く
(gui/mixins/export_mixin.pyがPNG画像バイト列/PDFページの生成を担当する)。
"""
import base64
import datetime
import html

from core.methods_text import generate_methods_text


def collect_methods_sections(project):
    """
    project内の、処理履歴(provenance)を持つデータセットそれぞれについて
    (データセット名, 方法文)のタプルのリストを返す(処理履歴を持たない
    元データのデータセットは対象外)。
    """
    return [
        (ds.name, generate_methods_text(ds, project))
        for ds in project.datasets
        if ds.provenance
    ]


def generate_html_report(image_png_bytes, methods_sections, title=""):
    """
    実験レポートを自己完結のHTML文字列として生成する(画像はbase64で
    埋め込むため、単一ファイルで完結し外部ファイル参照が要らない)。

    Args:
        image_png_bytes (bytes): グラフのPNG画像データ。
        methods_sections (list[tuple[str, str]]): collect_methods_sections()の戻り値。
        title (str): レポートのタイトル(空なら既定のタイトルを使う)。

    Returns:
        str: HTML文字列。
    """
    title_text = title.strip() or "実験レポート"
    title_html = html.escape(title_text)
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    image_b64 = base64.b64encode(image_png_bytes).decode('ascii')

    if methods_sections:
        items = "".join(
            f"<li><b>{html.escape(name)}</b>: {html.escape(text)}</li>"
            for name, text in methods_sections
        )
        methods_html = f"<ul>{items}</ul>"
    else:
        methods_html = "<p>(処理履歴を持つデータセットはありません)</p>"

    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\">"
        f"<title>{title_html}</title>\n"
        "<style>\n"
        "body { font-family: sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; }\n"
        "img { max-width: 100%; border: 1px solid #ccc; }\n"
        "</style></head><body>\n"
        f"<h1>{title_html}</h1>\n"
        f"<p>生成日時: {generated_at}</p>\n"
        f"<img src=\"data:image/png;base64,{image_b64}\" alt=\"plot\">\n"
        "<h2>方法</h2>\n"
        f"{methods_html}\n"
        "</body></html>\n"
    )
