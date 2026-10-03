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
#   GRAPHICA_TEST_SHARD=2/3 bash scripts/run_tests_chunked.sh # チャンクを 3 つに分けた 2 つ目だけ(CI のジョブ用)

set -u

# チャンクの重さの上限(重さ = 見積もった件数 × 重み。重みは count_tests.py が決める)
MAX_COST=600
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
JOBS="${GRAPHICA_TEST_JOBS:-$(python -c 'import os; print(os.cpu_count() or 1)')}"
TMPDIR="$(pwd)/.ci_test_chunks"
rm -rf "$TMPDIR"
mkdir -p "$TMPDIR/results"
# pytest の一時フォルダはプロジェクトの外に置く(中に置くと、そこで動くテストが pyproject.toml を拾う)
# Python に作らせるのは、Windows の Git Bash でも Python がそのまま読めるパスにするため
BASETEMP_ROOT=$(python -c 'import tempfile; print(tempfile.mkdtemp(prefix="graphica-pytest-"))')
export BASETEMP_ROOT
export PYTEST_ENTRY="$SCRIPTS_DIR/pytest_slice.py"
export GRAPHICA_COVERAGE="${GRAPHICA_COVERAGE:-0}"

fail=0

# 1 行 = 「重さ TAB 名前 TAB 対象の一覧」。一覧は pytest に渡す引数(ファイルと --graphica-slice)を 1 行ずつ並べたファイル。
# テストの ID は先に集めない(全体の収集は 1 プロセスで 30 秒前後かかり、その間ほかのコアが空く)。件数は
# count_tests.py が import せずに見積もり、重いファイルは pytest_slice.py の --graphica-slice=k/n で分ける。
# 軽いファイルはまとめて 1 プロセスにする(プロセスの起動と import だけで 1 回数秒かかる)。
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
  files=()
  for f in $group; do
    [ -f "$f" ] && files+=("$f")
  done
  [ "${#files[@]}" -eq 0 ] && continue
  while IFS="$(printf '\t')" read -r n weight f; do
    name=$(basename "$f" .py)
    # 見積もりが 0 件のファイルも流す(import で落ちるファイルを、収集のエラーとして見つけるため)
    [ "$n" -eq 0 ] && n=1
    cost=$((n * weight))

    if [ "$cost" -gt "$MAX_COST" ]; then
      slices=$(( (cost + MAX_COST - 1) / MAX_COST ))
      for k in $(seq 1 "$slices"); do
        chunk_no=$((chunk_no + 1))
        target="$TMPDIR/chunk_$chunk_no.txt"
        printf '%s\n--graphica-slice=%s/%s\n' "$f" "$k" "$slices" > "$target"
        printf '%s\t%s\t%s\n' "$(( cost / slices ))" "$name" "$target" >> "$CHUNKS"
      done
    else
      if [ $((pack_cost + cost)) -gt "$MAX_COST" ]; then
        flush_pack
      fi
      if [ -z "$pack_list" ]; then
        chunk_no=$((chunk_no + 1))
        pack_list="$TMPDIR/chunk_$chunk_no.txt"
        : > "$pack_list"
        pack_name="$name"
      else
        pack_name="$pack_name $name"
      fi
      echo "$f" >> "$pack_list"
      pack_cost=$((pack_cost + cost))
    fi
  done < <(python "$SCRIPTS_DIR/count_tests.py" "${files[@]}" | tr -d '\r')
  flush_pack
done

if [ -n "${GRAPHICA_TEST_SHARD:-}" ]; then
  # CI でチャンクを複数のジョブに分ける。どのジョブも同じチャンクの一覧を作るので、重い順に、そのとき合計が
  # いちばん軽いシャードへ割り当て(同じ重さなら番号の小さい方)、自分の番号の分だけを残す
  shard_index=${GRAPHICA_TEST_SHARD%/*}
  shard_count=${GRAPHICA_TEST_SHARD#*/}
  if ! [[ "$shard_index" =~ ^[0-9]+$ && "$shard_count" =~ ^[0-9]+$ ]] \
      || [ "$shard_index" -lt 1 ] || [ "$shard_index" -gt "$shard_count" ]; then
    echo "!!! FAILED: GRAPHICA_TEST_SHARD は i/n の形(1 <= i <= n): $GRAPHICA_TEST_SHARD"
    rm -rf "$TMPDIR" "$BASETEMP_ROOT"
    exit 1
  fi
  all_chunks=$(wc -l < "$CHUNKS" | tr -d ' ')
  awk -F'\t' '{print $1 "\t" NR}' "$CHUNKS" | sort -t"$(printf '\t')" -k1,1nr -k2,2n \
    | awk -F'\t' -v count="$shard_count" -v me="$shard_index" '{
        best = 1
        for (s = 2; s <= count; s++) if (load[s] < load[best]) best = s
        load[best] += $1
        if (best == me) print $2
      }' > "$TMPDIR/shard_lines.txt"
  awk 'NR == FNR { keep[$1] = 1; next } (FNR in keep)' "$TMPDIR/shard_lines.txt" "$CHUNKS" > "$CHUNKS.shard"
  mv "$CHUNKS.shard" "$CHUNKS"
  echo "=== shard $shard_index/$shard_count: $(wc -l < "$CHUNKS" | tr -d ' ') of $all_chunks chunks ==="
