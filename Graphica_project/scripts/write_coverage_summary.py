# scripts/write_coverage_summary.py
"""
`coverage` の計測結果を `docs/COVERAGE.md` に書き出す。

HTMLレポート(`htmlcov/`)は数千ファイルになるためリポジトリには入れない
(`.gitignore` 済み)。代わりに、レビューや引き継ぎで実際に見たい情報
——「全体の到達率」と「カバーが薄いモジュール」——だけをMarkdownの表にして
コミットする。

`scripts/run_coverage.sh` の最後から呼ばれる。単体でも、`coverage combine` 済みの
`.coverage` があれば実行できる。
"""
import json
import os
import subprocess
import sys
from datetime import date

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(PROJECT_ROOT, "docs", "COVERAGE.md")

# 「薄い」とみなす閾値。ここを下回るモジュールだけを一覧に出す
# (全モジュールを並べると100行を超えて、かえって読まれなくなるため)。
LOW_COVERAGE_THRESHOLD = 60.0
# 一覧に出す最大件数
MAX_LISTED = 25


def _coverage_json():
    """`coverage json` を一時ファイル経由で読み込む。"""
    path = os.path.join(PROJECT_ROOT, ".coverage_summary.json")
    subprocess.run(
        [sys.executable, "-m", "coverage", "json", "-o", path, "-q"],
        cwd=PROJECT_ROOT, check=True,
    )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    os.remove(path)
    return data


def _package_of(path):
    """'gui/mixins/foo.py' -> 'gui/mixins' のように、1段上のまとまりを返す。"""
    parts = path.replace("\\", "/").split("/")
    return "/".join(parts[:-1]) or "(ルート)"


def main():
    data = _coverage_json()
    totals = data["totals"]
    files = data["files"]

    by_package = {}
    for path, info in files.items():
        pkg = _package_of(path)
        acc = by_package.setdefault(pkg, {"statements": 0, "covered": 0, "files": 0})
        summary = info["summary"]
        acc["statements"] += summary["num_statements"]
        acc["covered"] += summary["covered_lines"]
        acc["files"] += 1

    low = sorted(
        (
            (path, info["summary"]["percent_covered"], info["summary"]["num_statements"])
            for path, info in files.items()
            if info["summary"]["num_statements"] >= 20
            and info["summary"]["percent_covered"] < LOW_COVERAGE_THRESHOLD
        ),
        key=lambda row: row[1],
    )

    lines = []
    lines.append("# テストカバレッジ")
    lines.append("")
    lines.append(f"計測日: {date.today().isoformat()}  ")
    lines.append(f"対象: `core` / `gui` / `models`(設定は `pyproject.toml` の "
                 "`[tool.coverage.*]`)")
    lines.append("")
    lines.append("このファイルは `bash scripts/run_coverage.sh` が自動生成する。"
                 "手で編集しても次回の実行で上書きされる。")
    lines.append("")
    lines.append("## 全体")
    lines.append("")
    lines.append("| 指標 | 値 |")
    lines.append("|---|---|")
    lines.append(f"| 行カバレッジ | **{totals['percent_covered']:.1f}%** "
                 f"({totals['covered_lines']:,} / {totals['num_statements']:,} 行) |")
    if "num_branches" in totals and totals["num_branches"]:
        branch_pct = 100.0 * totals["covered_branches"] / totals["num_branches"]
        lines.append(f"| 分岐カバレッジ | {branch_pct:.1f}% "
                     f"({totals['covered_branches']:,} / {totals['num_branches']:,}) |")
    lines.append(f"| 対象ファイル数 | {len(files)} |")
    lines.append("")

    lines.append("## パッケージ別")
    lines.append("")
    lines.append("| パッケージ | ファイル | 行カバレッジ |")
    lines.append("|---|---:|---:|")
    for pkg in sorted(by_package):
        acc = by_package[pkg]
        pct = 100.0 * acc["covered"] / acc["statements"] if acc["statements"] else 0.0
        lines.append(f"| `{pkg}` | {acc['files']} | {pct:.1f}% |")
    lines.append("")

    lines.append(f"## カバーが薄いモジュール(行カバレッジ {LOW_COVERAGE_THRESHOLD:.0f}% 未満、"
                 "20行以上のもの)")
    lines.append("")
    if not low:
        lines.append(f"該当なし。")
    else:
        lines.append("| モジュール | 行カバレッジ | 行数 |")
        lines.append("|---|---:|---:|")
        for path, pct, n in low[:MAX_LISTED]:
            lines.append(f"| `{path}` | {pct:.1f}% | {n} |")
        if len(low) > MAX_LISTED:
            lines.append("")
            lines.append(f"(ほか {len(low) - MAX_LISTED} 件。詳細は `htmlcov/index.html`)")
    lines.append("")
    lines.append("## 数字の読み方")
    lines.append("")
    lines.append("- **GUIのコードは行カバレッジが低く出やすい**。ダイアログのボタン"
                 "ハンドラのように「実際に押さないと通らない」経路が多く、ここを"
                 "100%に近づけること自体は目的ではない。")
    lines.append("- `tests/test_export_preview_panel.py` は全件パスした後の終了処理で"
                 "セグフォルトする既知の問題があり、そのチャンクの計測結果は書き出され"
                 "ない。関係するモジュールは**実際より低く出る**。")
    lines.append("- 行単位の詳細(どの行が通っていないか)は `htmlcov/index.html` を"
                 "開くこと。`htmlcov/` はリポジトリには入れていない。")
    lines.append("")

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"書き出し: {os.path.relpath(OUTPUT, PROJECT_ROOT)} "
          f"(全体 {totals['percent_covered']:.1f}%)")


if __name__ == "__main__":
    main()
