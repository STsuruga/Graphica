"""アプリ全体のテーマ。Fusion スタイルの上でパレットを切り替え、QSS でフラットな見た目にする。"""
import os
import re
import tempfile

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QFrame,
                               QProxyStyle, QStyle, QStyledItemDelegate, QStyleFactory)

from graphica.gui.icon_utils import icon as _svg_icon
from graphica.gui.theme_color import DEFAULT_THEME_COLOR, derive_accent, normalize_hex

_wheel_value_change_disabled = False
_original_show_combo_popup = None
_current_proxy_style = None
_current_tokens = None
_current_theme_color = DEFAULT_THEME_COLOR
_last_applied_dark = None  # 同じ (明暗, テーマカラー) での apply_theme() は重い処理を省く
_last_applied_theme_color = None

# 選択の角丸を描くデリゲートが使う。QSS の QTreeWidget の border-radius と同じ値にしておくこと
DATASET_LIST_ITEM_RADIUS = 8

# スピンボックスの矢印は PNG にして QSS の ::up-arrow / ::down-arrow の image で指定する。
# 枠を QSS で描いていると、QProxyStyle で矢印を描いても反映されたりされなかったりする。
_ARROW_ICON_CACHE_DIR = os.path.join(tempfile.gettempdir(), "graphica_theme_icons")


# 矢印の PNG の大きさ。QSS では 12px に縮めて出すので、高 DPI の画面でもにじまないよう倍で描く
ARROW_ICON_SIZE = 28


def _spinbox_arrow_icon_url(direction: str, color: str) -> str:
    """節の見出しと同じ線のシェブロンの PNG を(無ければ)作り、QSS の url() に入れられるパスを返す。"""
    os.makedirs(_ARROW_ICON_CACHE_DIR, exist_ok=True)
    safe_color = color.lstrip("#")
    # 形と大きさをファイル名に入れ、描き方を変えたとき古い PNG を使い回さない
    size = ARROW_ICON_SIZE
    filename = f"spin_chevron_{direction}_{safe_color}_{size}.png"
    path = os.path.join(_ARROW_ICON_CACHE_DIR, filename)

    if not os.path.exists(path):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(color))
        pen.setWidthF(size * 0.11)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx, cy = size / 2, size / 2
        half_width, half_height = size * 0.28, size * 0.14
        sign = -1 if direction == "up" else 1
        chevron = QPainterPath()
        chevron.moveTo(cx - half_width, cy - sign * half_height)
        chevron.lineTo(cx, cy + sign * half_height)
        chevron.lineTo(cx + half_width, cy - sign * half_height)
        painter.drawPath(chevron)
        painter.end()
        pixmap.save(path)

    # QSS の url() は Windows の区切りの \ を読めない
    return path.replace(os.sep, "/")

# 配色の唯一の定義(見本は docs/dev/mockups/gui_redesign/)。利用者が変えられるのはテーマカラーだけで、
# 強調の4色(accent・accent_fg・on_accent・accent_soft)はそこから theme_color.derive_accent() が作る。
# 配色パレット(データの線の色)とは別物。
_LIGHT_BASE_TOKENS = {
    "bg": "#F1F2F4", "surface": "#FFFFFF", "surface_2": "#F3F5F7",
    # 上部バー・帯・ステータスバー
    "chrome": "#E4E7EA",
    # surface_2 の地の上に浮かせる面(セグメントの選んだもの)
    "raised": "#FFFFFF",
    "border": "#E0E3E6", "border_strong": "#CBD0D5",
    "text_primary": "#191D1F", "text_secondary": "#56606A", "text_muted": "#8A939B",
    "success": "#22A06B", "danger": "#D1453B",
    # 良い状態のバッジ(フィットの R²)の地と文字
    "success_soft": "rgba(34, 160, 107, 0.14)", "success_fg": "#1A7F55",
    # 欠損値のセル。強調の色と被らない
    "warning_soft": "#FDF1D8",
}
_DARK_BASE_TOKENS = {
    "bg": "#111417", "surface": "#181B1F", "surface_2": "#1F2328",
    "chrome": "#0E1013",
    "raised": "#373E46",
    "border": "#272C32", "border_strong": "#373E46",
    "text_primary": "#E6E9EC", "text_secondary": "#A0A9B1", "text_muted": "#69737B",
    "success": "#5BD39A", "danger": "#F1857C",
    "success_soft": "rgba(91, 211, 154, 0.14)", "success_fg": "#5BD39A",
    "warning_soft": "rgba(250, 204, 21, 0.16)",
}


def build_tokens(dark: bool, theme_color: str = DEFAULT_THEME_COLOR) -> dict:
    """テーマカラーから強調の色を計算して、明暗の地の色と合わせた全トークンを返す。"""
    base = _DARK_BASE_TOKENS if dark else _LIGHT_BASE_TOKENS
    tokens = dict(base)
    derived = derive_accent(theme_color, base["surface"], dark)
    for key in ("accent", "accent_fg", "on_accent", "accent_soft"):
        tokens[key] = derived[key]
    return tokens


