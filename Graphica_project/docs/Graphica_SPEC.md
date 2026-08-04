# Graphica — 機能・仕様まとめ (AI引き継ぎ用)

このドキュメントは、別のチャットセッション/別のAIに渡して「追加機能の検討」「既存仕様の改善」を行ってもらうための引き継ぎ資料です。人間向けの読みやすさより、AIが正確に状況を把握できることを優先して書いています。

作成時点: 2026-08-04。リポジトリ: ローカルgitリポジトリ、GitHub上の `STsuruga/Graphica`(private)にpush済み。

---

## 1. 製品概要

**Graphica** は、実験データ(CSV/Excel)を読み込んでグラフ化・解析するためのWindowsデスクトップアプリケーション。ユーザーは主に理系の研究・実験用途(分光データ、時系列測定など)を想定している。UI言語は日本語がメイン(多言語対応の仕組み自体はあり、英語辞書もある)。

### 技術スタック
- Python 3.13
- GUI: PySide6 (Qt6)
- グラフ描画: matplotlib(`FigureCanvasQTAgg`埋め込み)
- データ処理: pandas, numpy, scipy(カーブフィット・ピーク検出・補間)
- Excel: openpyxl
- テスト: pytest(`tests/conftest.py`が`QT_QPA_PLATFORM=offscreen`を設定し、セッションスコープの`QApplication`フィクスチャを提供。ヘッドレスで動く)
- 配布: PyInstallerでexe化、GitHub Actionsでビルド自動化、pip配布(PyPI)にも対応済み

### リポジトリ構成
- リポジトリルートには `README.md`(ユーザー向け取扱説明書、日本語)のみ。
- 実体は全て `Graphica_project/` 配下(コマンドはすべてこのディレクトリをcwdとして実行する: `pip install -r requirements.txt`, `python main.py`, `pytest`)。
- リポジトリルートの `Graphica_ver1.spec` / `main_ver6.spec` は現行構成以前の古いPyInstaller specファイルで、使われていない(存在しないエントリポイントを参照している)。

---

## 2. アーキテクチャ

### 2.1 エントリポイントとウィンドウ階層

- `main.py`: クラッシュハンドラ(`gui/crash_handler.py`、未処理例外発生時に`graphica.log`へ書き込み+復旧案内ダイアログ)をインストールし、`QApplication`を1つ作って`MainAppWindow`を1つ表示する。
- `MainAppWindow` (`gui/main_app_window.py`): `QTabWidget`を持つ最上位ウィンドウ。**各タブは完全に独立した`PlotterApp`インスタンス**(それ自体が完全なQMainWindow: メニューバー・ドック・undoスタック・キャンバス・プロジェクトを個別に持つ)。既存の8つのMixin構成を「タブ対応」に書き換えるのではなく、タブごとに丸ごと別インスタンスを作る設計を選んでいる。
  - 最初のタブ(`run_startup_checks=True, tab_id=None`)だけがオートセーブ復元確認・初回起動ウェルカム表示・`clean_exit`のQSettings追跡を行う。2つ目以降のタブ(`tab_id=2,3,...`)はこれらをスキップし、オートセーブファイル名も衝突しないよう`autosave_tab{N}.pkl`のように分ける。

### 2.2 `PlotterApp`のMixin構成 (`gui/main_window.py`)

`PlotterApp(QMainWindow, ...)`は以下のMixin群から構成される(`gui/mixins/`配下):

| Mixin | 責務 |
|---|---|
| `UISetupMixin` | 一度きりのシグナル接続(`_connect_signals`)、メニューバー構築 |
| `SettingsMixin` | UI⇔軸ごと設定辞書の相互変換、フォント/色ピッカー、軸の挙動 |
| `DatasetMixin` | データセットの追加/削除/複製/プロパティ編集、カーブフィット、ピーク検出 |
| `CursorMixin` | データカーソルツール(クリックして座標を読み取る) |
| `AnnotationMixin` | グラフ上の自由なテキスト/矢印注釈 |
| `LayoutEditMixin` | 自由配置(非グリッド)レイアウトのドラッグ操作 |
| `ExportMixin` | 画像/PDF/SVGエクスポート、エクスポートプレビュー |
| `ProjectIOMixin` | プロジェクトの保存/読込メニュー、フォーマットテンプレート |
| `HelpMixin` | ヘルプダイアログ群 |
| `QuickAccessMixin` | クイックアクセスツールバー(項目87、後述) |

