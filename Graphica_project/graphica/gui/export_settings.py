"""書き出しの経路で共有するもの。matplotlib の rcParams は、書き出しの経路すべてがこれを使うこと。"""
from contextlib import contextmanager

import numpy as np
from matplotlib.collections import Collection, QuadMesh
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.spines import Spine

# 枠ぴったりの点(自動スケールは余白なし)を「はみ出し」と数えないための許し(ピクセル)
CLIP_TOLERANCE_PX = 0.5


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


def is_svg(fmt):
    return (fmt or '').lower().lstrip('.') == 'svg'


@contextmanager
def plot_clip_masks_removed(figure, enabled=True):
    """プロット枠の中に収まる系列のクリッピングを外して書き出す(SVG のクリッピングマスクが出ない)。

    枠の外にはみ出すデータを持つ系列(拡大した表示・拡大図の中身など)は、外すと枠の外に描かれてしまうので残す。
    抜けたあとは元に戻す(画面の図にも使う)。
    """
    if not enabled:
        yield
        return
    figure.draw_without_rendering()
    unclipped = []
    try:
        for ax in _all_axes(figure):
            box = ax.bbox
            for artist in ax.get_children():
                if not artist.get_clip_on() or artist is ax.patch or isinstance(artist, Spine):
                    continue
                # 枠とは別の形で切り抜いているもの(グラデーションの塗りなど)は、外すとその形も失う。
                # 軸に足した部品には matplotlib が軸の背景(=枠)を切り抜きの形として付けるので、それだけを外してよい
                clip_path = artist.get_clip_path()
                if clip_path is not None and getattr(clip_path, '_patch', None) is not ax.patch:
                    continue
                points = _drawn_points(artist, ax)
                if points is None:
                    continue
                points = points[np.isfinite(points).all(axis=1)]
                inside = ((points[:, 0] >= box.x0 - CLIP_TOLERANCE_PX) & (points[:, 0] <= box.x1 + CLIP_TOLERANCE_PX)
                          & (points[:, 1] >= box.y0 - CLIP_TOLERANCE_PX) & (points[:, 1] <= box.y1 + CLIP_TOLERANCE_PX))
                if inside.all():
                    artist.set_clip_on(False)
                    unclipped.append(artist)
        yield
    finally:
        for artist in unclipped:
            artist.set_clip_on(True)


def _all_axes(figure):
    """図の軸と、その中の拡大図(child_axes)。"""
    stack = list(figure.axes)
    while stack:
        ax = stack.pop()
        yield ax
        stack.extend(getattr(ax, 'child_axes', []))


def _drawn_points(artist, ax):
    """描く位置(画面の座標、N×2)。どこに描くか決められない種類は None(クリッピングを残す)。"""
    if isinstance(artist, Line2D):
        return artist.get_transform().transform(np.asarray(artist.get_xydata(), dtype=float).reshape(-1, 2))
    if isinstance(artist, QuadMesh):
        return artist.get_transform().transform(np.asarray(artist.get_coordinates(), dtype=float).reshape(-1, 2))
    if isinstance(artist, Collection):
        offsets = np.asarray(artist.get_offsets(), dtype=float).reshape(-1, 2)
        if len(offsets) and offsets.any():
            # 散布図: 点の位置。マーカーの形は点の大きさなので枠を越えても少しだけ
            return artist.get_offset_transform().transform(offsets)
        paths = artist.get_paths()
        if not paths:
            return np.empty((0, 2))
        transform = artist.get_transform()
        return np.vstack([transform.transform(path.vertices) for path in paths])
    if isinstance(artist, Patch):
        return artist.get_transform().transform(artist.get_path().vertices)
    if isinstance(artist, AxesImage):
        x0, x1, y0, y1 = artist.get_extent()
        return ax.transData.transform([[x0, y0], [x1, y1]])
    return None


def project_has_raster_gradient_fill(project):
    """グラデーションの塗り(imshow で描くのでベクター形式でもラスタになる)を使う系列があるか。"""
    return any(
        ds.plot_type == 'Area' and ds.gradient_enabled and ds.gradient_target in ('fill', 'both')
        for ds in project.datasets
    )
