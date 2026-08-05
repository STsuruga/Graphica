# tests/test_diagnostics.py
"""core/diagnostics.py (診断情報バンドル出力、C-1201) のテスト。"""
import os
import zipfile

from core.diagnostics import build_diagnostic_bundle
from core.version import LOG_FILE_NAME, __version__


def test_build_diagnostic_bundle_creates_zip_with_expected_entries(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / "appdata"))
    out_path = tmp_path / "diag.zip"

    build_diagnostic_bundle(str(out_path))

    assert out_path.exists()
    with zipfile.ZipFile(str(out_path)) as zf:
        names = zf.namelist()
        assert "environment.txt" in names
        assert "plugins.txt" in names
        # LOCALAPPDATAを隔離したので、この場所にログファイルは存在しないはず
        assert "log_not_found.txt" in names
        assert "graphica.log" not in names


def test_build_diagnostic_bundle_environment_txt_contains_version_and_python(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / "appdata"))
    out_path = tmp_path / "diag.zip"
    build_diagnostic_bundle(str(out_path))

    with zipfile.ZipFile(str(out_path)) as zf:
        env_text = zf.read("environment.txt").decode('utf-8')
    assert __version__ in env_text
    assert "Python" in env_text
    assert "matplotlib" in env_text


def test_build_diagnostic_bundle_includes_log_file_when_present(tmp_path, monkeypatch):
    fake_appdata = tmp_path / "appdata"
    monkeypatch.setenv('LOCALAPPDATA', str(fake_appdata))
    app_dir = fake_appdata / "Graphica"
    app_dir.mkdir(parents=True)
    (app_dir / LOG_FILE_NAME).write_text("dummy log line\n", encoding='utf-8')

    out_path = tmp_path / "diag.zip"
    build_diagnostic_bundle(str(out_path))

    with zipfile.ZipFile(str(out_path)) as zf:
        assert LOG_FILE_NAME in zf.namelist()
        assert zf.read(LOG_FILE_NAME).decode('utf-8').strip() == "dummy log line"


def test_build_diagnostic_bundle_omits_settings_txt_when_none_given(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / "appdata"))
    out_path = tmp_path / "diag.zip"
    build_diagnostic_bundle(str(out_path), settings_dict=None)

    with zipfile.ZipFile(str(out_path)) as zf:
        assert "settings.txt" not in zf.namelist()


def test_build_diagnostic_bundle_includes_settings_txt_when_given(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / "appdata"))
    out_path = tmp_path / "diag.zip"
    build_diagnostic_bundle(str(out_path), settings_dict={"dark_mode": True, "autosave_interval": 5})

    with zipfile.ZipFile(str(out_path)) as zf:
        settings_text = zf.read("settings.txt").decode('utf-8')
    assert "dark_mode" in settings_text
    assert "autosave_interval" in settings_text


def test_build_diagnostic_bundle_plugins_txt_handles_unloaded_registry(tmp_path, monkeypatch):
    """load_plugins_once()が一度も呼ばれていない(get_loaded_plugin_records()がNoneを返す)
    状態でもクラッシュしないこと。"""
    import core.plugin_api as plugin_api_module
    monkeypatch.setattr(plugin_api_module, "_singleton_manager", None)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / "appdata"))
    out_path = tmp_path / "diag.zip"

    build_diagnostic_bundle(str(out_path))

    with zipfile.ZipFile(str(out_path)) as zf:
        plugins_text = zf.read("plugins.txt").decode('utf-8')
    assert "未読み込み" in plugins_text


def test_build_diagnostic_bundle_plugins_txt_includes_hook_level_registration_errors(tmp_path, monkeypatch):
    """フック単位の登録失敗(フェーズA-2、プラグイン全体としては成功扱いなので
    通常のプラグイン一覧には現れない)も、診断バンドルには含まれること。"""
    import core.plugin_api as plugin_api_module
    monkeypatch.setattr(plugin_api_module, "_singleton_api", None)
    monkeypatch.setattr(plugin_api_module, "_singleton_manager", None)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / "appdata"))

    plugin_dir = tmp_path / "plugins" / "partial_failure_plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text('''
PLUGIN_INFO = {"name": "Partial Failure", "version": "1.0", "author": "test", "description": "d"}

def register(api):
    api.register_fit_function("線形", lambda x, a: a * x, ["a"])  # 組み込み名と衝突して失敗
    api.register_menu_action("OK", lambda main_window: None)
''', encoding='utf-8')

    plugin_api_module.load_plugins_once(str(tmp_path / "plugins"))

    out_path = tmp_path / "diag.zip"
    build_diagnostic_bundle(str(out_path))

    with zipfile.ZipFile(str(out_path)) as zf:
        plugins_text = zf.read("plugins.txt").decode('utf-8')
    assert "partial_failure_plugin" in plugins_text
    assert "fit_function" in plugins_text