`PlotterApp.__init__`はUIファイル読込→動的ウィジェット構築→動的レイアウト変更→シグナル接続→メニューバー→初期状態、という番号付きセクションで構成されている(後発の実装追加はこの構造に沿って挿入する)。

### 2.3 Designer生成UI vs 実行時構築UI

`ui_main_window.py`(`Graphica_project/`直下、`gui/`配下ではない)はQt Designer/`pyside6-uic`が生成したもので、**絶対に手編集しない**。アプリ機能の大半(後から段階的に追加されたもの)は`gui/main_window.py`側で実行時に構築されている。既存Designerウィジェットを置き換える場合は`layout.replaceWidget(old, new)`パターンを使い、行インデックスがずれないようにする。

### 2.4 コア層 (`core/`)

- `core/dataset.py` — `Dataset`データクラス。1つのプロットのデータ+スタイルを保持。詳細は本ドキュメント第3節。
- `core/commands.py` — 全ての`QUndoCommand`サブクラス(セル編集・行/列追加削除・データセットプロパティ変更・マスク切替・注釈変更・データセット並べ替え・列名変更)。コマンドはGUIウィジェットを一切知らず、`Dataset`/`ProjectModel`を直接操作する。GUI Mixinは`self.undo_stack`にコマンドをpushし、その後再描画する。
- `core/analysis.py` — カーブフィット・ピーク検出(scipyベース)。プラグイン提供のフィット関数もここに登録される(`_PLUGIN_FIT_FUNCTIONS`、プロセス全体で1つの辞書)。
- `core/excel_utils.py` — Excel固有処理(未計算数式セルの検出、複数シート対応)。
- `core/i18n.py` / `core/translations_en.py` — 最小限の翻訳レイヤ(Qt Linguistではない)。`tr(日本語テキスト)`が辞書を引く。`set_language()`は次回起動時のみ反映(動的な再翻訳はしない)。
- `core/plugin_api.py` — プラグイン機構(後述4.5)。
- `models/project.py` — `ProjectModel`(データセット群・軸ごと設定・レイアウトを含むプロジェクト全体)。保存形式の詳細は第5節。

### 2.5 描画 (`gui/canvas.py`)

`MplCanvas`がmatplotlibの`Figure`/`Axes`を保持し、全ての描画を行う(`_draw_data`, `_apply_appearance`)。

重要な非自明な挙動:
- `ax.set_xscale(...)`は「同じ値」を渡してもLocator/Formatterをリセットしてしまうため、カテゴリ軸/日付軸のコードパスはこれを一切呼ばないようにしている。
- フル再描画は`fig.clf()`を呼ぶため、`_update_plot()`をまたいで`Axes`オブジェクトをキャッシュしてはいけない(既に破棄されている)。
- `_draw_data`のデータセットごとのループでは、`ds.plot_type`(`'Line'/'Scatter'/'Line+Scatter'/'Area'/'Bar'`)で描画方法を分岐している。ウォーターフォール(後述)はこの`plot_type`とは独立したオーバーレイ処理として実装されている。

### 2.6 リソースパス

`gui/main_window.py`の`resource_path()`は、ソース実行時は`gui/main_window.py`自身の場所、PyInstallerでexe化された場合は`sys._MEIPASS`を基準にリソース(アイコン・サンプルデータ・アプリアイコン)を解決する。**プロセスのカレントディレクトリには依存しない設計**(過去に`os.path.abspath(".")`ベースの実装で、cwdが`Graphica_project/`以外だとアイコンが壊れるバグがあった教訓による)。新しいリソース読み込みコードは必ず`resource_path()`(または`icon_utils.icon()`)を経由すること。

### 2.7 設定・オートセーブ

