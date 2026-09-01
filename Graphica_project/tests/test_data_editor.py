# tests/test_data_editor.py
"""gui/data_editor.py (DataEditorDialog) に対する回帰テスト。"""
import os

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from core.dataset import Dataset
from gui.data_editor import DataEditorDialog
from gui.dialogs import (ColumnCalculatorDialog, ReplicateErrorDialog, ColumnStringOpsDialog,
                         ColumnVisibilityDialog, FindReplaceDialog)


def _make_dataset_with_bool_column(flag_value=True):
    df = pd.DataFrame({
        'x': [1.0, 2.0, 3.0],
        'y': [10.0, 20.0, 30.0],
        'flag': [flag_value, flag_value, flag_value],
    })
    return Dataset(name="D", df=df, x_col_name='x', y_col_name='y')


def _make_simple_dataset(n=3):
    df = pd.DataFrame({
        'x': [float(i) for i in range(n)],
        'y': [float(i * 10) for i in range(n)],
    })
    return Dataset(name="D", df=df, x_col_name='x', y_col_name='y')


def test_editing_bool_cell_to_false_string_actually_becomes_false(qapp):
    """
    回帰テスト: np.dtype(bool).type("False") は(Pythonのbool("文字列")と同じ)
    空文字列以外を全てTrueとして扱うため、bool列のセルに"False"と入力しても
    実際にはTrueのままになっていた。「列の計算」機能の比較式(例: "A > 10")
    から作られるbool列で実際に到達しうる、サイレントな誤変換バグだった。
    """
    ds = _make_dataset_with_bool_column(flag_value=True)
    dlg = DataEditorDialog(ds)
    try:
        col_index = list(dlg.view_df.columns).index('flag')
        dlg.table_widget.item(0, col_index).setText("False")
        assert bool(ds.df.loc[0, 'flag']) is False
    finally:
        dlg.close()


def test_editing_bool_cell_to_true_string_stays_true(qapp):
    ds = _make_dataset_with_bool_column(flag_value=False)
    dlg = DataEditorDialog(ds)
    try:
        col_index = list(dlg.view_df.columns).index('flag')
        dlg.table_widget.item(0, col_index).setText("True")
        assert bool(ds.df.loc[0, 'flag']) is True
    finally:
        dlg.close()


def test_icon_only_toolbar_buttons_do_not_retain_focus(qapp):
    """
    実機フィードバック(「ボタンが一回押すと他のボタン押すまでずっと色付きに
    なる」): QPushButtonの既定フォーカスポリシーのままだと、クリック後も
    gui/theme.pyのQPushButton:focus(青枠)が居座り続けてしまう。データテーブル
    (Data Editor)のアイコンのみのツールバーボタン群がNoFocusになっていることを
    確認する。
    """
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        for button in (
            dlg.add_row_button, dlg.delete_row_button, dlg.mask_rows_button,
            dlg.add_col_button, dlg.delete_col_button, dlg.calc_button,
            dlg.replicate_error_button, dlg.save_csv_button,
        ):
            assert button.focusPolicy() == Qt.FocusPolicy.NoFocus
    finally:
        dlg.close()


def test_editing_bool_cell_with_unparseable_text_does_not_raise(qapp):
    ds = _make_dataset_with_bool_column(flag_value=True)
    dlg = DataEditorDialog(ds)
    try:
        col_index = list(dlg.view_df.columns).index('flag')
        dlg.table_widget.item(0, col_index).setText("maybe")
    finally:
        dlg.close()


def test_masked_row_background_follows_current_theme_instead_of_fixed_light_gray(qapp):
    """
    回帰テスト: マスク済み行の背景色は以前 QColor(220,220,220) という
    ライトモード専用の固定色がハードコードされており、ダークモード
    (surfaceが暗色)では逆に浮いて見えていた。現在のテーマの
    surface_2トークンを反映していることを確認する。
    """
    from gui import theme
    from PySide6.QtGui import QColor

    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [10.0, 20.0]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y', masked_row_indices=[0])

    theme.apply_theme(qapp, dark=True)
    try:
        dlg = DataEditorDialog(ds)
        try:
            item = dlg.table_widget.item(0, 0)
            assert item.background().color() == QColor(theme.DARK_TOKENS['surface_2'])
        finally:
            dlg.close()
    finally:
        theme.apply_theme(qapp, dark=False)


# --- 欠損値(NaN)の可視化(項目C-201) ---