# 既定のテーマカラーでの全トークン。起動画面やキャンバスの定数など、設定を読む前に使う所はこれを見る
LIGHT_TOKENS = build_tokens(False)
DARK_TOKENS = build_tokens(True)


def tokens_for(dark: bool, theme_color: str = DEFAULT_THEME_COLOR) -> dict:
    """既定の色なら LIGHT_TOKENS / DARK_TOKENS そのもの、それ以外は作り直した辞書。"""
    if normalize_hex(theme_color) == DEFAULT_THEME_COLOR:
        return DARK_TOKENS if dark else LIGHT_TOKENS
    return build_tokens(dark, theme_color)

_FLAT_QSS_TEMPLATE = """
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {text_primary};
    /* 操作の強調(選択・ホバー・押下・フォーカス)はすべてテーマカラーの accent / accent_soft にそろえる。 */
    selection-background-color: {accent_soft};
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
    background: {accent_soft};
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
    background: {accent_soft};
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
    border: 1px solid {border};
    border-radius: 14px;
}}
/* グラフの下のパネル(GUI 刷新、アドバンスド): カードと同じ角丸。上にアイコン付きのタブ */
QFrame#bottom_panel {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 14px;
}}
QWidget#bottom_panel_header {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {border};
}}
QToolButton#bottom_tab {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px 10px;
    color: {text_secondary};
}}
QToolButton#bottom_tab:hover {{
    color: {text_primary};
}}
QToolButton#bottom_tab:checked {{
    background: {surface_2};
    color: {text_primary};
    font-weight: 600;
}}
QLabel#bottom_badge {{
    background: {surface_2};
    color: {text_secondary};
    border-radius: 5px;
    padding: 0 6px;
    font-size: 10.5px;
}}
QLabel#bottom_badge[ok="true"] {{
    background: {success_soft};
    color: {success_fg};
}}
QLabel#bottom_panel_meta {{
    color: {text_muted};
    font-size: 11.5px;
    background: transparent;
    margin-right: 4px;
}}
QStackedWidget#bottom_panel_stack, QStackedWidget#bottom_panel_stack > QWidget {{
    background: transparent;
    border: none;
}}
QTableView#bottom_data_table {{
    background: transparent;
    border: none;
    border-radius: 0;
    selection-background-color: {accent_soft};
    selection-color: {text_primary};
    gridline-color: {border};
}}
QTableView#bottom_data_table::item {{
    border-bottom: 1px solid {border};
    padding: 0 14px;
}}
QTableView#bottom_data_table QHeaderView::section {{
    padding: 4px 14px;
    font-weight: 600;
}}
QPlainTextEdit#bottom_log, QTextEdit#fit_info_textedit {{
    background: transparent;
    border: none;
    padding: 6px 10px;
}}
/* フィット結果の表: 桁がそろうよう等幅の数字。下のパネルの枠の中なので表の枠は付けない */
QTableWidget#fit_result_table {{
    background: transparent;
    border: none;
    border-radius: 0;
    font-family: "Consolas", "Menlo", monospace;
    selection-background-color: {accent_soft};
    selection-color: {text_primary};
}}
QTableWidget#fit_result_table::item {{
    border-bottom: 1px solid {border};
    padding: 0 10px;
}}
QLabel#fit_result_title {{
    font-weight: 600;
}}
/* 下のパネル自体が角丸の枠なので、中の一覧には枠を付けない */
QTreeWidget#provenance_tree {{
    background: transparent;
    border: none;
    border-radius: 0;
}}
QPlainTextEdit#bottom_log {{
    font-family: "Consolas", "Menlo", monospace;
    font-size: 11.5px;
}}
/* 欄の下の補足と、中身が空のときの案内。ダークでも読める淡い文字色にする */
QLabel[hint="true"] {{
    color: {text_muted};
    font-size: 9pt;
    background: transparent;
}}
QLabel[emptyNote="true"] {{
    color: {text_muted};
    padding: 12px;
    background: transparent;
}}
/* エクスポートのプレビューの枠: 下のパネルやカードと同じく角丸 */
QLabel#export_preview_frame {{
    background: {surface_2};
    border: 1px solid {border};
    border-radius: 10px;
    color: {text_muted};
}}
/* 縦横のスクロールバーが出たときの右下の角。既定の白い四角を消す */
QAbstractScrollArea::corner {{
    background: transparent;
    border: none;
}}
/* グラフのカード(GUI 刷新): ミニマップとの間は線を引かず、すき間だけ */
QFrame#canvas_separator {{
    background: transparent;
    border: none;
}}
QLabel#card_title {{
    font-size: 15px;
    font-weight: 600;
    background: transparent;
}}
QLabel#card_meta {{
    color: {text_muted};
    font-size: 11.5px;
    background: transparent;
}}
QToolButton#card_button {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 3px;
}}
QToolButton#card_button:hover {{
    background: {surface_2};
}}
QToolButton#card_button:checked {{
    background: {accent_soft};
    border: none;
}}
/* アドバンスドの道具: プロットの上に文字付き。モードの7つは1つの塊(toolSegment) */
QToolBar#plot_toolbar {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {border};
    padding: 0 0 6px 0;
    spacing: 0;
}}
QToolBar#plot_toolbar QToolButton {{
    border: none;
    border-radius: 6px;
    padding: 3px 6px;
    margin: 0 2px 0 0;
    color: {text_primary};
    font-size: 12px;
}}
QToolBar#plot_toolbar QToolButton[toolSegment="first"],
QToolBar#plot_toolbar QToolButton[toolSegment="middle"],
QToolBar#plot_toolbar QToolButton[toolSegment="last"] {{
    background: {surface_2};
    border-radius: 0;
    margin: 0;
    padding: 4px 7px;
}}
QToolBar#plot_toolbar QToolButton[toolSegment="first"] {{
    border-top-left-radius: 8px;
    border-bottom-left-radius: 8px;
}}
QToolBar#plot_toolbar QToolButton[toolSegment="last"] {{
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    margin-right: 4px;
}}
QToolBar#plot_toolbar QToolButton:hover {{
    background: {surface_2};
}}
QToolBar#plot_toolbar QToolButton[toolSegment="first"]:hover,
QToolBar#plot_toolbar QToolButton[toolSegment="middle"]:hover,
QToolBar#plot_toolbar QToolButton[toolSegment="last"]:hover {{
    color: {accent_fg};
}}
/* 選んでいるモードは強調の色で塗って白抜きにし(左の帯と同じ)、塊の中では角を丸めない */
QToolBar#plot_toolbar QToolButton:checked {{
    background: {accent};
    color: {on_accent};
    border: none;
    font-weight: 600;
}}
QToolBar#plot_toolbar QToolButton[toolSegment="middle"]:checked {{
    border-radius: 0;
}}
/* 選んでいるものにマウスを乗せても、文字は白抜きのまま(上の :hover の強調の色だと塗りと同じ色で消える) */
QToolBar#plot_toolbar QToolButton[toolSegment="first"]:checked:hover,
QToolBar#plot_toolbar QToolButton[toolSegment="middle"]:checked:hover,
QToolBar#plot_toolbar QToolButton[toolSegment="last"]:checked:hover {{
    background: {accent};
    color: {on_accent};
}}
/* シンプルの道具: グラフの左に浮かせた縦の並び */
QToolBar#plot_tool_rail {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 13px;
    padding: 4px;
    spacing: 3px;
}}
QToolBar#plot_tool_rail QToolButton {{
    border: none;
    border-radius: 9px;
    padding: 6px;
}}
QToolBar#plot_tool_rail QToolButton:hover {{
    background: {surface_2};
}}
QToolBar#plot_tool_rail QToolButton:checked {{
    background: {accent};
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
/* ツールバーのボタンは QToolButton なので、QPushButton とは別にホバーと押下を強調の色にする。 */
QToolButton:pressed {{
    background: {accent_soft};
}}
QToolButton:checked {{
    background: {accent_soft};
    border: 1px solid {accent};
}}
/* ステータスバー(GUI 刷新): 上部バー・帯と同じ chrome の地、小さめの文字 */
QStatusBar {{
    background: {chrome};
    border-top: 1px solid {border};
    min-height: 26px;
    color: {text_secondary};
    font-size: 11px;
}}
QStatusBar::item {{
    border: none;
}}
QStatusBar QLabel#status_text, QStatusBar QLabel#status_coordinates {{
    color: {text_secondary};
    font-size: 11px;
    background: transparent;
    padding: 0 6px;
}}
QStatusBar QLabel#status_coordinates {{
    font-family: "Consolas", "Menlo", monospace;
}}
QFrame#status_dot {{
    background: {success};
    border: none;
    border-radius: 3px;
}}
/* ⚙ のポップアップ(テーマカラー) */
QFrame#settings_popover {{
    background: {surface};
    border: 1px solid {border_strong};
    border-radius: 12px;
}}
QFrame#settings_popover QLabel {{
    background: transparent;
}}
QLabel#settings_popover_title {{
    font-weight: 600;
    font-size: 14px;
}}
QLabel#settings_popover_sub {{
    color: {text_muted};
    font-size: 11.5px;
}}
QLabel#settings_popover_strong {{
    font-weight: 600;
}}
QLabel#settings_popover_label {{
    color: {text_secondary};
    font-size: 12px;
}}
QLabel#settings_popover_mono {{
    font-family: "Consolas", "Menlo", monospace;
    font-size: 12px;
}}
QLabel#settings_popover_note {{
    color: {text_secondary};
    background: {surface_2};
    border-radius: 8px;
    padding: 6px 8px;
    font-size: 11.5px;
}}
QFrame#settings_popover_row {{
    background: transparent;
    border: none;
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
    border: 1px solid {accent};
}}
QDockWidget[dockActive="true"]::title {{
    border-bottom: 1px solid {accent};
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
    background: {accent};
}}

/* --- グループボックス / ボタン --- */
/* インスペクタの節の見出しと同じ形: 上に細い罫線、その下に太字の見出し。見出しは padding の中に置く
   (margin に置くと罫線が見出しの下に来る)。QFontDialog などの Qt 標準のダイアログでも見切れない。 */
QGroupBox {{
    background: transparent;
    border: none;
    border-top: 1px solid {border};
    border-radius: 0;
    margin-top: 6px;
    padding-top: 30px;
    font-weight: 500;
}}
QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 0;
    top: 9px;
    padding: 0;
    color: {text_primary};
    font-size: {subheading_pt}pt;
    font-weight: 600;
    background: transparent;
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
    subcontrol-origin: margin;
    left: 0;
    /* 上のモーダル側と同じく、枠の外にはみ出さない位置にする */
    top: 0px;
    padding: 0;
    color: {text_secondary};
    font-size: 12.5px;
    letter-spacing: .02em;
    background: transparent;
    border-radius: 0;
}}

/* --- プロパティ欄の節の見出し: 本文より少し大きく・太く・濃くし、中身を字下げする。
   区切りは細い罫線1本。1本目は親の見出しのすぐ下で二重線に見えるので引かない。 --- */
QToolButton#property_subsection_toggle {{
    background: transparent;
    border: none;
    border-top: 1px solid {border};
    border-radius: 0;
    /* 見本の節の見出し: 上に細い罫線、中身は 20px 字下げ(罫線はパディングを含む全幅に引かれる) */
    padding: 9px 2px 5px 0;
    margin-top: 4px;
    text-align: left;
    font-weight: 600;
    font-size: {subheading_pt}pt;
    color: {text_primary};
}}
QToolButton#property_subsection_toggle[firstSection="true"] {{
    border-top: none;
    margin-top: 0;
}}
QToolButton#property_subsection_toggle:!checked {{
    padding-top: 7px;
    padding-bottom: 7px;
    margin-top: 0;
}}
QToolButton#property_subsection_toggle:hover {{
    background: transparent;
    /* on_accent はライトでは白なので、薄い背景のホバーでは消える。文字用の accent_fg で強調する */
    color: {accent_fg};
}}
QToolButton#property_subsection_toggle:pressed {{
    background: transparent;
}}
QWidget#property_section_body QLabel {{
    color: {text_secondary};
    background: transparent;
}}
/* --- 右のインスペクタ(GUI 刷新): ドックの枠と見出しの帯は出さず、左に1本の罫線 --- */
QDockWidget#control_dock_widget {{
    background: {surface};
    border: none;
    border-left: 1px solid {border};
    border-radius: 0;
}}
QWidget#inspector, QWidget#inspector_page, QWidget#inspector_axes_content, QWidget#inspector_legend_content,
QScrollArea#inspector_scroll_properties, QScrollArea#inspector_scroll_axes,
QScrollArea#inspector_scroll_legend, QScrollArea#inspector_scroll_export,
QScrollArea#inspector_scroll_properties > QWidget > QWidget, QScrollArea#inspector_scroll_axes > QWidget > QWidget,
QScrollArea#inspector_scroll_legend > QWidget > QWidget, QScrollArea#inspector_scroll_export > QWidget > QWidget {{
    background: {surface};
    border: none;
}}
QWidget#inspector_tab_row {{
    background: {surface};
    border-bottom: 1px solid {border};
}}
QTabBar#inspector_tabs::tab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 12px 0 9px 0;
    margin-right: 16px;
    color: {text_secondary};
    font-weight: 400;
}}
QTabBar#inspector_tabs::tab:hover {{
    background: transparent;
    color: {text_primary};
}}
QTabBar#inspector_tabs::tab:selected {{
    background: transparent;
    border-bottom: 2px solid {accent};
    color: {text_primary};
    font-weight: 600;
}}
QWidget#inspector_target {{
    background: {surface};
    border-bottom: 1px solid {border};
}}
QLabel#inspector_target_name {{
    font-weight: 600;
    background: transparent;
}}
QLabel#inspector_target_sub {{
    color: {text_muted};
    font-size: 11px;
    background: transparent;
}}
/* シンプルのプロパティの下の案内(点線の枠と、アドバンスドに切り替えるリンク) */
QFrame#lite_more_box {{
    background: transparent;
    border: 1px dashed {border_strong};
    border-radius: 10px;
    margin: 12px 0 4px 0;
}}
QLabel#lite_more_text, QLabel#lite_more_icon {{
    color: {text_secondary};
    background: transparent;
    border: none;
}}
QPushButton#lite_more_button {{
    background: transparent;
    border: none;
    padding: 0;
    color: {accent_fg};
    font-weight: 600;
    text-align: left;
}}
QPushButton#lite_more_button:hover {{
    background: transparent;
    text-decoration: underline;
}}
QPushButton {{
    background: {surface};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 5px 14px;
}}
QPushButton:hover {{
    background: {surface_2};
    border-color: {accent};
}}
QPushButton:pressed {{
    background: {accent_soft};
}}
QPushButton:disabled {{
    color: {text_muted};
    border-color: {border};
}}
QPushButton:default {{
    /* 既定のボタン(Enter で実行)もほかの強調と同じ色で塗る。文字色は on_accent(塗りとの比で白か黒を選んである)。 */
    background: {accent};
    border-color: {accent};
    color: {on_accent};
}}
/* フォーカスの枠はほかの選択・フォーカスと同じ強調の色。ボタンの通常・ホバー・押下の色はそれぞれの規則で決める。 */
QPushButton:focus, QToolButton:focus {{
    border: 1px solid {accent};
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
    selection-background-color: {accent_soft};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {text_muted};
    background: {surface_2};
}}

/* --- タイトルと軸ラベルのプレビュー: 入力欄と同じ見た目にし、ホバーで枠を強調の色にしてクリックできることを示す --- */
QLabel#mathtext_preview_label {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
}}
QLabel#mathtext_preview_label:hover {{
    border-color: {accent};
}}
QLabel#mathtext_preview_label[placeholderShown="true"] {{
    color: {text_muted};
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
    background: {accent_soft};
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
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {{
    image: url({spin_up_arrow_disabled_url});
}}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
    image: url({spin_down_arrow_disabled_url});
}}
QComboBox {{
    /* 一覧はメニュー風ではなくリストで出す(メニュー風だと外側に四角い枠が描かれ、角丸にならない) */
    combobox-popup: 0;
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
QComboBox::down-arrow:disabled {{
    image: url({spin_down_arrow_disabled_url});
}}
/* 開いた一覧: 箱の角丸はプルダウンと同じ 6px(外側の器は透明にする。install_rounded_combo_popups) */
QComboBoxPrivateContainer {{
    background: transparent;
    border: none;
}}
QComboBox QAbstractItemView {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {accent_soft};
    selection-color: {accent_fg};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: 24px;
    padding: 0 8px;
    border-radius: 5px;
    color: {text_primary};
}}
QComboBox QAbstractItemView::item:hover {{
    background: {surface_2};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {accent_soft};
    color: {accent_fg};
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
    background: {accent_soft};
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
    background: {surface_2};
    border-radius: 7px;
    padding: 5px 9px;
}}

/* --- タブ --- */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
}}
/* 「軸」のサブタブは下線のタブだけにし、中身を箱で囲まない(インスペクタの中に箱が入れ子になる) */
QTabWidget#axis_tab_widget::pane {{
    border: none;
    border-top: 1px solid {border};
    border-radius: 0;
}}
QLabel#subplot_target_caption, QLabel#subplot_target_detail {{
    color: {text_secondary};
    font-size: 11.5px;
}}
QLabel#subplot_target_name {{
    font-weight: 600;
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
    border-bottom: 2px solid {accent};
    color: {accent_fg};
    font-weight: 600;
}}
/* QTabBar::close-button には何も指定しない。何か1つでも指定するとアイコンが描かれなくなる
   (QProxyStyle で差し替えても効かない)。見た目は _FlatThemeProxyStyle で決める。 */

QToolButton#add_tab_button {{
    border-radius: 7px;
    padding: 4px;
}}
QToolButton#add_tab_button:hover {{
    background: {surface};
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
    /* チェックボックスの塗りと同じ色 */
    background: {accent};
    border-color: {accent};
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
    /* つかめる場所を示すだけの部品なので、強調の色ではなく濃いグレー(text_muted)で強調する。
       ドラッグ中も :hover が当たり続けるので、:pressed もそろえる。 */
    background: {text_muted};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
/* 幅だけ取っておくスクロールバー(インスペクタ)で、スクロールするものが無いとき */
QScrollBar[scrollIdle="true"]::handle:vertical {{
    background: transparent;
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

/* --- GUI 刷新の部品(gui/widgets/)。寸法は見本 docs/dev/mockups/gui_redesign/ のまま --- */
/* セグメント: くぼんだ溝の上に、選んだものだけ白い板を浮かせる(区切り線なし)。
   板の下の影は SegmentedControl.paintEvent が描く(QSS には影が無い)。 */
QFrame#segmented_control {{
    background: {surface_2};
    border: 1px solid {border};
    border-radius: 14px;
}}
QToolButton#segment {{
    background: transparent;
    border: none;
    border-radius: 11px;
    padding: 0 8px;
    color: {text_secondary};
}}
QToolButton#segment:hover {{
    color: {text_primary};
}}
QToolButton#segment:checked {{
    background: {raised};
    color: {accent_fg};
    font-weight: 600;
}}
QToolButton#segment:disabled {{
    color: {text_muted};
}}
QToolButton#segment:checked:disabled {{
    background: {surface};
    color: {text_muted};
}}
/* グラフの種類のタイル(アイコン+文字) */
QToolButton#type_tile {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 9px;
    padding: 4px 2px;
    color: {text_secondary};
    font-size: 11px;
}}
QToolButton#type_tile:hover {{
    border-color: {border_strong};
    background: {surface};
}}
QToolButton#type_tile:checked {{
    border-color: {accent};
    background: {accent_soft};
    color: {accent_fg};
    font-weight: 600;
}}
/* スライダー(線の太さ・透明度)。数値は横の今のスピンボックス */
QSlider#slider_spin_slider::groove:horizontal {{
    height: 4px;
    background: {border_strong};
    border-radius: 2px;
}}
QSlider#slider_spin_slider::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}
QSlider#slider_spin_slider::handle:horizontal {{
    background: #FFFFFF;
    border: 2px solid {accent};
    width: 8px;
    height: 8px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider#slider_spin_slider::sub-page:horizontal:disabled {{
    background: {border_strong};
}}
QSlider#slider_spin_slider::handle:horizontal:disabled {{
    border-color: {border_strong};
}}
/* スライダーの横の数値(矢印なし) */
QDoubleSpinBox[sliderValue="true"], QSpinBox[sliderValue="true"] {{
    padding: 3px 4px;
}}
/* 統計のカード */
QFrame#stat_card {{
    background: {surface_2};
    border: none;
    border-radius: 9px;
}}
QLabel#stat_card_label {{
    color: {text_muted};
    font-size: 11px;
    background: transparent;
}}
QLabel#stat_card_value {{
    color: {text_primary};
    font-size: 14px;
    font-weight: 600;
    background: transparent;
}}
/* --- 画面の骨組み(gui/shell/): 上部バー・帯・左パネル --- */
QWidget#app_header {{
    background: {chrome};
    border-bottom: 1px solid {border};
}}
QLabel#header_title {{
    font-weight: 600;
    background: transparent;
}}
QFrame#header_separator {{
    background: {border_strong};
    border: none;
}}
QToolButton#header_button {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px;
}}
QToolButton#header_button:hover {{
    background: {surface};
}}
QToolButton#header_button:disabled {{
    background: transparent;
}}
QTabBar#project_tab_bar {{
    background: transparent;
}}
QTabBar#project_tab_bar::tab {{
    height: 32px;
    padding: 0 12px 0 12px;
    margin: 0 2px 0 0;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: {text_secondary};
    font-weight: 400;
}}
QTabBar#project_tab_bar::tab:hover {{
    background: {surface_2};
    color: {text_primary};
}}
QTabBar#project_tab_bar::tab:selected {{
    background: {surface};
    color: {text_primary};
    border: none;
    font-weight: 600;
}}
QPushButton#command_search {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 7px;
    padding: 0;
    text-align: left;
}}
QPushButton#command_search:hover {{
    border-color: {border_strong};
    background: {surface};
}}
QLabel#command_search_text {{
    color: {text_muted};
    background: transparent;
}}
/* ショートカットの表示は枠線を引かず、薄い地色だけで控えめに */
QLabel#kbd_hint {{
    color: {text_muted};
    background: {surface_2};
    border: none;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 10.5px;
}}
/* 上部バーのモードの切り替え(「アドバンスド」とスイッチ) */
QLabel#mode_label {{
    color: {text_primary};
    background: transparent;
    font-weight: 600;
}}
QPushButton[primaryButton="true"] {{
    background: {accent};
    border: 1px solid {accent};
    border-radius: 7px;
    color: {on_accent};
    font-weight: 600;
    padding: 5px 12px;
}}
/* アイコンだけのエクスポート: 大きさは Python 側の setFixedSize、余白でアイコンが切れないように */
QPushButton#header_export_button {{
    padding: 0;
}}
QPushButton[primaryButton="true"]:hover {{
    background: {accent};
    border-color: {accent_fg};
}}
QPushButton[primaryButton="true"]:pressed {{
    background: {accent_fg};
}}
QPushButton[primaryButton="true"]:disabled {{
    background: {border_strong};
    border-color: {border_strong};
    color: {surface};
}}
QPushButton[ghostButton="true"], QToolButton[ghostButton="true"] {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px;
}}
QPushButton[ghostButton="true"]:hover, QToolButton[ghostButton="true"]:hover {{
    background: {surface_2};
}}
QPushButton[ghostButton="true"]:pressed, QToolButton[ghostButton="true"]:pressed {{
    background: {accent_soft};
}}
QWidget#activity_rail {{
    background: {chrome};
    border-right: 1px solid {border};
}}
QToolButton#rail_button {{
    background: transparent;
    border: none;
    border-radius: 10px;
}}
QToolButton#rail_button:hover {{
    background: {surface_2};
}}
QToolButton#rail_button:checked {{
    background: {accent};
}}
QStackedWidget#left_panel, QWidget#dataset_page {{
    background: {surface};
}}
QStackedWidget#left_panel {{
    border-right: 1px solid {border};
}}
QLabel#panel_title {{
    font-size: 15px;
    font-weight: 600;
    background: transparent;
}}
QLabel#count_pill {{
    background: {surface_2};
    color: {text_secondary};
    border-radius: 9px;
    padding: 0 7px;
    font-size: 11px;
}}
QLabel#stats_target_label {{
    color: {text_secondary};
    font-size: 12px;
    background: transparent;
}}
QWidget#side_page, QScrollArea#side_page_scroll, QScrollArea#side_page_scroll > QWidget,
QWidget#side_page_body {{
    background: {surface};
    border: none;
}}
QLabel#side_page_section {{
    color: {text_muted};
    font-size: 11.5px;
    padding: 10px 6px 4px 6px;
    background: transparent;
}}
QLabel#side_page_note {{
    color: {text_secondary};
    background: transparent;
}}
QPushButton#side_page_row {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px 8px;
    text-align: left;
    color: {text_primary};
}}
QPushButton#side_page_row:hover {{
    background: {surface_2};
}}
QPushButton#side_page_row:checked {{
    background: {accent_soft};
    color: {accent_fg};
    font-weight: 600;
}}
QPushButton#side_page_row:disabled {{
    color: {text_muted};
}}
QFrame#panel_foot {{
    background: transparent;
    border: none;
    border-top: 1px solid {border};
}}

/* 開閉できる節の見出し(右に状態の要約。要約は SectionHeader が text_muted で描く) */
QToolButton#section_header {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 9px 0 5px 0;
    text-align: left;
    font-weight: 600;
    color: {text_primary};
}}
QToolButton#section_header:hover {{
    color: {accent_fg};
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
    format_args["spin_up_arrow_url"] = _spinbox_arrow_icon_url("up", tokens["text_secondary"])
    format_args["spin_down_arrow_url"] = _spinbox_arrow_icon_url("down", tokens["text_secondary"])
    format_args["spin_up_arrow_disabled_url"] = _spinbox_arrow_icon_url("up", tokens["text_muted"])
    format_args["spin_down_arrow_disabled_url"] = _spinbox_arrow_icon_url("down", tokens["text_muted"])
    _heading_pt, subheading_pt = heading_point_sizes()
    format_args["subheading_pt"] = f"{subheading_pt:.1f}"
    return _FLAT_QSS_TEMPLATE.format(**format_args)


def _token_qcolor(value: str) -> QColor:
    """トークンの色を QColor に。QColor(str) は QSS の "rgba(r, g, b, a)" を読めず不透明の黒になるので自前で解釈する。"""
    match = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", value)
    if not match:
        return QColor(value)
    r, g, b, a = match.groups()
    color = QColor(int(r), int(g), int(b))
    color.setAlphaF(float(a))
    return color


def build_palette(tokens: dict) -> QPalette:
    """トークンから QPalette を作る。QSS の効かない所(Qt 標準のダイアログ、palette(...) を使うプラグインの部品)も揃う。"""
    palette = QPalette()
    roles = {
        "Window": "bg", "WindowText": "text_primary",
        "Base": "surface", "AlternateBase": "surface_2", "Text": "text_primary",
        "Button": "surface", "ButtonText": "text_primary",
        "ToolTipBase": "surface", "ToolTipText": "text_primary", "PlaceholderText": "text_muted",
        "Highlight": "accent", "HighlightedText": "on_accent",
        "Link": "accent_fg", "LinkVisited": "accent_fg", "BrightText": "danger",
        "Light": "surface", "Midlight": "border", "Mid": "border_strong", "Dark": "border_strong", "Shadow": "text_muted",
    }
    for role, key in roles.items():
        palette.setColor(getattr(QPalette.ColorRole, role), _token_qcolor(tokens[key]))
    for role in ("Text", "ButtonText", "WindowText"):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(tokens["text_muted"]))
    return palette


def _is_toggle_switch(widget):
    """スイッチの見た目にするのはチェックボックスだけ。型を先に確かめる(Qt から渡る widget を、PySide が
    消えた別の部品の器と取り違えて返すことがあり、そのまま property() を呼ぶと例外が連鎖する)。"""
    return isinstance(widget, QCheckBox) and bool(widget.property(TOGGLE_SWITCH_PROPERTY))


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

    def pixelMetric(self, metric, option=None, widget=None):
        if _is_toggle_switch(widget):
            if metric == QStyle.PixelMetric.PM_IndicatorWidth:
                return TOGGLE_SWITCH_SIZE[0]
            if metric == QStyle.PixelMetric.PM_IndicatorHeight:
                return TOGGLE_SWITCH_SIZE[1]
        return super().pixelMetric(metric, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            if _is_toggle_switch(widget):
                self._draw_toggle_switch(option, painter)
            else:
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
            fill = QColor(tokens["accent"])
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
            check_color = QColor(tokens["on_accent"]) if enabled else QColor(tokens["text_muted"])
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

    def _draw_toggle_switch(self, option, painter):
        """オン・オフのスイッチ。オンは強調の色の地につまみが右、オフは灰色の地につまみが左。"""
        tokens = self._tokens
        checked = bool(option.state & QStyle.StateFlag.State_On)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        track = QColor(tokens["accent"] if checked else tokens["border_strong"])
        if not enabled:
            track.setAlphaF(0.45)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(option.rect)
        height = min(rect.height(), TOGGLE_SWITCH_SIZE[1])
        rect = QRectF(rect.x(), rect.center().y() - height / 2, min(rect.width(), TOGGLE_SWITCH_SIZE[0]), height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, height / 2, height / 2)
        margin = 2.5
        knob = height - 2 * margin
        knob_x = rect.right() - margin - knob if checked else rect.left() + margin
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(knob_x, rect.top() + margin, knob, knob))
        painter.restore()


# チェックボックスをスイッチの見た目にする目印(値は今のチェックボックスのまま。make_toggle_switch() で付ける)
TOGGLE_SWITCH_PROPERTY = "toggleSwitch"
TOGGLE_SWITCH_SIZE = (30, 17)


def make_toggle_switch(checkbox):
    """QCheckBox をスイッチの見た目にする。部品を差し替えないので、値の対応(バインディング)はそのまま。"""
    checkbox.setProperty(TOGGLE_SWITCH_PROPERTY, True)
    style = checkbox.style()
    style.unpolish(checkbox)
    style.polish(checkbox)
    checkbox.updateGeometry()
    return checkbox


def make_option_rows_switches(root):
    """root の中のフォームで、1行を丸ごと占めるチェックボックス(機能のオン/オフ)をスイッチの見た目にする。

    名前の横や欄の中に並んだ小さなチェックは対象にしない(行の形で見分ける)。
    """
    from PySide6.QtWidgets import QFormLayout
    for form in root.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.SpanningRole)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QCheckBox) and not _is_toggle_switch(widget):
                make_toggle_switch(widget)


def apply_theme(app, dark: bool, theme_color: str = None):
    """ライトでもダークでも Fusion を使い、パレットだけ替える(スタイルを替えるとボタンの大きさや余白まで変わる)。

    theme_color を省くと、前に当てたテーマカラーのまま明暗だけを替える。
    """
    global _current_proxy_style, _current_tokens, _current_theme_color
    global _last_applied_dark, _last_applied_theme_color
    if theme_color is not None:
        _current_theme_color = normalize_hex(theme_color)

    tokens = tokens_for(dark, _current_theme_color)
    _current_tokens = tokens

    # 同じ値で何度も呼ばれる(タブごとなど)。setPalette() と setStyleSheet() は1回約130ms かかるので省く
    if (_current_proxy_style is not None and _last_applied_dark == dark
            and _last_applied_theme_color == _current_theme_color):
        return
    _last_applied_dark = dark
    _last_applied_theme_color = _current_theme_color

    # スタイルは QApplication に1つだけ作り、setStyle() も1回だけ。setStyle() は古いスタイルを削除するので、
    # 差し替えるとほかのタブのウィジェットが削除済みのスタイルを触ってプロセスごと落ちる
    if _current_proxy_style is None:
        base_style = QStyleFactory.create('Fusion')
        _current_proxy_style = _FlatThemeProxyStyle(base_style, tokens)
        app.setStyle(_current_proxy_style)
        install_rounded_combo_popups()
    else:
        _current_proxy_style.update_tokens(tokens)
    app.setPalette(build_palette(tokens))

    app.setStyleSheet(build_qss(tokens))


def current_tokens() -> dict:
    """今のテーマの配色トークン。apply_theme() の前なら LIGHT_TOKENS。"""
    return _current_tokens or LIGHT_TOKENS


def current_theme_color() -> str:
    """今当てているテーマカラー(利用者が選んだ色。補正の前)。"""
    return _current_theme_color


def current_accent_soft_qcolor() -> QColor:
    """選択の背景(accent_soft)を QColor で返す。"""
    return _token_qcolor((_current_tokens or LIGHT_TOKENS)["accent_soft"])


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


def install_rounded_combo_popups():
    """コンボの一覧を、角丸の箱と余白のある行で出す(QSS の QComboBox QAbstractItemView)。

    角の外を透かすには一覧の窓を初めて出す前に半透明にする必要があり、行に QSS を効かせるには Fusion の
    メニュー風のデリゲートを替える必要がある。どちらもコンボごとなので、開くときに1回だけ行う。
    """
    global _original_show_combo_popup
    if _original_show_combo_popup is not None:
        return
    _original_show_combo_popup = QComboBox.showPopup

    def _show_popup(self):
        container = self.view().window()
        if not container.property("roundedPopup"):
            container.setProperty("roundedPopup", True)
            container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            # 窓の影は四角いので、角丸の外に影の角が出ないよう消す
            container.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
            # Windows では枠なしの印が無いと、半透明にしても角の外が四角く塗られる
            container.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            # Qt の内部のメニュー風デリゲート(Python からは基底の型に見える)のときだけ替える。
            # プラグインなどが付けたデリゲートは残す
            if type(self.itemDelegate()) is QAbstractItemDelegate:
                self.setItemDelegate(QStyledItemDelegate(self))
        # 外側の器の四角い枠(スタイルが替わると付け直されるので、開くたびに外す)
        container.setFrameShape(QFrame.Shape.NoFrame)
        _original_show_combo_popup(self)

    QComboBox.showPopup = _show_popup


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
