"""
メニューバーの中身の一覧表と、それを組み立てる関数。

項目は PlotterApp のメソッド名で呼び先を指す。コマンドパレット・クイックアクセス・ショートカット一覧は
メニューを辿って項目を集め、そのパス(「ファイル > エクスポート > 印刷(&R)...」)を識別子として保存するので、
文字列を変えると保存済みのピン留めが外れる。

PySide6 は、Python 側の参照が無くなった QMenu・menuAction・QAction を後から回収することがある
(メニューを辿ったとたん "already deleted" になる)。組み立てたものはすべて app._menu_keepalive に持たせる。
"""
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication

from graphica.core.i18n import tr
from graphica.core.version import APP_NAME
from graphica.gui.theme import apply_theme


@dataclass(frozen=True)
class Item:
    """
    メニューの1項目。slot は triggered(checkable なら toggled)に繋ぐメソッド名。
    attr を指定すると app にその名前で持たせる(ほかの場所から有効/無効やチェックを変えるもの)。
    checked は初めのチェック状態を持つ app の属性の点区切りの名前。after は作った後に呼ぶメソッド名。
    """
    text: str
    slot: str
    shortcut: object = None
    attr: Optional[str] = None
    checked: Optional[str] = None
    after: Optional[str] = None


@dataclass(frozen=True)
class Submenu:
    """on_show は開くたびに中身を作り直すメソッド名。fill_now なら作った時点でも一度呼ぶ。"""
    text: str
    items: tuple = ()
    attr: Optional[str] = None
    action_attr: Optional[str] = None
    on_show: Optional[str] = None
    fill_now: bool = False
    after: Optional[str] = None


@dataclass(frozen=True)
class DockToggle:
    """ドックの表示切り替え(ドック自身の toggleViewAction)。dock は app からの点区切りの名前。"""
    dock: str
    text: str


@dataclass(frozen=True)
class Call:
    """メニューとは別に、この位置で呼ぶ app のメソッド(組み立ての順番に意味があるもの)。"""
    method: str


@dataclass(frozen=True)
class Custom:
    """表で書けない項目。build(app, menu, keep) が menu に足す。"""
    build: Callable


SEPARATOR = object()


@dataclass(frozen=True)
class TopMenu:
    text: str
    attr: str
    items: tuple = ()
    action_attr: Optional[str] = None
    on_show: Optional[str] = None
    fill_now: bool = False


def _add_undo_redo(app, menu, keep):
    undo_action = app.undo_stack.createUndoAction(app, tr("元に戻す"))
    undo_action.setShortcut(QKeySequence.StandardKey.Undo)
    menu.addAction(undo_action)
    redo_action = app.undo_stack.createRedoAction(app, tr("やり直し"))
    redo_action.setShortcut(QKeySequence.StandardKey.Redo)
    menu.addAction(redo_action)
    keep.extend([undo_action, redo_action])


def _add_command_palette(app, menu, keep):
    # ウィンドウにも足して、メニューを開いていなくてもショートカットが効くようにする
    app.command_palette_action = QAction(tr("コマンドパレット(&K)..."), app)
    app.command_palette_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
    app.command_palette_action.triggered.connect(app._on_show_command_palette)
    app.addAction(app.command_palette_action)
    menu.addAction(app.command_palette_action)


FILE_MENU = TopMenu("ファイル(&F)", "_file_menu", (
    # Ctrl+O は「プロジェクトを開く」のもの
    Item("データファイルを開く(&D)...", "_on_add_dataset", attr="open_data_file_action"),
    SEPARATOR,
    Item("プロジェクトを開く(&O)...", "_on_load_project", QKeySequence.StandardKey.Open, attr="open_project_action"),
    Item("上書き保存(&P)", "_on_save_project", QKeySequence.StandardKey.Save, attr="save_project_action"),
    Item("名前を付けて保存(&A)...", "_on_save_project_as", QKeySequence.StandardKey.SaveAs,
         attr="save_project_as_action"),
    Item("クリップボードから貼り付け(&V)...", "_on_paste_data_from_clipboard"),
    Item("フォルダから一括インポート(&F)...", "_on_import_folder"),
    Submenu("最近使ったファイル", attr="recent_files_menu", action_attr="_recent_files_menu_action",
            after="_update_recent_files_menu"),
    Item("スタートアップ画面(&W)...", "_on_show_startup_screen"),
    SEPARATOR,
    Item("書式テンプレートを保存(&T)...", "_on_save_plot_template"),
    Item("書式テンプレートを適用(&A)...", "_on_load_plot_template"),
    SEPARATOR,
    Submenu("エクスポート", attr="_export_menu", action_attr="_export_menu_action", items=(
        # Ctrl+Shift+S は「名前を付けて保存」のもの(同じキーが2つあると Qt はどちらも発火させない)
        Item("名前を付けてエクスポート(&S)...", "_on_export_plot", attr="save_action"),
        # Ctrl+C は文字のコピーとぶつかるので割り当てない
        Item("グラフをコピー(&C)", "_on_copy_plot_to_clipboard"),
        Item("印刷(&R)...", "_on_print_plot", QKeySequence.StandardKey.Print, attr="print_action"),
        Item("バッチエクスポート(&B)...", "_on_batch_export"),
        Item("Pythonスクリプトとしてエクスポート...", "_on_export_python_script"),
        Item("LaTeX/Word用キャプションを生成...", "_on_generate_caption"),
        Item("実験レポートを生成 (HTML/PDF)...", "_on_generate_report"),
    )),
    SEPARATOR,
    Item("オートセーブ間隔を設定(&I)...", "_on_configure_autosave_interval", attr="autosave_interval_action",
         after="_update_autosave_menu_text"),
    Item("自動バックアップ履歴から復元(&H)...", "_on_show_autosave_history"),
    SEPARATOR,
    Item("設定・スタイルをエクスポート(&X)...", "_on_export_settings"),
    Item("設定・スタイルをインポート(&M)...", "_on_import_settings"),
))

