# gui/theme.py
"""
アプリ全体 (Qt UI) のダークモード切り替え、およびフラット/ミニマルな
見た目 (QSS) の適用を担当するモジュール。
ベースは QPalette + Fusion スタイルの標準的な手法だが、それに加えて
QSS (Qtスタイルシート) でツールバー・ボタン・入力欄・リスト等の見た目を
角丸/フラットに統一し、よりモダンな印象にしている。
"""
import os
import tempfile

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QProxyStyle, QStyle, QStyleFactory

from gui.icon_utils import icon as _svg_icon

# 起動時の元のパレット/スタイル名を保持し、ライトモードへの復帰に使う
_original_palette = None
_original_style_name = None
_wheel_value_change_disabled = False
_current_proxy_style = None  # QApplication.setStyle()に渡したオブジェクトへの参照を保持

# スピンボックスの上下矢印アイコンのキャッシュ先。
# ★ QSpinBox::up-button/down-buttonにQSSで何かプロパティを指定すると
#   ウィジェット自体もQSSで角丸枠にしている都合上(QLineEdit等と共有の
#   入力欄スタイル)、Qtの内部実装(QStyleSheetStyle)がCC_SpinBoxの描画を
#   丸ごと引き取ってしまい、QProxyStyle側でdrawPrimitive/drawComplexControlを
#   オーバーライドしても矢印の描画に一貫して反映されないことを検証の上で確認した
#   (呼ばれたり呼ばれなかったりする再現性の低い挙動だった)。
#   一方 QSS の `::up-arrow`/`::down-arrow` に `image: url(...)` で
#   実ファイルの矢印画像を指定する方式は確実に反映される。このため、
#   矢印だけは小さなPNGとして生成しキャッシュし、QSSから参照する。
_ARROW_ICON_CACHE_DIR = os.path.join(tempfile.gettempdir(), "graphica_theme_icons")


def _spinbox_arrow_icon_url(direction: str, color: str) -> str:
    """
    上向き/下向きの三角矢印PNGを(未生成なら)描画してキャッシュし、
    QSSの `url(...)` にそのまま埋め込める形式のパス文字列を返す。
    """
    os.makedirs(_ARROW_ICON_CACHE_DIR, exist_ok=True)
    safe_color = color.lstrip("#")
    filename = f"spin_arrow_{direction}_{safe_color}.png"
    path = os.path.join(_ARROW_ICON_CACHE_DIR, filename)

    if not os.path.exists(path):
        size = 12
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))

        cx, cy = size / 2, size / 2
        aw, ah = 3.5, 2.6
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

    # QSSのurl()はWindowsの円記号区切りパスを解釈できないため、
    # スラッシュ区切りに変換する。
    return path.replace(os.sep, "/")

# フラット/ミニマルテーマの配色トークン。
# チェックリスト(ロードマップ)アーティファクトで使ったものと近い、
# ニュートラルグレー+ティール系アクセントの配色に揃えている。
_LIGHT_TOKENS = {
    "bg": "#F7F7F5", "surface": "#FFFFFF", "surface_2": "#EFF1EF",
    "border": "#DFE2E1", "border_strong": "#C9CDCB",
    "text_primary": "#1B1F1E", "text_secondary": "#5B6462", "text_muted": "#8B938F",
    "accent": "#1F6F78", "accent_soft": "#E4F0EF", "accent_text": "#FFFFFF",
}
_DARK_TOKENS = {
    "bg": "#14171A", "surface": "#1B1F22", "surface_2": "#21262A",
    "border": "#2C3236", "border_strong": "#3A4147",
    "text_primary": "#EDEFEF", "text_secondary": "#A6AEB2", "text_muted": "#6E777B",
    "accent": "#5FB6BE", "accent_soft": "rgba(95, 182, 190, 0.16)", "accent_text": "#0E1113",
}

