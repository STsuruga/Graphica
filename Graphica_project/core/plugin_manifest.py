# core/plugin_manifest.py
"""
プラグインマニフェスト(plugin.json)の読み込み・検証(項目F-1)。

各プラグインディレクトリ直下に plugin.json を必須とする(従来 __init__.py に
埋め込んでいた PLUGIN_INFO 辞書はこれに置き換わった)。api_version は
このロードマップ(トラック1 フェーズA〜G)で実装したプラグインAPIの
バージョンを表し、フェーズGの完了時点で "1.0" として固定する。将来
破壊的変更を行う場合はここを "2.0" のように上げ、不一致のプラグインは
ロード前に(register()を一切呼ばずに)弾く。

entry_point キー(plugin.json のサンプルに含まれる
"graphica_plugin_jcamp:register" のような形式)は将来の拡張用に予約された
フィールドであり、現時点では未使用(実装が読むのは常に "モジュール直下の
__init__.py の register(api) 関数"という既存の固定規約のまま)。
"""
import json
import os

PLUGIN_API_VERSION = "1.0"
PLUGIN_MANIFEST_FILENAME = "plugin.json"

# entry_point は将来の拡張用予約フィールド(現状未使用)のため必須にしない。
_REQUIRED_MANIFEST_KEYS = ("name", "version", "api_version")


class PluginManifestError(Exception):
    """plugin.jsonの欠落・不正・api_version不一致を表す(呼び出し元でキャッチしてそのプラグインをスキップする用途)。"""


def load_plugin_manifest(plugin_dir):
    """
    plugin_dir/plugin.json を読み込み、辞書として返す。

    欠落・JSONとして不正・オブジェクトでない・必須キー(name/version/
    api_version)欠落・api_version不一致のいずれかの場合は
    PluginManifestError を送出する。
    """
    manifest_path = os.path.join(plugin_dir, PLUGIN_MANIFEST_FILENAME)
    if not os.path.exists(manifest_path):
        raise PluginManifestError(
            f"{PLUGIN_MANIFEST_FILENAME} が見つかりません(プラグインディレクトリ直下に必須です)。"
        )

    try:
        with open(manifest_path, encoding='utf-8') as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise PluginManifestError(f"{PLUGIN_MANIFEST_FILENAME} の読み込みに失敗しました: {e}") from e

    if not isinstance(manifest, dict):
        raise PluginManifestError(f"{PLUGIN_MANIFEST_FILENAME} はJSONオブジェクトである必要があります。")

    missing_keys = [k for k in _REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing_keys:
        raise PluginManifestError(
            f"{PLUGIN_MANIFEST_FILENAME} に必須キーがありません: {', '.join(missing_keys)}"
        )

    if manifest["api_version"] != PLUGIN_API_VERSION:
        raise PluginManifestError(
            f"api_version '{manifest['api_version']}' はサポート対象外です"
            f"(このGraphicaが対応するプラグインAPIのバージョンは '{PLUGIN_API_VERSION}' です)。"
        )

    return manifest
