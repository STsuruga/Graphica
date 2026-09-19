"""データセット一覧の各項目のアイコン(見た目の小さなプレビューと、表示/非表示の目)。

main_window と dataset_mixin の両方が使うので、循環 import を避けて別のモジュールにしている。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QIcon

from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE, linestyle_name
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
    show_marker = dataset.plot_type in (
        'Scatter', 'Line+Scatter', 'Density Scatter', COLOR_BY_COLUMN_PLOT_TYPE)
    y = height // 2

    if show_line:
        pen = QPen(color, max(1.0, min(dataset.linewidth, 3.0)))
        pen.setStyle(_LINESTYLE_TO_QT_PEN.get(linestyle_name(dataset.linestyle), Qt.PenStyle.SolidLine))
        painter.setPen(pen)
        painter.drawLine(2, y, width - 2, y)

    if show_marker:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        r = 3
        painter.drawEllipse(width // 2 - r, y - r, r * 2, r * 2)

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
