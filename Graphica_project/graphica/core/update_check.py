"""GitHub Releases で新しい版があるかを見る。公開 API への匿名の GET だけで、利用者を特定できるものは送らない。"""
import json
import re
import urllib.error
import urllib.request
from typing import Any

GITHUB_REPO = "STsuruga/Graphica"
_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_DEFAULT_TIMEOUT_SEC = 5


def _parse_version(version_str: str) -> tuple[int, ...]:
    """'v1.3.5' などを比べられる整数のタプルにする(数字以外は無視)。"""
    numbers = re.findall(r'\d+', version_str or '')
    return tuple(int(n) for n in numbers) if numbers else (0,)


def is_newer_version(remote_version: str, local_version: str) -> bool:
    return _parse_version(remote_version) > _parse_version(local_version)


def _asset_info(asset: dict[str, Any]) -> dict[str, Any]:
    digest = asset.get('digest') or ''
    return {
        'name': asset.get('name', '') or '',
        'url': asset.get('browser_download_url', '') or '',
        'size': int(asset.get('size') or 0),
        # GitHub が添付ファイルに付ける 'sha256:<16進>'。無い(古い)添付ファイルでは空
        'sha256': digest.split(':', 1)[1].lower() if digest.startswith('sha256:') else '',
    }


def fetch_latest_release_info(timeout: float = _DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
    """最新版の {'tag_name', 'html_url', 'name', 'body'(リリースノート), 'assets'(添付ファイル)}。

    通信や解釈の失敗は例外のまま(呼び出し側で捕まえる)。
    """
    request = urllib.request.Request(
        _RELEASES_LATEST_URL,
        headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Graphica-update-check'},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode('utf-8'))
    return {
        'tag_name': data.get('tag_name', '') or '',
        'html_url': data.get('html_url') or f'https://github.com/{GITHUB_REPO}/releases',
        'name': data.get('name', '') or '',
        'body': data.get('body', '') or '',
        'assets': [_asset_info(asset) for asset in data.get('assets') or [] if isinstance(asset, dict)],
    }


# 配布の形 -> 更新に使う添付ファイルの名前の条件(リリースに付ける名前は docs/dev/RELEASE_CHECKLIST.md)
_ASSET_MATCHERS = {
    'installer': lambda name: name.startswith('Graphica-') and name.endswith('-setup.exe'),
    'windows_zip': lambda name: name == 'Graphica-windows.zip',
    'macos': lambda name: name == 'Graphica-macos.zip',
}


def pick_asset(update_info: dict[str, Any], install_kind: str) -> dict[str, Any] | None:
    """その配布の形の更新に使う添付ファイル。無ければ None(ダウンロードページを案内する)。"""
    matches = _ASSET_MATCHERS.get(install_kind)
    if matches is None:
        return None
    for asset in update_info.get('assets') or []:
        if asset.get('url') and matches(asset.get('name', '')):
            return asset
    return None


def check_for_update(current_version: str, timeout: float = _DEFAULT_TIMEOUT_SEC, **_ignored: Any) -> dict[str, Any] | None:
    """TaskRunner 用。新しい版があれば fetch_latest_release_info() の辞書、無ければ None。"""
    info = fetch_latest_release_info(timeout=timeout)
    if info['tag_name'] and is_newer_version(info['tag_name'], current_version):
        return info
    return None
