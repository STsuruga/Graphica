"""gui/updater.py: 配布の形の見分け、インストーラーのダウンロードと確かめ、起動。"""
import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

import graphica.gui.updater as updater


# --- 配布の形 ---

def test_frozen_on_macos_is_macos(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert updater.install_kind() == 'macos'


def test_frozen_with_the_uninstaller_is_the_installer_version(monkeypatch, tmp_path):
    (tmp_path / "unins000.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Graphica.exe"))
    assert updater.install_kind() == 'installer'


def test_frozen_without_the_uninstaller_is_the_zip_version(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Graphica.exe"))
    assert updater.install_kind() == 'windows_zip'


class _FakeDistribution:
    def __init__(self, direct_url):
        self._direct_url = direct_url

    def read_text(self, name):
        return self._direct_url


@pytest.mark.parametrize("direct_url, expected", [
    (None, 'pip'),  # PyPI から入れた wheel には direct_url.json が無い
    (json.dumps({'url': 'file:///x', 'dir_info': {'editable': True}}), 'source'),
    (json.dumps({'url': 'file:///x', 'dir_info': {}}), 'pip'),
])
def test_not_frozen_is_pip_or_source(monkeypatch, direct_url, expected):
    import importlib.metadata
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: _FakeDistribution(direct_url))
    assert updater.install_kind() == expected


def test_not_installed_at_all_is_source(monkeypatch):
    import importlib.metadata

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(importlib.metadata, "distribution", missing)
    assert updater.install_kind() == 'source'


# --- ダウンロード ---

PAYLOAD = b"installer bytes " * 10000


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.exe"
    path.write_bytes(PAYLOAD)
    return path.as_uri()


def test_download_checks_size_and_sha256(tmp_path, source):
    dest = tmp_path / "Graphica-setup.exe"
    progress = []
    result = updater.download_file(source, str(dest), len(PAYLOAD), hashlib.sha256(PAYLOAD).hexdigest().upper(),
                                   report_progress=lambda done, total: progress.append((done, total)))
    assert result == str(dest)
    assert dest.read_bytes() == PAYLOAD
    assert progress[-1][0] == len(PAYLOAD) // 1024
    assert not pathlib.Path(str(dest) + ".part").exists()


def test_a_wrong_sha256_is_rejected_and_nothing_is_left(tmp_path, source):
    dest = tmp_path / "Graphica-setup.exe"
    with pytest.raises(ValueError, match="SHA-256"):
        updater.download_file(source, str(dest), len(PAYLOAD), "0" * 64)
    assert list(tmp_path.glob("Graphica-setup.exe*")) == []


def test_a_wrong_size_is_rejected(tmp_path, source):
    dest = tmp_path / "Graphica-setup.exe"
    with pytest.raises(ValueError, match="大きさ"):
        updater.download_file(source, str(dest), len(PAYLOAD) + 1)
    assert not dest.exists()


def test_cancelling_returns_none_and_removes_the_partial_file(tmp_path, source):
    dest = tmp_path / "Graphica-setup.exe"
    assert updater.download_file(source, str(dest), is_cancelled=lambda: True) is None
    assert list(tmp_path.glob("Graphica-setup.exe*")) == []


def test_without_a_published_digest_only_the_size_is_checked(tmp_path, source):
    dest = tmp_path / "Graphica-setup.exe"
    assert updater.download_file(source, str(dest), len(PAYLOAD), "") == str(dest)


# --- 起動 ---

def test_launch_passes_the_update_arguments_and_a_log(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: started.append((args, kwargs)))
    installer = str(tmp_path / "Graphica-9.9.9-setup.exe")

    updater.launch_installer(installer)

    (args, kwargs), = started
    assert args[0] == installer
    assert '/RELAUNCH=1' in args and '/SILENT' in args and '/CLOSEAPPLICATIONS' in args
    assert args[-1] == f"/LOG={tmp_path / 'Graphica-update.log'}"
    assert kwargs['close_fds'] is True
