"""
書き込み可能なユーザー単位のフォルダ(Windows では %LOCALAPPDATA%\\Graphica 配下)。

読み取り専用の同梱リソースは resource_path() で読む。インストール先(Program Files)は
書き込めないので、アプリが書くものは必ずここに置く。カレントディレクトリには依存しない。
"""
import os
import re

from graphica.core.version import APP_NAME


def get_app_data_dir() -> str:
    """無ければ作る。LOCALAPPDATA の無い環境では ~/.local/share/Graphica。"""
    base = os.environ.get('LOCALAPPDATA')
    if not base:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    app_dir = os.path.join(base, APP_NAME)
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def get_user_plugins_dir() -> str:
    """利用者が zip から入れたプラグインの置き場所。無ければ作る。"""
    plugins_dir = os.path.join(get_app_data_dir(), 'plugins')
    os.makedirs(plugins_dir, exist_ok=True)
    return plugins_dir


def get_plugin_data_dir(plugin_name: str) -> str:
    """プラグインごとの書き込み用フォルダ。無ければ作る。名前はフォルダ名に使える文字だけ残す。"""
    safe_name = re.sub(r'[^\w.-]', '_', plugin_name).strip('.') or '_'
    data_dir = os.path.join(get_app_data_dir(), 'plugin_data', safe_name)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir
