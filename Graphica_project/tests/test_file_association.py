"""ファイルの関連付け: 起動中のアプリへの受け渡し(gui/single_instance.py)、Windows の登録(gui/file_association.py)、
渡されたファイルを開くこと(MainAppWindow.open_files)、環境設定のボタン。"""
import uuid

import pandas as pd
import pytest
from PySide6.QtCore import QEvent, QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

import graphica.gui.app_settings as app_settings_module
import graphica.gui.file_association as file_association
import graphica.gui.main_window as main_window_module
from graphica.core.dataset import Dataset
from graphica.gui.single_instance import (FileOpenEventFilter, InstanceServer, files_to_open, instance_running,
                                          send_to_running_instance)


# macOS はソケットを長い一時フォルダに作り、パスが 104 文字を超えると開けないので、名前は短くする
def _pump(until, rounds=200):
    for _ in range(rounds):
        QApplication.processEvents()
        if until():
            return True
    return until()


# --- 起動中のアプリへの受け渡し ---

def test_paths_sent_by_a_second_launch_reach_the_running_one(qapp, tmp_path):
    """あとから起動したアプリ(別のプロセス)が送ったパスが、起動中のアプリに届き、送った側はすぐ終わる。"""
    import json
    import subprocess
    import sys
    import time

    name = f"gt-{uuid.uuid4().hex[:8]}"
    server = InstanceServer(name)
    assert server.listen()
    received = []
    server.open_requested.connect(received.append)
    paths = [str(tmp_path / "a.gra"), str(tmp_path / "データ.csv")]
    code = ("import sys, json; from PySide6.QtCore import QCoreApplication; app = QCoreApplication([]); "
            "from graphica.gui.single_instance import send_to_running_instance; "
            f"sys.exit(0 if send_to_running_instance(json.loads(sys.argv[1]), {name!r}) else 3)")
    client = subprocess.Popen([sys.executable, "-c", code, json.dumps(paths)])
    try:
        deadline = time.time() + 30
        while client.poll() is None and time.time() < deadline:
            QApplication.processEvents()
        assert client.returncode == 0
        assert _pump(lambda: received)
        assert received == [paths]
    finally:
        if client.poll() is None:
            client.kill()
        server.close()


def test_a_running_instance_is_detected(qapp):
    name = f"gt-{uuid.uuid4().hex[:8]}"
    server = InstanceServer(name)
    assert server.listen()
    try:
        assert instance_running(name)
    finally:
        server.close()


def test_nothing_is_running_when_no_server_listens(qapp):
    name = f"gt-{uuid.uuid4().hex[:8]}"
    assert not instance_running(name)
    assert not send_to_running_instance(["x.gra"], name)


def test_broken_messages_are_ignored(qapp):
    from PySide6.QtNetwork import QLocalSocket

    name = f"gt-{uuid.uuid4().hex[:8]}"
    server = InstanceServer(name)
    assert server.listen()
    received = []
    server.open_requested.connect(received.append)
    try:
        socket = QLocalSocket()
        socket.connectToServer(name)
        assert socket.waitForConnected(1000)
        socket.write(b"not json\n{\"open\": [1, \"ok.gra\"]}\n")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        assert _pump(lambda: received)
        assert received == [["ok.gra"]]
    finally:
        server.close()


def test_only_existing_files_from_the_command_line_are_opened(tmp_path):
    existing = tmp_path / "a.gra"
    existing.write_text("{}", encoding="utf-8")
    argv = ["Graphica.exe", "--safe-mode", str(existing), str(tmp_path / "missing.gra")]
    assert files_to_open(argv) == [str(existing)]


class _FakeFileOpenEvent:
    """QFileOpenEvent はテストの中で作ると落ちる(Qt の内部でしか作らない前提)ので、同じ形の偽物で試す。"""

    def __init__(self, path):
        self._path = path

    def type(self):
        return QEvent.Type.FileOpen

    def file(self):
        return self._path


