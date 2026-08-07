# プラグインAPI拡張 進捗管理

`Graphica_MASTER_SCHEDULE.md` のトラック0(着手前提条件)〜トラック4の進捗を記録する。
このファイルは各項目の「どう実装したか」の詳細ログ。**「今どこまで進んでいて次に何を
やるか」の短い要約は`CURRENT_STATE.md`を先に見ること**(新しいセッションはまず
`CURRENT_STATE.md`を読む運用)。このファイルは項目が完了するたびに追記していく
(上書きしない)。

## トラック0: 着手前提条件(必須・最優先)

`Graphica_ROADMAP_PLUGIN_AND_GUI.md` フェーズA〜Gの着手前に、以下4項目が全てマージ済みであることが条件。

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| C-001 | `.graphica` に `format_version` + migrationチェーンの追加 | ✅ 完了 | 2026-08-05 | `models/project.py`: `CURRENT_FORMAT_VERSION`定数 + `_migrate_project_data()`による移行チェーン。未バージョンファイルはversion 0として扱い、より新しいバージョンのファイルは明示的にエラー拒否する設計 |
| C-008 | 安全な数式評価器(`eval`/`exec`の排除) | ✅ 完了 | 2026-08-05 | `core/safe_eval.py`を新設し、AST制限評価器(eval/exec不使用)に統一。`core/analysis.py`(カーブフィットのカスタム数式)・`gui/data_editor.py`・`gui/mixins/dataset_mixin.py`(列計算、旧`pandas.eval(engine='python')`)の3箇所で使用していた`eval()`/`df.eval()`を全て置き換え。属性アクセスはカーブフィット用途では一切禁止、列計算用途のみ許可リスト化した`pandas.Series`/`Rolling`メソッド(`mean`/`rolling`/`cumsum`等)に限定。比較・論理演算子(`>`, `==`, `and`/`or`/`not`)もCalcHelpDialogの案内文言に合わせて要素ごとの`&`/`\|`/`~`として対応 |
| C-009 | `logging`基盤 + 出力先の統一 | ✅ 完了 | 2026-08-05 | `core/app_paths.py`を新設し`get_app_data_dir()`で`%LOCALAPPDATA%\Graphica`を解決(cwd非依存)。`main.py`の`_setup_logging()`と`gui/crash_handler.py`のログパス解決を、従来の`os.path.abspath(".")`(カレントディレクトリ依存、Program Files配下だと書込失敗しうる)から差し替え |
| C-1205 | 後方互換コーパス + シリアライズのラウンドトリップ検証 | ✅ 完了 | 2026-08-05 | `tests/fixtures/legacy_projects/`に静的な後方互換コーパス(v0の`.graphica`未指定ファイル、Dataset任意フィールド欠落、フォルダ機能追加前の`.pkl`、現実的な複数データセットプロジェクト)を追加。`_generate_corpus.py`で生成方法を文書化。`tests/test_backward_compat_corpus.py`で読込・デフォルト補完・再保存後の安定した固定点への到達(ラウンドトリップ安定性)を検証 |

**トラック0完了条件**: 上記4項目全てが✅になること。**達成(2026-08-05)**。トラック1(プラグインAPI拡張)への着手条件を満たした。

**推奨(必須ではないが先にあると楽になる)**

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| C-006 | `AppContext` 導入 | ✅ 完了 | 2026-08-05 | `gui/app_context.py`を新設。QSettings・最近使ったファイル・プラグインレジストリ(`load_plugins_once`)を集約し、`active_plotter_app`/`active_project`/`active_undo_stack`はアクセス時点でMainAppWindowの現在タブから都度取得(プラグインコールバックが古いタブを握り続ける既知の罠を回避)。`MainAppWindow.__init__`が1つ生成・保持(`self.app_context`)。既存の「PlotterApp/各Mixinの実装には一切手を加えない」というMainAppWindowの設計方針を踏襲し、`PlotterApp`自体は無改修 |
| C-002 | `visible_df` キャッシュ | ✅ 完了 | 2026-08-05 | `core/dataset.py`の`Dataset`に`__setattr__`フックとversion番号ベースのキャッシュを追加。`df`/`masked_row_indices`の再代入は自動検知して無効化、`set_cell`等のインプレース変更は`invalidate_visible_df_cache()`を明示呼び出し。列計算(C-008で追加した外部からのインプレース変更含む)も同様に対応済み |

