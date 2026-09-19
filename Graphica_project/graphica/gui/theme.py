"""アプリ全体のテーマ。Fusion スタイルの上でパレットを切り替え、QSS でフラットな見た目にする。"""
import os
import re
import tempfile

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox,
                               QProxyStyle, QStyle, QStyleFactory)

from graphica.gui.icon_utils import icon as _svg_icon

_original_palette = None
_original_style_name = None
_wheel_value_change_disabled = False
_current_proxy_style = None
_current_tokens = None
_last_applied_dark = None  # 同じ値での apply_theme() は重い処理を省く

# 選択の角丸を描くデリゲートが使う。QSS の QTreeWidget の border-radius と同じ値にしておくこと
DATASET_LIST_ITEM_RADIUS = 8

# スピンボックスの矢印は PNG にして QSS の ::up-arrow / ::down-arrow の image で指定する。
# 枠を QSS で描いていると、QProxyStyle で矢印を描いても反映されたりされなかったりする。
_ARROW_ICON_CACHE_DIR = os.path.join(tempfile.gettempdir(), "graphica_theme_icons")


def _spinbox_arrow_icon_url(direction: str, color: str) -> str:
    """三角の矢印の PNG を(無ければ)作り、QSS の url() に入れられるパスを返す。"""
    os.makedirs(_ARROW_ICON_CACHE_DIR, exist_ok=True)
    safe_color = color.lstrip("#")
    # 大きさをファイル名に入れ、寸法を変えたとき古い PNG を使い回さない
    size = 14
    filename = f"spin_arrow_{direction}_{safe_color}_{size}.png"
    path = os.path.join(_ARROW_ICON_CACHE_DIR, filename)

    if not os.path.exists(path):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))

        cx, cy = size / 2, size / 2
        aw, ah = 4.4, 3.3
        arrow_path = QPainterPath()
        if direction == "up":
            arrow_path.moveTo(cx - aw, cy + ah * 0.5)
            arrow_path.lineTo(cx + aw, cy + ah * 0.5)
            arrow_path.lineTo(cx, cy - ah * 0.5)
        else:
            arrow_path.moveTo(cx - aw, cy - ah * 0.5)
            arrow_path.lineTo(cx + aw, cy - ah * 0.5)
            arrow_path.lineTo(cx, cy + ah * 0.5)
        arrow_path.closeSubpath()
        painter.drawPath(arrow_path)
        painter.end()
        pixmap.save(path)

    # QSS の url() は Windows の区切りの \ を読めない
    return path.replace(os.sep, "/")

# 配色の唯一の定義。これを上書きする利用者の設定は無い(配色パレットはデータの線の色で、UI とは別)。
LIGHT_TOKENS = {
    "bg": "#F6F7F9", "surface": "#FFFFFF", "surface_2": "#EEF0F3",
    "border": "#DFE2E1", "border_strong": "#C9CDCB",
    "text_primary": "#1B1F1E", "text_secondary": "#5B6462", "text_muted": "#8B938F",
    "accent": "#1F6F78", "accent_soft": "#E4F0EF", "accent_text": "#FFFFFF",
    # データセット一覧の選択だけに使う半透明の青(アクセントのティールとは別)
    "selection_highlight": "rgba(37, 99, 235, 0.12)",
    # selection_highlight と同じ色の不透明版(枠やチェックボックスの塗りには透明だと困る)
    "selection_accent": "#2563EB",
    # 欠損値のセル。選択の青とも、アクセントとも被らない
    "warning_soft": "#FDF1D8",
}
DARK_TOKENS = {
    "bg": "#14171A", "surface": "#1B1F22", "surface_2": "#21262A",
    "border": "#2C3236", "border_strong": "#3A4147",
    "text_primary": "#EDEFEF", "text_secondary": "#A6AEB2", "text_muted": "#6E777B",
    "accent": "#5FB6BE", "accent_soft": "rgba(95, 182, 190, 0.16)", "accent_text": "#0E1113",
    "selection_highlight": "rgba(59, 130, 246, 0.22)",
    "selection_accent": "#3B82F6",
    "warning_soft": "rgba(250, 204, 21, 0.16)",
}