`QSettings("Graphica", "Graphica")`にダークモード・オートセーブ間隔・オートセーブ保存先・最近使ったファイル・ウィンドウ/ドックレイアウト・カスタムカラーパレット・言語などを永続化。オートセーブは世代管理(`_rotate_autosave_generations`、`AUTOSAVE_GENERATIONS`件保持)。ドックレイアウト(`saveState()`/`restoreState()`)は最初のタブでのみ、かつ初回起動時のみ適用される。

### 2.8 既知のアーキテクチャ上の落とし穴(他AIが実装する際の注意点)

1. **shiboken GCの罠**: `self.menuBar().actions()`をたどってから`.menu()`でQMenuを取得すると、その場では動いても後になって「Internal C++ object already deleted」エラーになることがある。対策として、メニュー作成時に`self._file_menu`/`self._edit_menu`等のインスタンス属性としてキャッシュし、常にそこから辿る(`_collect_menu_actions()`がこのパターンに従う)。
2. **restoreGeometry()のタイミング**: `restoreGeometry()`を`show()`より前(ネイティブウィンドウ未生成の状態)で呼ぶと、Windowsのウィンドウ枠の実寸が未確定なままジオメトリを復元してしまい、ウィンドウの画面上の位置についてQtが持つ内部認識が実際とズレる不具合が過去に発生した(ポップアップ位置・クリック判定・matplotlibのマウス座標など、画面座標変換を伴うもの全てが一律にズレて見えた)。対策: `self.winId()`でネイティブハンドルを先に生成してから`restoreGeometry()`を呼ぶ。
3. **Win32のDPI認識API呼び出しは危険**: `SetProcessDpiAwareness()`等をアプリ側で明示的に呼ぶと、Qt6自身が内部で行うPer-Monitor-V2 DPI認識の設定(`SetProcessDpiAwarenessContext()`)がアクセス拒否で失敗し、意図しないDPIモードのまま動作してしまう。**Qt6は何もしなくても正しくDPI認識するため、アプリ側でこの種のWin32 API呼び出しを追加しないこと。**
4. **`_RestrictedUnpickler`**: `models/project.py`の pickle(.pkl、旧形式)読込は`numpy`/`pandas`/`core.dataset`のみを許可するアンピクラーを使っており、任意コード実行への意図的な対策。許可リストを安易に広げないこと。

---

## 3. データモデル

### 3.1 `Dataset` (core/dataset.py) — 全フィールド

1つのプロット対象(1本の線/散布図/etc.)を表す。

**データ本体**
- `name: str` — 凡例名
- `df: pd.DataFrame` — 元データ全体
- `x_col_name: str` / `y_col_name: str` — 現在X/Y軸として選ばれている列名

**派生プロパティ(全て`masked_row_indices`除外後の`visible_df`経由)**
- `visible_df` — マスク行を除いたDataFrame(非破壊マスク、項目36)
- `x_data` / `y_data` — numpy配列
- `x_err_data` / `y_err_data` — 誤差列が設定されていればnumpy配列、なければNone

**スタイル基本**
- `plot_type: str = 'Line'` — `'Line' | 'Scatter' | 'Line+Scatter' | 'Area' | 'Bar'`
- `color: str = '#1f77b4'`
- `linestyle: str = '-'`
- `linewidth: float = 1.5`
- `marker: str = 'o'`
- `markersize: float = 6.0`
- `smoothing: bool = False` — CubicSplineで平滑化
- `alpha: float = 1.0`

**グラデーション (項目79)**
- `gradient_enabled: bool = False`
- `gradient_color2: str = '#ffffff'` — 終端色(開始色は`color`を流用)
- `gradient_target: str = 'line'` — `'line' | 'fill' | 'both'`(`'both'`はAreaのみ意味を持つ)
- 実装: 線は`matplotlib.collections.LineCollection`+`LinearSegmentedColormap`、塗りは`imshow`+`Polygon`クリップパス

