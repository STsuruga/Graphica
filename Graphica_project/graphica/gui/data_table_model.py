"""下のパネルの「データ表」: 選んだデータセットの表(読むだけ)。#・X・Y と、フィットがあればフィット値・残差。

行は描いている点と同じ visible_df(除外した行は出さない)。# はデータエディタ・カーソルの吹き出しと同じ、元の表の行の番号(1始まり)。
編集はデータエディタで行う。
"""
import numbers

import numpy as np
from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtGui import QBrush, QColor

from graphica.core.analysis import evaluate_saved_fit
from graphica.core.i18n import tr
from graphica.gui import theme

ROW_NUMBER_COLUMN = 0


def fit_result_for(dataset, datasets):
    """dataset のフィット結果。自分が持っていなければ、dataset から作った最後のフィットの曲線のもの。"""
    if dataset is None:
        return None
    if dataset.fit_result:
        return dataset.fit_result
    for other in reversed(list(datasets)):
        result = getattr(other, 'fit_result', None)
        if result and result.get('source_dataset_id') == dataset.dataset_id:
            return result
    return None


def fit_dataset_for(dataset, datasets):
    """fit_result_for と同じ規則で、フィットの文(fit_info)を持つデータセット。"""
    if dataset is None:
        return None
    if dataset.fit_result or dataset.fit_info:
        return dataset
    for other in reversed(list(datasets)):
        result = getattr(other, 'fit_result', None)
        if result and result.get('source_dataset_id') == dataset.dataset_id:
            return other
    return None


def _format(value):
    if value is None:
        return ""
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        if isinstance(value, float) and np.isnan(value):
            return ""
        return f"{value:.6g}"
    return str(value)


class DatasetTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._headers = []
        self._row_numbers = np.empty(0, dtype=int)
        self._columns = []  # 列ごとの値の並び(# の列を除く)
        self._residual_column = None
        self._highlighted_row = None

    def set_dataset(self, dataset, fit_result=None):
        self.beginResetModel()
        self._highlighted_row = None
        self._residual_column = None
        if dataset is None or getattr(dataset, 'data_kind', '1d') == '2d_grid' or dataset.df is None:
            self._headers, self._row_numbers, self._columns = [], np.empty(0, dtype=int), []
            self.endResetModel()
            return
        df = dataset.df
        visible = dataset.visible_df
        positions = df.index.get_indexer(visible.index)
        self._row_numbers = positions + 1
        x_name, y_name = dataset.x_col_name, dataset.y_col_name
        x_values = visible[x_name].tolist() if x_name in visible.columns else [None] * len(visible)
        y_values = visible[y_name].tolist() if y_name in visible.columns else [None] * len(visible)
        self._headers = ["#", x_name or "X", y_name or "Y"]
        self._columns = [x_values, y_values]
        fitted = self._fit_values(fit_result, x_values)
        if fitted is not None:
            y_numeric = np.asarray([v if isinstance(v, numbers.Real) else np.nan for v in y_values], dtype=float)
            residuals = y_numeric - fitted
            x_range = fit_result.get('x_range')
            if x_range:
                x_numeric = np.asarray([v if isinstance(v, numbers.Real) else np.nan for v in x_values], dtype=float)
                outside = (x_numeric < min(x_range)) | (x_numeric > max(x_range))
                residuals[outside] = np.nan
            self._headers += [tr("フィット値"), tr("残差")]
            self._columns += [fitted.tolist(), residuals.tolist()]
            self._residual_column = len(self._headers) - 1
        self.endResetModel()

    @staticmethod
    def _fit_values(fit_result, x_values):
        if not fit_result:
            return None
        try:
            x_numeric = np.asarray(x_values, dtype=float)
        except (TypeError, ValueError):
            return None
        return evaluate_saved_fit(fit_result, x_numeric)

    def row_for_number(self, row_number):
        """元の表の行の番号(1始まり)の、この表での行。出していなければ None。"""
        if row_number is None:
            return None
        found = np.nonzero(self._row_numbers == row_number)[0]
        return int(found[0]) if len(found) else None

    def set_highlighted_row(self, row):
        if row == self._highlighted_row:
            return
        previous, self._highlighted_row = self._highlighted_row, row
        for changed in (previous, row):
            if changed is not None and 0 <= changed < self.rowCount():
                self.dataChanged.emit(self.index(changed, 0), self.index(changed, self.columnCount() - 1))

    def highlighted_row(self):
        return self._highlighted_row

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self._row_numbers)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._headers[section] if 0 <= section < len(self._headers) else None
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter if section == ROW_NUMBER_COLUMN
                       else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def value(self, row, column):
        if column == ROW_NUMBER_COLUMN:
            return int(self._row_numbers[row])
        return self._columns[column - 1][row]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return _format(self.value(row, column))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter if column == ROW_NUMBER_COLUMN
                       else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            tokens = theme.current_tokens()
            if column == ROW_NUMBER_COLUMN:
                return QBrush(QColor(tokens["text_muted"]))
            if column == self._residual_column:
                value = self.value(row, column)
                if isinstance(value, float) and value < 0:
                    return QBrush(QColor(tokens["danger"]))
            return None
        if role == Qt.ItemDataRole.BackgroundRole and row == self._highlighted_row:
            return QBrush(theme.current_accent_soft_qcolor())
        return None
