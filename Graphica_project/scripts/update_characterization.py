"""特性テストの基準(tests/characterization/golden/)を作り直す。

使うのは挙動を意図して変える fix: のときと、ENVIRONMENT.md の版を上げるときだけ。
refactor: のコミットで基準が変わるなら、それは挙動を変えてしまったということ。

    python scripts/update_characterization.py            # すべて作り直して、もう一度回して一致を確かめる
    python scripts/update_characterization.py -k render  # 一部だけ(pytest の -k)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET = "tests/characterization"


def run_pytest(extra: list[str], update: bool) -> int:
    env = dict(os.environ)
    if update:
        env["GRAPHICA_UPDATE_GOLDEN"] = "1"
    else:
        env.pop("GRAPHICA_UPDATE_GOLDEN", None)
    command = [sys.executable, "-m", "pytest", TARGET, "-q", "-p", "no:cacheprovider", *extra]
    return subprocess.call(command, cwd=PROJECT_ROOT, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-k", dest="keyword", help="作り直すテストを pytest の -k で絞る")
    args = parser.parse_args()
    extra = ["-k", args.keyword] if args.keyword else []

    print("== 基準を書き出す ==")
    if run_pytest(extra, update=True) != 0:
        print("基準の書き出し中にテストが失敗した(基準は途中まで書き換わっている)")
        return 1
    print("== 書き出した基準でもう一度回す ==")
    if run_pytest(extra, update=False) != 0:
        print("書き出した直後なのに一致しない: 記録が実行ごとに揺れている")
        return 1
    subprocess.call(["git", "status", "--short", "--", "tests/characterization/golden"], cwd=PROJECT_ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
