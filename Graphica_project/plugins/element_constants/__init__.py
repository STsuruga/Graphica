# plugins/element_constants/__init__.py
"""
元素・物理定数テーブル(項目P-805)。データの検索・入力補正には一切データセット
(現在選択中のDataset)を必要としない参照ツールのため、register_analyzer
(Dataset必須)ではなくregister_panel(項目D-1)で常設のドックパネルとして提供する
(docs/Graphica_PLUGIN_BACKLOG.mdの「他パックの共通基盤」という位置づけの通り、
実データは plugins/element_constants/data.py 側に分離してあり、他のプラグインも
そのままimportして再利用できる)。

★ プラグインはcore/plugin_api.pyのPluginManager._load_module()により
graphica_plugin_element_constants という動的モジュール名でimportされ、
plugins.element_constants という「本物の」パッケージパスとしては存在しない
(sys.pathにGraphica_project/が乗っているかは実行形態=ソース実行/PyInstaller
フリーズ/ユーザープラグインディレクトリで変わるため信頼できない)。
そのため同じプラグインフォルダ内の他モジュール(data.py/panel.py)は、
spec_from_file_location(submodule_search_locations=...)が提供する相対import
(from . import ...)経由で参照する。
"""
from .data import ELEMENT_COLUMNS, CONSTANT_COLUMNS, find_element, find_constant
from .panel import ElementConstantsPanel


def _create_panel(project, undo_stack):
    return ElementConstantsPanel()


def register(api):
    api.register_panel("元素・物理定数テーブル", _create_panel, area="right")
