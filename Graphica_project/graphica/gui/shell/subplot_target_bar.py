"""「軸」タブの先頭の、編集するサブプロットを選ぶ行。グラフの並びを小さな升目で見せ、押して選ぶ。

値の持ち主は今までどおり app.active_axis_combo(隠して中に置く)。自由配置や升目が多すぎるときは、そのコンボを出す。
"""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from graphica.core.i18n import tr
from graphica.gui import theme

# これより多い升目は小さすぎて押せないので、プルダウンにする
MAX_GRID_CELLS = 9
CELL_WIDTH = 26
CELL_HEIGHT = 18
CELL_GAP = 3


class SubplotGrid(QWidget):
    """rows × cols の升目。押した升目の番号(左上から行ごと)を cellClicked で出す。"""

    cellClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows, self._cols, self._current = 1, 1, 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_grid(self, rows, cols, current):
        if (rows, cols, current) != (self._rows, self._cols, self._current):
            self._rows, self._cols, self._current = rows, cols, current
            self.updateGeometry()
            self.update()

    def sizeHint(self):
        return QSize(self._cols * CELL_WIDTH + (self._cols - 1) * CELL_GAP,
                     self._rows * CELL_HEIGHT + (self._rows - 1) * CELL_GAP)

    def _cell_rect(self, index):
        row, col = divmod(index, self._cols)
        return QRectF(col * (CELL_WIDTH + CELL_GAP) + 0.5, row * (CELL_HEIGHT + CELL_GAP) + 0.5,
                      CELL_WIDTH - 1, CELL_HEIGHT - 1)

    def cell_at(self, pos):
        for index in range(self._rows * self._cols):
            if self._cell_rect(index).contains(pos):
                return index
        return -1

    def mousePressEvent(self, event):
        index = self.cell_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and index >= 0:
            self.cellClicked.emit(index)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        tokens = theme.current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2))
        for index in range(self._rows * self._cols):
            rect = self._cell_rect(index)
            selected = index == self._current
            painter.setPen(QPen(QColor(tokens["accent"] if selected else tokens["border_strong"]), 1))
            painter.setBrush(theme.current_accent_soft_qcolor() if selected else Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 4, 4)
            font.setBold(selected)
            painter.setFont(font)
            painter.setPen(QColor(tokens["accent_fg"] if selected else tokens["text_secondary"]))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), str(index + 1))
        painter.end()


class SubplotTargetBar(QWidget):
    """「対象」+ 升目(かプルダウン)+ 選んでいるプロットの名前と系列の数。サブプロットが1つなら出さない。"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setObjectName("subplot_target_bar")
        self._app = app
        self.combo = app.active_axis_combo
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 10)
        layout.setSpacing(10)
        caption = QLabel(tr("対象"))
        caption.setObjectName("subplot_target_caption")
        layout.addWidget(caption, 0, Qt.AlignmentFlag.AlignVCenter)
        self.grid = SubplotGrid(self)
        self.grid.setToolTip(tr("編集するサブプロットを選ぶ"))
        self.grid.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.grid, 0, Qt.AlignmentFlag.AlignVCenter)
        self.combo.setParent(self)
        layout.addWidget(self.combo, 1)
        names = QVBoxLayout()
        names.setContentsMargins(0, 0, 0, 0)
        names.setSpacing(0)
        self.name_label = QLabel()
        self.name_label.setObjectName("subplot_target_name")
        self.detail_label = QLabel()
        self.detail_label.setObjectName("subplot_target_detail")
        names.addWidget(self.name_label)
        names.addWidget(self.detail_label)
        layout.addLayout(names, 1)
        self.combo.currentIndexChanged.connect(lambda _index: self.refresh())

    def _grid_shape(self):
        """(行, 列)。升目で見せられないとき(自由配置・多すぎる)は None。"""
        app = self._app
        if getattr(app.project, 'layout_mode', 'grid') == 'free':
            return None
        rows, cols = app.subplot_rows_spinbox.value(), app.subplot_cols_spinbox.value()
        if rows * cols > MAX_GRID_CELLS or rows * cols != self.combo.count():
            return None
        return rows, cols

    def _on_cell_clicked(self, index):
        if 0 <= index < self.combo.count():
            self.combo.setCurrentIndex(index)

    def refresh(self):
        count = self.combo.count()
        self.setVisible(count > 1)
        if count <= 1:
            return
        current = max(0, self.combo.currentIndex())
        shape = self._grid_shape()
        self.grid.setVisible(shape is not None)
        self.name_label.setVisible(shape is not None)
        self.detail_label.setVisible(shape is not None)
        self.combo.setVisible(shape is None)
        if shape is None:
            return
        rows, cols = shape
        self.grid.set_grid(rows, cols, current)
        self.name_label.setText(self.combo.itemText(current))
        series = sum(1 for ds in self._app.project.datasets if ds.subplot_target == current)
        row, col = divmod(current, cols)
        self.detail_label.setText(tr("{series} 系列 · {row} 行 {col} 列").format(series=series, row=row + 1, col=col + 1))
