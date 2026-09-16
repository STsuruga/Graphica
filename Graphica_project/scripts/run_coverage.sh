#!/bin/bash
# テストカバレッジを計測して、要約(docs/COVERAGE.md)、詳細(docs/COVERAGE_DETAILS.md)、
# HTML(htmlcov/)を出す。
#
#   使い方 (cwd = Graphica_project/):
#     bash scripts/run_coverage.sh
#
# 中身は run_tests_chunked.sh をカバレッジ付きで回しているだけ。テストの実行方法を
# 二重に持たないよう、チャンク実行のロジックはあちらに一本化してある
# (GRAPHICA_COVERAGE=1 で `python -m coverage run --parallel-mode -m pytest` に
# 切り替わる)。
#
# なぜ --parallel-mode が要るか: チャンクごとに別プロセスでテストを回すため、
# 1つの .coverage ファイルを複数プロセスが奪い合うと最後の1つしか残らない。
# parallel-mode では各プロセスが .coverage.<host>.<pid>.<乱数> を個別に書き、
# `coverage combine` で束ねる。
#
# 計測すると2〜3割遅くなる(実測: 通常17分台 → 22〜25分)。普段の回帰確認では
# 付けず、リリース前など必要なときだけ実行すること。
#
# ★ 既知の制約: tests/test_export_preview_panel.py は全件パスした後の終了処理で
#   セグフォルトする(CLAUDE.md「Known benign failure」)。プロセスが異常終了すると
#   そのチャンクのカバレッジデータは書き出されないため、このファイルが通る行は
#   実際より低く出る。テスト自体は通っているので、数字だけの問題。

set -u

cd "$(dirname "$0")/.." || exit 1

echo "=== 1/4 古い計測結果を片付け ==="
python -m coverage erase 2>/dev/null || true
rm -rf htmlcov
rm -f .coverage.*

echo "=== 2/4 カバレッジ付きでフルスイートを実行(通常より2〜3割遅い)==="
GRAPHICA_COVERAGE=1 bash scripts/run_tests_chunked.sh
suite_status=$?

echo "=== 3/4 チャンクごとの計測結果を結合 ==="
python -m coverage combine

echo "=== 4/4 レポートを生成 ==="
python -m coverage html -d htmlcov
python -m coverage report

python scripts/write_coverage_summary.py

echo
echo "HTML: htmlcov/index.html"
echo "要約: docs/COVERAGE.md"
echo "詳細: docs/COVERAGE_DETAILS.md"
if [ "$suite_status" -ne 0 ]; then
  echo "※ テスト側が非0で終了している。上のログを確認すること。"
fi
exit "$suite_status"
