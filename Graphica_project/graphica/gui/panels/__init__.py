"""画面の欄をまとめる部品(gui/panels/*.py)と、PlotterApp に部品の名前を出す窓口。

欄のウィジェットと状態はタブが持ち、部品は欄の読み書き・処理・信号の配線を持つ。PlotterApp は各部品の EXPOSED_NAMES を
同じ名前の属性として出し、読み書きを部品へ回す(テスト・メニュー・ほかの部品が今までの名前で使うため。monkeypatch も部品に届く)。
"""
from graphica.gui.panels.axis_settings import AxisSettingsPanel
from graphica.gui.panels.dataset_tree import DatasetTreePanel

__all__ = ["PANEL_CLASSES", "create_panels", "expose_panel_names"]

PANEL_CLASSES = {
    "axis_settings": AxisSettingsPanel,
    "dataset_tree": DatasetTreePanel,
}


def create_panels(app):
    return {key: panel_class(app) for key, panel_class in PANEL_CLASSES.items()}


class _PanelName:
    """PlotterApp の属性として、部品の同じ名前の属性を読み書きする。"""

    def __init__(self, panel_key, name):
        self._panel_key = panel_key
        self._name = name

    def __get__(self, app, owner=None):
        if app is None:
            # クラスから引いたとき(メニューの表の検査など)は、部品のクラスの同じ名前を返す
            return getattr(PANEL_CLASSES[self._panel_key], self._name, self)
        return getattr(app.panels[self._panel_key], self._name)

    def __set__(self, app, value):
        setattr(app.panels[self._panel_key], self._name, value)


def expose_panel_names(app_class):
    for key, panel_class in PANEL_CLASSES.items():
        for name in panel_class.EXPOSED_NAMES:
            if any(name in klass.__dict__ for klass in app_class.__mro__):
                raise TypeError(f"{app_class.__name__}.{name} は部品 {key} の名前とぶつかる")
            setattr(app_class, name, _PanelName(key, name))
