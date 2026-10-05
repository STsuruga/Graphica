# tests/test_main.py
"""main.py の --safe-mode 起動オプション判定(項目F-4)に対するテスト。

main.py は import時にQApplication等を構築しない
(if __name__ == '__main__': main() のガードがあるため)ので、
_safe_mode_flag_requested() だけを単体でimportしてテストできる。
"""
from graphica.__main__ import _safe_mode_flag_requested


def test_safe_mode_flag_present():
    assert _safe_mode_flag_requested(["prog.py", "--safe-mode"]) is True


def test_safe_mode_flag_absent():
    assert _safe_mode_flag_requested(["prog.py"]) is False


def test_safe_mode_flag_absent_with_other_args():
    """他の引数(開くファイルパス等)があっても、--safe-modeが無ければFalse。"""
    assert _safe_mode_flag_requested(["prog.py", "somefile.graphica"]) is False


def test_safe_mode_flag_present_alongside_other_args():
    assert _safe_mode_flag_requested(["prog.py", "somefile.graphica", "--safe-mode"]) is True


def test_native_crashes_are_written_to_the_log_file(tmp_path, monkeypatch):
    """Qt の中の不正アクセスなどは Python の例外にならないので、faulthandler で同じログに追記させる。"""
    import faulthandler
    import graphica.__main__ as entry_point

    enabled_with = []
    monkeypatch.setattr(faulthandler, "enable", lambda file=None, **kwargs: enabled_with.append(file))
    monkeypatch.setattr(entry_point, "_fault_log_file", None)
    log_path = tmp_path / "graphica.log"

    entry_point._enable_native_crash_log(str(log_path))

    (log_file,) = enabled_with
    assert log_file.name == str(log_path) and not log_file.closed
    assert entry_point._fault_log_file is log_file  # 持っておかないと閉じられて書けなくなる
    log_file.close()
