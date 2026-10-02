# テスト高速化の計画(2026-10-02 調査)

テスト一式と CI の待ち時間をさらに縮めるための計画。調査はクラウドのセッションで行い、実装はローカルで進める。
ここに書いた数字は 2026-10-02 の master(6409e8c 前後)での実測。

## 1. 今どこに時間がかかっているか

### CI(PR のとき)

| ジョブ | 全体 | 内訳 |
|---|---|---|
| test-windows | 約13.7分(**律速**) | 依存のインストール 80秒、lint+mypy 10秒、テストの収集 34秒、テスト 11.3分 |
| test-macos | 約7分 | 依存のインストール 47秒、テスト 6.2分(特性テストは飛ばされる) |
| install-check ×2 | 約1.5分 | |

Windows のテストは、42 チャンクの pytest の時間を足すと **2,604秒**で、それを4並列で流して約11分になっている。
並列の効率はすでに良いので、縮めるには作業量を減らすか、ジョブを分けて同時に流すしかない。

- 特性テスト(`tests/characterization/`、Windows でだけ比べる): **約718秒(28%)**
- それ以外: 約1,886秒

### 手元(Linux、4コア)

`scripts/run_tests_chunked.sh` の写しに `--junitxml` を足して、全 3,591 件を1件ずつ計測した(合計 1,370秒)。

| 種類 | 件数 | 合計 |
|---|---|---|
| ウィンドウ(`PlotterApp` / `MainAppWindow`)を作るファイルのテスト | 約1,610 | **約1,290秒(95%)** |
| それ以外 | 約1,690 | 約66秒 |

**時間のほぼすべては、ウィンドウを作るテスト**。ファイル別の上位は次のとおり。

| ファイル | 件数 | 合計 | 1件あたり |
|---|---|---|---|
| test_dataset_mixin.py | 422 | 435秒 | 1.03秒 |
| test_main_window.py | 175 | 130秒 | 0.74秒 |
| test_export_mixin.py | 61 | 66秒 | 1.08秒 |
| test_property_sections.py | 59 | 49秒 | 0.84秒 |
| test_cursor_mixin.py | 41 | 39秒 | 0.95秒 |
| test_mouse_modes.py | 50 | 35秒 | 0.70秒 |

### ウィンドウ1つの組み立て(手元で約0.5秒)

`PlotterApp(run_startup_checks=False, tab_id=2)` の各段の時間(8回の平均)。

| 段 | 時間 |
|---|---|
| `_arrange_property_docks` | 約180ms(ドックの中身を付け替えるたびに、スタイルが全部の部品に当て直される) |
| `_connect_and_initialize` | 約150ms(最初の描画と tight_layout) |
| そのほか全部 | 約140ms |
| 組み立て後の `processEvents()` ×5 | 約40ms |
| 破棄 | 約20ms |

ドックの組み立て順を入れ替える実験もしたが、縮んだのは約6%(約30ms)だけで、部品の木の状態も1か所変わった。
アプリの動きを変える危険に見合わないので、この計画には入れない。

## 2. やること(この順で進める)

効果の見込みは、Windows の CI での値。

### A. CI のテストを複数のジョブに分けて同時に流す(一番効く。テストは1件も減らない)

リポジトリは公開なので、Actions の標準ランナーは無料で、ジョブを増やしても費用はかからない。

- `scripts/run_tests_chunked.sh` に `GRAPHICA_TEST_SHARD=i/n` を足す。チャンクを作ったあと、重さの大きい順に、そのとき合計がいちばん軽いシャードへ割り当てる(LPT)。自分の番号のチャンクだけを流す。未指定なら今までどおり全部を流す。
- `build.yml` の test-windows を `strategy.matrix.shard: [1, 2, 3]` にする。lint と mypy は shard 1 だけで流す。
- test-macos は、PR のときだけ2つに分ける。master のカバレッジ計測は1ジョブのままにする(計測結果をジョブをまたいで結合する手間を省くため。master は PR の待ち時間に関係しない)。
- **注意**: ジョブ名が `test-windows` から `test-windows (1)` などに変わる。ブランチ保護の「必須のチェック」に `test-windows` / `test-macos` を登録している場合は、ユーザーが設定を直す必要がある。直さないと PR がマージできなくなるので、着手前に確認する。
- 見込み: Windows は約13.7分 → **約5〜6分**(準備に約1.5分、テストに約3.5〜4分)。macOS は約7分 → 約4分。

### B. pip のキャッシュ

