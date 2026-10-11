"""マーカーの塗りと枠線(Dataset の marker_fill など)を matplotlib の引数にする。描画と Python スクリプトの書き出しが共有する。

既定の値では空の辞書を返し、今までと同じ呼び出しのまま描く(保存済みのプロジェクトの見た目を変えない)。
"""
from typing import Any

MARKER_FILL_SOLID = 'solid'
MARKER_FILL_HOLLOW = 'hollow'
MARKER_FILL_COLOR = 'color'

# 'same' は系列の色(値で色分けする種類では塗りと同じ色)
MARKER_EDGE_SAME = 'same'
MARKER_EDGE_COLOR = 'color'

# matplotlib の既定(lines.markeredgewidth。scatter の枠線も同じ 1.0)
DEFAULT_MARKER_EDGE_WIDTH = 1.0

# 線だけでできた形。塗りが無く、scatter は枠線の色を無視して塗りの色で線を引く(白抜きにすると消える)
UNFILLED_MARKERS = frozenset({'+', 'x', '1', '2', '3', '4', '|', '_'})


def marker_is_unfilled(marker: Any) -> bool:
    return marker in UNFILLED_MARKERS


def scatter_marker_kwargs(ds: Any) -> dict[str, Any]:
    """単色の ax.scatter(color=ds.color, ...) の上に重ねる引数。"""
    kwargs: dict[str, Any] = {}
    edge_color = ds.marker_edge_color if ds.marker_edge == MARKER_EDGE_COLOR else None
    if marker_is_unfilled(ds.marker):
        if edge_color is not None:
            kwargs['color'] = edge_color
    else:
        if ds.marker_fill == MARKER_FILL_HOLLOW:
            kwargs['facecolors'] = 'none'
            kwargs['edgecolors'] = ds.color
        elif ds.marker_fill == MARKER_FILL_COLOR:
            kwargs['facecolors'] = ds.marker_face_color
            kwargs['edgecolors'] = ds.color
        if edge_color is not None:
            kwargs['edgecolors'] = edge_color
    if ds.marker_edge_width != DEFAULT_MARKER_EDGE_WIDTH:
        kwargs['linewidths'] = ds.marker_edge_width
    return kwargs


def mapped_scatter_marker_kwargs(ds: Any) -> tuple[dict[str, Any], bool]:
    """値で色分けする ax.scatter(c=..., ...) の引数と、描いたあとに白抜きにするか。

    塗りは色の対応が受け持つので「色を指定」は使わない。c と facecolors を一緒に渡すと c が勝つため、
    白抜きは描いたあとに apply_mapped_hollow で塗りを消す。
    """
    kwargs: dict[str, Any] = {}
    unfilled = marker_is_unfilled(ds.marker)
    if ds.marker_edge == MARKER_EDGE_COLOR and not unfilled:
        kwargs['edgecolors'] = ds.marker_edge_color
    if ds.marker_edge_width != DEFAULT_MARKER_EDGE_WIDTH:
        kwargs['linewidths'] = ds.marker_edge_width
    return kwargs, ds.marker_fill == MARKER_FILL_HOLLOW and not unfilled


def apply_mapped_hollow(artist: Any, ds: Any) -> None:
    """塗りを消す。枠線が系列の色なら、色の対応を枠線へ移す(元の枠線の色が None だと対応が枠線に付く)。"""
    artist.set_facecolor('none')
    if ds.marker_edge != MARKER_EDGE_COLOR:
        artist.set_edgecolor(None)


def line_marker_kwargs(ds: Any) -> dict[str, Any]:
    """マーカー付きの ax.plot(...) の引数。Line2D は線だけの形も枠線の色で引くので、形で分けなくてよい。"""
    kwargs: dict[str, Any] = {}
    if ds.marker_fill == MARKER_FILL_HOLLOW:
        kwargs['markerfacecolor'] = 'none'
    elif ds.marker_fill == MARKER_FILL_COLOR:
        kwargs['markerfacecolor'] = ds.marker_face_color
    if ds.marker_edge == MARKER_EDGE_COLOR:
        kwargs['markeredgecolor'] = ds.marker_edge_color
    if ds.marker_edge_width != DEFAULT_MARKER_EDGE_WIDTH:
        kwargs['markeredgewidth'] = ds.marker_edge_width
    return kwargs
