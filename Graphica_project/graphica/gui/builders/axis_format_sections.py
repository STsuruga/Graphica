"""「軸」タブの「ラベル/書式」を、ラベル・目盛・グリッド・外枠・カラーバーの開閉できる節に分ける。

行は Designer と axis_panel が formLayout_3 に作ったものを takeRow() で移す(欄の部品はそのままなので、
値の対応 AXIS_BINDINGS は変わらない)。見た目の部品(スライダー・セグメント)は値の持ち主の欄を取り込むか、
隠した持ち主と同期する。軸の設定を欄に戻した後(シグナルが止まっている)は refresh_axis_format_widgets() で合わせる。
"""
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from graphica.core.i18n import tr
from graphica.gui import ui_mode
from graphica.gui.builders.property_sections import attach_header_switch, build_section
from graphica.gui.widgets import ComboMirror, SegmentedControl, SliderSpin

# (キー, 見出し, 移す行(その行の名前か欄の属性の名前、並び順))
AXIS_FORMAT_SECTIONS = (
    ("labels", "ラベル", ("ui.title_text_label", "ui.x_label_text_label", "ui.y_label_text_label",
                          "y2_label_text_label", "ui.axis_label_format_label")),
    ("ticks", "目盛", ("ui.tick_format_label", "tick_direction_label", "tick_direction_y2_label",
                       "ui.tick_width_label", "tick_length_label")),
    ("grid", "グリッド", ("ui.minor_grid_visible_checkbox", "x_major_grid_style_label", "x_minor_grid_style_label",
                          "y_major_grid_style_label", "y_minor_grid_style_label")),
    ("spine", "外枠", ("ui.spine_format_label",)),
    ("colorbar", "カラーバー", ("colorbar_position_label", "colorbar_width_label", "colorbar_label_label")),
)
# 節の見出しに置くオン/オフ(その機能を表示するかどうか)
AXIS_SECTION_SWITCHES = {"grid": "ui.grid_visible_checkbox", "colorbar": "colorbar_enabled_checkbox"}

# 目盛の向き: (値, 表示, 説明)。コンボの文字がそのまま値
TICK_DIRECTION_ITEMS = (("out", "外", "外向き"), ("in", "内", "内向き"), ("inout", "両", "内外の両方"))
# 目盛の向きは主と補助を1行ずつ(2つ並べるとインスペクタの幅に入らない)。(名前の属性, 名前, 値の持ち主のコンボ)
TICK_DIRECTION_ROWS = (
    ("tick_direction_label", "主目盛の向き", "major_tick_direction_combo"),
    ("minor_tick_direction_label", "補助目盛の向き", "minor_tick_direction_combo"),
    ("tick_direction_y2_label", "第2軸の主目盛の向き", "major_tick_direction_y2_combo"),
    ("minor_tick_direction_y2_label", "第2軸の補助目盛の向き", "minor_tick_direction_y2_combo"),
)
Y2_TICK_DIRECTION_LABELS = ("tick_direction_y2_label", "minor_tick_direction_y2_label")
# スライダーの範囲(よく使う範囲。数値の欄はこれより外の値も受け付ける)
TICK_WIDTH_SLIDER_RANGE = (0.0, 3.0)
SPINE_WIDTH_SLIDER_RANGE = (0.0, 3.0)
COLORBAR_WIDTH_SLIDER_RANGE = (0.01, 0.2)


def build_axis_format_sections(app):
    """formLayout_3 の行を節に移し、部品をスイッチ・スライダー・セグメントにする。凡例の行を移した後に呼ぶ。"""
    source = app.ui.formLayout_3
    container = QWidget()
    container.setObjectName("axis_format_sections")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    app._axis_sections = {}
    for index, (key, title, rows) in enumerate(AXIS_FORMAT_SECTIONS):
        entry = build_section(tr(title), opened=True, first=(index == 0))
        for name in rows:
            _move_row(source, entry['form'], ui_mode.resolve(app, name))
        switch_name = AXIS_SECTION_SWITCHES.get(key)
        if switch_name is not None:
            checkbox = ui_mode.resolve(app, switch_name)
            row, _role = source.getWidgetPosition(checkbox)
            source.takeRow(row)
            attach_header_switch(entry, checkbox)
        layout.addWidget(entry['section'])
        app._axis_sections[key] = entry

    # 隣のタブ(X軸・Y軸)のほうが高いと余りの高さが節に配られ、節の間が空くので、余りは末尾で受ける
    layout.addStretch(1)

    # 行を移した後の formLayout_3 の場所に、節を入れる
    grid = app.ui.tab_3.layout()
    for index in range(grid.count()):
        if grid.itemAt(index).layout() is source:
            row, column, _rows, _columns = grid.getItemPosition(index)
            grid.addWidget(container, row + 1, column)
            break
    app.axis_format_sections_container = container

    _build_axis_format_widgets(app)


def _move_row(source, target, anchor):
    row, _role = source.getWidgetPosition(anchor)
    if row < 0:
        raise ValueError(f"{anchor!r} は formLayout_3 にありません")
    taken = source.takeRow(row)
    items = [item for item in (taken.labelItem, taken.fieldItem) if item is not None]
    parts = [item.widget() if item.widget() is not None else item.layout() for item in items]
    target.addRow(*parts)


