# tests/test_plugin_manifest.py
"""
core/plugin_manifest.py に対するテスト(改善ボード B-4)。

このモジュールには専用テストが無く、`test_plugin_manager.py` 等から間接的に
通っているだけだった(`load_plugin_manifest` を直接呼ぶテストは1件も無かった)。

マニフェストの検証はプラグインの**入口**にあたる。ここが緩むと不正な
plugin.json を持つプラグインが読み込まれてしまい、逆に厳しすぎると正当な
プラグインが「エラーも出ないまま読み込まれない」(`PluginManager.load_all` は
例外を握りつぶしてログに出すだけ)という、気づきにくい壊れ方をする。
分岐が6本しかない小さなモジュールなので、全分岐を固める。
"""
import json
import os

import pytest

from core.plugin_manifest import (
    PLUGIN_API_VERSION, PLUGIN_MANIFEST_FILENAME,
    PluginManifestError, load_plugin_manifest,
)


def _write_manifest(plugin_dir, content, raw=None):
    """plugin.json を書き出す。raw を渡すとその文字列をそのまま書く。"""
    os.makedirs(plugin_dir, exist_ok=True)
    path = os.path.join(plugin_dir, PLUGIN_MANIFEST_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        if raw is not None:
            f.write(raw)
        else:
            json.dump(content, f)
    return path


def _valid_manifest(**overrides):
    manifest = {
        "name": "demo",
        "version": "1.0",
        "api_version": PLUGIN_API_VERSION,
    }
    manifest.update(overrides)
    return manifest


# --- 正常系 ---

def test_loads_a_valid_manifest(tmp_path):
    plugin_dir = str(tmp_path / "demo")
    _write_manifest(plugin_dir, _valid_manifest())

    manifest = load_plugin_manifest(plugin_dir)

    assert manifest["name"] == "demo"
    assert manifest["version"] == "1.0"
    assert manifest["api_version"] == PLUGIN_API_VERSION


def test_optional_keys_are_returned_as_is(tmp_path):
    """author / description のような任意キーはそのまま素通しすること。"""
    plugin_dir = str(tmp_path / "demo")
    _write_manifest(plugin_dir, _valid_manifest(
        author="STsuruga", description="説明文"))

    manifest = load_plugin_manifest(plugin_dir)

    assert manifest["author"] == "STsuruga"
    assert manifest["description"] == "説明文"


def test_entry_point_is_accepted_but_not_required(tmp_path):
    """entry_point は将来の拡張用の予約フィールドで、現状ローダーは
    常に __init__.py の register(api) を呼ぶ。必須にしないこと。"""
    without = str(tmp_path / "without")
    _write_manifest(without, _valid_manifest())
    assert "entry_point" not in load_plugin_manifest(without)

    with_ep = str(tmp_path / "with")
    _write_manifest(with_ep, _valid_manifest(entry_point="demo:register"))
    assert load_plugin_manifest(with_ep)["entry_point"] == "demo:register"


# --- 異常系 ---

def test_missing_manifest_file_raises(tmp_path):
    plugin_dir = str(tmp_path / "no_manifest")
    os.makedirs(plugin_dir)

    with pytest.raises(PluginManifestError, match=PLUGIN_MANIFEST_FILENAME):
        load_plugin_manifest(plugin_dir)


def test_missing_plugin_directory_raises(tmp_path):
    with pytest.raises(PluginManifestError):
        load_plugin_manifest(str(tmp_path / "does_not_exist"))


def test_malformed_json_raises(tmp_path):
    plugin_dir = str(tmp_path / "broken")
    _write_manifest(plugin_dir, None, raw="{ this is not json")

    with pytest.raises(PluginManifestError, match="読み込みに失敗"):
        load_plugin_manifest(plugin_dir)


@pytest.mark.parametrize("raw", ["[]", '"just a string"', "42", "null"])
def test_non_object_json_raises(tmp_path, raw):
    """トップレベルがオブジェクトでないJSON(配列・文字列・数値・null)を弾くこと。"""
    plugin_dir = str(tmp_path / "not_object")
    _write_manifest(plugin_dir, None, raw=raw)

    with pytest.raises(PluginManifestError, match="JSONオブジェクト"):
        load_plugin_manifest(plugin_dir)


@pytest.mark.parametrize("missing_key", ["name", "version", "api_version"])
def test_missing_required_key_raises_and_names_it(tmp_path, missing_key):
    plugin_dir = str(tmp_path / "incomplete")
    manifest = _valid_manifest()
    del manifest[missing_key]
    _write_manifest(plugin_dir, manifest)

    with pytest.raises(PluginManifestError, match=missing_key):
        load_plugin_manifest(plugin_dir)


def test_all_missing_required_keys_are_listed_at_once(tmp_path):
    """1つ直すたびにエラーが出るより、まとめて分かる方が親切。"""
    plugin_dir = str(tmp_path / "empty_object")
    _write_manifest(plugin_dir, {})

    with pytest.raises(PluginManifestError) as excinfo:
        load_plugin_manifest(plugin_dir)

    message = str(excinfo.value)
    assert "name" in message and "version" in message and "api_version" in message


@pytest.mark.parametrize("bad_version", ["0.9", "1.0", "2", "2.0.0", ""])
def test_api_version_mismatch_raises(tmp_path, bad_version):
    """★ api_version が一致しないと、そのプラグインのコードは一切 import
    されない。PLUGIN_API_VERSION を上げる=既存の全プラグインが読み込まれなく
    なる、という重い変更であることを、この厳密比較が示している。"""
    plugin_dir = str(tmp_path / "wrong_api")
    _write_manifest(plugin_dir, _valid_manifest(api_version=bad_version))

    with pytest.raises(PluginManifestError, match="api_version"):
        load_plugin_manifest(plugin_dir)


def test_api_version_error_message_names_the_supported_version(tmp_path):
    """プラグイン作者が「何に合わせればよいか」分かるメッセージであること。"""
    plugin_dir = str(tmp_path / "wrong_api")
    _write_manifest(plugin_dir, _valid_manifest(api_version="99.0"))

    with pytest.raises(PluginManifestError) as excinfo:
        load_plugin_manifest(plugin_dir)

    message = str(excinfo.value)
    assert "99.0" in message
    assert PLUGIN_API_VERSION in message


# --- 同梱サンプルとの整合 ---

def test_the_bundled_example_plugin_manifest_is_valid():
    """★ 同梱サンプルが現行のバリデーションを通ること。PLUGIN_API_VERSION を
    上げたときに、サンプルの plugin.json の更新漏れをここで検出する。"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    plugin_dir = os.path.join(project_root, "plugins", "example_plugin")

    manifest = load_plugin_manifest(plugin_dir)

    assert manifest["api_version"] == PLUGIN_API_VERSION
