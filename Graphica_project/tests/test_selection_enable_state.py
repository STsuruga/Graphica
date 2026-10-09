"""選択に合わせたボタンの有効/無効が、選び直したときに必ず決め直されること。

データセットを削除したあと、Qt は隣の項目を「今の項目」にするが選ばない。その項目をクリックしても今の項目は
変わらず currentItemChanged が出ないので、削除・複製・編集のボタンが無効のまま残っていた(もう一度別の項目を
選ぶまで直らなかった)。
"""
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import graphica.gui.app_settings as app_settings_module
from graphica.core.dataset import Dataset
from graphica.gui.dialogs import ColorPaletteDialog, NamedColorManagerDialog
from graphica.gui.main_window import PlotterApp


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    w.show()
    QApplication.instance().processEvents()
    yield w
    w.close()


def _add(window, name):
    ds = Dataset(name=name, df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y")
    window._add_dataset(ds, None)
    return ds


def _buttons(window):
    return [window.ui.remove_dataset_button, window.duplicate_dataset_button, window.view_edit_data_button,
            window.auto_color_button, window.fit_curve_button, window.find_peaks_button]


def _tree(window):
    return window.ui.dataset_list_widget


def test_clicking_the_item_left_current_after_a_delete_enables_the_buttons(window):
    _add(window, "a")
    second = _add(window, "b")
    _add(window, "c")
    tree = _tree(window)
    tree.setCurrentItem(window._get_dataset_tree_item(second))
    window._on_remove_dataset()
    leftover = tree.currentItem()
    assert leftover is not None and not tree.selectedItems()
    assert not any(b.isEnabled() for b in _buttons(window))

    # 今の項目のままの項目をクリックする(今の項目は変わらず、選択だけが変わる)
    tree.setCurrentItem(leftover)

    assert tree.selectedItems() == [leftover]
    assert all(b.isEnabled() for b in _buttons(window))
    assert window.ui.legend_name_edit.text() == leftover.data(0, 0x0100).name


def test_clearing_the_selection_disables_the_buttons(window):
    ds = _add(window, "a")
    tree = _tree(window)
    tree.setCurrentItem(window._get_dataset_tree_item(ds))
    assert window.ui.remove_dataset_button.isEnabled()

    tree.clearSelection()

    assert not window.ui.remove_dataset_button.isEnabled()


def test_one_click_notifies_plugins_of_the_selection_once(window, monkeypatch):
    first = _add(window, "a")
    _add(window, "b")
    calls = []
    monkeypatch.setattr(window, "_notify_plugins_selection_changed", lambda: calls.append(1))

    _tree(window).setCurrentItem(window._get_dataset_tree_item(first))

    assert calls == [1]


# --- フィットのボタン ---

class _RunningFit:
    """計算中のフィットの代わり(fit_runner に置く)。"""

    def wait(self):
        pass

    def deleteLater(self):
        pass


def test_selecting_during_a_fit_keeps_the_fit_button_off(window):
    first, second = _add(window, "a"), _add(window, "b")
    tree = _tree(window)
    tree.setCurrentItem(window._get_dataset_tree_item(first))
    window.fitting.fit_runner = _RunningFit()
    window.fit_curve_button.setEnabled(False)

    try:
        tree.setCurrentItem(window._get_dataset_tree_item(second))

        assert not window.fit_curve_button.isEnabled()
        assert window.find_peaks_button.isEnabled()
    finally:
        window.fitting.fit_runner = None  # 閉じるときの後片付けが本物のフィットとして扱わないように


def test_a_finished_fit_does_not_turn_the_button_on_without_a_selection(window):
    ds = _add(window, "a")
    tree = _tree(window)
    tree.setCurrentItem(window._get_dataset_tree_item(ds))
    window.dataset_host.set_fit_button_enabled(False)
    tree.clearSelection()

    window.dataset_host.set_fit_button_enabled(True)

    assert not window.fit_curve_button.isEnabled()


def test_a_finished_fit_turns_the_button_back_on_with_a_selection(window):
    ds = _add(window, "a")
    _tree(window).setCurrentItem(window._get_dataset_tree_item(ds))
    window.dataset_host.set_fit_button_enabled(False)

    window.dataset_host.set_fit_button_enabled(True)

    assert window.fit_curve_button.isEnabled()


# --- 配色パレットの「選択した色を削除」 ---

def test_remove_color_needs_a_selected_color(qapp):
    dialog = ColorPaletteDialog({"自作": ["#000000", "#ffffff"]}, "自作")
    dialog.color_list.setCurrentRow(-1)
    assert not dialog.remove_color_button.isEnabled()

    dialog.color_list.setCurrentRow(1)
    assert dialog.remove_color_button.isEnabled()

    dialog._on_remove_color()  # 一覧を作り直すと何も選ばれていない
    assert not dialog.remove_color_button.isEnabled()


def test_builtin_palettes_still_cannot_remove_colors(qapp):
    from graphica.core.color_palettes import BUILTIN_PALETTES
    name = sorted(BUILTIN_PALETTES)[0]
    dialog = ColorPaletteDialog({}, name)
    dialog.color_list.setCurrentRow(0)
    assert not dialog.remove_color_button.isEnabled()


# --- 色の名前の管理 ---

@pytest.fixture
def named_colors_dialog(tmp_path):
    from graphica.core.named_colors import save_named_colors
    settings = QSettings(str(tmp_path / "named.ini"), QSettings.Format.IniFormat)
    save_named_colors(settings, [{"name": "a", "color": "#000000"}, {"name": "b", "color": "#111111"},
                                 {"name": "c", "color": "#222222"}])
    return NamedColorManagerDialog(settings)


def _states(dialog):
    return [b.isEnabled() for b in (dialog.edit_button, dialog.delete_button, dialog.up_button, dialog.down_button)]


def test_named_color_buttons_follow_the_selected_entry(named_colors_dialog):
    dialog = named_colors_dialog
    assert _states(dialog) == [False, False, False, False]
    assert dialog.add_button.isEnabled()

    dialog.color_list.setCurrentRow(0)
    assert _states(dialog) == [True, True, False, True]

    dialog.color_list.setCurrentRow(1)
    assert _states(dialog) == [True, True, True, True]

    dialog.color_list.setCurrentRow(2)
    assert _states(dialog) == [True, True, True, False]


def test_moving_to_the_top_turns_up_off(named_colors_dialog):
    dialog = named_colors_dialog
    dialog.color_list.setCurrentRow(1)

    dialog._on_move(-1)

    assert dialog.color_list.currentRow() == 0
    assert _states(dialog) == [True, True, False, True]
