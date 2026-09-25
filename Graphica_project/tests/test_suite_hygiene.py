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
import subprocess
import sys
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


# --- 設定の一括隔離 ---

def test_app_settings_go_to_a_per_test_ini_not_the_registry(isolated_settings_file):
    """本体の QSettings("Graphica", "Graphica") がレジストリではなくこのテスト専用の INI を使う。"""
    from PySide6.QtCore import QSettings

    settings = QSettings("Graphica", "Graphica")
    assert settings.format() == QSettings.Format.IniFormat
    assert Path(settings.fileName()) == Path(isolated_settings_file)
    settings.setValue("probe", "1")
    settings.sync()
    assert QSettings("Graphica", "Graphica").value("probe") == "1"


def test_each_test_starts_from_empty_settings():
    from PySide6.QtCore import QSettings

    assert QSettings("Graphica", "Graphica").value("probe") is None


def test_an_explicit_ini_path_is_left_alone(tmp_path):
    from PySide6.QtCore import QSettings

    path = tmp_path / "own.ini"
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    assert Path(settings.fileName()) == path


# --- モーダルの仕掛け線 ---

def test_an_unpatched_modal_raises_instead_of_hanging(modal_tripwire):
    from PySide6.QtWidgets import QDialog, QMessageBox

    with pytest.raises(AssertionError, match="QMessageBox.warning"):
        QMessageBox.warning(None, "題", "本文")
    with pytest.raises(AssertionError, match="QDialog.exec"):
        QDialog().exec()
    modal_tripwire.clear()


def test_print_dialogs_do_not_slip_past_the_tripwire(modal_tripwire):
    """QPrintDialog と QPageSetupDialog は exec を自前で持つので、別に差し替えてある。"""
    from PySide6.QtPrintSupport import QPageSetupDialog, QPrintDialog, QPrinter

    printer = QPrinter()
    with pytest.raises(AssertionError, match="QPrintDialog.exec"):
        QPrintDialog(printer).exec()
    with pytest.raises(AssertionError, match="QPageSetupDialog.exec"):
        QPageSetupDialog(printer).exec()
    modal_tripwire.clear()


def test_a_test_own_patch_wins_over_the_tripwire(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert QMessageBox.question(None, "題", "本文") == QMessageBox.StandardButton.Yes


def test_a_swallowed_modal_still_fails_the_test(tmp_path):
    """アプリ側が例外を握りつぶしても、テストの終わりに失敗になる。"""
    test_file = tmp_path / "test_swallowed.py"
    test_file.write_text(
        "from PySide6.QtWidgets import QMessageBox\n"
        "def test_x():\n"
        "    try:\n"
        "        QMessageBox.information(None, 't', 'm')\n"
        "    except Exception:\n"
        "        pass\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "tests.conftest",
         "-p", "no:cacheprovider", "--rootdir", str(tmp_path)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert result.returncode != 0, result.stdout
    assert "QMessageBox.information" in result.stdout
    assert "1 passed, 1 error" in result.stdout


# --- 特性テスト用の ID と時刻の固定 ---

def test_ids_and_time_are_deterministic(deterministic_ids_and_time):
    import pandas as pd

    from graphica.core.dataset import Dataset
    from graphica.core.provenance import build_provenance

    first = Dataset(name="a", df=pd.DataFrame({"x": [1], "y": [2]}), x_col_name="x", y_col_name="y")
    second = Dataset(name="b", df=pd.DataFrame({"x": [1], "y": [2]}), x_col_name="x", y_col_name="y")
    assert (first.dataset_id, second.dataset_id) == ("0" * 31 + "1", "0" * 31 + "2")
    assert build_provenance("op", {}, [first])["timestamp"] == "2026-01-01T00:00:00+00:00"


def test_chunk_runner_also_runs_the_characterization_tests():
    """特性テストはサブフォルダにあるので、ランナーの対象に入れておかないと CI で回らない。"""
    assert "tests/characterization/test_*.py" in _runner_source()


def test_chunk_runner_fails_a_file_that_cannot_be_collected(tmp_path):
    """import で落ちたテストファイルを黙って飛ばすと、その分のテストが消えたまま緑になる(K-30)。"""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (tests_dir / "test_broken.py").write_text(
        "from graphica.no_such_module import nothing\n\n\ndef test_never():\n    pass\n", encoding="utf-8")
    (tests_dir / "test_empty.py").write_text("# テストが無いだけのファイルは失敗にしない\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "run_tests_chunked.sh")],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert result.returncode != 0, result.stdout
    assert "!!! FAILED: tests/test_broken.py" in result.stdout
    assert "no_such_module" in result.stdout
    assert "!!! FAILED: tests/test_empty.py" not in result.stdout
    assert "1 passed" in result.stdout