def test_nan_cell_gets_warning_soft_background(qapp):
    from gui import theme
    from PySide6.QtGui import QColor

    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [10.0, np.nan]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y')
    dlg = DataEditorDialog(ds)
    try:
        nan_item = dlg.table_widget.item(1, 1)
        normal_item = dlg.table_widget.item(0, 1)
        assert nan_item.background().color() == QColor(theme.current_tokens()['warning_soft'])
        assert nan_item.text() == ""
        assert normal_item.background() != nan_item.background()
    finally:
        dlg.close()


def test_nan_cell_background_follows_current_theme(qapp):
    from gui import theme
    from PySide6.QtGui import QColor

    df = pd.DataFrame({'x': [1.0, np.nan], 'y': [10.0, 20.0]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y')

    theme.apply_theme(qapp, dark=True)
    try:
        dlg = DataEditorDialog(ds)
        try:
            item = dlg.table_widget.item(1, 0)
            assert item.background().color() == QColor(theme.DARK_TOKENS['warning_soft'])
        finally:
            dlg.close()
    finally:
        theme.apply_theme(qapp, dark=False)


def test_masked_row_background_takes_priority_over_nan_highlight(qapp):
    """マスク済み行(行全体の背景)とNaNセルの可視化が同じセルで重なる場合、
    マスク済みの背景色が優先され、二重に色が重ならないこと。"""
    from gui import theme
    from PySide6.QtGui import QColor

    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [np.nan, 20.0]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y', masked_row_indices=[0])
    dlg = DataEditorDialog(ds)
    try:
        item = dlg.table_widget.item(0, 1)  # マスク済み行のNaNセル
        assert item.background().color() == QColor(theme.current_tokens()['surface_2'])
    finally:
        dlg.close()


def test_empty_string_cell_is_not_treated_as_nan(qapp):
    """実際の空文字列(オブジェクト列)はpd.isnaでFalseになるため、NaN扱いされない"""
    df = pd.DataFrame({'x': [1.0, 2.0], 'label': ["", "b"]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='x')
    dlg = DataEditorDialog(ds)
    try:
        col_index = list(dlg.view_df.columns).index('label')
        item = dlg.table_widget.item(0, col_index)
        # 何も背景色を設定していない場合、QBrushのスタイルはNoBrush(既定・透明)のまま
        assert item.background().style() == Qt.BrushStyle.NoBrush
    finally:
        dlg.close()


# --- セル編集: 数値列・文字列列(bool以外の型変換パス) ---

def test_editing_numeric_cell_converts_to_float_and_pushes_command(qapp):
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.item(0, 0).setText("99.5")
        assert ds.df.loc[0, 'x'] == 99.5
        assert dlg.undo_stack.count() == 1
    finally:
        dlg.close()


def test_editing_numeric_cell_with_invalid_text_becomes_nan(qapp):
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.item(0, 0).setText("not_a_number")
        assert pd.isna(ds.df.loc[0, 'x'])
    finally:
        dlg.close()


def test_editing_cell_to_empty_string_becomes_nan(qapp):
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.item(0, 0).setText("")
        assert pd.isna(ds.df.loc[0, 'x'])
    finally:
        dlg.close()


def test_editing_datetime_cell_with_unparseable_text_falls_back_to_raw_string(qapp):
    """
    数値/bool以外(日付など)の型で変換に失敗した場合、np.nanにはせず入力文字列を
    そのまま使うフォールバック分岐(380行)を確認する。
    """
    df = pd.DataFrame({'x': [1.0, 2.0], 'd': pd.to_datetime(['2024-01-01', '2024-01-02'])})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='x')
    dlg = DataEditorDialog(ds)
    try:
        col_index = list(dlg.view_df.columns).index('d')
        dlg.table_widget.item(0, col_index).setText("not_a_date")
        assert ds.df.loc[0, 'd'] == "not_a_date"
    finally:
        dlg.close()


def test_editing_string_column_cell_keeps_raw_text(qapp):
    df = pd.DataFrame({'x': [1.0, 2.0], 'label': ['a', 'b']})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='x')
    dlg = DataEditorDialog(ds)
    try:
        col_index = list(dlg.view_df.columns).index('label')
        dlg.table_widget.item(0, col_index).setText("hello")
        assert ds.df.loc[0, 'label'] == "hello"
    finally:
        dlg.close()


def test_editing_cell_with_unchanged_value_does_not_push_command(qapp):
    """
    Qtはセルのテキストが完全に同一ならcellChanged自体を発火しないため、
    「表示上のテキストは変わるが、パース後の値は変わらない」入力
    (例: "0.0" -> "0") でのみ、この再表示のみの分岐(403-406行)に到達できる。
    """
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.item(0, 0).setText("0")  # パース後は既存値(0.0)と同じ
        assert dlg.undo_stack.count() == 0
        assert dlg.table_widget.item(0, 0).text() == "0.0"  # 元の表記に正規化される
    finally:
        dlg.close()


def test_on_cell_changed_with_out_of_range_row_does_not_raise(qapp):
    """
    _on_cell_changed()に想定外の行番号を渡した場合の例外処理経路
    (外側except → 復元試行も同じ理由で失敗し諦める分岐)を確認する。
    """
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_cell_changed(999, 0)  # 例外を吸収して何も起きない
    finally:
        dlg.close()


def test_on_cell_changed_recovers_display_when_command_construction_fails(qapp, monkeypatch):
    """
    行/列自体は正当だが、コマンド作成中に予期しない例外が起きた場合
    (外側except -> 復元は成功する経路、415-419行)を確認する。
    """
    import gui.data_editor as data_editor_module

    def _raise(*args, **kwargs):
        raise RuntimeError("コマンド作成失敗(テスト用)")

    monkeypatch.setattr(data_editor_module, "EditCellCommand", _raise)
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.item(0, 0).setText("42.0")  # 値は変わるのでコマンド作成が試みられる
        # 例外後、テーブル表示は元の値に復元される
        assert dlg.table_widget.item(0, 0).text() == "0.0"
        assert ds.df.loc[0, 'x'] == 0.0  # データ自体は変更されていない
    finally:
        dlg.close()


# --- ソート(_on_header_clicked) ---

def test_header_click_sorts_ascending_then_descending_on_second_click(qapp):
    df = pd.DataFrame({'x': [3.0, 1.0, 2.0], 'y': [10.0, 20.0, 30.0]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y')
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_header_clicked(0)  # x列で昇順
        assert dlg.sort_state == ('x', True)
        assert list(dlg.view_df['x']) == [1.0, 2.0, 3.0]

        dlg._on_header_clicked(0)  # 同じ列を再度クリック -> 降順
        assert dlg.sort_state == ('x', False)
        assert list(dlg.view_df['x']) == [3.0, 2.0, 1.0]
    finally:
        dlg.close()


def test_header_click_shows_sort_indicator_in_table_header(qapp):
    df = pd.DataFrame({'x': [3.0, 1.0], 'y': [10.0, 20.0]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y')
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_header_clicked(0)
        header = dlg.table_widget.horizontalHeader()
        assert header.isSortIndicatorShown() is True
        assert header.sortIndicatorSection() == 0
    finally:
        dlg.close()


def test_header_click_on_mixed_type_column_shows_sort_error(qapp, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))

    df = pd.DataFrame({'x': pd.Series(['a', 1, 'b'], dtype=object), 'y': [1.0, 2.0, 3.0]})
    ds = Dataset(name="D", df=df, x_col_name='y', y_col_name='y')
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_header_clicked(0)
        assert len(calls["warning"]) == 1
        assert dlg.sort_state == (None, True)  # ソートは反映されない
    finally:
        dlg.close()


# --- 列名の変更(_on_header_double_clicked、項目64) ---

def test_header_double_click_renames_column(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("new_x", True)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_header_double_clicked(0)
        assert 'new_x' in ds.df.columns
        assert 'x' not in ds.df.columns
    finally:
        dlg.close()


def test_header_double_click_cancelled_does_not_rename(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("new_x", False)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_header_double_clicked(0)
        assert 'x' in ds.df.columns
    finally:
        dlg.close()


def test_header_double_click_empty_or_same_name_does_not_rename(qapp, monkeypatch):
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("  ", True)))
        dlg._on_header_double_clicked(0)
        assert 'x' in ds.df.columns

        monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("x", True)))
        dlg._on_header_double_clicked(0)
        assert 'x' in ds.df.columns
    finally:
        dlg.close()


def test_header_double_click_duplicate_name_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("y", True)))
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_header_double_clicked(0)  # 'x' -> 'y' (既存)
        assert len(calls["warning"]) == 1
        assert 'x' in ds.df.columns
    finally:
        dlg.close()


