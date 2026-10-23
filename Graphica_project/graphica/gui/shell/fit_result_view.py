"""下のパネルの「フィット結果」: パラメータ・値・標準誤差・相対誤差の表と、コピーのボタン。

表は保存したフィット結果(fit_result)から作る。表にできない結果(パラメータの無いもの)は、
フィットのときに作った文章(fit_info)をそのまま出す。どちらも保存の形式には触れない。
"""
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from graphica.core.fit_models import fit_type_label
from graphica.core.i18n import tr
from graphica.gui import motion

# 見せる値は誤差の有効数字に合わせて丸める(コピーは丸めない)
ERROR_SIGNIFICANT_DIGITS = 2
PLAIN_SIGNIFICANT_DIGITS = 6
COPY_SIGNIFICANT_DIGITS = 10
TABLE_COLUMNS = ("パラメータ", "値", "標準誤差", "相対誤差")


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def format_value_and_error(value, error):
    """(値, 誤差) の表示の文字。誤差があれば誤差の有効数字2桁の位まで値を丸める。"""
    if not _finite(value):
        return str(value), ""
    if not _finite(error) or error <= 0:
        return f"{value:.{PLAIN_SIGNIFICANT_DIGITS}g}", ""
    decimals = ERROR_SIGNIFICANT_DIGITS - 1 - math.floor(math.log10(error))
    if decimals > 0 and abs(value) < 1e6:
        return f"{value:.{decimals}f}", f"± {error:.{decimals}f}"
    return f"{value:.{PLAIN_SIGNIFICANT_DIGITS}g}", f"± {error:.{ERROR_SIGNIFICANT_DIGITS}g}"


def relative_error_text(value, error):
    if not (_finite(value) and _finite(error)) or value == 0 or error <= 0:
        return ""
    return f"{abs(error / value) * 100:.2g} %"


def fit_table_rows(fit_result):
    """[(名前, 値, 誤差, 固定か)]。表にできない結果なら空。"""
    if not fit_result:
        return []
    names = list(fit_result.get('param_names') or [])
    values = list(fit_result.get('params') or [])
    errors = list(fit_result.get('param_errors') or [])
    if not names or len(names) != len(values):
        return []
    fixed = fit_result.get('fixed_params') or {}
    errors += [None] * (len(values) - len(errors))
    return [(name, value, error, name in fixed) for name, value, error in zip(names, values, errors)]


def fit_title(fit_result):
    if fit_result.get('fit_type') == 'multi_peak':
        return tr("多峰分離 ({kind} × {count})").format(kind=fit_result.get('component_type', ""),
                                                      count=fit_result.get('n_components', ""))
    label = fit_type_label(fit_result, "")
    if fit_result.get('custom_formula'):
        return f"{label}: {fit_result['custom_formula']}"
    return str(label)


def table_tsv(fit_result):
    """表をタブ区切りで(Excel にそのまま貼れる)。値は丸めない。"""
    lines = ["\t".join(tr(column) for column in TABLE_COLUMNS)]
    for name, value, error, fixed in fit_table_rows(fit_result):
        error_text = tr("固定") if fixed else (f"{error:.{COPY_SIGNIFICANT_DIGITS}g}" if _finite(error) else "")
        relative = "" if fixed else relative_error_text(value, error).replace(" %", "")
        lines.append("\t".join((name, f"{value:.{COPY_SIGNIFICANT_DIGITS}g}", error_text, relative)))
    r_squared = fit_result.get('r_squared')
    if _finite(r_squared):
        lines.append(f"R²\t{r_squared:.{COPY_SIGNIFICANT_DIGITS}g}")
    return "\n".join(lines)


def values_tsv(fit_result):
    return "\t".join(f"{value:.{COPY_SIGNIFICANT_DIGITS}g}" for _name, value, _error, _fixed in fit_table_rows(fit_result))


class FitResultView(QWidget):
    def __init__(self, text_view, parent=None):
        super().__init__(parent)
        self.setObjectName("fit_result_view")
        self._fit_result = None
        self._text_view = text_view

        self.title_label = QLabel()
        self.title_label.setObjectName("fit_result_title")
        self.detail_label = QLabel()
        self.detail_label.setProperty("hint", True)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.detail_label, 1)

        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setObjectName("fit_result_table")
        self.table.setHorizontalHeaderLabels([tr(column) for column in TABLE_COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setHighlightSections(False)
        for column in range(1, len(TABLE_COLUMNS)):
            self.table.horizontalHeaderItem(column).setTextAlignment(
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.table.horizontalHeaderItem(0).setTextAlignment(
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

        self.copy_table_button = QPushButton(tr("表をコピー"))
        self.copy_table_button.setToolTip(tr("タブ区切りでコピー(Excel にそのまま貼れます)"))
        self.copy_values_button = QPushButton(tr("値だけコピー"))
        self.copy_values_button.setToolTip(tr("パラメータの値だけを、タブ区切りの1行で"))
        self.copy_text_button = QPushButton(tr("文章でコピー"))
        self.copy_table_button.clicked.connect(lambda: self._copy(table_tsv(self._fit_result)))
        self.copy_values_button.clicked.connect(lambda: self._copy(values_tsv(self._fit_result)))
        self.copy_text_button.clicked.connect(lambda: self._copy(self._text_view.toPlainText()))
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        for button in (self.copy_table_button, self.copy_values_button, self.copy_text_button):
            buttons.addWidget(button)
        buttons.addStretch(1)

        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(14, 8, 14, 8)
        table_layout.setSpacing(6)
        table_layout.addLayout(title_row)
        table_layout.addWidget(self.table, 1)
        table_layout.addLayout(buttons)

        self.stack = QStackedWidget()
        self.stack.addWidget(table_page)
        self.stack.addWidget(text_view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.set_result(None)

    def _copy(self, text):
        if text:
            QGuiApplication.clipboard().setText(text)
            motion.toast(self, tr("コピーしました"))

    def set_result(self, fit_result):
        """表にできる結果なら表を、そうでなければ文章(フィットが無ければ案内)を出す。"""
        self._fit_result = fit_result
        rows = fit_table_rows(fit_result)
        if not rows:
            self.stack.setCurrentWidget(self._text_view)
            return
        self.stack.setCurrentIndex(0)
        self.title_label.setText(fit_title(fit_result))
        points = len(fit_result.get('residuals') or [])
        self.detail_label.setText(tr("{points} 点").format(points=points) if points else "")
        self.table.setRowCount(len(rows))
        for row, (name, value, error, fixed) in enumerate(rows):
            value_text, error_text = format_value_and_error(value, None if fixed else error)
            cells = (name, value_text, tr("固定") if fixed else error_text,
                     "" if fixed else relative_error_text(value, error))
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                align = Qt.AlignmentFlag.AlignLeft if column == 0 else Qt.AlignmentFlag.AlignRight
                item.setTextAlignment(int(align | Qt.AlignmentFlag.AlignVCenter))
                self.table.setItem(row, column, item)
