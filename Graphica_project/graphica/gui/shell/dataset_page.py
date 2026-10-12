"""左パネルの「データセット」のページ。今の一覧・検索欄・操作のボタンを、中央の下から移して並べ直す。

見本(docs/dev/mockups/gui_redesign/)の並び: 見出し(件数・フォルダ・＋追加)、検索欄、一覧、選んでいる
データセットの統計カード(2段目はアドバンスドだけ)、下に操作のボタンの行。
"""
import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QTreeWidgetItemIterator,
                               QVBoxLayout, QWidget)

from graphica.core.analysis import sample_standard_deviation
from graphica.core.i18n import tr
from graphica.gui.dataset_style_icon import make_dataset_style_icon
from graphica.gui.shell.icons import themed_icon
from graphica.gui.widgets import StatCard

LEFT_PANEL_WIDTH = 280
# ボタンの行に残すもの(左から)。曲線フィット・ピーク検出・多峰フィット・新規作成は「…」のメニューへ
FOOT_BUTTONS = (
    ("view_edit_data_button", "table"),
    ("duplicate_dataset_button", "copy"),
    ("auto_color_button", "palette"),
)
OVERFLOW_BUTTON_ACTIONS = (
    ("new_dataset_button", "新規作成..."),
    None,
    ("fit_curve_button", "曲線フィット..."),
    ("find_peaks_button", "ピーク検出..."),
    ("multi_peak_fit_button", "多峰フィット..."),
)


def _ghost(button, icon_name, size=30):
    """枠の無いアイコンのボタンにする(今のボタンをそのまま使う)。"""
    button.setProperty("iconOnly", True)
    button.setProperty("ghostButton", True)
    button.setText("")
    button.setFixedSize(size, size)
    button.setIconSize(QSize(18, 18))
    button.setIcon(themed_icon(icon_name))
    button.setProperty("iconName", icon_name)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def _take_all(layout):
    """レイアウトから部品を全部外す(部品は消さない。区切りの線は消す)。"""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None and widget.objectName() == "button_row_separator":
            widget.deleteLater()


def _dataset_items(tree):
    iterator = QTreeWidgetItemIterator(tree)
    while iterator.value():
        item = iterator.value()
        if item.data(0, Qt.ItemDataRole.UserRole) is not None:
            yield item
        iterator += 1


class DatasetPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setObjectName("dataset_page")
        self._app = app
        tree = app.ui.dataset_list_widget
        old_container = tree.parentWidget()
        app.ui.gridLayout_2.removeWidget(old_container)
        _take_all(old_container.layout())
        old_container.deleteLater()
        _take_all(app.ui.horizontalLayout_3)
        app.ui.gridLayout_2.removeItem(app.ui.horizontalLayout_3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 見出し
        head = QHBoxLayout()
        head.setContentsMargins(14, 0, 10, 0)
        head.setSpacing(6)
        title = QLabel(tr("データセット"))
        title.setObjectName("panel_title")
        self.count_label = QLabel("0")
        self.count_label.setObjectName("count_pill")
        self.count_label.setFixedHeight(18)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(title)
        head.addWidget(self.count_label)
        head.addStretch(1)
        head.addWidget(_ghost(app.new_folder_button, "folder-plus", size=28))
        add_button = app.ui.add_dataset_button
        add_button.setProperty("iconOnly", False)
        add_button.setProperty("primaryButton", True)
        add_button.setText(tr("追加"))
        add_button.setMinimumSize(0, 0)
        add_button.setMaximumSize(16777215, 16777215)
        add_button.setIconSize(QSize(14, 14))
        add_button.setIcon(themed_icon("plus", size=14, token="on_accent"))
        add_button.style().unpolish(add_button)
        add_button.style().polish(add_button)
        head.addWidget(add_button)
        head_box = QWidget()
        head_box.setFixedHeight(52)
        head_box.setLayout(head)
        layout.addWidget(head_box)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(12, 0, 12, 8)
        search_row.addWidget(app.dataset_search_edit)
        layout.addLayout(search_row)

        tree_row = QHBoxLayout()
        tree_row.setContentsMargins(8, 0, 8, 4)
        # 余った高さは一覧に回す(カードや見出しは中身の高さのまま)
        tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tree_row.addWidget(tree)
        layout.addLayout(tree_row, 1)

        # 選んでいるデータセットの統計
        stats_head = QHBoxLayout()
        stats_head.setContentsMargins(14, 6, 14, 6)
        stats_head.setSpacing(6)
        self.stats_swatch = QLabel()
        self.stats_name = QLabel("-")
        self.stats_name.setObjectName("stats_target_label")
        stats_head.addWidget(self.stats_swatch)
        stats_head.addWidget(self.stats_name, 1)
        layout.addLayout(stats_head)
        self.cards = {}
        layout.addWidget(self._card_row((("n", "点の数"), ("mean", "平均"), ("sd", "標準偏差"))))
        app.dataset_stats_advanced_row = self._card_row((("min", "最小"), ("max", "最大"), ("missing", "欠損")))
        layout.addWidget(app.dataset_stats_advanced_row)
        layout.addSpacing(6)

        # 操作のボタンの行
        foot = QFrame()
        foot.setObjectName("panel_foot")
        foot_layout = QHBoxLayout(foot)
        foot_layout.setContentsMargins(8, 6, 8, 6)
        foot_layout.setSpacing(2)
        for attr, icon_name in FOOT_BUTTONS:
            foot_layout.addWidget(_ghost(getattr(app, attr), icon_name))
        foot_layout.addStretch(1)
        overflow = app.dataset_overflow_button
        overflow.setText("")
        overflow.setProperty("ghostButton", True)
        overflow.setFixedSize(30, 30)
        overflow.setIconSize(QSize(18, 18))
        overflow.setIcon(themed_icon("dots"))
        overflow.setProperty("iconName", "dots")
        overflow.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self._extend_overflow_menu(overflow.menu())
        foot_layout.addWidget(overflow)
        foot_layout.addWidget(_ghost(app.ui.remove_dataset_button, "trash"))
        layout.addWidget(foot)

        # 移さなかったボタン(…のメニューから押す)は見せないだけで残す(シグナルとテストはそのまま)
        for entry in OVERFLOW_BUTTON_ACTIONS:
            if entry is not None:
                button = getattr(app, entry[0])
                button.setParent(self)
                button.hide()

        # ダークモードの切り替えでアイコンを作り直す表(_refresh_custom_svg_icons)を、移したボタンの形に合わせる
        icons = app._dataset_action_button_icons
        for attr, icon_name in FOOT_BUTTONS:
            button = getattr(app, attr)
            icons[button] = (icon_name, icons.get(button, (icon_name, ""))[1])
        icons.pop(add_button, None)

        self.setFixedWidth(LEFT_PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.timeout.connect(self.refresh_count)
        model = tree.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
            signal.connect(lambda *args: self._count_timer.start(0))
        self.refresh_count()
        self.set_stats(None)

    def _card_row(self, entries):
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        grid = QGridLayout(row)
        grid.setContentsMargins(12, 0, 12, 6)
        grid.setSpacing(6)
        for column, (key, label) in enumerate(entries):
            card = StatCard(tr(label))
            self.cards[key] = card
            grid.addWidget(card, 0, column)
        return row

    def _extend_overflow_menu(self, menu):
        """今の「…」のメニューの頭に、ボタンの行から外した操作を足す(押すと元のボタンを押したのと同じ)。"""
        first = menu.actions()[0] if menu.actions() else None
        self._overflow_actions = []
        for entry in OVERFLOW_BUTTON_ACTIONS:
            if entry is None:
                action = menu.insertSeparator(first)
            else:
                attr, text = entry
                button = getattr(self._app, attr)
                action = QAction(tr(text), menu)
                menu.insertAction(first, action)
                action.triggered.connect(button.click)
                self._overflow_actions.append((action, button))
        menu.insertSeparator(first)
        # ボタンの有効・無効は選択で変わるので、開くたびに写す
        menu.aboutToShow.connect(self._sync_overflow_enabled)

    def _sync_overflow_enabled(self):
        for action, button in self._overflow_actions:
            action.setEnabled(button.isEnabled())

    def refresh_count(self):
        self.count_label.setText(str(sum(1 for _ in _dataset_items(self._app.ui.dataset_list_widget))))

    def set_stats(self, dataset):
        """選んでいるデータセットの Y の統計(NaN は数えない)。None なら全部「-」。"""
        values = dict.fromkeys(("n", "mean", "sd", "min", "max", "missing"), "-")
        if dataset is None:
            self.stats_name.setText("-")
            self.stats_swatch.clear()
        else:
            self.stats_name.setText(dataset.name)
            self.stats_swatch.setPixmap(make_dataset_style_icon(dataset).pixmap(QSize(16, 10)))
            try:
                y = np.asarray(dataset.y_data, dtype=float)
                valid = y[~np.isnan(y)]
                values["missing"] = str(int(len(y) - len(valid)))
                if len(valid):
                    std = sample_standard_deviation(valid)
                    values.update(n=str(len(valid)), mean=f"{np.mean(valid):.4g}",
                                  sd="-" if np.isnan(std) else f"{std:.4g}",
                                  min=f"{np.min(valid):.4g}", max=f"{np.max(valid):.4g}")
            except (TypeError, ValueError):
                pass
        for key, card in self.cards.items():
            card.set_value(values[key])

    def refresh_icons(self):
        app = self._app
        for attr, icon_name in FOOT_BUTTONS:
            getattr(app, attr).setIcon(themed_icon(icon_name))
        app.new_folder_button.setIcon(themed_icon("folder-plus"))
        app.ui.remove_dataset_button.setIcon(themed_icon("trash"))
        app.dataset_overflow_button.setIcon(themed_icon("dots"))
        app.ui.add_dataset_button.setIcon(themed_icon("plus", size=14, token="on_accent"))
