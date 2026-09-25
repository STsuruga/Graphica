"""特性テストのシナリオ部品: モーダルの記録と台本、同じ条件でのアプリの組み立て。"""
from __future__ import annotations

from collections import deque
from typing import Any

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMenu, QMessageBox


class ModalLog:
    """出たモーダルを順に記録し、台本(respond で積んだ答え)を返す。

    台本が空のときの答え: 通知は Ok、ファイル・入力の問い合わせは取り消し、ダイアログの exec は Rejected。
    はい/いいえの問いは答えを決めないと挙動が決まらないので、台本が無ければ失敗にする。
    """

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self._answers: deque[Any] = deque()

    def respond(self, *answers: Any) -> None:
        self._answers.extend(answers)

    def _next(self, kind: str, default: Any) -> Any:
        if self._answers:
            return self._answers.popleft()
        if default is _REQUIRED:
            raise AssertionError(f"{kind} に答える台本が無い(ModalLog.respond で積む)")
        return default

    def record(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)

    def take(self) -> list[dict[str, Any]]:
        entries, self.entries = self.entries, []
        return entries


_REQUIRED = object()


def _button_names(buttons: Any) -> list[str]:
    names = []
    for button in QMessageBox.StandardButton:
        if button != QMessageBox.StandardButton.NoButton and (buttons & button) == button:
            names.append(button.name)
    return names


def _message_box_static(log: ModalLog, kind: str, default: Any):
    def show(parent, title, text, buttons=None, defaultButton=None, *args, **kwargs):
        entry = {"kind": f"QMessageBox.{kind}", "title": title, "text": text}
        if buttons is not None:
            entry["buttons"] = _button_names(buttons)
        if defaultButton is not None:
            entry["default"] = getattr(defaultButton, "name", str(defaultButton))
        log.record(entry)
        return log._next(kind, default)
    return show


def _about(log: ModalLog, kind: str):
    def show(parent, title="", text="", *args, **kwargs):
        log.record({"kind": f"QMessageBox.{kind}", "title": title, "text": text})
    return show


def _file_dialog(log: ModalLog, kind: str, default: Any):
    def show(parent=None, caption="", directory="", filter="", *args, **kwargs):
        log.record({"kind": f"QFileDialog.{kind}", "caption": caption, "filter": filter})
        return log._next(kind, default)
    return show


def _input_dialog(log: ModalLog, kind: str, default: Any):
    def show(parent, title, label, *args, **kwargs):
        log.record({"kind": f"QInputDialog.{kind}", "title": title, "label": label})
        return log._next(kind, default)
    return show


def _dialog_exec(log: ModalLog):
    def exec_(self, *args, **kwargs):
        entry: dict[str, Any] = {"kind": "exec", "class": type(self).__name__, "title": self.windowTitle()}
        if isinstance(self, QMessageBox):
            entry["text"] = self.text()
            entry["informative"] = self.informativeText()
            entry["icon"] = self.icon().name
            entry["buttons"] = [b.text() for b in self.buttons()]
        log.record(entry)
        answer = log._next("exec", QDialog.DialogCode.Rejected)
        if callable(answer):
            return answer(self)
        return int(answer.value) if hasattr(answer, "value") else answer
    return exec_


def _menu_exec(log: ModalLog):
    def exec_(self, *args, **kwargs):
        log.record({"kind": "QMenu.exec", "actions": [a.text() for a in self.actions()]})
        return log._next("QMenu.exec", None)
    return exec_


def install_modal_log(monkeypatch) -> ModalLog:
    log = ModalLog()
    ok = QMessageBox.StandardButton.Ok
    for kind in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, kind, _message_box_static(log, kind, ok))
    monkeypatch.setattr(QMessageBox, "question", _message_box_static(log, "question", _REQUIRED))
    for kind in ("about", "aboutQt"):
        monkeypatch.setattr(QMessageBox, kind, _about(log, kind))
    for kind, default in (("getOpenFileName", ("", "")), ("getOpenFileNames", ([], "")),
                          ("getSaveFileName", ("", "")), ("getExistingDirectory", "")):
        monkeypatch.setattr(QFileDialog, kind, _file_dialog(log, kind, default))
    for kind, default in (("getText", ("", False)), ("getInt", (0, False)), ("getDouble", (0.0, False)),
                          ("getItem", ("", False)), ("getMultiLineText", ("", False))):
        monkeypatch.setattr(QInputDialog, kind, _input_dialog(log, kind, default))
    monkeypatch.setattr(QDialog, "exec", _dialog_exec(log))
    monkeypatch.setattr(QMenu, "exec", _menu_exec(log))
    return log


class AppEnvironment:
    """シナリオごとに同じ条件でアプリを組み立てる(設定・言語・テーマ・プラグイン)。"""

    def __init__(self, tmp_path, monkeypatch, modal_log: ModalLog):
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.modal_log = modal_log

    def settings(self, **values: Any) -> None:
        from PySide6.QtCore import QSettings

        settings = QSettings("Graphica", "Graphica")
        for key, value in values.items():
            settings.setValue(key, value)
        settings.sync()

    def use_plugins(self, example_plugin: bool) -> None:
        """利用者のプラグインフォルダは読まない。同梱の example_plugin を読むかどうかだけを選ぶ。"""
        import graphica.core.analysis as analysis_module
        import graphica.core.plugin_api as plugin_api_module
        import graphica.gui.main_window as main_window_module

        self.monkeypatch.setattr(plugin_api_module, "_singleton_api", None)
        self.monkeypatch.setattr(plugin_api_module, "_singleton_manager", None)
        self.monkeypatch.setattr(analysis_module, "_PLUGIN_FIT_FUNCTIONS", {})
        paths = [main_window_module.resource_path("plugins")] if example_plugin else []
        self.monkeypatch.setattr(main_window_module, "plugin_search_paths", lambda: list(paths))

    def main_window(self, *, language: str = "ja", dark: bool = False, example_plugin: bool = True, **settings):
        from graphica.gui.main_app_window import MainAppWindow

        self.settings(language=language, dark_mode=dark, autosave_dir=str(self.tmp_path / "autosave"), **settings)
        self.use_plugins(example_plugin)
        window = MainAppWindow()
        window.resize(1300, 850)
        window.show()
        pump()
        return window

    def tab(self, *, language: str = "ja", dark: bool = False, example_plugin: bool = False,
            size: tuple[int, int] = (1100, 700), **settings):
        from graphica.gui.main_window import PlotterApp

        self.settings(language=language, dark_mode=dark, autosave_dir=str(self.tmp_path / "autosave"), **settings)
        self.use_plugins(example_plugin)
        window = PlotterApp(run_startup_checks=False, tab_id=2)
        window.resize(*size)
        window.show()
        pump()
        return window


def dispose(widget) -> None:
    """ループの中で作ったウィンドウをその場で破棄する(溜めると後のシナリオほど遅くなる)。"""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    widget.close()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def pump(times: int = 5) -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    for _ in range(times):
        app.processEvents()
