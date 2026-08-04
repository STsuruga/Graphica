# Graphica 実装ロードマップ: プラグインAPI拡張 + GUIモダン化

**このファイルの使い方**: `Graphica_project/` をcwdとしてClaude Codeに渡す。フェーズ順に上から着手し、各フェーズの「完了条件」を満たしてから次へ進むこと。実際の分野特化プラグイン(XPS/XRD/JCAMPインポータ等)の開発はこのロードマップの範囲外。ゴールは (1) プラグインが本体を一切改変せずに実装できる状態、(2) GUIの見た目がモダンに刷新された状態、の両方を作ることまで。

**参照**: `Graphica_SPEC.md`(現行仕様、特に2.8節の既知の罠と7章の設計合意事項)。本ロードマップの決定はすべて7章の合意事項と矛盾しないこと。

---

## 0. 全体の順序とタイミングの考え方

### 結論: GUI改修は最後(フェーズH)に置く

```
フェーズA: 土台(型・エラー隔離・テスト基盤)
フェーズB: データ入出力フック
フェーズC: データ処理フック
フェーズD: UIフック(register_panel / register_plot_type)
フェーズE: exe配布環境でのプラグイン運用
フェーズF: マニフェスト・管理UI・安全性
フェーズG: 描画バックエンド差し替え(骨組みのみ)
─────────────────────────────────────
フェーズH: GUIモダン化(QSSカスタマイズ)   ← 全部終わってから着手
```

### なぜ最後なのか(3つの理由)

**理由1: 見た目の変更とアーキテクチャの変更を同時にやると、バグの切り分けが困難になる**
プラグインAPI実装中に何かが動かなくなったとき、原因が「フックのロジック」なのか「QSSの副作用」なのか分からなくなる。片方ずつ確定させながら進める。

**理由2: 二度手間を避ける**
フェーズDで `register_panel`、フェーズFで管理UI(プラグイン一覧タブ)という**新しいUI要素**が追加される。これを先にデフォルトの見た目で作り、GUI改修フェーズでまとめてスタイルを当てる方が、「Dで作った直後にスタイルを当てて、Fで追加したらまた当て直す」という二度手間を避けられる。**新しいUI要素は全部出揃ってから、一括でスタイルを当てるのが効率的。**

**理由3: プラグイン開発者への一貫した基準を先に確定できる**
`register_panel`(D-1)で作られるプラグイン製パネルは、将来的に本体の見た目に馴染む必要がある。先にGUIのスタイル(色トークン・余白・角丸などのルール)を確定させておけば、`docs/plugin_development.md`(F-3)に「パネルはこのスタイルガイドに従うこと」と明記でき、プラグイン開発者に一貫した基準を示せる。順序が逆だと、その基準自体が後から変わってしまう。

### 例外: 色トークンの下調べだけは先にやっても良い

厳密に「H以外では一切GUIに触るな」という意味ではない。**現状のQSS実装がどこにあり、どういう構造になっているかを調べる作業(H-1の一部)は、いつ着手しても後戻りコストが低い**ので、手が空いたタイミングで先にやっておいて構わない。ただし実際に色やスタイルを変更する作業(H-2以降)はフェーズG完了後まで待つ。

---

## フェーズA: 土台

プラグインAPI全体で共有する型・エラーハンドリング・テストの仕組みを先に作る。

### A-1. `PluginContext` / 登録結果の型を定義

**やること**: `core/plugin_api.py` に、各 `register_*` の返り値・エラー型を統一する。

```python
# core/plugin_types.py (新規)
from dataclasses import dataclass
from enum import Enum

class PluginHookKind(Enum):
    IMPORTER = "importer"
    EXPORTER = "exporter"
    PROCESSOR = "processor"
    ANALYZER = "analyzer"
    PANEL = "panel"
    PLOT_TYPE = "plot_type"
    FIT_FUNCTION = "fit_function"       # 既存
    MENU_ACTION = "menu_action"         # 既存
    RENDER_BACKEND = "render_backend"

@dataclass
class PluginRegistrationError:
    plugin_name: str
    hook_kind: PluginHookKind
    message: str
    exception: Exception | None = None
```

