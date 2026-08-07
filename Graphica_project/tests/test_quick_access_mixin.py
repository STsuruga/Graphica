# tests/test_quick_access_mixin.py
"""
項目87 「クイックアクセスのカスタムツールバー」 (gui/mixins/quick_access_mixin.py) の
テスト。tests/test_main_window.py の _make_isolated_plotter_app と同じ方針
(QSettingsを一時ファイルにリダイレクト)で、PlotterAppのインスタンス化と
QSettingsへの永続化をテストする。
"""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from gui.dialogs import QuickAccessManagerDialog
from core.plugin_api import GraphicaPluginAPI


def _make_isolated_plotter_app(tmp_path, monkeypatch, settings_path=None, plugin_api=None):
    """
    QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る。

    settings_path を指定すると、複数のPlotterAppインスタンス間で同じ設定
    ファイルを共有できる(再起動をまたいだ永続化のラウンドトリップを
    テストするため)。plugin_api を渡すと、実際のファイルシステム上の
    プラグインディレクトリを使わずに、load_plugins_once() が返す
    GraphicaPluginAPI を差し替えられる。
    """
    if settings_path is None:
        settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)

    if plugin_api is not None:
        monkeypatch.setattr(
            main_window_module, "load_plugins_once",
            lambda plugins_dir, disabled_names=None: plugin_api
        )

    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window, settings_path


def _find_action(window, text_fragment):
    """_collect_menu_actions() から、指定した文字列を含むテキストの最初のアクションを探す"""
    for path, action in window._collect_menu_actions():
        if text_fragment in path[-1]:
            return path, action
    raise AssertionError(f"'{text_fragment}' を含むアクションが見つかりませんでした")


def test_quick_access_toolbar_is_not_movable(tmp_path, monkeypatch):
    """
    項目H-2-1(GUIモダン化): Qt標準のツールバー移動グリップ(ドラッグ用の
    ハンドル)はフラット/ミニマルテーマと視覚的に馴染まないため、
    setMovable(False)で無効化している。
    """
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.quick_access_toolbar.isMovable() is False


def test_pin_action_adds_it_to_the_toolbar(tmp_path, monkeypatch):
    """アクションをピン留めすると、クイックアクセスツールバーに追加されること"""
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)

    path, action = _find_action(window, "コマンドパレット")
    ident = " > ".join(path)

    assert action not in window.quick_access_toolbar.actions()
    assert not window.is_quick_access_pinned(ident)

    window.pin_quick_access_action(ident, action)

    assert action in window.quick_access_toolbar.actions()
    assert window.is_quick_access_pinned(ident)


def test_unpin_action_removes_it_from_the_toolbar(tmp_path, monkeypatch):
    """ピン留めしたアクションを解除すると、ツールバーから取り除かれること"""
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)

    path, action = _find_action(window, "コマンドパレット")
    ident = " > ".join(path)
    window.pin_quick_access_action(ident, action)
    assert action in window.quick_access_toolbar.actions()

    window.unpin_quick_access_action(ident)

    assert action not in window.quick_access_toolbar.actions()
    assert not window.is_quick_access_pinned(ident)
    assert ident not in window._get_pinned_quick_access_ids()


def test_pinned_set_persists_to_qsettings(tmp_path, monkeypatch):
    """ピン留めした識別子がQSettingsに書き込まれ、直接読み出せること"""
    window, settings_path = _make_isolated_plotter_app(tmp_path, monkeypatch)

    path, action = _find_action(window, "ダークモード")
    ident = " > ".join(path)
    window.pin_quick_access_action(ident, action)

    raw_settings = QSettings(settings_path, QSettings.Format.IniFormat)
    stored = raw_settings.value("quick_access_pinned_actions", [])
    if isinstance(stored, str):
        stored = [stored]
    assert ident in list(stored)


def test_pinned_actions_restore_into_a_fresh_plotter_app_instance(tmp_path, monkeypatch):
    """
    1つ目のPlotterAppでピン留めした内容が、同じQSettingsを見る2つ目の
    (新規に作られた、メニューも作り直された)PlotterAppインスタンスの
    ツールバーに復元されること。複数タブ(項目40)は各タブが独自のメニュー/
    QActionを持つため、これは「QSettingsの永続化データだけを共有し、
    各タブが自分自身のメニューから同じ識別子のアクションを見つけて
    復元する」という設計の検証を兼ねる。
    """
    settings_path = str(tmp_path / "shared_settings.ini")
    window1, _ = _make_isolated_plotter_app(tmp_path, monkeypatch, settings_path=settings_path)

    path, action1 = _find_action(window1, "ダークモード")
    ident = " > ".join(path)
    window1.pin_quick_access_action(ident, action1)
    window1.close()

    window2, _ = _make_isolated_plotter_app(tmp_path, monkeypatch, settings_path=settings_path)

    assert window2.is_quick_access_pinned(ident)
    restored_texts = [a.text() for a in window2.quick_access_toolbar.actions()]
    assert action1.text() in restored_texts
    # 別インスタンスなので、実際に復元されたQActionは別オブジェクトのはず
    assert window2._quick_access_actions[ident] is not action1
    window2.close()


