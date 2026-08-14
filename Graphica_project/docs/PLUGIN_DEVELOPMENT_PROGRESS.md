# トラック4(プラグイン本体の開発) 進捗管理

`Graphica_MASTER_SCHEDULE.md` のトラック4(プラグイン本体の開発)の進捗を記録する。
このファイルは各項目の「どう実装したか」の詳細ログ。**「今どこまで進んでいて次に何を
やるか」の短い要約は`CURRENT_STATE.md`を先に見ること**(新しいセッションはまず
`CURRENT_STATE.md`を読む運用)。このファイルは項目が完了するたびに追記していく
(上書きしない)。トラック1は`PLUGIN_API_PROGRESS.md`、トラック2は
`GUI_MODERNIZATION_PROGRESS.md`、トラック3は`CORE_FEATURES_PROGRESS.md`が
同じ役割を持つ(対象トラックが異なるだけ)。

`docs/Graphica_PLUGIN_BACKLOG.md`の「着手推奨プラグイン Top 8」(P-805→P-101→
P-304→...)の順に着手する。作業ブランチは`git worktree`で別ディレクトリを切った
`feature/plugin-track4`(masterから分岐。本体側で並行するトラック3-4
(C-003/C-004)とはファイルが重ならないため、真に並行して進められる)。

## トラック4: プラグイン開発

| ID | プラグイン | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| P-805 | 元素・物理定数テーブル | ✅ 完了 | 2026-08-15 | `plugins/element_constants/`を新設。データ本体(`data.py`)はGUI/plugin機構いずれにも非依存のプレーンなPythonモジュールとして分離し、「他パックの共通基盤」という位置づけ通り単体テストしやすくした(ただし後述の通り、他プラグインからの直接importでの再利用にはimportlib越しの相対import制約がある)。周期表データ(原子番号/元素記号/英語名/原子量、118元素)はmendeleev/periodictable等の外部パッケージがGraphica同梱パッケージ(numpy/pandas/scipy/matplotlib/PySide6/openpyxl)に含まれておらず追加もできない(プラグインの`requires`規約は同梱パッケージのみ許可)ため自前で同梱、物理定数は`scipy.constants.physical_constants`(CODATA値、同梱済み)をそのまま再利用し値を手で転記していない。UIは現在選択中のデータセットを一切必要としない参照ツールという性質上、`register_analyzer`(Dataset必須)ではなく`register_panel`(項目D-1)で常設ドックパネルとして提供(`ElementConstantsPanel`、検索モード切替+検索欄+結果テーブル)。**実装中に判明した設計上の注意点**: `core/plugin_api.py`の`PluginManager._load_module()`は各プラグインを`graphica_plugin_<name>`という動的モジュール名でimportし、`plugins.<name>`という「本物の」パッケージパスとしては存在しない(ソース実行/PyInstallerフリーズ/ユーザープラグインディレクトリのいずれでも`sys.path`の状態に依存しない安定した参照方法が必要)。そのため同一プラグイン内の他モジュール参照は`from plugins.element_constants.data import ...`のような絶対importではなく、`spec_from_file_location(submodule_search_locations=...)`が提供する相対import(`from .data import ...`)を使う必要がある(最初の実装で絶対importを使い、実際の読み込み経路でのみ失敗する不具合を作りかけたため、`tests/test_element_constants_plugin.py`に`tmp_path`ではなく実際の`plugins/`ディレクトリをそのまま`PluginManager`に渡すスモークテストを追加し、この種の「tmp_pathベースのテストでは検出できない本番経路限定の不具合」を機械的に検出できるようにした) |

## 次にやること

`Graphica_PLUGIN_BACKLOG.md`の「着手推奨プラグイン Top 8」の2番目、P-101
(JCAMP-DXインポータ、`register_importer`)に進む。3番目のP-304(UV-Visパック、
`register_analyzer`)まで実装すると、`register_importer`/`register_analyzer`/
`register_panel`の3フックがプラグイン開発の実用に耐えるかの検証も兼ねる
(`Graphica_PLUGIN_BACKLOG.md`自身の位置づけ通り)。
