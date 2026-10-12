"""画面の組み立てで共有する定数と小さな部品。main_window からも同じ名前で読める。"""
import os
from PySide6.QtCore import QEvent, QObject, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionViewItem, QStyledItemDelegate
from graphica.core.i18n import tr
from graphica.gui import theme
from graphica.gui.dataset_style_icon import DATASET_TREE_NAME_COLUMN
from graphica.gui.icon_utils import ICONS_DIR, load_svg_icon
from graphica.gui.mathtext_preview import FitWidthPixmapLabel
from graphica.gui.resources import resource_path


# 列番号は dataset_mixin も使うので gui/dataset_style_icon.py にある(循環 import を避けるため)
DATASET_TREE_VISIBILITY_COLUMN_WIDTH = 26  # 目のアイコン(16px)+クリックの余白


# ドックの既定の配置を変えたら上げる。保存時の値と違えば保存済みの配置を戻さない
# (戻すと、新しい既定の配置が既存の利用者に届かない)。
DOCK_LAYOUT_VERSION = 6


# データセットのプロパティ欄の節。行は self._prop_form(キー).addRow で足す(番号指定の挿入はしない)。
DATASET_PROPERTY_SECTIONS = (
    ('data',      'データ列'),
    ('style',     '基本スタイル'),
    ('marker',    'マーカー'),
    ('gradient',  'グラデーション'),
    ('waterfall', 'ウォーターフォール'),
    ('map',       '2Dマップ・値による配色'),
    ('extra',     '表示の追加要素'),
    ('place',     '配置・情報'),
)


# プラグインの種類名は任意の長さなので、コンボの希望幅を固定して省略表示させる
# (広がると QFormLayout の列幅を通じてドックに横スクロールバーが出る)。
PLOT_TYPE_COMBO_MIN_CHARS = 11


def cap_combo_width(combo):
    """長い項目があっても、コンボの希望幅を種別の欄と同じ文字数にそろえる(項目は開いた一覧で全文が見える)。"""
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(PLOT_TYPE_COMBO_MIN_CHARS)


COLORMAP_CHOICES = [
    'viridis', 'plasma', 'inferno', 'magma', 'cividis',
    'coolwarm', 'RdBu', 'seismic', 'jet', 'turbo',
    'gray', 'Blues', 'Greens', 'Reds', 'YlOrRd',
]


# Qt 既定の 24px だと、狭いウィンドウでボタンが「>>」に押し込まれて押せない
TOOLBAR_ICON_SIZE = 18


def _svg_icon(name, size=20):
    """テーマの text_secondary 色で描いたアイコン。テーマが変わっても自動では変わらない

    (常に見えているものは _refresh_custom_svg_icons で作り直す)。
    """
    from graphica.gui import theme
    color = theme.current_tokens()["text_secondary"]
    return load_svg_icon(resource_path(os.path.join(ICONS_DIR, f"{name}.svg")),
                          color=color, size=size)


class _DatasetTreeSelectionDelegate(QStyledItemDelegate):
    """選択の背景を、アイコンの列と文字の列にまたがる1つの角丸で描く。

    QSS の ::item:selected は2つの列に別々の角丸を描き、間に隙間ができる。背景だけ自前で塗り、
    State_Selected を外してから標準の描画に任せる。
    """

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        if opt.state & QStyle.StateFlag.State_Selected:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # 展開矢印の字下げの分だけ左が空くので、左端まで塗る(字下げの列には何も描かれない)
            rect = QRectF(opt.rect)
            rect.setLeft(0)
            path = QPainterPath()
            path.addRoundedRect(
                rect, theme.DATASET_LIST_ITEM_RADIUS, theme.DATASET_LIST_ITEM_RADIUS
            )
            painter.fillPath(path, theme.current_accent_soft_qcolor())
            painter.restore()
            # 標準の選択の背景を重ねないよう落とす(文字とアイコンの色は選択で変わらない)
            opt.state &= ~QStyle.StateFlag.State_Selected

        count_text = _point_count_text(index)
        if not count_text:
            super().paint(painter, opt, index)
            return
        # 右端に点の数を出す。名前はその手前で省略されるよう、文字の幅を縮めてから描く
        full_rect = QRect(opt.rect)
        count_width = opt.fontMetrics.horizontalAdvance(count_text) + DATASET_TREE_COUNT_PADDING
        opt.rect = full_rect.adjusted(0, 0, -count_width, 0)
        super().paint(painter, opt, index)
        painter.save()
        painter.setPen(QColor(theme.current_tokens()["text_muted"]))
        painter.drawText(full_rect.adjusted(0, 0, -DATASET_TREE_COUNT_PADDING // 2, 0),
                         int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), count_text)
        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(max(hint.height(), DATASET_TREE_ROW_HEIGHT))
        return hint


# 一覧の行の高さと、右端の点の数の余白(見本 docs/dev/mockups/gui_redesign/ の 38px から行の間の分を引いた高さ)
DATASET_TREE_ROW_HEIGHT = 34
DATASET_TREE_COUNT_PADDING = 12


def _point_count_text(index):
    """データセットの行なら「41 点」(除外した行は数えない)。フォルダや目の列は空。"""
    if index.column() != DATASET_TREE_NAME_COLUMN:
        return ""
    dataset = index.data(Qt.ItemDataRole.UserRole)
    if dataset is None:
        return ""
    try:
        count = len(dataset.df) - len(getattr(dataset, "masked_row_indices", ()) or ())
    except TypeError:
        return ""
    return f"{max(count, 0)} {tr('点')}"


class _IgnoreWheelFilter(QObject):
    def eventFilter(self, watched, event):
        return event.type() == QEvent.Type.Wheel


def disable_wheel_tab_switching(tab_widget):
    """ホイールでタブが切り替わらないようにする。

    タブバーは QTabWidget が C++ 側で作るので、wheelEvent をクラスごと書き換えても効かない。
    """
    tab_bar = tab_widget.tabBar()
    tab_bar.installEventFilter(_IgnoreWheelFilter(tab_bar))


class _ClickableMathPreviewLabel(FitWidthPixmapLabel):
    """タイトルと軸ラベルの欄。mathtext を描いたプレビューで、クリックで編集ダイアログを開く。

    値は隠した元の QLineEdit が持つ(textChanged もそちらから出る)。
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mathtext_preview_label")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setToolTip(tr("クリックして編集"))
        # QLabel は既定でホバーを追跡せず、QSS の :hover が効かない
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _insert_form_row_after(form, anchor, *row):
    """form の anchor(ラベルか欄)の行の次に入れる。行番号で入れると、ほかの挿入の順番が変わったときに黙って別の位置に入る。"""
    anchor_row, _ = form.getWidgetPosition(anchor)
    if anchor_row < 0:
        raise ValueError(f"{anchor!r} は {form.objectName()} にありません")
    form.insertRow(anchor_row + 1, *row)
