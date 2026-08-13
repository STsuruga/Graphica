#!/bin/bash
# tests/test_*.py を「ファイルごとに新しいpytestプロセス」で小分け実行する。
#
# 経緯: フルスイート(~1000テスト超)を1つのpytestプロセスで通しで実行すると、
# 各テストが _make_isolated_plotter_app() でQMainWindow/matplotlib Figureを
# 作りっぱなしにする(close()しない)慣習がリポジトリ全体にあるため、Qt/
# matplotlibのネイティブリソースがプロセス内に溜まり続け、テストが進むほど
# 1テストあたりの所要時間が悪化する。ローカルでは1256テストのフル実行が
# 90分経っても終わらなかったことを確認済み。CI (GitHub Actions、Windows/
# macOS両ランナー) でも同じ症状が発生し、"Run tests" ステップで1時間以上
# 応答がなくなる(既知の実績: あるコミットでは6時間でタイムアウト・強制
# キャンセルされた)。
#
# 対策として、テストファイルごとに(さらに大きいファイルは30テストずつに
# 分割して)毎回新しいpytestプロセスを起動する。プロセスを終了させれば
# 蓄積したリソースは解放されるため、この症状を回避できる。
#
# 使い方 (cwd = Graphica_project/):
#   bash scripts/run_tests_chunked.sh

set -u

CHUNK_SIZE=30
TMPDIR="$(pwd)/.ci_test_chunks"
rm -rf "$TMPDIR"
mkdir -p "$TMPDIR"

fail=0

for f in tests/test_*.py; do
  name=$(basename "$f" .py)
  ids_file="$TMPDIR/${name}_ids.txt"
  python -m pytest "$f" --collect-only -q 2>/dev/null | grep "::" > "$ids_file"
  n=$(wc -l < "$ids_file")

  if [ "$n" -eq 0 ]; then
    continue
  fi

  if [ "$n" -gt "$CHUNK_SIZE" ]; then
    split -l "$CHUNK_SIZE" "$ids_file" "$TMPDIR/${name}_chunk_"
    chunks=("$TMPDIR/${name}_chunk_"*)
  else
    chunks=("$f")
  fi

  for c in "${chunks[@]}"; do
    if [ "$c" == "$f" ]; then
      target="$f"
    else
      target=$(cat "$c")
    fi
    echo "=== $name :: $c ==="
    output=$(python -m pytest $target -q 2>&1)
    rc=$?
    echo "$output"
    if [ "$rc" -ne 0 ]; then
      # pytest自体は「N passed」のサマリー行まで到達しているのに、そのあとの
      # プロセス終了(Qt/matplotlibのネイティブリソース解放処理)でクラッシュし、
      # rcだけが非0になるケースがある(tests/test_export_preview_panel.py で
      # WindowsでもmacOSでも実際に観測済み: 全テストの成功サマリー出力後に
      # segmentation fault)。これはテスト内容自体の不具合ではなくインタプリタ
      # 終了時の既知の問題なので、失敗として扱わない。「failed」「error」を
      # 含まない「N passed」サマリー行が出ていることを条件に区別する。
      summary_line=$(echo "$output" | grep -E "^[0-9]+ (passed|failed|error)" | tail -n1)
      if [ -n "$summary_line" ] && ! echo "$summary_line" | grep -qE "failed|error"; then
        echo "!!! WARN: $c exited rc=$rc after all tests already passed (likely a Qt/matplotlib interpreter-teardown crash, not a real test failure): $summary_line"
      else
        echo "!!! FAILED: $c (rc=$rc)"
        fail=1
      fi
    fi
  done
done

rm -rf "$TMPDIR"
exit $fail
