import pickle
import io
import json
import os
import logging

from core.dataset import Dataset
from core.json_utils import GraphicaJSONEncoder

logger = logging.getLogger(__name__)

# --- pickle 読み込みの安全対策 ---
# プロジェクトファイル(.pkl)は Dataset/DataFrame/ndarray などデータ専用の
# オブジェクトしか含まないはずなので、復元を許可するモジュールをホワイトリスト化する。
# これにより、細工された .pkl から os.system 等の任意コードが実行されるのを防ぐ。
_ALLOWED_MODULE_PREFIXES = (
    "numpy",
    "pandas",
    "core.dataset",
)
_ALLOWED_BUILTINS = {
    "builtins": {
        "object", "list", "dict", "set", "frozenset", "tuple", "str", "bytes",
        "bytearray", "int", "float", "complex", "bool", "slice", "range",
    },
    "collections": {"OrderedDict", "defaultdict"},
    "copyreg": {"_reconstructor", "__newobj__"},
}


class _RestrictedUnpickler(pickle.Unpickler):
    """許可されたモジュール/クラスのみ復元するUnpickler(任意コード実行対策)。"""

    def find_class(self, module, name):
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


# --- .graphica (JSON) 形式のバージョン管理 ---
# format_version導入前(このキー自体が無い)ファイルは version 0 として扱う。
# 破壊的な構造変更をする際は、CURRENT_FORMAT_VERSIONをインクリメントし、
# 旧バージョンからの変換関数を _MIGRATIONS に追加すること。
CURRENT_FORMAT_VERSION = 1


def _migrate_v0_to_v1(data):
    """format_version未導入(旧data構造そのもの)をversion 1として扱えるようにする。
    このバージョン間でデータ構造自体に変更は無く、format_versionフィールドの
    導入そのものが移行内容のため、変換処理はno-op。"""
    return data


# from_version -> データを (from_version + 1) に変換する関数
_MIGRATIONS = {
    0: _migrate_v0_to_v1,
}


def _migrate_project_data(data):
    """dataのformat_versionを見て、CURRENT_FORMAT_VERSIONまで順に移行する。
    未来バージョン(このアプリより新しいバージョンで保存されたファイル)は
    安全側に倒して明示的にエラーとする(無言でフィールドを無視して壊れた
    状態のまま読み込むことを避けるため)。"""
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


