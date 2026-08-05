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
