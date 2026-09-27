# tests/test_project_model_json_compat.py
"""
JSON保存形式(.graphica)追加に伴う後方互換性・堅牢性のテスト。

tests/test_project_model_json.py (stage1) は、新形式の基本的な往復・
dtypeフィデリティ・numpy由来の値・オブジェクト同一性・単純な壊れたIDの
スキップを既にカバーしている。このファイルはそれと重複しないよう、
以下の観点に絞る:

  1. 手で壊した/不正な .graphica ファイルが、クラッシュせず妥当な
     失敗の仕方をする(または妥当なデフォルトにフォールバックする)こと。
  2. stage1のテストが試していないと思われるエッジケースデータの往復。
"""
import json

import pandas as pd
import pytest

from graphica.core.dataset import Dataset
from graphica.models.project import ProjectModel


def make_dataset(**overrides):
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [10.0, 20.0, 30.0]})
    kwargs = dict(name="D1", df=df, x_col_name='x', y_col_name='y')
    kwargs.update(overrides)
    return Dataset(**kwargs)


# ---------------------------------------------------------------------------
# 2. 壊れた/手編集された .graphica の堅牢性
# ---------------------------------------------------------------------------

def test_load_graphica_invalid_json_raises_clear_exception(tmp_path):
    """構文的に壊れたJSONは、原因不明のトレースバックではなく
    json.JSONDecodeError (ValueErrorのサブクラス) としてはっきり失敗すること。"""
    path = tmp_path / "broken.graphica"
    path.write_text("{ this is not valid json ][", encoding='utf-8')

    project = ProjectModel()
    with pytest.raises(json.JSONDecodeError):
        project.load_project(str(path))


def test_load_graphica_empty_json_object_falls_back_to_defaults(tmp_path):
    """
    構文的には正しいが中身が空({})の.graphicaファイル。

    既知の懸念点: _load_project_json が主要キーに対して .get(key, default)
    を使わず直接 data['...'] でアクセスしていれば KeyError でクラッシュする
    はず、という点をテストで検証する。

    実際にコードを読んだ結果(models/project.py の _load_project_json)、
    datasets/dataset_group_tree/all_plot_settings/active_axis_index/
    layout_rows/layout_cols/layout_mode の全キーが .get(key, default) 経由で
    読まれており、ここは既に堅牢である
    ことが分かった。よってこのテストは「ギャップがない」ことを積極的に
    確認する回帰テストとして書く(見つかったギャップではない)。
    """
    path = tmp_path / "empty.graphica"
    path.write_text("{}", encoding='utf-8')

    project = ProjectModel()
    project.load_project(str(path))  # 例外を出さずに読み込めることを確認

    assert project.datasets == []
    assert project.dataset_group_tree == {'name': '', 'children': []}
    assert project.all_plot_settings == []
    assert project.active_axis_index == 0
    assert project.layout_rows == 1
    assert project.layout_cols == 1
    assert project.layout_mode == 'grid'


def test_load_graphica_dataset_missing_required_field_raises_clear_error(tmp_path):
    """
    このテストで当初見つかったギャップ(後日修正済み):

    Dataset.from_dict() は、必須(デフォルト値なし)のdataclassフィールド
    (name / x_col_name / y_col_name) が入力dictに存在しない場合、
    以前は「その属性を一切セットしない」という挙動になっており
    (fields()ループのif/elif/elifのどの分岐にも該当せず単に何もしないため)、
    'name' キーが欠けた壊れた/手編集の .graphica ファイルを読み込んでも
    load_project() 自体は例外を出さずに完了し、実際に壊れているのは
    「後でその属性にアクセスした瞬間」(AttributeError) になっていた。

    「壊れた.graphicaファイルは分かりやすく失敗するべき」という設計意図
    (dataset_idが存在しないリーフをスキップする処理など)に対して
    一貫していなかったため、Dataset.from_dict() 側にelse節を追加し、
    その場で分かりやすい ValueError を送出するよう修正した。
    """
    project = ProjectModel()
    ds = make_dataset(name="D1")
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{}]
    path = tmp_path / "missing_name.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    del raw['datasets'][0]['name']  # 'name' キーを手動で削除(壊れたファイルを再現)
    # 対応するdataset_group_treeのリーフのdataset_idは変えない(存在するIDのまま)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)

    reloaded = ProjectModel()
    with pytest.raises(ValueError, match="name"):
        reloaded.load_project(str(path))


