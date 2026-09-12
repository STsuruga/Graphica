# tests/test_split_by_column.py
"""
カテゴリ列による系列の自動分割(改善ボード D-1)に対するテスト。

1つのファイルに「試料名」「条件」「測定日」のような区分列があり、その値ごとに
系列を分けたい(long形式データの取り込み)ケースへの対応。従来は「行フィルタ」を
条件の数だけ手作業で繰り返すしかなかった。
"""
import matplotlib
matplotlib.use("Agg")
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

import gui.main_window as main_window_module
import gui.mixins.dataset_mixin as dataset_mixin_module
from gui.main_window import PlotterApp
from core.dataset import Dataset
from core.analysis import split_dataframe_by_column


# =============================================================================
# core/analysis.py の純粋関数
# =============================================================================

def _long_df():
    """3条件が縦に積まれた long 形式のデータ。"""
    return pd.DataFrame({
        "x": [1.0, 2.0, 1.0, 2.0, 1.0, 2.0],
        "y": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        "sample": ["B", "B", "A", "A", "C", "C"],
    })


def test_splits_into_one_group_per_distinct_value():
    result = split_dataframe_by_column(_long_df(), "sample")

    assert result['n_groups'] == 3
    assert [label for label, _ in result['groups']] == ["B", "A", "C"]


def test_group_order_follows_first_appearance_not_sort_order():
    """pandasのgroupbyの既定(値のソート順)ではなく、ファイル中での初出順にする。
    測定順・濃度順のようにファイルの並び自体に意味があることが多いため。"""
    result = split_dataframe_by_column(_long_df(), "sample")

    labels = [label for label, _ in result['groups']]
    assert labels == ["B", "A", "C"]
    assert labels != sorted(labels)


def test_each_group_keeps_only_its_own_rows():
    result = split_dataframe_by_column(_long_df(), "sample")
    groups = dict(result['groups'])

    assert list(groups["A"]["y"]) == [30.0, 40.0]
    assert list(groups["B"]["y"]) == [10.0, 20.0]
    assert list(groups["C"]["y"]) == [50.0, 60.0]


def test_each_group_keeps_every_column():
    result = split_dataframe_by_column(_long_df(), "sample")
    _label, sub_df = result['groups'][0]

    assert list(sub_df.columns) == ["x", "y", "sample"]


def test_group_index_is_reset():
    """元のindexラベルを引きずると、新しいデータセットのマスクや行番号表示が
    分かりにくくなるため0始まりに振り直す。"""
    result = split_dataframe_by_column(_long_df(), "sample")
    groups = dict(result['groups'])

    assert list(groups["A"].index) == [0, 1]


def test_rows_with_a_missing_split_value_are_dropped_and_counted():
    """黙って減らすと「点が足りない」と気づきにくいので、件数を返す。"""
    df = pd.DataFrame({
        "x": [1.0, 2.0, 3.0],
        "y": [10.0, 20.0, 30.0],
        "sample": ["A", None, "B"],
    })
    result = split_dataframe_by_column(df, "sample")

    assert result['n_groups'] == 2
    assert result['n_dropped'] == 1


def test_numeric_split_column_labels_are_readable():
    """numpyのスカラ型をそのままstr()すると 'np.float64(1.5)' になりうる。"""
    df = pd.DataFrame({
        "x": [1.0, 2.0, 3.0],
        "y": [10.0, 20.0, 30.0],
        "conc": [1.5, 1.5, 2.0],
    })
    result = split_dataframe_by_column(df, "conc")

    assert [label for label, _ in result['groups']] == ["1.5", "2"]


def test_single_valued_column_yields_one_group():
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0], "c": ["same", "same"]})
    result = split_dataframe_by_column(df, "c")

    assert result['n_groups'] == 1


def test_unknown_column_raises():
    with pytest.raises(ValueError, match="存在しません"):
        split_dataframe_by_column(_long_df(), "missing")


# =============================================================================
# GUI 経路
# =============================================================================

def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 600)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _choose_column(monkeypatch, column, accepted=True):
    """QInputDialog.getItem をモックする。

    ★ モックし忘れると、offscreen環境でもモーダルダイアログの exec() が
    イベントループを無期限にブロックする(このプロジェクトで実際に一度
    踏んでいる。docs/CURRENT_STATE.md の C-407 の記述参照)。
    """
    monkeypatch.setattr(
        dataset_mixin_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (column, accepted)),
    )


