"""書き出しの経路で共有するもの。matplotlib の rcParams は、書き出しの経路すべてがこれを使うこと。"""
from contextlib import ExitStack, contextmanager

import numpy as np
from matplotlib.cbook import STEP_LOOKUP_MAP
from matplotlib.collections import LineCollection, PathCollection, PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon, Rectangle
from matplotlib.path import Path
from matplotlib.transforms import Bbox

# 枠を切り落とすのはベクター形式だけ(ラスタは枠の外を描かないので同じ)
CROPPABLE_FORMATS = ('svg', 'pdf', 'eps', 'ps')


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


def is_croppable_format(fmt):
    return (fmt or '').lower().lstrip('.') in CROPPABLE_FORMATS


@contextmanager
def outside_frame_cropped(figure, enabled=True):
    """プロット枠の外にはみ出す部分を削って書き出す(抜けたら元に戻す。画面の図にも使う)。

    ベクター形式は枠の外もデータを持ち、クリッピングマスクで隠している。PowerPoint の「図形に変換」などは
    マスクを捨てるので、枠の外の線や点が出てしまう。線は枠の縁で切り、点は枠の外のものを除き、塗りと棒は
    枠の形に切り取って、マスクも使わない。削り方が決められないもの(2D マップなど)はマスクのまま残す。
    """
    if not enabled:
        yield
        return
    figure.draw_without_rendering()
    with ExitStack() as restore:
        for ax in list(_all_axes(figure)):
            _freeze_limits(ax, restore)
            box = ax.bbox
            for artist in list(ax.get_children()):
                if not artist.get_clip_on() or not _clipped_by_frame(artist, ax):
                    continue
                cropper = _cropper_for(artist)
                if cropper is None:
                    continue
                cropper(artist, ax, box, restore)
                artist.set_clip_on(False)
                restore.callback(artist.set_clip_on, True)
        yield


def _all_axes(figure):
    """図の軸と、その中の拡大図(child_axes)。"""
    stack = list(figure.axes)
    while stack:
        ax = stack.pop()
        yield ax
        stack.extend(getattr(ax, 'child_axes', []))


def _clipped_by_frame(artist, ax):
    """枠(軸の背景)で切り抜かれているか。別の形で切り抜いているもの(グラデーションの塗りなど)は触らない。"""
    clip_path = artist.get_clip_path()
    return clip_path is None or getattr(clip_path, '_patch', None) is ax.patch


def _freeze_limits(ax, restore):
    """データを削ると自動の範囲が変わるので、今の範囲で止めておく。"""
    x_auto, y_auto = ax.get_autoscalex_on(), ax.get_autoscaley_on()
    ax.set_xlim(ax.get_xlim())
    ax.set_ylim(ax.get_ylim())
    restore.callback(ax.set_autoscaley_on, y_auto)
    restore.callback(ax.set_autoscalex_on, x_auto)


def _box(box):
    return Bbox([[box.x0, box.y0], [box.x1, box.y1]])


def _inside(points, box):
    return ((points[:, 0] >= box.x0) & (points[:, 0] <= box.x1)
            & (points[:, 1] >= box.y0) & (points[:, 1] <= box.y1))


