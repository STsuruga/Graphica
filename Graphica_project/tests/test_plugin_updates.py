"""プラグインの更新(core/plugin_updates.py と gui/plugin_update_flow.py)。通信はすべて差し替える。"""
import json
import os
import zipfile

import pytest
from PySide6.QtWidgets import QApplication

import graphica.gui.plugin_update_flow as flow
from graphica.core.plugin_manifest import PLUGIN_API_VERSION, PluginManifestError
from graphica.core.plugin_updates import (
    check_plugin_updates, check_update_zip, find_plugin_updates, installed_user_plugins, parse_plugin_index,
    zip_manifest,
)
from graphica.gui import app_settings

INDEX = [
    {"folder": "mass_spec", "name": "Mass Spec Pack", "repo": "STsuruga/graphica-plugin-mass-spec"},
    {"folder": "color_studio", "name": "Color Studio", "repo": "STsuruga/graphica-plugin-color-studio"},
]


def _write_plugin(plugins_dir, folder, version, api_version=PLUGIN_API_VERSION, name=None):
    path = os.path.join(plugins_dir, folder)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "plugin.json"), "w", encoding="utf-8") as f:
        json.dump({"name": name or folder, "version": version, "api_version": api_version}, f)
    with open(os.path.join(path, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("def register(api):\n    pass\n")
    return path


def _make_zip(zip_path, folder, version, api_version=PLUGIN_API_VERSION, name=None):
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(f"{folder}/plugin.json",
                    json.dumps({"name": name or folder, "version": version, "api_version": api_version}))
        zf.writestr(f"{folder}/__init__.py", "def register(api):\n    pass\n")
    return zip_path


def _release(version, with_zip=True):
    return {"version": version, "html_url": "https://example.invalid/release", "body": "notes",
            "zip": {"name": "p.zip", "url": "https://example.invalid/p.zip", "size": 0, "sha256": ""}
            if with_zip else None}


# --- 一覧と比べ方 ---

def test_the_index_keeps_only_complete_entries():
    data = {"plugins": [
        {"folder": "a", "name": "A", "repo": "o/a"},
        {"folder": "b", "repo": "not-a-repo"},
        {"name": "C", "repo": "o/c"},
        "garbage",
    ]}
    assert parse_plugin_index(data) == [{"folder": "a", "name": "A", "repo": "o/a"}]
    assert parse_plugin_index(None) == []


def test_installed_plugins_include_ones_with_an_old_api(tmp_path):
    _write_plugin(tmp_path, "mass_spec", "0.2.0", name="Mass Spec Pack")
    _write_plugin(tmp_path, "old", "1.0", api_version="1.0")
    os.makedirs(tmp_path / "no_manifest")
    os.makedirs(tmp_path / ".tmp_install_x")
    assert installed_user_plugins(str(tmp_path)) == [
        {"folder": "mass_spec", "name": "Mass Spec Pack", "version": "0.2.0"},
        {"folder": "old", "name": "old", "version": "1.0"},
    ]


def test_only_newer_releases_with_a_zip_are_offered():
    installed = [
        {"folder": "mass_spec", "name": "Mass Spec Pack", "version": "0.2.0"},
        {"folder": "renamed_folder", "name": "Color Studio", "version": "1.0.0"},
        {"folder": "unknown", "name": "Unknown", "version": "1.0.0"},
    ]
    releases = {"STsuruga/graphica-plugin-mass-spec": _release("1.0.0"),
                "STsuruga/graphica-plugin-color-studio": _release("1.0.0")}
    updates = find_plugin_updates(installed, INDEX, releases.__getitem__)
    assert [(u["folder"], u["current"], u["latest"]) for u in updates] == [("mass_spec", "0.2.0", "1.0.0")]


def test_a_release_without_a_zip_or_a_failing_repository_is_skipped():
    installed = [{"folder": "mass_spec", "name": "Mass Spec Pack", "version": "0.2.0"},
                 {"folder": "color_studio", "name": "Color Studio", "version": "0.1.0"}]

    def fetch(repo):
        if repo.endswith("mass-spec"):
            raise OSError("404")
        return _release("1.0.0", with_zip=False)

    assert find_plugin_updates(installed, INDEX, fetch) == []


def test_no_installed_plugins_means_no_network(tmp_path, monkeypatch):
    import graphica.core.plugin_updates as module
    monkeypatch.setattr(module, "fetch_plugin_index", lambda timeout: pytest.fail("通信した"))
    assert check_plugin_updates(str(tmp_path)) == []


# --- 落とした zip の確認 ---

def test_the_zip_must_hold_the_same_plugin_with_a_usable_api(tmp_path):
    ok = _make_zip(str(tmp_path / "ok.zip"), "mass_spec", "1.0.0")
    assert check_update_zip(ok, "mass_spec")["version"] == "1.0.0"
    with pytest.raises(PluginManifestError):
        check_update_zip(ok, "other")
    future = _make_zip(str(tmp_path / "future.zip"), "mass_spec", "9.0", api_version="99.0")
    with pytest.raises(PluginManifestError, match="Graphica を更新"):
        check_update_zip(future, "mass_spec")
    empty = str(tmp_path / "empty.zip")
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("mass_spec/__init__.py", "")
    with pytest.raises(PluginManifestError):
        zip_manifest(empty)


def test_download_and_install_replaces_the_plugin_and_reports_failures(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    _write_plugin(plugins, "mass_spec", "0.2.0")
    _write_plugin(plugins, "color_studio", "0.1.0")
    source = {"mass_spec": _make_zip(str(tmp_path / "ms.zip"), "mass_spec", "1.0.0"),
              "color_studio": _make_zip(str(tmp_path / "cs.zip"), "wrong_folder", "1.0.0")}

    def fake_download(url, dest, size=0, sha256="", report_progress=None, is_cancelled=None):
        folder = os.path.basename(dest).split("-")[0]
        with open(source[folder], "rb") as src, open(dest, "wb") as out:
            out.write(src.read())
        return dest

    monkeypatch.setattr(flow, "download_file", fake_download)
    updates = [{"folder": f, "name": f, "current": "0", "latest": "1.0.0", "zip": _release("1")["zip"]}
               for f in ("mass_spec", "color_studio")]
    download_dir = tmp_path / "dl"
    download_dir.mkdir()
    results = flow.download_and_install(updates, str(plugins), str(download_dir))
    assert [(u["folder"], error is None) for u, error in results] == [("mass_spec", True), ("color_studio", False)]
    versions = {p["folder"]: p["version"] for p in installed_user_plugins(str(plugins))}
    assert versions == {"mass_spec": "1.0.0", "color_studio": "0.1.0"}
    assert os.listdir(download_dir) == []


# --- 画面の流れ ---

class _SyncRunner:
    """TaskRunner の代わりに、start() でその場で fn を呼ぶ。"""

    class _Signal:
        def __init__(self):
            self.slots = []

        def connect(self, slot):
            self.slots.append(slot)

        def disconnect(self):
            self.slots = []

    def __init__(self, fn, *args, parent=None, **kwargs):
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.succeeded, self.failed = self._Signal(), self._Signal()

    def start(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            for slot in self.failed.slots:
                slot(str(e))
            return
        for slot in self.succeeded.slots:
            slot(result)


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    from test_main_app_window import _make_isolated_main_app_window
    main = _make_isolated_main_app_window(tmp_path, monkeypatch)
    yield main.tab_widget.currentWidget()
    main.close()


def test_the_startup_check_runs_once_a_day_and_offers_updates(window, monkeypatch):
    found = [{"folder": "mass_spec", "name": "Mass Spec Pack", "current": "0.2.0", "latest": "1.0.0",
              "html_url": "", "body": "", "zip": {}}]
    calls, offered = [], []
    monkeypatch.setattr(flow, "TaskRunner", _SyncRunner)
    monkeypatch.setattr(flow, "check_plugin_updates", lambda plugins_dir: calls.append(1) or found)
    monkeypatch.setattr(flow, "offer_updates", lambda app, updates: offered.append(updates))
    app_settings.PLUGIN_UPDATE_LAST_CHECK.write(window.settings, "")
    flow.start_startup_check(window)
    assert offered == [found]
    flow.start_startup_check(window)  # 同じ日の2回目は調べない
    assert calls == [1]


def test_a_manual_check_says_everything_is_up_to_date(window, monkeypatch):
    shown = []
    monkeypatch.setattr(flow, "TaskRunner", _SyncRunner)
    monkeypatch.setattr(flow, "check_plugin_updates", lambda plugins_dir: [])
    monkeypatch.setattr(flow.notify, "information", lambda parent, title, text: shown.append(text))
    window._on_check_plugin_updates()
    assert shown and "最新" in shown[0]


def test_the_dialog_returns_only_the_checked_updates(window, monkeypatch):
    from PySide6.QtCore import Qt
    from graphica.gui.dialogs import PluginUpdatesDialog
    updates = [{"folder": f, "name": f, "current": "0", "latest": "1", "html_url": "", "body": "", "zip": {}}
               for f in ("a", "b")]
    dialog = PluginUpdatesDialog(updates, window)
    dialog.update_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert [u["folder"] for u in dialog.selected_updates()] == ["b"]
    applied = []
    monkeypatch.setattr(PluginUpdatesDialog, "exec", lambda self: PluginUpdatesDialog.DialogCode.Accepted)
    monkeypatch.setattr(flow, "apply_updates", lambda app, selected: applied.append(selected))
    flow.offer_updates(window, updates)
    assert [u["folder"] for u in applied[0]] == ["a", "b"]


def test_installing_reports_a_restart_is_needed(window, monkeypatch):
    shown = []
    monkeypatch.setattr(flow, "TaskRunner", _SyncRunner)
    monkeypatch.setattr(flow, "download_and_install", lambda updates, *a, **k: [(updates[0], None)])
    monkeypatch.setattr(flow.notify, "information", lambda parent, title, text: shown.append(text))
    flow.apply_updates(window, [{"folder": "a", "name": "A", "current": "0.1", "latest": "1.0", "zip": {}}])
    assert "起動し直す" in shown[0] and "A 0.1 → 1.0" in shown[0]
    assert window._plugin_update_runner is None


def test_the_help_menu_and_preferences_offer_the_check(window):
    texts = [action.text() for action in window._help_menu.actions()]
    assert "プラグインの更新を確認..." in texts
    from graphica.gui.dialogs import PreferencesDialog
    dialog = PreferencesDialog(False, 5, parent=window, on_check_plugin_updates=lambda: None)
    assert not dialog.check_plugin_updates_button.isHidden()
    assert PreferencesDialog(False, 5, parent=window).check_plugin_updates_button.isHidden()
    QApplication.processEvents()
