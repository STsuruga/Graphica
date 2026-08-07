# core/plugin_api.py
"""
Graphicaのプラグイン機構。

設計方針:
- プラグインは `plugins/` ディレクトリ(resource_path("plugins")、実行ファイルの
  隣。無ければ起動時に自動作成する)配下の、各サブフォルダとして配置する。
  各サブフォルダは `__init__.py` を持つ通常のPythonパッケージで、以下の2つを
  トップレベルに定義する:

    PLUGIN_INFO = {"name": "...", "version": "...", "author": "...",
                    "description": "..."}

    def register(api: GraphicaPluginAPI) -> None:
        ...  # api.register_fit_function(...) 等を呼ぶ

- プラグインはアプリと同じPythonプロセス内で実行される、サンドボックスなしの
  通常のPythonコードである。信頼できる配布元のプラグインのみ導入すること
  (models/project.py の pickle 復元における _RestrictedUnpickler の
  ドキュメントコメントと同様の注意が必要)。
- 1つのプラグインの読み込み/登録に失敗しても、他のプラグインの読み込みや
  アプリ本体の起動を止めない(例外はログに記録し、そのプラグインだけを
  スキップする)。
- 拡張ポイントは現時点では「カーブフィット関数の追加」「メニューへの
  アクション追加」「データインポーターの追加」「エクスポート形式の追加」
  「データ処理の追加」「解析の追加」「パネルの追加」「プロット種別の追加」の8つ。
  今後も同様のパターン(register_xxx メソッドを追加する)で拡張できる。
- 【項目D-3・方針決定】UIフック(register_panel/register_menu_action等)が
  プラグイン側から渡す表示名(パネルのタイトル、メニュー項目名等)は、
  現時点では英語表記のみサポートする。core/i18n.py の tr() による翻訳統合は
  行わない(プラグイン側の文字列をtr()の辞書キーとして解決しようとすると、
  プラグイン作者が本体の翻訳辞書の存在を意識する必要が生じてしまい、
  過剰な結合になるため)。プラグインエコシステムが実際に育ち、多言語対応の
  需要が具体化してから、プラグイン側にも言語別文字列を渡せる仕組み
  (例: name引数をdictにする等)を改めて検討する。それまではこの制約を
  docs/plugin_development.md(将来のF-3)にも明記すること。
"""
import importlib
import importlib.util
import logging
import os
import sys

from core.analysis import register_fit_function
from core.plugin_types import (
    PluginAnalyzer, PluginExporter, PluginHookKind, PluginImporter,
    PluginPanel, PluginPlotType, PluginProcessor, PluginRegistrationError,
)

logger = logging.getLogger(__name__)

PLUGIN_MANIFEST_ATTR = "PLUGIN_INFO"
PLUGIN_REGISTER_FUNC = "register"


def _normalize_extension(extension):
    """拡張子を先頭ピリオド付き・小文字の形に揃える(例: "JDX" -> ".jdx")。"""
    ext = extension.lower()
    return ext if ext.startswith('.') else '.' + ext


def _check_plugin_dependencies(info):
    """PLUGIN_INFOのrequiresキー(あれば)を見て、importできないモジュール名を列挙して返す(項目E-3)。"""
    missing = []
    for module_name in info.get("requires", []) or []:
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    return missing


class PluginLoadError(Exception):
    """プラグインの読み込み/登録に失敗したことを表す(呼び出し側でキャッチして続行する用途)"""