# --- 行選択とグラフ側ハイライト連動 ---

def test_get_selected_master_indices_reflects_table_selection(qapp):
    ds = _make_simple_dataset(n=4)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(1)
        dlg.table_widget.selectRow(3)  # 追加選択ではなく単一選択に変わる想定だが、
        # selectRowは既存選択をクリアするため、明示的にCtrl的な複数選択にはならない。
        assert dlg.get_selected_master_indices() == [3]
    finally:
        dlg.close()


def test_table_selection_changed_emits_rows_highlighted_signal(qapp):
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    received = []
    dlg.rowsHighlighted.connect(lambda indices: received.append(indices))
    try:
        dlg.table_widget.selectRow(0)
        assert received[-1] == [0]
    finally:
        dlg.close()


def test_select_row_by_master_index_selects_and_scrolls(qapp):
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.select_row_by_master_index(2)
        selected_rows = {idx.row() for idx in dlg.table_widget.selectionModel().selectedRows()}
        assert selected_rows == {2}
    finally:
        dlg.close()


def test_select_row_by_master_index_with_unknown_index_is_noop(qapp):
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(0)
        dlg.select_row_by_master_index(999)  # 存在しないindex -> 何もしない
        selected_rows = {idx.row() for idx in dlg.table_widget.selectionModel().selectedRows()}
        assert selected_rows == {0}
    finally:
        dlg.close()


