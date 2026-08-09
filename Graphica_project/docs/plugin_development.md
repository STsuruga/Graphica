# Graphica プラグイン開発ガイド

このドキュメントは、Graphica本体のソースコードを読まなくても簡単なプラグインを
書けるようにするためのリファレンスです。想定読者はGraphicaのコードベースを
初めて見るサードパーティ開発者です。

Graphicaのプラグインは、アプリと同じPythonプロセス内で実行される通常のPython
パッケージです。サンドボックスは無いため、**信頼できる配布元のプラグインのみ
導入してください**(自分で書く分には問題ありません)。

---

## クイックスタート

プラグインは `plugins/` フォルダ配下の1サブフォルダとして配置します。最小構成は
次の2ファイルだけです。

```
plugins/
  hello_plugin/
    __init__.py
    plugin.json
```

`plugin.json`(マニフェスト。詳細は後述):

```json
{
  "name": "Hello Plugin",
  "version": "1.0",
  "api_version": "1.0"
}
```

`__init__.py`(トップレベルに `register(api)` 関数を1つ定義するだけ):

```python
from PySide6.QtWidgets import QMessageBox


def _say_hello(main_window):
    QMessageBox.information(main_window, "Hello Plugin", "Hello from a plugin!")


def register(api):
    api.register_menu_action("Say Hello", _say_hello, shortcut="Ctrl+Shift+H")
```

これだけで、Graphicaを起動すると「プラグイン」メニューに "Say Hello" が追加され、
クリックすると本文冒頭のメッセージが表示されます。以降の節で、この
`register(api)` に渡ってくる `api`(`GraphicaPluginAPI`)が提供する全フックを
説明します。

---

## プラグインディレクトリと探索の仕組み

Graphicaはプラグインを2箇所から探索します(`gui/main_window.py` の
`plugin_search_paths()`、項目E-1):

1. **ソースから `python main.py` で実行している場合のみ**:
   `Graphica_project/plugins/`(このリポジトリの `plugins/` フォルダ。開発者向け)
2. **常に**: `%LOCALAPPDATA%\Graphica\plugins`
   (`core/app_paths.py` の `get_user_plugins_dir()`。exe配布版でも書き込み可能な
   ユーザー専用フォルダ)

exe化されたビルド(`is_frozen()` が真、つまり `sys._MEIPASS` が存在する状態)
では1.は探索されません。exeを配布されたユーザーが自分でプラグインを追加する
場合は、必ず2.の `%LOCALAPPDATA%\Graphica\plugins` フォルダにプラグインの
サブフォルダを配置してもらうことになります。

同名のプラグインフォルダが両方の探索パスに存在する場合、探索順の早い方
(開発時なら1.)が採用され、もう一方は警告ログを出してスキップされます。

各サブフォルダの直下には `__init__.py` と `plugin.json` が必須です。
`__init__.py` が存在しないフォルダはそもそもプラグイン候補として認識されません。

### エンドユーザー向け: zipインストール

環境設定ダイアログの「プラグインをインストール」ボタンから、プラグインをzip
ファイルとしてインストールできます(`core/plugin_install.py`、項目E-2)。
zipは以下のいずれかのレイアウトに対応しています。

- (a) 単一のトップレベルフォルダの中に `__init__.py` がある
  (例: `my_plugin/__init__.py`)
- (b) `__init__.py` がzipルート直下にある(フォルダに包まれていない)

インストール先は常に `%LOCALAPPDATA%\Graphica\plugins` で、同名プラグインの
再インストール(上書き)にも対応しています。この処理はzipを展開して配置する
だけのローカル操作であり、ネットワーク経由でのダウンロードは行いません
(プラグイン自体をどこから入手するかはユーザーの責任です)。

プラグイン開発者としては、配布用に上記(a)または(b)のレイアウトでzip化して
おけば、この導線でそのままユーザーに配ってもらえます。

---

## `plugin.json`(マニフェスト)

各プラグインフォルダの直下に `plugin.json` を置く必要があります
(`core/plugin_manifest.py`、項目F-1)。**必須キーは `name` / `version` /
`api_version` の3つだけ**です。

