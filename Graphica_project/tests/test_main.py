# tests/test_main.py
"""main.py の --safe-mode 起動オプション判定(項目F-4)に対するテスト。

main.py は import時にQApplication等を構築しない
(if __name__ == '__main__': main() のガードがあるため)ので、
_safe_mode_flag_requested() だけを単体でimportしてテストできる。
"""
from main import _safe_mode_flag_requested


def test_safe_mode_flag_present():
    assert _safe_mode_flag_requested(["prog.py", "--safe-mode"]) is True


def test_safe_mode_flag_absent():
    assert _safe_mode_flag_requested(["prog.py"]) is False


def test_safe_mode_flag_absent_with_other_args():
    """他の引数(開くファイルパス等)があっても、--safe-modeが無ければFalse。"""
    assert _safe_mode_flag_requested(["prog.py", "somefile.graphica"]) is False


def test_safe_mode_flag_present_alongside_other_args():
    assert _safe_mode_flag_requested(["prog.py", "somefile.graphica", "--safe-mode"]) is True
