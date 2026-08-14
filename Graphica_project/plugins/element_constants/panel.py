# plugins/element_constants/panel.py
"""元素・物理定数テーブル(項目P-805)のドックパネルUI。"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from .data import ELEMENT_COLUMNS, CONSTANT_COLUMNS, find_element, find_constant

MODE_ELEMENT = "元素"
MODE_CONSTANT = "物理定数"


class ElementConstantsPanel(QWidget):
    """
    「元素」/「物理定数」を切り替えて検索できる、常設の参照パネル。
    現在選択中のデータセットとは無関係に、いつでも検索できる
    (register_analyzerではなくregister_panelで提供している理由と同じ)。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([MODE_ELEMENT, MODE_CONSTANT])
        self.mode_combo.currentTextChanged.connect(self._on_search_changed)
        search_row.addWidget(self.mode_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("元素記号/原子番号/英語名、または定数名で検索")
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_edit, 1)
        layout.addLayout(search_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.result_table = QTableWidget()
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.verticalHeader().setVisible(False)
        layout.addWidget(self.result_table)

        self._on_search_changed()

    def _on_search_changed(self, _text=None):
        mode = self.mode_combo.currentText()
        query = self.search_edit.text()

        if mode == MODE_ELEMENT:
            self._populate_table(ELEMENT_COLUMNS, find_element(query) if query else [])
        else:
            self._populate_table(CONSTANT_COLUMNS, find_constant(query) if query else [])

        if not query:
            self.status_label.setText("検索語を入力してください")
        elif self.result_table.rowCount() == 0:
            self.status_label.setText("該当なし")
        else:
            self.status_label.setText(f"{self.result_table.rowCount()}件見つかりました")

    def _populate_table(self, columns, rows):
        self.result_table.setColumnCount(len(columns))
        self.result_table.setHorizontalHeaderLabels(columns)
        self.result_table.setRowCount(len(rows))
        for row_index, row_values in enumerate(rows):
            for col_index, value in enumerate(row_values):
                self.result_table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