## トラック0': クイックウィン(トラック0と並行、いつでも着手可)

**全9項目完了(2026-08-05)。**

| ID | 項目 | 状態 | 備考 |
|---|---|---|---|
| C-801 | PDFフォント埋め込み | ✅ 完了 | `gui/mixins/export_mixin.py`: PDF保存時に`mpl.rc_context({'pdf.fonttype': 42, 'ps.fonttype': 42})`を適用(単発エクスポート・バッチエクスポート両方)。TrueType埋め込みでベクター編集ソフトでもテキストを選択・編集可能に |
| C-301/302 | Savitzky-Golay平滑化 + 微分スペクトル | ✅ 完了 | `core/analysis.py`に`calculate_savgol()`追加(deriv=0/1/2)。`gui/dialogs.py`の`SavGolDialog` + `dataset_mixin.py`の`_on_savgol_dataset`(規格化と同じ「カレント1件→新規データセット」パターン) |
| C-402 | 重み付きフィット | ✅ 完了 | `core/analysis.py`の`calculate_curve_fit()`に`sigma`引数追加(`scipy.optimize.curve_fit`にabsolute_sigma=Trueで渡す)。`FitDialog`に「Y誤差列を重みとして使用する」チェックボックス |
| C-404 | フィット範囲の指定 | ✅ 完了 | `calculate_curve_fit()`に`x_range`引数追加(範囲外の点はp0推定にも一切使わない)。`FitDialog`にフィット範囲指定欄。C-402と同じダイアログ・同じコミットで実施(UI共有のため) |
| C-502 | 誤差バンド | ✅ 完了 | `Dataset.error_display`フィールド('bar'/'band'/'both')追加。`gui/canvas.py`で`error_display in ('band','both')`時に`fill_between`で誤差帯を描画。UIは`formLayout_4`に「誤差の表示形式」コンボボックス追加 |
| C-805 | カラーマップ自動配色 | ✅ 完了 | 既存の離散パレット自動配色(`_on_auto_assign_colors`)とは別に、`_on_auto_assign_colors_from_colormap`を追加。連続カラーマップ(viridis等)から選択数ぶんを均等サンプリング。オーバーフローメニューに追加 |
| C-901 / C-007 | Undo履歴パネル + QUndoGroup | ✅ 完了 | `gui/main_app_window.py`に`QUndoGroup`を新設し、各タブの`undo_stack`(PlotterApp側は無改修)を`addStack`/`removeStack`で登録・タブ切替時に`setActiveStack`で追従。`QUndoView`をドックパネル化し、タブ横断で常にアクティブなタブの履歴を表示(既定は非表示、タブバー右上「履歴」ボタンで表示切替) |
| C-1201 | 診断情報バンドル出力 | ✅ 完了 | `core/diagnostics.py`の`build_diagnostic_bundle()`(ログ・環境情報・設定値・プラグイン読込状況をzip化、core/はPySide6非依存)。ヘルプメニューに「診断情報をエクスポート...」 |
| C-712 | パネルラベル自動採番 | ✅ 完了 | `ProjectModel.panel_labels_enabled`(プロジェクトごとの状態、保存/読込対応)。`gui/canvas.py`の`redraw_all()`に`panel_labels_enabled`引数追加、`_panel_label_for_index()`でExcel列名方式の(a)(b)...(aa)(ab)...を機械的に計算。表示メニューにトグル |

## トラック1: プラグインAPI拡張(フェーズA〜G)