def test_macos_file_open_events_are_forwarded(qapp):
    event_filter = FileOpenEventFilter()
    received = []
    event_filter.open_requested.connect(received.append)
    assert event_filter.eventFilter(qapp, _FakeFileOpenEvent("/tmp/x.gra")) is True
    assert received == [["/tmp/x.gra"]]
    assert event_filter.eventFilter(qapp, QEvent(QEvent.Type.MouseMove)) is False


# --- Windows の登録(レジストリは偽物) ---

class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_WRITE = KEY_ALL_ACCESS = 0
    REG_SZ = 1

    def __init__(self):
        self.keys = {}

    class _Key:
        def __init__(self, reg, path):
            self.reg, self.path = reg, path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def CreateKeyEx(self, root, path, reserved=0, access=0):
        parts = path.split("\\")
        for i in range(1, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:i]), {})
        return self._Key(self, path)

    def OpenKey(self, root, path, reserved=0, access=0):
        if path not in self.keys:
            raise FileNotFoundError(path)
        return self._Key(self, path)

    def SetValueEx(self, key, name, reserved, kind, value):
        self.keys[key.path][name] = value

    def QueryValueEx(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(name)
        return self.keys[key.path][name], self.REG_SZ

    def EnumKey(self, key, index):
        children = sorted({k[len(key.path) + 1:].split("\\")[0] for k in self.keys
                           if k.startswith(key.path + "\\")})
        if index >= len(children):
            raise OSError("no more")
        return children[index]

    def DeleteKey(self, root, path):
        if any(k.startswith(path + "\\") for k in self.keys):
            raise OSError("has children")
        del self.keys[path]


EXE = r"C:\Program Files\Graphica\Graphica.exe"


def test_register_points_both_extensions_at_the_exe():
    reg = FakeWinreg()
    file_association.register(EXE, winreg=reg, notify_shell=False)

    assert reg.keys[r"Software\Classes\.gra"][""] == "Graphica.Project"
    assert reg.keys[r"Software\Classes\.graphica"][""] == "Graphica.Project"
    assert reg.keys[r"Software\Classes\Graphica.Project\shell\open\command"][""] == f'"{EXE}" "%1"'
    assert reg.keys[r"Software\Classes\Graphica.Project\DefaultIcon"][""] == f'"{EXE}",0'
    assert file_association.is_registered(EXE, winreg=reg)
    assert not file_association.is_registered(r"C:\other\Graphica.exe", winreg=reg)


def test_unregister_removes_only_what_points_at_graphica():
    reg = FakeWinreg()
    file_association.register(EXE, winreg=reg, notify_shell=False)
    reg.keys[r"Software\Classes\.graphica"][""] = "SomeOtherApp.File"

    file_association.unregister(winreg=reg, notify_shell=False)

    assert r"Software\Classes\.gra" not in reg.keys
    assert reg.keys[r"Software\Classes\.graphica"][""] == "SomeOtherApp.File"
    assert not any(k.startswith(r"Software\Classes\Graphica.Project") for k in reg.keys)
    assert not file_association.is_registered(EXE, winreg=reg)


def test_registration_is_offered_only_for_the_windows_exe(monkeypatch):
    monkeypatch.setattr(file_association.sys, "platform", "win32")
    monkeypatch.setattr(file_association.sys, "frozen", True, raising=False)
    assert file_association.is_supported()
    monkeypatch.delattr(file_association.sys, "frozen")
    assert not file_association.is_supported()
    monkeypatch.setattr(file_association.sys, "frozen", True, raising=False)
    monkeypatch.setattr(file_association.sys, "platform", "darwin")
    assert not file_association.is_supported()


def test_preferences_buttons_follow_the_registration(qapp, monkeypatch):
    from graphica.gui.dialogs import PreferencesDialog

    state = {"registered": False}
    monkeypatch.setattr(file_association, "is_supported", lambda: True)
    monkeypatch.setattr(file_association, "is_registered", lambda: state["registered"])
    monkeypatch.setattr(file_association, "register", lambda: state.update(registered=True))
    monkeypatch.setattr(file_association, "unregister", lambda: state.update(registered=False))

    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    assert dlg.register_file_association_button.isEnabled()
    assert not dlg.unregister_file_association_button.isEnabled()

    dlg.register_file_association_button.click()
    assert state["registered"]
    assert not dlg.register_file_association_button.isEnabled()
    assert dlg.unregister_file_association_button.isEnabled()

    dlg.unregister_file_association_button.click()
    assert not state["registered"]
    assert dlg.register_file_association_button.isEnabled()


def test_preferences_buttons_are_disabled_outside_the_exe(qapp, monkeypatch):
    from graphica.gui.dialogs import PreferencesDialog

    monkeypatch.setattr(file_association, "is_supported", lambda: False)
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    assert not dlg.register_file_association_button.isEnabled()
    assert not dlg.unregister_file_association_button.isEnabled()


# --- 渡されたファイルを開く ---

@pytest.fixture
def main_app_window(tmp_path, monkeypatch):
    from graphica.gui.main_app_window import MainAppWindow

    settings_path = str(tmp_path / "settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))

    class FakeWelcomeDialog:
        def __init__(self, *args, **kwargs):
            self.load_sample_requested = False
            self.selected_recent_file = None
            self.load_template_requested = False

        def exec(self):
            return 0

    monkeypatch.setattr(main_window_module, "WelcomeDialog", FakeWelcomeDialog)
    window = MainAppWindow()
    for _ in range(5):
        QApplication.processEvents()
    return window


def _saved_project(tab, path, name):
    tab.project.datasets.append(Dataset(name=name, df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
                                        x_col_name="x", y_col_name="y"))
    tab._save_project_to_path(str(path))
    tab.project.datasets.clear()
    tab._remember_saved_content()


def test_running_app_opens_each_project_in_a_new_tab(main_app_window, tmp_path):
    first_tab = main_app_window.tab_widget.widget(0)
    a, b = tmp_path / "a.gra", tmp_path / "b.graphica"
    _saved_project(first_tab, a, "A")
    _saved_project(first_tab, b, "B")

    main_app_window.open_files([str(a), str(b)])

    tabs = [main_app_window.tab_widget.widget(i) for i in range(main_app_window.tab_widget.count())]
    assert len(tabs) == 3
    assert [ds.name for ds in tabs[1].project.datasets] == ["A"]
    assert [ds.name for ds in tabs[2].project.datasets] == ["B"]
    assert main_app_window.tab_widget.currentIndex() == 2


def test_launch_with_a_file_reuses_the_empty_first_tab(main_app_window, tmp_path):
    first_tab = main_app_window.tab_widget.widget(0)
    a = tmp_path / "a.gra"
    _saved_project(first_tab, a, "A")

    main_app_window.open_files([str(a)], reuse_empty_tab=True)

    assert main_app_window.tab_widget.count() == 1
    assert [ds.name for ds in first_tab.project.datasets] == ["A"]


def test_launch_does_not_replace_a_tab_that_has_content(main_app_window, tmp_path):
    first_tab = main_app_window.tab_widget.widget(0)
    a = tmp_path / "a.gra"
    _saved_project(first_tab, a, "A")
    first_tab._add_dataset(Dataset(name="kept", df=pd.DataFrame({"x": [1], "y": [2]}), x_col_name="x",
                                   y_col_name="y"))

    main_app_window.open_files([str(a)], reuse_empty_tab=True)

    assert main_app_window.tab_widget.count() == 2
    assert [ds.name for ds in first_tab.project.datasets] == ["kept"]


def test_data_files_are_queued_into_the_last_opened_tab(main_app_window, tmp_path, monkeypatch):
    first_tab = main_app_window.tab_widget.widget(0)
    a = tmp_path / "a.gra"
    _saved_project(first_tab, a, "A")
    csv = tmp_path / "d.csv"
    csv.write_text("x,y\n1,2\n", encoding="utf-8")
    queued = []
    from graphica.gui.main_window import PlotterApp
    monkeypatch.setattr(PlotterApp, "_queue_data_files", lambda self, paths: queued.append((self, paths)))

    main_app_window.open_files([str(csv), str(a)])

    last_tab = main_app_window.tab_widget.widget(main_app_window.tab_widget.count() - 1)
    assert queued == [(last_tab, [str(csv)])]
