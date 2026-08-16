# tests/test_methods_text.py
"""core/methods_text.py の describe_operation / generate_methods_text
(項目C-1101/C-1102) に対するテスト。"""
import pandas as pd
import pytest
from types import SimpleNamespace

from core.dataset import Dataset
from core.methods_text import describe_operation, generate_methods_text


def _make_dataset(name, provenance=None):
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y", provenance=provenance)


# --- describe_operation ---

def test_describe_operation_none_returns_unknown():
    assert describe_operation(None) == "不明な操作"


def test_describe_operation_savgol_includes_params():
    text = describe_operation({
        'operation': 'savgol', 'params': {'window_length': 5, 'polyorder': 2, 'deriv': 1},
    })
    assert "Savitzky-Golay" in text
    assert "window=5" in text
    assert "polyorder=2" in text
    assert "deriv=1" in text


@pytest.mark.parametrize("method,expected_label", [
    ("als", "ALS法"),
    ("polynomial", "多項式法"),
    ("rubberband", "ラバーバンド法"),
    ("manual", "手動点指定"),
])
def test_describe_operation_baseline_methods(method, expected_label):
    text = describe_operation({'operation': f'baseline_{method}', 'params': {}})
    assert "ベースライン補正" in text
    assert expected_label in text


def test_describe_operation_normalize_max_mode():
    text = describe_operation({'operation': 'normalize', 'params': {'mode': '最大値基準'}})
    assert "規格化" in text
    assert "最大値基準" in text


def test_describe_operation_normalize_x_value_mode_includes_reference_x():
    text = describe_operation({
        'operation': 'normalize',
        'params': {'mode': '特定X値での強度基準', 'reference_x': 3.5},
    })
    assert "3.5" in text


def test_describe_operation_resample_includes_method():
    text = describe_operation({'operation': 'resample', 'params': {'method': 'cubic'}})
    assert "リサンプリング" in text
    assert "cubic" in text


def test_describe_operation_arithmetic_includes_symbol():
    text = describe_operation({'operation': 'arithmetic', 'params': {'operation_symbol': 'A - B'}})
    assert "A - B" in text


def test_describe_operation_curve_fit_includes_fit_type_and_r_squared():
    text = describe_operation({
        'operation': 'curve_fit',
        'params': {'fit_type': '線形 (y = ax + b)', 'r_squared': 0.987654},
    })
    assert "線形" in text
    assert "R²=0.9877" in text


def test_describe_operation_curve_fit_without_r_squared_omits_it():
    text = describe_operation({'operation': 'curve_fit', 'params': {'fit_type': '線形'}})
    assert "R²" not in text


def test_describe_operation_unknown_operation_falls_back_to_raw_name():
    assert describe_operation({'operation': 'something_new', 'params': {}}) == 'something_new'


# --- generate_methods_text ---

def test_generate_methods_text_no_provenance_reports_raw_data():
    ds = _make_dataset("raw")
    text = generate_methods_text(ds, SimpleNamespace(datasets=[ds]))
    assert "raw" in text
    assert "元データ" in text


def test_generate_methods_text_single_step_mentions_source_and_operation():
    source = _make_dataset("raw")
    prov = {
        'operation': 'savgol', 'params': {'window_length': 5, 'polyorder': 2, 'deriv': 0},
        'source_dataset_ids': [source.dataset_id], 'source_dataset_names': [source.name],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }
    derived = _make_dataset("smoothed", provenance=prov)

    text = generate_methods_text(derived, SimpleNamespace(datasets=[source, derived]))

    assert "raw" in text
    assert "Savitzky-Golay" in text
    assert "smoothed" in text


def test_generate_methods_text_multi_step_chain_lists_all_operations_in_order():
    grandparent = _make_dataset("raw")
    parent = _make_dataset("baseline_corrected", provenance={
        'operation': 'baseline_als', 'params': {},
        'source_dataset_ids': [grandparent.dataset_id], 'source_dataset_names': [grandparent.name],
        'timestamp': '2026-08-16T00:00:00+00:00',
    })
    child = _make_dataset("fit_result", provenance={
        'operation': 'curve_fit', 'params': {'fit_type': 'ガウシアン', 'r_squared': 0.99},
        'source_dataset_ids': [parent.dataset_id], 'source_dataset_names': [parent.name],
        'timestamp': '2026-08-16T00:00:01+00:00',
    })

    text = generate_methods_text(child, SimpleNamespace(datasets=[grandparent, parent, child]))

    # ベースライン補正の説明の方がカーブフィットの説明より前に出現すること(祖先→子孫の順)
    baseline_pos = text.find("ベースライン補正")
    fit_pos = text.find("カーブフィット")
    assert baseline_pos != -1 and fit_pos != -1
    assert baseline_pos < fit_pos
    assert "raw" in text


def test_generate_methods_text_stops_at_deleted_ancestor():
    """親データセットが既に削除されていて project.datasets に見つからない場合、
    そこで祖先探索を打ち切り、それより前の処理は文章に含めないこと
    (再帰は起こさずクラッシュもしない)。"""
    prov = {
        'operation': 'savgol', 'params': {'window_length': 5, 'polyorder': 2, 'deriv': 0},
        'source_dataset_ids': ['deleted-id'], 'source_dataset_names': ['deleted_source'],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }
    ds = _make_dataset("smoothed", provenance=prov)

    text = generate_methods_text(ds, SimpleNamespace(datasets=[ds]))

    assert "deleted_source" in text
    assert "Savitzky-Golay" in text


def test_generate_methods_text_multi_parent_step_lists_source_names():
    ds_a = _make_dataset("A")
    ds_b = _make_dataset("B")
    prov = {
        'operation': 'arithmetic', 'params': {'operation_symbol': 'A - B'},
        'source_dataset_ids': [ds_a.dataset_id, ds_b.dataset_id],
        'source_dataset_names': [ds_a.name, ds_b.name],
        'timestamp': '2026-08-16T00:00:00+00:00',
    }
    diff = _make_dataset("diff", provenance=prov)

    text = generate_methods_text(diff, SimpleNamespace(datasets=[ds_a, ds_b, diff]))

    assert "A" in text
    assert "B" in text
    assert "diff" in text
