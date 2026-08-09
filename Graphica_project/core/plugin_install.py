# core/plugin_install.py
"""
プラグインのzipインストール処理(項目E-2/E-4)。

環境設定ダイアログの「プラグインをインストール」ボタン(gui/dialogs.py の
PreferencesDialog._on_install_plugin)から呼ばれる。ダウンロードしたzipを
展開するだけの機能であり、ネットワーク経由での取得は行わない
(core/plugin_api.py と同じく、プラグインは信頼できる配布元のもののみ
導入すること)。
"""
import os
import shutil
import tempfile
import uuid
import zipfile

from core.app_paths import get_user_plugins_dir


class PluginInstallError(Exception):
    """zipのインストールに失敗したことを表す(呼び出し元でユーザーに表示する用途)"""


def _reject_unsafe_members(zf):
    # zip-slip対策: 展開前に全メンバーのパスを検査する。normpath後に ".." で
    # 始まる(target_dirの外に出る相対パス)か、絶対パスになっているものは
    # target_dir外への書き込みを意味するため拒否する。
    for member in zf.namelist():
        normalized = os.path.normpath(member)
        if normalized.startswith("..") or os.path.isabs(normalized):
            raise PluginInstallError(
                f"安全でないパスを含むzipファイルです(不正なエントリ: '{member}')。"
            )


def _find_plugin_root(staging_dir, zip_path):
    """
    展開済みのstaging_dir配下から、プラグイン本体のフォルダと採用する
    プラグイン名を決定する。

    Returns:
        tuple (str, str): (プラグイン本体のディレクトリの絶対パス, 採用する
        プラグインフォルダ名)。
    """
    if os.path.exists(os.path.join(staging_dir, "__init__.py")):
        # レイアウト(b): __init__.py がzipルート直下にある(フォルダに包まれていない)
        name = os.path.splitext(os.path.basename(zip_path))[0]
        return staging_dir, name

    entries = [e for e in os.listdir(staging_dir) if os.path.isdir(os.path.join(staging_dir, e))]
    if len(entries) == 1:
        candidate = os.path.join(staging_dir, entries[0])
        if os.path.exists(os.path.join(candidate, "__init__.py")):
            # レイアウト(a): 単一のトップレベルフォルダの中に __init__.py がある
            return candidate, entries[0]

    raise PluginInstallError(
        "zip内に __init__.py を持つプラグインが見つかりませんでした。"
        "プラグインフォルダそのもの、またはそのフォルダを1つだけ含むzipを指定してください。"
    )


def install_plugin_zip(zip_path, target_dir=None):
    """
    zip_path のプラグインを target_dir(省略時は get_user_plugins_dir())に
    インストールする。成功時はインストールしたプラグインのフォルダ名を返す。
    失敗時は PluginInstallError を送出する。
    """
    if target_dir is None:
        target_dir = get_user_plugins_dir()

    if not zipfile.is_zipfile(zip_path):
        raise PluginInstallError(f"'{zip_path}' は有効なzipファイルではありません。")

    # ステージング先はtarget_dirと同じボリューム上に作る(項目E-4): 最終的な
    # os.replace()を真のアトミックリネームにするため。target_dir配下に置いても、
    # ステージングディレクトリ自体のトップレベルには(レイアウト(a)の場合)
    # __init__.pyが無い(1階層下のリネーム前サブフォルダの中にあるだけ)ため、
    # 展開中にdiscover_plugin_dirs()がこれをプラグインとして誤検出することはない。
    staging_dir = tempfile.mkdtemp(prefix=".tmp_install_", dir=target_dir)
    try:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                _reject_unsafe_members(zf)
                zf.extractall(staging_dir)
        except zipfile.BadZipFile as e:
            raise PluginInstallError(f"zipファイルの展開に失敗しました: {e}") from e

        plugin_root, plugin_name = _find_plugin_root(staging_dir, zip_path)
        final_path = os.path.join(target_dir, plugin_name)

        stale_path = None
        if os.path.exists(final_path):
            # 再インストール(既存プラグインの上書き)。先に既存フォルダを
            # 退避してから新しいものを配置し、最後にまとめて削除する。
            stale_path = f"{final_path}.old-{uuid.uuid4().hex}"
            os.replace(final_path, stale_path)

        # レイアウト(b)の場合、plugin_root は staging_dir 自身であり、この
        # os.replace() でstaging_dir丸ごとがfinal_pathへ改名される。ごく短い間、
        # 展開済みでまだリネーム前のstaging_dir自身が「__init__.pyを直下に持つ
        # ディレクトリ」に見える一瞬(=discover_plugin_dirs()から見て
        # 壊れかけのプラグインに見えうる窓)が理論上あるが、単一プロセス内での
        # インストールを前提とし、本格的な単一インスタンス化(QLocalServer等)は
        # このロードマップの範囲外とする(既知の残存リスクとして明記)。
        os.replace(plugin_root, final_path)

        if stale_path is not None:
            shutil.rmtree(stale_path, ignore_errors=True)

        return plugin_name
    finally:
        # レイアウト(b)で既にstaging_dir自体がfinal_pathへ移動済みの場合、
        # このrmtreeは存在しないパスに対する安全な無視動作になる。
        shutil.rmtree(staging_dir, ignore_errors=True)
