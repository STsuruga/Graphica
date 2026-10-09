import hashlib
import json
import os
import logging
import uuid

from PySide6.QtCore import QObject, Signal

from graphica.core.dataset import Dataset
from graphica.core.json_utils import GraphicaJSONEncoder

logger = logging.getLogger(__name__)

# 保存は .gra。.graphica(以前の拡張子)も中身は同じ JSON なので読み書きできる
PROJECT_FILE_EXTENSION = '.gra'
PROJECT_FILE_EXTENSIONS = ('.gra', '.graphica')
LEGACY_PICKLE_EXTENSION = '.pkl'


# format_version が無いファイルは 0。構造を変えたら上げて、前の版からの変換を _MIGRATIONS に足す
CURRENT_FORMAT_VERSION = 1


def _migrate_v0_to_v1(data):
    """0 から 1 は format_version を足しただけで、構造は同じ。"""
    return data


# from_version -> (from_version + 1) の形にする関数
_MIGRATIONS = {
    0: _migrate_v0_to_v1,
}


def _migrate_project_data(data):
    """CURRENT_FORMAT_VERSION まで順に変換する。新しい版のファイルはエラーにする(黙って半分だけ読まない)。"""
    version = data.get('format_version', 0)
    if version > CURRENT_FORMAT_VERSION:
        raise ValueError(
            f"このプロジェクトファイルはバージョン{version}で保存されていますが、"
            f"このアプリケーションが対応しているのはバージョン{CURRENT_FORMAT_VERSION}までです。"
            "アプリケーションを最新版に更新してください。"
        )
    while version < CURRENT_FORMAT_VERSION:
        migrate = _MIGRATIONS.get(version)
        if migrate is None:
            raise ValueError(f"バージョン{version}からの移行手順が見つかりません。")
        data = migrate(data)
        version += 1
    return data


