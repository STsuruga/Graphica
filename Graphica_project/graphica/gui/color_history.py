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

from graphica.gui import app_settings

MAX_RECENT_COLORS = 16


def load_recent_colors_into_picker(settings):
    """起動時に一度呼び、QSettingsに保存された「最近使った色」をカスタムカラー欄に復元する。"""
    colors = app_settings.as_list(app_settings.RECENT_COLORS.read(settings))
    if not colors:
        return
    for i, color_name in enumerate(colors[:MAX_RECENT_COLORS]):
        QColorDialog.setCustomColor(i, QColor(color_name))


def ask_color(parent=None, initial=None, title=""):
    """色を選ばせる。無効な QColor ならキャンセル。

    どの OS でも Qt のダイアログを使う。macOS の OS の色パネルにはカスタムカラー欄が無く、「最近使った色」が出ない。
    """
    return QColorDialog.getColor(initial if initial is not None else QColor("white"), parent, title,
                                 QColorDialog.ColorDialogOption.DontUseNativeDialog)


def get_color_with_history(settings, parent=None, initial=None):
    """
    QColorDialog.getColor() のラッパー。選択(Cancel以外)された色を
    「最近使った色」の先頭に記録し、QSettingsへ永続化する。
    """
    color = ask_color(parent, initial)

    if color.isValid():
        color_name = color.name()
        colors = [c for c in app_settings.as_list(app_settings.RECENT_COLORS.read(settings)) if c != color_name]
        colors.insert(0, color_name)
        colors = colors[:MAX_RECENT_COLORS]
        app_settings.RECENT_COLORS.write(settings, colors)
        for i, c in enumerate(colors):
            QColorDialog.setCustomColor(i, QColor(c))

    return color
