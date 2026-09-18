# core/plugin_manifest.py
"""
プラグインのマニフェスト(plugin.json)の読み込みと検証。

api_version が PLUGIN_API_VERSION と一致しないプラグインは、import する前に弾く。
壊す変更をしたら PLUGIN_API_VERSION を上げる。entry_point キーは予約済みで未使用
(常にパッケージの __init__.py の register(api) を呼ぶ)。
"""
import json
import os

PLUGIN_API_VERSION = "2.0"
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
