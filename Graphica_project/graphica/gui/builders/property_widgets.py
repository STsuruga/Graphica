"""プロパティの見た目の部品: 線の種類のセグメント、太さ・透明度のスライダー、平滑化のスイッチ、色のチップ、
シンプルの種類のタイルと「アドバンスドですべて表示」の案内。

値の持ち主は今のコンボ・スピンボックス・チェックボックスのまま(バインディングの表はそちらを見る)。
バインディングで戻すとシグナルが止まるので、戻したあとに refresh_property_widgets() で見た目を合わせる。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from graphica.core.i18n import tr
from graphica.gui import theme
from graphica.gui.builders.common import _svg_icon
from graphica.gui.dataset_bindings import NO_MARKER
from graphica.gui.widgets import ComboMirror, SegmentedControl, SliderSpin, TypeTileGroup

LINE_STYLE_ITEMS = (("solid", "実線"), ("dashed", "破線"), ("dotted", "点線"), ("dashdot", "一点鎖線"))

# (絵, 表示名, 種別のコンボの値)
TYPE_TILES = (
    ("line", "線", "Line"),
    ("scatter", "点", "Scatter"),
    ("line_scatter", "線+点", "Line+Scatter"),
    ("bar", "棒", "Bar"),
)
# 点を描く種類。マーカーが「なし」のまま選ぶと何も見えないので、円にする
_MARKER_TYPES = ("Scatter", "Line+Scatter")
_DEFAULT_MARKER = "o"

# スライダーの範囲(よく使う範囲。数値の欄はこれより外の値も受け付ける)
LINEWIDTH_SLIDER_RANGE = (0.0, 5.0)
ALPHA_SLIDER_RANGE = (0.0, 1.0)

QUICK_COLOR_COUNT = 5


class _TypeTileMirror(ComboMirror):
    """タイルで点を描く種類を選んだとき、マーカーが無ければ円にする。種類の変更と1つの「元に戻す」にまとめる。"""

    def __init__(self, view, combo, app):
        self._app = app
        super().__init__(view, combo)

    def _on_view_changed(self, index):
        app = self._app
        needs_marker = (self.view.itemData(index) in _MARKER_TYPES
                        and app.ui.marker_combo.currentData() == NO_MARKER)
        if not needs_marker:
            super()._on_view_changed(index)
            return
        app.undo_stack.beginMacro(tr("グラフの種類"))
        try:
            app.ui.marker_combo.setCurrentIndex(app.ui.marker_combo.findData(_DEFAULT_MARKER))
            super()._on_view_changed(index)
        finally:
            app.undo_stack.endMacro()


def _swap_field(form, old_field, new_field):
    """フォームの欄を差し替える(行の位置はそのまま)。old_field は new_field の中に取り込む前に呼ぶこと。"""
    if form.replaceWidget(old_field, new_field) is None:
        raise ValueError("欄がフォームに見つからない")


def _hidden_owner_row(view, owner):
    """見た目の部品と、隠した値の持ち主(コンボ)を1つの欄にまとめる(持ち主が節の外に浮かないように)。"""
    field = QWidget()
    layout = QHBoxLayout(field)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(view, 1)
    owner.setParent(field)
    owner.hide()
    return field


def build_property_widgets(app):
    """基本スタイルの節の部品を見本の形に替える。build_dataset_style_controls の最後に呼ぶ(行が全部できた後)。"""
    style_form = app._prop_form('style')

    # 線の種類: 線の絵のセグメント
    app.linestyle_segments = SegmentedControl()
    for line_style, tooltip in LINE_STYLE_ITEMS:
        app.linestyle_segments.addLineStyleItem(line_style, tooltip=tr(tooltip))
    placeholder = QWidget()
    _swap_field(style_form, app.ui.linestyle_combo, placeholder)
    app.linestyle_field = _hidden_owner_row(app.linestyle_segments, app.ui.linestyle_combo)
    _swap_field(style_form, placeholder, app.linestyle_field)
    placeholder.deleteLater()
    app.linestyle_mirror = ComboMirror(app.linestyle_segments, app.ui.linestyle_combo)

    # 線の太さ・透明度: スライダー+数値(数値の欄は今のスピンボックス)
    app.linewidth_slider = _slider_field(style_form, app.ui.linewidth_spinbox, *LINEWIDTH_SLIDER_RANGE)
    app.alpha_slider = _slider_field(style_form, app.alpha_spinbox, *ALPHA_SLIDER_RANGE)

    # 平滑化: 部品は替えず、描き方だけスイッチに
    theme.make_toggle_switch(app.ui.smoothing_checkbox)

    # 色: 見本の右に、今の配色パレットの色
    app.color_picker_widget.show_quick_colors(quick_colors(app))

    # シンプルの種類: アイコンの4択(裏で「種別」のコンボを書く)
    app.plot_type_tiles = TypeTileGroup()
    for glyph, text, value in TYPE_TILES:
        app.plot_type_tiles.addTile(glyph, tr(text), value)
    app.plot_type_tiles_mirror = _TypeTileMirror(app.plot_type_tiles, app.ui.plot_type_combo, app)
    app._plot_type_tiles_row.layout().addWidget(app.plot_type_tiles)

    app.lite_more_box = _build_lite_more_box(app)
    app._dataset_property_sections_container.layout().addWidget(app.lite_more_box)


def _slider_field(form, spinbox, slider_min, slider_max):
    placeholder = QWidget()
    _swap_field(form, spinbox, placeholder)
    slider = SliderSpin(spinbox, slider_min, slider_max)
    _swap_field(form, placeholder, slider)
    placeholder.deleteLater()
    return slider


def _build_lite_more_box(app):
    """シンプルで隠している項目の案内と、アドバンスドに切り替えるリンク。"""
    box = QFrame()
    box.setObjectName("lite_more_box")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)

    row = QHBoxLayout()
    row.setSpacing(8)
    app.lite_more_icon = QLabel()
    app.lite_more_icon.setObjectName("lite_more_icon")
    app.lite_more_icon.setPixmap(_svg_icon("lock", size=15).pixmap(15, 15))
    app.lite_more_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
    text = QLabel(tr("誤差・透明度・平滑化・マーカー・グラデーション・ウォーターフォール・2D マップなど"))
    text.setObjectName("lite_more_text")
    text.setWordWrap(True)
    row.addWidget(app.lite_more_icon)
    row.addWidget(text, 1)
    layout.addLayout(row)

    app.lite_more_button = QPushButton(tr("アドバンスドですべて表示 →"))
    app.lite_more_button.setObjectName("lite_more_button")
    app.lite_more_button.setFlat(True)
    app.lite_more_button.setCursor(Qt.CursorShape.PointingHandCursor)
    app.lite_more_button.clicked.connect(app.show_advanced_mode)
    layout.addWidget(app.lite_more_button, 0, Qt.AlignmentFlag.AlignLeft)
    return box


def quick_colors(app):
    return list(app.colors.active_color_cycle())[:QUICK_COLOR_COUNT]


def refresh_property_widgets(app):
    """バインディングで欄を戻したあと(シグナルが止まっている)、見た目の部品を合わせる。"""
    if not hasattr(app, 'linestyle_mirror'):
        return
    app.linestyle_mirror.refresh()
    app.plot_type_tiles_mirror.refresh()
    app.linewidth_slider.refresh()
    app.alpha_slider.refresh()
    app.color_picker_widget.show_quick_colors(quick_colors(app))
