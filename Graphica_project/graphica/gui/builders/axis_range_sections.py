"""「軸」タブの X軸・Y軸を、範囲・目盛・目盛の数値(と単位・第2Y軸)の開閉できる節に分ける。

ラベル/書式の節(axis_format_sections)と同じく、行は Designer と axis_panel が作った QFormLayout から
takeRow() で移すだけなので、欄の部品と値の対応 AXIS_BINDINGS は変わらない。
"""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from graphica.core.i18n import tr
from graphica.gui import ui_mode
from graphica.gui.builders.property_sections import build_section
from graphica.gui.widgets import ComboMirror, SegmentedControl

# 節: (キー, 見出し, 移す行(その行の名前か欄の属性の名前、並び順))。{a} は軸の接頭辞(x / y)
_AXIS_SECTIONS = (
    ("range", "範囲", ("ui.{a}_autoscale_checkbox", "ui.{a}_min_label", "ui.{a}_max_label",
                       "{a}_view_range_button", "ui.{a}_log_checkbox", "{a}_log_note", "ui.{a}_invert_checkbox")),
    ("ticks", "目盛", ("{a}_ticks_visible_checkbox", "ui.{a}_major_tick_label", "ui.{a}_major_tick_interval_label",
                       "ui.{a}_minor_ticks_visible_checkbox", "ui.{a}_minor_tick_interval_label",
                       "{a}_log_minor_subs_label", "{a}_log_minor_labels_checkbox")),
    ("tick_labels", "目盛の数値", ("{a}_tick_labels_visible_checkbox", "{a}_tick_format_label",
                                   "{a}_tick_decimals_spinbox")),
)
X_UNIT_ROWS = ("x_secondary_axis_source_unit_label", "x_secondary_axis_target_unit_label")
# 第2Y軸の行(名前の無い行は欄の属性で指す)。並びは主の Y軸の「範囲」「目盛」と同じ
# 主目盛の決め方(選んだ番号で値を持つ index の束ね)
TICK_MODE_ITEMS = ("自動", "固定間隔")
TICK_MODE_COMBOS = (("x_ticks", "ui.x_major_tick_mode_combo"), ("y_ticks", "ui.y_major_tick_mode_combo"),
                    ("y2", "y2_major_tick_mode_combo"))
Y2_ROWS = ("y2_autoscale_checkbox", "y2_min_spinbox", "y2_max_spinbox", "y2_view_range_button",
           "y2_log_checkbox", "y2_log_note", "y2_invert_checkbox", "y2_major_tick_mode_combo",
           "y2_major_tick_interval_spinbox", "y2_minor_ticks_visible_checkbox", "y2_minor_tick_interval_spinbox")


def build_axis_range_sections(app):
    """X軸・Y軸のタブの行を節に移す。第2Y軸のグループボックスも節にする。"""
    app._axis_tab_sections = {}
    x_layout = _sections_layout(app.ui.tab, app.ui.formLayout)
    y_layout = _sections_layout(app.ui.tab_2, app.ui.formLayout_2)
    for axis, source, layout in (("x", app.ui.formLayout, x_layout), ("y", app.ui.formLayout_2, y_layout)):
        for index, (key, title, rows) in enumerate(_AXIS_SECTIONS):
            entry = build_section(tr(title), opened=True, first=(index == 0))
            for name in rows:
                _move_row(source, entry['form'], ui_mode.resolve(app, name.format(a=axis)))
            layout.addWidget(entry['section'])
            app._axis_tab_sections[f"{axis}_{key}"] = entry

    units = build_section(tr("単位"), opened=True)
    for name in X_UNIT_ROWS:
        _move_row(app.ui.formLayout, units['form'], ui_mode.resolve(app, name))
    x_layout.addWidget(units['section'])
    app._axis_tab_sections["x_units"] = units
    app.x_unit_section = units['section']

    y2 = build_section(tr("第2Y軸"), opened=False)
    group = app.y2_axis_group
    for name in Y2_ROWS:
        _move_row(group.layout(), y2['form'], ui_mode.resolve(app, name))
    group.parentWidget().layout().removeWidget(group)
    group.hide()
    group.deleteLater()
    del app.y2_axis_group
    y_layout.addWidget(y2['section'])
    app._axis_tab_sections["y2"] = y2
    app.y2_axis_section = y2['section']
    app._y2_in_use = None
    set_y2_in_use(app, False)

    # 主目盛の 自動/固定間隔 は2択なのでセグメントにする。値の持ち主はコンボのまま(番号をデータにして突き合わせる)
    app.tick_mode_mirrors = []
    for section_key, combo_name in TICK_MODE_COMBOS:
        combo = ui_mode.resolve(app, combo_name)
        segments = SegmentedControl()
        for index, text in enumerate(TICK_MODE_ITEMS):
            combo.setItemData(index, index)
            segments.addItem(tr(text), index)
        form = app._axis_tab_sections[section_key]['form']
        field = QWidget()
        field_layout = QHBoxLayout(field)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.addWidget(segments, 1)
        if form.replaceWidget(combo, field) is None:
            raise ValueError(f"{combo_name} が節のフォームにありません")
        combo.setParent(field)
        combo.hide()
        app.tick_mode_mirrors.append(ComboMirror(segments, combo))

    # 隣のタブのほうが高いと余りの高さが節に配られ、節の間が空くので、余りは末尾で受ける
    for layout in (x_layout, y_layout):
        layout.addStretch(1)
    # タブの中の左右の余白をなくし、入力欄の左端をほかのタブ(プロパティ・凡例・エクスポート)とそろえる
    for tab in (app.ui.tab, app.ui.tab_2, app.ui.tab_3):
        tab.layout().setContentsMargins(0, 10, 0, 0)


def set_y2_in_use(app, in_use):
    """第2Y軸を使うデータセットが出たら節を開き、いなくなったら畳んで「使っていません」と出す。

    変わったときだけ開閉するので、使っていないときに手で開いたものは閉じない。
    """
    sections = getattr(app, '_axis_tab_sections', None)
    if sections is None or app._y2_in_use == in_use:
        return
    app._y2_in_use = in_use
    toggle = sections["y2"]['toggle']
    toggle.setChecked(in_use)
    if hasattr(toggle, 'set_state_text'):
        toggle.set_state_text("" if in_use else tr("使っていません"))


def _sections_layout(tab, source):
    """タブの中で source(Designer のフォーム)があった位置の下に、節を縦に並べる入れ物を置く。"""
    container = QWidget()
    container.setObjectName("axis_tab_sections")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    grid = tab.layout()
    for index in range(grid.count()):
        if grid.itemAt(index).layout() is source:
            row, column, _rows, _columns = grid.getItemPosition(index)
            grid.addWidget(container, row + 1, column)
            break
    else:
        raise ValueError("タブの中にフォームが見つからない")
    return layout


def _move_row(source, target, anchor):
    row, _role = source.getWidgetPosition(anchor)
    if row < 0:
        raise ValueError(f"{anchor!r} は元のフォームにありません")
    taken = source.takeRow(row)
    items = [item for item in (taken.labelItem, taken.fieldItem) if item is not None]
    parts = [item.widget() if item.widget() is not None else item.layout() for item in items]
    target.addRow(*parts)
