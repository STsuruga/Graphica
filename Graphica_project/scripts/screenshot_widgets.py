"""GUI 刷新の部品(gui/widgets/)を見本のプロパティ欄のように並べ、ライト/ダークで PNG に撮る。

    python scripts/screenshot_widgets.py <出力フォルダ> [--theme-color #RRGGBB]

部品はまだ画面に組み込む前なので、見本(docs/dev/mockups/gui_redesign/)と見比べるのに使う。cwd = Graphica_project/。
"""
import argparse
import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
                               QLabel, QLineEdit, QVBoxLayout, QWidget)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def _spin(value, decimals=2, maximum=100.0):
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(0.0, maximum)
    spin.setSingleStep(0.1)
    spin.setValue(value)
    return spin


def build_gallery():
    from graphica.gui import theme
    from graphica.gui.icon_utils import icon
    from graphica.gui.widgets import (ColorChipRow, ComboMirror, SectionHeader, SegmentedControl, SliderSpin,
                                      StatCard, TypeTileGroup)

    root = QWidget()
    root.setObjectName("gallery")
    root.setFixedWidth(340)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(16, 12, 16, 16)
    outer.setSpacing(4)

    mode = SegmentedControl()
    mode.addItem("シンプル", "lite")
    mode.addItem("詳細", "advanced")
    mode.setCurrentIndex(1)
    outer.addWidget(QLabel("モードの切り替え(上部バー)"))
    outer.addWidget(mode)

    header = SectionHeader("基本スタイル")
    header.setIcon(icon("chevron-down", size=13))
    outer.addWidget(header)

    form = QFormLayout()
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(4)
    tiles = TypeTileGroup()
    for glyph, text, value in (("line", "線", "Line"), ("scatter", "点", "Scatter"),
                               ("line_scatter", "線+点", "Line+Marker"), ("bar", "棒", "Bar")):
        tiles.addTile(glyph, text, value)
    form.addRow(tiles)
    legend = QLineEdit("cooling_curve")
    form.addRow("凡例名", legend)
    chips = ColorChipRow(["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"])
    chips.set_current_color("#1f77b4")
    form.addRow("色", chips)

    linestyle_combo = QComboBox()
    for style in ("solid", "dashed", "dotted", "dashdot"):
        linestyle_combo.addItem(style)
    line_seg = SegmentedControl()
    for style, tip in (("-", "実線"), ("--", "破線"), (":", "点線"), ("-.", "一点鎖線")):
        line_seg.addLineStyleItem(style, data={"-": "solid", "--": "dashed", ":": "dotted", "-.": "dashdot"}[style],
                                  tooltip=tip)
    ComboMirror(line_seg, linestyle_combo)
    form.addRow("線の種類", line_seg)
    form.addRow("線の太さ", SliderSpin(_spin(1.5, maximum=20.0), 0.0, 5.0))
    form.addRow("透明度", SliderSpin(_spin(1.0, maximum=1.0), 0.0, 1.0))
    smoothing = theme.make_toggle_switch(QCheckBox())
    form.addRow("平滑化", smoothing)
    on_switch = theme.make_toggle_switch(QCheckBox())
    on_switch.setChecked(True)
    form.addRow("(オン)", on_switch)
    outer.addLayout(form)

    for title, state in (("マーカー", "なし"), ("グラデーション", "オフ"), ("ウォーターフォール", "オフ")):
        closed = SectionHeader(title)
        closed.setIcon(icon("chevron-right", size=13))
        closed.setChecked(False)
        closed.set_state_text(state)
        outer.addWidget(closed)

    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.HLine)
    outer.addWidget(separator)
    outer.addWidget(QLabel("統計カード"))
    stats = QGridLayout()
    stats.setSpacing(6)
    for i, (label, value) in enumerate((("点の数", "41"), ("平均", "42.99"), ("標準偏差", "17.54"),
                                        ("最小", "26.84"), ("最大", "90.18"), ("欠損", "0"))):
        stats.addWidget(StatCard(label, value), i // 3, i % 3)
    outer.addLayout(stats)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir")
    parser.add_argument("--theme-color", default=None)
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    app = QApplication(sys.argv)
    from graphica.__main__ import APP_FONT_FAMILIES, APP_FONT_POINT_SIZE
    font = QFont()
    font.setFamilies(APP_FONT_FAMILIES)
    font.setPointSizeF(APP_FONT_POINT_SIZE)
    app.setFont(font)
    from graphica.gui import theme
    from graphica.gui.theme_color import DEFAULT_THEME_COLOR

    for dark in (False, True):
        theme.apply_theme(app, dark, args.theme_color or DEFAULT_THEME_COLOR)
        gallery = build_gallery()
        gallery.setStyleSheet("QWidget#gallery { background: %s; }" % theme.current_tokens()["surface"])
        gallery.move(-3000, 0)
        gallery.show()
        for _ in range(20):
            app.processEvents()
        path = os.path.join(args.out_dir, f"{'dark' if dark else 'light'}.png")
        gallery.grab().save(path)
        print(path, flush=True)
        gallery.close()
    os._exit(0)


if __name__ == "__main__":
    main()
