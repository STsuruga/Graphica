"""プラグインの zip を展開してインストールする(取得はしない。信頼できる配布元のものだけを入れること)。"""
import os
import shutil
import tempfile
import uuid
import zipfile

from graphica.core.app_paths import get_user_plugins_dir


class PluginInstallError(Exception):
    """メッセージはそのまま利用者に見せる。"""


def _reject_unsafe_members(zf: zipfile.ZipFile) -> None:
    # zip-slip: 正規化して .. で始まるか絶対パスなら、target_dir の外に書くので拒否する
    for member in zf.namelist():
        normalized = os.path.normpath(member)
        if normalized.startswith("..") or os.path.isabs(normalized):
            raise PluginInstallError(
                f"安全でないパスを含むzipファイルです(不正なエントリ: '{member}')。"
            )


def _find_plugin_root(staging_dir: str, zip_path: str) -> tuple[str, str]:
    """(プラグイン本体のフォルダの絶対パス, 採用するフォルダ名)"""
    if os.path.exists(os.path.join(staging_dir, "__init__.py")):
        # __init__.py が zip の直下にある
        name = os.path.splitext(os.path.basename(zip_path))[0]
        return staging_dir, name

    entries = [e for e in os.listdir(staging_dir) if os.path.isdir(os.path.join(staging_dir, e))]
    if len(entries) == 1:
        candidate = os.path.join(staging_dir, entries[0])
        if os.path.exists(os.path.join(candidate, "__init__.py")):
            # 1つのフォルダの中に __init__.py がある
            return candidate, entries[0]

    raise PluginInstallError(
        "zip内に __init__.py を持つプラグインが見つかりませんでした。"
        "プラグインフォルダそのもの、またはそのフォルダを1つだけ含むzipを指定してください。"
    )


def install_plugin_zip(zip_path: str, target_dir: str | None = None) -> str:
    """target_dir(省略時は get_user_plugins_dir())に入れ、フォルダ名を返す。失敗は PluginInstallError。"""
    if target_dir is None:
        target_dir = get_user_plugins_dir()

    if not zipfile.is_zipfile(zip_path):
        raise PluginInstallError(f"'{zip_path}' は有効なzipファイルではありません。")

    # 展開先は target_dir と同じボリュームに作る(最後の os.replace() を原子的な改名にするため)。
    # 展開先の直下には __init__.py が無いので、プラグインとして誤って見つかることはない
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
            # 上書きのときは、既存のものを先に退避して最後に消す
            stale_path = f"{final_path}.old-{uuid.uuid4().hex}"
            os.replace(final_path, stale_path)

        # zip の直下に __init__.py があった場合、改名までの一瞬だけ展開先が半端なプラグインに見える。
        # 1つのプロセスで入れる前提なので、そのままにしている
        os.replace(plugin_root, final_path)

        if stale_path is not None:
            shutil.rmtree(stale_path, ignore_errors=True)

        return plugin_name
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
