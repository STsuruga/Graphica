"""フォームの行を「ウィジェットの次」に入れる補助(main_window._insert_form_row_after)。"""
import pytest
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QWidget

from graphica.gui.main_window import _insert_form_row_after


def _form_with_rows(*names):
    host = QWidget()
    form = QFormLayout(host)
    widgets = {}
    for name in names:
        widgets[name] = QLineEdit()
        form.addRow(QLabel(name), widgets[name])
    return host, form, widgets


def test_row_goes_right_after_the_anchor_field():
    host, form, widgets = _form_with_rows("a", "b", "c")
    new_field = QLineEdit()

    _insert_form_row_after(form, widgets["a"], QLabel("new"), new_field)

    assert form.getWidgetPosition(new_field)[0] == 1
    assert form.getWidgetPosition(widgets["b"])[0] == 2


def test_the_anchor_can_be_the_label():
    host, form, widgets = _form_with_rows("a", "b")
    label = form.labelForField(widgets["b"])
    new_field = QLineEdit()

    _insert_form_row_after(form, label, QLabel("new"), new_field)

    assert form.getWidgetPosition(new_field)[0] == 2


def test_a_missing_anchor_fails_loudly():
    host, form, _ = _form_with_rows("a")

    with pytest.raises(ValueError):
        _insert_form_row_after(form, QLineEdit(), QLabel("new"), QLineEdit())
