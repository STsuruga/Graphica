"""画面の短い動き(gui/motion.py)。テストの環境(offscreen)では止まっているので、ここでだけ動かして最後の形を確かめる。"""
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from graphica.gui import motion, ui_mode
from graphica.gui.builders.property_sections import build_section
from graphica.gui.widgets import SegmentedControl
from test_main_app_window import _make_isolated_main_app_window

WAIT_MS = max(motion.EXPAND_MS, motion.SLIDE_MS, motion.FADE_MS) + 150


def _wait_until_still(owner, name, timeout_ms=3000):
    """動きが終わるまで待つ(並列で重いときは、決まった時間では終わらないことがある)。"""
    QTest.qWait(30)
    waited = 30
    while motion.running(owner, name) and waited < timeout_ms:
        QTest.qWait(20)
        waited += 20
    QTest.qWait(20)


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


def test_a_section_opens_and_closes_by_clipping_its_rows_at_their_full_height(qapp, moving):
    entry = build_section("節", opened=False)
    entry['form'].addRow("名前", QLineEdit())
    entry['form'].addRow("もう1つ", QLineEdit())
    section = entry['section']
    section.resize(300, 200)
    section.show()
    body, clip = entry['body'], entry['clip']
    assert clip.isHidden()
    entry['toggle'].setChecked(True)
    QTest.qWait(motion.EXPAND_MS // 2)
    # 動いている間、中身は本来の高さのまま(行を詰め直さない)で、外枠だけが低い
    assert body.height() == body.sizeHint().height() and 0 < clip.height() < body.height()
    entry['toggle'].setChecked(False)  # 開ききる前に閉じても、今の高さから縮む
    QTest.qWait(5)
    height_when_reversed = clip.height()
    assert height_when_reversed > 0
    QTest.qWait(WAIT_MS)
    assert clip.isHidden() and body.isHidden()
    entry['toggle'].setChecked(True)
    QTest.qWait(WAIT_MS)
    assert not body.isHidden() and clip.maximumHeight() == motion.UNBOUNDED_HEIGHT
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
    _wait_until_still(indicator, "_motion_slide")
    target = tab.inspector.tab_bar.tabRect(tab.inspector.page_index("export"))
    # 線はタブの右の余白の手前まで(文字の幅)
    from graphica.gui.shell.inspector import INSPECTOR_TAB_SPACING
    assert indicator.geometry().left() == target.left()
    assert indicator.geometry().width() == target.width() - INSPECTOR_TAB_SPACING
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


def test_the_rail_plate_stretches_on_its_way_to_the_new_button(qapp, moving):
    from graphica.gui.shell.rail import ActivityRail
    rail = ActivityRail()
    for key in ("data", "analysis", "notes"):
        rail.add_page(key, "database", key)
    rail.resize(56, 300)
    rail.show()
    QTest.qWait(20)
    start = rail._plate_rect()
    rail.select_page("notes")
    end = rail._plate_rect()
    QTest.qWait(80)
    # 途中は前のボタンから伸びて、元の四角より縦に長い
    assert rail._sliding is not None and rail._sliding.height() > start.height()
    QTest.qWait(400)
    assert rail._sliding is None and rail._plate_rect() == end
    rail.close()


def test_switching_a_section_on_opens_it_after_its_rows_are_shown(qapp, moving):
    from PySide6.QtWidgets import QCheckBox
    from graphica.gui.builders.property_sections import attach_header_switch
    entry = build_section("節", opened=False)
    extra = QLineEdit()
    extra.setVisible(False)
    entry['form'].addRow("いつも", QLineEdit())
    entry['form'].addRow("オンで出る", extra)
    switch = QCheckBox("x")
    attach_header_switch(entry, switch)
    # オンにしたら行が出る(グラデーションの詳細の欄のように、同じ知らせで出し入れされる)
    switch.toggled.connect(extra.setVisible)
    section = entry['section']
    section.resize(300, 300)
    section.show()
    QTest.qWait(20)
    switch.click()
    QTest.qWait(5)
    # 動き出す時点で、オンで出た行の分まで中身の高さに入っている(止まったときに跳ねない)
    assert extra.isVisible()
    full = entry['body'].height()
    QTest.qWait(WAIT_MS)
    assert entry['body'].height() == full
    section.close()


def test_switching_a_section_off_shrinks_from_its_full_height_even_though_its_rows_vanish(qapp, moving):
    from PySide6.QtWidgets import QCheckBox
    from graphica.gui.builders.property_sections import attach_header_switch
    entry = build_section("節", opened=True)
    rows = [QLineEdit() for _ in range(3)]
    for index, row in enumerate(rows):
        entry['form'].addRow(f"行{index}", row)
    switch = QCheckBox("x")
    switch.setChecked(True)
    attach_header_switch(entry, switch)
    # オフにしたら中の行が消える(グラデーションの詳細の欄のように、同じ知らせで出し入れされる)
    for row in rows:
        switch.toggled.connect(row.setVisible)
    section = entry['section']
    section.resize(300, 300)
    section.show()
    QTest.qWait(20)
    full = entry['clip'].height()
    switch.click()
    QTest.qWait(5)
    clip = entry['clip']
    # 行はもう隠れているが、外枠は閉じ始めの高さから縮み、その間は中身の絵をかぶせている
    assert not rows[0].isVisible()
    assert clip.height() >= full - 2 and clip._close_picture is not None
    QTest.qWait(WAIT_MS)
    assert clip.isHidden() and clip._close_picture is None
    section.close()


def test_rows_below_move_in_the_same_step_as_the_section(qapp, moving):
    from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget
    page = QWidget()
    layout = QVBoxLayout(page)
    first = build_section("上", opened=False)
    first['form'].addRow("名前", QLineEdit())
    below = build_section("下", opened=True)
    below['form'].addRow("名前", QLineEdit())
    layout.addWidget(first['section'])
    layout.addWidget(below['section'])
    layout.addStretch(1)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(page)
    area.resize(300, 200)
    area.show()
    QTest.qWait(20)
    first['toggle'].setChecked(True)
    QTest.qWait(5)
    gaps = set()
    for _ in range(12):
        QTest.qWait(16)
        # 下の節の上端は、いつも上の節の見出し+外枠のすぐ下(途中の回で重ならない・離れない)
        gaps.add(below['section'].y() - (first['section'].y() + first['section'].height()))
    assert len(gaps) == 1
    area.close()