class GraphicaPluginAPI:
    """
    プラグインの `register(api)` に渡されるオブジェクト。
    プラグインが触れて良い範囲を明示的なメソッド越しに限定するための窓口
    (Datasetやウィジェットの内部実装へ直接アクセスさせない)。
    """

    def __init__(self, main_window=None):
        self._main_window = main_window
        self._menu_actions = []  # (text, callback, shortcut) のリスト。メニュー構築側が読む。
        self._importers = {}  # 拡張子(".jdx"等) -> list[PluginImporter](priority降順)
        self._exporters = {}  # format_name.lower() -> PluginExporter
        self._processors = {}  # name -> PluginProcessor
        self._analyzers = {}  # name -> PluginAnalyzer
        self._panels = {}  # name -> PluginPanel
        self._plot_types = {}  # type_name -> PluginPlotType

        # フック登録の失敗をプラグイン単位ではなくフック単位で隔離するための
        # 記録先(フェーズA-2)。1プラグインが複数のフックを登録する場合、
        # そのうち1つが失敗しても他のフックの登録は継続する。
        # F-2(プラグイン管理UI)から読み出される想定。
        self._registration_errors = []  # list[PluginRegistrationError]
        # 現在register(api)を実行中のプラグイン名。PluginManager.load_all()が
        # 各プラグインのregister()を呼ぶ直前に差し替える。register_xxx呼び出し
        # 自体はどのプラグインが呼んでいるか知らないため、この経由で伝える。
        self._current_plugin_name = "(不明なプラグイン)"

    def _safe_register(self, hook_kind, fn, *args, **kwargs):
        """
        フック登録処理(fn)を実行し、例外が起きてもプラグイン全体を巻き込まず
        このフック1件の失敗として隔離する(フェーズA-2)。

        Returns:
            bool: 登録に成功したかどうか。
        """
        try:
            fn(*args, **kwargs)
            return True
        except Exception as e:
            self._registration_errors.append(
                PluginRegistrationError(self._current_plugin_name, hook_kind, str(e), e)
            )
            logger.warning(
                "[plugin:%s] %s の登録に失敗しました: %s",
                self._current_plugin_name, hook_kind.value, e,
            )
            return False

    def register_fit_function(self, name, func, param_names, p0=None):
        """
        カーブフィットの選択肢に、プラグイン提供の関数を追加する。

        Args:
            name (str): フィットタイプのコンボボックスに表示される名前
                (組み込みのフィットタイプ名や他のプラグイン名と重複不可)。
            func (callable): scipy.optimize.curve_fit に渡せる f(x, *params) 形式の関数。
            param_names (list[str]): パラメータ名のリスト(結果表示に使われる)。
            p0 (list[float] | callable | None): 初期値のリスト、または
                (x_data, y_data) -> list[float] を返す関数。省略時は全て1.0。
        """
        return self._safe_register(
            PluginHookKind.FIT_FUNCTION, register_fit_function, name, func, param_names, p0=p0
        )

    def register_menu_action(self, text, callback, shortcut=None):
        """
        「プラグイン」メニューにアクションを追加する。

        Args:
            text (str): メニューに表示するテキスト。
            callback (callable): クリック時に呼ばれる関数。呼び出し時に
                現在アクティブな PlotterApp インスタンスを1引数として渡す
                (データセット一覧やキャンバスへは、そこから通常のpublicな
                属性経由でアクセスする)。
            shortcut (str | None): キーボードショートカット(例: "Ctrl+Shift+P")。
        """
        return self._safe_register(
            PluginHookKind.MENU_ACTION, self._menu_actions.append, (text, callback, shortcut)
        )

    def register_importer(self, extensions, loader, *, name=None, priority=0):
        """
        データファイルの読み込みに、プラグイン提供のローダーを追加する(項目B-1)。
        登録した拡張子は、データ追加のファイルダイアログ・ドラッグ&ドロップ一括取込
        (項目77)の両方で自動的に受け付けられるようになる(gui/workers.pyの
        read_data_file()がファイル読み込みの入口で優先的に参照する)。

        現時点では単一の pandas.DataFrame を返すローダーのみサポートする
        (複数シート/複数データセットを一度に返す形式は未対応。将来的な拡張点)。

        Args:
            extensions (list[str]): 対応する拡張子のリスト(例: [".jdx", ".dx"]、
                先頭のピリオドは省略可)。
            loader (callable): ファイルパス(str)を受け取り、pandas.DataFrame を
                返す関数。
            name (str | None): エラーメッセージ等に表示する名前
                (省略時は登録元のプラグイン名)。
            priority (int): 同じ拡張子に複数のプラグインが登録した場合の優先順位
                (値が大きいほど優先。同点の場合は登録順)。
        """
        return self._safe_register(
            PluginHookKind.IMPORTER, self._do_register_importer, extensions, loader,
            name=name or self._current_plugin_name, priority=priority,
        )

    def _do_register_importer(self, extensions, loader, *, name, priority):
        for ext in extensions:
            ext = _normalize_extension(ext)
            importer = PluginImporter(extension=ext, loader=loader, name=name, priority=priority)
            bucket = self._importers.setdefault(ext, [])
            bucket.append(importer)
            # 優先度の高い順に並べ替える(同点は登録順を保つ安定ソート)
            bucket.sort(key=lambda imp: -imp.priority)

    def get_importer_for_extension(self, extension):
        """
        指定した拡張子に対して最も優先度の高い登録済みインポーターを返す
        (登録が無ければNone)。

        Args:
            extension (str): 先頭ピリオドの有無・大文字小文字を問わない。
        """
        bucket = self._importers.get(_normalize_extension(extension))
        return bucket[0] if bucket else None

    def get_importer_extensions(self):
        """登録済みインポーターが対応する拡張子の一覧(重複無し、ソート済み)。"""
        return sorted(self._importers.keys())

    def register_exporter(self, format_name, extension, writer, *, name=None):
        """
        プロットのエクスポート形式に、プラグイン提供の書き出し処理を追加する
        (項目B-2)。バッチエクスポートの「形式」コンボボックス・単発エクスポートの
        保存ダイアログの両方から選べるようになる。

        Args:
            format_name (str): エクスポート形式の選択肢に表示される名前
                (例: "MyFormat")。BatchExportDialogの形式コンボの選択値として
                そのまま使われる。
            extension (str): 出力ファイルの拡張子(先頭ピリオドは省略可)。
            writer (callable): (matplotlib.figure.Figure, 出力パス:str) を受け取り、
                ファイルへの書き出しを行う関数。戻り値は使われない。
            name (str | None): エラーメッセージ等に表示する名前
                (省略時は登録元のプラグイン名)。
        """
        return self._safe_register(
            PluginHookKind.EXPORTER, self._do_register_exporter, format_name, extension, writer,
            name=name or self._current_plugin_name,
        )

    def _do_register_exporter(self, format_name, extension, writer, *, name):
        self._exporters[format_name.lower()] = PluginExporter(
            format_name=format_name, extension=_normalize_extension(extension), writer=writer, name=name
        )

    def get_exporter(self, format_name):
        """指定した形式名(大文字小文字を問わない)に対応する登録済みエクスポーターを返す。"""
        return self._exporters.get(format_name.lower())

    def get_exporter_for_extension(self, extension):
        """指定した拡張子に対応する登録済みエクスポーターを返す(無ければNone)。"""
        ext = _normalize_extension(extension)
        for exporter in self._exporters.values():
            if exporter.extension == ext:
                return exporter
        return None

    def get_exporters(self):
        """登録済みエクスポーターの一覧。"""
        return list(self._exporters.values())

    def register_processor(self, name, fn, *, category="general", param_schema=None):
        """
        「現在のデータセット」に対する非破壊のデータ処理を、プラグインメニューの
        「データ処理」配下に追加する(項目C-1)。

        fn は元のDatasetを一切変更せず、新しいDatasetを返すこと(規格化・
        Savitzky-Golay等の既存機能と同じ非破壊パターン)。実行結果の新規
        Datasetの追加はAddDatasetCommand経由でUndo/Redoスタックにpushされる
        ため、プラグイン側はUndoを一切意識する必要が無い。

        Args:
            name (str): メニューに表示される名前(他のプラグインの同名処理と
                重複不可)。
            fn (callable): (Dataset, dict) -> Dataset。第2引数はparam_schema
                から自動生成されたフォームで入力された値の辞書
                (param_schema省略時は空の辞書)。
            category (str): メニューでのグルーピングに使うカテゴリ名。
            param_schema (list[dict] | None): パラメータ入力フォームの自動生成に
                使うスキーマ。各要素は少なくとも "name"(パラメータ名)と
                "type"("int"/"float"/"str"/"bool"/"choice")を持つ辞書。
                例: [{"name": "window", "label": "窓幅", "type": "int",
                      "default": 5, "min": 1, "max": 999}]
                省略時はパラメータ入力無しで即実行される。
        """
        return self._safe_register(
            PluginHookKind.PROCESSOR, self._do_register_processor, name, fn,
            category=category, param_schema=param_schema, plugin_name=self._current_plugin_name,
        )

    def _do_register_processor(self, name, fn, *, category, param_schema, plugin_name):
        if name in self._processors:
            raise ValueError(f"データ処理 '{name}' は既に登録されています。")
        self._processors[name] = PluginProcessor(
            name=name, fn=fn, category=category, param_schema=list(param_schema or []),
            plugin_name=plugin_name,
        )

    def get_processors(self):
        """登録済みデータ処理の一覧。"""
        return list(self._processors.values())

    def get_processor_categories(self):
        """登録済みデータ処理のカテゴリ一覧(重複無し、ソート済み)。"""
        return sorted({p.category for p in self._processors.values()})

    def register_analyzer(self, name, fn, *, output_kind="table", param_schema=None):
        """
        「現在のデータセット」を解析し、構造化された結果(表・注釈・派生データセット)
        を返すフックを、プラグインメニューの「解析」配下に追加する(項目C-2)。

        Args:
            name (str): メニューに表示される名前(他のプラグインの同名解析と
                重複不可)。
            fn (callable): (Dataset, dict) -> AnalysisResult。第2引数は
                register_processorと同様、param_schemaから自動生成された
                フォームの入力値。
            output_kind (str): 解析結果の主な性質を表す分類用の文字列
                (現状は表示上の分類用途のみで、動作は変えない)。
            param_schema (list[dict] | None): register_processorと同じ形式。
        """
        return self._safe_register(
            PluginHookKind.ANALYZER, self._do_register_analyzer, name, fn,
            output_kind=output_kind, param_schema=param_schema, plugin_name=self._current_plugin_name,
        )

    def _do_register_analyzer(self, name, fn, *, output_kind, param_schema, plugin_name):
        if name in self._analyzers:
            raise ValueError(f"解析 '{name}' は既に登録されています。")
        self._analyzers[name] = PluginAnalyzer(
            name=name, fn=fn, output_kind=output_kind, param_schema=list(param_schema or []),
            plugin_name=plugin_name,
        )

    def get_analyzers(self):
        """登録済み解析処理の一覧。"""
        return list(self._analyzers.values())

    def register_panel(self, name, widget_factory, *, area="right"):
        """
        プラグイン製のドックパネルを追加する(項目D-1)。register_dockという
        別フックには分離せず、この1つに統合する(当初検討した分離案は
        区別する実益が薄いため不採用)。

        widget_factoryはタブ(PlotterAppインスタンス)ごとに、そのタブの
        構築時に個別に呼ばれる。register_menu_action同様、GraphicaPluginAPI
        自身は特定のタブへの参照を保持しない(shibokenのGC罠・古いタブへの
        参照固定を避けるため、CLAUDE.md参照)。

        Args:
            name (str): パネルのタイトル(ドックのタイトルバー・表示メニューに
                使われる。他のプラグインの同名パネルと重複不可)。
            widget_factory (callable): (ProjectModel, QUndoStack) -> QWidget。
                呼び出しはタブごとに1回。例外を投げた場合、そのタブでは
                パネルを作らずログに警告を残す(他のパネル・タブ自体の
                起動は継続する)。
            area (str): "right"/"left"/"top"/"bottom"のいずれか。実際の
                Qt.DockWidgetAreaへのマッピングはGUI側で行う(coreは
                PySide6に依存しないため)。
        """
        return self._safe_register(
            PluginHookKind.PANEL, self._do_register_panel, name, widget_factory,
            area=area, plugin_name=self._current_plugin_name,
        )

    def _do_register_panel(self, name, widget_factory, *, area, plugin_name):
        if name in self._panels:
            raise ValueError(f"パネル '{name}' は既に登録されています。")
        self._panels[name] = PluginPanel(
            name=name, widget_factory=widget_factory, area=area, plugin_name=plugin_name,
        )

    def get_panels(self):
        """登録済みパネルの一覧。"""
        return list(self._panels.values())

    def register_plot_type(self, type_name, drawer, *, requires_2d=False):
        """
        データセットのプロット種別(plot_type)に、プラグイン提供の描画方法を
        追加する(項目D-2)。既存5種類('Line'/'Scatter'/'Line+Scatter'/'Area'/
        'Bar')の描画コードは変更しない。gui/canvas.pyは未知のplot_typeに
        遭遇した際にこのレジストリを引く、というフォールバック経路のみが
        新設される(既存分岐を壊さない増分実装)。

        Args:
            type_name (str): ds.plot_typeに設定する値。データセットプロパティ
                ダイアログのプロット種別コンボボックスにも表示される
                (組み込み5種類・他のプラグインの同名と重複不可)。
            drawer (callable): (Dataset, Axes, x_data, y_data) -> Artist | None。
                x_data/y_dataは既にウォーターフォールのオフセット等が適用
                済みの描画用配列(ds.x_data/ds.y_dataそのものではない場合が
                ある)。返り値のArtistはds.artistにキャッシュされ、凡例表示に
                使われる(不要ならNoneを返してよい)。ウォーターフォールの
                隠蔽描画・グラデーション等の追加オーバーレイは組み込み
                plot_typeのみの対応であり、プラグイン製plot_typeには
                自動適用されない(既知の制限)。
            requires_2d (bool): 現状は表示上の分類用途のみ(将来の2Dマップ系
                プラグインplot_type向けの予約フラグ)。
        """
        return self._safe_register(
            PluginHookKind.PLOT_TYPE, self._do_register_plot_type, type_name, drawer,
            requires_2d=requires_2d, plugin_name=self._current_plugin_name,
        )

    def _do_register_plot_type(self, type_name, drawer, *, requires_2d, plugin_name):
        if type_name in self._plot_types:
            raise ValueError(f"プロット種別 '{type_name}' は既に登録されています。")
        self._plot_types[type_name] = PluginPlotType(
            type_name=type_name, drawer=drawer, requires_2d=requires_2d, plugin_name=plugin_name,
        )

    def get_plot_types(self):
        """登録済みプロット種別の一覧。"""
        return list(self._plot_types.values())

    def get_plot_type(self, type_name):
        """指定した名前に対応する登録済みプロット種別を返す(無ければNone)。"""
        return self._plot_types.get(type_name)

    @property
    def menu_actions(self):
        return list(self._menu_actions)

    @property
    def registration_errors(self):
        """このプロセスで発生した、フック単位の登録失敗の一覧。"""
        return list(self._registration_errors)


