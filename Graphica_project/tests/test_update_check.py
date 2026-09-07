# tests/test_update_check.py
"""core/update_check.py(項目161、C-1203: アップデート通知)に対するテスト。"""
import json
import urllib.error
from io import BytesIO

import pytest

import core.update_check as update_check_module
from core.update_check import is_newer_version, fetch_latest_release_info, check_for_update


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