**ウォーターフォール (項目80、項目109で仕様変更)**
- `waterfall_enabled: bool = False` — **plot_typeとは独立したフラグ**(初版はplot_typeの専用値`'Waterfall'`だったが、線種/マーカー等の通常のスタイル選択と排他になり使いにくいとのフィードバックで変更した。どのplot_typeとも組み合わせ可能)
- `waterfall_offset_x: float = 0.0`
- `waterfall_offset_y: float = 1.0`
- 積み重ねインデックスは、同一サブプロット内で`waterfall_enabled=True`のデータセットだけをリスト順に0始まりで数えたもの。N番目は`(N*offset_x, N*offset_y)`だけずらして描画。手前のトレースが奥を隠す遮蔽(occlusion)を、背景色`fill_between`で表現(zorderで前後関係を制御)。Areaは自身の塗りと二重になるため遮蔽は対象外。

**データ点ラベル**
- `show_point_labels: bool = False`
- `point_label_col_name: str | None` — Noneならy_dataそのものを表示

**誤差バー**
- `x_err_col_name: str | None`
- `y_err_col_name: str | None`

**マスク(項目36)**
- `masked_row_indices: list` — `df.index`のラベルのリスト(位置ではない)

**その他**
- `fit_info: str | None` — カーブフィット結果文字列
- `use_secondary_y: bool = False` — 第2Y軸使用
- `subplot_target: int = 0` — 描画先サブプロット番号
- `artist: object` — matplotlib Artistへの生参照(シリアライズ対象外、repr対象外)
- `dataset_id: str` — UUID hex、フォルダ分け機能等で名前に依存せず一意特定するためのID

**データ編集メソッド** (core/commands.pyのUndoコマンドから呼ばれる)
`set_cell` / `add_row` / `delete_last_row` / `delete_rows` / `restore_rows` / `add_column` / `remove_column` / `rename_column`(項目64、参照している設定を自動追従) / `restore_column`

**シリアライズ**
`to_dict()`/`from_dict()`(JSON、.graphica形式)、`__getstate__`/`__setstate__`(pickle、旧.pkl形式)。両方とも`dataclasses.fields()`に対して汎用的なので、新フィールド追加時に個別の対応コードは基本不要(デフォルト値で自動補完)。ただし**plot_type値の削除・意味変更のような破壊的変更をする場合は、`from_dict`/`__setstate__`内で明示的な移行コードが必要**(waterfall_enabled導入時の実例あり: 旧`plot_type=='Waterfall'`を`plot_type='Line'+waterfall_enabled=True`に読み替え)。

### 3.2 `ProjectModel` (models/project.py)

プロジェクト全体(全データセット、軸ごと設定`all_plot_settings`、レイアウト情報、レイアウトモード`grid`/`free`)を保持。JSON形式(.graphica)と旧pickle形式(.pkl)の両方をロード可能(保存は新形式のみ)。

---

## 4. 主要機能インベントリ

以下、実装済み機能を分野別に整理する(ロードマップ項目番号付き)。**この番号は今後の会話でも「#78を直して」のように参照される可能性がある。**

