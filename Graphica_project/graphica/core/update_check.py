"""GitHub Releases で新しい版があるかを見る。公開 API への匿名の GET だけで、利用者を特定できるものは送らない。"""
import json
import re
import urllib.error
import urllib.request

GITHUB_REPO = "STsuruga/Graphica"
_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_DEFAULT_TIMEOUT_SEC = 5


def _parse_version(version_str):
    """'v1.3.5' などを比べられる整数のタプルにする(数字以外は無視)。"""
    numbers = re.findall(r'\d+', version_str or '')
    return tuple(int(n) for n in numbers) if numbers else (0,)


def is_newer_version(remote_version, local_version):
    return _parse_version(remote_version) > _parse_version(local_version)


def fetch_latest_release_info(timeout=_DEFAULT_TIMEOUT_SEC):
    """最新版の {'tag_name', 'html_url', 'name'}。通信や解釈の失敗は例外のまま(呼び出し側で捕まえる)。"""
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
    }


def check_for_update(current_version, timeout=_DEFAULT_TIMEOUT_SEC, **_ignored):
    """TaskRunner 用。新しい版があれば {'tag_name', 'html_url', 'name'}、無ければ None。"""
    info = fetch_latest_release_info(timeout=timeout)
    if info['tag_name'] and is_newer_version(info['tag_name'], current_version):
        return info
    return None