class PluginManager:
    """
    plugins/ ディレクトリ配下のプラグインを検出・読み込み・登録するマネージャー。
    """

    def __init__(self, plugins_dir):
        # plugins_dir は単一パス(str、既存の呼び出し元との後方互換)か、
        # 優先順位つきの複数パス(list[str]、項目E-1)のどちらでも受け付ける。
        self.plugins_dirs = [plugins_dir] if isinstance(plugins_dir, str) else list(plugins_dir)
        # 読み込み結果の記録: 各要素は
        # {"name": フォルダ名, "info": PLUGIN_INFO or None, "error": str or None}
        self.loaded_plugins = []
        # discover_plugin_dirs() が最後に見つけた、プラグイン名 -> 発見元ディレクトリ。
        # _load_module() が同じ呼び出し内でどのディレクトリから読むかを引くのに使う。
        self._plugin_locations = {}

    def discover_plugin_dirs(self):
        """
        plugins_dirs を優先順位順に走査し、__init__.py を持つサブディレクトリ名の
        一覧を返す(戻り値は従来通りフォルダ名のリスト、項目E-1)。
        複数の探索パスに同名のプラグインフォルダが存在する場合、先に見つかった
        方(＝探索順の早いパス)を採用し、後から見つかった方はログに警告を
        出してスキップする。
        """
        self._plugin_locations = {}
        names = []
        for plugins_dir in self.plugins_dirs:
            if not os.path.isdir(plugins_dir):
                continue
            for entry in sorted(os.listdir(plugins_dir)):
                entry_path = os.path.join(plugins_dir, entry)
                if not (os.path.isdir(entry_path) and os.path.exists(os.path.join(entry_path, "__init__.py"))):
                    continue
                if entry in self._plugin_locations:
                    logger.warning(
                        "プラグイン '%s' は複数の探索パスに存在するため、'%s' のものを使用します"
                        "('%s' は無視されます)。",
                        entry, self._plugin_locations[entry], plugins_dir,
                    )
                    continue
                self._plugin_locations[entry] = plugins_dir
                names.append(entry)
        return names

    def _load_module(self, plugin_name):
        """1つのプラグインパッケージを importlib で読み込み、モジュールオブジェクトを返す"""
        base_dir = self._plugin_locations[plugin_name]
        init_path = os.path.join(base_dir, plugin_name, "__init__.py")
        module_name = f"graphica_plugin_{plugin_name}"
        spec = importlib.util.spec_from_file_location(
            module_name, init_path,
            submodule_search_locations=[os.path.join(base_dir, plugin_name)],
        )
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"プラグイン '{plugin_name}' のモジュール仕様を作成できませんでした。")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            sys.modules.pop(module_name, None)
            raise PluginLoadError(f"プラグイン '{plugin_name}' の読み込み中にエラー: {e}") from e
        return module

    def load_all(self, api):
        """
        plugins_dir 配下の全プラグインを読み込み、register(api) を呼び出す。
        1つのプラグインで例外が発生しても、他のプラグインの読み込みは継続する。
        """
        self.loaded_plugins = []
        for plugin_name in self.discover_plugin_dirs():
            record = {"name": plugin_name, "info": None, "error": None}
            try:
                module = self._load_module(plugin_name)

                info = getattr(module, PLUGIN_MANIFEST_ATTR, None)
                if not isinstance(info, dict):
                    raise PluginLoadError(
                        f"プラグイン '{plugin_name}' に {PLUGIN_MANIFEST_ATTR} (dict) がありません。"
                    )
                record["info"] = info

                missing = _check_plugin_dependencies(info)
                if missing:
                    raise PluginLoadError(
                        f"プラグイン '{plugin_name}' の依存パッケージが不足しています: "
                        f"{', '.join(missing)}。プラグインは本体に同梱済みの依存"
                        "(numpy/pandas/scipy/matplotlib/PySide6等)のみ使用できます。"
                        "pip版のGraphicaであれば追加の依存パッケージを導入して動作させられます。"
                    )

                register_func = getattr(module, PLUGIN_REGISTER_FUNC, None)
                if not callable(register_func):
                    raise PluginLoadError(
                        f"プラグイン '{plugin_name}' に {PLUGIN_REGISTER_FUNC}(api) 関数がありません。"
                    )
                # register_xxx呼び出し自身はどのプラグインが呼んでいるか知らないため、
                # ここで現在実行中のプラグイン名をapiに伝える(_safe_register参照)。
                api._current_plugin_name = plugin_name
                register_func(api)

            except Exception as e:
                record["error"] = str(e)
                logger.warning("プラグイン '%s' の読み込みに失敗しました: %s", plugin_name, e)

            self.loaded_plugins.append(record)

        return self.loaded_plugins


