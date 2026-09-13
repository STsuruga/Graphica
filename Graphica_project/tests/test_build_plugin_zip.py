# tests/test_build_plugin_zip.py
"""
scripts/build_plugin_zip.py(改善ボード D-4)のテスト。

リポジトリの plugins/ は plugin_search_paths() の `if not is_frozen()` 分岐に
より**ソース実行時にしか読まれない**ため、PyInstallerで固めたexeの利用者へ
プラグインを届けるには、環境設定の「プラグインをインストール...」が受け取れる
zipに固めて配る必要がある。このスクリプトがその配布物を作る。

最も重要なのは「作ったzipが実際に install_plugin_zip() でインストールできる」
ことなので、往復(ビルド→インストール)を通して確かめる。
"""
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import build_plugin_zip  # noqa: E402

from core.plugin_install import install_plugin_zip  # noqa: E402


def _make_plugin(root, name, version="1.0", extra_files=None):
    plugin_dir = os.path.join(root, name)
    os.makedirs(plugin_dir, exist_ok=True)
    with open(os.path.join(plugin_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("def register(api):\n    pass\n")
    with open(os.path.join(plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
        json.dump({"name": name, "version": version, "api_version": "1.0"}, f)
    for rel_path, content in (extra_files or {}).items():
        path = os.path.join(plugin_dir, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return plugin_dir


@pytest.fixture
def plugins_root(tmp_path, monkeypatch):
    """PLUGINS_DIR を一時ディレクトリへ差し替える。"""
    root = tmp_path / "plugins"
    root.mkdir()
    monkeypatch.setattr(build_plugin_zip, "PLUGINS_DIR", str(root))
    return str(root)


# --- ビルド ---

def test_builds_a_zip_named_after_the_plugin_and_version(plugins_root, tmp_path):
    _make_plugin(plugins_root, "demo", version="2.3")

    zip_path = build_plugin_zip.build_plugin_zip("demo", out_dir=str(tmp_path / "out"))

    assert os.path.basename(zip_path) == "demo-2.3.zip"
    assert os.path.exists(zip_path)


def test_zip_uses_the_single_top_level_folder_layout(plugins_root, tmp_path):
    """core/plugin_install.py の _find_plugin_root() が受け付ける
    「レイアウト(a)」。展開後のフォルダ名がそのままプラグイン名になる。"""
    _make_plugin(plugins_root, "demo")

    zip_path = build_plugin_zip.build_plugin_zip("demo", out_dir=str(tmp_path / "out"))

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "demo/__init__.py" in names
    assert "demo/plugin.json" in names
    assert all(n.startswith("demo/") for n in names)


def test_nested_files_are_included(plugins_root, tmp_path):
    _make_plugin(plugins_root, "demo", extra_files={"sub/helper.py": "x = 1\n"})

    zip_path = build_plugin_zip.build_plugin_zip("demo", out_dir=str(tmp_path / "out"))

    with zipfile.ZipFile(zip_path) as zf:
        assert "demo/sub/helper.py" in zf.namelist()


def test_pycache_and_compiled_files_are_excluded(plugins_root, tmp_path):
    _make_plugin(plugins_root, "demo", extra_files={
        "__pycache__/stale.cpython-313.pyc": "junk",
        "leftover.pyc": "junk",
    })

    zip_path = build_plugin_zip.build_plugin_zip("demo", out_dir=str(tmp_path / "out"))

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert not any("__pycache__" in n for n in names)
    assert not any(n.endswith(".pyc") for n in names)


def test_missing_plugin_folder_raises(plugins_root, tmp_path):
    with pytest.raises(FileNotFoundError, match="プラグインフォルダがありません"):
        build_plugin_zip.build_plugin_zip("nope", out_dir=str(tmp_path / "out"))


def test_plugin_without_a_manifest_raises(plugins_root, tmp_path):
    plugin_dir = os.path.join(plugins_root, "broken")
    os.makedirs(plugin_dir)
    with open(os.path.join(plugin_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")

    with pytest.raises(FileNotFoundError, match="plugin.json"):
        build_plugin_zip.build_plugin_zip("broken", out_dir=str(tmp_path / "out"))


def test_plugin_without_init_raises(plugins_root, tmp_path):
    plugin_dir = os.path.join(plugins_root, "broken")
    os.makedirs(plugin_dir)
    with open(os.path.join(plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "broken", "version": "1.0", "api_version": "1.0"}, f)

    with pytest.raises(FileNotFoundError, match="__init__.py"):
        build_plugin_zip.build_plugin_zip("broken", out_dir=str(tmp_path / "out"))


# --- 探索 ---

def test_discovers_only_complete_plugins(plugins_root):
    _make_plugin(plugins_root, "good_a")
    _make_plugin(plugins_root, "good_b")
    os.makedirs(os.path.join(plugins_root, "incomplete"))  # 必須ファイルなし

    assert build_plugin_zip.discover_plugin_names() == ["good_a", "good_b"]


# --- 往復: ビルドしたzipが実際にインストールできること ---

def test_built_zip_installs_through_the_real_installer(plugins_root, tmp_path):
    """★ これが通らなければ配布物として意味がない。"""
    _make_plugin(plugins_root, "demo", extra_files={"sub/helper.py": "x = 1\n"})
    zip_path = build_plugin_zip.build_plugin_zip("demo", out_dir=str(tmp_path / "out"))

    install_target = tmp_path / "installed"
    install_target.mkdir()
    installed_name = install_plugin_zip(zip_path, target_dir=str(install_target))

    assert installed_name == "demo"
    installed_dir = install_target / "demo"
    assert (installed_dir / "__init__.py").exists()
    assert (installed_dir / "plugin.json").exists()
    assert (installed_dir / "sub" / "helper.py").exists()


def test_the_bundled_example_plugin_can_be_packaged(tmp_path):
    """同梱サンプルがそのままzip化・インストールできること。
    PLUGINS_DIR は差し替えず、リポジトリの plugins/ をそのまま使う。

    プラグイン本体は種類ごとに別リポジトリで開発する方針(2026-09-13)のため、
    本体リポジトリの plugins/ に残るのは example_plugin だけ。各プラグイン
    リポジトリは自前の scripts/build_zip.py を持つ。"""
    zip_path = build_plugin_zip.build_plugin_zip(
        "example_plugin", out_dir=str(tmp_path / "out")
    )

    install_target = tmp_path / "installed"
    install_target.mkdir()
    installed_name = install_plugin_zip(zip_path, target_dir=str(install_target))

    assert installed_name == "example_plugin"
    assert (install_target / "example_plugin" / "__init__.py").exists()
    assert (install_target / "example_plugin" / "plugin.json").exists()


# --- CLI ---

def test_cli_all_builds_every_plugin(plugins_root, tmp_path, capsys):
    _make_plugin(plugins_root, "one")
    _make_plugin(plugins_root, "two")
    out_dir = str(tmp_path / "out")

    exit_code = build_plugin_zip.main(["--all", "--out-dir", out_dir])

    assert exit_code == 0
    assert sorted(os.listdir(out_dir)) == ["one-1.0.zip", "two-1.0.zip"]


def test_cli_builds_a_named_plugin_only(plugins_root, tmp_path):
    _make_plugin(plugins_root, "one")
    _make_plugin(plugins_root, "two")
    out_dir = str(tmp_path / "out")

    exit_code = build_plugin_zip.main(["one", "--out-dir", out_dir])

    assert exit_code == 0
    assert os.listdir(out_dir) == ["one-1.0.zip"]


def test_cli_without_arguments_exits_with_usage(plugins_root):
    with pytest.raises(SystemExit):
        build_plugin_zip.main([])
