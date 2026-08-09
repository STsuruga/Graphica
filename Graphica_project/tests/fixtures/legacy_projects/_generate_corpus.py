# tests/fixtures/legacy_projects/_generate_corpus.py
"""
このディレクトリの後方互換コーパス(C-1205)を生成するための一回限りの
スクリプト。pytest実行時には一切importされない(ファイル名が test_ で
始まっていないため収集対象外)。

新しいフォーマット変更(format_versionのインクリメント等)を行った際、
「その変更の1つ前の世代のファイル」を新たにコーパスへ追加したくなったら、
このスクリプトに追記して再実行し、生成物をコミットすること。
既存のコーパスファイルは一度生成したら基本的に上書きしない
(過去のスナップショットとしての意味が無くなるため)。

実行方法:
    cd Graphica_project
    python tests/fixtures/legacy_projects/_generate_corpus.py
"""
import json
import os
import pickle

import numpy as np
import pandas as pd

from core.dataset import Dataset
from models.project import ProjectModel

HERE = os.path.dirname(os.path.abspath(__file__))


def _write_json(filename, data):
    path = os.path.join(HERE, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"wrote {path}")


def _write_pickle(filename, data):
    path = os.path.join(HERE, filename)
    with open(path, 'wb') as f:
        pickle.dump(data, f)
    print(f"wrote {path}")


def make_v0_no_format_version():
    """
    C-001(format_version導入)より前に保存された.graphica。
    現行のsave_project()で一度保存した上で、'format_version'キーを
    取り除いて再現する(=導入前のコードが実際に書いていたであろう内容と
    キー集合として同一)。
    """
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0, 4.0], 'y': [10.0, 15.0, 13.0, 22.0]})
    ds = Dataset(name="旧バージョンの測定データ", df=df, x_col_name='x', y_col_name='y', color='#2ca02c')

    project = ProjectModel()
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{'title': 'Plot 1'}]
    project.active_axis_index = 0
    project.layout_rows = 1
    project.layout_cols = 1
    project.layout_mode = 'grid'

    tmp_path = os.path.join(HERE, '_tmp_v0.graphica')
    project.save_project(tmp_path)
    with open(tmp_path, encoding='utf-8') as f:
        data = json.load(f)
    os.remove(tmp_path)
    del data['format_version']
    _write_json('v0_no_format_version.graphica', data)


def make_v0_dataset_missing_optional_fields():
    """
    Dataset側に新しいフィールド(alpha/gradient_enabled/waterfall_enabled/
    dataset_id等)が追加される前に保存された.graphicaを再現する。
    tests/test_project_model_json_compat.py の
    test_old_pickle_dataset_missing_dataclass_fields_backfilled_end_to_end は
    .pkl 経路のみをカバーしており、.graphica(JSON)側の同種コーパスが
    無かったためこちらに追加する。
    """
    df = pd.DataFrame({'x': [1.0, 2.0], 'y': [3.0, 4.0]})
    ds = Dataset(name="旧バージョンのデータセット", df=df, x_col_name='x', y_col_name='y')

    project = ProjectModel()
    project.datasets = [ds]
    project.dataset_group_tree = {'name': '', 'children': [{'dataset': ds}]}
    project.all_plot_settings = [{}]

    tmp_path = os.path.join(HERE, '_tmp_v0_dataset.graphica')
    project.save_project(tmp_path)
    with open(tmp_path, encoding='utf-8') as f:
        data = json.load(f)
    os.remove(tmp_path)
    del data['format_version']
    # 'dataset_id' は dataset_group_tree 側が参照しているため、ここでは
    # 意図的に残す(dataset_idの後方互換は別途 .pkl 側のコーパスで検証する)。
    for missing_field in (
        'alpha', 'gradient_enabled', 'gradient_color2', 'gradient_target',
        'waterfall_enabled', 'waterfall_offset_x', 'waterfall_offset_y',
        'show_point_labels', 'point_label_col_name',
        'masked_row_indices', 'use_secondary_y', 'fit_info',
    ):
        data['datasets'][0].pop(missing_field, None)
    _write_json('v0_dataset_missing_optional_fields.graphica', data)


def make_pre_folder_feature_pkl():
    """
    フォルダ分け機能(dataset_group_tree)・自由レイアウト機能(layout_mode)が
    追加される前の、最も古い世代の.pkl。当時のコードが実際に書いていた
    であろう最小のキー集合(datasets/all_plot_settings/active_axis_index/
    layout_rows/layout_cols のみ)を、save_project()を経由せず直接pickle化する。
    """
    df = pd.DataFrame({'wavelength': [400, 450, 500, 550], 'absorbance': [0.12, 0.34, 0.28, 0.09]})
    ds = Dataset(name="Sample A", df=df, x_col_name='wavelength', y_col_name='absorbance')
    data = {
        'datasets': [ds],
        'all_plot_settings': [{'title': 'UV-Vis'}],
        'active_axis_index': 0,
        'layout_rows': 1,
        'layout_cols': 1,
        # dataset_group_tree, layout_mode は意図的に省略
    }
    _write_pickle('pre_folder_feature.pkl', data)


def make_realistic_multi_dataset_project():
    """
    エッジケースではなく「実際のユーザーが保存しそうな」規模の.graphica。
    日本語データセット名・ネストしたフォルダ・複数サブプロット・注釈を含む、
    現実的なリグレッションアンカーとしてのコーパス。
    """
    df1 = pd.DataFrame({
        '時間(s)': np.linspace(0, 10, 20),
        '電圧(V)': np.sin(np.linspace(0, 10, 20)) * 2 + 5,
    })
    df2 = pd.DataFrame({
        '時間(s)': np.linspace(0, 10, 15),
        '電流(mA)': np.cos(np.linspace(0, 10, 15)) * 1.5 + 3,
    })
    ds1 = Dataset(name="測定1", df=df1, x_col_name='時間(s)', y_col_name='電圧(V)', color='#1f77b4')
    ds2 = Dataset(name="測定2", df=df2, x_col_name='時間(s)', y_col_name='電流(mA)',
                  color='#ff7f0e', subplot_target=1)

    project = ProjectModel()
    project.datasets = [ds1, ds2]
    project.dataset_group_tree = {
        'name': '', 'children': [
            {'name': '実験A', 'children': [{'dataset': ds1}, {'dataset': ds2}]},
        ],
    }
    project.all_plot_settings = [
        {
            'title': '電圧プロット',
            'annotations': [{'type': 'text', 'text': 'ピーク', 'xy': (5.0, 6.5), 'xytext': (6.0, 7.0)}],
            'legend_order': ['測定1'],
            'free_rect': None,
        },
        {'title': '電流プロット', 'annotations': [], 'legend_order': ['測定2'], 'free_rect': None},
    ]
    project.active_axis_index = 0
    project.layout_rows = 1
    project.layout_cols = 2
    project.layout_mode = 'grid'

    path = os.path.join(HERE, 'realistic_multi_dataset.graphica')
    project.save_project(path)
    print(f"wrote {path}")


if __name__ == '__main__':
    make_v0_no_format_version()
    make_v0_dataset_missing_optional_fields()
    make_pre_folder_feature_pkl()
    make_realistic_multi_dataset_project()
