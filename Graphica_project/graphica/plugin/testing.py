"""
プラグインのテスト用の公開の入口。Graphica を起動せずに試せる。

    from graphica.plugin.testing import FakeGraphicaPluginAPI, FakePluginContext, load_plugin_like_graphica
"""
import os
import shutil
import tempfile

from graphica.core.plugin_api import GraphicaPluginAPI, PluginManager
from graphica.core.plugin_install import PluginInstallError, install_plugin_zip
from graphica.core.plugin_testing import FakeGraphicaPluginAPI, FakePluginContext

__all__ = [
    "FakeGraphicaPluginAPI",
    "FakePluginContext",
    "PluginInstallError",
    "install_zip_like_graphica",
    "load_plugin_like_graphica",
]


def load_plugin_like_graphica(plugin_folder, work_dir=None):
    """
    本体と同じ経路(manifest の検証 → import → register(api))でプラグインを読み込む。
    相対 import の誤りや api_version の不一致など、偽物の API では見つからない問題を確かめる。

    Args:
        plugin_folder (str): plugin.json と __init__.py のあるフォルダ。
        work_dir (str | None): 写しを置く場所(pytest の tmp_path など)。省略時は一時フォルダ。
    Returns:
        tuple[GraphicaPluginAPI, dict]: 登録を受けた API と、読み込み結果
            ({"name", "info", "error", "disabled"}。成功なら error は None)。
            フック単位の失敗は api.registration_errors にある。
    """
    plugin_folder = os.path.normpath(plugin_folder)
    name = os.path.basename(plugin_folder)
    # 本体は探索フォルダの中のサブフォルダをすべてプラグインとみなすので、対象だけを写した場所で読む。
    plugins_dir = tempfile.mkdtemp(prefix="graphica_plugins_", dir=work_dir)
    shutil.copytree(plugin_folder, os.path.join(plugins_dir, name),
                    ignore=shutil.ignore_patterns("__pycache__"))
    api = GraphicaPluginAPI()
    records = PluginManager(plugins_dir).load_all(api)
    return api, records[0]


def install_zip_like_graphica(zip_path, target_dir):
    """
    本体の「プラグインをインストール」と同じ処理で zip を target_dir に展開する。

    Returns:
        str: インストールされたプラグインのフォルダ名。
    Raises:
        PluginInstallError: zip の中身が本体の期待する形でない。
    """
    return install_plugin_zip(zip_path, target_dir=target_dir)
