"""CSV・TXT の日付の列(gui/workers.py parse_date_columns)。空でない値がすべて日付として読める文字の列だけを日付型にする。"""
import pandas as pd

from graphica.gui.workers import load_data_file_task, parse_date_columns


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_a_csv_date_column_becomes_dates(tmp_path):
    path = _write(tmp_path, "days.csv", "date,value\n2025/1/1,1.5\n2025/1/2,2.5\n2025/1/3,3.5\n")
    df = load_data_file_task(path)
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert df["date"].iloc[1] == pd.Timestamp("2025-01-02")
    assert df["value"].tolist() == [1.5, 2.5, 3.5]


def test_a_tab_separated_text_file_gets_the_same_rule(tmp_path):
    path = _write(tmp_path, "log.txt", "time\tT\n2025-01-01T10:00\t20.1\n2025-01-01T11:00\t20.4\n2025-01-02\t20.9\n")
    df = load_data_file_task(path)
    assert pd.api.types.is_datetime64_any_dtype(df["time"])
    assert df["time"].iloc[2] == pd.Timestamp("2025-01-02")


def test_blanks_become_missing_dates():
    df = parse_date_columns(pd.DataFrame({"d": ["2025-03-01", "", None, "2025-03-04"]}))
    assert pd.api.types.is_datetime64_any_dtype(df["d"])
    assert df["d"].isna().tolist() == [False, True, True, False]


def test_columns_that_are_not_all_dates_stay_text():
    df = parse_date_columns(pd.DataFrame({
        # 時刻だけの値は読んだ日の日付が補われるので日付にしない
        "clock": ["12:30", "13:00", "13:30"],
        "label": ["2025-01-01", "peak", "2025-01-03"],
        "zones": ["2025-01-01T00:00+09:00", "2025-01-01T00:00+00:00", "2025-01-02"],
        "names": ["a", "b", "c"],
        "number": [1.0, 2.0, 3.0],
        "empty": [None, "", " "],
    }))
    assert {c: str(t) for c, t in df.dtypes.items()} == {
        "clock": "object", "label": "object", "zones": "object", "names": "object", "number": "float64",
        "empty": "object",
    }


def test_date_columns_survive_saving_and_opening_a_project(tmp_path):
    from graphica.core.dataset import Dataset
    from graphica.models.project import ProjectModel

    df = load_data_file_task(_write(tmp_path, "days.csv", "date,value\n2025/1/1,1\n2025/1/2,2\n"))
    project = ProjectModel()
    project.datasets.append(Dataset(df=df, name="days", x_col_name="date", y_col_name="value"))
    path = str(tmp_path / "days.graphica")
    project.save_project(path)

    loaded = ProjectModel()
    loaded.load_project(path)
    restored = loaded.datasets[0].df
    assert pd.api.types.is_datetime64_any_dtype(restored["date"])
    assert restored["date"].tolist() == df["date"].tolist()
