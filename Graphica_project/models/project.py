import pickle
import io
import os
import logging

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

        self.current_filepath = filepath

    def load_project(self, filepath):
        """pickleファイルから状態を復元(信頼できるオブジェクトのみ許可)"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"ファイルが見つかりません: {filepath}")

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

        self.current_filepath = filepath