```json
{
  "name": "JCAMP Importer",
  "version": "1.0",
  "api_version": "1.0",
  "author": "Your Name",
  "description": "JCAMP-DX file import support",
  "requires": ["numpy"],
  "entry_point": "graphica_plugin_jcamp:register"
}
```

- `name` (必須): プラグインの表示名。
- `version` (必須): プラグイン自身のバージョン文字列(任意の書式。Graphica側は
  中身を検証しません)。
- `api_version` (必須): このプラグインが対応するGraphicaプラグインAPIの
  バージョン。現在の値は **`"1.0"`**(`core/plugin_manifest.py` の
  `PLUGIN_API_VERSION`)。ここが一致しないプラグインは、`__init__.py` を
  importすることすら無く、ロード前に安全にスキップされます。
- `author` / `description` (任意、推奨): 診断・管理UI上での表示に使われます。
  無くてもロードは失敗しません。
- `requires` (任意): 依存ポリシー節を参照。
- `entry_point` (任意、**現時点では未使用**): 将来の拡張用に予約されている
  フィールドです。今は何を書いても実際の挙動には影響しません。ロード処理は
  常に「プラグインフォルダ直下の `__init__.py` にある `register(api)` 関数を
  呼ぶ」という固定の規約で動いており、`entry_point` の値を見て別のモジュールや
  関数を探すような実装にはまだなっていません。書いても無視されるだけなので、
  将来の互換性のために書いておいて構いませんが、「これで呼び出し先を変えられる」
  と誤解しないでください。

`plugin.json` が無い、JSONとして壊れている、JSONオブジェクトでない、必須キーが
欠けている、`api_version` が不一致——これらはいずれも例外を起こさず、該当
プラグインだけが警告ログとともにスキップされます(他のプラグインの読み込みや
アプリ本体の起動には影響しません)。

---

## 依存パッケージポリシー

プラグインが `import` できるのは、**標準ライブラリ**と、**Graphica本体が既に
同梱している依存パッケージ**だけです(`requirements.txt` より):

- `PySide6`
- `matplotlib`
- `numpy`
- `pandas`
- `scipy`
- `openpyxl`

これ以外の外部パッケージ(例: `requests`)への依存は避けてください。exe配布版
にはこれらしか同梱されておらず、プラグインが独自に追加パッケージを
`pip install` させることは想定していません(pip版のGraphicaであれば、
ユーザー自身がその環境に追加パッケージを入れれば動作させられます)。

`plugin.json` の任意キー `"requires"` に、そのプラグインが必要とする
importできるモジュール名のリストを書いておくと、Graphica起動時に
`importlib.util.find_spec()` で存在確認が行われます(`core/plugin_api.py` の
`_check_plugin_dependencies`)。1つでも見つからないモジュールがあれば、
そのプラグイン全体が「依存パッケージが不足しています」という明確なメッセージ
とともにスキップされます(クラッシュはしません)。

```json
{
  "name": "SciPy Fitter",
  "version": "1.0",
  "api_version": "1.0",
  "requires": ["scipy"]
}
```

---

## `register_*` フック一覧

以下すべて、`register(api)` の中で `api.register_xxx(...)` として呼び出します。
**どのフックも呼び出し自体は例外を送出しません** — 登録に失敗した場合は
戻り値が `False` になり、失敗の詳細はログとプラグイン管理UI側に記録される
だけです(詳しくは「エラー処理と診断」の節を参照)。戻り値が要らなければ
無視して構いません。

### `register_fit_function(name, func, param_names, p0=None)`

カーブフィットの選択肢に、プラグイン提供の関数を追加します。

- `name` (str): フィットタイプのコンボボックスに表示される名前。組み込みの
  フィットタイプ名や他のプラグインの登録名と重複できません。
- `func` (callable): `scipy.optimize.curve_fit` にそのまま渡せる
  `f(x, *params)` 形式の関数。