- `actions/setup-python` に `cache: pip` と `cache-dependency-path: Graphica_project/requirements.txt` を足す(test-windows・test-macos。install-check は wheel を作るので別に検討)。
- 見込み: 1ジョブあたり約30〜50秒。

### C. テスト前の収集をやめる(Windows で34秒、その間は3コアが空いている)

今は、重いファイルをテスト ID で分けるために、最初に1プロセスで全体を `--collect-only` している。

- 案: `tests/conftest.py` に `--graphica-slice=k/n` を足し、`pytest_collection_modifyitems` で「そのファイルの k 番目の 1/n」だけを残す。ランナーは、ファイルの重さを `def test_` の数などで見積もり、重いファイルを「ファイル名 + `--graphica-slice`」で分ける。そうすれば ID が要らない。
  - パラメータ化の件数は見積もりからずれる(例: `test_mouse_modes.py` の42通り)。分け方の釣り合いが少し崩れるだけなので、困らない。
  - 収集の失敗は、各チャンクの pytest が `errors` として出す。今の「集められなかったファイルを失敗にする」判定(`test_suite_hygiene.py` が確かめている)は、この形に合わせて直す。
  - 1つのチャンクに1件も残らないと、pytest が rc=5 を返す。これは失敗にしない。
- 見込み: Windows で約30秒。シャードに分けたあとは、ジョブごとに効く。

### D. ガベージコレクションの対象から、読み込み済みのライブラリを外す

ウィンドウのテストでは、Python の不要メモリの回収が1件あたり約60ms(約8%)を使っていた。
読み込み済みの大量のオブジェクト(pandas・scipy・matplotlib・PySide6)を、回収のたびに走査しているため。

- `tests/conftest.py` で、重い import のあと(QApplication の fixture を作る前後)に `gc.collect(); gc.freeze()` を1回呼ぶ。
- 実測(ウィンドウを作ってデータセットを1つ足し、描いて閉じる): 1件 約850〜890ms → 約780〜800ms。回収の時間は約60ms → 約22ms。
- `gc.set_threshold` も上げると、回収の時間はさらに約10msまで下がった。ただし、全体の時間は freeze だけのときと差が無かったので、freeze だけでよい。
- 見込み: テスト全体の約7〜8%(Windows で約200秒、4並列で約50秒)。
- 確認: `tests/test_suite_hygiene.py` のウィンドウ破棄のテストが通ること。メモリの使用量が増えないこと。freeze した後に作られたオブジェクトは、今までどおり回収される。

### E. 重複しているマウスモードの排他テストを消す(30件)

`tests/test_mouse_modes.py::test_activating_a_mode_deactivates_every_other_mode` は、7モードの全42通りの順序対で次のことを確かめている。

- 後から入れたモードが有効になる
- 先のモードのフラグが False になる
- 先のモードのツールバーのボタンのチェックが外れる
- 有効なモードが後のモードになる

次の各ファイルのテストは、そのどれか1通りを、フラグを直接立てる形で確かめているだけで、上のテストに含まれる。

- `test_cursor_mixin.py`: `test_toggle_cursor_mode_on_turns_off_annotation_mode_first`
- `test_peak_placement_mixin.py`: `test_toggle_*_mode_on_turns_off_*` の8件
- `test_range_select_mixin.py`: 同じ形の6件
- `test_region_highlight_mixin.py`: 同じ形の3件と、`test_toggle_other_modes_on_turn_off_region_highlight_mode`(ウィンドウを6つ作る。1件4.4秒)
- `test_slice_extraction_mixin.py`: 同じ形の10件

`test_annotation_mixin.py::test_toggle_annotation_mode_on_turns_off_cursor_mode_first` だけは、ほかにも確かめていることがある。注釈モードを入れたときにイベントの接続(`_annotation_press_cid` / `_annotation_release_cid`)ができることと、ステータスバーに案内が出ることだ。

- この3つの確認が、注釈モードを入れるほかのテストに無ければ、カーソルモードを先に入れる部分を外した「注釈モードを入れる」テストとして残す。
- 消す前に、1件ずつ確かめることが3つある。
  - 確認内容が全42通りのテストに含まれていること。
  - その組み合わせが MOUSE_MODES に入っていること。
  - 消したあと、`pytest tests/test_mouse_modes.py tests/test_*_mixin.py` が通ること。
- 見込み: 手元で約22秒、Windows で約35秒。

### F. 全42通りのテストを、7件にまとめる(作るウィンドウを42 → 7)