EDIT_MENU = TopMenu("編集(&E)", "_edit_menu", (
    Custom(_add_undo_redo),
    SEPARATOR,
    Item("環境設定(&P)...", "_on_show_preferences"),
    Custom(_add_command_palette),
))

# 右クリックと同じ中身を開くたびに作る(片方だけに項目を足さないため)
DATASET_MENU = TopMenu("データセット(&D)", "_dataset_menu", action_attr="_dataset_menu_action",
                       on_show="_populate_dataset_menu", fill_now=True)

VIEW_MENU = TopMenu("表示(&V)", "_view_menu", (
    DockToggle("ui.control_dock_widget", "プロパティパネル"),
    DockToggle("export_preview_dock_widget", "エクスポートプレビュー"),
    DockToggle("residual_dock_widget", "残差プロット"),
    DockToggle("provenance_dock_widget", "処理履歴"),
    Item("ミニマップ(レンジスライダー)", "_on_toggle_minimap", attr="minimap_action", checked="minimap_visible"),
    Item("キャンバスを別ウィンドウに切り離す", "_on_toggle_canvas_detached", attr="canvas_detach_action",
         checked="canvas_detached"),
    Item("パネルラベルを自動表示 ((a)(b)(c)...)", "_on_toggle_panel_labels", attr="panel_labels_action",
         checked="project.panel_labels_enabled"),
    Item("色覚シミュレーションプレビュー...", "_on_show_cvd_simulation", attr="cvd_simulation_action"),
    Submenu("ドックレイアウト", attr="_dock_layout_menu", action_attr="_dock_layout_menu_action", items=(
        Item("現在のレイアウトを保存...", "_on_save_dock_layout_preset", attr="_save_layout_action"),
        Submenu("レイアウトを読み込み", attr="load_layout_menu", action_attr="_load_layout_menu_action",
                on_show="_populate_load_layout_menu"),
        SEPARATOR,
        Item("既定のレイアウトにリセット", "_on_reset_dock_layout", attr="_reset_layout_action"),
    )),
    # クイックアクセスのツールバーはここで作る(表示メニューの項目と同じ順番で組み立てる必要がある)
    Call("_create_quick_access_toolbar"),
    SEPARATOR,
    Item("ダークモード", "_on_toggle_dark_mode", attr="dark_mode_action", checked="canvas.dark_mode"),
))

HELP_MENU = TopMenu("ヘルプ(&H)", "_help_menu", (
    Item("mathtext リファレンス...", "_on_show_help"),
    Item("列計算機能 リファレンス...", "_on_show_calc_help"),
    Item("キーボードショートカット一覧...", "_on_show_shortcuts"),
    SEPARATOR,
    Item("診断情報をエクスポート...", "_on_export_diagnostic_bundle"),
    Item("アップデートを確認...", "_on_check_for_update"),
    SEPARATOR,
    Item("{app} について...", "_on_show_about"),
))


def _resolve(app, dotted):
    obj = app
    for part in dotted.split('.'):
        obj = getattr(obj, part)
    return obj


def _set_attr(app, name, value):
    if name:
        setattr(app, name, value)