- `param_names` (list[str]): パラメータ名のリスト(結果表示に使われます)。
- `p0` (list[float] | callable | None): 初期値のリスト、または
  `(x_data, y_data) -> list[float]` を返す関数。省略時は全パラメータが `1.0`
  として初期化されます。

```python
import numpy as np

def double_exp(x, a, b, c, d):
    return a * np.exp(-b * x) + c * np.exp(-d * x)

def double_exp_p0(x_data, y_data):
    amp = float(np.nanmax(np.abs(y_data))) or 1.0
    return [amp, 1.0, amp, 0.1]

def register(api):
    api.register_fit_function(
        "Double Exponential Decay", double_exp, ["a", "b", "c", "d"], p0=double_exp_p0
    )
```

登録すると、カーブフィットのフィットタイプ選択コンボボックスに `name` の値が
追加され、ユーザーが選択すると `func`/`param_names`/`p0` を使ったフィットが
実行されます。

### `register_menu_action(text, callback, shortcut=None)`

「プラグイン」メニューにアクションを追加します。

- `text` (str): メニューに表示するテキスト。
- `callback` (callable): クリック時に呼ばれる関数。呼び出し時に、**現在
  アクティブな `PlotterApp` インスタンスが1引数として渡されます**。データセット
  一覧やキャンバスへは、そこから公開属性経由でアクセスしてください
  (例: `main_window._get_current_dataset()`)。
- `shortcut` (str | None): キーボードショートカット(例: `"Ctrl+Shift+P"`)。

```python
def register(api):
    api.register_menu_action("Show current dataset name", _show_name, shortcut="Ctrl+Alt+N")

def _show_name(main_window):
    ds = main_window._get_current_dataset()
    ...
```

> **重要**: `callback` に渡ってくる `main_window` は**呼び出し時点で
> アクティブなタブ**です。Graphicaは複数タブ(複数の独立した `PlotterApp`)を
> 同時に開けるため、`register(api)` の実行時にたまたま存在したタブへの参照を
> どこかにキャッシュして使い回す、というような実装は避けてください。

### `register_importer(extensions, loader, *, name=None, priority=0)`

データファイルの読み込みに、プラグイン提供のローダーを追加します。登録した
拡張子は、データ追加のファイルダイアログとドラッグ&ドロップ一括取込の両方で
自動的に受け付けられるようになります。

- `extensions` (list[str]): 対応する拡張子のリスト(例: `[".jdx", ".dx"]`。
  先頭のピリオドは省略可、大文字小文字も区別されません)。
- `loader` (callable): ファイルパス(str)を受け取り、`pandas.DataFrame` を
  返す関数。
- `name` (str | None): エラーメッセージ等に表示する名前。省略時は登録元
  プラグイン名が使われます。
- `priority` (int): 同じ拡張子に複数のプラグインが登録した場合の優先順位
  (値が大きいほど優先。同点の場合は登録順)。

現時点では**単一の `pandas.DataFrame` を返すローダーのみ**サポートされます
(複数シート/複数データセットを一度に返す形式は未対応です)。

```python
import pandas as pd

def load_jdx(filepath):
    # 実際にはここでJCAMP-DXパーサ等を呼ぶ
    return pd.DataFrame({"x": [...], "y": [...]})

def register(api):
    api.register_importer([".jdx", ".dx"], load_jdx, name="JCAMP Importer", priority=10)
```

### `register_exporter(format_name, extension, writer, *, name=None)`

プロットのエクスポート形式に、プラグイン提供の書き出し処理を追加します。
バッチエクスポートの「形式」コンボボックスと、単発エクスポートの保存ダイアログ
の両方から選べるようになります。

- `format_name` (str): エクスポート形式の選択肢に表示される名前(例:
  `"MyFormat"`)。バッチエクスポートダイアログの形式コンボの選択値としてそのまま
  使われます。
- `extension` (str): 出力ファイルの拡張子(先頭ピリオドは省略可)。
- `writer` (callable): `(matplotlib.figure.Figure, 出力パス: str)` を受け取り、
  ファイルへの書き出しを行う関数。戻り値は使われません。