def test_stale_pinned_id_is_skipped_without_crashing(tmp_path, monkeypatch):
    """
    存在しない(例: プラグインが削除された後の)識別子がQSettingsに
    残っていても、復元時にエラーにならず単に無視されること。
    """
    settings_path = str(tmp_path / "stale_settings.ini")
    raw_settings = QSettings(settings_path, QSettings.Format.IniFormat)
    raw_settings.setValue(
        "quick_access_pinned_actions",
        ["存在しないメニュー(X) > 存在しないアクション", ],
    )
    raw_settings.sync()

    # クラッシュしないことそのものがテストの主眼
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch, settings_path=settings_path)

    # ツールバーには「管理...」ボタンとその直後の区切り線しか無いはず
    # (存在しないIDに対応するアクションは1つも追加されていない)。
    non_separator_actions = [a for a in window.quick_access_toolbar.actions() if not a.isSeparator()]
    assert non_separator_actions == [window.quick_access_manage_action]
    assert window._quick_access_actions == {}
    window.close()


def test_plugin_registered_action_can_be_pinned(tmp_path, monkeypatch):
    """プラグインが register_menu_action() で追加したアクションも、通常のアクションと同様にピン留めできること"""
    fake_api = GraphicaPluginAPI()
    fake_api.register_menu_action("プラグインのテストアクション", lambda main_window: None)

    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch, plugin_api=fake_api)

    # 「プラグイン」メニューが作られ、_collect_menu_actions() 経由で拾えること
    path, action = _find_action(window, "プラグインのテストアクション")
    assert path[0].startswith("プラグイン")
    ident = " > ".join(path)

    window.pin_quick_access_action(ident, action)

    assert action in window.quick_access_toolbar.actions()
    assert window.is_quick_access_pinned(ident)
    window.close()


def test_context_menu_resolves_the_action_under_the_cursor(tmp_path, monkeypatch):
    """
    メニュー項目を右クリックしたときの対象解決ロジック
    (_resolve_quick_access_menu_target) が、_collect_menu_actions() と
    同じパスでそのアクションを見つけられること。
    """
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)

    menu = window._edit_menu
    # QMenuは実際に画面へポップアップされて初めて実サイズにレイアウトされる。
    # テストでは開かないため、actionAt()がsizeHint()基準の座標を正しく
    # 拾えるよう、明示的に実サイズをsizeHint()へ合わせておく。
    menu.resize(menu.sizeHint())
    target_action = window.command_palette_action
    rect = menu.actionGeometry(target_action)
    assert not rect.isNull()

    result = window._resolve_quick_access_menu_target(menu, rect.center())
    assert result is not None
    ident, path, action = result
    assert action is target_action

    collected_paths = [p for p, a in window._collect_menu_actions() if a is target_action]
    assert path in collected_paths


def test_quick_access_pinnable_menus_have_custom_context_menu_policy(tmp_path, monkeypatch):
    """全ての最上位メニューに、右クリックでのピン留め用コンテキストメニューが設置されていること"""
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)
    for menu in window._quick_access_pinnable_menus():
        assert menu.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_manage_dialog_checkbox_pins_and_unpins_action(tmp_path, monkeypatch):
    """管理ダイアログのチェックボックスの切り替えで、ピン留め/解除が実際に反映されること"""
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)

    def toggle(ident, path, checked):
        if checked:
            for p, action in window._collect_menu_actions():
                if p == path:
                    window.pin_quick_access_action(ident, action)
                    break
        else:
            window.unpin_quick_access_action(ident)

    dialog = QuickAccessManagerDialog(
        window._collect_menu_actions, window.is_quick_access_pinned, toggle, window
    )
    try:
        target_item = None
        for i in range(dialog.list_widget.count()):
            item = dialog.list_widget.item(i)
            if "コマンドパレット" in item.text():
                target_item = item
                break
        assert target_item is not None
        assert target_item.checkState() == Qt.CheckState.Unchecked

        target_item.setCheckState(Qt.CheckState.Checked)
        assert window.command_palette_action in window.quick_access_toolbar.actions()

        target_item.setCheckState(Qt.CheckState.Unchecked)
        assert window.command_palette_action not in window.quick_access_toolbar.actions()
    finally:
        dialog.close()


def test_manage_dialog_search_filters_the_list(tmp_path, monkeypatch):
    """管理ダイアログの検索欄で一覧が絞り込まれること"""
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)

    dialog = QuickAccessManagerDialog(
        window._collect_menu_actions, window.is_quick_access_pinned, lambda *a: None, window
    )
    try:
        total_count = dialog.list_widget.count()
        assert total_count > 1

        dialog.search_edit.setText("コマンドパレット")
        filtered_count = dialog.list_widget.count()
        assert 0 < filtered_count < total_count
        for i in range(filtered_count):
            assert "コマンドパレット" in dialog.list_widget.item(i).text()
    finally:
        dialog.close()
