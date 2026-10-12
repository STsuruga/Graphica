"""上部バー・帯のアイコン。色はテーマのトークンで焼き込むので、テーマを替えたら作り直す(refresh_*)。"""
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

from graphica.gui import theme
from graphica.gui.icon_utils import icon


def themed_icon(name, size=18, token="text_secondary"):
    return icon(name, color=theme.current_tokens()[token], size=size)


def checkable_icon(name, size=20, off_token="text_secondary", on_token="on_accent"):
    """押していないときと押したとき(強調の色で塗った上)で色を変えるアイコン。"""
    tokens = theme.current_tokens()
    result = QIcon()
    for state, token in ((QIcon.State.Off, off_token), (QIcon.State.On, on_token)):
        pixmap = icon(name, color=tokens[token], size=size).pixmap(QSize(size, size))
        result.addPixmap(pixmap, QIcon.Mode.Normal, state)
    return result