- `name` (str | None): エラーメッセージ等に表示する名前。省略時は登録元
  プラグイン名。

```python
def write_myformat(fig, out_path):
    fig.savefig(out_path)  # 実際には独自形式の書き出し処理

def register(api):
    api.register_exporter("MyFormat", ".myf", write_myformat)
```

### `register_processor(name, fn, *, category="general", param_schema=None)`

「現在のデータセット」に対する**非破壊の**データ処理を、プラグインメニューの
「データ処理」配下に追加します。

- `name` (str): メニューに表示される名前。他のプラグインの同名処理と重複
  できません。
- `fn` (callable): `(Dataset, dict) -> Dataset`。第2引数は `param_schema` から
  自動生成されたフォームで入力された値の辞書(`param_schema` 省略時は空の辞書)。
- `category` (str): メニューでのグルーピングに使うカテゴリ名。
- `param_schema` (list[dict] | None): パラメータ入力フォームの自動生成に使う
  スキーマ。書式は後述。省略時はパラメータ入力なしで即実行されます。

**`fn` は元の `Dataset` を一切変更せず、新しい `Dataset` を返してください。**
実行結果の新規Datasetの追加はGraphica側でUndo/Redoスタックにpushされるため、
プラグイン側はUndoを一切意識する必要がありません(詳しくは「プラグイン作者
向けの設計原則」の節を参照)。

```python
import numpy as np
from core.dataset import Dataset

def smooth(dataset, params):
    window = params["window"]
    new_df = dataset.df.copy()
    new_df["y"] = new_df["y"].rolling(window, center=True, min_periods=1).mean()
    return Dataset(name=f"{dataset.name} (smoothed)", df=new_df, color=dataset.color)

def register(api):
    api.register_processor(
        "Moving Average",
        smooth,
        category="Smoothing",
        param_schema=[
            {"name": "window", "label": "Window size", "type": "int",
             "default": 5, "min": 1, "max": 999},
        ],
    )
```

### `register_analyzer(name, fn, *, output_kind="table", param_schema=None)`

「現在のデータセット」を解析し、**構造化された結果**(表・注釈・派生データセット)
を返すフックを、プラグインメニューの「解析」配下に追加します。

- `name` (str): メニューに表示される名前。他のプラグインの同名解析と重複
  できません。
- `fn` (callable): `(Dataset, dict) -> AnalysisResult`。第2引数は
  `register_processor` と同様、`param_schema` から自動生成されたフォームの
  入力値。
- `output_kind` (str): 解析結果の主な性質を表す分類用の文字列。現状は表示上の
  分類用途のみで、動作は変わりません(例: `"table"`)。
- `param_schema` (list[dict] | None): `register_processor` と同じ形式。

`fn` の戻り値は `core/plugin_types.py` の `AnalysisResult`(dataclass)です。

```python
@dataclass
class AnalysisResult:
    table: object = None             # pandas.DataFrame | None
    annotations: list | None = None  # list[dict] | None
    new_datasets: list | None = None # list[Dataset] | None
```

- `table`: `pandas.DataFrame`。結果ダイアログに表として表示され、CSV出力も
  できます。
- `annotations`: 現在の軸に注釈として追加される辞書のリスト。
- `new_datasets`: 非破壊に(Undo対応で)追加される新規 `Dataset` のリスト。

3つとも省略可能(`None`)で、必要なものだけ埋めれば構いません。3つ全部を
使う例:

```python
import pandas as pd
from core.plugin_types import AnalysisResult
from core.dataset import Dataset

def find_peak(dataset, params):
    x, y = dataset.x_data, dataset.y_data
    idx = y.argmax()
    peak_table = pd.DataFrame({"x": [x[idx]], "y": [y[idx]]})
    annotation = {"x": x[idx], "y": y[idx], "text": "peak"}
    baseline = Dataset(name=f"{dataset.name} (baseline)", df=dataset.df.assign(y=0), color=dataset.color)
    return AnalysisResult(
        table=peak_table,
        annotations=[annotation],
        new_datasets=[baseline],
    )

def register(api):
    api.register_analyzer("Peak Finder", find_peak, output_kind="table")
```

