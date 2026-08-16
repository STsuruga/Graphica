# tests/test_provenance_panel.py
"""項目C-1101「処理履歴」の専用ドックパネル(ProvenancePanel)に対するテスト。"""
import pandas as pd
import pytest
from types import SimpleNamespace

from gui.provenance_panel import ProvenancePanel
from core.dataset import Dataset


def _make_dataset(name, provenance=None):
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y", provenance=provenance)


@pytest.fixture
def panel(qapp):
    p = ProvenancePanel()
    p.show()
    qapp.processEvents()
    yield p
    p.close()


def test_provenance_panel_starts_with_placeholder_visible(panel):
    assert panel.placeholder_label.isVisible() is True
    assert panel.tree.isVisible() is False


def test_provenance_panel_refresh_none_shows_placeholder(panel):
    panel.refresh(None, SimpleNamespace(datasets=[]))
    assert panel.placeholder_label.isVisible() is True
    assert panel.tree.isVisible() is False


def test_provenance_panel_refresh_dataset_without_provenance_shows_tree_with_root_only(panel):
    """provenanceを持たない(元データの)データセットでも、ルート1件だけの
    ツリーとして表示され、プレースホルダには戻らない(何が選択されているかは
    分かるようにする)。"""
    ds = _make_dataset("raw")
    panel.refresh(ds, SimpleNamespace(datasets=[ds]))
    assert panel.placeholder_label.isVisible() is False
    assert panel.tree.isVisible() is True
    assert panel.tree.topLevelItemCount() == 1
    root = panel.tree.topLevelItem(0)
    assert root.text(0) == "raw"
    assert root.childCount() == 0


def test_provenance_panel_refresh_shows_operation_and_source_dataset(panel):
    source = _make_dataset("raw")
    prov = {
        'operation': 'savgol',
        'params': {'window_length': 5, 'polyorder': 2, 'deriv': 0},
        'source_dataset_ids': [source.dataset_id],
        'source_dataset_names': [source.name],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }
    derived = _make_dataset("smoothed", provenance=prov)

    panel.refresh(derived, SimpleNamespace(datasets=[source, derived]))

    root = panel.tree.topLevelItem(0)
    assert root.text(0) == "smoothed"
    assert root.childCount() == 1
    operation_item = root.child(0)
    assert "Savitzky-Golay" in operation_item.text(0)
    assert operation_item.childCount() == 1
    assert operation_item.child(0).text(0) == "raw"


def test_provenance_panel_recurses_into_ancestor_provenance(panel):
    """祖先データセット自身もprovenanceを持っていれば、さらにその下へ再帰的に
    ツリーが伸びること(2世代以上の処理チェーン)。"""
    grandparent = _make_dataset("raw")
    parent_prov = {
        'operation': 'baseline_als', 'params': {},
        'source_dataset_ids': [grandparent.dataset_id],
        'source_dataset_names': [grandparent.name],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }
    parent = _make_dataset("baseline_corrected", provenance=parent_prov)
    child_prov = {
        'operation': 'savgol', 'params': {'window_length': 5, 'polyorder': 2, 'deriv': 0},
        'source_dataset_ids': [parent.dataset_id],
        'source_dataset_names': [parent.name],
        'timestamp': '2026-08-16T00:00:01+00:00',
    }
    child = _make_dataset("smoothed", provenance=child_prov)

    panel.refresh(child, SimpleNamespace(datasets=[grandparent, parent, child]))

    root = panel.tree.topLevelItem(0)
    op1 = root.child(0)
    parent_item = op1.child(0)
    assert parent_item.text(0) == "baseline_corrected"
    assert parent_item.childCount() == 1  # さらに1世代分の操作ノード
    op2 = parent_item.child(0)
    assert op2.childCount() == 1
    assert op2.child(0).text(0) == "raw"


def test_provenance_panel_shows_deleted_marker_when_source_dataset_removed(panel):
    """親データセットが既に削除されていても(project.datasetsに見つからなくても)
    クラッシュせず、名前+「(削除済み)」として表示すること。"""
    prov = {
        'operation': 'normalize', 'params': {'mode': '最大値基準'},
        'source_dataset_ids': ['no-longer-exists'],
        'source_dataset_names': ['deleted_source'],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }
    ds = _make_dataset("normalized", provenance=prov)

    panel.refresh(ds, SimpleNamespace(datasets=[ds]))

    root = panel.tree.topLevelItem(0)
    operation_item = root.child(0)
    assert operation_item.child(0).text(0) == "deleted_source(削除済み)"


def test_provenance_panel_handles_multiple_source_datasets(panel):
    """データセット間演算のように親が2つある場合、両方が子ノードとして
    表示されること。"""
    ds_a = _make_dataset("A")
    ds_b = _make_dataset("B")
    prov = {
        'operation': 'arithmetic', 'params': {'operation_symbol': 'A - B'},
        'source_dataset_ids': [ds_a.dataset_id, ds_b.dataset_id],
        'source_dataset_names': [ds_a.name, ds_b.name],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }
    diff = _make_dataset("diff", provenance=prov)

    panel.refresh(diff, SimpleNamespace(datasets=[ds_a, ds_b, diff]))

    operation_item = panel.tree.topLevelItem(0).child(0)
    assert operation_item.childCount() == 2
    child_names = {operation_item.child(i).text(0) for i in range(2)}
    assert child_names == {"A", "B"}


def test_provenance_panel_breaks_cycle_without_infinite_recursion(panel):
    """理論上発生しないはずの循環参照(壊れた/手編集されたプロジェクト
    ファイル)でも、無限再帰にならず安全に打ち切ること。"""
    ds1 = _make_dataset("d1")
    ds2 = _make_dataset("d2")
    ds1.provenance = {
        'operation': 'normalize', 'params': {},
        'source_dataset_ids': [ds2.dataset_id], 'source_dataset_names': [ds2.name],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }
    ds2.provenance = {
        'operation': 'normalize', 'params': {},
        'source_dataset_ids': [ds1.dataset_id], 'source_dataset_names': [ds1.name],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }

    panel.refresh(ds1, SimpleNamespace(datasets=[ds1, ds2]))  # スタックオーバーフローせず戻ればOK


def test_provenance_panel_refresh_replaces_previous_tree_not_accumulates(panel):
    ds1 = _make_dataset("first")
    ds2 = _make_dataset("second")

    panel.refresh(ds1, SimpleNamespace(datasets=[ds1]))
    panel.refresh(ds2, SimpleNamespace(datasets=[ds2]))

    assert panel.tree.topLevelItemCount() == 1
    assert panel.tree.topLevelItem(0).text(0) == "second"


def test_provenance_panel_refresh_back_to_none_after_showing_data_returns_to_placeholder(panel):
    ds = _make_dataset("d")
    panel.refresh(ds, SimpleNamespace(datasets=[ds]))
    assert panel.tree.isVisible() is True

    panel.refresh(None, SimpleNamespace(datasets=[]))
    assert panel.placeholder_label.isVisible() is True
    assert panel.tree.isVisible() is False