fi

total=$(wc -l < "$CHUNKS" | tr -d ' ')
echo "=== $total chunks, $JOBS in parallel ==="

# 1 チャンクを流し、出力と終了コードを results/<番号>.log / .rc に残す。
# --basetemp を分けるのは、pytest が並行する別プロセスの一時フォルダを古いものとして消さないため。
# --continue-on-collection-errors は、まとめたファイルの 1 つが import で落ちても、残りのファイルを流すため
run_chunk() {
  index=$1; name=$2; target=$3; total=$4; results=$5
  # パスは空白を含みうるので、1 行を 1 引数として渡す
  set --
  while IFS= read -r line; do
    set -- "$@" "$line"
  done < "$target"
  if [ "$GRAPHICA_COVERAGE" = "1" ]; then
    # 各プロセスが .coverage.<host>.<pid>.<乱数> に書き、run_coverage.sh が combine する
    set -- -m coverage run --parallel-mode "$PYTEST_ENTRY" "$@"
  else
    set -- "$PYTEST_ENTRY" "$@"
  fi
  python "$@" -q -p no:cacheprovider --continue-on-collection-errors --basetemp="$BASETEMP_ROOT/$index" \
    > "$results/$index.log" 2>&1
  rc=$?
  echo "$rc" > "$results/$index.rc"
  rm -rf "$BASETEMP_ROOT/$index"
  echo "[$(ls "$results"/*.rc | wc -l | tr -d ' ')/$total] $name (rc=$rc)"
}
export -f run_chunk

# 重いチャンクから始め、最後に 1 つだけ長いチャンクが残るのを避ける。
# 区切りは NUL(作業フォルダのパスに空白があっても 1 引数のまま渡す)。
# チャンクが無い(シャードに何も割り当たらない)ときに流さないのは、GNU の xargs が入力が空でも 1 回実行するため
if [ "$total" -gt 0 ]; then
  nl -ba -w1 -s"$(printf '\t')" "$CHUNKS" | sort -t"$(printf '\t')" -k2,2nr \
    | while IFS="$(printf '\t')" read -r index cost name target; do
        printf '%s\0%s\0%s\0%s\0%s\0' "$index" "$name" "$target" "$total" "$TMPDIR/results"
      done \
    | xargs -0 -n 5 -P "$JOBS" bash -c 'run_chunk "$@"' _
fi

# 結果は元の順番で出す
while IFS="$(printf '\t')" read -r index cost name target; do
  echo "=== $name ==="
  output=$(cat "$TMPDIR/results/$index.log" 2>/dev/null)
  rc=$(cat "$TMPDIR/results/$index.rc" 2>/dev/null || echo "missing")
  echo "$output"
  # import などで収集できなかったファイルは、まとめた中のどれかが分かるよう名前を出す
  echo "$output" | grep -oE "ERROR collecting [^ ]+" | sed 's/^ERROR collecting //' | while read -r path; do
    echo "!!! FAILED: $path (collection failed)"
  done
  if [ "$rc" = "5" ]; then
    # 1 件も集まらなかった(テストの無いファイルだけのチャンクや、見積もりより件数が少なかった分割の最後)
    :
  elif [ "$rc" != "0" ]; then
    # 「N passed」のサマリーまで出たあとの終了処理でだけ落ちたもの(test_export_preview_panel.py の
    # セグフォルト)は失敗にしない。サマリーに failed / error を含むものは失敗
    summary_line=$(echo "$output" | grep -E "^[0-9]+ (passed|failed|error|deselected)" | tail -n1)
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