#### `param_schema` の書式(`register_processor`/`register_analyzer` 共通)

`param_schema` は辞書のリストで、各要素はパラメータ入力フォームの1行に対応
します(自動生成は `gui/dialogs.py` の `PluginParamDialog` が行います)。各要素
のキー:

| キー | 必須 | 説明 |
|---|---|---|
| `name` | 必須 | パラメータ名。`fn` の第2引数の辞書のキーになる |
| `label` | 任意 | フォームに表示するラベル(省略時は `name`) |
| `type` | 任意(省略時 `"str"`) | `"int"` / `"float"` / `"str"` / `"bool"` / `"choice"` |
| `default` | 任意 | 初期値 |
| `min` / `max` | `int`/`float`のみ | 値の範囲 |
| `choices` | `choice`のみ | 選択肢のリスト |
| `decimals` | `float`のみ | 小数点以下桁数(省略時4) |

```python
param_schema = [
    {"name": "window", "label": "Window size", "type": "int", "default": 5, "min": 1, "max": 999},
    {"name": "threshold", "label": "Threshold", "type": "float", "default": 0.1, "decimals": 3},
    {"name": "mode", "label": "Mode", "type": "choice", "default": "linear", "choices": ["linear", "log"]},
    {"name": "normalize", "label": "Normalize", "type": "bool", "default": True},
]
```

### `register_panel(name, widget_factory, *, area="right")`

プラグイン製のドックパネルを追加します。

- `name` (str): パネルのタイトル(ドックのタイトルバー・表示メニューに使われる)。
  他のプラグインの同名パネルと重複できません。
- `widget_factory` (callable): `(ProjectModel, QUndoStack) -> QWidget`。
- `area` (str): `"right"` / `"left"` / `"top"` / `"bottom"` のいずれか。

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class MyPanel(QWidget):
    def __init__(self, project, undo_stack):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Datasets: {len(project.datasets)}"))

def register(api):
    api.register_panel("My Panel", lambda project, undo_stack: MyPanel(project, undo_stack), area="right")
```

**重要な実行時の挙動**(`gui/main_window.py` を確認):

- `widget_factory` は**タブ(`PlotterApp` インスタンス)ごとに、タブの構築時に
  個別に1回だけ**呼ばれます。開いているタブが3つあれば `widget_factory` は
  3回呼ばれ、それぞれ独立した `QWidget` インスタンスが3つ作られます。
- `widget_factory` は**実際の `QWidget` サブクラスのインスタンスを返す必要が
  あります**。`QWidget` でない値を返した場合、または呼び出し中に例外が
  発生した場合は、そのタブでのみパネルの構築がスキップされます(警告ログに
  記録されるだけで、他のパネル・そのタブ自体の起動・他のタブへは影響しません)。
  つまり1タブでの構築失敗が、アプリ全体やそのタブの起動を止めることは
  ありません。
- 追加されたドックの初期状態は**非表示**です。表示状態はQSettingsのドック
  レイアウト復元(前回起動時の状態)に委ねられます。

### `register_plot_type(type_name, drawer, *, requires_2d=False)`

データセットのプロット種別(`plot_type`)に、プラグイン提供の描画方法を
追加します。既存5種類(`'Line'` / `'Scatter'` / `'Line+Scatter'` / `'Area'` /
`'Bar'`)の描画コードは変更されず、未知の `plot_type` に遭遇した場合の
フォールバック経路として動作します。

- `type_name` (str): `ds.plot_type` に設定される値。データセットプロパティ
  ダイアログのプロット種別コンボボックスにも表示されます(組み込み5種類・他の
  プラグインの同名と重複できません)。
- `drawer` (callable): `(Dataset, Axes, x_data, y_data) -> Artist | None`。
  `x_data`/`y_data` は、既にウォーターフォールのオフセット等が適用済みの
  「描画用配列」です(`ds.x_data`/`ds.y_data` そのものとは限りません)。
  戻り値の `Artist` は `ds.artist` にキャッシュされ、凡例表示に使われます
  (不要なら `None` を返して構いません)。
- `requires_2d` (bool): 現状は表示上の分類用途のみ(将来の2Dマップ系プラグイン
  向けの予約フラグ)。

```python
def draw_step(dataset, ax, x_data, y_data):
    (artist,) = ax.step(x_data, y_data, where="mid", color=dataset.color, label=dataset.name)
    return artist