### フェーズA: 土台

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| A-1 | `PluginContext`/登録結果の型定義 | ✅ 完了 | 2026-08-05 | `core/plugin_types.py`新設(`PluginHookKind` Enum、`PluginRegistrationError` dataclass)。既存の`register_fit_function`/`register_menu_action`は外部から見た挙動を変えずに内部でこれらの型を使うようリファクタ |
| A-2 | フック登録失敗の隔離を共通化 | ✅ 完了 | 2026-08-05 | `GraphicaPluginAPI._safe_register()`で各`register_xxx`をラップし、`self._registration_errors`に記録。従来はプラグイン単位(register()全体)でしか隔離していなかったが、フック単位に細分化(1つのフックが失敗しても同じプラグインの他のフックは登録され続ける)。`PluginManager.load_all()`が`api._current_plugin_name`を差し替えてどのプラグインの呼び出しか伝える。`core/diagnostics.py`(C-1201)の`plugins.txt`にもフック単位の失敗を追記 |
| A-3 | プラグイン開発者向けテストダブル | ✅ 完了 | 2026-08-05 | `core/plugin_testing.py`新設。`FakeGraphicaPluginAPI`(本体非起動でプラグインのregister()呼び出しを単体テスト可能に)。フックメソッドは現時点で`register_fit_function`/`register_menu_action`のみ(B/C/Dで随時追加) |
| A-4 | シグネチャ契約テスト | ✅ 完了 | 2026-08-05 | `tests/test_plugin_api_contract.py`。`FakeGraphicaPluginAPI`と本物`GraphicaPluginAPI`の`register_*`メソッドの引数名・デフォルト値が一致することを`inspect`で機械的に検証。以降のフェーズで新しいフックを追加した際、片方だけの実装漏れを検知する |

**フェーズA完了条件**: 上記4項目が✅。**達成(2026-08-05)**。フェーズB(データ入出力フック)に着手可能。

### フェーズB: データ入出力フック

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| B-1 | `register_importer()` | ✅ 完了 | 2026-08-05 | `GraphicaPluginAPI.register_importer(extensions, loader, *, name=None, priority=0)`。実際の読み込みは`gui/workers.py`の`read_data_file()`の入口(唯一の拡張子判定の集約点だった)で優先的に参照し、未登録拡張子はビルトインCSV/Excel処理にフォールバック(プラグイン0件時は完全に従来通り)。D&D一括取込(項目77)の対応拡張子・データセット追加のファイルダイアログフィルタの両方に登録拡張子を自動反映。現時点では単一DataFrameを返すローダーのみ対応(複数シート返却は未対応、将来の拡張点として明記) |
| B-2 | `register_exporter()` | ✅ 完了 | 2026-08-05 | `GraphicaPluginAPI.register_exporter(format_name, extension, writer, *, name=None)`。`BatchExportDialog`の形式コンボ・単発エクスポートの保存ダイアログフィルタの両方に登録形式を自動追加。`_save_figure_with_options()`/`_on_export_plot()`がビルトインsavefigより先にプラグインwriterを確認 |
| B-3 | インポート/エクスポート失敗時UXの統一 | ✅ 完了 | 2026-08-05 | `core/plugin_types.py`に`PluginExecutionError`(登録時ではなく実行時の失敗、文字列化すると`[プラグイン名]`が必ず付く)を追加。新しいUIを作らず、既存のエラーダイアログ経路(`DataLoadWorker`→`QMessageBox.critical`、エクスポートの`QMessageBox.warning`/バッチ結果一覧)にそのまま乗せることで統一 |

**フェーズB完了条件**: 上記3項目が✅。**達成(2026-08-05)**。フェーズC(データ処理フック)に着手可能。

