# tests/test_data_editor.py
"""gui/data_editor.py (DataEditorDialog) に対する回帰テスト。"""
import pandas as pd

from core.dataset import Dataset
from gui.data_editor import DataEditorDialog


def _make_dataset_with_bool_column(flag_value=True):
    df = pd.DataFrame({
        'x': [1.0, 2.0, 3.0],
        'y': [10.0, 20.0, 30.0],
        'flag': [flag_value, flag_value, flag_value],
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
