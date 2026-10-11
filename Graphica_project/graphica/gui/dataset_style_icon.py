"""データセット一覧の各項目のアイコン(見た目の小さなプレビューと、表示/非表示の目)。

main_window と dataset_mixin の両方が使うので、循環 import を避けて別のモジュールにしている。
"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QPen, QColor, QBrush, QIcon

from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE, linestyle_name
from graphica.core.marker_style import MARKER_EDGE_COLOR, MARKER_FILL_COLOR, MARKER_FILL_HOLLOW, marker_is_unfilled
from graphica.gui.icon_utils import icon as _icon_from_svg

_STYLE_ICON_SIZE = (28, 14)

# 列0はアイコンと名前、列1は表示/非表示の目
DATASET_TREE_NAME_COLUMN = 0
DATASET_TREE_VISIBILITY_COLUMN = 1

# 線種の表示名(linestyle_name で揃えたもの)から Qt のペン。記号('--')だけ見ると 'dashed' が実線になる
_LINESTYLE_TO_QT_PEN = {
    'solid': Qt.PenStyle.SolidLine,
    'dashed': Qt.PenStyle.DashLine,
    'dashdot': Qt.PenStyle.DashDotLine,
    'dotted': Qt.PenStyle.DotLine,
}


# マーカーを描く種類
MARKER_PLOT_TYPES = ('Scatter', 'Line+Scatter', 'Density Scatter', COLOR_BY_COLUMN_PLOT_TYPE)


def marker_painter_path(marker, size):
    """matplotlib のマーカーの形を、原点を中心にした幅 size px ほどの QPainterPath にする。描かない値は None。"""
    from matplotlib.markers import MarkerStyle
    from matplotlib.path import Path as MplPath

    try:
        style = MarkerStyle(marker)
    except ValueError:
        return None
    path = style.get_path().transformed(style.get_transform())
    if len(path.vertices) == 0:
        return None
    # matplotlib の形はおよそ幅 1 の Y 上向き。画面は Y 下向きなので反転する
    def point(x, y):
        return QPointF(x * size, -y * size)

    painter_path = QPainterPath()
    for vertices, code in path.iter_segments(simplify=False, curves=True):
        if code == MplPath.MOVETO:
            painter_path.moveTo(point(*vertices))
        elif code == MplPath.LINETO:
            painter_path.lineTo(point(*vertices))
        elif code == MplPath.CURVE3:
            painter_path.quadTo(point(*vertices[:2]), point(*vertices[2:]))
        elif code == MplPath.CURVE4:
            painter_path.cubicTo(point(*vertices[:2]), point(*vertices[2:4]), point(*vertices[4:]))
        elif code == MplPath.CLOSEPOLY:
            painter_path.closeSubpath()
    return painter_path


def _draw_marker(painter, marker, center, size, brush, pen):
    path = marker_painter_path(marker, size)
    if path is None:
        return
    painter.save()
    painter.translate(center)
    painter.setPen(pen)
    painter.setBrush(brush)
    painter.drawPath(path)
    painter.restore()


_MARKER_CHOICE_ICON_SIZE = 16
# 明暗どちらのテーマの選択肢の背景でも見える中間の灰色
_MARKER_CHOICE_ICON_COLOR = '#808080'


def marker_choice_icon(marker):
    """マーカーの形の選択肢に付ける形の絵。描かない値('None')は None。"""
    if marker_painter_path(marker, 1) is None:
        return None
    side = _MARKER_CHOICE_ICON_SIZE
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(_MARKER_CHOICE_ICON_COLOR)
    brush = Qt.BrushStyle.NoBrush if marker_is_unfilled(marker) else QBrush(color)
    _draw_marker(painter, marker, QPointF(side / 2, side / 2), side * 0.7, brush, QPen(color, 1.2))
    painter.end()
    return QIcon(pixmap)


def _marker_brush_and_pen(dataset, color):
    """一覧のアイコン用。塗りと枠線の指定を映す(値で色分けする種類も系列の色で代わりに描く)。"""
    edge = QColor(dataset.marker_edge_color) if dataset.marker_edge == MARKER_EDGE_COLOR else QColor(color)
    edge.setAlphaF(color.alphaF())
    pen = QPen(edge, max(0.0, min(dataset.marker_edge_width, 2.0)))
    if dataset.marker_edge_width <= 0:
        pen = QPen(Qt.PenStyle.NoPen)
    if marker_is_unfilled(dataset.marker):
        return Qt.BrushStyle.NoBrush, QPen(edge, 1.2)
    if dataset.marker_fill == MARKER_FILL_HOLLOW:
        return Qt.BrushStyle.NoBrush, pen
    if dataset.marker_fill == MARKER_FILL_COLOR:
        face = QColor(dataset.marker_face_color)
        face.setAlphaF(color.alphaF())
        return QBrush(face), pen
    return QBrush(color), pen


def make_dataset_style_icon(dataset):
    """色・線種・線幅・マーカー・透明度を映した小さな画像。選ばなくても一覧で見分けられるように。"""
    width, height = _STYLE_ICON_SIZE
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = QColor(dataset.color)
    # 透明度が低くても一覧では見えるよう下限を設ける
    color.setAlphaF(max(0.2, min(dataset.alpha, 1.0)))

    show_line = dataset.plot_type in ('Line', 'Line+Scatter', 'Step')
    show_marker = dataset.plot_type in MARKER_PLOT_TYPES
    y = height // 2

    if show_line:
        pen = QPen(color, max(1.0, min(dataset.linewidth, 3.0)))
        pen.setStyle(_LINESTYLE_TO_QT_PEN.get(linestyle_name(dataset.linestyle), Qt.PenStyle.SolidLine))
        painter.setPen(pen)
        painter.drawLine(2, y, width - 2, y)

    if show_marker:
        brush, pen = _marker_brush_and_pen(dataset, color)
        _draw_marker(painter, dataset.marker, QPointF(width / 2, y), 8, brush, pen)

    painter.end()

    # Selected モードにも同じ画像を入れる(入れないと Fusion が選択時の画像を作り、塗りつぶした四角になる)
    icon = QIcon()
    icon.addPixmap(pixmap, QIcon.Mode.Normal)
    icon.addPixmap(pixmap, QIcon.Mode.Selected)
    return icon


# 目の列の固定幅(DATASET_TREE_VISIBILITY_COLUMN_WIDTH)に収まる大きさ
_VISIBILITY_ICON_SIZE = 16


def make_dataset_visibility_icon(dataset):
    name = "eye" if getattr(dataset, "visible", True) else "eye-off"
    return _icon_from_svg(name, size=_VISIBILITY_ICON_SIZE)


def apply_dataset_visibility_text_style(item, dataset, column=0):
    """隠した系列の名前を text_muted の色にする。表示に戻すときは色を消してテーマの文字色に任せる。"""
    if getattr(dataset, "visible", True):
        item.setData(column, Qt.ItemDataRole.ForegroundRole, None)
    else:
        from graphica.gui import theme
        item.setForeground(column, QBrush(QColor(theme.current_tokens()["text_muted"])))
