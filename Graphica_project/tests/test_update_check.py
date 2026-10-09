# tests/test_update_check.py
"""core/update_check.py(項目161、C-1203: アップデート通知)に対するテスト。"""
import json
import urllib.error

import pytest

import graphica.core.update_check as update_check_module
from graphica.core.update_check import check_for_update, fetch_latest_release_info, is_newer_version, pick_asset


# --- is_newer_version / _parse_version ---

def test_is_newer_version_true_for_higher_patch():
    assert is_newer_version("v1.3.6", "1.3.5") is True


def test_is_newer_version_false_for_equal_version():
    assert is_newer_version("v1.3.5", "1.3.5") is False


def test_is_newer_version_false_for_lower_version():
    assert is_newer_version("v1.3.4", "1.3.5") is False


def test_is_newer_version_compares_numerically_not_lexically():
    """'1.10.0' > '1.9.9' は文字列比較だと逆転する典型例、数値比較を検証する"""
    assert is_newer_version("v1.10.0", "1.9.9") is True


def test_is_newer_version_handles_missing_v_prefix():
    assert is_newer_version("2.0.0", "1.10.0") is True


def test_is_newer_version_handles_empty_string_gracefully():
    assert is_newer_version("", "1.3.5") is False


# --- fetch_latest_release_info (urllib.request.urlopenをモック) ---

class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode('utf-8')

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_latest_release_info_parses_expected_fields(monkeypatch):
    payload = {'tag_name': 'v1.4.0', 'html_url': 'https://github.com/x/y/releases/tag/v1.4.0', 'name': 'v1.4.0'}
    monkeypatch.setattr(update_check_module.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload))

    result = fetch_latest_release_info()

    assert result == {
        'tag_name': 'v1.4.0',
        'html_url': 'https://github.com/x/y/releases/tag/v1.4.0',
        'name': 'v1.4.0',
        'body': '',
        'assets': [],
    }


def test_fetch_latest_release_info_defaults_html_url_when_missing(monkeypatch):
    monkeypatch.setattr(update_check_module.urllib.request, "urlopen",
                         lambda *a, **k: _FakeResponse({'tag_name': 'v1.4.0'}))

    result = fetch_latest_release_info()

    assert result['html_url'] == f'https://github.com/{update_check_module.GITHUB_REPO}/releases'


def test_fetch_latest_release_info_propagates_network_errors(monkeypatch):
    def _raise(*a, **k):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(update_check_module.urllib.request, "urlopen", _raise)

    with pytest.raises(urllib.error.URLError):
        fetch_latest_release_info()


# --- check_for_update ---

def test_check_for_update_returns_info_when_newer_version_available(monkeypatch):
    monkeypatch.setattr(update_check_module, "fetch_latest_release_info",
                         lambda timeout=5: {'tag_name': 'v9.9.9', 'html_url': 'https://x', 'name': 'v9.9.9'})

    result = check_for_update("1.3.5")

    assert result == {'tag_name': 'v9.9.9', 'html_url': 'https://x', 'name': 'v9.9.9'}


def test_check_for_update_returns_none_when_already_latest(monkeypatch):
    monkeypatch.setattr(update_check_module, "fetch_latest_release_info",
                         lambda timeout=5: {'tag_name': 'v1.3.5', 'html_url': 'https://x', 'name': 'v1.3.5'})

    result = check_for_update("1.3.5")

    assert result is None


def test_check_for_update_accepts_and_ignores_task_runner_kwargs(monkeypatch):
    """TaskRunnerはreport_progress/is_cancelledを常にキーワード引数で渡すため、
    それらを無視して正常に動作すること。"""
    monkeypatch.setattr(update_check_module, "fetch_latest_release_info",
                         lambda timeout=5: {'tag_name': 'v1.3.5', 'html_url': 'https://x', 'name': 'v1.3.5'})

    result = check_for_update("1.3.5", report_progress=lambda *a: None, is_cancelled=lambda: False)

    assert result is None


# --- リリースノートと添付ファイル ---

RELEASE = {
    'tag_name': 'v2.2.0', 'html_url': 'https://github.com/x/y/releases/tag/v2.2.0', 'name': 'v2.2.0',
    'body': '## 新機能\n- something',
    'assets': [
        {'name': 'Graphica-2.2.0-setup.exe', 'browser_download_url': 'https://x/setup.exe', 'size': 123,
         'digest': 'sha256:ABCDEF'},
        {'name': 'Graphica-windows.zip', 'browser_download_url': 'https://x/win.zip', 'size': 456},
        {'name': 'Graphica-macos.zip', 'browser_download_url': 'https://x/mac.zip', 'size': 789, 'digest': None},
        'not a dict',
    ],
}


def test_fetch_reads_release_notes_and_assets(monkeypatch):
    monkeypatch.setattr(update_check_module.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(RELEASE))

    result = fetch_latest_release_info()

    assert result['body'] == '## 新機能\n- something'
    assert result['assets'] == [
        {'name': 'Graphica-2.2.0-setup.exe', 'url': 'https://x/setup.exe', 'size': 123, 'sha256': 'abcdef'},
        {'name': 'Graphica-windows.zip', 'url': 'https://x/win.zip', 'size': 456, 'sha256': ''},
        {'name': 'Graphica-macos.zip', 'url': 'https://x/mac.zip', 'size': 789, 'sha256': ''},
    ]


@pytest.mark.parametrize("kind, expected", [
    ('installer', 'Graphica-2.2.0-setup.exe'), ('windows_zip', 'Graphica-windows.zip'),
    ('macos', 'Graphica-macos.zip'), ('pip', None), ('source', None)])
def test_pick_asset_for_each_install_kind(monkeypatch, kind, expected):
    monkeypatch.setattr(update_check_module.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(RELEASE))
    asset = pick_asset(fetch_latest_release_info(), kind)
    assert (asset['name'] if asset else None) == expected


def test_pick_asset_returns_none_when_the_release_lacks_the_file():
    assert pick_asset({'assets': [{'name': 'other.zip', 'url': 'https://x/o.zip'}]}, 'installer') is None
    assert pick_asset({}, 'installer') is None
