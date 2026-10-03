"""run_tests_chunked.sh から呼ぶ pytest の入口。

--graphica-slice=k/n を付けると、集めたテストを n 等分した k 番目だけを流す(重いファイルを複数のプロセスに分けるため)。
それ以外の引数はそのまま pytest に渡す。テストの ID を先に集めなくて済むので、収集は各プロセスが自分の分だけ行う。
"""
import os
import sys

import pytest


class _Slice:
    def __init__(self, index, count):
        self.index = index
        self.count = count

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        start = len(items) * (self.index - 1) // self.count
        end = len(items) * self.index // self.count
        deselected = items[:start] + items[end:]
        if deselected:
            config.hook.pytest_deselected(items=deselected)
        items[:] = items[start:end]


def main(argv):
    plugins = []
    args = []
    for arg in argv:
        if arg.startswith("--graphica-slice="):
            index, count = (int(v) for v in arg.split("=", 1)[1].split("/"))
            if not 1 <= index <= count:
                raise SystemExit(f"--graphica-slice の値が範囲外: {arg}")
            plugins.append(_Slice(index, count))
        else:
            args.append(arg)
    # python -m pytest と同じく、作業フォルダから import できるようにする(tests.test_xxx を import するテストがある)
    sys.path.insert(0, os.getcwd())
    return int(pytest.main(args, plugins=plugins))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
