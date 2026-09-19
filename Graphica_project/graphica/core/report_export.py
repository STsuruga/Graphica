"""グラフの画像と処理の「方法」の文をまとめたレポート(HTML)。GUI には依存しない。"""
import base64
import datetime
import html

from graphica.core.methods_text import generate_methods_text


def collect_methods_sections(project):
    """履歴を持つデータセットごとの (名前, 方法の文)。元データは含めない。"""
    return [
        (ds.name, generate_methods_text(ds, project))
        for ds in project.datasets
        if ds.provenance
    ]


def generate_html_report(image_png_bytes, methods_sections, title=""):
    """画像を base64 で埋め込んだ1ファイルで完結する HTML。title が空なら既定のタイトル。"""
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