# ★ フィット関数のレジストリ (core/analysis.py の _PLUGIN_FIT_FUNCTIONS) は
# プロセス全体で1つのモジュールレベル辞書であり、複数プロジェクトタブ(項目40)
# では PlotterApp インスタンスがタブごとに作られるため、タブが増えるたびに
# 同じプラグインを読み込むと「既に登録されています」エラーになってしまう。
# そのためプラグインの読み込み・登録はプロセス全体で1度だけ行い、以降の呼び出しは
# 同じ GraphicaPluginAPI インスタンス(と、そのmenu_actions)を使い回す。
_singleton_api = None
_singleton_manager = None


def load_plugins_once(plugins_dir):
    """
    plugins_dir 配下のプラグインを、プロセス内で最初の呼び出し時にのみ読み込む。
    2回目以降の呼び出しは、キャッシュされた GraphicaPluginAPI をそのまま返す
    (新しいタブが開かれるたびに再読み込み・再登録が走らないようにするため)。
    """
    global _singleton_api, _singleton_manager
    if _singleton_api is not None:
        return _singleton_api

    dirs = [plugins_dir] if isinstance(plugins_dir, str) else list(plugins_dir)
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    _singleton_api = GraphicaPluginAPI()
    _singleton_manager = PluginManager(plugins_dir)
    _singleton_manager.load_all(_singleton_api)
    return _singleton_api