def test_close_event_emits_empty_rows_highlighted(qapp):
    ds = _make_simple_dataset(n=2)
    dlg = DataEditorDialog(ds)
    received = []
    dlg.rowsHighlighted.connect(lambda indices: received.append(indices))
    dlg.table_widget.selectRow(0)
    dlg.close()
    assert received[-1] == []


# --- 行の追加/削除 ---

def test_add_row_button_appends_nan_row_and_is_undoable(qapp):
    ds = _make_simple_dataset(n=2)
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_add_row()
        assert len(ds.df) == 3
        assert pd.isna(ds.df['x'].iloc[-1])

        dlg.undo_stack.undo()
        assert len(ds.df) == 2
    finally:
        dlg.close()


def test_delete_rows_with_no_selection_is_noop(qapp):
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.clearSelection()
        dlg._on_delete_rows()
        assert len(ds.df) == 3
    finally:
        dlg.close()


def test_delete_rows_removes_selected_rows_and_is_undoable(qapp):
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(1)
        dlg._on_delete_rows()
        assert len(ds.df) == 2
        assert 1 not in ds.df.index

        dlg.undo_stack.undo()
        assert len(ds.df) == 3
        assert 1 in ds.df.index
    finally:
        dlg.close()


# --- 外れ値マスクのトグル(項目36) ---

def test_toggle_mask_rows_with_no_selection_is_noop(qapp):
    ds = _make_simple_dataset(n=2)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.clearSelection()
        dlg._on_toggle_mask_rows()
        assert ds.masked_row_indices == []
    finally:
        dlg.close()


def test_toggle_mask_rows_masks_then_unmasks_selected_row(qapp):
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(0)
        dlg._on_toggle_mask_rows()
        assert 0 in ds.masked_row_indices

        dlg.table_widget.selectRow(0)
        dlg._on_toggle_mask_rows()
        assert 0 not in ds.masked_row_indices
    finally:
        dlg.close()


def test_toggle_mask_rows_is_undoable(qapp):
    ds = _make_simple_dataset(n=2)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(0)
        dlg._on_toggle_mask_rows()
        assert 0 in ds.masked_row_indices

        dlg.undo_stack.undo()
        assert 0 not in ds.masked_row_indices
    finally:
        dlg.close()


# --- 列の追加/削除 ---

