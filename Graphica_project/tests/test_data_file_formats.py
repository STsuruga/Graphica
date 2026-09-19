# tests/test_data_file_formats.py
"""
ビルトインで読めるデータファイル形式(v1.4.2)。

ファイルを開くダイアログの一覧には以前から *.txt と *.xls が出ていたが、
読み込み側は .txt を「未対応のファイル形式」として弾き、.xls は openpyxl
固定で読もうとして失敗していた。.txt は CSV と同じ経路(文字コード・区切り文字の
自動判定)で、.xls は xlrd で読む。ダイアログのフィルタ・ドラッグ&ドロップ・
フォルダ一括インポート・プレビュー・元ファイルからの再読み込みが、すべて
同じ拡張子一覧(gui/workers.py)を参照していることもここで固定する。
"""
import os

import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog

import graphica.gui.main_window as main_window_module
from graphica.core.dataset import Dataset
from graphica.core.excel_utils import find_unevaluated_formula_cells
from graphica.gui.dialogs import ColumnPreviewDialog
from graphica.gui.main_window import PlotterApp, SUPPORTED_DATA_FILE_EXTENSIONS
from graphica.gui.workers import (
    BUILTIN_DATA_FILE_EXTENSIONS,
    excel_engine_for,
    load_data_file_task,
    pandas_separator,
    read_data_file,
)

LEGACY_XLS = os.path.join(os.path.dirname(__file__), "fixtures", "legacy_two_sheets.xls")


def _write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return str(path)


# --- 拡張子一覧 ---

def test_every_advertised_extension_is_readable():
    assert set(BUILTIN_DATA_FILE_EXTENSIONS) == {".csv", ".txt", ".xlsx", ".xls"}


def test_drag_and_drop_accepts_the_same_extensions_as_the_reader():
    assert SUPPORTED_DATA_FILE_EXTENSIONS == BUILTIN_DATA_FILE_EXTENSIONS


@pytest.mark.parametrize("name, engine", [
    ("a.xls", "xlrd"), ("A.XLS", "xlrd"), ("a.xlsx", "openpyxl"), ("a.XLSX", "openpyxl"),
])
def test_excel_engine_is_chosen_by_extension(name, engine):
    assert excel_engine_for(name) == engine


def test_whitespace_separator_collapses_runs_of_spaces():
    assert pandas_separator(" ") == (r"\s+", "python")
    assert pandas_separator(",") == (",", "c")
    assert pandas_separator("\t") == ("\t", "c")


# --- 区切り文字付きテキスト(.csv / .txt) ---

@pytest.mark.parametrize("name, text", [
    ("comma.csv", "x,y\n1,2\n3,4\n"),
    ("semicolon.csv", "x;y\n1;2\n3;4\n"),
    ("tab.csv", "x\ty\n1\t2\n3\t4\n"),
    ("tab.txt", "x\ty\n1\t2\n3\t4\n"),
    ("comma.txt", "x,y\n1,2\n3,4\n"),
    ("aligned.txt", "x    y\n1    2\n3    4\n"),
])
def test_delimited_text_files_are_read_into_two_columns(tmp_path, name, text):
    df = read_data_file(_write(tmp_path, name, text))
    assert list(df.columns) == ["x", "y"]
    assert df["y"].tolist() == [2, 4]


def test_shift_jis_txt_is_decoded(tmp_path):
    path = _write(tmp_path, "sjis.txt", "時間\t温度\n1\t20.5\n2\t21.0\n", encoding="cp932")
    df = read_data_file(path)
    assert list(df.columns) == ["時間", "温度"]


def test_tab_separated_file_passes_the_two_column_check(tmp_path):
    """以前はカンマ固定で読んで1列に潰れ、ここで弾かれていた。"""
    df = load_data_file_task(_write(tmp_path, "tab.csv", "a\tb\n1\t2\n"))
    assert df.shape == (1, 2)


def test_unknown_extension_is_still_rejected(tmp_path):
    with pytest.raises(ValueError, match="未対応"):
        read_data_file(_write(tmp_path, "data.dat", "x,y\n1,2\n"))