def get_loaded_plugin_records():
    """最後に load_plugins_once() で読み込まれたプラグインの一覧を返す(未読み込みならNone)"""
    return None if _singleton_manager is None else list(_singleton_manager.loaded_plugins)


def get_plugin_registration_errors():
    """
    フック単位の登録失敗の一覧を返す(未読み込みならNone、フェーズA-2)。
    プラグイン全体としては読み込みに成功していても、個別のregister_xxx呼び出しが
    失敗している場合はここに記録される(get_loaded_plugin_recordsのerrorには現れない)。
    """
    return None if _singleton_api is None else _singleton_api.registration_errors


def get_plugin_api():
    """
    現在ロード済みの GraphicaPluginAPI を返す(未読み込みなら None)。
    plugins_dir を知らない呼び出し元(gui/workers.py 等、UIから離れた場所)向けの
    アクセサ。load_plugins_once() と異なり、未読み込みでも新規ロードは行わない。
    """
    return _singleton_api


def get_registered_importer_extensions():
    """登録済みインポーターが対応する拡張子の一覧(未読み込みなら空リスト、項目B-1)。"""
    return _singleton_api.get_importer_extensions() if _singleton_api is not None else []


def get_registered_exporters():
    """登録済みエクスポーターの一覧(未読み込みなら空リスト、項目B-2)。"""
    return _singleton_api.get_exporters() if _singleton_api is not None else []


def get_registered_processors():
    """登録済みデータ処理の一覧(未読み込みなら空リスト、項目C-1)。"""
    return _singleton_api.get_processors() if _singleton_api is not None else []


def get_registered_analyzers():
    """登録済み解析処理の一覧(未読み込みなら空リスト、項目C-2)。"""
    return _singleton_api.get_analyzers() if _singleton_api is not None else []


def get_registered_panels():
    """登録済みパネルの一覧(未読み込みなら空リスト、項目D-1)。"""
    return _singleton_api.get_panels() if _singleton_api is not None else []


def get_registered_plot_types():
    """登録済みプロット種別の一覧(未読み込みなら空リスト、項目D-2)。"""
    return _singleton_api.get_plot_types() if _singleton_api is not None else []
