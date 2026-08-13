# gui/dataset_style_icon.py
"""
データセットツリーの各項目に表示するミニプレビューアイコンを生成する。
main_window.py (アイテム新規作成時) と dataset_mixin.py (プロパティ変更後の
再描画時) の両方から使われる独立モジュール
(main_window <-> dataset_mixin の循環importを避けるため、あえて分離している)。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QIcon

from gui.icon_utils import icon as _icon_from_svg

# アイコンのサイズ (幅, 高さ)
_STYLE_ICON_SIZE = (28, 14)

# --- 項目C-907: データセットリスト(QTreeWidget)の列インデックス ---
# main_window.py (ツリーの構築・アイテム生成) と dataset_mixin.py (クリック検知・
# プロパティ変更後の再同期) の両方から参照するため、両モジュールが依存できる
# この独立モジュールに置く(main_window <-> dataset_mixin循環importを避ける理由は
# 上のモジュールdocstring参照)。列0=スタイルアイコン+名前(既存)、
# 列1=表示/非表示トグル用の目アイコン(今回追加)。
DATASET_TREE_NAME_COLUMN = 0
DATASET_TREE_VISIBILITY_COLUMN = 1

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

    # ★ 項目H-2-2(GUIモダン化): QIcon(pixmap) のように単一のPixmapだけを渡すと、
    #   ツリー項目が選択された際にQt(Fusionスタイル)が「選択時用アイコン」を
    #   自動生成しようとし、この透明背景の線プレビューに対してはハイライト色で
    #   塗り潰したような空白の四角として描画されてしまう(実機で報告・確認済み)。
    #   同じPixmapをSelectedモードにも明示的に登録することで、この自動生成を
    #   起こさせず、選択時も非選択時と同じ見た目(色付きの線/マーカー)のまま
    #   表示させる。
    icon = QIcon()
    icon.addPixmap(pixmap, QIcon.Mode.Normal)
    icon.addPixmap(pixmap, QIcon.Mode.Selected)
    return icon


# データセットの表示/非表示アイコンサイズ(項目C-907)。列0のスタイルアイコン
# (28x14、上のmake_dataset_style_icon)より小さい正方形にして、専用列の
# 固定幅(main_window.py DATASET_TREE_VISIBILITY_COLUMN_WIDTH)に収める。
_VISIBILITY_ICON_SIZE = 16


def make_dataset_visibility_icon(dataset):
    """
    dataset.visible の状態に応じた「目」アイコンを返す(項目C-907、データセット
    リストの表示/非表示トグル)。実体はTabler Icons由来のSVG
    (assets/icons/eye.svg / eye-off.svg、MITライセンス)を gui/icon_utils.icon()
    経由で読み込んだもので、手描きのアイコンパスは使わない。
    """
    name = "eye" if getattr(dataset, "visible", True) else "eye-off"
    return _icon_from_svg(name, size=_VISIBILITY_ICON_SIZE)


def apply_dataset_visibility_text_style(item, dataset, column=0):
    """
    非表示中(dataset.visible=False)のデータセットは、ツリーの名前列を
    テーマのtext_mutedトークン色にグレーアウトして、目アイコンに加えて
    一覧上でもひと目で「非表示中」と分かるようにする(項目C-907の補助的な
    視覚表現、必須ではないナイス・トゥ・ハブ)。
    表示中に戻す際は、明示的な色を指定せず ForegroundRole のデータそのものを
    クリアする(Noneを設定)ことで、QSS/パレットが決める通常の文字色に
    フォールバックさせる(固定色をここで決め打ちすると、テーマ切替時に
    追従できなくなるため)。
    """
    if getattr(dataset, "visible", True):
        item.setData(column, Qt.ItemDataRole.ForegroundRole, None)
    else:
        from gui import theme
        item.setForeground(column, QBrush(QColor(theme.current_tokens()["text_muted"])))