# --- Excel(.xlsx / .xls) ---

def test_legacy_xls_is_read_with_xlrd():
    df = read_data_file(LEGACY_XLS)
    assert list(df.columns) == ["時間 (s)", "温度"]
    assert df["温度"].tolist() == [20.0, 21.5, 23.0, 24.5, 26.0]


def test_xlsx_is_still_read(tmp_path):
    path = str(tmp_path / "book.xlsx")
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(path, index=False)
    assert read_data_file(path)["b"].tolist() == [3, 4]


def test_formula_scan_skips_xls_without_logging_an_error(caplog):
    with caplog.at_level("ERROR"):
        assert find_unevaluated_formula_cells(LEGACY_XLS) == (False, [], True)
    assert not caplog.records


# --- 列の選択ダイアログ ---

def test_preview_dialog_lists_xls_sheets():
    dlg = ColumnPreviewDialog(read_data_file(LEGACY_XLS), "legacy.xls", file_path=LEGACY_XLS)
    assert dlg.is_excel is True
    assert dlg.sheet_names == ["測定1", "測定2"]


def test_preview_dialog_can_switch_xls_sheets():
    dlg = ColumnPreviewDialog(read_data_file(LEGACY_XLS), "legacy.xls", file_path=LEGACY_XLS)
    dlg.sheet_combo.setCurrentText("測定2")
    assert list(dlg.get_dataframe().columns) == ["x", "y"]


def test_preview_dialog_treats_txt_like_csv(tmp_path):
    path = _write(tmp_path, "tab.txt", "x\ty\n1\t2\n")
    dlg = ColumnPreviewDialog(read_data_file(path), "tab.txt", file_path=path)
    assert dlg.is_csv is True
    assert list(dlg.get_dataframe().columns) == ["x", "y"]


def test_preview_dialog_whitespace_matches_the_initial_read(tmp_path):
    path = _write(tmp_path, "aligned.txt", "x    y\n1    2\n")
    dlg = ColumnPreviewDialog(read_data_file(path), "aligned.txt", file_path=path)
    assert list(dlg.get_dataframe().columns) == ["x", "y"]


# --- メインウィンドウの各入口 ---

@pytest.fixture
def window(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    w = PlotterApp(run_startup_checks=False, tab_id=2)
    QApplication.instance().processEvents()
    yield w
    w.close()


def test_open_dialog_filter_lists_exactly_the_readable_extensions(window, monkeypatch):
    captured = {}

    def fake_open(parent, caption, directory, filter_text):
        captured["filter"] = filter_text
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(fake_open))
    window._on_add_dataset()
    data_filter = captured["filter"].split(";;")[0]
    for ext in BUILTIN_DATA_FILE_EXTENSIONS:
        assert f"*{ext}" in data_filter


def test_drop_queue_accepts_txt_and_xls(window, monkeypatch, tmp_path):
    queued = []
    monkeypatch.setattr(window, "_process_next_queued_file", lambda: queued.append(True))
    warnings = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    window._queue_data_files([
        _write(tmp_path, "a.txt", "x\ty\n1\t2\n"), LEGACY_XLS, _write(tmp_path, "b.dat", "x"),
    ])
    assert len(warnings) == 1  # b.dat だけが弾かれる
    assert "b.dat" in str(warnings[0])
    assert "a.txt" not in str(warnings[0]) and "legacy_two_sheets.xls" not in str(warnings[0])


def test_reload_from_source_reads_an_xls_sheet(window, monkeypatch):
    df = pd.read_excel(LEGACY_XLS, sheet_name="測定2", engine="xlrd")
    ds = Dataset(name="legacy", df=df.iloc[:1].copy(), x_col_name="x", y_col_name="y",
                 source_file=LEGACY_XLS, source_sheet="測定2")
    window._add_dataset_with_undo(ds)
    QApplication.instance().processEvents()
    monkeypatch.setattr(main_window_module.QMessageBox, "warning",
                        lambda *a, **k: pytest.fail(f"warning shown: {a[1:]}"))
    window._on_reload_dataset_from_source()
    assert len(window._get_current_dataset().df) == 3
