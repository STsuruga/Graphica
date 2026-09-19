"""
graphica/gui/datasets/ の機能クラスに共通する約束事。

機能クラスは QWidget ではないので、ダイアログの親に self を渡すと Qt が TypeError を出す。
親には必ず self._host.parent_widget を渡す。
"""
import ast
import pathlib

import pandas as pd
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget

import graphica.gui.datasets as datasets_package
from graphica.core.dataset import Dataset
from graphica.gui.datasets import colors as colors_module
from graphica.gui.datasets import processing as processing_module
import graphica.gui.main_window as main_window_module
from graphica.gui.main_window import PlotterApp

DATASETS_DIR = pathlib.Path(datasets_package.__file__).parent
ALLOWED_SELF_CALLS = {"getattr", "setattr", "hasattr"}


def _calls_passing_bare_self(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in ALLOWED_SELF_CALLS:
            continue
        values = list(node.args) + [keyword.value for keyword in node.keywords]
        if any(isinstance(value, ast.Name) and value.id == "self" for value in values):
            found.append(f"{path.name}:{node.lineno}")
    return found


def test_controllers_never_pass_themselves_as_a_call_argument():
    offenders = [hit for path in sorted(DATASETS_DIR.glob("*.py")) for hit in _calls_passing_bare_self(path)]
    assert offenders == []


def _make_window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.processEvents()
    return window


def test_colormap_dialog_gets_the_window_as_parent(tmp_path, monkeypatch):
    window = _make_window(tmp_path, monkeypatch)
    df = pd.DataFrame({"x": [0, 1], "y": [1.0, 2.0]})
    for name in ("a", "b"):
        window._add_dataset(Dataset(name=name, df=df.copy(), x_col_name="x", y_col_name="y"), None, select=True)
    parents = []

    def fake_get_item(parent, *args, **kwargs):
        parents.append(parent)
        return "", False

    monkeypatch.setattr(colors_module.QInputDialog, "getItem", staticmethod(fake_get_item))
    window.ui.dataset_list_widget.selectAll()

    window.colors.auto_assign_colors_from_colormap()

    assert parents and isinstance(parents[0], QWidget)


def test_normalize_dialog_gets_the_window_as_parent(tmp_path, monkeypatch):
    window = _make_window(tmp_path, monkeypatch)
    df = pd.DataFrame({"x": [0, 1, 2], "y": [1.0, 2.0, 3.0]})
    window._add_dataset(Dataset(name="a", df=df, x_col_name="x", y_col_name="y"), None, select=True)
    parents = []

    class FakeDialog:
        def __init__(self, *args, parent=None, **kwargs):
            parents.append(parent)

        def exec(self):
            return 0

    monkeypatch.setattr(processing_module, "NormalizeDatasetDialog", FakeDialog)

    window.processing.normalize()

    assert parents and isinstance(parents[0], QWidget)
