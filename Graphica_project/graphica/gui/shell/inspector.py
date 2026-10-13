"""右のインスペクタ: 下線のタブ(プロパティ・軸・凡例・エクスポート)と、選んでいるデータセットの見出し。

見本(docs/dev/mockups/gui_redesign/)では幅 340px。中身は今の部品をそのまま並べ直す(値の対応は変わらない)。
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QTabBar, QVBoxLayout,
                               QWidget)

from graphica.core.i18n import tr
from graphica.gui.dataset_bindings import MARKER_CHOICES, NO_MARKER
from graphica.gui.dataset_style_icon import NON_MARKER_PLOT_TYPES, make_dataset_style_icon

INSPECTOR_WIDTH = 340
# (キー, タブの名前)。並びは見本どおり
INSPECTOR_PAGES = (("properties", "プロパティ"), ("axes", "軸"), ("legend", "凡例"), ("export", "エクスポート"))


def scroll_page(widget, object_name):
    """縦だけスクロールする入れ物(横に出ると欄が切れるので、横のスクロールバーは出さない)。"""
    scroll = QScrollArea()
    scroll.setObjectName(object_name)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    # 出し入れすると中の幅が変わって欄が並び直すので、縦のスクロールバーの幅はいつも取っておき、
    # スクロールするものが無いときはつまみを見せない(QSS の scrollIdle)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    bar = scroll.verticalScrollBar()
    bar.rangeChanged.connect(lambda minimum, maximum: _set_scroll_idle(bar, maximum <= minimum))
    _set_scroll_idle(bar, True)
    scroll.setWidget(widget)
    return scroll


def _set_scroll_idle(bar, idle):
    if bar.property("scrollIdle") == idle:
        return
    bar.setProperty("scrollIdle", idle)
    bar.style().unpolish(bar)
    bar.style().polish(bar)


def wrap_long_rows(widget):
    """中の QFormLayout を、入らない行は名前を上・欄を下に折り返す形にする(幅 340px に収めるため)。"""
    for form in widget.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)


class TargetHeader(QWidget):
    """選んでいるデータセットの見出し: 線の見本・名前・「時間_s → 温度_degC · Line」。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inspector_target")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)
        self.swatch = QLabel()
        self.swatch.setFixedWidth(24)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.name_label = QLabel("-")
        self.name_label.setObjectName("inspector_target_name")
        self.sub_label = QLabel("")
        self.sub_label.setObjectName("inspector_target_sub")
        texts.addWidget(self.name_label)
        texts.addWidget(self.sub_label)
        layout.addWidget(self.swatch)
        layout.addLayout(texts, 1)

    def set_dataset(self, dataset):
        if dataset is None:
            self.swatch.clear()
            self.name_label.setText(tr("データセットを選んでください"))
            self.sub_label.setText("")
            return
        self.swatch.setPixmap(make_dataset_style_icon(dataset).pixmap(QSize(24, 10)))
        self.name_label.setText(dataset.name)
        x_name = getattr(dataset, 'x_col_name', '') or ''
        y_name = getattr(dataset, 'y_col_name', '') or ''
        self.sub_label.setText(f"{x_name} → {y_name} · {dataset.plot_type}")


def section_state_texts(dataset):
    """閉じていても分かるよう、節の見出しの右に出す今の状態(節のキー -> 文字)。"""
    if dataset is None:
        return {}
    marker_names = dict(MARKER_CHOICES)
    if dataset.plot_type in NON_MARKER_PLOT_TYPES or dataset.marker in (NO_MARKER, None, ''):
        marker = tr("なし")
    else:
        marker = tr(marker_names.get(dataset.marker, dataset.marker))
    on, off = tr("オン"), tr("オフ")
    return {
        "marker": marker,
        "gradient": on if dataset.gradient_enabled else off,
        "waterfall": on if dataset.waterfall_enabled else off,
        "map": "2D" if getattr(dataset, 'data_kind', '1d') == '2d_grid' else off,
    }


class Inspector(QWidget):
    """下線のタブと、タブごとのページ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inspector")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("inspector_tabs")
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(16, 0, 16, 0)
        tab_row.addWidget(self.tab_bar)
        tab_row.addStretch(1)
        tab_box = QWidget()
        tab_box.setObjectName("inspector_tab_row")
        tab_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tab_box.setLayout(tab_row)
        layout.addWidget(tab_box)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self._keys = []
        self.tab_bar.currentChanged.connect(self.stack.setCurrentIndex)

    def add_page(self, key, title, widget):
        self._keys.append(key)
        self.stack.addWidget(widget)
        self.tab_bar.addTab(tr(title))

    def page_index(self, key):
        return self._keys.index(key)

    def show_page(self, key):
        self.tab_bar.setCurrentIndex(self.page_index(key))

    def current_page(self):
        index = self.tab_bar.currentIndex()
        return self._keys[index] if 0 <= index < len(self._keys) else None

    def set_page_visible(self, key, visible):
        """タブを見せる・隠す(アドバンスドだけの「凡例」)。隠したタブを開いていたら最初のタブへ。"""
        index = self.page_index(key)
        self.tab_bar.setTabVisible(index, visible)
        if not visible and self.tab_bar.currentIndex() == index:
            self.tab_bar.setCurrentIndex(0)

    def is_page_visible(self, key):
        return self.tab_bar.isTabVisible(self.page_index(key))
