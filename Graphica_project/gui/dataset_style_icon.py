# gui/dataset_style_icon.py
"""
データセットツリーの各項目に表示するミニプレビューアイコンを生成する。
main_window.py (アイテム新規作成時) と dataset_mixin.py (プロパティ変更後の
再描画時) の両方から使われる独立モジュール
(main_window <-> dataset_mixin の循環importを避けるため、あえて分離している)。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QIcon

# アイコンのサイズ (幅, 高さ)
_STYLE_ICON_SIZE = (28, 14)

# matplotlibの線種文字列 -> Qtのペンスタイルの対応表
_LINESTYLE_TO_QT_PEN = {
    '-': Qt.PenStyle.SolidLine,
    '--': Qt.PenStyle.DashLine,
    '-.': Qt.PenStyle.DashDotLine,
    ':': Qt.PenStyle.DotLine,
}


def make_dataset_style_icon(dataset):
    """
    データセットの色・線種・線幅・マーカー・透明度を反映したミニプレビュー画像を作り、
    QIconとして返す。データセットツリーの各項目のアイコンに使うことで、選択しなくても
    見た目(配色や線種)が一覧上で一目で分かるようにする。
    """
    width, height = _STYLE_ICON_SIZE
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = QColor(dataset.color)
    # 透明度が低いデータセットでも、リスト上では完全に見えなくならないよう下限を設ける
    color.setAlphaF(max(0.2, min(dataset.alpha, 1.0)))

    # ウォーターフォール(項目80/109)はplot_typeとは独立したフラグになったため、
    # ここでは特別扱いせず通常通りplot_typeだけでプレビュー内容を決める。
    show_line = dataset.plot_type in ('Line', 'Line+Scatter')
    show_marker = dataset.plot_type in ('Scatter', 'Line+Scatter')
    y = height // 2

    if show_line:
        pen = QPen(color, max(1.0, min(dataset.linewidth, 3.0)))
        pen.setStyle(_LINESTYLE_TO_QT_PEN.get(dataset.linestyle, Qt.PenStyle.SolidLine))
        painter.setPen(pen)
        painter.drawLine(2, y, width - 2, y)

    if show_marker:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        r = 3
        painter.drawEllipse(width // 2 - r, y - r, r * 2, r * 2)

    painter.end()
    return QIcon(pixmap)
