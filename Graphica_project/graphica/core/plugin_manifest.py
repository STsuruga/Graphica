"""
プラグインのマニフェスト(plugin.json)の読み込みと検証。

プラグイン API の版は "主番号.小番号"。壊す変更で主番号を、互換のある追加で小番号を上げる。
plugin.json の api_version は、主番号が本体と同じで小番号が本体以下なら読み込む
(使う機能がそろっている)。合わないプラグインは import する前に弾く。
entry_point キーは予約済みで未使用(常にパッケージの __init__.py の register(api) を呼ぶ)。
"""
import json
import os

PLUGIN_API_VERSION = "2.0"
PLUGIN_MANIFEST_FILENAME = "plugin.json"

_REQUIRED_MANIFEST_KEYS = ("name", "version", "api_version")


class PluginManifestError(Exception):
    """plugin.json が無い・壊れている・api_version が合わない(呼び出し側はそのプラグインを飛ばす)。"""


def load_plugin_manifest(plugin_dir):
    """plugin_dir/plugin.json を辞書で返す。不正なら PluginManifestError。"""
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

    if not is_compatible_api_version(manifest["api_version"]):
        raise PluginManifestError(
            f"api_version '{manifest['api_version']}' はサポート対象外です"
            f"(このGraphicaのプラグインAPIは '{PLUGIN_API_VERSION}'。主番号が同じで、"
            f"小番号がこれ以下のプラグインを読み込めます)。"
        )

    return manifest


def parse_api_version(text):
    """ "2.1" -> (2, 1)。形が違えば None。"""
    parts = str(text).split(".")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1])


def is_compatible_api_version(plugin_api_version, app_api_version=PLUGIN_API_VERSION):
    plugin = parse_api_version(plugin_api_version)
    app = parse_api_version(app_api_version)
    return plugin is not None and plugin[0] == app[0] and plugin[1] <= app[1]
