"""入れたプラグインに新しい版が出ていないかを調べる(公開プラグインの一覧と GitHub Releases への匿名の GET だけ)。

一覧は本体リポジトリの docs/plugin_index.json(プラグインのフォルダ名・名前 → GitHub のリポジトリ)。
入れ替えは利用者が選んだものだけで、ここでは調べるのと、落とした zip を確かめるところまで。
"""
import json
import os
import urllib.request
import zipfile
from typing import Any, Callable, Iterable

from graphica.core.plugin_manifest import (
    PLUGIN_MANIFEST_FILENAME, PluginManifestError, is_compatible_api_version, load_plugin_manifest,
)
from graphica.core.update_check import GITHUB_REPO, _asset_info, is_newer_version

PLUGIN_INDEX_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/master/Graphica_project/docs/plugin_index.json"
_DEFAULT_TIMEOUT_SEC = 5
_HEADERS = {'Accept': 'application/vnd.github+json', 'User-Agent': 'Graphica-plugin-update-check'}


def _get_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def parse_plugin_index(data: Any) -> list[dict[str, str]]:
    """一覧の JSON から、folder と repo のそろった項目だけを返す(壊れた行は飛ばす)。

    Args:
        data: {"plugins": [{"folder", "name", "repo"}, ...]}。

    Returns:
        {"folder", "name", "repo"} のリスト。
    """
    entries = data.get('plugins') if isinstance(data, dict) else None
    result = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        folder, repo = entry.get('folder'), entry.get('repo')
        if isinstance(folder, str) and folder and isinstance(repo, str) and repo.count('/') == 1:
            result.append({'folder': folder, 'name': str(entry.get('name') or folder), 'repo': repo})
    return result


def fetch_plugin_index(timeout: float = _DEFAULT_TIMEOUT_SEC) -> list[dict[str, str]]:
    """公開プラグインの一覧。通信の失敗は例外のまま。"""
    return parse_plugin_index(_get_json(PLUGIN_INDEX_URL, timeout))


def fetch_latest_plugin_release(repo: str, timeout: float = _DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
    """repo の最新リリース: {"version", "html_url", "body", "zip"(添付の zip の情報か None)}。"""
    data = _get_json(f"https://api.github.com/repos/{repo}/releases/latest", timeout)
    zips = [_asset_info(asset) for asset in data.get('assets') or []
            if isinstance(asset, dict) and str(asset.get('name', '')).lower().endswith('.zip')]
    return {
        'version': str(data.get('tag_name') or '').lstrip('vV'),
        'html_url': data.get('html_url') or f"https://github.com/{repo}/releases",
        'body': data.get('body') or '',
        'zip': zips[0] if zips else None,
    }


def installed_user_plugins(plugins_dir: str) -> list[dict[str, str]]:
    """plugins_dir の直下のプラグイン({"folder", "name", "version"})。plugin.json が読めないものは飛ばす。"""
    result: list[dict[str, str]] = []
    if not os.path.isdir(plugins_dir):
        return result
    for folder in sorted(os.listdir(plugins_dir)):
        path = os.path.join(plugins_dir, folder)
        if folder.startswith('.') or not os.path.isdir(path):
            continue
        manifest: dict[str, Any] | None
        try:
            manifest = load_plugin_manifest(path)
        except PluginManifestError:
            # API の版が合わなくなった古いものも、新しい版で直るかもしれないので一覧には入れる
            manifest = _read_manifest_loosely(path)
        if manifest is None:
            continue
        result.append({'folder': folder, 'name': str(manifest.get('name') or folder),
                       'version': str(manifest.get('version') or '0')})
    return result


def _read_manifest_loosely(path: str) -> dict[str, Any] | None:
    try:
        with open(os.path.join(path, PLUGIN_MANIFEST_FILENAME), encoding='utf-8') as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def find_plugin_updates(installed: Iterable[dict[str, str]], index: list[dict[str, str]],
                        fetch_release: Callable[[str], dict[str, Any]]) -> list[dict[str, Any]]:
    """入れたプラグインのうち、一覧にあって新しい版の zip が出ているもの。

    Args:
        installed: installed_user_plugins() の結果。
        index: fetch_plugin_index() の結果。フォルダ名で、無ければ名前で突き合わせる。
        fetch_release: リポジトリ名 → fetch_latest_plugin_release() の結果。1件の失敗は飛ばす。

    Returns:
        {"folder", "name", "current", "latest", "repo", "html_url", "body", "zip"} のリスト。
    """
    by_folder = {entry['folder']: entry for entry in index}
    by_name = {entry['name']: entry for entry in index}
    updates = []
    for plugin in installed:
        entry = by_folder.get(plugin['folder']) or by_name.get(plugin['name'])
        if entry is None:
            continue
        try:
            release = fetch_release(entry['repo'])
        except Exception:  # 1つのリポジトリの失敗(消された・通信)でほかを止めない
            continue
        if release.get('zip') is None or not is_newer_version(release['version'], plugin['version']):
            continue
        updates.append({
            'folder': plugin['folder'], 'name': plugin['name'], 'current': plugin['version'],
            'latest': release['version'], 'repo': entry['repo'], 'html_url': release['html_url'],
            'body': release['body'], 'zip': release['zip'],
        })
    return updates


def check_plugin_updates(plugins_dir: str, timeout: float = _DEFAULT_TIMEOUT_SEC,
                         **_ignored: Any) -> list[dict[str, Any]]:
    """TaskRunner から呼ぶ入口。入れたものが無ければ通信しない。"""
    installed = installed_user_plugins(plugins_dir)
    if not installed:
        return []
    index = fetch_plugin_index(timeout)
    return find_plugin_updates(installed, index, lambda repo: fetch_latest_plugin_release(repo, timeout))


def zip_manifest(zip_path: str) -> dict[str, Any]:
    """zip の中のプラグインの plugin.json(トップのフォルダ直下)。見つからなければ PluginManifestError。"""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = [n for n in zf.namelist()
                     if n.endswith('/' + PLUGIN_MANIFEST_FILENAME) and n.count('/') == 1]
            if not names:
                raise PluginManifestError(f"zip に {PLUGIN_MANIFEST_FILENAME} が見つかりません。")
            manifest = json.loads(zf.read(names[0]).decode('utf-8'))
    except (zipfile.BadZipFile, ValueError, KeyError) as e:
        raise PluginManifestError(f"zip の {PLUGIN_MANIFEST_FILENAME} を読めません: {e}") from e
    if not isinstance(manifest, dict):
        raise PluginManifestError(f"{PLUGIN_MANIFEST_FILENAME} はJSONオブジェクトである必要があります。")
    return manifest


def check_update_zip(zip_path: str, folder: str) -> dict[str, Any]:
    """入れ替える前の確認: 同じフォルダ名のプラグインで、この Graphica の API で読めること。"""
    with zipfile.ZipFile(zip_path) as zf:
        tops = {name.split('/', 1)[0] for name in zf.namelist() if name.strip('/')}
    if tops != {folder}:
        raise PluginManifestError(f"zip の中身が「{folder}」のプラグインではありません。")
    manifest = zip_manifest(zip_path)
    if not is_compatible_api_version(manifest.get('api_version')):
        raise PluginManifestError(
            f"新しい版はこの Graphica では使えません(プラグイン API {manifest.get('api_version')})。"
            "Graphica を更新してから入れてください。")
    return manifest