**完了条件**: `core/plugin_types.py` が存在し、既存の `register_fit_function` / `register_menu_action` が(内部的にでも)この型を使うようリファクタされている。既存機能の外部から見た挙動は変えない。

**テスト**: `tests/test_plugin_types.py` で型のインスタンス化を検証する軽いテストのみで良い。

---

### A-2. フック登録の失敗を隔離する共通デコレータ/ラッパー

**やること**: 4.5節の既存方針「1プラグインの失敗が他や本体起動を止めない」を、新設する全フックにも同じ形で適用する。現状この隔離ロジックがどこに実装されているか(`load_plugins_once`まわり)を確認し、全 `register_*` から呼ばれる共通経路に一本化する。

```python
def _safe_register(self, plugin_name: str, hook_kind: PluginHookKind, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
        return True
    except Exception as e:
        self._registration_errors.append(
            PluginRegistrationError(plugin_name, hook_kind, str(e), e)
        )
        logger.warning(f"[plugin:{plugin_name}] {hook_kind.value} registration failed: {e}")
        return False
```

**完了条件**: `GraphicaPluginAPI` に `self._registration_errors: list[PluginRegistrationError]` があり、フェーズF-2(管理UI)から読み出せる。既存の2フックもこの経路を通るようリファクタ済み。

**テスト**: 意図的に例外を投げるダミープラグインを`tests/fixtures/plugins/`に置き、起動処理がクラッシュしないこと・エラーが記録されることを検証。

---

### A-3. プラグイン開発者向けの疑似API(テストダブル)を先に作る

**やること**: 本体を起動しなくてもプラグイン側が単体テストを書けるよう、`GraphicaPluginAPI` の最小スタブを独立モジュールとして用意する。

```python
# core/plugin_testing.py (新規)
class FakeGraphicaPluginAPI:
    """本体を起動せずにプラグインのregister呼び出しを検証するためのテストダブル。
    実際のGraphicaPluginAPIと同じpublicメソッドシグネチャを維持すること。"""
    def __init__(self):
        self.importers = {}
        self.exporters = {}
        self.processors = {}
        self.analyzers = {}
        self.panels = {}
        self.plot_types = {}
        self.fit_functions = {}
        self.menu_actions = {}

    def register_importer(self, extensions, loader, **kw): ...
    # 以下、各フック実装時に追加していく
```

**完了条件**: `core/plugin_testing.py` が存在する。各フックのメソッドは、そのフックを実装するフェーズ(B/C/D)で同時に追加する。

### A-4. シグネチャ乖離を防ぐ契約テスト

**やること**: `FakeGraphicaPluginAPI` と本物の `GraphicaPluginAPI` のpublicメソッドシグネチャが一致していることを機械的に検証するテストを1本追加する。

```python
# tests/test_plugin_api_contract.py
import inspect
from core.plugin_api import GraphicaPluginAPI
from core.plugin_testing import FakeGraphicaPluginAPI

def test_fake_api_matches_real_api_signatures():
    real_methods = {n for n, _ in inspect.getmembers(GraphicaPluginAPI, inspect.isfunction) if n.startswith("register_")}
    fake_methods = {n for n, _ in inspect.getmembers(FakeGraphicaPluginAPI, inspect.isfunction) if n.startswith("register_")}
    assert real_methods == fake_methods
    for name in real_methods:
        real_sig = inspect.signature(getattr(GraphicaPluginAPI, name))
        fake_sig = inspect.signature(getattr(FakeGraphicaPluginAPI, name))
        assert real_sig.parameters.keys() == fake_sig.parameters.keys(), name
```

**完了条件**: このテストが恒久的にCIに残る。以降のフェーズで新しい `register_*` を追加するたびに、このテストが「本物とスタブ両方に実装したか」を強制する。

---

## フェーズB: データ入出力フック

### B-1. `register_importer(extensions, loader, *, name=None, priority=0)`

**やること**: `core/plugin_api.py` に追加。