def _add_items(app, menu, items, keep):
    for item in items:
        if item is SEPARATOR:
            menu.addSeparator()
        elif isinstance(item, Item):
            action = menu.addAction(tr(item.text).format(app=APP_NAME) if '{app}' in item.text else tr(item.text))
            if item.shortcut is not None:
                action.setShortcut(item.shortcut)
            slot = getattr(app, item.slot)
            if item.checked is not None:
                action.setCheckable(True)
                action.setChecked(_resolve(app, item.checked))
                action.toggled.connect(slot)
            else:
                action.triggered.connect(slot)
            keep.append(action)
            _set_attr(app, item.attr, action)
            if item.after:
                getattr(app, item.after)()
        elif isinstance(item, Submenu):
            submenu = menu.addMenu(tr(item.text))
            _hold_menu(app, submenu, item.attr, item.action_attr, keep)
            _add_items(app, submenu, item.items, keep)
            _connect_on_show(app, submenu, item.on_show, item.fill_now)
            if item.after:
                getattr(app, item.after)()
        elif isinstance(item, DockToggle):
            action = _resolve(app, item.dock).toggleViewAction()
            action.setText(tr(item.text))
            menu.addAction(action)
            keep.append(action)
        elif isinstance(item, Call):
            getattr(app, item.method)()
        elif isinstance(item, Custom):
            item.build(app, menu, keep)
        else:
            raise TypeError(f"メニューの一覧表に知らない要素があります: {item!r}")


def _hold_menu(app, menu, attr, action_attr, keep):
    # QMenu だけでなく、開くための menuAction も持つ(こちらが回収されるとメニューごと消える)
    keep.extend([menu, menu.menuAction()])
    _set_attr(app, attr, menu)
    _set_attr(app, action_attr, menu.menuAction())


def _connect_on_show(app, menu, on_show, fill_now):
    if on_show:
        menu.aboutToShow.connect(getattr(app, on_show))
        if fill_now:
            getattr(app, on_show)()


def _add_top_menu(app, menu_bar, top, keep):
    menu = menu_bar.addMenu(tr(top.text))
    _hold_menu(app, menu, top.attr, top.action_attr, keep)
    _add_items(app, menu, top.items, keep)
    _connect_on_show(app, menu, top.on_show, top.fill_now)
    return menu


def _add_plugin_menu(app, menu_bar, keep):
    """プラグインがメニュー項目・データ処理・解析・パネルのどれかを登録しているときだけ作る。"""
    api = app.plugin_api
    processors = api.get_processors()
    analyzers = api.get_analyzers()
    if not (api.menu_actions or processors or analyzers or app._plugin_panel_docks):
        return
    plugin_menu = menu_bar.addMenu(tr("プラグイン(&P)"))
    _hold_menu(app, plugin_menu, "_plugin_menu", None, keep)
    for menu_action in api.menu_actions:
        action = plugin_menu.addAction(menu_action.text)
        if menu_action.shortcut:
            action.setShortcut(QKeySequence(menu_action.shortcut))
        action.triggered.connect(lambda checked=False, ma=menu_action: app._run_plugin_menu_action(ma))
        keep.append(action)

    if processors:
        if api.menu_actions:
            plugin_menu.addSeparator()
        processing_menu = plugin_menu.addMenu(tr("データ処理"))
        _hold_menu(app, processing_menu, None, None, keep)
        by_category = {}
        for proc in processors:
            by_category.setdefault(proc.category, []).append(proc)
        for category in sorted(by_category.keys()):
            category_menu = processing_menu.addMenu(category)
            _hold_menu(app, category_menu, None, None, keep)
            for proc in sorted(by_category[category], key=lambda p: p.name):
                action = category_menu.addAction(proc.name)
                action.triggered.connect(lambda checked=False, p=proc: app.plugin_runs.run_processor(p))
                keep.append(action)

    if analyzers:
        if api.menu_actions or processors:
            plugin_menu.addSeparator()
        analysis_menu = plugin_menu.addMenu(tr("解析"))
        _hold_menu(app, analysis_menu, None, None, keep)
        for analyzer in sorted(analyzers, key=lambda a: a.name):
            action = analysis_menu.addAction(analyzer.name)
            action.triggered.connect(lambda checked=False, a=analyzer: app.plugin_runs.run_analyzer(a))
            keep.append(action)

    if app._plugin_panel_docks:
        if api.menu_actions or processors or analyzers:
            plugin_menu.addSeparator()
        panel_menu = plugin_menu.addMenu(tr("パネル"))
        _hold_menu(app, panel_menu, None, None, keep)
        for name in sorted(app._plugin_panel_docks.keys()):
            action = app._plugin_panel_docks[name].toggleViewAction()
            panel_menu.addAction(action)
            keep.append(action)


def build_menu_bar(app):
    """app のメニューバーを一覧表から組み立てる。__init__ から1回だけ呼ぶ。"""
    keep = []
    app._menu_keepalive = keep
    menu_bar = app.menuBar()
    for top in (FILE_MENU, EDIT_MENU, DATASET_MENU, VIEW_MENU):
        _add_top_menu(app, menu_bar, top, keep)
    # アプリ全体のスタイル(Fusion)とテーマを当て直す(何度呼んでも同じ)
    apply_theme(QApplication.instance(), app.canvas.dark_mode)
    _add_plugin_menu(app, menu_bar, keep)
    _add_top_menu(app, menu_bar, HELP_MENU, keep)
