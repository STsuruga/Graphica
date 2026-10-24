"""書き出しの経路で共有するもの。matplotlib の rcParams は、書き出しの経路すべてがこれを使うこと。"""


def export_rc_params(fmt, svg_text_as_path=False):
    """mpl.rc_context() に渡す辞書。

    SVG は文字をテキストのまま残すか、パスにするか。PDF はフォントを TrueType(Type 42)で埋め込む
    (既定の Type 3 だとベクター編集ソフトで文字を編集できない)。ラスタは何もしない。
    fmt の先頭のドットと大文字小文字は無視する。
    """
    fmt = (fmt or '').lower().lstrip('.')
    if fmt == 'svg':
        return {'svg.fonttype': 'path' if svg_text_as_path else 'none'}
    if fmt in ('pdf', 'ps', 'eps'):
        return {'pdf.fonttype': 42, 'ps.fonttype': 42}
    return {}


def project_has_raster_gradient_fill(project):
    """グラデーションの塗り(imshow で描くのでベクター形式でもラスタになる)を使う系列があるか。"""
    return any(
        ds.plot_type == 'Area' and ds.gradient_enabled and ds.gradient_target in ('fill', 'both')
        for ds in project.datasets
    )
