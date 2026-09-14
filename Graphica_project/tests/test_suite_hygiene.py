# tests/test_suite_hygiene.py
"""
テストスイート自身の衛生状態に対するテスト(改善ボード E-3)。

このスイートの多くのテストは `PlotterApp` を組み立てたまま閉じずに終わる。
QApplication は生きたままなので、放っておくとウィジェットがプロセス内に
溜まり続ける。実測では `tests/test_main_window.py` の165件を通す間に
**生存ウィジェットが 16,707 → 98,525 個まで線形に増えて**いた。

これが効くのは「アプリ内の全ウィジェットを走査する処理」で、テーマ再適用
(`app.setStyleSheet()` は生きている全ウィジェットを再ポリッシュする)や
アイコンの一括更新がそれにあたる。結果として**後ろのテストほど遅くなり**、
同じテストが単独では 0.79 秒、165件の最後の方では 66 秒かかっていた。

`tests/conftest.py` の `destroy_leftover_windows` がこれを断っている。
このファイルは**その後始末が実際に効いていること**を固定する。ここが黙って
壊れると、症状は「テストが失敗する」ではなく「スイートがじわじわ遅くなる」
なので、普通のテストでは絶対に気づけない。

参考(E-3 で入れた対策と実測):

| 対策 | 効果 |
|---|---|
| 残ったウィンドウの破棄 | `test_main_window.py` 349秒 → 74秒 |
| 収集を1プロセスに集約 | 収集だけで 255秒 → 5.3秒 |
| 一括書き換え中の再描画停止 | `test_settings_mixin.py` 234秒 → 31秒 |
| CHUNK_SIZE 30 → 150 | チャンク 150 → 98 |
| **フルスイート全体** | **約35分 → 約17.5分** |
"""
import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow

import tests.conftest as conftest_module


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _live_widget_count():
    return len(QApplication.allWidgets())


# --- 後始末フィクスチャ本体 ---

def test_the_teardown_fixture_is_autouse():
    """
    autouse を外すと、ウィンドウを閉じないテストがまた溜め始める。
    症状が「遅くなるだけ」で失敗しないため、設定自体を固定しておく。
    """
    fixture = conftest_module.destroy_leftover_windows
    # pytest のバージョンによって内部属性名が違う(8系は
    # _fixture_function_marker、それ以前は _pytestfixturefunction)ため、
    # 見つかった方を使う。どちらも無ければ pytest 側の仕様変更なので、
    # conftest のソースを直接見るところまで落とす。
    marker = getattr(fixture, "_fixture_function_marker", None) \
        or getattr(fixture, "_pytestfixturefunction", None)
    if marker is not None:
        assert marker.autouse is True
    else:
        source = (PROJECT_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
        assert re.search(r"@pytest\.fixture\(autouse=True\)\s*\ndef destroy_leftover_windows",
                         source), "destroy_leftover_windows が autouse ではない"


# ★ 下の2件は「この順番で実行されること」に依存している(pytest はファイル内の
#   定義順に実行し、このリポジトリは実行順をランダム化するプラグインを入れて
#   いない)。前のテストが残したウィンドウが、次のテストが始まる時点で
#   片付いていることを見るため、どうしても2件に分ける必要がある。
_LEAKED = {}


def test_leaking_windows_on_purpose():
    """わざと閉じずにウィンドウを残す(直後のテストで回収を確認する)。"""
    _LEAKED["before"] = _live_widget_count()
    for _ in range(20):
        window = QMainWindow()
        window.show()
    assert _live_widget_count() > _LEAKED["before"]


def test_the_leaked_windows_are_gone_by_the_next_test():
    """
    ★ 本命。前のテストが残した20個のウィンドウが、このテストが始まる時点で
    破棄されていること。`close()` しただけでは C++ オブジェクトは生き残るので、
    `deleteLater()` + `sendPostedEvents(DeferredDelete)` まで行う必要がある。
    """
    assert "before" in _LEAKED, "前のテストが実行されていない(実行順の前提が崩れている)"
    assert _live_widget_count() <= _LEAKED["before"], (
        "前のテストが残したウィンドウが片付いていない。"
        "conftest の destroy_leftover_windows を確認すること"
    )


def test_top_level_windows_do_not_pile_up_within_one_test():
    """
    1テストの中で作った・閉じたウィンドウは、そのテストの中では残っていてよい
    (後始末はテスト後に走る)。ここでは「フィクスチャが走る前に勝手に消される」
    という逆の壊れ方をしていないことを確認する。
    """
    window = QMainWindow()
    window.show()
    assert window.isVisible()
    window.close()
    assert not window.isVisible()


# --- チャンクランナーの設定 ---

def _runner_source():
    return (PROJECT_ROOT / "scripts" / "run_tests_chunked.sh").read_text(encoding="utf-8")


def test_chunk_runner_collects_test_ids_in_a_single_process():
    """
    ★ 以前はファイルごとに `pytest --collect-only` を起動しており、
    92ファイル×約2.8秒＝**約255秒**を「テストを1件も実行しないまま」
    消費していた(1プロセスなら約5.3秒)。戻すと、目に見えない形で
    4分ほど失う。
    """
    source = _runner_source()
    assert "pytest tests/ --collect-only" in source, \
        "全体を1回で収集する行が無い"
    # ファイルごとの収集は、まとめての収集が失敗したときの保険としてのみ残る
    per_file_collects = source.count('pytest "$f" --collect-only')
    assert per_file_collects == 1, \
        "ファイルごとの収集が保険以外の場所にも残っている"


def test_chunk_runner_still_isolates_per_file():
    """
    チャンクを大きくしても、ファイル単位の分離自体は残すこと。
    `tests/test_export_preview_panel.py` は全件パスした後の終了処理で
    セグフォルトする既知問題があり、1プロセスにまとめると以降のテストが
    道連れになる。
    """
    source = _runner_source()
    assert "for f in tests/test_*.py" in source


def test_chunk_size_is_documented_and_reasonable():
    match = re.search(r"^CHUNK_SIZE=(\d+)", _runner_source(), re.M)
    assert match, "CHUNK_SIZE が見つからない"
    chunk_size = int(match.group(1))
    # 小さすぎるとプロセス起動の回数が増えるだけ(蓄積は conftest 側で断ってある)。
    # 大きすぎると、将来また別の蓄積が出たときに気づきにくくなる。
    assert 50 <= chunk_size <= 500, f"CHUNK_SIZE={chunk_size} は想定外"


# --- 遅いテストを作らないための注意書き ---

def test_settings_mixin_bulk_mutation_still_suppresses_redraws():
    """
    ★ `_mutate_every_control` は約90個のコントロールを順に書き換える。
    そのたびに `_on_axis_setting_changed` → `_update_plot_appearance()`
    (tight_layout + draw)が走ると、1テスト35〜42秒・ファイル全体で234秒に
    なる(実測)。再描画を止める仕掛けが外れたら気づけるようにしておく。
    """
    import inspect
    import tests.test_settings_mixin as module

    source = inspect.getsource(module._mutate_every_control)
    assert "_without_live_redraw" in source
