"""GUI 刷新の見た目の部品。値の持ち主は今の部品(コンボ・チェックボックス・スピンボックス)のままにして同期する。"""
from graphica.gui.widgets.cards import SectionHeader, StatCard
from graphica.gui.widgets.color_chips import ColorChip, ColorChipRow
from graphica.gui.widgets.segmented import LINE_STYLE_PENS, ComboMirror, SegmentedControl
from graphica.gui.widgets.slider_spin import SliderSpin
from graphica.gui.widgets.type_tiles import GLYPHS, TypeTileGroup

__all__ = [
    "ColorChip", "ColorChipRow", "ComboMirror", "GLYPHS", "LINE_STYLE_PENS", "SectionHeader",
    "SegmentedControl", "SliderSpin", "StatCard", "TypeTileGroup",
]