def _clip_segment(start, end, box):
    """線分を枠で切る(Liang–Barsky)。枠の中に何も残らなければ None。"""
    x0, y0 = start
    dx, dy = end[0] - x0, end[1] - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - box.x0), (dx, box.x1 - x0), (-dy, y0 - box.y0), (dy, box.y1 - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return (np.array([x0 + t0 * dx, y0 + t0 * dy]), np.array([x0 + t1 * dx, y0 + t1 * dy]))


def _clip_polyline(points, box):
    """折れ線を枠で切った区間のリスト(画面の座標)。縁との交点まで残す。"""
    pieces, current = [], []

    def close():
        if len(current) > 1:
            pieces.append(list(current))
        current.clear()

    for start, end in zip(points[:-1], points[1:]):
        clipped = None
        if np.isfinite(start).all() and np.isfinite(end).all():
            clipped = _clip_segment(start, end, box)
        if clipped is None:
            close()
            continue
        a, b = clipped
        if not (current and np.allclose(current[-1], a)):
            close()
            current.append(a)
        current.append(b)
        if not np.allclose(b, end):
            close()
    close()
    return pieces


def _pieces_to_xy(pieces, inverse):
    """区間を NaN で区切った1本のデータ(元の座標)に戻す。"""
    rows = []
    for piece in pieces:
        if rows:
            rows.append([np.nan, np.nan])
        rows.extend(piece)
    if not rows:
        return np.empty(0), np.empty(0)
    data = np.array(rows, dtype=float)
    finite = np.isfinite(data).all(axis=1)
    data[finite] = inverse.transform(data[finite])
    return data[:, 0], data[:, 1]


def _visible_style(value):
    return value not in ('None', 'none', '', ' ', None)


def _crop_line(line, ax, box, restore):
    restore.callback(line.set_data, line.get_xdata(orig=True), line.get_ydata(orig=True))
    restore.callback(line.set_drawstyle, line.get_drawstyle())
    transform = line.get_transform()
    xy = np.asarray(line.get_xydata(), dtype=float).reshape(-1, 2)
    has_line = _visible_style(line.get_linestyle())
    marker = line.get_marker()
    inside_points = xy[_inside(transform.transform(xy), box)]
    if not has_line:
        line.set_data(inside_points[:, 0], inside_points[:, 1])
        return
    drawn = xy
    drawstyle = line.get_drawstyle()
    if drawstyle != 'default' and drawstyle in STEP_LOOKUP_MAP:
        drawn = np.asarray(STEP_LOOKUP_MAP[drawstyle](xy[:, 0], xy[:, 1]), dtype=float).T
    line.set_drawstyle('default')
    line.set_data(*_pieces_to_xy(_clip_polyline(transform.transform(drawn), box), transform.inverted()))
    if _visible_style(marker):
        # 線を縁で切ると交点が増えるので、点は枠の中のものだけを別の線で描く
        restore.callback(line.set_marker, marker)
        markers = Line2D(inside_points[:, 0], inside_points[:, 1])
        markers.update_from(line)
        line.set_marker('None')
        markers.set_linestyle('None')
        markers.set_marker(marker)
        markers.set_transform(transform)
        markers.set_clip_on(False)
        ax.add_line(markers)
        restore.callback(markers.remove)


def _crop_scatter(collection, ax, box, restore):
    offsets = np.asarray(collection.get_offsets(), dtype=float).reshape(-1, 2)
    count = len(offsets)
    if not count:
        return
    keep = _inside(collection.get_offset_transform().transform(offsets), box)
    if keep.all():
        return
    restore.callback(collection.set_offsets, offsets)
    collection.set_offsets(offsets[keep])
    array = collection.get_array()
    if array is not None and np.size(array) == count:
        restore.callback(collection.set_array, array)
        collection.set_array(np.asarray(array)[keep])
    else:
        for getter, setter in ((collection.get_facecolor, collection.set_facecolor),
                               (collection.get_edgecolor, collection.set_edgecolor)):
            colors = getter()
            if len(colors) == count:
                restore.callback(setter, colors)
                setter(colors[keep])
    sizes = collection.get_sizes()
    if len(sizes) == count:
        restore.callback(collection.set_sizes, sizes)
        collection.set_sizes(sizes[keep])


def _crop_polygons(collection, ax, box, restore):
    transform = collection.get_transform()
    inverse = transform.inverted()
    paths = list(collection.get_paths())
    cropped = []
    for path in paths:
        clipped = transform.transform_path(path).clip_to_bbox(_box(box))
        # 消えた多角形も空のまま残す(色の並びと数を合わせる)
        cropped.append(inverse.transform_path(clipped) if len(clipped.vertices) else Path(np.empty((0, 2))))
    # PolyCollection は Path ではなく頂点と命令の並びで受け取る
    restore.callback(_set_polygon_paths, collection, paths)
    _set_polygon_paths(collection, cropped)


def _set_polygon_paths(collection, paths):
    verts = [path.vertices for path in paths]
    codes = [path.codes if path.codes is not None else _polyline_codes(len(path.vertices)) for path in paths]
    collection.set_verts_and_codes(verts, codes)


def _polyline_codes(count):
    codes = np.full(count, Path.LINETO, dtype=Path.code_type)
    if count:
        codes[0] = Path.MOVETO
    return codes


def _crop_segments(collection, ax, box, restore):
    transform = collection.get_transform()
    inverse = transform.inverted()
    segments = collection.get_segments()
    count = len(segments)
    new_segments, source = [], []
    for index, segment in enumerate(segments):
        for piece in _clip_polyline(transform.transform(np.asarray(segment, dtype=float).reshape(-1, 2)), box):
            new_segments.append(inverse.transform(np.array(piece)))
            source.append(index)
    source = np.array(source, dtype=int)
    array = collection.get_array()
    colors = collection.get_color()
    widths = collection.get_linewidth()
    restore.callback(collection.set_segments, segments)
    collection.set_segments(new_segments)
    # 区間ごとの色(グラデーションの線など)は、切って増えた区間にも元の区間の色を付ける
    if array is not None and np.size(array) == count:
        restore.callback(collection.set_array, array)
        collection.set_array(np.asarray(array)[source])
    elif len(colors) == count:
        restore.callback(collection.set_color, colors)
        collection.set_color(colors[source])
    if len(widths) == count:
        restore.callback(collection.set_linewidth, widths)
        collection.set_linewidth(np.asarray(widths)[source])


def _crop_rectangle(rect, ax, box, restore):
    transform = rect.get_transform()
    corners = transform.transform(rect.get_path().vertices[:4])
    x0, x1 = max(corners[:, 0].min(), box.x0), min(corners[:, 0].max(), box.x1)
    y0, y1 = max(corners[:, 1].min(), box.y0), min(corners[:, 1].max(), box.y1)
    xy, width, height, visible = rect.get_xy(), rect.get_width(), rect.get_height(), rect.get_visible()

    def put_back():
        rect.set_xy(xy)
        rect.set_width(width)
        rect.set_height(height)
        rect.set_visible(visible)
    restore.callback(put_back)
    if x0 >= x1 or y0 >= y1:
        rect.set_visible(False)
        return
    # 棒は (左下, 幅, 高さ) をデータの座標で持つ。軸が反転していても、枠の中の長方形は同じ
    (dx0, dy0), (dx1, dy1) = rect.get_data_transform().inverted().transform([[x0, y0], [x1, y1]])
    rect.set_xy((min(dx0, dx1), min(dy0, dy1)))
    rect.set_width(abs(dx1 - dx0))
    rect.set_height(abs(dy1 - dy0))


def _crop_polygon_patch(polygon, ax, box, restore):
    clipped = polygon.get_transform().transform_path(polygon.get_path()).clip_to_bbox(_box(box))
    xy, visible = polygon.get_xy(), polygon.get_visible()

    def put_back():
        polygon.set_xy(xy)
        polygon.set_visible(visible)
    restore.callback(put_back)
    if len(clipped.vertices) < 3:
        polygon.set_visible(False)
        return
    polygon.set_xy(polygon.get_data_transform().inverted().transform(clipped.vertices))


# 種類ごとの削り方。いちばん近い種類のものを使う(LineCollection は PolyCollection より前)
_CROPPERS = (
    (Line2D, _crop_line),
    (PathCollection, _crop_scatter),
    (LineCollection, _crop_segments),
    (PolyCollection, _crop_polygons),
    (Rectangle, _crop_rectangle),
    (Polygon, _crop_polygon_patch),
)


def _cropper_for(artist):
    return next((crop for kind, crop in _CROPPERS if isinstance(artist, kind)), None)


def project_has_raster_gradient_fill(project):
    """グラデーションの塗り(imshow で描くのでベクター形式でもラスタになる)を使う系列があるか。"""
    return any(
        ds.plot_type == 'Area' and ds.gradient_enabled and ds.gradient_target in ('fill', 'both')
        for ds in project.datasets
    )
