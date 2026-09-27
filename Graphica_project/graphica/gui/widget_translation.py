"""組み立てた画面の文字を、あとからまとめて tr() で訳す(Designer の .ui で作った部品にも効かせるため)。

日本語のときは何もしない。選択肢(QComboBox)は文字そのものを値として保存するものがあるので、ここでは
番号やデータで値を持つと分かっているものだけを訳す(ほかは作る所で tr() を通す)。
"""
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QDockWidget, QGroupBox, QLabel, QLineEdit, QTabWidget,
                               QToolBar, QWidget)

from graphica.core.i18n import DEFAULT_LANGUAGE, get_language, tr

# 選んだ番号で値を持つ選択肢(gui/axis_bindings.py の index)。表示を訳しても保存する値は変わらない
INDEX_BOUND_COMBOS = ("x_major_tick_mode_combo", "y_major_tick_mode_combo")


def _translate(text):
    translated = tr(text)
    return translated if translated != text else None


def translate_widget_texts(root):
    if get_language() == DEFAULT_LANGUAGE:
        return
    for widget in [root] + root.findChildren(QWidget):
        tooltip = widget.toolTip()
        if tooltip and (new := _translate(tooltip)):
            widget.setToolTip(new)
        if isinstance(widget, (QLabel, QAbstractButton)):
            if (new := _translate(widget.text())):
                widget.setText(new)
        elif isinstance(widget, QGroupBox):
            if (new := _translate(widget.title())):
                widget.setTitle(new)
        elif isinstance(widget, (QDockWidget, QToolBar)):
            if (new := _translate(widget.windowTitle())):
                widget.setWindowTitle(new)
        elif isinstance(widget, QLineEdit):
            if widget.placeholderText() and (new := _translate(widget.placeholderText())):
                widget.setPlaceholderText(new)
        elif isinstance(widget, QComboBox) and widget.objectName() in INDEX_BOUND_COMBOS:
            for i in range(widget.count()):
                if (new := _translate(widget.itemText(i))):
                    widget.setItemText(i, new)
        if isinstance(widget, QTabWidget):
            for i in range(widget.count()):
                if (new := _translate(widget.tabText(i))):
                    widget.setTabText(i, new)
