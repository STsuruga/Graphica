# tests/test_dataset_style_icon.py
"""
gui/dataset_style_icon.py のうち、データセットリストの表示/非表示トグル
(項目C-907)で追加した make_dataset_visibility_icon() /
apply_dataset_visibility_text_style() に対するテスト。

QApplication は tests/conftest.py のセッションスコープ autouse フィクスチャ
(qapp)が用意するため、ここで個別にセットアップする必要はない。
"""
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTreeWidgetItem

from core.dataset import Dataset
from gui.dataset_style_icon import (
    make_dataset_visibility_icon, apply_dataset_visibility_text_style,
    DATASET_TREE_NAME_COLUMN, DATASET_TREE_VISIBILITY_COLUMN,
)


def _make_dataset(visible=True):
    df = pd.DataFrame({'x': [0, 1], 'y': [1.0, 2.0]})
    return Dataset(name="d", df=df, x_col_name='x', y_col_name='y', visible=visible)


def test_make_dataset_visibility_icon_visible_is_not_null():
    ds = _make_dataset(visible=True)
    icon = make_dataset_visibility_icon(ds)
    assert not icon.isNull()


def test_make_dataset_visibility_icon_hidden_is_not_null():
    ds = _make_dataset(visible=False)
    icon = make_dataset_visibility_icon(ds)
    assert not icon.isNull()


def test_make_dataset_visibility_icon_differs_between_states():
    """visible/非visibleで異なるSVG(eye.svg / eye-off.svg)から生成されるため、
    ピクセルデータが一致しないことを確認する(誤って同じアイコンを返す
    回帰を防ぐ)。"""
    visible_icon = make_dataset_visibility_icon(_make_dataset(visible=True))
    hidden_icon = make_dataset_visibility_icon(_make_dataset(visible=False))

    visible_image = visible_icon.pixmap(16, 16).toImage()
    hidden_image = hidden_icon.pixmap(16, 16).toImage()
    assert visible_image != hidden_image


def test_make_dataset_visibility_icon_missing_attr_defaults_to_visible_icon():
    """visible属性を持たないオブジェクトでも(getattr既定値True)、
    表示状態(eye.svg)のアイコンが返る。"""
    ds = _make_dataset(visible=True)
    del ds.__dict__['visible']

    icon = make_dataset_visibility_icon(ds)
    visible_icon = make_dataset_visibility_icon(_make_dataset(visible=True))

    assert icon.pixmap(16, 16).toImage() == visible_icon.pixmap(16, 16).toImage()


def test_apply_dataset_visibility_text_style_hidden_sets_muted_foreground():
    item = QTreeWidgetItem(["d"])
    ds = _make_dataset(visible=False)

    apply_dataset_visibility_text_style(item, ds, column=DATASET_TREE_NAME_COLUMN)

    brush = item.foreground(DATASET_TREE_NAME_COLUMN)
    assert brush.color().isValid()
    # 完全な透明/デフォルトのままではなく、明示的な色が設定されていること
    assert brush.color() != QColor()


def test_apply_dataset_visibility_text_style_visible_clears_foreground_override():
    item = QTreeWidgetItem(["d"])
    ds_hidden = _make_dataset(visible=False)
    ds_visible = _make_dataset(visible=True)

    # 先に非表示色を適用してから、表示に戻したときにクリアされることを確認する
    apply_dataset_visibility_text_style(item, ds_hidden, column=DATASET_TREE_NAME_COLUMN)
    apply_dataset_visibility_text_style(item, ds_visible, column=DATASET_TREE_NAME_COLUMN)

    assert item.data(DATASET_TREE_NAME_COLUMN, Qt.ItemDataRole.ForegroundRole) is None
