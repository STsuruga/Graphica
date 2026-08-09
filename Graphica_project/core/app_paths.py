# core/app_paths.py
"""
書き込み可能なアプリケーションデータディレクトリの解決 (C-009)。

gui/main_window.py の resource_path() が「読み取り専用の同梱リソース」
(アイコン・サンプルデータ等) を解決するのに対し、こちらは「ユーザー環境に
書き込む必要があるファイル」(現状はログファイルのみ) の置き場所を解決する。
exe化した際にインストール先が Program Files 配下だと書き込み権限が無く
失敗するため、必ずユーザーごとに書き込み保証がある %LOCALAPPDATA% (Windows)
配下に置く。resource_path() 同様、プロセスのカレントディレクトリには依存しない。
"""
import os

from core.version import APP_NAME


def get_app_data_dir():
    """
    書き込み可能なアプリケーションデータディレクトリのパスを返す(無ければ作成する)。

    - Windows: %LOCALAPPDATA%\\Graphica
    - LOCALAPPDATA が無い環境(Windows以外での開発時等): ~/.local/share/Graphica 相当
    """
    base = os.environ.get('LOCALAPPDATA')
    if not base:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    app_dir = os.path.join(base, APP_NAME)
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def get_user_plugins_dir():
    """
    ユーザーが追加するプラグインの置き場所のパスを返す(無ければ作成する、項目E-1)。

    exe化したビルドでは resource_path("plugins") が指す場所が PyInstaller の
    _internal フォルダの奥に埋もれてしまい、Program Files 配下等インストール先
    自体が読み取り専用のことも多く、ユーザーが自分でプラグインを配置できる
    場所として機能しない。get_app_data_dir() 配下の常に書き込み可能な場所に
    "plugins" を切ることで、exe配布環境でもユーザー自身がプラグインファイルを
    置ける場所を用意する(gui/main_window.py の plugin_search_paths() から
    resource_path("plugins") と併せて参照される)。
    """
    plugins_dir = os.path.join(get_app_data_dir(), 'plugins')
    os.makedirs(plugins_dir, exist_ok=True)
    return plugins_dir