def test_add_column_via_input_dialog(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("new_col", True)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_add_column()
        assert 'new_col' in ds.df.columns
        assert dlg.undo_stack.count() == 1
    finally:
        dlg.close()


def test_add_column_cancelled_does_not_add(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_add_column()
        assert list(ds.df.columns) == ['x', 'y']
    finally:
        dlg.close()


def test_add_column_duplicate_name_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("y", True)))
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_add_column()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_delete_column_with_no_selection_shows_warning(qapp, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.setCurrentCell(-1, -1)
        dlg._on_delete_column()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_delete_column_used_in_plot_is_protected(qapp, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.setCurrentCell(0, 0)  # 'x' はプロットのX軸に使用中
        dlg._on_delete_column()
        assert len(calls["warning"]) == 1
        assert 'x' in ds.df.columns
    finally:
        dlg.close()


def test_delete_column_removes_extra_column_and_is_undoable(qapp):
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [3.0, 4.0], 'extra': [5.0, 6.0]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='y')
    dlg = DataEditorDialog(ds)
    try:
        col_index = list(dlg.view_df.columns).index('extra')
        dlg.table_widget.setCurrentCell(0, col_index)
        dlg._on_delete_column()
        assert 'extra' not in ds.df.columns

        dlg.undo_stack.undo()
        assert 'extra' in ds.df.columns
    finally:
        dlg.close()


# --- 列の計算(_on_calculate_column) ---

def test_calculate_column_success_adds_new_column(qapp, monkeypatch):
    monkeypatch.setattr(ColumnCalculatorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnCalculatorDialog, "get_formula", lambda self: ("z", "x + y"))
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    changed = []
    dlg.dataChanged.connect(lambda: changed.append(True))
    try:
        dlg._on_calculate_column()
        assert 'z' in ds.df.columns
        assert list(ds.df['z']) == list(ds.df['x'] + ds.df['y'])
        assert changed == [True]
    finally:
        dlg.close()


def test_calculate_column_cancelled_does_nothing(qapp, monkeypatch):
    monkeypatch.setattr(ColumnCalculatorDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_column()
        assert list(ds.df.columns) == ['x', 'y']
    finally:
        dlg.close()


def test_calculate_column_empty_formula_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(ColumnCalculatorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnCalculatorDialog, "get_formula", lambda self: ("", ""))
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_column()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


# --- 文字列操作(_on_column_string_ops, 項目C-205) ---

def _make_string_dataset():
    df = pd.DataFrame({
        'x': [0.0, 1.0, 2.0],
        'label': ["400nm,red", "500nm,green", "600nm,blue"],
        'first': ["A", "B", "C"],
        'second': ["1", "2", "3"],
    })
    return Dataset(name="D", df=df, x_col_name='x', y_col_name='x')


def test_column_string_ops_split_adds_new_columns(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_mode", lambda self: ColumnStringOpsDialog.MODE_SPLIT)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_split_settings", lambda self: ("label", ",", "part"))
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    changed = []
    dlg.dataChanged.connect(lambda: changed.append(True))
    try:
        dlg._on_column_string_ops()
        assert list(ds.df['part_1']) == ["400nm", "500nm", "600nm"]
        assert list(ds.df['part_2']) == ["red", "green", "blue"]
        assert changed == [True]
    finally:
        dlg.close()


def test_column_string_ops_split_empty_delimiter_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_mode", lambda self: ColumnStringOpsDialog.MODE_SPLIT)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_split_settings", lambda self: ("label", "", "part"))
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_column_string_ops()
        assert len(calls["warning"]) == 1
        assert 'part_1' not in ds.df.columns
    finally:
        dlg.close()


def test_column_string_ops_split_default_prefix_uses_source_column_name(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_mode", lambda self: ColumnStringOpsDialog.MODE_SPLIT)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_split_settings", lambda self: ("label", ",", ""))
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_column_string_ops()
        assert 'label_1' in ds.df.columns
        assert 'label_2' in ds.df.columns
    finally:
        dlg.close()


def test_column_string_ops_merge_concatenates_with_separator(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_mode", lambda self: ColumnStringOpsDialog.MODE_MERGE)
    monkeypatch.setattr(
        ColumnStringOpsDialog, "get_merge_settings",
        lambda self: (["first", "second"], "_", "combined"),
    )
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_column_string_ops()
        assert list(ds.df['combined']) == ["A_1", "B_2", "C_3"]
    finally:
        dlg.close()


def test_column_string_ops_merge_requires_two_columns(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_mode", lambda self: ColumnStringOpsDialog.MODE_MERGE)
    monkeypatch.setattr(
        ColumnStringOpsDialog, "get_merge_settings", lambda self: (["first"], "_", "combined")
    )
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_column_string_ops()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_column_string_ops_merge_duplicate_output_name_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnStringOpsDialog, "get_mode", lambda self: ColumnStringOpsDialog.MODE_MERGE)
    monkeypatch.setattr(
        ColumnStringOpsDialog, "get_merge_settings",
        lambda self: (["first", "second"], "_", "first"),  # 既存列名と衝突
    )
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_column_string_ops()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_column_string_ops_extract_numeric_default_pattern(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        ColumnStringOpsDialog, "get_mode", lambda self: ColumnStringOpsDialog.MODE_EXTRACT_NUMERIC
    )
    monkeypatch.setattr(
        ColumnStringOpsDialog, "get_extract_settings",
        lambda self: ("label", r'[-+]?\d*\.?\d+', "label_numeric"),
    )
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_column_string_ops()
        assert list(ds.df['label_numeric']) == [400.0, 500.0, 600.0]
    finally:
        dlg.close()


def test_column_string_ops_extract_numeric_invalid_regex_shows_critical(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        ColumnStringOpsDialog, "get_mode", lambda self: ColumnStringOpsDialog.MODE_EXTRACT_NUMERIC
    )
    monkeypatch.setattr(
        ColumnStringOpsDialog, "get_extract_settings",
        lambda self: ("label", "[invalid(regex", "label_numeric"),
    )
    calls = {"critical": []}
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: calls["critical"].append(a)))
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_column_string_ops()
        assert len(calls["critical"]) == 1
    finally:
        dlg.close()


def test_column_string_ops_cancelled_does_nothing(qapp, monkeypatch):
    monkeypatch.setattr(ColumnStringOpsDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    ds = _make_string_dataset()
    original_columns = list(ds.df.columns)
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_column_string_ops()
        assert list(ds.df.columns) == original_columns
    finally:
        dlg.close()


# --- 列の表示/非表示(_on_toggle_column_visibility, 項目C-207) ---

def test_column_visibility_hides_selected_columns(qapp, monkeypatch):
    monkeypatch.setattr(ColumnVisibilityDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnVisibilityDialog, "get_hidden_columns", lambda self: ["y"])
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_toggle_column_visibility()
        y_index = list(dlg.view_df.columns).index('y')
        x_index = list(dlg.view_df.columns).index('x')
        assert dlg.table_widget.isColumnHidden(y_index) is True
        assert dlg.table_widget.isColumnHidden(x_index) is False
    finally:
        dlg.close()


def test_column_visibility_persists_across_table_rebuild(qapp, monkeypatch):
    """ソート等でテーブルが再構築(_populate_table再呼び出し)されても非表示状態が保たれる"""
    monkeypatch.setattr(ColumnVisibilityDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnVisibilityDialog, "get_hidden_columns", lambda self: ["y"])
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_toggle_column_visibility()
        dlg._reset_view()  # テーブルの再構築を誘発
        y_index = list(dlg.view_df.columns).index('y')
        assert dlg.table_widget.isColumnHidden(y_index) is True
    finally:
        dlg.close()


def test_column_visibility_cancelled_keeps_all_visible(qapp, monkeypatch):
    monkeypatch.setattr(ColumnVisibilityDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_toggle_column_visibility()
        assert dlg._hidden_columns == set()
    finally:
        dlg.close()


def test_column_headers_are_movable_for_drag_reorder(qapp):
    """項目C-207: 列のドラッグ&ドロップ並べ替え(Qt標準機能を有効化しただけ)"""
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        assert dlg.table_widget.horizontalHeader().sectionsMovable() is True
    finally:
        dlg.close()


# --- 検索/置換(_on_find_next/_on_replace_all, 項目C-208) ---

def _open_find_replace(dlg):
    dlg._on_open_find_replace()
    return dlg._find_replace_dialog


def test_open_find_replace_creates_dialog_once(qapp):
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        first = _open_find_replace(dlg)
        second = _open_find_replace(dlg)
        assert first is second
    finally:
        dlg.close()


def test_find_next_selects_matching_cell(qapp):
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("500nm")
        dlg._on_find_next()
        assert dlg.table_widget.currentRow() == 1
        assert dlg.table_widget.currentColumn() == list(ds.df.columns).index('label')
        assert "見つかりました" in fr.status_label.text()
    finally:
        dlg.close()


def test_find_next_case_insensitive(qapp):
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("RED")
        dlg._on_find_next()
        assert "見つかりました" in fr.status_label.text()
    finally:
        dlg.close()


def test_find_next_no_match_shows_status(qapp):
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("nonexistent_value")
        dlg._on_find_next()
        assert fr.status_label.text() == "見つかりませんでした"
    finally:
        dlg.close()


def test_find_next_restricts_to_target_column(qapp):
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("A")  # 'first'列にのみ存在("label"列には無い)
        fr.column_combo.setCurrentText("second")  # 存在しない列に限定
        dlg._on_find_next()
        assert fr.status_label.text() == "見つかりませんでした"
    finally:
        dlg.close()


def test_find_next_wraps_around_and_advances_each_call(qapp):
    df = pd.DataFrame({'x': [0.0, 1.0], 'label': ["match", "match"]})
    ds = Dataset(name="D", df=df, x_col_name='x', y_col_name='x')
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("match")
        dlg._on_find_next()
        first_row = dlg.table_widget.currentRow()
        dlg._on_find_next()
        second_row = dlg.table_widget.currentRow()
        assert first_row != second_row  # 前回の続きから探すため別のセルが見つかる
    finally:
        dlg.close()


def test_replace_all_replaces_matching_cells_case_insensitively(qapp):
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("NM")
        fr.replace_edit.setText("nanometer")
        dlg._on_replace_all()
        assert list(ds.df['label']) == ["400nanometer,red", "500nanometer,green", "600nanometer,blue"]
        assert "3件を置換しました" in fr.status_label.text()
    finally:
        dlg.close()


def test_replace_all_is_undoable(qapp):
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("red")
        fr.replace_edit.setText("crimson")
        dlg._on_replace_all()
        assert ds.df.loc[0, 'label'] == "400nm,crimson"

        dlg.undo_stack.undo()
        assert ds.df.loc[0, 'label'] == "400nm,red"
    finally:
        dlg.close()


def test_replace_all_skips_non_string_columns(qapp):
    """数値列は検索対象だが置換対象からは除外される(dtype暗黙変換を避けるため)"""
    ds = _make_string_dataset()  # 'x'列は数値
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("1")
        fr.replace_edit.setText("999")
        dlg._on_replace_all()
        # 'x'列(数値)は対象外のため変化しない。'second'列の"1"は置換される。
        assert list(ds.df['x']) == [0.0, 1.0, 2.0]
        assert ds.df.loc[0, 'second'] == "999"
    finally:
        dlg.close()


def test_replace_all_no_matches_shows_status(qapp):
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        fr.search_edit.setText("nonexistent_value")
        dlg._on_replace_all()
        assert "見つかりませんでした" in fr.status_label.text()
    finally:
        dlg.close()


def test_replace_all_empty_query_shows_status(qapp):
    ds = _make_string_dataset()
    dlg = DataEditorDialog(ds)
    try:
        fr = _open_find_replace(dlg)
        dlg._on_replace_all()
        assert fr.status_label.text() == "検索文字列を入力してください"
    finally:
        dlg.close()


# --- 行へ移動(_on_jump_to_row, 項目C-208) ---

def test_jump_to_row_selects_target_row(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(lambda *a, **k: (2, True)))
    ds = _make_simple_dataset(n=5)
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_jump_to_row()
        assert dlg.table_widget.currentRow() == 1  # 1始まりの入力2 -> 0始まりの行1
    finally:
        dlg.close()


def test_jump_to_row_cancelled_does_nothing(qapp, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(lambda *a, **k: (2, False)))
    ds = _make_simple_dataset(n=5)
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_jump_to_row()
        assert dlg.table_widget.currentRow() == -1
    finally:
        dlg.close()


def test_jump_to_row_empty_table_shows_info(qapp, monkeypatch):
    calls = {"information": []}
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: calls["information"].append(a)))
    ds = _make_simple_dataset(n=0)
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_jump_to_row()
        assert len(calls["information"]) == 1
    finally:
        dlg.close()