### フェーズC: データ処理・解析フック

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| C-1 | `register_processor()` | ✅ 完了 | 2026-08-05 | `GraphicaPluginAPI.register_processor(name, fn, *, category="general", param_schema=None)`。`fn`は`(Dataset, dict) -> Dataset`で、元のDatasetを一切変更しない非破壊パターン(規格化・Savitzky-Golayと同じ)。プラグインメニューに「データ処理」サブメニューを追加し、`category`ごとにさらにサブメニューでグルーピング。`param_schema`(型ヒント方式ではなく明示的なdictリスト方式を採用、理由: ラベル・min/max・choices・デフォルト値をプラグイン作者が明示制御できる)から`PluginParamDialog`(`gui/dialogs.py`)が入力フォームを自動生成する |
| C-2 | `register_analyzer()` | ✅ 完了 | 2026-08-05 | `GraphicaPluginAPI.register_analyzer(name, fn, *, output_kind="table", param_schema=None)`。`fn`は`(Dataset, dict) -> AnalysisResult`(`core/plugin_types.py`に新設、`table`/`annotations`/`new_datasets`の3種の結果をそれぞれ独立に保持可能な構造化データ)。プラグインメニューに「解析」サブメニューを追加。結果の`table`は既存`ResultDialog`、`annotations`は既存`SetAnnotationsCommand`、`new_datasets`はC-3のUndo経路にそのまま乗せる形で統合し、新しい表示UIは作らない |
| C-3 | プラグイン処理結果のプロジェクト保存統合 | ✅ 完了 | 2026-08-05 | `Dataset.source_plugin`フィールド追加(生成元プラグイン名、通常操作で作られたDatasetは`None`のまま)。JSON/pickle双方とも`dataclasses.fields()`による既存の汎用シリアライズ経路にそのまま乗るため、追加のシリアライズコード不要で往復する(欠落時は`None`にフォールバック、後方互換)。C-1/C-2が生成した新規Datasetの追加は、既存の「データセット追加はUndo非対応」という設計境界を維持したまま、新設の`AddDatasetCommand`(`core/commands.py`)+`_add_dataset_with_undo()`(`gui/main_window.py`)経由でのみUndo/Redo可能にした(既存の規格化・Savitzky-Golay等は意図的に対象外のまま) |

**フェーズC完了条件**: 上記3項目が✅。**達成(2026-08-05)**。フェーズD(GUI拡張フック)に着手可能。

### フェーズD: UIフック

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| D-1 | `register_panel()` | ✅ 完了 | 2026-08-07 | `GraphicaPluginAPI.register_panel(name, widget_factory, *, area="right")`。`register_dock`という別フックには分離せず統合(当初検討した分離案は不採用)。`widget_factory: (ProjectModel, QUndoStack) -> QWidget`はタブ(`PlotterApp`インスタンス)ごとに個別に呼ばれ、`gui/main_window.py`の`__init__`で`QDockWidget`として追加(既定は非表示、表示状態はQSettingsのドックレイアウト復元に任せる)。構築失敗(例外・`QWidget`以外の返り値)は該当パネルのみスキップしログ警告、他のパネル・タブ自体の起動は継続する。表示切替は「プラグイン」メニューの「パネル」サブメニューに`toggleViewAction()`を集約 |
| D-2 | `register_plot_type()` | ✅ 完了 | 2026-08-07 | `GraphicaPluginAPI.register_plot_type(type_name, drawer, *, requires_2d=False)`。既存5種類(Line/Scatter/Line+Scatter/Area/Bar)の`gui/canvas.py`の分岐は変更せず、未知の`plot_type`に遭遇した場合のみプラグインレジストリを引くフォールバックのelse節を新設(増分実装)。`drawer: (Dataset, Axes, x_data, y_data) -> Artist | None`。ウォーターフォール等の追加オーバーレイはプラグイン描画には自動適用されない既知の制限。データセットプロパティのプロット種別コンボボックスにも、Area/Barと同じ実行時追加方式で反映 |
| D-3 | UIフックのi18n統合方針決定 | ✅ 完了 | 2026-08-07 | 【方針決定】プラグイン側の表示名(パネルタイトル・メニュー項目名等)は当面英語表記のみサポートし、`core/i18n.py`の`tr()`による翻訳統合は行わない(プラグイン作者に本体翻訳辞書への依存を強いる過剰な結合を避けるため)。プラグインエコシステムが育ってから再検討する、という判断を`core/plugin_api.py`のモジュールdocstringに明記 |

**フェーズD完了条件**: 上記3項目が✅。**達成(2026-08-07)**。

