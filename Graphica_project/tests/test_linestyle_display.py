# tests/test_linestyle_display.py
"""
線種の表示(v1.4.2)。

フィット曲線は linestyle='--' で作られ破線で描かれるのに、プロパティパネルの
「線の種類」には直前のデータセットの表示(多くは solid)が残っていた。コンボの
項目は 'solid'/'dashed'/... の表示名で、記号の '--' と一致しなかったため。
データセットリストのアイコンは逆に記号しか知らず、パネルで 'dashed' を選んだ
データセットが実線のアイコンになっていた。
"""
import pandas as pd
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

import graphica.gui.main_window as main_window_module
from graphica.core.dataset import Dataset, LINESTYLE_NAMES, linestyle_name
from graphica.gui.dataset_style_icon import _LINESTYLE_TO_QT_PEN
from graphica.gui.main_window import PlotterApp


@pytest.mark.parametrize("value, name", [
    ("-", "solid"), ("solid", "solid"),
    ("--", "dashed"), ("dashed", "dashed"),
    (":", "dotted"), ("dotted", "dotted"),
    ("-.", "dashdot"), ("dashdot", "dashdot"),
    ("Dashed", "dashed"),
    ("None", None), ("", None), (None, None), ("unknown", None),
])
def test_linestyle_name_normalizes_symbols_and_names(value, name):
    assert linestyle_name(value) == name


def test_every_combo_name_has_an_icon_pen_style():
    assert set(_LINESTYLE_TO_QT_PEN) == set(LINESTYLE_NAMES)


@pytest.mark.parametrize("value, pen", [
    ("--", Qt.PenStyle.DashLine), ("dashed", Qt.PenStyle.DashLine),
    (":", Qt.PenStyle.DotLine), ("dotted", Qt.PenStyle.DotLine),
])
def test_icon_pen_style_accepts_both_spellings(value, pen):
    assert _LINESTYLE_TO_QT_PEN[linestyle_name(value)] == pen


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.instance().processEvents()
    yield w
    w.close()


def _select(window, index):
    tree = window.ui.dataset_list_widget
    item = tree.topLevelItem(index)
    tree.clearSelection()
    item.setSelected(True)
    tree.setCurrentItem(item)
    QApplication.instance().processEvents()


def _dataset(name, linestyle):
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [1.0, 4.0, 9.0]})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y", linestyle=linestyle)


def test_fit_curve_style_shows_dashed_after_a_solid_dataset(window):
    window._add_dataset_with_undo(_dataset("data", "-"))
    window._add_dataset_with_undo(_dataset("Fit (data)", "--"))
    _select(window, 0)
    assert window.ui.linestyle_combo.currentText() == "solid"
    _select(window, 1)
    assert window.ui.linestyle_combo.currentText() == "dashed"


def test_symbol_and_name_spellings_show_the_same_item(window):
    window._add_dataset_with_undo(_dataset("a", ":"))
    window._add_dataset_with_undo(_dataset("b", "dotted"))
    _select(window, 0)
    first = window.ui.linestyle_combo.currentText()
    _select(window, 1)
    assert first == window.ui.linestyle_combo.currentText() == "dotted"


def test_no_line_value_clears_the_selection_instead_of_keeping_the_previous_one(window):
    window._add_dataset_with_undo(_dataset("data", "--"))
    window._add_dataset_with_undo(_dataset("peaks", "None"))
    _select(window, 0)
    _select(window, 1)
    assert window.ui.linestyle_combo.currentIndex() == -1


def test_showing_the_value_does_not_rewrite_the_stored_linestyle(window):
    ds = _dataset("Fit (data)", "--")
    window._add_dataset_with_undo(ds)
    _select(window, 0)
    assert ds.linestyle == "--"
    assert window.undo_stack.count() == 1  # 追加の1件だけ(表示で変更コマンドが積まれない)