_FLAT_QSS_TEMPLATE = """
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {text_primary};
    selection-background-color: {accent};
    selection-color: {accent_text};
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
    color: {accent};
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
    color: {accent};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 8px;
}}

/* --- 操作ボタン行のグループ区切り(項目70) --- */
QFrame#button_row_separator {{
    background: {border};
    max-width: 1px;
    border: none;
    margin: 2px 4px;
}}

/* --- データセットリスト直下のミニ統計(項目69) --- */
QLabel#dataset_mini_stats_label {{
    color: {text_muted};
    font-size: 11.5px;
    padding: 2px 4px;
}}

/* --- キャンバス周り(項目72): プロット領域を1枚のカードとして視覚的に区切る --- */
QWidget#plot_container {{
    background: {surface};
    border: 1px solid {border};
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
QToolButton:pressed, QToolButton:checked {{
    background: {accent_soft};
}}
QToolButton:checked {{
    border: 1px solid {accent};
}}
QStatusBar {{
    background: {surface};
    border-top: 1px solid {border};
}}
QDockWidget::title {{
    background: {surface_2};
    padding: 6px 8px;
    border-bottom: 1px solid {border};
    font-weight: 600;
    letter-spacing: .01em;
}}

/* --- スプリッター(ドック/パネルの境界): 既定のOSハンドルはフラットテーマと
   馴染まないため、細く控えめなハンドルに置き換え、ホバー時のみアクセント色で
   「動かせる」ことを示す(GUI洗練) --- */
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
    top: -6px;
    padding: 2px 8px;
    color: {accent};
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: .02em;
    background: {accent_soft};
    border-radius: 5px;
}}

/* --- ドック内のグループボックスは二重の箱にしない(GUI洗練) ---
   QDockWidget自体がすでに1枚のカードとして枠を持っているため、その中の
   グループボックスにも同じ枠+色付きチップの見出しを重ねると、箱の中に
   箱が入れ子になって窮屈に見える。ドック内では枠を取り払い、見出しは
   控えめなラベルのみにする(モーダルダイアログ側のグループボックスは
   従来どおりのチップ付きスタイルを維持) */
QDockWidget QGroupBox {{
    border: none;
    border-radius: 0;
    margin-top: 18px;
    padding-top: 6px;
}}
QDockWidget QGroupBox::title {{
    left: 0;
    top: -4px;
    padding: 0;
    color: {text_secondary};
    background: transparent;
    border-radius: 0;
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
    background: {accent};
    border-color: {accent};
    color: {accent_text};
}}
QPushButton:focus, QToolButton:focus {{
    border: 1px solid {accent};
}}

/* --- アイコンのみの正方形ボタン(データセット操作ボタン行、GUI洗練) ---
   テキストラベルを持たず、ツールチップで用途を示す。9個並んでも横幅を
   取らないよう正方形に固定する(実際のサイズ指定はPython側setFixedSize) */
QPushButton[iconOnly="true"] {{
    padding: 4px;
}}

/* --- 入力欄 --- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {accent};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {text_muted};
    background: {surface_2};
}}

/* --- スピンボックスの上下ボタン(GUI洗練) ---
   ボックス自体(背景・区切り線)はQSSで問題なくスタイルできるが、矢印
   (::up-arrow/::down-arrow)は `width`/`height` の指定だけでも描画されなく
   なることを確認した(QLineEdit等と共有の角丸入力欄スタイルがQSpinBox
   自体にも掛かっているため、Qt内部でCC_SpinBoxの描画がQStyleSheetStyleに
   丸ごと引き取られ、QProxyStyle側のdrawPrimitive/drawComplexControlの
   オーバーライドが安定して反映されないことを検証済み)。矢印だけは実際の
   画像ファイル(image: url(...))として与えることで確実に表示される。 */
QSpinBox, QDoubleSpinBox {{
    padding-right: 16px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    height: 12px;
    border: none;
    border-left: 1px solid {border};
    background: {surface_2};
    border-top-right-radius: 5px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    height: 12px;
    border: none;
    border-left: 1px solid {border};
    border-top: 1px solid {border};
    background: {surface_2};
    border-bottom-right-radius: 5px;
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
    width: 10px;
    height: 10px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({spin_down_arrow_url});
    width: 10px;
    height: 10px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    /* スピンボックスと同じ理由(QSSでwidth/heightを指定するだけで矢印自体が
       描画されなくなる)により、画像として与える */
    image: url({spin_down_arrow_url});
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background: {surface};
    border: 1px solid {border};
    selection-background-color: {accent_soft};
    selection-color: {accent};
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
    background: {accent_soft};
    color: {text_primary};
}}
QTreeWidget::item, QListWidget::item {{
    padding: 5px 4px;
    border-radius: 5px;
}}

/* --- データセットリストは選択状態がひと目でわかるよう、はっきりした
   アクセント色の塗りつぶしにする(他の淡いリスト/テーブルの選択色とは
   意図的に差をつける) --- */
QTreeWidget#dataset_list_widget::item:selected {{
    background: {accent};
    color: {accent_text};
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
    border-bottom: 2px solid {accent};
    color: {accent};
    font-weight: 600;
}}
/* ★ QTabBar::close-button に何かひとつでもプロパティを指定すると(paddingや
   border-radiusだけでも)、Qtがこのサブコントロールを「スタイルシートで
   カスタム描画される」ものとみなし、アイコン自体が一切描画されなくなる
   (QProxyStyleでstandardIcon/standardPixmapを差し替えても効果が無い)。
   そのため、閉じるボタンにはQSSを一切当てず、アイコンの見た目は
   _TabCloseIconStyle (QProxyStyle) 側だけで制御する。 */

QToolButton#add_tab_button {{
    margin: 3px 6px 3px 2px;
    border-radius: 13px;
    padding: 5px;
}}
QToolButton#add_tab_button:hover {{
    background: {accent_soft};
}}

/* --- チェックボックス / ラジオボタン ---
   ★ QCheckBox::indicator はQSSで何もスタイルしない。タブの閉じるボタンと
   同様に、サブコントロールにQSSで何かひとつでもプロパティ(width/height/
   border等)を指定すると、Qtがチェックマーク自体を描画しなくなり、
   ただの塗りつぶし四角になってしまう(実際にこれで報告された)。
   見た目(枠・塗りつぶし・チェックマーク)はすべて _FlatThemeProxyStyle の
   drawPrimitive(PE_IndicatorCheckBox) で自前描画する。 */
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border_strong};
    border-radius: 7px;
    background: {surface};
}}
QRadioButton::indicator:checked {{
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
QScrollBar::handle:vertical:hover {{
    background: {accent};
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
QScrollBar::handle:horizontal:hover {{
    background: {accent};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""


def _build_flat_qss(dark: bool) -> str:
    tokens = _DARK_TOKENS if dark else _LIGHT_TOKENS
    format_args = dict(tokens)
    format_args["spin_up_arrow_url"] = _spinbox_arrow_icon_url("up", tokens["text_primary"])
    format_args["spin_down_arrow_url"] = _spinbox_arrow_icon_url("down", tokens["text_primary"])
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
    """
    QSSだけでは実現できない(あるいはQtの既知の癖により逆に壊れる)、いくつかの
    描画をQProxyStyle側で肩代わりするための共通スタイル。

    ★ 共通する根本原因: Qtは、あるサブコントロールにQSSで何かひとつでも
    プロパティ(padding, border-radius, width...)を指定すると、そのサブ
    コントロールを「スタイルシートでカスタム描画されるもの」とみなし、
    アイコンやチェックマークなどの「中身」を一切描画しなくなることがある。
    - タブを閉じる「×」ボタン: QTabBar::close-buttonにQSSを当てると、
      アイコン自体が完全に消える(実機で報告され、調査の上で発見)。
      → QSSは一切当てず、標準アイコンをここで差し替える。
    - チェックボックス: QCheckBox::indicatorにQSSを当てると、チェック時に
      ただの塗りつぶし四角になり、チェックマークが描画されない
      (同じく実機で報告)。
      → QSSは一切当てず、枠・塗りつぶし・チェックマークをすべてここで
      自前描画する。
    """
    def __init__(self, base_style, tokens):
        super().__init__(base_style)
        self._tokens = tokens
        self._close_icon = _svg_icon("x", color=tokens["text_secondary"], size=14)
        self._close_pixmap = self._close_icon.pixmap(14, 14)

    def standardIcon(self, standard_icon, option=None, widget=None):
        if standard_icon == QStyle.StandardPixmap.SP_TabCloseButton:
            return self._close_icon
        return super().standardIcon(standard_icon, option, widget)

    def standardPixmap(self, standard_pixmap, option=None, widget=None):
        # ★ Qt内部のタブ「閉じる」ボタン(private CloseButton)は、実際には
        #   standardIcon()ではなくこちらのstandardPixmap()経由でアイコンを
        #   取得している。standardIcon()だけをオーバーライドしても効果が
        #   無かったため、両方をオーバーライドする必要がある。
        if standard_pixmap == QStyle.StandardPixmap.SP_TabCloseButton:
            return self._close_pixmap
        return super().standardPixmap(standard_pixmap, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            self._draw_checkbox_indicator(option, painter)
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
                # 部分選択状態: 横棒のみ
                path.moveTo(r.x() + r.width() * 0.22, r.y() + r.height() * 0.5)
                path.lineTo(r.x() + r.width() * 0.78, r.y() + r.height() * 0.5)
            else:
                # チェックマーク(レ点)
                path.moveTo(r.x() + r.width() * 0.20, r.y() + r.height() * 0.52)
                path.lineTo(r.x() + r.width() * 0.42, r.y() + r.height() * 0.74)
                path.lineTo(r.x() + r.width() * 0.82, r.y() + r.height() * 0.26)
            painter.drawPath(path)

        painter.restore()


def apply_theme(app, dark: bool):
    """
    QApplication 全体にダーク/ライトのテーマを適用する。

    ライト/ダークどちらのときも常に Fusion スタイルを使い、パレット(色)だけを
    切り替える。スタイル自体をネイティブ⇔Fusionで切り替えると、ツールバーの
    ボタンサイズや余白などQStyle依存の見た目がモードごとに変わってしまうため、
    スタイルは固定してモード間の見た目の一貫性を保つ。
    """
    global _original_palette, _original_style_name, _current_proxy_style
    if _original_palette is None:
        _original_palette = QPalette(app.palette())
        _original_style_name = app.style().objectName()

    tokens = _DARK_TOKENS if dark else _LIGHT_TOKENS
    base_style = QStyleFactory.create('Fusion')
    _current_proxy_style = _FlatThemeProxyStyle(base_style, tokens)
    app.setStyle(_current_proxy_style)
    if dark:
        app.setPalette(_build_dark_palette())
    else:
        app.setPalette(_original_palette)

    # パレットに加えて QSS を適用し、ツールバー/ボタン/入力欄/リスト等を
    # 角丸・フラットな見た目に統一する(モダンなミニマルテーマ)。
    app.setStyleSheet(_build_flat_qss(dark))


def disable_scroll_value_change():
    """
    QSpinBox/QDoubleSpinBox/QComboBoxは既定でマウスホイールで値が変わり、
    スクロール可能なドック/ダイアログの中でスクロールしようとしただけで
    意図せず値が変わる事故が起きやすい。

    ★ 当初は「フォーカスが無い間だけ無視する」という条件付きの実装を
    試したが、実際には効果がなかった: QAbstractSpinBoxの既定のフォーカス
    ポリシーは Qt.FocusPolicy.WheelFocus であり、フォームを開いた直後は
    フォーカス可能な最初のウィジェットに自動的にフォーカスが当たる上、
    一度どれかのフィールドにフォーカスが移ると、ユーザーがマウスを別の
    フィールドへ動かして単にスクロールしただけでは、フォーカス自体は
    そのフィールドに残ったままになる。つまり「マウスカーソルが今どこに
    あるか」と「hasFocus()が真かどうか」は一致しないため、フォーカスの
    有無では判定できない。そのため、ホイールによる値変更は常に無効化する
    (値の変更は上下矢印ボタン、またはキーボード入力/フォーカス後の
    キー操作で行う)。

    ホイールイベントを event.ignore() で無視すると (accept() せず、独自の
    処理も行わないと)、Qtはそのイベントを親ウィジェットへ伝播させるため、
    スピンボックスの上でマウスホイールを回してもスクロールエリア自体は
    問題なくスクロールできる。

    クラスのメソッドを直接書き換えるため、アプリ起動時に一度だけ呼び出す
    (QApplication生成後、最初のウィジェットが作られる前が望ましい)。
    """
    global _wheel_value_change_disabled
    if _wheel_value_change_disabled:
        return
    _wheel_value_change_disabled = True

    def _ignore_wheel_event(self, event):
        event.ignore()

    QAbstractSpinBox.wheelEvent = _ignore_wheel_event
    QComboBox.wheelEvent = _ignore_wheel_event
