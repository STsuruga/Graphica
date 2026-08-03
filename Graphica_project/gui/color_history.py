# gui/color_history.py
"""
QColorDialog で選択した色を「最近使った色」としてQSettingsに永続化し、
QColorDialogのカスタムカラー欄(プロセス内で共有される静的な状態)に
反映するためのヘルパー。

QColorDialog.setCustomColor() はダイアログのインスタンスではなく
Qt側の静的な状態を書き換えるため、一度読み込めばアプリ内のどの
QColorDialog.getColor() 呼び出しにも反映される。
"""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog

MAX_RECENT_COLORS = 16
_SETTINGS_KEY = "recent_colors"


def load_recent_colors_into_picker(settings):
    """起動時に一度呼び、QSettingsに保存された「最近使った色」をカスタムカラー欄に復元する。"""
    colors = settings.value(_SETTINGS_KEY, [])
    if not colors:
        return
    for i, color_name in enumerate(colors[:MAX_RECENT_COLORS]):
        QColorDialog.setCustomColor(i, QColor(color_name))


def get_color_with_history(settings, parent=None, initial=None):
    """
    QColorDialog.getColor() のラッパー。選択(Cancel以外)された色を
    「最近使った色」の先頭に記録し、QSettingsへ永続化する。
    """
    if initial is not None:
        color = QColorDialog.getColor(initial, parent)
    else:
        color = QColorDialog.getColor(parent=parent)

    if color.isValid():
        color_name = color.name()
        colors = [c for c in settings.value(_SETTINGS_KEY, []) if c != color_name]
        colors.insert(0, color_name)
        colors = colors[:MAX_RECENT_COLORS]
        settings.setValue(_SETTINGS_KEY, colors)
        for i, c in enumerate(colors):
            QColorDialog.setCustomColor(i, QColor(c))

    return color
