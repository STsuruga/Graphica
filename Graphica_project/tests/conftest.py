# tests/conftest.py
"""
テストスイート共通のフィクスチャ。

core/commands.py の各コマンドは QUndoCommand (QObject派生) を継承しているため、
QApplication のインスタンスが存在しないと生成できない。GUIを一切表示しない
オフスクリーンプラットフォームで、セッション全体で1つだけQApplicationを用意する。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
