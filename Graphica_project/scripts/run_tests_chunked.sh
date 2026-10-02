#!/bin/bash
# tests/ を小分けにして、別々の pytest プロセスで並列に流す。
#
# プロセスを分けるのは、並列に流すためと、1 つのプロセスが落ちてもほかのチャンクの結果を失わないため。
# tests/test_export_preview_panel.py は全件パスのあとの終了処理でセグフォルトする。サマリーまで出てから
# 落ちたものは、下の判定で警告にとどめる。
#
# 使い方 (cwd = Graphica_project/):
#   bash scripts/run_tests_chunked.sh
#   GRAPHICA_TEST_JOBS=1 bash scripts/run_tests_chunked.sh   # 1 つずつ流す(既定は CPU の数)
#   GRAPHICA_COVERAGE=1 bash scripts/run_tests_chunked.sh    # カバレッジ付き(まとめは scripts/run_coverage.sh)

set -u

# 1 プロセスに渡すテスト ID の上限(Windows のコマンドラインの長さに収める)
CHUNK_SIZE=150
# チャンクの重さの上限。ウィンドウを作るテストは 1 件約 0.5 秒で、ほかの数十倍かかるので重みを付ける
MAX_COST=600
HEAVY_WEIGHT=10
JOBS="${GRAPHICA_TEST_JOBS:-$(python -c 'import os; print(os.cpu_count() or 1)')}"
TMPDIR="$(pwd)/.ci_test_chunks"
rm -rf "$TMPDIR"
mkdir -p "$TMPDIR/results"
# pytest の一時フォルダはプロジェクトの外に置く(中に置くと、そこで動くテストが pyproject.toml を拾う)
# Python に作らせるのは、Windows の Git Bash でも Python がそのまま読めるパスにするため
BASETEMP_ROOT=$(python -c 'import tempfile; print(tempfile.mkdtemp(prefix="graphica-pytest-"))')
export BASETEMP_ROOT

if [ "${GRAPHICA_COVERAGE:-0}" = "1" ]; then
  # 各プロセスが .coverage.<host>.<pid>.<乱数> に書き、run_coverage.sh が combine する
  PYTEST_CMD="python -m coverage run --parallel-mode -m pytest"
else
  PYTEST_CMD="python -m pytest"
fi
export PYTEST_CMD

fail=0

# 収集は全体を 1 プロセスで 1 回だけ(ファイルごとに起動すると、収集だけで数分かかる)
ALL_IDS="$TMPDIR/all_ids.txt"
python -m pytest tests/ --collect-only -q 2>/dev/null | grep "::" > "$ALL_IDS" || true

# 1 行 = 「重さ TAB 名前 TAB 対象の一覧」。一覧は pytest に渡す引数(ファイルかテスト ID)を 1 行ずつ並べたファイル。
# 重いファイルは分け、軽いファイルはまとめて 1 プロセスにする(プロセスの起動と import だけで 1 回数秒かかる)。
# 特性テストは条件をそろえて動かすので、ほかと混ぜない。
CHUNKS="$TMPDIR/chunks.tsv"
: > "$CHUNKS"
chunk_no=0
pack_list=""
pack_cost=0
pack_name=""

flush_pack() {
  if [ -n "$pack_list" ]; then
    printf '%s\t%s\t%s\n' "$pack_cost" "$pack_name" "$pack_list" >> "$CHUNKS"
  fi
  pack_list=""
  pack_cost=0
  pack_name=""
}

