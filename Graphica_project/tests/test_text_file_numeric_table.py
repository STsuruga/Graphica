"""測定条件の行に挟まれた数値の表を持つテキストファイルの読み込み(JASCO の TXT など)。"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QDialog

import graphica.gui.notify as notify_module
from graphica.gui.dialogs import ColumnPreviewDialog
from graphica.gui.workers import find_numeric_table, read_data_file

JASCO_LIKE = (
    "TITLE\tsample\n"
    "DATA TYPE\tINFRARED SPECTRUM\n"
    "XUNITS\t1/CM\n"
    "YUNITS\t%T\n"
    "NPOINTS\t5\n"
    "XYDATA\n"
    "4000\t90.1\n"
    "3999.5\t90.2\n"
    "3999\t90.3\n"
    "3998.5\t90.4\n"
    "3998\t90.5\n"
    "\n"
    "##### Extended Information\n"
    "[Comments]\n"
    "試料\tKBr 錠剤\n"
)


@pytest.fixture
def jasco_file(tmp_path):
    path = tmp_path / "ir.txt"
    path.write_bytes(JASCO_LIKE.encode("cp932"))
    return path


def test_the_table_between_the_instrument_header_and_footer_is_found():
    table = find_numeric_table(JASCO_LIKE.splitlines())
    assert (table.first_line, table.stop_line, table.delimiter, table.header) == (6, 11, "\t", None)


def test_the_line_just_above_is_the_header_when_it_has_as_many_text_fields():
    lines = ["Instrument: A", "Wavenumber,Transmittance", "1,2", "3,4", "5,6", "end"]
    table = find_numeric_table(lines)
    assert (table.first_line, table.stop_line, table.delimiter) == (2, 5, ",")
    assert table.header == ["Wavenumber", "Transmittance"]


def test_too_short_a_run_is_not_a_table():
    assert find_numeric_table(["a,b", "1,2", "3,4"]) is None


def test_a_jasco_like_text_file_reads_as_numbers(jasco_file):
    df = read_data_file(str(jasco_file))
    assert list(df.columns) == ["列1", "列2"]
    assert all(pd.api.types.is_numeric_dtype(df[c]) for c in df.columns)
    assert df["列1"].tolist() == [4000, 3999.5, 3999, 3998.5, 3998]
    assert df["列2"].tolist() == [90.1, 90.2, 90.3, 90.4, 90.5]


@pytest.mark.parametrize("preamble, pandas_error", [
    ("Instrument:A\n", None),  # 1 列の表として読めてしまう(数値の列が無い)
    ("Instrument:A\nDate:2026-01-01\n", pd.errors.ParserError),  # 列数が合わず読めない
])
def test_a_preamble_above_the_header_is_skipped(tmp_path, preamble, pandas_error):
    path = tmp_path / "with_preamble.csv"
    path.write_text(preamble + "x,y\n1,2\n3,4\n5,6\n", encoding="utf-8")
    if pandas_error:
        with pytest.raises(pandas_error):
            pd.read_csv(path)
    df = read_data_file(str(path))
    assert list(df.columns) == ["x", "y"]
    assert df["y"].tolist() == [2, 4, 6]


@pytest.mark.parametrize("text", [
    "x,y\n1,2\n3,4\n5,6\n",
    "name,value\na,1\nb,2\nc,3\n",  # 文字の列があっても数値の列があれば今までどおり
    "name,kind\na,p\nb,q\nc,r\n",  # 数値の表が無ければ今までどおり
])
def test_files_that_already_read_are_read_as_before(tmp_path, text):
    path = tmp_path / "plain.csv"
    path.write_text(text, encoding="utf-8")
    pd.testing.assert_frame_equal(read_data_file(str(path)), pd.read_csv(path))


def test_the_preview_finds_the_table_and_says_so(jasco_file):
    dialog = ColumnPreviewDialog(pd.DataFrame(), "ir.txt", file_path=str(jasco_file))
    assert dialog.get_dataframe().shape == (5, 2)
    assert "7〜11 行目の数値の表" in dialog.info_label.text()
    assert dialog.get_selected_columns() == ("列1", "列2")


def test_the_preview_limits_rows_and_checks_types_for_text_files(jasco_file):
    dialog = ColumnPreviewDialog(pd.DataFrame(), "ir.txt", file_path=str(jasco_file))
    dialog.csv_nrows_spinbox.setValue(2)
    assert dialog.get_dataframe()["列1"].tolist() == [4000, 3999.5]
    assert dialog.check_types_button.isVisibleTo(dialog)


def test_a_header_row_set_by_hand_is_used_as_is(jasco_file):
    dialog = ColumnPreviewDialog(pd.DataFrame(), "ir.txt", file_path=str(jasco_file))
    dialog.csv_header_row_spinbox.setValue(6)
    assert list(dialog.get_dataframe().columns) == ["XYDATA"]
    assert "数値の表" not in dialog.info_label.text()


def test_a_y_column_mixing_text_and_numbers_is_refused_with_a_reason(monkeypatch):
    warnings = []
    monkeypatch.setattr(notify_module, "warning", lambda *args, **kwargs: warnings.append(args[2]))
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": ["1.0", "XYDATA", float("nan")]})
    dialog = ColumnPreviewDialog(df, "data.csv")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert len(warnings) == 1 and "「y」" in warnings[0] and "列の型を確認" in warnings[0]


def test_a_text_only_y_column_is_still_accepted(monkeypatch):
    monkeypatch.setattr(notify_module, "warning", lambda *args, **kwargs: pytest.fail("警告は出ない"))
    dialog = ColumnPreviewDialog(pd.DataFrame({"x": [1.0, 2.0], "y": ["a", "b"]}), "data.csv")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
