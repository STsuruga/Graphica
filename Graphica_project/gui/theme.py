# gui/theme.py
"""
アプリ全体 (Qt UI) のダークモード切り替え、およびフラット/ミニマルな
見た目 (QSS) の適用を担当するモジュール。
ベースは QPalette + Fusion スタイルの標準的な手法だが、それに加えて
QSS (Qtスタイルシート) でツールバー・ボタン・入力欄・リスト等の見た目を
角丸/フラットに統一し、よりモダンな印象にしている。
"""
from PySide6.QtGui import QColor, QPalette

# 起動時の元のパレット/スタイル名を保持し、ライトモードへの復帰に使う
_original_palette = None
_original_style_name = None

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
    border: none;
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
QComboBox::drop-down {{
    border: none;
    width: 20px;
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

/* --- タブ --- */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
}}
QTabBar::tab {{
    background: transparent;
    padding: 6px 14px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    border-bottom: 2px solid {accent};
    color: {accent};
}}

/* --- チェックボックス / ラジオボタン --- */
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border_strong};
    border-radius: 3px;
    background: {surface};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}
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
    return _FLAT_QSS_TEMPLATE.format(**tokens)


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


def apply_theme(app, dark: bool):
    """
    QApplication 全体にダーク/ライトのテーマを適用する。

    ライト/ダークどちらのときも常に Fusion スタイルを使い、パレット(色)だけを
    切り替える。スタイル自体をネイティブ⇔Fusionで切り替えると、ツールバーの
    ボタンサイズや余白などQStyle依存の見た目がモードごとに変わってしまうため、
    スタイルは固定してモード間の見た目の一貫性を保つ。
    """
    global _original_palette, _original_style_name
    if _original_palette is None:
        _original_palette = QPalette(app.palette())
        _original_style_name = app.style().objectName()

    app.setStyle('Fusion')
    if dark:
        app.setPalette(_build_dark_palette())
    else:
        app.setPalette(_original_palette)

    # パレットに加えて QSS を適用し、ツールバー/ボタン/入力欄/リスト等を
    # 角丸・フラットな見た目に統一する(モダンなミニマルテーマ)。
    app.setStyleSheet(_build_flat_qss(dark))
