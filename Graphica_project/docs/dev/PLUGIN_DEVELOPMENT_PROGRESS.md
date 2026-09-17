# トラック4(プラグイン本体の開発) 進捗管理

`Graphica_MASTER_SCHEDULE.md` のトラック4(プラグイン本体の開発)の進捗を記録する。
このファイルは各項目の「どう実装したか」の詳細ログ。**「今どこまで進んでいて次に何を
やるか」の短い要約は`CURRENT_STATE.md`を先に見ること**(新しいセッションはまず
`CURRENT_STATE.md`を読む運用)。このファイルは項目が完了するたびに追記していく
(上書きしない)。トラック1は`PLUGIN_API_PROGRESS.md`、トラック2は
`GUI_MODERNIZATION_PROGRESS.md`、トラック3は`CORE_FEATURES_PROGRESS.md`が
同じ役割を持つ(対象トラックが異なるだけ)。

`docs/dev/Graphica_PLUGIN_BACKLOG.md`の「着手推奨プラグイン Top 8」(P-805→P-101→
P-304→...)の順に着手する。

## ★ 開発の場所: プラグインは種類ごとに別リポジトリ(2026-09-13、ユーザー判断)

**プラグインは本体リポジトリの`plugins/`ではなく、種類ごとに独立した
GitHubリポジトリで開発する。** 命名は`graphica-plugin-<name>`。

本体リポジトリの`plugins/`に残すのは`example_plugin`(APIの使い方を示す
同梱サンプル)だけ。理由は2つ:

- `gui/main_window.py`の`plugin_search_paths()`は`if not is_frozen()`のときだけ
  `resource_path("plugins")`を探索するため、**本体に同梱してもexe利用者には
  届かない**。どのみち配布はzipになる。
- プラグインごとにリリースサイクル・Issue・バージョンを分けられる。

**各プラグインリポジトリの構成**(`graphica-plugin-element-constants`が雛形):

```
<plugin_name>/            ← プラグイン本体(このフォルダ名がプラグイン名になる)
  __init__.py             ← register(api)
  plugin.json             ← name / version / api_version
tests/
  conftest.py             ← QApplicationフィクスチャ + requires_graphica マーカー
scripts/build_zip.py      ← 配布用zipのビルド
README.md / .gitignore / requirements-dev.txt
```

**テストの走らせ方**: 本体は`pip install -e <PlotterApp>/Graphica_project`で
editable install する(`pyproject.toml`があり`core`/`gui`/`models`を
トップレベルパッケージとして公開しているのでそのまま入る)。本体が無い環境でも
データ処理など本体非依存のテストだけは走るよう、`conftest.py`の
`requires_graphica`マーカーで分岐させる。

**プラグイン同士はimportできない**: `PluginManager._load_module()`が
`graphica_plugin_<name>`という動的モジュール名で読み込むため、
`element_constants.data`のような絶対パスは本番環境では解決しない。
他プラグインのモジュールを再利用したい場合はコピーして同梱すること。

(旧: `feature/plugin-track4`ブランチ+`git worktree`で本体リポジトリ内の
`plugins/`に置く運用。このブランチにはP-101のパーサがWIPで残っているだけ。)

## トラック4: プラグイン開発

| ID | プラグイン | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| P-805 | 元素・物理定数テーブル | ✅ 完了(別リポジトリ) | 2026-08-15 | `plugins/element_constants/`を新設。データ本体(`data.py`)はGUI/plugin機構いずれにも非依存のプレーンなPythonモジュールとして分離し、「他パックの共通基盤」という位置づけ通り単体テストしやすくした(ただし後述の通り、他プラグインからの直接importでの再利用にはimportlib越しの相対import制約がある)。周期表データ(原子番号/元素記号/英語名/原子量、118元素)はmendeleev/periodictable等の外部パッケージがGraphica同梱パッケージ(numpy/pandas/scipy/matplotlib/PySide6/openpyxl)に含まれておらず追加もできない(プラグインの`requires`規約は同梱パッケージのみ許可)ため自前で同梱、物理定数は`scipy.constants.physical_constants`(CODATA値、同梱済み)をそのまま再利用し値を手で転記していない。UIは現在選択中のデータセットを一切必要としない参照ツールという性質上、`register_analyzer`(Dataset必須)ではなく`register_panel`(項目D-1)で常設ドックパネルとして提供(`ElementConstantsPanel`、検索モード切替+検索欄+結果テーブル)。**実装中に判明した設計上の注意点**: `core/plugin_api.py`の`PluginManager._load_module()`は各プラグインを`graphica_plugin_<name>`という動的モジュール名でimportし、`plugins.<name>`という「本物の」パッケージパスとしては存在しない(ソース実行/PyInstallerフリーズ/ユーザープラグインディレクトリのいずれでも`sys.path`の状態に依存しない安定した参照方法が必要)。そのため同一プラグイン内の他モジュール参照は`from plugins.element_constants.data import ...`のような絶対importではなく、`spec_from_file_location(submodule_search_locations=...)`が提供する相対import(`from .data import ...`)を使う必要がある(最初の実装で絶対importを使い、実際の読み込み経路でのみ失敗する不具合を作りかけたため、`tests/test_element_constants_plugin.py`に`tmp_path`ではなく実際の`plugins/`ディレクトリをそのまま`PluginManager`に渡すスモークテストを追加し、この種の「tmp_pathベースのテストでは検出できない本番経路限定の不具合」を機械的に検出できるようにした)。**2026-09-13、別リポジトリ https://github.com/STsuruga/graphica-plugin-element-constants へ移設**(上記「開発の場所」節のユーザー判断による)。本体リポジトリの`plugins/element_constants/`と`tests/test_element_constants_plugin.py`は削除済み。 |

## 次にやること

**★ 2026-09-17: プラグインは1件ずつ別チャット・別リポジトリで開発する運用を開始(ユーザー判断)。**

共通の資料と進捗は **プラグイン開発ハブ(Artifact)** にまとめた:
https://claude.ai/artifact/GZ3LTLJjbxj1LQsAhZFg2o

- 全件の状態は、このファイルではなく**ハブのデータベース**(collection `plugins`、
  doc_id = `P-xxx`、フィールド `state` / `repo` / `version` / `release_url` / `note` /
  `updated`)が正。各プラグインのチャットが着手時・完了時に更新する。
- ハブの各項目に、そのまま新しいチャットへ貼る「引継ぎプロンプト」がある。
- ハブのページ本体は `docs/dev/plugin_hub.html`。仕様や説明を直すときはこのファイルを
  編集して同じ URL に再公開する(状態はデータベース側なので消えない)。
- 共通ルール・API 早見表はハブにある(`docs/plugin_development.md` の誤った例は
  2026-09-17 に修正済み: `Dataset` の必須引数、annotations の形、同梱依存の xlrd、
  `register_render_backend` が未接続であること)。

着手順(ハブの「着手順」と同じ): P-402(統計検定、改善ボード D-3)→ P-101(JCAMP-DX)→
P-304(UV-Vis)→ P-202(スパイク除去)→ P-306(CV)→ P-201(Shirley/Tougaard)→
P-401(PCA)→ P-303(Raman/FT-IR)。

P-101 のパーサ(`plugins/jcamp_dx_importer/parser.py`、221行、未検証)は
`feature/plugin-track4` ブランチの WIP コミット `e6f5a7e` にある。新しいリポジトリへ
移したあと、ブランチと worktree を消すかはユーザー判断。

プラグインが完了したら、ハブの更新に加えて上の表にも1行追記する(本体リポジトリへの
書き込みはこの記録だけ。プラグインのチャットは本体のコードを変更しない)。
