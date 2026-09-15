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

# ★ 改善ボード E-3 で 30 -> 150 に引き上げた。
# チャンクを細かく切っていたのは「1プロセスにQt/matplotlibのリソースが溜まり、
# テストが進むほど1件あたりが遅くなる」ためだったが、その蓄積の主因
# (テストが閉じないまま残すウィンドウ)を tests/conftest.py の
# destroy_leftover_windows で断ったので、同じプロセスで多く流しても劣化しない。
# 実測: tests/test_dataset_mixin.py(435件)は 30件×15チャンクで308秒、
# 150件×3チャンクなら237秒。プロセス起動のぶんだけ速くなる。
# ファイル単位の分離自体は残す — tests/test_export_preview_panel.py の
# 「全件パス後に終了処理でセグフォルトする」既知問題があり、1プロセスに
# まとめると以降のテストが道連れになるため。
CHUNK_SIZE=150
TMPDIR="$(pwd)/.ci_test_chunks"
rm -rf "$TMPDIR"
mkdir -p "$TMPDIR"

fail=0

# ★ カバレッジ計測モード。`GRAPHICA_COVERAGE=1 bash scripts/run_tests_chunked.sh`
# で有効になる(既定はオフ。計測すると2〜3割遅くなるので、普段の回帰確認では
# 付けない — リリース前など必要なときだけ)。
# チャンクごとに別プロセスなので、coverage の --parallel-mode で
# `.coverage.<host>.<pid>.<乱数>` を各プロセスが個別に書き、あとから
# `coverage combine` で1つにまとめる。設定(対象範囲・除外行)は
# pyproject.toml の [tool.coverage.*]。
# まとめて報告まで行うには scripts/run_coverage.sh を使うこと。
if [ "${GRAPHICA_COVERAGE:-0}" = "1" ]; then
  PYTEST_CMD=(python -m coverage run --parallel-mode -m pytest)
else
  PYTEST_CMD=(python -m pytest)
fi

# ★ 改善ボード E-3: テストIDの収集は「全体を1プロセスで1回」だけ行う。
# 以前はファイルごとに pytest --collect-only を起動しており、92ファイル×約2.8秒＝
# 約255秒を「テストを1件も実行しないまま」消費していた(1プロセスなら約5秒)。
# 収集はテスト本体を実行しないため、チャンク分割の理由である
# 「1プロセスへのQt/matplotlibリソース蓄積」はここでは起こらない。
ALL_IDS="$TMPDIR/all_ids.txt"
python -m pytest tests/ --collect-only -q 2>/dev/null | grep "::" > "$ALL_IDS" || true

for f in tests/test_*.py; do
  name=$(basename "$f" .py)
  ids_file="$TMPDIR/${name}_ids.txt"
  # "tests/foo.py::" で始まる行だけを抜く。末尾の ".py::" があるので
  # test_dataset.py と test_dataset_mixin.py を取り違えることはない。
  grep -F "$f::" "$ALL_IDS" > "$ids_file" || true
  n=$(wc -l < "$ids_file")

  if [ "$n" -eq 0 ]; then
    # まとめての収集がそのファイルを落とした可能性(import エラー等で
    # 1ファイルだけ収集できなかった場合)があるので、単体で収集し直してから
    # 「テスト0件」と判断する。ここに落ちるのは異常時だけなので遅くてよい。
    python -m pytest "$f" --collect-only -q 2>/dev/null | grep "::" > "$ids_file" || true
    n=$(wc -l < "$ids_file")
  fi

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
    echo "=== $name :: $c ==="
    if [ "$c" == "$f" ]; then
      output=$("${PYTEST_CMD[@]}" "$f" -q 2>&1)
    else
      # ★ バグ修正: 以前は target=$(cat "$c") で複数行のテストID一覧を1つの
      # シェル変数に読み込み、pytest呼び出し時にクォートせず渡していた
      # (python -m pytest $target -q)。これはテストIDが空白を含まない前提で
      # しか動かず、パラメータ化テストのID(例: "ローレンツ関数 (y = a / (1 +
      # ((x-b)/c)^2) + d)-expected_names0" のように空白・括弧を含むもの)が
      # シェルの単語分割(IFS)でバラバラの引数に分解されてしまい、
      # 「file or directory not found: (y」のような分かりにくいエラーで
      # チャンク全体が失敗扱いになっていた(実際にこのセッションで発生した)。
      # 1行=配列の1要素として読み込み、"${array[@]}"で渡すことで、
      # 各テストID内の空白を保ったまま個別の引数として扱う。
      # ★ bash 3.2(macOSがGPLv3回避のため標準搭載しているバージョン)には
      # mapfile/readarrayが無い(bash 4.0以降の機能)ため、代わりにこの
      # while readループを使う(bash 3.2/4+のどちらでも動く)。
      target_ids=()
      while IFS= read -r line; do
        target_ids+=("$line")
      done < "$c"
      output=$("${PYTEST_CMD[@]}" "${target_ids[@]}" -q 2>&1)
    fi
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