def test_calculate_column_invalid_formula_shows_critical_error(qapp, monkeypatch):
    monkeypatch.setattr(ColumnCalculatorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ColumnCalculatorDialog, "get_formula", lambda self: ("z", "undefined_col + 1"))
    calls = {"critical": []}
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: calls["critical"].append(a)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_column()
        assert len(calls["critical"]) == 1
    finally:
        dlg.close()


# --- 誤差の自動計算(_on_calculate_replicate_error) ---

def _make_replicate_dataset():
    df = pd.DataFrame({
        'x': [1.0, 2.0, 3.0],
        'rep1': [10.0, 20.0, 30.0],
        'rep2': [11.0, 19.0, 31.0],
        'rep3': [9.0, 21.0, 29.0],
    })
    return Dataset(name="D", df=df, x_col_name='x', y_col_name='rep1')


def test_calculate_replicate_error_success_adds_mean_and_error_columns(qapp, monkeypatch):
    monkeypatch.setattr(ReplicateErrorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        ReplicateErrorDialog, "get_settings",
        lambda self: (["rep1", "rep2", "rep3"], "SD", "measurement")
    )
    ds = _make_replicate_dataset()
    dlg = DataEditorDialog(ds)
    changed = []
    dlg.dataChanged.connect(lambda: changed.append(True))
    try:
        dlg._on_calculate_replicate_error()
        assert 'measurement_mean' in ds.df.columns
        assert 'measurement_SD' in ds.df.columns
        assert changed == [True]
    finally:
        dlg.close()


def test_calculate_replicate_error_sem_and_ci95_suffixes(qapp, monkeypatch):
    monkeypatch.setattr(ReplicateErrorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        ReplicateErrorDialog, "get_settings",
        lambda self: (["rep1", "rep2", "rep3"], "SEM", "measurement")
    )
    ds = _make_replicate_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_replicate_error()
        assert 'measurement_SEM' in ds.df.columns
    finally:
        dlg.close()

    monkeypatch.setattr(
        ReplicateErrorDialog, "get_settings",
        lambda self: (["rep1", "rep2", "rep3"], "95%CI", "measurement2")
    )
    ds2 = _make_replicate_dataset()
    dlg2 = DataEditorDialog(ds2)
    try:
        dlg2._on_calculate_replicate_error()
        assert 'measurement2_CI95' in ds2.df.columns
    finally:
        dlg2.close()


