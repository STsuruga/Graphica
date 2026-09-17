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

**★ プラグイン開発自体が後回し(2026-09-13、ユーザー判断)。**
土台(別リポジトリ方針・zipビルド・テストの走らせ方)は整ったので、
再開したいときはこのファイルの「開発の場所」節から読めばすぐ始められる。
**このセクションの内容は「再開したときの着手順」であって、いま進行中の
作業ではない。**

再開時の1番目は、改善ボード D-3 の **P-402(統計検定と有意差ブラケット)**
(ユーザー判断でコア機能への昇格はせず、プラグインとして作る方針が確定済み)。
`graphica-plugin-stats`(仮)として新しいリポジトリを切る。

その後は`Graphica_PLUGIN_BACKLOG.md`の「着手推奨プラグイン Top 8」に戻り、
P-101(JCAMP-DXインポータ、`register_importer`)→ P-304(UV-Visパック、
`register_analyzer`)と進む。この3つで`register_importer`/`register_analyzer`/
`register_panel`の3フックが実用に耐えるかの検証も兼ねる
(`Graphica_PLUGIN_BACKLOG.md`自身の位置づけ通り)。

P-101のパーサ(`plugins/jcamp_dx_importer/parser.py`、221行)は
`feature/plugin-track4`ブランチにWIPコミット`e6f5a7e`として退避してある。
着手時はそこから取り出して新しいリポジトリへ移すこと。