def test_load_graphica_dataframe_mismatched_column_lengths_raises_clear_error(tmp_path):
    """
    データが壊れた.graphicaファイル: dfのdata辞書内で、列ごとのリストの
    長さがindexの長さと食い違っている(手編集や部分的な書き込み破損を想定)。
    サイレントにズレたデータが出来上がるのではなく、分かりやすい例外に
    なることを確認する。
    """
    project = ProjectModel()
    ds = make_dataset(name="D1")
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{}]
    path = tmp_path / "corrupt_df.graphica"
    project.save_project(str(path))

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    # 'y' 列だけ意図的に短くする(indexは3行分あるまま)
    raw['datasets'][0]['df']['data']['y'] = [10.0, 20.0]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)

    reloaded = ProjectModel()
    with pytest.raises(ValueError):
        reloaded.load_project(str(path))


# ---------------------------------------------------------------------------
# 3. stage1が試していないと思われるエッジケースの往復
# ---------------------------------------------------------------------------

def test_roundtrip_empty_zero_row_dataset(tmp_path):
    """
    0行のDataFrameを持つDatasetの往復。列は存在するが行が無いケース。

    このテストで当初見つかったギャップ(後日修正済み):
    Dataset._df_to_dict()/_df_from_dict() (core/dataset.py) は index を
    以前は素の list としてのみ保存/復元しており、行が0件のときは空リスト
    ([])から作られた Index の dtype が 'object' になり、元のDataFrameが
    持っていた(デフォルトコンストラクタ由来の)'int64' RangeIndexとは
    食い違っていた(行が1件以上あればpandasが値からdtypeを推定できるため
    問題にならない境界条件のバグだった)。_df_to_dict()がindexのdtypeも
    明示的に保存し、_df_from_dict()で復元時に付け直すよう修正済み。
    """
    df = pd.DataFrame({
        'x': pd.array([], dtype='float64'),
        'y': pd.array([], dtype='float64'),
    })
    ds = make_dataset(name="Empty", df=df)

    project = ProjectModel()
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{}]
    path = tmp_path / "empty_dataset.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    reloaded_df = reloaded.datasets[0].df
    assert len(reloaded_df) == 0
    assert list(reloaded_df.columns) == ['x', 'y']
    # ★ dtype(int64)は一致させるが、Indexの具象クラス(RangeIndex vs 素の
    # Index)まではJSON往復では区別しない(この違いはこのアプリのどこでも
    # 意味を持たないため、check_index_type=Falseでそこだけ許容する)。
    pd.testing.assert_frame_equal(reloaded_df, df, check_dtype=True, check_index_type=False)
    assert reloaded_df.index.dtype == 'int64'


def test_roundtrip_unicode_and_emoji_names_and_columns(tmp_path):
    """日本語アプリのため、データセット名・フォルダ名・列名に日本語や絵文字が
    使われるケースの往復を確認する(ensure_ascii=Falseの効果も含む)。"""
    df = pd.DataFrame({
        '温度(℃)': [20.5, 21.0],
        '💧湿度': [50.0, 55.5],
    })
    ds = make_dataset(name="測定データ📈", df=df, x_col_name='温度(℃)', y_col_name='💧湿度')

    project = ProjectModel()
    project.datasets = [ds]
    project.dataset_group_tree = {
        'name': '', 'children': [
            {'name': '実験フォルダ🧪', 'children': [{'dataset': ds}]},
        ],
    }
    project.all_plot_settings = [{}]
    path = tmp_path / "unicode.graphica"
    project.save_project(str(path))

    # ensure_ascii=False により、ファイル中に読める形の日本語が残っていること
    raw_text = path.read_text(encoding='utf-8')
    assert '測定データ📈' in raw_text
    assert '\\u' not in raw_text

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    reloaded_ds = reloaded.datasets[0]
    assert reloaded_ds.name == "測定データ📈"
    assert list(reloaded_ds.df.columns) == ['温度(℃)', '💧湿度']
    assert reloaded_ds.x_col_name == '温度(℃)'
    assert reloaded_ds.y_col_name == '💧湿度'
    assert reloaded.dataset_group_tree['children'][0]['name'] == '実験フォルダ🧪'


