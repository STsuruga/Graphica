# tests/test_plugin_install.py
"""core/plugin_install.py (プラグインのzipインストール、項目E-2/E-4) に対するテスト。"""
import os
import zipfile

import pytest

import core.plugin_install as plugin_install_module
from core.plugin_install import install_plugin_zip, PluginInstallError


def _make_wrapped_zip(tmp_path, zip_name, folder_name, extra_content="x = 1"):
    """<folder_name>/__init__.py を含むzip(一般的な形)を作る"""
    zip_path = tmp_path / zip_name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(f"{folder_name}/__init__.py", extra_content)
    return str(zip_path)


def _make_flat_zip(tmp_path, zip_name, extra_content="x = 1"):
    """__init__.py がzipルート直下にある(フォルダに包まれていない)zipを作る"""
    zip_path = tmp_path / zip_name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("__init__.py", extra_content)
    return str(zip_path)


# --- 正常系: 2つのzipレイアウト ---

def test_install_wrapped_folder_zip(tmp_path):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    zip_path = _make_wrapped_zip(tmp_path, "my_plugin.zip", "my_plugin")

    name = install_plugin_zip(zip_path, target_dir=str(target_dir))

    assert name == "my_plugin"
    assert os.path.isfile(os.path.join(str(target_dir), "my_plugin", "__init__.py"))


def test_install_flat_root_zip_uses_zip_stem(tmp_path):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    zip_path = _make_flat_zip(tmp_path, "flat_plugin.zip")

    name = install_plugin_zip(zip_path, target_dir=str(target_dir))

    assert name == "flat_plugin"
    assert os.path.isfile(os.path.join(str(target_dir), "flat_plugin", "__init__.py"))


# --- 再インストール(項目E-4: アトミック置き換え) ---

def test_reinstall_overwrites_and_leaves_no_leftovers(tmp_path):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    zip_path = _make_wrapped_zip(tmp_path, "my_plugin.zip", "my_plugin", extra_content="x = 1")

    install_plugin_zip(zip_path, target_dir=str(target_dir))

    zip_path_v2 = _make_wrapped_zip(tmp_path, "my_plugin_v2.zip", "my_plugin", extra_content="x = 2")
    name = install_plugin_zip(zip_path_v2, target_dir=str(target_dir))

    assert name == "my_plugin"
    init_path = os.path.join(str(target_dir), "my_plugin", "__init__.py")
    with open(init_path, encoding="utf-8") as f:
        assert f.read() == "x = 2"

    assert os.listdir(str(target_dir)) == ["my_plugin"]


# --- 異常系 ---

def test_not_a_zip_file_raises(tmp_path):
    not_a_zip = tmp_path / "not_a_zip.txt"
    not_a_zip.write_text("hello", encoding="utf-8")

    with pytest.raises(PluginInstallError):
        install_plugin_zip(str(not_a_zip), target_dir=str(tmp_path))


def test_zip_without_init_py_raises(tmp_path):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    zip_path = tmp_path / "no_init.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("some_folder/readme.txt", "not a plugin")

    with pytest.raises(PluginInstallError):
        install_plugin_zip(str(zip_path), target_dir=str(target_dir))


def test_zip_slip_relative_traversal_raises_and_writes_nothing_outside(tmp_path):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("my_plugin/__init__.py", "x = 1")
        zf.writestr("../../evil.py", "pwned = True")

    with pytest.raises(PluginInstallError):
        install_plugin_zip(str(zip_path), target_dir=str(target_dir))

    assert not os.path.exists(tmp_path / "evil.py")
    assert os.listdir(str(target_dir)) == []


def test_zip_slip_absolute_path_raises_and_writes_nothing_outside(tmp_path):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    zip_path = tmp_path / "evil_abs.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("my_plugin/__init__.py", "x = 1")
        # ZipInfoを使い、ドライブ付き絶対パスのメンバー名を明示的に書き込む
        # (os.path.isabs()がプラットフォームを問わず確実に絶対パスと判定する形)
        zf.writestr(zipfile.ZipInfo("C:/evil_abs.py"), "pwned = True")

    with pytest.raises(PluginInstallError):
        install_plugin_zip(str(zip_path), target_dir=str(target_dir))

    assert os.listdir(str(target_dir)) == []


# --- target_dir省略時のデフォルト解決 ---

def test_target_dir_none_resolves_via_get_user_plugins_dir(tmp_path, monkeypatch):
    user_plugins_dir = tmp_path / "user_plugins"
    user_plugins_dir.mkdir()
    monkeypatch.setattr(plugin_install_module, "get_user_plugins_dir", lambda: str(user_plugins_dir))

    zip_path = _make_wrapped_zip(tmp_path, "my_plugin.zip", "my_plugin")

    name = install_plugin_zip(zip_path)

    assert name == "my_plugin"
    assert os.path.isfile(os.path.join(str(user_plugins_dir), "my_plugin", "__init__.py"))
