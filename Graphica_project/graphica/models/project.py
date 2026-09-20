import hashlib
import pickle
import json
import os
import logging

from PySide6.QtCore import QObject, Signal

from graphica.core.dataset import Dataset
from graphica.core.json_utils import GraphicaJSONEncoder

logger = logging.getLogger(__name__)

# .pkl から復元してよいモジュール。細工された .pkl で任意のコードを実行されないように
_ALLOWED_MODULE_PREFIXES = (
    "numpy",
    "pandas",
    "graphica.core.dataset",
)
# パッケージを graphica.* に移す前に保存した .pkl は、Dataset を "core.dataset" の名前で持っている。
_RENAMED_MODULES = {"core.dataset": "graphica.core.dataset"}
_ALLOWED_BUILTINS = {
    "builtins": {
        "object", "list", "dict", "set", "frozenset", "tuple", "str", "bytes",
        "bytearray", "int", "float", "complex", "bool", "slice", "range",
    },
    "collections": {"OrderedDict", "defaultdict"},
    "copyreg": {"_reconstructor", "__newobj__"},
}


class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        module = _RENAMED_MODULES.get(module, module)
        allowed_names = _ALLOWED_BUILTINS.get(module)
        if allowed_names is not None and name in allowed_names:
            return super().find_class(module, name)
        if any(module == prefix or module.startswith(prefix + ".") for prefix in _ALLOWED_MODULE_PREFIXES):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"読み込みが許可されていないオブジェクトです ({module}.{name})。"
            "信頼できないファイルの可能性があります。"
        )


def _restricted_loads(fileobj):
    return _RestrictedUnpickler(fileobj).load()


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
        """拡張子で形式を決める。.pkl は pickle、.graphica は JSON(開いてもコードが実行されない)。"""
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.pkl':
            self._save_project_pickle(filepath)
        elif ext == '.graphica':
            self._save_project_json(filepath)
        else:
            raise ValueError(f"サポートされていない拡張子です: {ext}")

        self.current_filepath = filepath

    def load_project(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"ファイルが見つかりません: {filepath}")

        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.pkl':
            self._load_project_pickle(filepath)
        elif ext == '.graphica':
            self._load_project_json(filepath)
        else:
            raise ValueError(f"サポートされていない拡張子です: {ext}")

        self.current_filepath = filepath


    def _save_project_pickle(self, filepath):
        data = {
            'datasets': self.datasets,
            'dataset_group_tree': self.dataset_group_tree,
            'all_plot_settings': self.all_plot_settings,
            'active_axis_index': self.active_axis_index,
            'layout_rows': self.layout_rows,
            'layout_cols': self.layout_cols,
            'layout_mode': self.layout_mode,
            'panel_labels_enabled': self.panel_labels_enabled,
            'share_x_axis': self.share_x_axis,
            'share_y_axis': self.share_y_axis,
        }
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

    def _load_project_pickle(self, filepath):
        """許可したクラスだけを復元する。"""
        with open(filepath, 'rb') as f:
            try:
                data = _restricted_loads(f)
            except pickle.UnpicklingError:
                logger.exception("プロジェクトファイルの読み込みを拒否しました: %s", filepath)
                raise

        self.datasets = data.get('datasets', [])
        # フォルダ機能より前の .pkl にはキーが無いので、全部をルートに置く
        self.dataset_group_tree = data.get('dataset_group_tree') or {
            'name': '', 'children': [{'dataset': ds} for ds in self.datasets]
        }
        self.all_plot_settings = data.get('all_plot_settings', [])
        self.active_axis_index = data.get('active_axis_index', 0)
        self.layout_rows = data.get('layout_rows', 1)
        self.layout_cols = data.get('layout_cols', 1)
        self.layout_mode = data.get('layout_mode', 'grid')
        self.panel_labels_enabled = data.get('panel_labels_enabled', False)
        self.share_x_axis = data.get('share_x_axis', False)
        self.share_y_axis = data.get('share_y_axis', False)


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
        """_tree_to_json() の逆。見つからない ID は警告して除く(壊れたファイルでも読めるように)。"""
        if 'dataset_id' in node:
            ds = dataset_map.get(node['dataset_id'])
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
        dataset_map = {ds.dataset_id: ds for ds in self.datasets}

        tree_data = data.get('dataset_group_tree')
        if tree_data:
            self.dataset_group_tree = self._tree_from_json(tree_data, dataset_map)
        else:
            # キーが無ければ、.pkl と同じく全部をルートに置く
            self.dataset_group_tree = {
                'name': '', 'children': [{'dataset': ds} for ds in self.datasets]
            }

        self.all_plot_settings = data.get('all_plot_settings', [])
        self.active_axis_index = data.get('active_axis_index', 0)
        self.layout_rows = data.get('layout_rows', 1)
        self.layout_cols = data.get('layout_cols', 1)
        self.layout_mode = data.get('layout_mode', 'grid')
        self.panel_labels_enabled = data.get('panel_labels_enabled', False)
        self.share_x_axis = data.get('share_x_axis', False)
        self.share_y_axis = data.get('share_y_axis', False)