def register(api):
    api.register_plot_type("Step", draw_step)
```

**既知の制限**: ウォーターフォールの隠蔽描画・グラデーション等、組み込み
プロット種別に対する追加オーバーレイ機能は、プラグイン製 `plot_type` には
**自動適用されません**(`gui/canvas.py` の `_draw_data` は未知の `plot_type` を
見つけると、このレジストリを引いて `drawer` をそのまま呼ぶだけの独立した経路
です)。それらの見た目が必要な場合は `drawer` の中で自前に実装してください。

---

## プラグイン作者向けの設計原則

Graphica本体の設計方針は、プラグインコードにもそのまま当てはまります。

**1. 非破壊: `register_processor` は入力の `Dataset` を書き換えない**

Graphica本体のデータ処理(規格化、Savitzky-Golayフィルタ等)はすべて、元の
データセットをそのまま残し、加工結果を新規データセットとして追加します。
これは型システムで強制されているわけではなく、**規約として** `fn` の実装者
(プラグイン作者)が守るべきルールです。

```python
# 悪い例: 入力Datasetを直接書き換えている
def bad_smooth(dataset, params):
    dataset.df["y"] = dataset.df["y"].rolling(5, center=True).mean()
    return dataset  # 同じオブジェクトを返しているので、元のデータが失われる

# 良い例: 新しいDatasetを作って返す
def good_smooth(dataset, params):
    new_df = dataset.df.copy()
    new_df["y"] = new_df["y"].rolling(5, center=True).mean()
    return Dataset(name=f"{dataset.name} (smoothed)", df=new_df, color=dataset.color)
```

新規Datasetの追加はGraphica側でUndo/Redoコマンドとしてスタックにpushされる
ため、`good_smooth` のように新しい `Dataset` さえ正しく返せば、Undo対応は
自動的についてきます。逆に元のオブジェクトを書き換えると、Undoで復元される
はずの「元の状態」自体が汚染されてしまいます。

**2. 構造化データ: `register_analyzer` の結果は文字列に詰め込まない**

解析結果を1本のフォーマット済み文字列(例: `f"peak at x={x}, y={y}"`)として
返すのではなく、`AnalysisResult` の `table`/`annotations`/`new_datasets` という
構造化されたフィールドに分けて返してください。これにより、結果ダイアログでの
表形式表示・CSV出力・注釈のプロットへの反映・派生データセットのUndo管理が、
プラグイン側で何もしなくても本体側の既存機能でそのまま動きます。文字列に
詰め込んでしまうと、これらの機能が一切使えなくなります。

---

## i18n(多言語化)についての制限

プラグイン側からGraphica本体に渡す表示名(`register_panel` のパネルタイトル、
`register_menu_action` のメニューテキスト等)は、**現時点では英語表記のみ
サポート**です。Graphica本体の翻訳レイヤー(`core/i18n.py` の `tr()`)には
統合されません。

これは意図的な設計判断です(`core/plugin_api.py` モジュールdocstringの
「D-3」の項を参照)。もしプラグインが渡す文字列を `tr()` の辞書キーとして
解決しようとすると、プラグイン作者が本体の翻訳辞書の中身を意識しなければ
ならなくなり、プラグインと本体が過剰に結合してしまいます。プラグイン
エコシステムが育ち、多言語対応の需要が具体化した段階で、プラグイン側にも
言語別文字列を渡せる仕組み(例: `name` 引数を `dict` にする等)を改めて
検討する予定であり、今のところの制約であって恒久的な仕様ではありません。

---

## プラグインをテストする(`FakeGraphicaPluginAPI`)

Graphica本体(GUI/QApplication)を一切起動せずに、`register(api)` が期待通りの
フックを登録しているかを単体テストできます。`core/plugin_testing.py` の
`FakeGraphicaPluginAPI` は、実際の `GraphicaPluginAPI`(`core/plugin_api.py`)と
**同じpublicメソッドシグネチャ**を持つテストダブルです(Graphica本体側の契約
テスト `tests/test_plugin_api_contract.py` が、新しいフックが追加されるたびに
本物とこのフェイクのシグネチャが一致し続けることを機械的に保証しています。
プラグイン作者はこの仕組みの中身を知る必要はなく、「フェイクは信用してよい」
とだけ理解していれば十分です)。

例: 先ほどの `hello_plugin` を、Qtを一切importせずにpytestでテストする。

```python
# my_plugin/__init__.py
def _say_hello(main_window):
    ...  # 実際にはダイアログを出す等