def _build_axis_format_widgets(app):
    ticks = app._axis_sections['ticks']['form']
    # 主/補助を横に並べた2行を外し、1行ずつのセグメントにする(置く位置は外した行の所)
    position, _role = ticks.getWidgetPosition(app.tick_direction_label)
    for label_attr in ("tick_direction_label", "tick_direction_y2_label"):
        row, _role = ticks.getWidgetPosition(getattr(app, label_attr))
        taken = ticks.takeRow(row)
        if taken.fieldItem is not None and taken.fieldItem.layout() is not None:
            holder = taken.fieldItem.layout()
            while holder.count():
                holder.takeAt(0)
            holder.deleteLater()
    app.tick_direction_mirrors = []
    for offset, (label_attr, text, combo_attr) in enumerate(TICK_DIRECTION_ROWS):
        label = getattr(app, label_attr, None)
        if label is None:
            label = QLabel()
            setattr(app, label_attr, label)
        label.setText(tr(text))
        combo = getattr(app, combo_attr)
        segments = SegmentedControl()
        for value, item_text, tooltip in TICK_DIRECTION_ITEMS:
            segments.addItem(tr(item_text), value, tr(tooltip))
        ticks.insertRow(position + offset, label, _hidden_owner(segments, combo))
        app.tick_direction_mirrors.append(ComboMirror(segments, combo))
    app.tick_width_slider = _slider_in_form(ticks, app.ui.tick_width_spinbox, *TICK_WIDTH_SLIDER_RANGE)

    # 外枠: 太さ(スライダー)と色を別の行に
    spine = app._axis_sections['spine']['form']
    row, _role = spine.getWidgetPosition(app.ui.spine_format_label)
    taken = spine.takeRow(row)
    owner_layout = taken.fieldItem.layout() if taken.fieldItem is not None else None
    if owner_layout is not None:
        owner_layout.removeWidget(app.ui.spine_width_spinbox)
        owner_layout.removeWidget(app.ui.spine_color_button)
    app.ui.spine_format_label.setText(tr("外枠の太さ"))
    app.spine_width_slider = SliderSpin(app.ui.spine_width_spinbox, *SPINE_WIDTH_SLIDER_RANGE)
    spine.addRow(app.ui.spine_format_label, app.spine_width_slider)
    app.spine_color_label = QLabel(tr("外枠の色"))
    spine.addRow(app.spine_color_label, app.ui.spine_color_button)

    colorbar = app._axis_sections['colorbar']['form']
    app.colorbar_position_segments = SegmentedControl()
    for index in range(app.colorbar_position_combo.count()):
        app.colorbar_position_segments.addItem(app.colorbar_position_combo.itemText(index),
                                               app.colorbar_position_combo.itemData(index))
    owner = _hidden_owner(app.colorbar_position_segments, None)
    colorbar.replaceWidget(app.colorbar_position_combo, owner)
    _adopt_hidden(owner, app.colorbar_position_combo)
    app.colorbar_position_mirror = ComboMirror(app.colorbar_position_segments, app.colorbar_position_combo)
    app.colorbar_width_slider = _slider_in_form(colorbar, app.colorbar_width_spinbox, *COLORBAR_WIDTH_SLIDER_RANGE)


def set_y2_tick_direction_visible(app, visible):
    """第2軸の目盛の向きの2行を出し入れする(第2Y軸を使っているサブプロットがあるときだけ出す)。"""
    sections = getattr(app, '_axis_sections', None)
    for label_attr in Y2_TICK_DIRECTION_LABELS:
        label = getattr(app, label_attr, None)
        if label is None:
            continue
        if sections is None:
            label.setVisible(visible)
        else:
            sections['ticks']['form'].setRowVisible(label, visible)


def refresh_axis_format_widgets(app):
    """軸の設定を欄に戻した後(シグナルが止まっている)、見た目の部品を合わせる。"""
    if not hasattr(app, 'colorbar_width_slider'):
        return
    for mirror in app.tick_direction_mirrors:
        mirror.refresh()
    app.colorbar_position_mirror.refresh()
    for slider in (app.tick_width_slider, app.spine_width_slider, app.colorbar_width_slider):
        slider.refresh()


def _hidden_owner(view, owner):
    """見た目の部品と、隠した値の持ち主(コンボ)を1つの欄にまとめる。"""
    field = QWidget()
    layout = QHBoxLayout(field)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(view, 1)
    if owner is not None:
        _adopt_hidden(field, owner)
    return field


def _adopt_hidden(field, owner):
    owner.setParent(field)
    owner.hide()


def _slider_in_form(form: QFormLayout, spinbox, slider_min, slider_max):
    placeholder = QWidget()
    if form.replaceWidget(spinbox, placeholder) is None:
        raise ValueError("欄がフォームに見つからない")
    slider = SliderSpin(spinbox, slider_min, slider_max)
    form.replaceWidget(placeholder, slider)
    placeholder.deleteLater()
    return slider