### 4.1 データ入出力
- CSV/Excel読み込み、ヘッダー行指定・シート切替・複数シート一括インポート・セル範囲指定・数式セル警告・クリップボード貼り付け・列型自動判定確認(#13,14,23-27)
- 複数ファイルの一括ドラッグ&ドロップ読込(#77): 対応拡張子(.csv/.xls/.xlsx)を順次キューイング、非対応はまとめて1回警告してスキップ
- データセット表をCSV/Excelとして書き出し(#57)
- 空のテーブルから新規データセット作成 + 列名リネーム(#63,64)

### 4.2 データ処理・解析
- カーブフィット(対数・べき乗・ガウシアン等+ユーザー定義数式、R²・残差表示)(#11,54)、ピーク検出
- 反復測定からの誤差自動計算(#12)
- データセット間演算(差分・比率などを新規データセットとして生成)(#20)
- バッチ処理(#22)・バッチ列計算
- 規格化(ノーマライズ)機能(#78): 最大値基準/特定X値での強度基準でY値を正規化、非破壊で新規データセット生成。マスク行は自動除外。基準値がほぼ0の場合は警告し中止
- 外れ値のマスク機能(非破壊)(#36)
- 統計サマリー(常時表示パネル→ツールバーのオンデマンドポップアップに移行済み)(#21)

### 4.3 プロット表現・軸機能
- 塗りつぶし(Area)/棒グラフ(Bar)(#28)
- データポイントラベル表示 + 大量データでのフリーズ防止(表示上限点数、超過時ポップアップ確認)(#29)
- 日付/時刻軸・カテゴリ(文字列)軸の自動フォーマット(#30,31)
- グラデーション適用(線ストローク/塗り、対象選択可)(#79)
- ウォーターフォール表示(積み重ねオプション、plot_type非依存)(#80/#109、詳細は3.1節)
- グリッド線の詳細カスタマイズ(X/Y軸・主/補助目盛それぞれ独立の線種・太さ・透過度)(#82)
- 目盛りの指数表記フォーマット切替(自動/軸端まとめ/目盛りごと/常に小数)(#62)
- 凡例の表示順序をドラッグで並べ替え(#59)
- 軸ラベルの文字装飾(太字/イタリック/上付き/下付き、mathtext自動生成)+ ギリシャ文字/記号パレット(#61/#81): 4×4パレット(α β γ δ ε μ π ρ Σ σ τ Ω ω Δ θ φ)、選択なしでもカーソル位置に挿入可。総和・積分・矢印・比較演算子等のリファレンスも拡充。**本格LaTeX(usetex)化は今回は見送り、将来的にプラグインとして提供する方針**(mathtext拡張のみ実装)

### 4.4 UI/操作性
- GUIモダン化(フラット/ミニマルテーマ、ダークモード両立)(#46)
- コマンドパレット(Ctrl+Shift+P)、キーボードショートカット一覧(#47,55)
- レンジスライダー(ミニマップ)(#83): グラフ下部に全サブプロット共通の小さいFigureを表示、`matplotlib.widgets.SpanSelector`でドラッグ選択→全サブプロットのX軸ズームに反映(`set_xlim`+`draw_idle`のみ、フル再描画はしない)。表示メニューで表示/非表示切替、QSettingsで記憶
- スナップ・トゥ・グリッド(#84): テキスト/矢印注釈のドラッグ位置をピクセル単位でスナップ。環境設定でON/OFF+間隔(px)。既定は無効。`SetAnnotationsCommand`経由でUndo対応
- 自由配置レイアウトの拡大縮小拡張(#85): サブプロット選択時にX/Y/幅/高さの数値入力欄を表示、マウスドラッグと同じ更新経路(`ax.set_position()`+`all_plot_settings[idx]['free_rect']`)を共有
- マルチモニター対応・Canvas切り離し(#86): 既存の`self.canvas`インスタンスを破棄せず、`plot_container`と独立ウィンドウ(`DetachedCanvasWindow`)の間で親を実行時付け替え。アプリ全体に散在する約70箇所の`self.canvas`参照を無変更で維持。位置/サイズをQSettingsで記憶
- クイックアクセスのカスタムツールバー(#87): メニュー項目を右クリックしてピン留め。識別はメニュー階層のテキストパス文字列(QActionは毎回作り直されるためobjectNameは使えない)。プラグイン登録アクションもピン留め対象
- 自由なテキスト注釈・矢印(Undo/Redo対応)(#18,60)
- データ⇔グラフの双方向ハイライト(#34)
- グラフ要素の直接クリック選択(#35)
- 自由配置レイアウトページ(#37)、複数プロジェクトのタブ化(#40)

### 4.5 拡張性
- プラグインアーキテクチャ(#76): `plugins/`ディレクトリ配下に配置するだけで、カーブフィット関数追加・メニューアクション追加が可能。`core/plugin_api.py`の`GraphicaPluginAPI`が窓口(`register_fit_function`, `register_menu_action`)。多タブ構成でも二重登録が起きないよう、プロセス全体で1度だけ読み込む(`load_plugins_once`のモジュールレベルシングルトン)。1プラグインの失敗が他や本体起動を止めない設計
- 多言語対応(#41、`core/i18n.py`、次回起動時反映)

### 4.6 エクスポート
- 画像/PDF/SVGエクスポート、常時表示のエクスポートプレビューパネル(#45)
- SVGクリップボードコピー、SVGテキスト保持(#108関連、目盛り数字等を`<text>`要素として出力)
- 背景透過選択
- ベクトル出力の「テキストのパス化」選択オプション(#88): SVG限定、`svg.fonttype`を`'none'`(既定、テキスト保持)/`'path'`(アウトライン化)で切替。単発/バッチ/プレビューパネルの全経路で対応
- バッチエクスポート(複数サブプロット/複数プロジェクトファイル一括)(#52)
- 印刷(QPrinter直接出力)(#48)

### 4.7 製品化・信頼性
- プロジェクト保存形式のJSON本格移行(#74): pickle(.pkl)→JSON(.graphica)。`Dataset.to_dict/from_dict`、日時列dtype保持、numpy int64/float64混入対応JSONEncoder。旧.pklは引き続き開ける(後方互換)、1回限りの自動移行フォールバックあり
- オートセーブ世代管理+復元プロンプト(#6)
- クラッシュ時のユーザー向け案内(#16)
- 統合「環境設定」ダイアログ(#15)
- pip配布(PyPI公開)対応(#73)、GitHub Actions CIビルド自動化(#75)

### 4.8 未着手(配布フェーズ、優先度低)
- インストーラ化(#42)、コード署名(#43)、アップデート通知機構(#44)、macOS対応(#53) — いずれも`status: pending`。配布フェーズ関連のためソフト本体の機能とは別枠。

---

## 5. プロジェクトファイル形式 (.graphica)

- JSON形式。`ProjectModel`全体(データセットリスト、軸ごと設定、レイアウトモード等)をシリアライズ。
- `Dataset.to_dict()`: `dataclasses.fields()`を汎用的に走査してdict化。`df`は`_df_to_dict`で日時列dtype等を保ったまま変換(datetime64はISO8601文字列、NaTはNone)。numpyの`int64`/`float64`が紛れ込むケースに対応するカスタムJSONEncoderあり。
- `Dataset.from_dict()`: 欠けているフィールドはdataclassのデフォルト値で補完。必須フィールド(name/x_col_name/y_col_name)が欠けている場合は明示的にエラー(壊れたファイルの早期検知)。
- 後方互換: 旧pickle(.pkl)ファイルも`_RestrictedUnpickler`(numpy/pandas/core.datasetのみ許可)経由で引き続き読み込み可能。

---

## 6. テスト方針

- pytest、`Graphica_project/tests/`配下。`conftest.py`が`QT_QPA_PLATFORM=offscreen`とセッションスコープ`QApplication`フィクスチャを提供、手動セットアップ不要。
- QSettingsを使うテストは実際のレジストリ/iniを汚染しないよう一時ファイルにリダイレクトする(`IsolatedQSettings`パターン、`tests/test_main_window.py`の`_make_isolated_plotter_app`を参照)。
- 2026-08-04時点で248件のテストが通過(全機能追加を通じて一貫して増加、既知の回帰なし)。
- リンター/フォーマッターは未導入(`.flake8`/`pyproject.toml`/`.pylintrc`なし)。周囲のコードスタイルに合わせる。

---

## 7. 今後の検討で押さえておくべき設計上の合意事項

他AI/別チャットに追加機能を検討してもらう際、以下は既に確定した方針として扱ってよい:

1. **本格LaTeXレンダリング**は今回スコープ外。将来、プラグイン機構(#76)経由で`usetex=True`エンジンに差し替え可能な設計にする想定だが、具体的なプラグインAPIフックはまだ未設計・未実装(意図的に見送った)。
2. **ウォーターフォールのようなplot_type関連の新機能は、既存のスタイル選択(線種/マーカー/色)と排他にしない**こと。#80の反省を踏まえ、可能な限り「独立したON/OFFフラグ」として既存スタイルと直交させる設計が好ましい(グラデーション機能#79も同じ設計パターン)。
3. **Win32のDPI関連API呼び出しは追加しない**(2.8節参照、過去に深刻なバグの原因になった)。
4. **配布用exeを使うユーザーの環境には外部ソフト(LaTeX等)がインストールされていない前提**で機能設計すること(配布フェーズの各項目#42-44,53参照)。
5. マルチタブ・マルチウィンドウ(#40, #86)の存在を前提に、新しいグローバル状態(シングルトン、モジュールレベル変数)を追加する際は、タブ間の二重登録・競合が起きないか要検討(プラグイン機構#76のシングルトンパターンを参考に)。
