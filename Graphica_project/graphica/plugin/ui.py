"""
プラグインのパネル(register_panel)を本体と同じ形にする部品(プラグイン API 2.2)。

パネルを作るところでだけ import すること(Qt の画面の部品を読み込むので、計算だけのテストでは読まない)。
見た目は本体のテーマに従い、明暗・テーマカラーを替えると一緒に替わる。本体の画面の作りが変わっても、
ここの名前と引数はプラグイン API の版で守る。
"""
from typing import Any

from PySide6.QtWidgets import QCheckBox, QFormLayout, QWidget

from graphica.gui import motion as _motion
from graphica.gui import theme as _theme
from graphica.gui.builders.property_sections import attach_header_switch as _attach_header_switch
from graphica.gui.builders.property_sections import build_section as _build_section
from graphica.gui.widgets.segmented import SegmentedControl

__all__ = ["SegmentedControl", "make_switch", "section", "show_toast", "theme_color"]

# theme_color() で読める色の名前
THEME_COLOR_NAMES = (
    "bg", "surface", "surface_2", "border", "border_strong", "text_primary", "text_secondary", "text_muted",
    "accent", "accent_fg", "on_accent", "success", "danger",
)


def section(title: str, opened: bool = True, switch: QCheckBox | None = None) -> tuple[QWidget, QFormLayout]:
    """見出しを押して開閉できる節。(節の部品, 中身のフォーム) を返す。

    Args:
        title: 見出しの文字。
        opened: 初めに開いておくか。
        switch: 見出しの右端に置く QCheckBox(機能のオン/オフ)。オフの間は中身を畳み、オンにすると開く。

    Returns:
        (節の部品, 中身の QFormLayout)。部品をパネルのレイアウトに足し、行はフォームに addRow する。
    """
    entry = _build_section(title, opened=opened)
    if switch is not None:
        _attach_header_switch(entry, switch)
    return entry['section'], entry['form']


def make_switch(checkbox: QCheckBox) -> QCheckBox:
    """QCheckBox をオン/オフのスイッチの見た目にする(値と toggled はそのまま)。渡したものを返す。"""
    return _theme.make_toggle_switch(checkbox)


def theme_color(name: str) -> str:
    """今のテーマの色(#RRGGBB か rgba(...))。自前で描く部品は、描くたびにこれで色を読む。

    Args:
        name: THEME_COLOR_NAMES のどれか(例: "accent"、"text_muted"、"surface")。

    Returns:
        色の文字列。QColor() にそのまま渡せる(rgba の色は QColor では読めないので、使うのは不透明の色だけにする)。
    """
    if name not in THEME_COLOR_NAMES:
        raise ValueError(f"知らない色の名前: {name!r}(使える名前: {', '.join(THEME_COLOR_NAMES)})")
    return str(_theme.current_tokens()[name])


def show_toast(widget: Any, text: str) -> None:
    """widget のウィンドウの右下に、短い知らせ(「書き出しました」など)を出して消す。"""
    _motion.toast(widget, text)
