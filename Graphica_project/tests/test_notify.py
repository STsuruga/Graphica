"""利用者への通知の窓口(gui/notify.py)。"""
import re
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

import graphica.gui.notify as notify

PACKAGE = Path(notify.__file__).resolve().parents[1]
DIRECT_CALL = re.compile(
    r"\bQMessageBox\.(information|warning|critical|question|about)\(|"
    r"\bQFileDialog\.get(OpenFileNames?|SaveFileName|ExistingDirectory)\(|"
    r"\bQInputDialog\.get(Text|Int|Double|Item)\("
)


def test_messages_and_questions_go_through_notify():
    # crash_handler は例外処理の最中に動くので窓口を通さない
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.name in ("notify.py", "crash_handler.py"):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if DIRECT_CALL.search(line):
                offenders.append(f"{path.relative_to(PACKAGE)}:{number}")
    assert offenders == []


def test_notify_passes_arguments_and_returns_what_qt_returns(monkeypatch):
    calls = []

    def fake_question(*args, **kwargs):
        calls.append((args, kwargs))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    answer = notify.question(None, "題", "本文", buttons, QMessageBox.StandardButton.Yes)
    assert answer == QMessageBox.StandardButton.No
    assert calls == [((None, "題", "本文", buttons, QMessageBox.StandardButton.Yes), {})]