def register(api):
    api.register_menu_action("Say Hello", _say_hello, shortcut="Ctrl+Shift+H")
```

```python
# tests/test_my_plugin.py
from core.plugin_testing import FakeGraphicaPluginAPI
from my_plugin import register

def test_register_adds_hello_menu_action():
    api = FakeGraphicaPluginAPI()
    register(api)

    assert len(api.menu_actions) == 1
    text, callback, shortcut = api.menu_actions[0]
    assert text == "Say Hello"
    assert shortcut == "Ctrl+Shift+H"
    assert callable(callback)
```

`register_importer`/`register_exporter`/`register_processor`/`register_analyzer`/
`register_panel`/`register_plot_type` も同様に、`api.importers` /
`api.exporters` / `api.processors` / `api.analyzers` / `api.panels` /
`api.plot_types` という辞書に登録内容がそのまま格納されるので、そこを
`assert` すれば検証できます(それぞれの辞書の形は `core/plugin_testing.py`
の各 `register_xxx` 実装を参照してください)。

---

## エラー処理と診断

Graphicaのプラグイン機構は「1箇所の失敗が全体を巻き込まない」ことを一貫した
方針にしています。

- **マニフェスト不正**: `plugin.json` が無い/壊れている/`api_version`不一致
  → そのプラグインの `__init__.py` はimportすらされずスキップ。
- **`register()` 実行時の例外**: そのプラグイン全体の読み込みが失敗として記録
  され、他のプラグインの読み込みには影響しません。
- **依存パッケージ不足**: `plugin.json` の `requires` に列挙したモジュールが
  見つからない場合、明確なメッセージとともにそのプラグインだけスキップ。
- **個々の `register_xxx` 呼び出しの失敗**: 1つのプラグインが複数のフックを
  登録する場合、そのうち1つが例外を投げても、他のフックの登録は続行されます
  (フック単位での隔離)。
- **`register_panel` の `widget_factory` がタブごとに失敗**: そのタブでだけ
  パネルがスキップされ、他のタブ・アプリ本体には影響しません。

いずれの場合も**ダイアログは出ず、アプリはクラッシュしません**。つまり、
プラグインにタイプミス等の軽微な不具合があると、目に見えるエラーなしに
「何も起きない」ように見えることがあります。プラグインが期待通りに動作
しない場合は、まず `graphica.log`(`%LOCALAPPDATA%\Graphica` 配下)を確認して
ください。詳細な警告メッセージがそこに記録されています。

ユーザーに動作報告してもらう際は、環境設定から出力できる診断情報バンドル
(`core/diagnostics.py` の `build_diagnostic_bundle`。OS/Pythonバージョン・
主要依存パッケージのバージョン等をまとめたzip)も、プラグインが原因の不具合
かどうかを切り分ける手がかりになります。

---

## プラグイン製パネルのスタイルガイド

現時点(GUIモダン化フェーズ、トラック2)は未着手のため、`register_panel` で
追加するパネルの見た目については、**特別な指定はありません。標準のQtウィジェット
スタイルにそのまま従ってください。** トラック2完了後、本体の色トークン・
余白の基準単位などのデザイン規約が確定次第、この節に追記します。