### フェーズE: exe配布環境でのプラグイン運用

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| E-1 | プラグイン探索パスを`%LOCALAPPDATA%`に追加 | ✅ 完了 | 2026-08-07 | `core/app_paths.py`に`get_user_plugins_dir()`追加(`get_app_data_dir()`配下の`plugins`)。`gui/main_window.py`に`is_frozen()`/`plugin_search_paths()`を新設し、ソース実行時のみ`resource_path("plugins")`(開発者向け)、常に`get_user_plugins_dir()`(exe配布環境でもユーザーが書き込める場所)を探索対象にする。`PluginManager`/`load_plugins_once()`は単一パス(str)・複数パス(list)の両方を受け付けるよう拡張(既存呼び出し元との後方互換を維持)。`discover_plugin_dirs()`の戻り値の形は変更せず、同名プラグインが複数パスに存在する場合は探索順の早い方を優先しログ警告 |
| E-2 | プラグインのインストール導線(GUI) | ✅ 完了 | 2026-08-07 | `core/plugin_install.py`新設、`install_plugin_zip(zip_path, target_dir=None)`。環境設定ダイアログ(`PreferencesDialog`)に「プラグイン」グループ+「プラグインをインストール...」ボタンを追加(既存のOK/Cancelフローとは独立した即時実行、オートセーブ保存先の参照ボタンと同じ位置づけ)。zipの2レイアウト(単一フォルダに包まれている/`__init__.py`がzip直下)双方に対応し、成功時は次回起動時に有効になる旨をダイアログで明示 |
| E-3 | 【方針決定】プラグインの依存パッケージ問題 | ✅ 完了 | 2026-08-07 | 【方針決定】プラグインは本体に同梱済みの依存(numpy/pandas/scipy/matplotlib/PySide6等)のみ使用可、という「純標準ライブラリ縛り+本体依存のみ」を採用。`PLUGIN_INFO`に任意の`"requires"`キー(モジュール名のリスト)を追加できるようにし、`core/plugin_api.py`の`_check_plugin_dependencies()`が`importlib.util.find_spec()`で不足を検出。`PluginManager.load_all()`に組み込み、依存不足のプラグインは既存の失敗隔離経路(`record["error"]`)でロードをスキップ、アプリはクラッシュしない |
| E-4 | 単一インスタンス化(多重起動時のプラグイン二重ロード対策) | ✅ 完了 | 2026-08-07 | E-2の`install_plugin_zip()`に統合実装。zipは`target_dir`と同一ボリューム上の一時ステージングディレクトリへ展開してから`os.replace()`による単一のアトミックリネームで最終配置(再インストール時は既存フォルダを一時退避してから入れ替え)。ステージング中は`discover_plugin_dirs()`から見て壊れかけのプラグインとして誤検出されない(トップレベルに`__init__.py`が無い)よう設計。zip-slip対策(パストラバーサル)も同時に実装。本格的な`QLocalServer`ベースの単一インスタンス化はロードマップの範囲外として明記 |

**フェーズE完了条件**: 上記4項目が✅。**達成(2026-08-07)**。フェーズF(マニフェスト・管理UI・安全性)に着手可能。

### フェーズF〜G

未着手。詳細は `Graphica_ROADMAP_PLUGIN_AND_GUI.md` を参照。

## トラック2〜4

未着手(トラック1完了が前提、トラック2はH-0のみ先行着手可)。詳細は `Graphica_MASTER_SCHEDULE.md` / `Graphica_ROADMAP_PLUGIN_AND_GUI.md` を参照。

---

## 更新履歴

- 2026-08-05: 新規作成。C-001完了を反映。
- 2026-08-05: C-008・C-009・C-1205完了を反映。トラック0(必須4項目)が全て完了。
- 2026-08-05: C-006・C-002(推奨2項目)完了を反映。トラック0の推奨分も含め全て完了。
- 2026-08-05: トラック0'(クイックウィン9項目)完了を反映。
- 2026-08-05: トラック1 フェーズA(A-1〜A-4)完了を反映。
- 2026-08-05: トラック1 フェーズB(B-1〜B-3)完了を反映。
- 2026-08-05: トラック1 フェーズC(C-1〜C-3)完了を反映。
- 2026-08-07: トラック1 フェーズD(D-1〜D-3)・フェーズE(E-1〜E-4)完了を反映。