def _silence_message_boxes(monkeypatch, question_answer=None):
    monkeypatch.setattr(
        dataset_mixin_module.QMessageBox, "information",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        dataset_mixin_module.QMessageBox, "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    if question_answer is not None:
        monkeypatch.setattr(
            dataset_mixin_module.QMessageBox, "question",
            staticmethod(lambda *a, **k: question_answer),
        )


def _add_source(window, df=None, name="measurements"):
    ds = Dataset(name=name, df=df if df is not None else _long_df(),
                 x_col_name="x", y_col_name="y")
    window._add_dataset(ds, select=True)
    return ds


def _names(window):
    return [d.name for d in window.project.datasets]


def test_split_adds_one_dataset_per_group(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_source(window)
        _choose_column(monkeypatch, "sample")
        _silence_message_boxes(monkeypatch)

        window._on_split_dataset_by_column()

        assert _names(window) == [
            "measurements",
            "measurements (B)",
            "measurements (A)",
            "measurements (C)",
        ]
    finally:
        window.close()


def test_split_keeps_the_original_dataset(tmp_path, monkeypatch):
    """非破壊: 元のデータセットは残す(不要なら削除すればよく、削除も
    改善ボード A-3 でUndo可能になっている)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        source = _add_source(window)
        _choose_column(monkeypatch, "sample")
        _silence_message_boxes(monkeypatch)

        window._on_split_dataset_by_column()

        assert window.project.datasets[0] is source
        assert len(source.df) == 6
    finally:
        window.close()


def test_split_inherits_the_x_and_y_columns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_source(window)
        _choose_column(monkeypatch, "sample")
        _silence_message_boxes(monkeypatch)

        window._on_split_dataset_by_column()

        for ds in window.project.datasets[1:]:
            assert ds.x_col_name == "x"
            assert ds.y_col_name == "y"
    finally:
        window.close()


def test_split_assigns_distinct_colours(tmp_path, monkeypatch):
    """既定色のままだと全系列が同じ色になり、分割した意味がほとんど無くなる。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_source(window)
        _choose_column(monkeypatch, "sample")
        _silence_message_boxes(monkeypatch)

        window._on_split_dataset_by_column()

        colours = [ds.color for ds in window.project.datasets[1:]]
        assert len(set(colours)) == 3
    finally:
        window.close()


def test_split_records_provenance(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        source = _add_source(window)
        _choose_column(monkeypatch, "sample")
        _silence_message_boxes(monkeypatch)

        window._on_split_dataset_by_column()

        prov = window.project.datasets[1].provenance
        assert prov['operation'] == 'split_by_column'
        assert prov['params']['split_column'] == 'sample'
        assert prov['params']['group_value'] == 'B'
        assert prov['source_dataset_ids'] == [source.dataset_id]
    finally:
        window.close()


def test_the_whole_split_undoes_in_one_step(tmp_path, monkeypatch):
    """N件の追加を beginMacro でまとめ、Undo 1回で元に戻ること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_source(window)
        _choose_column(monkeypatch, "sample")
        _silence_message_boxes(monkeypatch)

        window._on_split_dataset_by_column()
        assert len(window.project.datasets) == 4

        window.undo_stack.undo()

        assert _names(window) == ["measurements"]
    finally:
        window.close()


def test_redo_restores_every_split_series(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_source(window)
        _choose_column(monkeypatch, "sample")
        _silence_message_boxes(monkeypatch)

        window._on_split_dataset_by_column()
        window.undo_stack.undo()
        window.undo_stack.redo()

        assert len(window.project.datasets) == 4
    finally:
        window.close()


def test_cancelling_the_column_dialog_changes_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_source(window)
        _choose_column(monkeypatch, "sample", accepted=False)
        _silence_message_boxes(monkeypatch)
        before = window.undo_stack.count()

        window._on_split_dataset_by_column()

        assert _names(window) == ["measurements"]
        assert window.undo_stack.count() == before
    finally:
        window.close()


def test_single_valued_column_adds_nothing_and_explains_why(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0], "c": ["same", "same"]})
        _add_source(window, df=df)
        _choose_column(monkeypatch, "c")
        shown = []
        monkeypatch.setattr(
            dataset_mixin_module.QMessageBox, "information",
            staticmethod(lambda *a, **k: shown.append(a) or QMessageBox.StandardButton.Ok),
        )

        window._on_split_dataset_by_column()

        assert _names(window) == ["measurements"]
        assert shown, "1種類しかない場合は理由を案内すること"
    finally:
        window.close()


def test_many_groups_asks_for_confirmation_first(tmp_path, monkeypatch):
    """連続値の列を誤って選ぶと大量の系列ができてしまうため、作る前に確認する。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        n = window.SPLIT_BY_COLUMN_CONFIRM_THRESHOLD + 5
        df = pd.DataFrame({
            "x": list(range(n)), "y": list(range(n)),
            "value": [float(i) for i in range(n)],
        })
        _add_source(window, df=df)
        _choose_column(monkeypatch, "value")
        _silence_message_boxes(monkeypatch, question_answer=QMessageBox.StandardButton.No)

        window._on_split_dataset_by_column()

        assert _names(window) == ["measurements"]
    finally:
        window.close()


def test_many_groups_proceeds_when_confirmed(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        n = window.SPLIT_BY_COLUMN_CONFIRM_THRESHOLD + 5
        df = pd.DataFrame({
            "x": list(range(n)), "y": list(range(n)),
            "value": [float(i) for i in range(n)],
        })
        _add_source(window, df=df)
        _choose_column(monkeypatch, "value")
        _silence_message_boxes(monkeypatch, question_answer=QMessageBox.StandardButton.Yes)

        window._on_split_dataset_by_column()

        assert len(window.project.datasets) == 1 + n
    finally:
        window.close()


def test_menu_entry_lives_in_the_data_processing_submenu(tmp_path, monkeypatch):
    """改善ボード C-2 で作った「データ処理」サブメニューに入っていること。"""
    from PySide6.QtCore import QPoint
    import tests.test_dataset_mixin as dataset_mixin_tests

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_source(window)
        dataset_mixin_tests._patch_recording_menu(monkeypatch)
        window._on_dataset_tree_context_menu(QPoint(0, 0))
        root = dataset_mixin_tests._RecordingMenu.last_instance

        data_proc = None
        for action in root.actions():
            if action.menu() is not None and action.text() == "データ処理":
                data_proc = action.menu()
        assert data_proc is not None
        texts = [a.text() for a in data_proc.actions() if not a.isSeparator()]
        assert "列の値で系列に分割..." in texts
    finally:
        window.close()
