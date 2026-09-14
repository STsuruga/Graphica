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

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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
