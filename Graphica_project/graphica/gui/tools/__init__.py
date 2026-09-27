"""マウスの 7 つのモードのツール(gui/tools/*.py)と、PlotterApp にツールの名前を出す窓口。

ツールは状態を自分で持つ。PlotterApp は各ツールの EXPOSED_NAMES を同じ名前の属性として出し、読み書きをツールへ回す
(テスト・メニュー・ほかの mixin が今までの名前で使うため。monkeypatch もツールに届く)。
"""
from graphica.gui.tools.annotation import AnnotationTool
from graphica.gui.tools.cursor import CursorTool
from graphica.gui.tools.layout_edit import LayoutEditTool
from graphica.gui.tools.manager import MOUSE_MODES, MOUSE_MODES_BY_NAME, MouseMode, ToolManager
from graphica.gui.tools.peak_placement import PeakPlacementTool
from graphica.gui.tools.range_select import RangeSelectTool
from graphica.gui.tools.region_highlight import RegionHighlightTool
from graphica.gui.tools.slice_extraction import SliceExtractionTool

__all__ = ["MOUSE_MODES", "MOUSE_MODES_BY_NAME", "MouseMode", "ToolManager", "TOOL_CLASSES", "create_tools",
           "expose_tool_names"]

# キーは MOUSE_MODES の name と同じ
TOOL_CLASSES = {
    "cursor": CursorTool,
    "annotation": AnnotationTool,
    "layout_edit": LayoutEditTool,
    "range_select": RangeSelectTool,
    "peak_placement": PeakPlacementTool,
    "slice_extraction": SliceExtractionTool,
    "region_highlight": RegionHighlightTool,
}


def create_tools(app):
    return {key: tool_class(app) for key, tool_class in TOOL_CLASSES.items()}


class _ToolName:
    """PlotterApp の属性として、ツールの同じ名前の属性を読み書きする。"""

    def __init__(self, tool_key, name):
        self._tool_key = tool_key
        self._name = name

    def __get__(self, app, owner=None):
        if app is None:
            # クラスから引いたとき(メニューの表の検査など)は、ツールのクラスの同じ名前を返す
            return getattr(TOOL_CLASSES[self._tool_key], self._name, self)
        return getattr(app.mouse_tools[self._tool_key], self._name)

    def __set__(self, app, value):
        setattr(app.mouse_tools[self._tool_key], self._name, value)


def expose_tool_names(app_class):
    for key, tool_class in TOOL_CLASSES.items():
        for name in tool_class.EXPOSED_NAMES:
            if any(name in klass.__dict__ for klass in app_class.__mro__):
                raise TypeError(f"{app_class.__name__}.{name} はツール {key} の名前とぶつかる")
            setattr(app_class, name, _ToolName(key, name))
