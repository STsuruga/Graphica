# core/update_check.py
"""
GitHub Releasesを参照したアップデート通知(項目161、C-1203)。

「取得のみ・送信なし」: 公開のGitHub REST APIへ匿名GETリクエストを送るだけで、
ユーザーを特定できる情報は一切送信しない(User-Agent以外のヘッダも付けない)。
GUIに一切依存しない純粋関数のみを置く(gui/mixins/help_mixin.pyのTaskRunner経由で
バックグラウンド実行される想定)。
"""
import json
import re
import urllib.error
import urllib.request

GITHUB_REPO = "STsuruga/Graphica"
_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_DEFAULT_TIMEOUT_SEC = 5


def _parse_version(version_str):
    """
    'v1.3.5' や '1.3.5' のようなバージョン文字列を、比較可能な整数タプルに変換する。
    数値以外の部分(プレリリースサフィックス等)は無視し、抽出できた数値部分だけを使う。
    """
    numbers = re.findall(r'\d+', version_str or '')
    return tuple(int(n) for n in numbers) if numbers else (0,)


def is_newer_version(remote_version, local_version):
    """remote_versionがlocal_versionより新しいかどうかを判定する(純粋関数)。"""
    return _parse_version(remote_version) > _parse_version(local_version)


def fetch_latest_release_info(timeout=_DEFAULT_TIMEOUT_SEC):
    """
    GitHub Releasesの最新版情報を取得する。

    Returns:
        dict: {'tag_name': str, 'html_url': str, 'name': str}

    Raises:
        urllib.error.URLError, TimeoutError, ValueError等: ネットワーク/パース
            エラー。呼び出し側(TaskRunner経由)でキャッチし、アップデート確認の
            失敗がアプリの他の動作に影響しないようにする想定。
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
    }


def check_for_update(current_version, timeout=_DEFAULT_TIMEOUT_SEC, **_ignored):
    """
    アップデート確認のエントリポイント(gui.task_runner.TaskRunnerに渡すfn想定、
    report_progress/is_cancelled引数は無視するため**_ignoredで受け流す)。

    Returns:
        dict | None: 現在のバージョンより新しい版があれば
            {'tag_name', 'html_url', 'name'}、無ければ(取得成功だが最新版)None。
    """
    info = fetch_latest_release_info(timeout=timeout)
    if info['tag_name'] and is_newer_version(info['tag_name'], current_version):
        return info
    return None