- 「最初に入れるモード」だけでパラメータ化し(7件)、1つのウィンドウの中で、残り6モードを順に確かめる。
  - 各組み合わせの前に、全モードを `_toggle_*_mode(False)` とボタンのチェック外しで解除する。
  - 失敗したときに組み合わせが分かるよう、assert のメッセージに `first` と `second` を入れる。
- 確かめる内容は今と同じにする。「全42通り」という数は、テスト名と docstring で分かるようにしておく(CLAUDE.md が「42 ordered pairs」と書いている)。
- 見込み: 手元で約25秒、Windows で約45秒。

### G. 列の値で分割するテストの閾値を、テストの中で下げる

- `tests/test_split_by_column.py` の2件(337行目と356行目のあたり)は、`SPLIT_BY_COLUMN_CONFIRM_THRESHOLD + 5` = 35グループに分けている。そのうち `test_many_groups_proceeds_when_confirmed` は**1件で約14秒**かかる(データセットを1つ足すたびに全体を描き直すため。アプリ側の問題は Issue #90)。
- `monkeypatch.setattr(processing_module, "SPLIT_BY_COLUMN_CONFIRM_THRESHOLD", 3)` にして、8グループで同じことを確かめる。`tests/test_canvas.py` の `small_lttb` と同じ考え方。
- 見込み: 手元で約12秒、Windows で約20秒。Issue #90 を直せば、このテストはどのみち速くなる。

### H. 中身がまったく同じテスト(2組)

- `test_dataset_mixin.py` の `test_dataset_tree_context_menu_omits_global_visibility_actions_when_project_empty` と `test_context_menu_no_selection_shows_only_new_folder`
- `test_canvas.py` の `test_axis_label_shown_by_default` と `test_axis_label_visible_defaults_to_true_for_legacy_settings`

どちらも1件1秒未満なので、効果は小さい。名前が表す意図が違う(後者は「古い設定を読んだとき」)。片方を消すのではなく、意図どおりの中身になっているかを見直す。

## 3. やらないこと(理由つき)

- **ウィンドウを複数のテストで使い回す**(特に test_dataset_mixin.py の422件。Windows の時間の約23%)。
  - 効果は一番大きい。ただ、テストどうしが状態(データセット、Undo、軸の設定、マウスモード、ドック、言語、テーマ)を持ち越して、見落としや誤検知が起きる危険が大きい。
  - A〜G で十分速くなるので、見送る。どうしても必要になったら、ファイルを限って別に検討する。
- **ウィンドウの組み立てそのものを速くする**(ドックの組み立て順の変更など)。上に書いたとおり効果が小さく、アプリの動きを変える危険がある。
- **特性テストを PR で流さない**。内部の作り替えで動きが変わっていないことを確かめる唯一の網なので、残す。A でシャードに分ければ、待ち時間への影響は小さくなる。

## 4. 進め方と確認

1. 着手前に、今の時間を手元で測る(`bash scripts/run_tests_chunked.sh` の所要時間と、`=== N chunks` の行)。
2. D・E・F・G・H(テストと conftest)→ C(ランナー)→ A・B(CI)の順に進める。区切りごとに、関係するファイルのテストを流す。
3. conftest とランナーに触れるので、最後に**テスト一式**を流す(`bash scripts/run_tests_chunked.sh`)。`ruff check .` と `mypy` も流す。
4. PR を出し、CI の各ジョブの時間を前と比べる。シャードごとの時間の偏りも見る(偏っていたら、割り当てか MAX_COST を調整する)。
5. CLAUDE.md の次の箇所を、変わった内容に合わせて直す。
   - 「Full-suite execution and progress reporting」と「Why the suite used to be twice as slow」
   - CI の説明
   - `test_mouse_modes.py` が「all 42 ordered pairs」を確かめているという記述
6. CURRENT_STATE.md を更新する。

## 5. 計測のしかた(同じ条件で前後を比べるため)

- 1件ずつの時間: `scripts/run_tests_chunked.sh` を写し、pytest の行に `--junitxml="$results/$index.xml" -o junit_family=xunit1` を足す。結果フォルダ(`$TMPDIR`)を消さないようにして流し、XML の `testcase` の `time` を集計する。
- ウィンドウ1つの組み立て: `PlotterApp` の `_build_*` などの各段を、時間を測る関数で包んで8回作る。設定は一時 INI に向ける(`app_settings.QSettings` を差し替える)。
- CI: ジョブのログには、チャンクごとに `N passed ... in X s` が出る。これを足すと、そのジョブの作業量の合計になる。
