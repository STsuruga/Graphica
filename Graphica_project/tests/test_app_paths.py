# tests/test_app_paths.py
"""core/app_paths.py (C-009: ログ出力先を%LOCALAPPDATA%に統一) のテスト。"""
import os

from core.app_paths import get_app_data_dir
from core.version import APP_NAME


def test_get_app_data_dir_uses_localappdata_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    result = get_app_data_dir()
    assert result == os.path.join(str(tmp_path), APP_NAME)


def test_get_app_data_dir_creates_directory_if_missing(monkeypatch, tmp_path):
    fake_local_appdata = tmp_path / "does_not_exist_yet"
    monkeypatch.setenv('LOCALAPPDATA', str(fake_local_appdata))
    result = get_app_data_dir()
    assert os.path.isdir(result)


def test_get_app_data_dir_is_cwd_independent(monkeypatch, tmp_path):
    """カレントディレクトリを変えても解決先が変わらないことを確認する。"""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    original_cwd = os.getcwd()
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    try:
        os.chdir(str(other_dir))
        result = get_app_data_dir()
    finally:
        os.chdir(original_cwd)
    assert result == os.path.join(str(tmp_path), APP_NAME)


def test_get_app_data_dir_falls_back_when_localappdata_unset(monkeypatch, tmp_path):
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.delenv('XDG_DATA_HOME', raising=False)
    monkeypatch.setattr(os.path, 'expanduser', lambda p: str(fake_home) if p == '~' else p)
    result = get_app_data_dir()
    assert result == os.path.join(str(fake_home), '.local', 'share', APP_NAME)
    assert os.path.isdir(result)
