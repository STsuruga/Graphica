# tests/conftest.py
"""
テストスイート共通のフィクスチャ。

core/commands.py の各コマンドは QUndoCommand (QObject派生) を継承しているため、
QApplication のインスタンスが存在しないと生成できない。GUIを一切表示しない
オフスクリーンプラットフォームで、セッション全体で1つだけQApplicationを用意する。

あわせて、テストが残したウィンドウを毎テスト後に破棄する
(destroy_leftover_windows、改善ボード E-3)。詳細はそのdocstringを参照。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 未保存の変更の確認ダイアログ(v1.4.2)は、閉じる/開くたびにモーダルで止まるため
# スイート全体では無効にする。この機能のテスト(tests/test_unsaved_changes.py)だけが
# monkeypatch で "1" に戻す。
os.environ["GRAPHICA_CONFIRM_UNSAVED_CHANGES"] = "0"

import itertools
import shutil
import tempfile

import pytest
from PySide6 import QtCore
from PySide6.QtPrintSupport import QPageSetupDialog, QPrintDialog
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFontDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
)

# QSettings("Graphica", "Graphica") は setDefaultFormat を無視して常にレジストリへ書くので、
# クラスそのものを差し替えて一時 INI に向ける。本体とテストが import する前でなければ効かない。
# ファイル名を明示した呼び出し(テスト側の IsolatedQSettings)はそのまま通す。
# このファイルは tests.conftest としても import されるので、状態はクラスに持たせて二重に差し替えない。
if not getattr(QtCore.QSettings, "redirects_to_test_ini", False):
    _RealQSettings = QtCore.QSettings

    class _TestIsolatedQSettings(_RealQSettings):
        redirects_to_test_ini = True
        root = tempfile.mkdtemp(prefix="graphica-test-settings-")
        current_file = os.path.join(root, "session.ini")
        counter = itertools.count()

        def __init__(self, *args, **kwargs):
            names_a_file = (
                (len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], _RealQSettings.Format))
                or "fileName" in kwargs
            )
            if names_a_file:
                super().__init__(*args, **kwargs)
                return
            parent = kwargs.get("parent")
            if parent is None:
                parent = next((a for a in args if isinstance(a, QtCore.QObject)), None)
            super().__init__(type(self).current_file, _RealQSettings.Format.IniFormat, parent)

    QtCore.QSettings = _TestIsolatedQSettings
    _RealQSettings.setDefaultFormat(_RealQSettings.Format.IniFormat)
    _RealQSettings.setPath(_RealQSettings.Format.IniFormat, _RealQSettings.Scope.UserScope,
                           _TestIsolatedQSettings.root)

SETTINGS_CLASS = QtCore.QSettings


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    shutil.rmtree(SETTINGS_CLASS.root, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_settings_file():
    """テストごとに空の設定ファイルから始める(前のテストが書いた設定を持ち越さない)。"""
    SETTINGS_CLASS.current_file = os.path.join(SETTINGS_CLASS.root, f"test{next(SETTINGS_CLASS.counter)}.ini")
    yield SETTINGS_CLASS.current_file


class UnpatchedModalError(AssertionError):
    pass


# オフスクリーンのモーダルは誰も閉じないので、差し替え忘れはチャンクごと止まる。
# 呼ばれた時点で例外にし、アプリ側が例外を握りつぶしてもテストの終わりに失敗させる。
# テストが自分で差し替えたものは、この fixture より後に入るのでそちらが優先される。
_MODAL_TRIPWIRES = (
    (QMessageBox, ("warning", "information", "critical", "question", "about", "aboutQt")),
    (QFileDialog, ("getOpenFileName", "getOpenFileNames", "getSaveFileName", "getExistingDirectory",
                   "getOpenFileUrl", "getOpenFileUrls", "getSaveFileUrl", "getExistingDirectoryUrl")),
    (QInputDialog, ("getText", "getInt", "getDouble", "getItem", "getMultiLineText")),
    (QColorDialog, ("getColor",)),
    (QFontDialog, ("getFont",)),
    (QDialog, ("exec", "exec_")),
    # 印刷の 2 つは exec を自前で持つので、QDialog.exec の差し替えをすり抜ける
    (QPrintDialog, ("exec", "exec_")),
    (QPageSetupDialog, ("exec", "exec_")),
    (QMenu, ("exec", "exec_")),
)


def _describe_modal_args(args):
    texts = [a for a in args if isinstance(a, str)]
    owner = next((a for a in args if isinstance(a, QtCore.QObject)), None)
    if owner is not None and not texts and hasattr(owner, "windowTitle"):
        texts = [owner.windowTitle()]
    return " / ".join(texts)[:200]


@pytest.fixture(autouse=True)
def modal_tripwire():
    calls = []

    def make_tripwire(qualname):
        def tripwire(*args, **kwargs):
            message = f"差し替えられていないモーダル {qualname} が呼ばれた: {_describe_modal_args(args)}"
            calls.append(message)
            raise UnpatchedModalError(message)
        return tripwire

    with pytest.MonkeyPatch.context() as mp:
        for cls, names in _MODAL_TRIPWIRES:
            for name in names:
                mp.setattr(cls, name, make_tripwire(f"{cls.__name__}.{name}"))
        yield calls
    if calls:
        pytest.fail("\n".join(calls), pytrace=False)


@pytest.fixture
def deterministic_ids_and_time(monkeypatch):
    """特性テスト用: uuid4 を連番にし、保存物・書き出しに入る現在時刻を固定する。"""
    import datetime as datetime_module
    import uuid

    counter = itertools.count(1)
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=next(counter)))

    fixed_utc = datetime_module.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime_module.timezone.utc)

    class FixedDatetime(datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_utc.astimezone(tz) if tz is not None else fixed_utc.replace(tzinfo=None)

    class FixedDatetimeModule:
        def __getattr__(self, name):
            return FixedDatetime if name == "datetime" else getattr(datetime_module, name)

    from graphica.core import diagnostics, provenance, report_export
    from graphica.gui.mixins import export_mixin, help_mixin

    for module in (provenance, diagnostics, help_mixin):
        monkeypatch.setattr(module, "datetime", FixedDatetime)
    for module in (report_export, export_mixin):
        monkeypatch.setattr(module, "datetime", FixedDatetimeModule())
    return fixed_utc


@pytest.fixture(autouse=True)
def destroy_leftover_windows(qapp):
    """
    テストが残したトップレベルウィンドウを、毎テスト後に**実際に破棄**する
    (改善ボード E-3)。

    このスイートの多くのテストは `PlotterApp` を組み立てたまま閉じずに終わる。
    QApplication は生きたままなので、それらのウィジェットはプロセス内に residual
    として溜まり続ける。実測すると `tests/test_main_window.py` の165件を通す間に
    **生存ウィジェットが 16,707 → 98,525 個まで線形に増えて**いた。

    これが効くのは「アプリ内の全ウィジェットを走査する処理」で、テーマ再適用
    (`app.setStyleSheet()` は生きている全ウィジェットを再ポリッシュする)や
    アイコンの一括更新がそれにあたる。結果として**後ろのテストほど遅くなる**:
    同じテストが単独では 0.79 秒、165件の最後の方では 66 秒かかっていた。

    ★ `close()` だけでは足りない。Qt のウィジェットは `close()` しても
    C++ オブジェクトは生きたままで、`deleteLater()` で予約した破棄も
    イベントループを回すまで実行されない。`sendPostedEvents(DeferredDelete)` で
    その場で回収するところまでやって初めて数が減る(実測: `close()` だけだと
    349秒→304秒どまり、破棄まで行うと **349秒→74秒**)。

    ★ 自前で後始末しているテストと衝突しない。conftest の autouse フィクスチャは
    テスト側のフィクスチャより**先に**セットアップされるため、後片付けは
    **後から**走る。テスト側の `w.close()` が先に終わってからここが動く。
    """
    yield

    import matplotlib.pyplot as plt
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    plt.close("all")
    for widget in list(qapp.topLevelWidgets()):
        try:
            widget.close()
            widget.setParent(None)
            widget.deleteLater()
        except RuntimeError:
            # 既にC++側が破棄されているウィジェット(テスト側で片付け済み)
            pass
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
