# core/diagnostics.py
"""
バグ報告時に添付できる診断情報バンドル(zip)を作る (C-1201)。

core/ の他モジュール同様GUI(PySide6)には依存しない: QSettingsの内容は
呼び出し側(gui/mixins/help_mixin.py)が {key: value} のプレーンなdictに
変換してから渡す。
"""
import logging
import os
import platform
import sys
import zipfile
from datetime import datetime

from core.app_paths import get_app_data_dir
from core.version import APP_NAME, LOG_FILE_NAME, __version__

logger = logging.getLogger(__name__)

# バージョン情報を収集する対象の依存パッケージ
_DEPENDENCY_MODULES = ('PySide6', 'matplotlib', 'numpy', 'pandas', 'scipy', 'openpyxl')


def _collect_environment_info():
    lines = [
        f"{APP_NAME} {__version__}",
        f"生成日時: {datetime.now().astimezone().isoformat()}",
        f"OS: {platform.platform()}",
        f"Python: {sys.version}",
        "",
        "--- 依存パッケージ ---",
    ]
    for module_name in _DEPENDENCY_MODULES:
        try:
            module = __import__(module_name)
            version = getattr(module, '__version__', '(バージョン不明)')
        except Exception:
            version = "未インストール、または読み込み失敗"
        lines.append(f"{module_name}: {version}")
    return "\n".join(lines)


def _collect_plugin_info():
    from core.plugin_api import get_loaded_plugin_records, get_plugin_registration_errors
    records = get_loaded_plugin_records()
    if records is None:
        return "プラグインは未読み込みです。"
    if not records:
        return "読み込まれたプラグインはありません。"
    lines = []
    for record in records:
        name = record.get("name", "(不明)")
        info = record.get("info") or {}
        version = info.get("version", "?")
        error = record.get("error")
        status = "OK" if error is None else f"読み込み失敗: {error}"
        lines.append(f"- {name} (v{version}): {status}")

    # プラグイン全体としては読み込みに成功していても、個別のregister_xxx呼び出しが
    # 失敗している場合はrecordのerrorには現れないため、別途一覧化する(フェーズA-2)。
    registration_errors = get_plugin_registration_errors()
    if registration_errors:
        lines.append("")
        lines.append("--- フック単位の登録失敗 ---")
        for err in registration_errors:
            lines.append(f"- [{err.plugin_name}] {err.hook_kind.value}: {err.message}")

    return "\n".join(lines)


def _collect_settings_info(settings_dict):
    if not settings_dict:
        return "(設定値なし)"
    lines = [f"{key} = {value!r}" for key, value in sorted(settings_dict.items())]
    return "\n".join(lines)


def build_diagnostic_bundle(out_path, settings_dict=None):
    """
    診断情報バンドル(zip)を out_path に書き出す。

    含まれる内容:
      - environment.txt: アプリ/OS/Pythonバージョン、主要依存パッケージのバージョン
      - plugins.txt: 読み込み済みプラグインの一覧と成否
      - settings.txt: QSettingsの内容(呼び出し側がdictとして渡した場合のみ)
      - graphica.log (存在すれば): アプリのログファイル

    Args:
        out_path (str): 出力先のzipファイルパス。
        settings_dict (dict | None): QSettingsの内容を {key: value} の
            プレーンなdictに変換したもの。Noneならsettings.txtは省略する。
    """
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("environment.txt", _collect_environment_info())
        zf.writestr("plugins.txt", _collect_plugin_info())
        if settings_dict is not None:
            zf.writestr("settings.txt", _collect_settings_info(settings_dict))

        log_path = os.path.join(get_app_data_dir(), LOG_FILE_NAME)
        if os.path.exists(log_path):
            zf.write(log_path, arcname=LOG_FILE_NAME)
        else:
            zf.writestr("log_not_found.txt", f"ログファイルが見つかりませんでした: {log_path}")