_FLAT_QSS_TEMPLATE = """
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {text_primary};
    /* 操作の強調(選択・ホバー・押下・フォーカス)は青の selection_highlight / selection_accent にそろえる。
       ティールの accent は操作の強調ではないもの(QProgressBar::chunk など)だけ。 */
    selection-background-color: {selection_highlight};
    selection-color: {text_primary};
}}
QToolTip {{
    background: {surface};
    color: {text_primary};
    border: 1px solid {border_strong};
    padding: 4px 6px;
    border-radius: 4px;
}}

/* --- メニューバー / メニュー --- */
QMenuBar {{
    background: {surface};
    border-bottom: 1px solid {border};
    padding: 2px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {selection_highlight};
    color: {text_primary};
}}
QMenu {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {selection_highlight};
    color: {text_primary};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 8px;
}}

/* --- 操作ボタン行のグループ区切り --- */
QFrame#button_row_separator {{
    background: {border};
    max-width: 1px;
    border: none;
    margin: 2px 4px;
}}

/* --- データセット一覧の下の短い統計値 --- */
QLabel#dataset_mini_stats_label {{
    color: {text_muted};
    font-size: 11.5px;
    padding: 2px 4px;
}}

/* --- キャンバスの周り: 角丸の背景のカード。枠線は付けない --- */
QWidget#plot_container {{
    background: {surface};
    border-radius: 8px;
}}
QFrame#canvas_separator {{
    background: {border};
    max-height: 1px;
    border: none;
}}

/* --- ツールバー / ステータスバー / ドック --- */
QToolBar {{
    background: {surface};
    border: none;
    border-bottom: 1px solid {border};
    spacing: 4px;
    padding: 4px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
}}
QToolButton:hover {{
    background: {surface_2};
}}
/* ツールバーのボタンは QToolButton なので、QPushButton とは別にホバーと押下を青にする。 */
QToolButton:pressed {{
    background: {selection_highlight};
}}
QToolButton:checked {{
    background: {selection_highlight};
    border: 1px solid {selection_accent};
}}
QStatusBar {{
    background: {surface};
    border-top: 1px solid {border};
}}
/* QScrollArea は既定の枠を消す。背景は QScrollArea・ビューポート・中身のウィジェットの3段すべてに指定する
   (アプリ全体に QSS を当てると素の QWidget もパレットの色で塗られ、ビューポートだけでは中身に覆われて効かない)。 */
QScrollArea {{
    border: none;
    background: {bg};
}}
QScrollArea > QWidget {{
    background: {bg};
}}
QScrollArea > QWidget > QWidget {{
    background: {bg};
}}
/* --- ドック: 枠と角丸で1枚のカードに見せる(積んだドックの間はスプリッターの隙間があるので二重線にならない) --- */
QDockWidget {{
    /* 指定しないと OS のパレットの色が透け、背景のトークンが効かない */
    background: {bg};
    border: 1px solid {border};
    border-radius: 8px;
}}
QDockWidget::title {{
    background: {surface_2};
    padding: 6px 8px;
    border-bottom: 1px solid {border};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    letter-spacing: .01em;
}}
/* フォーカスのあるドックの枠。dockActive は install_dock_focus_highlight() が付け外しする。 */
QDockWidget[dockActive="true"] {{
    border: 1px solid {selection_accent};
}}
QDockWidget[dockActive="true"]::title {{
    border-bottom: 1px solid {selection_accent};
}}

/* --- スプリッター: 細く控えめにし、ホバーでだけ色を付ける --- */
QSplitter::handle {{
    background: {border};
}}
QSplitter::handle:horizontal {{
    width: 3px;
    margin: 2px 0;
}}
QSplitter::handle:vertical {{
    height: 3px;
    margin: 0 2px;
}}
QSplitter::handle:hover {{
    background: {selection_accent};
}}

/* --- グループボックス / ボタン --- */
QGroupBox {{
    background: transparent;
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 20px;
    padding-top: 14px;
    font-weight: 500;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    /* 枠の外にはみ出さない位置にする。はみ出すと、QFontDialog などの Qt 標準のダイアログでは上の余白が無く見切れる。 */
    top: 0px;
    padding: 2px 8px;
    color: {selection_accent};
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: .02em;
    background: {selection_highlight};
    border-radius: 5px;
}}

/* --- ドックの中のグループボックスは枠とチップを付けない(カードの中に箱が入れ子になって窮屈に見える) --- */
QDockWidget QGroupBox {{
    border: none;
    border-radius: 0;
    margin-top: 18px;
    padding-top: 6px;
}}
/* 折りたたみの中身のグループボックス(collapsibleBody)はタイトルを外のボタンに移したので、
   タイトル用の上の余白(margin-top と padding-top で 24px)を 0 にする。 */
QDockWidget QGroupBox[collapsibleBody="true"] {{
    margin-top: 0px;
    padding-top: 0px;
}}
QDockWidget QGroupBox::title {{
    left: 0;
    /* 上のモーダル側と同じく、枠の外にはみ出さない位置にする */
    top: 0px;
    padding: 0;
    color: {text_secondary};
    background: transparent;
    border-radius: 0;
}}

/* --- 開閉できる見出し(データセットのプロパティ / プロットのプロパティ): 横いっぱい・左寄せ・太字 --- */
QToolButton#collapsible_section_toggle {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 4px;
    text-align: left;
    font-weight: 600;
    /* フォームのラベルは既定の 9pt(約 12px)で描かれるので、見出しはそれより大きくする(見出し > 節の見出し > 項目) */
    font-size: {heading_pt}pt;
    color: {text_secondary};
}}
QToolButton#collapsible_section_toggle:hover {{
    background: {surface_2};
    color: {text_primary};
}}
QToolButton#collapsible_section_toggle:pressed {{
    background: {selection_highlight};
}}

/* --- プロパティ欄の節の見出し: 本文より少し大きく・太く・濃くし、中身を字下げする。
   区切りは細い罫線1本。1本目は親の見出しのすぐ下で二重線に見えるので引かない。 --- */
QToolButton#property_subsection_toggle {{
    background: transparent;
    border: none;
    border-top: 1px solid {border};
    border-radius: 0;
    /* 親の見出し(padding-left: 4px)より内側に入れて、親 → 子 → 中身の階段にする。
       罫線はパディングを含む全幅に引かれるので、字下げしても横いっぱいのまま。 */
    padding: 6px 2px 4px 12px;
    text-align: left;
    font-weight: 600;
    font-size: {subheading_pt}pt;
    color: {text_primary};
}}
QToolButton#property_subsection_toggle[firstSection="true"] {{
    border-top: none;
    padding-top: 2px;
}}
QToolButton#property_subsection_toggle:hover {{
    background: {surface_2};
    /* accent_text はライトでは白なので、薄い背景のホバーでは消える。青の文字で強調する */
    color: {selection_accent};
}}
QToolButton#property_subsection_toggle:pressed {{
    background: {selection_highlight};
}}
QPushButton {{
    background: {surface};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 5px 14px;
}}
QPushButton:hover {{
    background: {surface_2};
    border-color: {selection_accent};
}}
QPushButton:pressed {{
    background: {selection_highlight};
}}
QPushButton:disabled {{
    color: {text_muted};
    border-color: {border};
}}
QPushButton:default {{
    /* 既定のボタン(Enter で実行)もほかの強調と同じ青にする。文字色は accent_text(どちらのモードでも読める)。 */
    background: {selection_accent};
    border-color: {selection_accent};
    color: {accent_text};
}}
/* フォーカスの枠はほかの選択・フォーカスと同じ青。ボタンの通常・ホバー・押下の色はそれぞれの規則で決める。 */
QPushButton:focus, QToolButton:focus {{
    border: 1px solid {selection_accent};
}}

/* --- アイコンだけの正方形のボタン(大きさは Python 側の setFixedSize) --- */
QPushButton[iconOnly="true"] {{
    padding: 4px;
}}

/* --- 入力欄 --- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {selection_highlight};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {selection_accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {text_muted};
    background: {surface_2};
}}

/* --- タイトルと軸ラベルのプレビュー: 入力欄と同じ見た目にし、ホバーで枠を青くしてクリックできることを示す --- */
QLabel#mathtext_preview_label {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
}}
QLabel#mathtext_preview_label:hover {{
    border-color: {selection_accent};
}}

/* --- スピンボックスの上下ボタン: 矢印は width / height を指定するだけで描かれなくなるので、
   画像(image: url(...))で与える。 --- */
QSpinBox, QDoubleSpinBox {{
    padding-right: 20px;
}}
/* 上下のボタンはそれぞれ独立した小さな角丸にして枠から少し離し、ふだんは透明にして矢印だけを見せる
   (ホバーと押下のときだけ背景を出す)。 */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    height: 13px;
    margin: 1px 2px 1px 1px;
    border: 1px solid transparent;
    border-radius: 4px;
    background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    height: 13px;
    margin: 1px 2px 1px 1px;
    border: 1px solid transparent;
    border-radius: 4px;
    background: transparent;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {border_strong};
}}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background: {selection_highlight};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({spin_up_arrow_url});
    width: 12px;
    height: 12px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({spin_down_arrow_url});
    width: 12px;
    height: 12px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    /* スピンボックスと同じ理由で画像にし、大きさもそろえる */
    image: url({spin_down_arrow_url});
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background: {surface};
    border: 1px solid {border};
    selection-background-color: {selection_highlight};
    selection-color: {text_primary};
    outline: none;
}}

/* --- リスト / ツリー / テーブル --- */
QTreeWidget, QListWidget, QTableWidget {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 8px;
    alternate-background-color: {surface_2};
}}
QHeaderView::section {{
    background: {surface_2};
    color: {text_secondary};
    border: none;
    border-bottom: 1px solid {border};
    padding: 4px 6px;
}}
QTreeWidget::item, QListWidget::item, QTableWidget::item {{
    padding: 3px;
}}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
    background: {selection_highlight};
    color: {text_primary};
}}
QTreeWidget::item, QListWidget::item {{
    padding: 5px 4px;
    border-radius: 5px;
}}

/* --- データセット一覧の選択: 背景は _DatasetTreeSelectionDelegate が1つの角丸で描く
   (QSS の ::item:selected はアイコンの列と文字の列に別々の角丸を描き、隙間ができる)。
   展開矢印の字下げの列は delegate を通らない drawBranches() で描かれ、汎用の ::item:selected が
   にじみ出るので、この一覧では透明にして打ち消す。 --- */
QTreeWidget#dataset_list_widget {{
    selection-background-color: transparent;
    selection-color: {text_primary};
    /* 無いと、選択とフォーカスが重なったとき角丸の上に点線の四角が描かれる */
    outline: none;
    /* 枠線だけ消し、背景と角丸は残す */
    border: none;
}}
/* 汎用の ::item:selected が字下げの列ににじむのを、この一覧だけ打ち消す(上の説明を参照)。 */
QTreeWidget#dataset_list_widget::item:selected {{
    background: transparent;
}}

/* --- データセットの検索欄の枠線を消す --- */
QLineEdit#dataset_search_edit {{
    border: none;
}}

/* --- タブ --- */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
}}
QTabBar::tab {{
    background: transparent;
    color: {text_secondary};
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{
    background: {surface_2};
    color: {text_primary};
}}
QTabBar::tab:selected {{
    background: {surface};
    border-bottom: 2px solid {selection_accent};
    color: {selection_accent};
    font-weight: 600;
}}
/* QTabBar::close-button には何も指定しない。何か1つでも指定するとアイコンが描かれなくなる
   (QProxyStyle で差し替えても効かない)。見た目は _FlatThemeProxyStyle で決める。 */

QToolButton#add_tab_button {{
    margin: 3px 6px 3px 2px;
    border-radius: 13px;
    padding: 5px;
}}
QToolButton#add_tab_button:hover {{
    background: {selection_highlight};
}}

/* --- チェックボックスとラジオボタン: QCheckBox::indicator には何も指定しない。何か1つでも指定すると
   チェックマークが描かれず塗りつぶしの四角になる。見た目は _FlatThemeProxyStyle が描く。 --- */
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border_strong};
    border-radius: 7px;
    background: {surface};
}}
QRadioButton::indicator:checked {{
    /* チェックボックスの塗りと同じ青 */
    background: {selection_accent};
    border-color: {selection_accent};
}}

/* --- プログレスバー --- */
QProgressBar {{
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    background: {surface_2};
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 6px;
}}

/* --- スクロールバー --- */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {border_strong};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed {{
    /* つかめる場所を示すだけの部品なので、青ではなく濃いグレー(text_muted)で強調する。
       ドラッグ中も :hover が当たり続けるので、:pressed もそろえる。 */
    background: {text_muted};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {border_strong};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:pressed {{
    background: {text_muted};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""


# 見出しの文字サイズはアプリ既定のフォントからの相対にする。px で固定すると、OS 既定の大きさ
# (Windows 9pt、macOS 13pt 前後)によって見出しが本文より小さくなる。
HEADING_POINT_OFFSET = 2.0      # 上の2つの開閉見出し
SUBHEADING_POINT_OFFSET = 1.0   # プロパティ欄の節の見出し
_FALLBACK_BASE_POINT_SIZE = 9.0


def heading_point_sizes():
    """(上の見出し, 節の見出し) の pt。"""
    app = QApplication.instance()
    base = app.font().pointSizeF() if app is not None else _FALLBACK_BASE_POINT_SIZE
    if base <= 0:
        # ピクセル指定のフォントだと pointSizeF() は -1
        base = _FALLBACK_BASE_POINT_SIZE
    return base + HEADING_POINT_OFFSET, base + SUBHEADING_POINT_OFFSET


def build_qss(tokens: dict) -> str:
    """_FLAT_QSS_TEMPLATE の {token} を埋めた QSS。矢印の画像は text_primary の色で作る。"""
    format_args = dict(tokens)
    format_args["spin_up_arrow_url"] = _spinbox_arrow_icon_url("up", tokens["text_primary"])
    format_args["spin_down_arrow_url"] = _spinbox_arrow_icon_url("down", tokens["text_primary"])
    heading_pt, subheading_pt = heading_point_sizes()
    format_args["heading_pt"] = f"{heading_pt:.1f}"
    format_args["subheading_pt"] = f"{subheading_pt:.1f}"
    return _FLAT_QSS_TEMPLATE.format(**format_args)


def _build_dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.ColorRole.Link, QColor(90, 160, 230))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(60, 120, 200))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    return palette


class _FlatThemeProxyStyle(QProxyStyle):
    """QSS では描けないもの(QSS を当てると中身が消えるもの)をここで描く。

    QTabBar::close-button に QSS を当てると × が消え、QCheckBox::indicator に当てるとチェックマークが
    描かれない。どちらも QSS は当てず、ここでアイコンを差し替え、チェックボックスを自前で描く。
    """
    def __init__(self, base_style, tokens):
        super().__init__(base_style)
        self.update_tokens(tokens)

    def update_tokens(self, tokens):
        """色だけ替える(作り直して setStyle() し直すとクラッシュする。apply_theme() を参照)。"""
        self._tokens = tokens
        self._close_icon = _svg_icon("x", color=tokens["text_secondary"], size=14)
        self._close_pixmap = self._close_icon.pixmap(14, 14)

    def standardIcon(self, standard_icon, option=None, widget=None):
        if standard_icon == QStyle.StandardPixmap.SP_TabCloseButton:
            return self._close_icon
        return super().standardIcon(standard_icon, option, widget)

    def standardPixmap(self, standard_pixmap, option=None, widget=None):
        # タブの閉じるボタンは standardIcon() ではなく standardPixmap() でアイコンを取る
        if standard_pixmap == QStyle.StandardPixmap.SP_TabCloseButton:
            return self._close_pixmap
        return super().standardPixmap(standard_pixmap, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            self._draw_checkbox_indicator(option, painter)
            return
        if element == QStyle.PrimitiveElement.PE_FrameTabBarBase:
            # タブにしたドックの上に出る灰色の線(Fusion が描く、QSS では消せない)を描かない
            return
        super().drawPrimitive(element, option, painter, widget)

    def _draw_checkbox_indicator(self, option, painter):
        tokens = self._tokens
        checked = bool(option.state & QStyle.StateFlag.State_On)
        tristate = bool(option.state & QStyle.StateFlag.State_NoChange)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)

        if not enabled:
            fill = QColor(tokens["surface_2"])
            border = QColor(tokens["border"])
        elif checked or tristate:
            fill = QColor(tokens["selection_accent"])
            border = fill
        else:
            fill = QColor(tokens["surface"])
            border = QColor(tokens["border_strong"])

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(border)
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.setBrush(fill)
        rect = QRectF(option.rect).adjusted(0.75, 0.75, -0.75, -0.75)
        painter.drawRoundedRect(rect, 3, 3)

        if checked or tristate:
            check_color = QColor(tokens["accent_text"]) if enabled else QColor(tokens["text_muted"])
            check_pen = QPen(check_color)
            check_pen.setWidthF(1.6)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            r = option.rect
            path = QPainterPath()
            if tristate:
                # 一部だけ選ばれている: 横棒
                path.moveTo(r.x() + r.width() * 0.22, r.y() + r.height() * 0.5)
                path.lineTo(r.x() + r.width() * 0.78, r.y() + r.height() * 0.5)
            else:
                path.moveTo(r.x() + r.width() * 0.20, r.y() + r.height() * 0.52)
                path.lineTo(r.x() + r.width() * 0.42, r.y() + r.height() * 0.74)
                path.lineTo(r.x() + r.width() * 0.82, r.y() + r.height() * 0.26)
            painter.drawPath(path)

        painter.restore()


def apply_theme(app, dark: bool):
    """ライトでもダークでも Fusion を使い、パレットだけ替える(スタイルを替えるとボタンの大きさや余白まで変わる)。"""
    global _original_palette, _original_style_name, _current_proxy_style, _current_tokens
    global _last_applied_dark
    if _original_palette is None:
        _original_palette = QPalette(app.palette())
        _original_style_name = app.style().objectName()

    tokens = DARK_TOKENS if dark else LIGHT_TOKENS
    _current_tokens = tokens

    # 同じ値で何度も呼ばれる(タブごとなど)。setPalette() と setStyleSheet() は1回約130ms かかるので省く
    if _current_proxy_style is not None and _last_applied_dark == dark:
        return
    _last_applied_dark = dark

    # スタイルは QApplication に1つだけ作り、setStyle() も1回だけ。setStyle() は古いスタイルを削除するので、
    # 差し替えるとほかのタブのウィジェットが削除済みのスタイルを触ってプロセスごと落ちる
    if _current_proxy_style is None:
        base_style = QStyleFactory.create('Fusion')
        _current_proxy_style = _FlatThemeProxyStyle(base_style, tokens)
        app.setStyle(_current_proxy_style)
    else:
        _current_proxy_style.update_tokens(tokens)
    if dark:
        app.setPalette(_build_dark_palette())
    else:
        app.setPalette(_original_palette)

    app.setStyleSheet(build_qss(tokens))


def current_tokens() -> dict:
    """今のテーマの配色トークン。apply_theme() の前なら LIGHT_TOKENS。"""
    return _current_tokens or LIGHT_TOKENS


def current_selection_highlight_qcolor() -> QColor:
    """selection_highlight を QColor で返す。

    トークンは QSS 用の "rgba(r, g, b, a)" で、QColor(str) はこれを読めず不透明の黒になるので自前で解釈する。
    """
    tokens = _current_tokens or LIGHT_TOKENS
    raw = tokens["selection_highlight"]
    match = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", raw)
    if not match:
        return QColor(raw)
    r, g, b, a = match.groups()
    color = QColor(int(r), int(g), int(b))
    color.setAlphaF(float(a))
    return color


def install_dock_focus_highlight(window):
    """フォーカスのあるドックの枠を強調する(dockActive プロパティを QSS で描く)。

    focusChanged はプロセス全体で1つなので、ほかのタブのドックにフォーカスが移ったら、このウィンドウの強調を消すだけにする。
    後から足したドック(プラグインのパネル)も、祖先を辿るので登録しなくてよい。
    """
    from PySide6.QtWidgets import QApplication, QDockWidget

    def _dock_ancestor(widget):
        while widget is not None and not isinstance(widget, QDockWidget):
            widget = widget.parentWidget()
        return widget

    def _set_active(dock, active):
        if dock is None:
            return
        dock.setProperty("dockActive", active)
        style = dock.style()
        style.unpolish(dock)
        style.polish(dock)

    state = {"active": None}

    def _on_focus_changed(old, new):
        dock = _dock_ancestor(new) if new is not None else None
        if dock is not None and dock.window() is not window:
            dock = None
        if dock is state["active"]:
            return
        _set_active(state["active"], False)
        _set_active(dock, True)
        state["active"] = dock

    app = QApplication.instance()
    app.focusChanged.connect(_on_focus_changed)
    # 窓が破棄された後に接続が残らないように
    window.destroyed.connect(lambda: app.focusChanged.disconnect(_on_focus_changed))


def apply_form_spacing(widget, spacing=12):
    """フォームの行の間隔を spacing まで広げる(既に広いものは縮めない)。"""
    from PySide6.QtWidgets import QFormLayout
    for form_layout in widget.findChildren(QFormLayout):
        if form_layout.verticalSpacing() < spacing:
            form_layout.setVerticalSpacing(spacing)


def disable_scroll_value_change():
    """スピンボックスとコンボでホイールによる値の変更を止める(スクロールしただけで値が変わる)。

    フォーカスの有無では判定できない(フォーカスはカーソルが離れても残る)ので常に止める。無視したイベントは
    親に渡るので、スクロールはそのままできる。クラスのメソッドを書き換えるので、起動時に1回呼ぶ。
    """
    global _wheel_value_change_disabled
    if _wheel_value_change_disabled:
        return
    _wheel_value_change_disabled = True

    def _ignore_wheel_event(self, event):
        event.ignore()

    QAbstractSpinBox.wheelEvent = _ignore_wheel_event
    QComboBox.wheelEvent = _ignore_wheel_event
