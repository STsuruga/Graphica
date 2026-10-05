"""数値の列名(Excel の数値の見出しなど)。core/dataset.py の column_key / with_string_columns と、データセットでのそろえ方。

以前は数値の列名のまま持っていたため、保存(未保存の判定で辞書のキーを並べ替えて比べる)が
「float と str は比べられない」で失敗し、保存できたファイルも読み戻すと列が空になって開けず、
データエディタで列名を変えようとすると入力欄に数値を渡して落ちていた。
"""
import json

import numpy as np
import pandas as pd
import pytest

from graphica.core.dataset import Dataset, column_key, with_string_columns
from graphica.models.project import GraphicaJSONEncoder, ProjectModel


def _numeric_header_df():
    # pd.read_excel は数値の見出しを数値の列名にする
    return pd.DataFrame({1.5: [1.0, 2.0, 3.0], 2: [4.0, 5.0, 6.0], "Height/nm": [7.0, 8.0, 9.0]})


@pytest.mark.parametrize("column, key", [
    ("Height", "Height"), (1.5, "1.5"), (2, "2"), (2.0, "2.0"), (np.int64(3), "3"), (np.float64(0.25), "0.25"),
])
def test_column_key_matches_what_json_makes_of_a_dict_key(column, key):
    assert column_key(column) == key


def test_with_string_columns_leaves_the_callers_frame_alone():
    df = _numeric_header_df()
    converted = with_string_columns(df)
    assert list(converted.columns) == ["1.5", "2", "Height/nm"]
    assert list(df.columns) == [1.5, 2, "Height/nm"]
    text_only = pd.DataFrame({"a": [1]})
    assert with_string_columns(text_only) is text_only


def test_a_dataset_keeps_string_column_names_and_references():
    ds = Dataset(name="d", df=_numeric_header_df(), x_col_name=1.5, y_col_name=2)

    assert list(ds.df.columns) == ["1.5", "2", "Height/nm"]
    assert (ds.x_col_name, ds.y_col_name) == ("1.5", "2")
    assert list(ds.x_data) == [1.0, 2.0, 3.0]


def test_a_project_with_numeric_headers_saves_and_loads_back(tmp_path):
    project = ProjectModel()
    project.datasets.append(Dataset(name="d", df=_numeric_header_df(), x_col_name=1.5, y_col_name=2))
    path = tmp_path / "numeric.gra"

    project.content_fingerprint()  # 以前はここで TypeError
    project.save_project(str(path))
    loaded = ProjectModel()
    loaded.load_project(str(path))

    ds = loaded.datasets[0]
    assert list(ds.df.columns) == ["1.5", "2", "Height/nm"]
    assert list(ds.y_data) == [4.0, 5.0, 6.0]


def test_a_file_saved_with_numeric_column_names_still_opens(tmp_path):
    """修正前に書けてしまったファイル: columns は数値のまま、data と dtypes のキーは JSON で文字列になっている。"""
    project = ProjectModel()
    project.datasets.append(Dataset(name="d", df=pd.DataFrame({"a": [0.0]}), x_col_name="a", y_col_name="a"))
    payload = project._json_payload()
    payload['datasets'][0].update({
        'x_col_name': 1.5, 'y_col_name': 2,
        'df': {
            'columns': [1.5, 2, "Height/nm"],
            'index': [0, 1, 2],
            'index_dtype': 'int64',
            # json.dumps がキーを "1.5" / "2" にする(修正前の書き出しと同じ)
            'data': {1.5: [1.0, 2.0, 3.0], 2: [4.0, 5.0, 6.0], "Height/nm": [7.0, 8.0, 9.0]},
            'dtypes': {1.5: 'float64', 2: 'float64', "Height/nm": 'float64'},
        },
    })
    path = tmp_path / "old.gra"
    path.write_text(json.dumps(payload, cls=GraphicaJSONEncoder), encoding='utf-8')

    loaded = ProjectModel()
    loaded.load_project(str(path))

    ds = loaded.datasets[0]
    assert len(ds.df) == 3
    assert (ds.x_col_name, ds.y_col_name) == ("1.5", "2")
    assert list(ds.x_data) == [1.0, 2.0, 3.0]
    assert list(ds.y_data) == [4.0, 5.0, 6.0]


def test_renaming_the_z_column_follows_in_the_dataset():
    df = pd.DataFrame({"x": [0.0, 1.0], "y": [0.0, 1.0], "z": [5.0, 6.0]})
    ds = Dataset(name="map", df=df, x_col_name="x", y_col_name="y", z_col_name="z", data_kind="2d_grid")

    ds.rename_column("z", "intensity")

    assert ds.z_col_name == "intensity"


# --- 画面からの操作 ---

def test_renaming_a_numeric_header_in_the_data_editor_offers_it_as_text(qapp, monkeypatch):
    from graphica.gui import notify
    from graphica.gui.data_editor import DataEditorDialog

    ds = Dataset(name="d", df=_numeric_header_df(), x_col_name=1.5, y_col_name=2)
    offered = []
    monkeypatch.setattr(notify, "get_text", lambda *a, **k: offered.append(k.get('text')) or ("width", True))
    dialog = DataEditorDialog(ds)
    try:
        dialog._on_header_double_clicked(0)
    finally:
        dialog.close()

    assert offered == ["1.5"]
    assert ds.x_col_name == "width"


def test_reloading_an_excel_sheet_with_numeric_headers(tmp_path, monkeypatch):
    import graphica.gui.main_window as main_window_module
    from PySide6.QtWidgets import QApplication
    from tests.test_main_window import _make_isolated_plotter_app

    path = tmp_path / "numeric.xlsx"
    _numeric_header_df().to_excel(path, index=False)
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    df = pd.read_excel(path)
    ds = Dataset(name="xl", df=df.iloc[:1].copy(), x_col_name=1.5, y_col_name=2, source_file=str(path))
    window._add_dataset_with_undo(ds)
    QApplication.instance().processEvents()
    monkeypatch.setattr(main_window_module.QMessageBox, "warning",
                        lambda *a, **k: pytest.fail(f"warning shown: {a[1:]}"))

    window.transfer.reload_from_source()

    assert list(window.current_dataset().y_data) == [4.0, 5.0, 6.0]
