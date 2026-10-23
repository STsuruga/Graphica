"""画面の短い動き(gui/motion.py)。テストの環境(offscreen)では止まっているので、ここでだけ動かして最後の形を確かめる。"""
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from graphica.gui import motion, ui_mode
from graphica.gui.builders.property_sections import build_section
from graphica.gui.widgets import SegmentedControl
from test_main_app_window import _make_isolated_main_app_window

WAIT_MS = max(motion.EXPAND_MS, motion.SLIDE_MS, motion.FADE_MS) + 150


@pytest.fixture
def moving(monkeypatch):
    monkeypatch.setattr(motion, "is_enabled", lambda: True)


def test_motion_is_off_without_a_screen(qapp):
    assert QApplication.instance().platformName() == "offscreen"
    assert not motion.is_enabled()


def test_without_motion_values_jump_to_the_end(qapp):
    seen, done = [], []
    motion.animate_value(qapp, "_test_motion", 0, 10, seen.append, lambda: done.append(True))
    assert seen == [10] and done == [True]


def test_a_section_grows_open_and_shrinks_closed(qapp, moving):
    entry = build_section("節", opened=False)
    entry['form'].addRow("名前", QLineEdit())
    section = entry['section']
    section.resize(300, 200)
    section.show()
    body = entry['body']
    assert body.isHidden()
    entry['toggle'].setChecked(True)
    assert not body.isHidden() and body.maximumHeight() < body.sizeHint().height()
    QTest.qWait(WAIT_MS)
    assert body.maximumHeight() == motion.UNBOUNDED_HEIGHT
    entry['toggle'].setChecked(False)
    assert not body.isHidden()  # 縮み終わるまでは出したまま
    QTest.qWait(WAIT_MS)
    assert body.isHidden() and body.maximumHeight() == motion.UNBOUNDED_HEIGHT
    section.close()


def test_the_segment_plate_slides_to_the_new_choice(qapp, moving):
    segments = SegmentedControl()
    for text in ("外", "内", "両"):
        segments.addItem(text, text)
    segments.resize(240, 28)
    segments.show()
    QTest.qWait(20)
    segments.setCurrentIndex(2)
    assert segments._sliding_plate is not None
    QTest.qWait(WAIT_MS)
    assert segments._sliding_plate is None
    assert segments._plate_rect() == segments._group.button(2).geometry().toRectF()
    segments.close()


def test_the_bottom_panel_collapses_to_the_same_height_with_motion(tmp_path, monkeypatch, qapp, moving):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    window.set_ui_mode(ui_mode.ADVANCED)
    window.resize(1200, 800)
    window.show()
    QTest.qWait(50)
    tab = window.tab_widget.currentWidget()
    splitter, panel = tab.center_splitter, tab.bottom_panel
    total = sum(splitter.sizes())
    splitter.setSizes([total - 260, 260])
    panel.set_collapsed(True)
    QTest.qWait(WAIT_MS)
    from graphica.gui.shell import bottom_panel
    assert splitter.sizes()[1] == bottom_panel.HEADER_HEIGHT + 2
    assert panel.stack.isHidden()
    panel.set_collapsed(False)
    QTest.qWait(WAIT_MS)
    assert splitter.sizes()[1] == 260 and not panel.stack.isHidden()
    window.close()


def test_switching_inspector_tabs_crossfades_from_a_picture_of_the_old_page(tmp_path, monkeypatch, qapp, moving):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    window.show()
    QTest.qWait(30)
    tab = window.tab_widget.currentWidget()
    tab.inspector.show_page("axes")
    overlay = tab.inspector.stack._motion_crossfade_overlay
    assert overlay.isVisible() and overlay.geometry() == tab.inspector.stack.rect()
    # 新しいページ自体には効果を付けない(付けると後ろに前のページの絵が残る)
    assert tab.inspector.stack.currentWidget().graphicsEffect() is None
    QTest.qWait(WAIT_MS)
    window.close()


def test_the_tab_underline_slides_to_the_new_tab(tmp_path, monkeypatch, qapp, moving):
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    window.show()
    QTest.qWait(30)
    tab = window.tab_widget.currentWidget()
    indicator = tab.inspector.tab_indicator
    tab.inspector.show_page("export")
    QTest.qWait(WAIT_MS)
    target = tab.inspector.tab_bar.tabRect(tab.inspector.page_index("export"))
    assert indicator.geometry().left() == target.left() and indicator.geometry().width() == target.width()
    window.close()


def test_a_switch_knob_slides_and_then_drops_the_progress(qapp, moving):
    from PySide6.QtWidgets import QCheckBox
    from graphica.gui import theme
    checkbox = theme.make_toggle_switch(QCheckBox("x"))
    checkbox.show()
    checkbox.setChecked(True)
    assert checkbox.property(motion.SWITCH_PROGRESS_PROPERTY) is not None
    QTest.qWait(WAIT_MS)
    assert checkbox.property(motion.SWITCH_PROGRESS_PROPERTY) is None
    checkbox.close()


def test_a_toast_shows_and_hides(qapp):
    from PySide6.QtWidgets import QWidget
    window = QWidget()
    window.resize(400, 300)
    window.show()
    motion.toast(window, "保存しました")
    box = window._toast
    assert box.isVisible() and box.text() == "保存しました"
    box._fade_out()
    assert box.isHidden()
    window.close()


def test_the_preference_turns_motion_off_and_on(qapp, monkeypatch):
    monkeypatch.setattr(QApplication.instance(), "platformName", lambda: "windows")
    try:
        motion.set_enabled(False)
        assert not motion.is_enabled()
        motion.set_enabled(True)
        assert motion.is_enabled()
    finally:
        motion.set_enabled(True)


def test_switching_tabs_again_after_the_crossfade_finished_does_not_raise(tmp_path, monkeypatch, qapp, moving):
    from PySide6.QtCore import QEvent
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    window.show()
    QTest.qWait(30)
    tab = window.tab_widget.currentWidget()
    tab.inspector.show_page("axes")
    QTest.qWait(WAIT_MS)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    tab.inspector.show_page("export")
    tab.inspector.show_page("properties")
    QTest.qWait(WAIT_MS)
    window.close()


def test_the_dataset_list_band_slides_to_the_newly_selected_row(tmp_path, monkeypatch, qapp, moving):
    import pandas as pd
    from graphica.core.dataset import Dataset
    window = _make_isolated_main_app_window(tmp_path, monkeypatch)
    window.show()
    tab = window.tab_widget.currentWidget()
    datasets = [Dataset(name=n, df=pd.DataFrame({"x": [0.0, 1.0], "y": [1.0, 2.0]}), x_col_name="x", y_col_name="y")
                for n in ("a", "b")]
    for dataset in datasets:
        tab._add_dataset(dataset)
    tree = tab.ui.dataset_list_widget
    tree.setCurrentItem(tab._get_dataset_tree_item(datasets[0]))
    QTest.qWait(WAIT_MS)
    tree.setCurrentItem(tab._get_dataset_tree_item(datasets[1]))
    assert tree.sliding_selection_band is not None
    QTest.qWait(WAIT_MS)
    assert tree.sliding_selection_band is None
    window.close()


def test_the_subplot_cell_highlight_slides(qapp, moving):
    from graphica.gui.shell.subplot_target_bar import SubplotGrid
    grid = SubplotGrid()
    grid.set_grid(2, 2, 0)
    grid.show()
    grid.set_grid(2, 2, 3)
    assert grid._sliding is not None
    QTest.qWait(WAIT_MS)
    assert grid._sliding is None
    grid.close()