def test_roundtrip_dataset_group_tree_with_empty_folder(tmp_path):
    """データセットを1つも含まない空のフォルダノードが往復で保持されること。"""
    ds = make_dataset(name="D1")
    project = ProjectModel()
    project.datasets = [ds]
    project.dataset_group_tree = {
        'name': '',
        'children': [
            {'dataset': ds},
            {'name': '空フォルダ', 'children': []},
        ],
    }
    project.all_plot_settings = [{}]
    path = tmp_path / "empty_folder.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    assert len(reloaded.dataset_group_tree['children']) == 2
    empty_folder = reloaded.dataset_group_tree['children'][1]
    assert empty_folder == {'name': '空フォルダ', 'children': []}


def test_roundtrip_zero_datasets_project(tmp_path):
    """データセットが1つも無い(新規プロジェクトのまま保存する等の)ケース。"""
    project = ProjectModel()
    project.datasets = []
    project.dataset_group_tree = {'name': '', 'children': []}
    project.all_plot_settings = []
    path = tmp_path / "no_datasets.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    assert reloaded.datasets == []
    assert reloaded.dataset_group_tree == {'name': '', 'children': []}
    assert reloaded.all_plot_settings == []


def test_roundtrip_multiple_subplots_with_annotations_and_free_rect(tmp_path):
    """
    複数サブプロット(layout_rows/cols > 1, all_plot_settingsが2件以上)の
    それぞれについて、annotations/legend_order/free_rectが個別に往復すること。
    stage1のmake_rich_project()は2サブプロットだが、ここでは3サブプロット
    ('grid'レイアウトで rows=2, cols=2 の4区画中3つ使用)かつ、それぞれの
    annotationsが複数件・空リストの両方を含む形で確認する。
    """
    ds1 = make_dataset(name="D1")
    ds2 = make_dataset(name="D2", subplot_target=1)
    ds3 = make_dataset(name="D3", subplot_target=2)

    project = ProjectModel()
    project.datasets = [ds1, ds2, ds3]
    project.dataset_group_tree = {
        'name': '', 'children': [{'dataset': d} for d in (ds1, ds2, ds3)]
    }
    project.all_plot_settings = [
        {
            'title': 'Plot A',
            'annotations': [
                {'type': 'text', 'text': 'A1', 'xy': (1.0, 2.0), 'xytext': (1.5, 2.5)},
                {'type': 'text', 'text': 'A2', 'xy': (3.0, 4.0), 'xytext': (3.5, 4.5)},
            ],
            'legend_order': ['D1'],
            'free_rect': None,
        },
        {'title': 'Plot B', 'annotations': [], 'legend_order': ['D2'], 'free_rect': None},
        {
            'title': 'Plot C',
            'annotations': [{'type': 'arrow', 'text': 'C1', 'xy': (0.0, 0.0), 'xytext': (1.0, 1.0)}],
            'legend_order': ['D3'],
            'free_rect': None,
        },
    ]
    project.active_axis_index = 2
    project.layout_rows = 2
    project.layout_cols = 2
    project.layout_mode = 'grid'

    path = tmp_path / "multi_subplot.graphica"
    project.save_project(str(path))

    reloaded = ProjectModel()
    reloaded.load_project(str(path))

    assert len(reloaded.all_plot_settings) == 3
    assert reloaded.layout_rows == 2
    assert reloaded.layout_cols == 2
    assert reloaded.active_axis_index == 2

    settings = reloaded.all_plot_settings
    assert settings[0]['legend_order'] == ['D1']
    assert len(settings[0]['annotations']) == 2
    assert settings[0]['annotations'][1]['text'] == 'A2'
    assert list(settings[0]['annotations'][1]['xy']) == [3.0, 4.0]

    assert settings[1]['annotations'] == []
    assert settings[1]['legend_order'] == ['D2']

    assert settings[2]['annotations'][0]['type'] == 'arrow'
    assert settings[2]['legend_order'] == ['D3']