- `extensions`: `[".jdx", ".dx"]` のようなリスト
- `loader`: `Callable[[Path], pd.DataFrame]` または `Callable[[Path], dict[str, pd.DataFrame]]`(複数シート対応、#25と同じ形)
- 同じ拡張子に複数登録された場合、`priority` の高い順、同点はロード順
- **[要確認]** 現状の「クリップボード貼り付け」「D&D一括取込(#77)」「Excelシート切替」の読み込み経路がどこに集約されているかを特定し、その経路の**入口**にプラグインimporterを割り込ませる。UIコード側の分岐を増やさない。

**完了条件**:
- ファイルダイアログのフィルタ一覧に、登録済みimporterの拡張子が自動的に追加される
- D&D一括取込(#77)の対応拡張子判定がプラグイン登録分も含めて動く
- プラグイン0件のときの動作が現状と完全に同一

**テスト**: ダミーの `.testfmt` importerを登録し、D&Dで取り込めることを確認。既存のCSV/Excelテストが全て通ること。

---

### B-2. `register_exporter(format_name, extension, writer, *, name=None)`

**やること**: `ExportMixin` の画像/PDF/SVGエクスポートの選択肢に、プラグイン提供の形式を追加できるようにする。

**完了条件**: 既存のPNG/PDF/SVGエクスポートに影響がないこと。ダミーエクスポータ登録でダイアログに選択肢が増えることをテストで確認。

---

### B-3. インポート/エクスポートの失敗時UXの統一

**やること**: プラグインimporter/exporterが例外を投げた場合のユーザー向けエラーダイアログを、既存の「数式セル警告」等と同じトーンで用意する。「どのプラグインが失敗したか」をエラーメッセージに含める。

**完了条件**: 失敗時にアプリがクラッシュせず、原因がプラグイン名付きで表示される。

---

## フェーズC: データ処理フック

### C-1. `register_processor(name, fn, *, category="general")`

**やること**: `Dataset → Dataset`(非破壊、新規データセット生成)の処理を登録できるようにする。既存の「規格化(#78)」「データセット間演算(#20)」と**同じ非破壊パターンを強制する**シグネチャにする。

```python
def register_processor(self, name: str, fn: Callable[[Dataset, dict], Dataset], *, category: str = "general"):
    """fn は元のDatasetを変更せず、新しいDatasetを返すこと。
    UndoコマンドはAddDatasetCommand経由でpushされる(プラグイン側はUndoを意識しない)。"""
```

- メニューの「データ処理」配下に `category` ごとにグルーピングして自動表示
- パラメータ入力は簡易フォーム自動生成(型ヒント or `param_schema`引数のどちらで実装するか決めて統一する)

**完了条件**: ダミープロセッサを登録し、メニューから実行→新規データセットが非破壊で生成される→Undoで消えることを確認。7章-6(非破壊を既定とする)に準拠。

---

### C-2. `register_analyzer(name, fn, *, output_kind="table")`

**やること**: `Dataset → 表/注釈/派生データ` を返す解析フック。

```python
def register_analyzer(self, name: str, fn: Callable[[Dataset, dict], AnalysisResult], *, output_kind: str = "table"):
    ...

@dataclass
class AnalysisResult:
    table: pd.DataFrame | None = None
    annotations: list[dict] | None = None
    new_datasets: list[Dataset] | None = None
```

結果は文字列ではなく構造化データで保持する(7章-7に準拠)。

**完了条件**: ダミーanalyzerを登録し、結果パネルに表示され、CSV出力できることを確認。

---

### C-3. プラグイン処理結果のプロジェクト保存への統合

**やること**: `register_processor`/`register_analyzer` が生成した新規Dataset・注釈が `.graphica` 保存に正しく含まれ、プラグイン無し環境で開いたときに壊れないことを保証する。

- 生成されたDatasetには通常のシリアライズ(3.1節)がそのまま使える設計にする
- **[要確認・重要]** プラグイン由来のDatasetに「どのプラグインで生成されたか」をメタデータとして残すかどうかを決める。**本ロードマップでは残す方針を推奨**(将来のprovenance機能と自然に接続するため)。着手前に本体側の `format_version` 導入が完了していることを前提条件とする。

**完了条件**: プラグインで生成したDatasetを含むプロジェクトを保存→プラグイン無効化状態で再度開く→クラッシュせず通常データとして表示され、生成元プラグイン名が見える。

---

## フェーズD: UIフック

### D-1. `register_panel(name, widget_factory, *, area="right")`

**やること**: プラグインが独自のドックウィジェットを追加できるようにする。`widget_factory: Callable[[ProjectModel], QWidget]`。

- `AppContext`(2.9節で提案)がまだ無い場合、このフェーズでは`PlotterApp`インスタンスへの限定的な参照(現在のタブの`ProjectModel`と`undo_stack`のみ)を渡す形で妥協してよい
- ドックの表示/非表示はQSettingsで記憶(既存のドックと同じ扱い)
- 2.8節の罠(shiboken GC)に注意: プラグインパネルへの参照もインスタンス属性としてキャッシュするパターンを踏襲する
- **register_dockは別フックにせず、register_panelに統合する**(当初検討した分離案は採用しない。区別する実益が薄いため)

**完了条件**: ダミーパネルを登録し、表示メニューから表示/非表示を切り替えられ、タブごとに独立して存在すること(2.1節のタブ独立設計を踏襲)。

---

### D-2. `register_plot_type(type_name, drawer, *, requires_2d=False)`

**やること**: `gui/canvas.py` の `_draw_data` にある `plot_type` 分岐を、プラグインが新しい種類を追加できる形に外部化する。

- **[重要・難易度高]** 既存の5種類(`'Line'/'Scatter'/'Line+Scatter'/'Area'/'Bar'`)は現状のコードのまま変更しない。「未知の`plot_type`が来たらプラグインレジストリを引く」というフォールバック経路だけを追加する(ウォーターフォールが直交フラグで実装されている前例=7章-2に倣い、既存分岐を壊さない増分実装にする)。

```python
def _draw_dataset(self, ds, ax):
    if ds.plot_type in self.BUILTIN_PLOT_TYPES:
        self._draw_builtin(ds, ax)  # 既存コードをそのまま関数化しただけ
    else:
        drawer = plugin_registry.get_plot_type(ds.plot_type)
        if drawer:
            drawer(ds, ax)
        else:
            logger.warning(f"Unknown plot_type: {ds.plot_type}, falling back to Line")
            self._draw_line(ds, ax)
```

- 返り値のArtistは`ds.artist`にキャッシュされ、2.5節の「`fig.clf()`をまたいでAxesをキャッシュしない」原則に従う

**完了条件**: ダミーplot_typeを登録し、通常のLine/Scatterと同じUIフロー(データセットプロパティダイアログでの選択)から使えること。既存5種類のテストが全てグリーンのまま。

---

### D-3. UIフックのi18n統合

**やること**: プラグインパネル・メニュー項目名の翻訳をどう扱うか決める。**推奨: 当初は英語表記のみサポートとし、i18n統合はプラグインエコシステムが育ってから対応**(過剰実装を避ける)。

**完了条件**: この判断をコードコメントに残し、将来のTODOとして`core/plugin_api.py`のdocstringに明記する。

---

## フェーズE: exe配布環境でのプラグイン運用

**このフェーズはA完了後、B/C/Dと並行して進めてよい。**

### E-1. プラグイン探索パスを `%LOCALAPPDATA%` に追加

**やること**: 現状「`plugins/`ディレクトリに置くだけ」の探索ロジックを確認し、探索対象を以下の優先順で統合する。

```python
def _plugin_search_paths() -> list[Path]:
    paths = []
    if not is_frozen():
        paths.append(resource_path("plugins"))  # 開発者向け(ソース実行時のみ)
    user_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "plugins"
    user_dir.mkdir(parents=True, exist_ok=True)
    paths.append(user_dir)
    return paths
```

- `resource_path()`(2.6節)の既存の使い分け原則をそのまま踏襲し、**新しいWin32 APIやカレントディレクトリ依存を一切追加しない**(2.8節-3の教訓を厳守)

**完了条件**: exe化したビルドで、`%LOCALAPPDATA%\Graphica\plugins\` に置いたプラグインが起動時にロードされる。ソース実行時は従来通り`plugins/`も見る。

---

### E-2. プラグインのインストール導線(GUI)

**やること**: 「環境設定」または専用メニューに「プラグインをインストール」ボタンを追加。zipファイルを選択→E-1のユーザーディレクトリへ展開する。

- ダウンロードしたzipの展開のみ(ネットワーク経由の自動取得はスコープ外)
- 展開後、次回起動時にロードされる旨をダイアログで明示

**完了条件**: zipを選んでインストール→再起動→プラグインが有効になっていることを確認できる。

**注記(フェーズHとの接続)**: このダイアログ自体の見た目は、フェーズHで他のダイアログと合わせて一括調整する。ここでは機能のみ実装し、スタイルはデフォルトのままで良い。

---

### E-3. 【要方針決定】プラグインの依存パッケージ問題

**背景**: exe同梱のPythonにはpipが無い。プラグインが `h5py` や `plotly` のような外部依存を必要とする場合、現状は導入手段が無い。

**このロードマップでの決定**: 「純標準ライブラリ縛り + 本体依存のみ」を採用する。プラグインは `numpy`/`pandas`/`scipy`/`matplotlib`/`PySide6` 等、**本体が既に同梱している依存のみ使用可**という制約を明文化する。それ以外が必要なプラグインは「pip版のGraphicaでのみ動作」と明示し、依存チェック機構だけ用意する。

```python
def _check_plugin_dependencies(manifest: PluginManifest) -> list[str]:
    """マニフェストのrequiresを見て、importできないモジュールを列挙して返す。"""
    missing = []
    for module_name in manifest.requires:
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    return missing
```

**完了条件**: 依存不足のプラグインは明示的なメッセージとともにロードをスキップする(A-2のエラー隔離経路に乗せる)。アプリはクラッシュしない。

---

### E-4. 単一インスタンス化(多重起動時のプラグイン二重ロード対策)

**やること**: E-2のzip展開処理に排他ロック(一時ファイル+リネームのアトミック操作)を入れる。本格的な単一インスタンス化(`QLocalServer`)はこのロードマップの範囲外とし、本体バックログ側の別タスクに委ねる。

**完了条件**: zip展開中に他プロセスが同じディレクトリを読んでも、壊れたプラグインファイルを読み込まないこと。

---

## フェーズF: マニフェスト・管理UI・安全性

### F-1. プラグインマニフェスト `plugin.json`

**やること**: 各プラグインディレクトリ直下に必須とする。

```json
{
  "name": "jcamp-importer",
  "version": "1.0.0",
  "author": "...",
  "api_version": "1.0",
  "requires": ["numpy", "pandas"],
  "description": "JCAMP-DX file import support",
  "entry_point": "graphica_plugin_jcamp:register"
}
```

- `api_version`: このロードマップで実装するプラグインAPIのバージョン。フェーズA〜Gの完了時点で `"1.0"` として固定する。以後の破壊的変更は `"2.0"` のように上げ、不一致のプラグインをロード前に弾いて警告を出す
- マニフェスト無し/不正な場合、ロードせず警告(A-2のエラー隔離経路)

**完了条件**: マニフェスト無し・不正なプラグインが安全にスキップされる。`api_version`不一致の検出テストがある。

---

### F-2. プラグイン管理UI

**やること**: 環境設定(#15)に「プラグイン」タブを追加。

- ロード済みプラグイン一覧(name/version/author)
- 個別ON/OFF(QSettingsに記憶、次回起動反映でよい)
- A-2の`_registration_errors`とE-3の依存不足情報を表示
- 「プラグインフォルダを開く」ボタン(E-1のユーザーディレクトリへのショートカット)

**完了条件**: 意図的に壊したダミープラグインを置いた状態で起動し、管理UIにエラー理由が表示される。

**注記(フェーズHとの接続)**: この新しいタブ自体のビジュアルは、フェーズHでまとめてスタイルを当てる。機能実装が先、見た目の調整は後。

---

### F-3. プラグイン開発者向けドキュメント

**やること**: `docs/plugin_development.md`(新規)を作成し、以下を記載する。

- 全 `register_*` フックの一覧とシグネチャ
- E-3で決定した依存ポリシー
- F-1のマニフェスト形式
- `FakeGraphicaPluginAPI`を使ったテストの書き方
- 7章-6/7-7の設計原則をプラグイン開発者にも適用する旨の注記
- **フェーズH完了後に追記する項目**: プラグイン製パネル(`register_panel`)が従うべきスタイルガイド(色トークン名、余白の基準単位など)。フェーズH完了までは「現時点ではQt標準スタイルに従う」とだけ書いておく

**完了条件**: このドキュメントだけを読んで、本体ソースを見ずに簡単なimporterプラグインが書ける状態になっていること。

---

### F-4. セーフモード起動

**やること**: 既存の`clean_exit`のQSettings追跡(2.1節/2.7節)を流用し、「前回異常終了を検出しました。プラグインを無効にして起動しますか?」ダイアログを追加。`--safe-mode`起動オプションも用意。

**完了条件**: 異常終了を意図的に発生させた次回起動でダイアログが出る。`--safe-mode`指定時は全プラグインがロードされない。

---

## フェーズG: 描画バックエンド差し替え(低優先度、骨組みのみ)

**やること**: `register_render_backend` は、7章-1で「将来LaTeX対応をプラグインで」と方針だけ決まっている機能。**本ロードマップでは、フックの型を定義するところまでで止め、実装(呼び出し箇所への組み込み)はしない。**

```python
def register_render_backend(self, name: str, backend: RenderBackend):
    """将来のusetex差し替え等のためのプレースホルダ。
    現時点ではgui/canvas.pyのレンダリング経路には未接続。
    接続時はMplCanvasの初期化経路を変更する大きめの変更になるため、
    別ロードマップとして切り出すこと。"""
```

**完了条件**: 型定義とdocstringのみ存在すればよい。`gui/canvas.py`への実際の組み込みはこのロードマップのスコープ外と明記する。

---

## フェーズH: GUIモダン化(QSSカスタマイズ)

**着手条件: フェーズA〜Gが全て完了していること。** このフェーズ単独で新しいセッション/新しいブランチを切ることを推奨する(`feature/gui-modernization`)。

### 方針: サードパーティテーマ(qt-material等)は採用しない。既存QSSの磨き込みで進める

**理由**:
1. `#46`(既存のフラット/ミニマルテーマ・ダークモード)は既に自前のQSS/設定の仕組みで実装済みと見られる。サードパーティの一括スタイルシートを上から重ねると、既存のダークモード切り替えロジック(2.7節)・カスタムウィジェット(ドック、クイックアクセスツールバー`#87`、色ピッカー、レイアウトエディタのドラッグハンドル)の見た目が意図せず上書きされるリスクが高い
2. 調査時点(2026年8月)で`qt-material`は直近1年ほど活発なメンテナンスが確認できず、将来のPySide6バージョンアップへの追従リスクがある
3. `matplotlib`の`FigureCanvasQTAgg`部分はQtのスタイルシートの対象外であり、どのみち`Dataset`/`ProjectModel`側の配色設定として別途ダークモード対応させる必要がある。「サードパーティテーマを入れれば全部モダンになる」わけではない

### H-0. 現状把握(このステップだけは先行着手可、H着手前でも良い)

**やること**: 既存のQSS実装の所在と構造を調査する。

- `#46`のQSSファイルがどこにあるか(`gui/resources/*.qss` 等)を特定
- ダーク/ライト切り替えがQSS切り替えなのか、パレット(`QPalette`)ベースなのか、あるいは両方の併用なのかを確認
- `matplotlib`側の配色(Figure背景・軸色・グリッド色)がダークモードとどう連動しているか(`rcParams`経由か、`Dataset`のスタイル設定経由か)を確認
- 既存のカスタムウィジェット一覧を洗い出す: ドック各種、クイックアクセスツールバー(`#87`)、色ピッカー、レイアウトエディタのハンドル、ミニマップ(`#83`)、エクスポートプレビューパネル、コマンドパレット(`#47`)

**成果物**: `docs/gui_style_audit.md`(新規)に上記の調査結果をまとめる。以降のH-1〜H-5はこの調査結果を土台に進める。

---

### H-1. デザイントークンの整理

**やること**: 色・余白・角丸・フォントサイズなどを、QSS文字列に直書きするのではなく、**一箇所の辞書/設定ファイルから生成する方式**に変える。

```python
# gui/theme/tokens.py (新規)
LIGHT_TOKENS = {
    "color.background": "#fafafa",
    "color.surface": "#ffffff",
    "color.primary": "#2563eb",
    "color.text": "#1a1a1a",
    "color.text_muted": "#6b7280",
    "color.border": "#e5e7eb",
    "radius.sm": "4px",
    "radius.md": "8px",
    "spacing.unit": "8px",
    # ...
}
DARK_TOKENS = {
    "color.background": "#1a1a1a",
    "color.surface": "#242424",
    "color.primary": "#3b82f6",
    "color.text": "#f0f0f0",
    "color.text_muted": "#9ca3af",
    "color.border": "#333333",
    "radius.sm": "4px",
    "radius.md": "8px",
    "spacing.unit": "8px",
}

def build_qss(tokens: dict) -> str:
    """QSSテンプレート(.qss.tpl)を読み込み、{{color.primary}}等のプレースホルダを
    tokensで置換して最終的なQSS文字列を返す。"""
```

- 既存の`#46`実装が既にトークン的な構造を持っているなら、それを踏襲・整理する形にする(全面書き直しはしない)
- **[要確認]** 既存のカスタムカラーパレット機能(2.7節、QSettingsに永続化)との関係を整理する。ユーザーが独自に選んだアクセントカラーがある場合、`tokens["color.primary"]`をそれで上書きできる設計にする

**完了条件**: `LIGHT_TOKENS`/`DARK_TOKENS`が一箇所に定義され、既存のQSS生成がこれを経由するようにリファクタされている。ダークモード切り替えの見た目が、リファクタ前と実質的に同一であること(回帰なし)。

---

### H-2. コンポーネント単位の磨き込み

**やること**: H-0で洗い出したカスタムウィジェット単位で、順に見た目を調整する。**全部を一度にやらず、1コンポーネントずつ差分として進める**(4.5節のプラグイン設計と同じ「増分実装」の考え方)。

推奨する着手順(見た目の印象への影響が大きい順):

1. メインツールバー・メニューバー
2. データセットリスト・データテーブル
3. ドック全般(境界線、タイトルバー、フォーカス時の強調)
4. ボタン・入力フィールド・コンボボックス(フラットデザインへの統一)
5. クイックアクセスツールバー(`#87`)
6. ダイアログ群(環境設定、エクスポート設定、フィットダイアログ等)
7. **プラグイン管理UI(F-2で追加されたタブ)** — ここで初めて他のダイアログと統一されたスタイルが当たる
8. ステータスバー・通知トースト類

**完了条件**: 各コンポーネントごとに、ライト/ダーク両モードでのスクリーンショットを`docs/gui_style_audit.md`に追記し、Before/Afterを記録する。既存のUIテスト(オフスクリーン)が壊れていないこと。

---

### H-3. matplotlib(Figure)側の配色連動

**やること**: グラフ描画領域の配色を、H-1のトークンと連動させる。

- ダークモード時のFigure背景・軸線・グリッド線・テキスト色を、`gui/theme/tokens.py`の値から導出する
- **[要確認]** 現状、ユーザーがデータセットごとに背景色を個別設定できる場合(グラフのAppearance設定)、アプリ全体のダークモード切り替えとどちらを優先するかのルールを明確にする(推奨: ユーザーが明示的に設定した色は保持し、未設定項目のみテーマに追従)
- 2.5節の「`ax.set_xscale`の罠」「`fig.clf()`後にAxesをキャッシュしない」といった既存の注意点は、配色変更の実装でも当然守る

**完了条件**: ダークモード切り替え時に、既存のグラフ(サンプルプロジェクト)の見た目が破綻しないこと。ユーザーが個別設定した色が上書きされないこと。

---

### H-4. アイコンセットの見直し(任意、優先度低)

**やること**: 既存のアイコンがモダン化に合わせて刷新が必要か判断する。刷新する場合、追加依存を増やさない範囲で行う(SVGアイコンをリソースとして同梱する形が無難。アイコンフォントライブラリの追加は新規依存になるため、必要性を吟味してから決める)。

**完了条件**: この判断自体を記録に残す(「今回は見送り」でも可)。見送る場合、その理由をコメントとして残す。

---

### H-5. 画像回帰テストの追加

**やること**: H-2のコンポーネント単位の変更が今後の開発で意図せず崩れないよう、主要画面のスクリーンショット比較テストを追加する。

- `pytest-mpl`または類似の仕組みで、代表的な画面(メインウィンドウ、環境設定ダイアログ、エクスポートプレビュー)のベースライン画像を固定
- CIで差分が閾値を超えたら警告(matplotlib本体のバージョン更新でグラフ描画が変わった場合と同じ考え方)

**完了条件**: `tests/test_gui_style_regression.py`が追加され、H-2完了時点の見た目がベースラインとして記録されている。

---

## 完了の全体基準

以下が全て満たされた時点で、このロードマップの目標を達成したとみなす。

### プラグインAPI(フェーズA〜G)

- [ ] `register_importer` / `register_exporter` / `register_processor` / `register_analyzer` / `register_panel` / `register_plot_type` が実装され、統一されたエラー隔離(A-2)を通る
- [ ] `FakeGraphicaPluginAPI`が全フックをカバーし、契約テスト(A-4)がCIで通る
- [ ] exe化したビルドで `%LOCALAPPDATA%\Graphica\plugins\` からプラグインをロードできる
- [ ] zipインストールのGUI導線がある
- [ ] 依存不足プラグインが安全にスキップされ、理由が表示される
- [ ] `plugin.json` マニフェストが必須化され、`api_version` チェックがある
- [ ] プラグイン管理UIから状態が見える
- [ ] `docs/plugin_development.md` が存在し、本体ソース非公開でも開発できる内容になっている
- [ ] 既存248件(2026-08-04時点)のテストが全てグリーンのまま(回帰なし)
- [ ] ダミープラグイン(importer 1件、processor 1件、panel 1件、plot_type 1件)を実際に作り、本体ソースを一切変更せずに動作することを確認済み

### GUIモダン化(フェーズH)

- [ ] `docs/gui_style_audit.md` に現状調査とBefore/Afterが記録されている
- [ ] `gui/theme/tokens.py` に色・余白・角丸等が一元化されている
- [ ] H-2で列挙した全コンポーネントのスタイル調整が完了している
- [ ] ダークモード切替時にグラフ(matplotlib側)の配色が破綻しない
- [ ] プラグイン管理UI(F-2)が他のダイアログと統一された見た目になっている
- [ ] 画像回帰テストが追加され、CIに組み込まれている
- [ ] `docs/plugin_development.md` にパネル用スタイルガイドが追記されている

---

## 実装時の注意(既存仕様からの継承事項)

- 2.8節の4つの罠(shiboken GC / restoreGeometry / Win32 DPI API / `_RestrictedUnpickler`の許可リスト)は、プラグインパネル(D-1)・GUI改修(フェーズH)いずれの作業でも同様に注意する
- 7章-5「マルチタブ・マルチウィンドウを前提に、新しいグローバル状態を追加する際はタブ間の二重登録・競合を要検討」は、`register_*`が全てプロセス全体で1回のみ実行される現行方針(4.5節)を維持する限り問題にならないが、D-1のパネルなど**タブごとにインスタンス化される要素**は各タブで個別に呼ばれる設計であることをコード上で明確にする
- 7章-2「plot_type関連の新機能は既存スタイル選択と排他にしない」原則は、D-2のプラグインplot_typeにも適用する
- 破壊的なシリアライズ変更(C-3で触れたDatasetへのプラグイン由来メタデータ追加等)は、本体側の `format_version` 導入が完了してから着手すること
- フェーズHの作業は、**新しいWin32 API呼び出しやカレントディレクトリ依存を一切追加しない**という2.8節-3の原則の対象外ではない。QSSやトークンの変更であっても、リソースパスの解決は必ず`resource_path()`(2.6節)を経由すること