def test_calculate_replicate_error_cancelled_does_nothing(qapp, monkeypatch):
    monkeypatch.setattr(ReplicateErrorDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    ds = _make_replicate_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_replicate_error()
        assert 'measurement_mean' not in ds.df.columns
    finally:
        dlg.close()


def test_calculate_replicate_error_too_few_columns_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(ReplicateErrorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ReplicateErrorDialog, "get_settings", lambda self: (["rep1"], "SD", "measurement"))
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_replicate_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_replicate_error()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_calculate_replicate_error_empty_base_name_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(ReplicateErrorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        ReplicateErrorDialog, "get_settings", lambda self: (["rep1", "rep2"], "SD", "")
    )
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_replicate_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_replicate_error()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_calculate_replicate_error_duplicate_output_columns_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(ReplicateErrorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        ReplicateErrorDialog, "get_settings",
        lambda self: (["rep1", "rep2"], "SD", "rep1")  # rep1_mean/rep1_SDが既存名と衝突しない前提だが
        # ここでは意図的に既存列'rep1'と同名ベースを使うのではなく、既存の出力列名と衝突させる
    )
    ds = _make_replicate_dataset()
    ds.df['dup_mean'] = 0.0
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    monkeypatch.setattr(
        ReplicateErrorDialog, "get_settings",
        lambda self: (["rep1", "rep2"], "SD", "dup")
    )
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_replicate_error()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


# --- CSVとして保存(_on_save_as_csv) ---

def test_save_as_csv_cancelled_does_nothing(qapp, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_save_as_csv()  # 例外が起きなければOK
    finally:
        dlg.close()


def test_save_as_csv_success_writes_file_and_shows_information(qapp, monkeypatch, tmp_path):
    out_path = str(tmp_path / "out.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out_path, "")))
    calls = {"information": []}
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: calls["information"].append(a))
    )
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_save_as_csv()
        assert os.path.exists(out_path)
        assert len(calls["information"]) == 1
    finally:
        dlg.close()


def test_save_as_csv_suggested_filename_strips_copy_suffix(qapp, monkeypatch):
    captured = {}

    def fake_get_save_file_name(self, title, suggested_name, filter_str):
        captured["suggested"] = suggested_name
        return "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_get_save_file_name))
    ds = _make_simple_dataset()
    ds.name = "MyData (copy)"
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_save_as_csv()
        assert captured["suggested"] == "MyData_edited.csv"
    finally:
        dlg.close()


def test_save_as_csv_failure_shows_warning(qapp, monkeypatch):
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: ("/nonexistent_dir_xyz/out.csv", ""))
    )
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_save_as_csv()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


# --- 行選択とマスターDFのズレに対する安全性チェック(想定外の状態からの復旧) ---

def test_delete_rows_index_error_from_desynced_view_df_shows_warning(qapp, monkeypatch):
    """
    selectedItems()が返す表示上の行番号がview_df.indexの範囲を超える
    (何らかの理由でview_dfとテーブルの表示行数がズレた)場合の安全性チェックを確認する。
    """
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(2)
        dlg.view_df = dlg.view_df.iloc[:1]  # view_dfを意図的に縮める(ズレを再現)
        dlg._on_delete_rows()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_delete_rows_with_indices_missing_from_master_shows_warning(qapp, monkeypatch):
    """
    view_dfの行が指すインデックスが、既にマスターDF(dataset.df)から
    削除されていた(ズレている)場合の安全性チェックを確認する。
    """
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(0)
        ds.df = ds.df.drop(index=0)  # マスターから先に消してズレを作る
        dlg._on_delete_rows()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_toggle_mask_rows_index_error_from_desynced_view_df_shows_warning(qapp, monkeypatch):
    calls = {"warning": []}
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a)))
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(2)
        dlg.view_df = dlg.view_df.iloc[:1]
        dlg._on_toggle_mask_rows()
        assert len(calls["warning"]) == 1
    finally:
        dlg.close()


def test_toggle_mask_rows_with_indices_missing_from_master_is_noop(qapp):
    ds = _make_simple_dataset(n=3)
    dlg = DataEditorDialog(ds)
    try:
        dlg.table_widget.selectRow(0)
        ds.df = ds.df.drop(index=0)  # マスターから先に消してズレを作る
        dlg._on_toggle_mask_rows()  # 例外にならず、何も起きない
        assert ds.masked_row_indices == []
    finally:
        dlg.close()


def test_calculate_replicate_error_unexpected_exception_shows_critical(qapp, monkeypatch):
    """selected_colsに存在しない列名が混じっている等、計算中の予期しない例外は
    critical メッセージとして表示され、アプリがクラッシュしないことを確認する。"""
    monkeypatch.setattr(ReplicateErrorDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        ReplicateErrorDialog, "get_settings",
        lambda self: (["rep1", "not_a_real_column"], "SD", "measurement")
    )
    calls = {"critical": []}
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: calls["critical"].append(a)))
    ds = _make_replicate_dataset()
    dlg = DataEditorDialog(ds)
    try:
        dlg._on_calculate_replicate_error()
        assert len(calls["critical"]) == 1
    finally:
        dlg.close()