class ProjectModel:
    def __init__(self):
        # 現在のファイルパス
        self.current_filepath = ""

        # --- アプリケーションのコア状態（ここですべて一元管理） ---
        self.datasets = []              # Datasetオブジェクトのリスト
        # データセットのフォルダ分け構造。
        # {'name': str, 'children': [...]} の入れ子。
        # 子要素は {'name':..., 'children':[...]} (フォルダ) か
        # {'dataset': <Datasetオブジェクト>} (データセットのリーフ) のどちらか。
        # name='' のルートは表示されない仮想フォルダ。
        self.dataset_group_tree = {'name': '', 'children': []}
        self.all_plot_settings = []     # 各プロットの外観設定リスト
        self.active_axis_index = 0      # 現在編集中のプロット番号

        # --- レイアウト情報 ---
        self.layout_rows = 1            # 行数
        self.layout_cols = 1            # 列数
        # 'grid' (行数×列数の均等グリッド) か 'free' (サブプロットをドラッグで
        # 自由な位置・サイズに配置するレイアウト) か。'free'時は all_plot_settings の
        # 各要素数がそのままサブプロット数となり、各要素の 'free_rect' キーに
        # (left, bottom, width, height) の正規化座標(0〜1)が保持される。
        self.layout_mode = 'grid'

    def save_project(self, filepath):
        """
        現在のアプリケーション状態を保存する。
        拡張子によって保存形式を振り分ける:
          - .pkl      : 従来通りpickleで保存(挙動は変更なし)
          - .graphica : 新形式。JSONとして保存する(信頼できないファイルを
                        開いても任意コード実行が起きないよう、データ専用の
                        フォーマットにするための移行先)
        """
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.pkl':
            self._save_project_pickle(filepath)
        elif ext == '.graphica':
            self._save_project_json(filepath)
        else:
            raise ValueError(f"サポートされていない拡張子です: {ext}")

        self.current_filepath = filepath

    def load_project(self, filepath):
        """保存形式(拡張子)に応じてプロジェクトファイルを読み込む"""
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

    # --- .pkl (pickle) 形式 ---

    def _save_project_pickle(self, filepath):
        """現在のアプリケーション状態を丸ごとpickleで保存"""
        data = {
            'datasets': self.datasets,
            'dataset_group_tree': self.dataset_group_tree,
            'all_plot_settings': self.all_plot_settings,
            'active_axis_index': self.active_axis_index,
            'layout_rows': self.layout_rows,
            'layout_cols': self.layout_cols,
            'layout_mode': self.layout_mode,
        }
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

    def _load_project_pickle(self, filepath):
        """pickleファイルから状態を復元(信頼できるオブジェクトのみ許可)"""
        with open(filepath, 'rb') as f:
            try:
                data = _restricted_loads(f)
            except pickle.UnpicklingError:
                logger.exception("プロジェクトファイルの読み込みを拒否しました: %s", filepath)
                raise

        # 読み込んだデータを自身にセット
        self.datasets = data.get('datasets', [])
        # 古い形式の.pklファイル(フォルダ機能追加前)にはキーが無いため、
        # その場合は全データセットがルート直下にあるものとして構築し直す。
        self.dataset_group_tree = data.get('dataset_group_tree') or {
            'name': '', 'children': [{'dataset': ds} for ds in self.datasets]
        }
        self.all_plot_settings = data.get('all_plot_settings', [])
        self.active_axis_index = data.get('active_axis_index', 0)
        self.layout_rows = data.get('layout_rows', 1)
        self.layout_cols = data.get('layout_cols', 1)
        self.layout_mode = data.get('layout_mode', 'grid')

    # --- .graphica (JSON) 形式 ---

    @staticmethod
    def _tree_to_json(node):
        """dataset_group_tree を、Datasetの生参照を dataset_id 文字列に
        置き換えたJSON化可能な形に変換する(再帰)。"""
        if 'dataset' in node:
            return {'dataset_id': node['dataset'].dataset_id}
        return {
            'name': node.get('name', ''),
            'children': [ProjectModel._tree_to_json(child) for child in node.get('children', [])],
        }

    @staticmethod
    def _tree_from_json(node, dataset_map):
        """_tree_to_json() の逆変換。dataset_id を、読み込み済みdatasetsの
        中から見つけた実際のDatasetオブジェクト(同一インスタンス)に
        再リンクする。存在しないIDの場合は警告してそのリーフを除外する
        (壊れた/手編集されたファイルでも読み込みがクラッシュしないように)。"""
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

    def _save_project_json(self, filepath):
        """現在のアプリケーション状態をJSON(.graphica)として保存する"""
        data = {
            'format_version': CURRENT_FORMAT_VERSION,
            'datasets': [ds.to_dict() for ds in self.datasets],
            'dataset_group_tree': self._tree_to_json(self.dataset_group_tree),
            'all_plot_settings': self.all_plot_settings,
            'active_axis_index': self.active_axis_index,
            'layout_rows': self.layout_rows,
            'layout_cols': self.layout_cols,
            'layout_mode': self.layout_mode,
        }
        # ensure_ascii=False: データセット名/フォルダ名に日本語が使われることが
        # 多いため、\uXXXXエスケープではなく読める形でファイルに残す。
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=GraphicaJSONEncoder, indent=2, ensure_ascii=False)

    def _load_project_json(self, filepath):
        """JSON(.graphica)ファイルから状態を復元する"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        data = _migrate_project_data(data)

        self.datasets = [Dataset.from_dict(d) for d in data.get('datasets', [])]
        dataset_map = {ds.dataset_id: ds for ds in self.datasets}

        tree_data = data.get('dataset_group_tree')
        if tree_data:
            self.dataset_group_tree = self._tree_from_json(tree_data, dataset_map)
        else:
            # dataset_group_tree キーが無い場合(将来この形式が変わった場合等)は、
            # pickle側の後方互換処理と同様に、全データセットをルート直下に置く。
            self.dataset_group_tree = {
                'name': '', 'children': [{'dataset': ds} for ds in self.datasets]
            }

        self.all_plot_settings = data.get('all_plot_settings', [])
        self.active_axis_index = data.get('active_axis_index', 0)
        self.layout_rows = data.get('layout_rows', 1)
        self.layout_cols = data.get('layout_cols', 1)
        self.layout_mode = data.get('layout_mode', 'grid')
