"""
コメントと docstring だけを整理した変更で、コードが変わっていないことを確かめる。

    python scripts/check_comment_only_diff.py core/named_colors.py gui/canvas.py
    python scripts/check_comment_only_diff.py --base master core/named_colors.py

各ファイルを基準(既定は HEAD)と比べ、コメントと docstring を除いた AST が同じなら SAME、
違えば DIFF を出す。1つでも DIFF なら終了コード 1。パスは Graphica_project/ からの相対。
"""
import argparse
import ast
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _without_docstrings(source):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree, include_attributes=False)


def _source_at(base, rel_path):
    git_path = (PROJECT_ROOT / rel_path).resolve().relative_to(PROJECT_ROOT.parent).as_posix()
    result = subprocess.run(
        ["git", "show", f"{base}:{git_path}"],
        cwd=PROJECT_ROOT, capture_output=True, check=True,
    )
    return result.stdout.decode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--base", default="HEAD")
    args = parser.parse_args(argv)

    all_same = True
    for rel_path in args.paths:
        current = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")
        same = _without_docstrings(_source_at(args.base, rel_path)) == _without_docstrings(current)
        all_same &= same
        print(("SAME " if same else "DIFF ") + rel_path)
    return 0 if all_same else 1


if __name__ == "__main__":
    sys.exit(main())