for group in "tests/test_*.py" "tests/characterization/test_*.py"; do
  for f in $group; do
    [ -f "$f" ] || continue
    name=$(basename "$f" .py)
    ids_file="$TMPDIR/${name}_ids.txt"
    # 末尾の ".py::" まで含めて引くので、test_dataset.py と test_dataset_mixin.py を取り違えない
    grep -F "$f::" "$ALL_IDS" > "$ids_file" || true
    n=$(wc -l < "$ids_file" | tr -d ' ')

    if [ "$n" -eq 0 ]; then
      # まとめての収集が import エラーなどでこのファイルだけ落とした可能性がある。単体で収集し直し、
      # 「テストが 1 件も無い」(rc=5)以外で 0 件なら失敗にする(黙って飛ばすとテストが消えたまま緑になる)
      collect_output=$(python -m pytest "$f" --collect-only -q 2>&1)
      collect_rc=$?
      echo "$collect_output" | grep "::" > "$ids_file" || true
      n=$(wc -l < "$ids_file" | tr -d ' ')
      if [ "$n" -eq 0 ] && [ "$collect_rc" -ne 5 ]; then
        echo "=== $name :: $f ==="
        echo "$collect_output"
        echo "!!! FAILED: $f (collection failed, rc=$collect_rc)"
        fail=1
        continue
      fi
    fi

    if [ "$n" -eq 0 ]; then
      continue
    fi

    weight=1
    if grep -qE "PlotterApp\(|_make_isolated_plotter_app|MainAppWindow\(|make_window|scenario\." "$f"; then
      weight=$HEAVY_WEIGHT
    fi
    cost=$((n * weight))

    if [ "$cost" -gt "$MAX_COST" ]; then
      piece=$((MAX_COST / weight))
      if [ "$piece" -gt "$CHUNK_SIZE" ]; then
        piece=$CHUNK_SIZE
      fi
      split -l "$piece" "$ids_file" "$TMPDIR/${name}_chunk_"
      for c in "$TMPDIR/${name}_chunk_"*; do
        printf '%s\t%s\t%s\n' "$(( $(wc -l < "$c" | tr -d ' ') * weight ))" "$name" "$c" >> "$CHUNKS"
      done
    else
      if [ $((pack_cost + cost)) -gt "$MAX_COST" ]; then
        flush_pack
      fi
      if [ -z "$pack_list" ]; then
        chunk_no=$((chunk_no + 1))
        pack_list="$TMPDIR/pack_$chunk_no.txt"
        : > "$pack_list"
        pack_name="$name"
      else
        pack_name="$pack_name $name"
      fi
      echo "$f" >> "$pack_list"
      pack_cost=$((pack_cost + cost))
    fi
  done
  flush_pack
done

total=$(wc -l < "$CHUNKS" | tr -d ' ')
echo "=== $total chunks, $JOBS in parallel ==="

# 1 チャンクを流し、出力と終了コードを results/<番号>.log / .rc に残す。
# --basetemp を分けるのは、pytest が並行する別プロセスの一時フォルダを古いものとして消さないため
run_chunk() {
  index=$1; name=$2; target=$3; total=$4; results=$5
  # テスト ID は空白や括弧を含む(パラメータの ID)ので、1 行を 1 引数として渡す
  set --
  while IFS= read -r line; do
    set -- "$@" "$line"
  done < "$target"
  $PYTEST_CMD "$@" -q -p no:cacheprovider --basetemp="$BASETEMP_ROOT/$index" > "$results/$index.log" 2>&1
  rc=$?
  echo "$rc" > "$results/$index.rc"
  rm -rf "$BASETEMP_ROOT/$index"
  echo "[$(ls "$results"/*.rc | wc -l | tr -d ' ')/$total] $name (rc=$rc)"
}
export -f run_chunk

# 重いチャンクから始め、最後に 1 つだけ長いチャンクが残るのを避ける。
# 区切りは NUL(作業フォルダのパスに空白があっても 1 引数のまま渡す)
nl -ba -w1 -s"$(printf '\t')" "$CHUNKS" | sort -t"$(printf '\t')" -k2,2nr \
  | while IFS="$(printf '\t')" read -r index cost name target; do
      printf '%s\0%s\0%s\0%s\0%s\0' "$index" "$name" "$target" "$total" "$TMPDIR/results"
    done \
  | xargs -0 -n 5 -P "$JOBS" bash -c 'run_chunk "$@"' _

# 結果は元の順番で出す
while IFS="$(printf '\t')" read -r index cost name target; do
  echo "=== $name ==="
  output=$(cat "$TMPDIR/results/$index.log" 2>/dev/null)
  rc=$(cat "$TMPDIR/results/$index.rc" 2>/dev/null || echo "missing")
  echo "$output"
  if [ "$rc" != "0" ]; then
    # 「N passed」のサマリーまで出たあとの終了処理でだけ落ちたもの(test_export_preview_panel.py の
    # セグフォルト)は失敗にしない。サマリーに failed / error を含むものは失敗
    summary_line=$(echo "$output" | grep -E "^[0-9]+ (passed|failed|error)" | tail -n1)
    if [ -n "$summary_line" ] && ! echo "$summary_line" | grep -qE "failed|error"; then
      echo "!!! WARN: $name exited rc=$rc after all tests already passed (likely a Qt/matplotlib interpreter-teardown crash, not a real test failure): $summary_line"
    else
      echo "!!! FAILED: $name (rc=$rc)"
      fail=1
    fi
  fi
done < <(nl -ba -w1 -s"$(printf '\t')" "$CHUNKS")

rm -rf "$TMPDIR" "$BASETEMP_ROOT"
exit $fail