class ProjectModel(QObject):
    """1つの文書(データセット、軸ごとの設定、レイアウト)。

    既存の変更箇所は PlotterApp._update_plot() を直接呼ぶ。changed は、そのメソッドを知らない新しい経路が
    再描画を頼むためのもので、今は誰も発行しない。
    """

    changed = Signal()

    def __init__(self):
        super().__init__()
        # 最後に保存・読み込みしたパス(オートセーブでも変わる。上書き保存先は PlotterApp._current_project_path)
        self.current_filepath = ""

        self.datasets = []
        # {'name', 'children': [...]} の入れ子。子はフォルダか {'dataset': Dataset}。name='' のルートは表示しない
        self.dataset_group_tree = {'name': '', 'children': []}
        self.all_plot_settings = []     # 軸ごとの設定(core/axis_settings.py)
        self.active_axis_index = 0

        self.layout_rows = 1
        self.layout_cols = 1
        # 'grid' か 'free'。'free' では all_plot_settings の数がサブプロットの数で、各設定の
        # 'free_rect' に (left, bottom, width, height) を 0〜1 で持つ
        self.layout_mode = 'grid'

        # (a)(b)(c)… は描くときに並びから決めるので、文字は保存しない
        self.panel_labels_enabled = False

        # 同じ行(sharex)・同じ列(sharey)のサブプロットの軸を束ね、内側の目盛りラベルを隠す。グリッドのときだけ
        self.share_x_axis = False
        self.share_y_axis = False

    def notify_changed(self):
        self.changed.emit()

    def save_project(self, filepath):
        """JSON で保存する(開いてもコードが実行されない)。拡張子は .gra か .graphica。"""
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in PROJECT_FILE_EXTENSIONS:
            raise ValueError(f"サポートされていない拡張子です: {ext}")
        self._save_project_json(filepath)
        self.current_filepath = filepath

    def load_project(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"ファイルが見つかりません: {filepath}")

        ext = os.path.splitext(filepath)[1].lower()
        if ext == LEGACY_PICKLE_EXTENSION:
            raise ValueError("旧形式(.pkl)のプロジェクトには対応していません。")
        if ext not in PROJECT_FILE_EXTENSIONS:
            raise ValueError(f"サポートされていない拡張子です: {ext}")
        self._load_project_json(filepath)
        self.current_filepath = filepath

    @staticmethod
    def _tree_to_json(node):
        """Dataset の参照を dataset_id の文字列にする(JSON にするため)。"""
        if 'dataset' in node:
            return {'dataset_id': node['dataset'].dataset_id}
        return {
            'name': node.get('name', ''),
            'children': [ProjectModel._tree_to_json(child) for child in node.get('children', [])],
        }

    @staticmethod
    def _tree_from_json(node, dataset_map):
        """_tree_to_json() の逆。見つからない ID は警告して除く(壊れたファイルでも読めるように)。

        dataset_map は ID -> まだ並びに置いていないデータセットの列。同じ ID の系列があれば(複製が ID まで写していた
        ころのファイル)、出てきた順に1本ずつ割り当てる。
        """
        if 'dataset_id' in node:
            candidates = dataset_map.get(node['dataset_id'])
            ds = candidates.pop(0) if candidates else None
            if ds is None:
                logger.warning(
                    "dataset_group_tree内に存在しないdataset_idがあるため、"
                    "このリーフをスキップします: %s", node['dataset_id']
                )
                return None
            return {'dataset': ds}

        children = []
        for child in node.get('children', []):
            converted = ProjectModel._tree_from_json(child, dataset_map)
            if converted is not None:
                children.append(converted)
        return {'name': node.get('name', ''), 'children': children}

    def _make_dataset_ids_unique(self):
        """同じ ID の2本目以降に新しい ID を振る(並びを決めてから。統計値ラベルなどの参照は1本目を指したまま)。"""
        seen = set()
        for ds in self.datasets:
            if ds.dataset_id in seen:
                logger.warning("同じ dataset_id のデータセットがあったため、新しい ID を振りました: %s", ds.name)
                ds.dataset_id = uuid.uuid4().hex
            seen.add(ds.dataset_id)

    def content_fingerprint(self):
        """保存すると書き出される内容のハッシュ(未保存の変更の判定)。

        Undo の clean 状態では判定しない(軸の設定・列の計算・フォルダ操作は Undo の対象外)。
        呼ぶ前に UI にしか無い状態を反映しておくこと(PlotterApp._sync_project_from_ui)。
        """
        payload = self._json_payload()
        # 編集対象のサブプロットを切り替えただけで保存の確認が出ないように
        payload.pop('active_axis_index', None)
        text = json.dumps(payload, cls=GraphicaJSONEncoder, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _json_payload(self):
        """.graphica に書き出す辞書(保存と content_fingerprint で共有)。"""
        return {
            'format_version': CURRENT_FORMAT_VERSION,
            'datasets': [ds.to_dict() for ds in self.datasets],
            'dataset_group_tree': self._tree_to_json(self.dataset_group_tree),
            'all_plot_settings': self.all_plot_settings,
            'active_axis_index': self.active_axis_index,
            'layout_rows': self.layout_rows,
            'layout_cols': self.layout_cols,
            'layout_mode': self.layout_mode,
            'panel_labels_enabled': self.panel_labels_enabled,
            'share_x_axis': self.share_x_axis,
            'share_y_axis': self.share_y_axis,
        }

    def _save_project_json(self, filepath):
        data = self._json_payload()
        # 名前に日本語が多いので \uXXXX にせず読める形で残す
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=GraphicaJSONEncoder, indent=2, ensure_ascii=False)

    def _load_project_json(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        data = _migrate_project_data(data)

        self.datasets = [Dataset.from_dict(d) for d in data.get('datasets', [])]
        dataset_map = {}
        for ds in self.datasets:
            dataset_map.setdefault(ds.dataset_id, []).append(ds)

        tree_data = data.get('dataset_group_tree')
        if tree_data:
            self.dataset_group_tree = self._tree_from_json(tree_data, dataset_map)
        else:
            # キーが無ければ、.pkl と同じく全部をルートに置く
            self.dataset_group_tree = {
                'name': '', 'children': [{'dataset': ds} for ds in self.datasets]
            }
        self._make_dataset_ids_unique()

        self.all_plot_settings = data.get('all_plot_settings', [])
        self.active_axis_index = data.get('active_axis_index', 0)
        self.layout_rows = data.get('layout_rows', 1)
        self.layout_cols = data.get('layout_cols', 1)
        self.layout_mode = data.get('layout_mode', 'grid')
        self.panel_labels_enabled = data.get('panel_labels_enabled', False)
        self.share_x_axis = data.get('share_x_axis', False)
        self.share_y_axis = data.get('share_y_axis', False)
