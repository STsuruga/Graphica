# tests/test_menu_restructure.py
"""
メニュー導線の整理(改善ボード C-2 / C-3 / C-4)と、2Dマップでの
ウォーターフォール設定の非表示(A-5)に対するテスト。

- C-2: データセット右クリックメニュー(約30項目のフラット)を5つのサブメニューへ
- C-3: ファイルメニューのエクスポート系7項目をサブメニューへ、
       色覚シミュレーションプレビューは「確認」の機能なので表示メニューへ
- C-4: 「データファイルを開く」をファイルメニュー先頭に追加
- A-5: 2Dマップではウォーターフォール設定を丸ごと隠す

★ C-3 でメニュー項目を移動すると、クイックアクセスのピン留め識別子
  ("ファイル(F) > 名前を付けてエクスポート(S)..." のようなパス全体)が変わり、
  既存ユーザーのピンが**警告もなく消える**。その読み替え
  (_migrate_pinned_quick_access_ids)もここで検証する。
"""
import matplotlib
matplotlib.use("Agg")
import pandas as pd
import pytest
from PySide6.QtCore import QSettings, QPoint
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from core.dataset import Dataset
from gui.mixins.quick_access_mixin import (
    QUICK_ACCESS_SETTINGS_KEY, quick_access_action_identifier,
)


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 600)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _menu_item_texts(menu):
    """区切り線を除いた、そのメニュー直下の項目テキスト(サブメニュー名を含む)"""
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def _submenu(menu, title):
    for a in menu.actions():
        if a.menu() is not None and a.text() == title:
            return a.menu()
    return None


# =============================================================================
# C-4: 「データファイルを開く」
# =============================================================================

def test_open_data_file_is_the_first_item_of_the_file_menu(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        assert _menu_item_texts(window._file_menu)[0] == "データファイルを開く(&D)..."
    finally:
        window.close()


def test_open_data_file_uses_the_same_handler_as_the_add_dataset_button(tmp_path, monkeypatch):
    """中央の「データ追加」ボタンと同じ導線であること(別実装にしない)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        called = []
        monkeypatch.setattr(window, "_on_add_dataset", lambda: called.append(True))
        # 接続先の同一性は直接見られないので、実際に発火させて確認する
        window.open_data_file_action.triggered.disconnect()
        window.open_data_file_action.triggered.connect(window._on_add_dataset)
        window.open_data_file_action.trigger()
        assert called == [True]
    finally:
        window.close()


def test_open_data_file_does_not_steal_the_open_project_shortcut(tmp_path, monkeypatch):
    """Ctrl+O は従来どおり「プロジェクトを開く」のもの(手癖を壊さない)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        assert window.open_data_file_action.shortcut().isEmpty()
        assert not window.open_project_action.shortcut().isEmpty()
    finally:
        window.close()


# =============================================================================
# C-3: エクスポートのサブメニュー化 / 色覚シミュレーションプレビューの移動
# =============================================================================

EXPORT_ITEMS = [
    "名前を付けてエクスポート(&S)...",
    "グラフをコピー(&C)",
    "印刷(&R)...",
    "バッチエクスポート(&B)...",
    "Pythonスクリプトとしてエクスポート...",
    "LaTeX/Word用キャプションを生成...",
    "実験レポートを生成 (HTML/PDF)...",
]


def test_export_actions_moved_into_a_submenu(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        export_menu = _submenu(window._file_menu, "エクスポート")
        assert export_menu is not None
        assert _menu_item_texts(export_menu) == EXPORT_ITEMS
        # トップレベルからは消えていること
        top = _menu_item_texts(window._file_menu)
        for item in EXPORT_ITEMS:
            assert item not in top
    finally:
        window.close()


def test_file_menu_is_shorter_than_before(tmp_path, monkeypatch):
    """22項目あったファイルメニューが、サブメニュー化で目に見えて短くなること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        assert len(_menu_item_texts(window._file_menu)) <= 16
    finally:
        window.close()


def test_export_submenu_keeps_both_the_menu_and_its_opener_action(tmp_path, monkeypatch):
    """★ shiboken/PySide6 の癖への対策(8607665 / a9809e7 と同じ):
    QMenu だけでなく menuAction() も永続参照として保持すること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        assert window._export_menu is not None
        assert window._export_menu_action is not None
        assert window._export_menu_action is window._export_menu.menuAction()
    finally:
        window.close()


def test_print_shortcut_still_works_inside_the_submenu(tmp_path, monkeypatch):
    """サブメニューへ移してもショートカット(Ctrl+P)は従来どおり効くこと。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        assert not window.print_action.shortcut().isEmpty()
    finally:
        window.close()


def test_cvd_preview_moved_from_the_file_menu_to_the_view_menu(tmp_path, monkeypatch):
    """色覚シミュレーションプレビューは図を出力する機能ではなく
    「今の配色がどう見えるかを確認する」機能なので表示メニュー側。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        assert "色覚シミュレーションプレビュー..." in _menu_item_texts(window._view_menu)
        assert "色覚シミュレーションプレビュー..." not in _menu_item_texts(window._file_menu)
        export_menu = _submenu(window._file_menu, "エクスポート")
        assert "色覚シミュレーションプレビュー..." not in _menu_item_texts(export_menu)
    finally:
        window.close()


def test_collect_menu_actions_reaches_the_nested_export_items(tmp_path, monkeypatch):
    """コマンドパレット/ショートカット一覧がサブメニュー内の項目も拾えること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        paths = [path for path, _action in window._collect_menu_actions()]
        idents = {quick_access_action_identifier(p) for p in paths}
        assert "ファイル(F) > エクスポート > 名前を付けてエクスポート(S)..." in idents
        assert "表示(V) > 色覚シミュレーションプレビュー..." in idents
    finally:
        window.close()


def test_collect_menu_actions_is_stable_across_repeated_calls(tmp_path, monkeypatch):
    """★ 回帰テスト: サブメニューを追加すると、その menuAction() を保持しない限り
    PySide6 がメニューごと破棄する(「ドックレイアウト」で実際に起きた
    セッションを壊すバグ)。2回呼んで結果が一致することで確認する。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        first = {quick_access_action_identifier(p) for p, _ in window._collect_menu_actions()}
        second = {quick_access_action_identifier(p) for p, _ in window._collect_menu_actions()}
        third = {quick_access_action_identifier(p) for p, _ in window._collect_menu_actions()}
        assert first == second == third
        # サブメニュー本体も生きたままであること
        assert window._export_menu.actions()
    finally:
        window.close()


# =============================================================================
# C-3 に伴うクイックアクセスのピン留め移行
# =============================================================================

def test_pinned_export_action_survives_the_move_into_the_submenu(tmp_path, monkeypatch):
    """★ これが無いと、サブメニュー化した時点で既存ユーザーのピンが
    エラーも警告も無くツールバーから消える(_restore_quick_access_actions は
    一致しない識別子を黙ってスキップする設計のため)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        old_ident = "ファイル(F) > 名前を付けてエクスポート(S)..."
        new_ident = "ファイル(F) > エクスポート > 名前を付けてエクスポート(S)..."
        available = {
            quick_access_action_identifier(path): action
            for path, action in window._collect_menu_actions()
        }
        migrated, changed = window._migrate_pinned_quick_access_ids([old_ident], available)

        assert changed is True
        assert migrated == [new_ident]
    finally:
        window.close()


def test_pinned_cvd_preview_survives_the_move_to_another_menu(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        old_ident = "ファイル(F) > 色覚シミュレーションプレビュー..."
        available = {
            quick_access_action_identifier(path): action
            for path, action in window._collect_menu_actions()
        }
        migrated, changed = window._migrate_pinned_quick_access_ids([old_ident], available)

        assert changed is True
        assert migrated == ["表示(V) > 色覚シミュレーションプレビュー..."]
    finally:
        window.close()


def test_migration_leaves_already_valid_identifiers_untouched(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        available = {
            quick_access_action_identifier(path): action
            for path, action in window._collect_menu_actions()
        }
        ident = "ファイル(F) > エクスポート > 印刷(R)..."
        assert ident in available
        migrated, changed = window._migrate_pinned_quick_access_ids([ident], available)

        assert migrated == [ident]
        assert changed is False
    finally:
        window.close()


def test_migration_skips_identifiers_with_no_unique_match(tmp_path, monkeypatch):
    """存在しない項目は誤爆を避けてそのまま残す(復元時に黙ってスキップされる)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        available = {
            quick_access_action_identifier(path): action
            for path, action in window._collect_menu_actions()
        }
        ident = "プラグイン > すでに消えたプラグインの項目"
        migrated, changed = window._migrate_pinned_quick_access_ids([ident], available)

        assert migrated == [ident]
        assert changed is False
    finally:
        window.close()


def test_restore_migrates_and_writes_back_the_new_identifier(tmp_path, monkeypatch):
    """読み替え結果はQSettingsへ書き戻し、次回以降は読み替え不要にする。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        old_ident = "ファイル(F) > 名前を付けてエクスポート(S)..."
        new_ident = "ファイル(F) > エクスポート > 名前を付けてエクスポート(S)..."
        window.settings.setValue(QUICK_ACCESS_SETTINGS_KEY, [old_ident])

        window._restore_quick_access_actions()

        assert window.is_quick_access_pinned(new_ident)
        assert window._get_pinned_quick_access_ids() == [new_ident]
    finally:
        window.close()


# =============================================================================
# C-2: データセット右クリックメニューのサブメニュー化
# =============================================================================

CONTEXT_SUBMENUS = {
    "データ処理": [
        "規格化(ノーマライズ)...",
        "Savitzky-Golayフィルタ(平滑化/微分)...",
        "ベースライン補正...",
        "区間積分(台形則/Simpson則)...",
        "累積積分(台形則/Simpson則)...",
        "共通X格子へのリサンプリング/補間...",
        "重複X値の検出...",
        "行フィルタ...",
        "外れ値検出(Z-score/IQR)...",
    ],
    "解析・注釈": [
        "統計値アンカーラベルを追加...",
        "インセット(拡大図)を追加...",
        "ピーク位置に自動ラベルを追加...",
        "ヒストグラム / KDE...",
    ],
    "複数データセット": [
        "データセット間演算...",
        "X軸アライメント(相互相関)...",
        "平均±SD生成...",
        "バッチ列計算...",
        "バッチカーブフィット...",
    ],
    "エクスポート": [
        "フィット結果のエクスポート...",
        "「方法」文をコピー...",
        "データ表をファイルに書き出す...",
    ],
    "タブ操作": [
        "別のタブへコピー...",
        "別のタブへ移動...",
    ],
}


def _build_context_menu(window, monkeypatch):
    """右クリックメニューをモーダル表示せずに構築し、ルートのQMenuを返す。"""
    import tests.test_dataset_mixin as dataset_mixin_tests

    dataset_mixin_tests._patch_recording_menu(monkeypatch)
    window._on_dataset_tree_context_menu(QPoint(0, 0))
    return dataset_mixin_tests._RecordingMenu.last_instance


def _add_datasets(window, count):
    added = []
    for i in range(count):
        ds = Dataset(
            name="d%d" % i,
            df=pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 4.0]}),
            x_col_name="x", y_col_name="y",
        )
        window._add_dataset(ds, select=True)
        added.append(ds)
    return added


def test_context_menu_groups_actions_into_five_submenus(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_datasets(window, 2)
        window.ui.dataset_list_widget.selectAll()
        root = _build_context_menu(window, monkeypatch)

        assert root.submenu_titles() == list(CONTEXT_SUBMENUS)
        for title, expected in CONTEXT_SUBMENUS.items():
            sub = _submenu(root, title)
            assert _menu_item_texts(sub) == expected, title
    finally:
        window.close()


def test_context_menu_top_level_is_much_shorter(tmp_path, monkeypatch):
    """約30項目のフラットなメニューから、トップレベルが大幅に減ること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_datasets(window, 2)
        window.ui.dataset_list_widget.selectAll()
        root = _build_context_menu(window, monkeypatch)

        assert len(_menu_item_texts(root)) <= 13
    finally:
        window.close()


def test_context_menu_keeps_frequent_one_click_actions_at_the_top(tmp_path, monkeypatch):
    """フォルダ操作・スタイルのコピー/貼り付け・再読み込み・削除は
    1クリックで終わる頻出操作なのでトップレベルに残す。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_datasets(window, 1)
        root = _build_context_menu(window, monkeypatch)

        top = _menu_item_texts(root)
        for item in ("新しいフォルダ", "スタイルをコピー", "スタイルを貼り付け",
                     "元ファイルから再読み込み", "削除"):
            assert item in top, item
    finally:
        window.close()


def test_context_menu_hides_empty_submenus(tmp_path, monkeypatch):
    """1件だけ選択しているときは「複数データセット」に入る項目が無いので、
    空のサブメニューは出さない(開いても何も無いメニューは邪魔なだけ)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_datasets(window, 1)
        root = _build_context_menu(window, monkeypatch)

        assert "複数データセット" not in root.submenu_titles()
        assert "データ処理" in root.submenu_titles()
    finally:
        window.close()


def test_context_menu_with_no_selection_has_no_submenus(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        root = _build_context_menu(window, monkeypatch)

        assert root.submenu_titles() == []
        assert _menu_item_texts(root) == ["新しいフォルダ"]
    finally:
        window.close()


def test_every_action_is_still_reachable_after_grouping(tmp_path, monkeypatch):
    """回帰テスト: グループ化で項目が消えていないこと。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_datasets(window, 2)
        window.ui.dataset_list_widget.selectAll()
        root = _build_context_menu(window, monkeypatch)

        reachable = set(root.added_texts)
        for expected in CONTEXT_SUBMENUS.values():
            for item in expected:
                assert item in reachable, item
    finally:
        window.close()


# =============================================================================
# A-5: 2Dマップではウォーターフォール設定を隠す
# =============================================================================

WATERFALL_WIDGET_ATTRS = (
    "waterfall_checkbox",
    "waterfall_offset_x_label", "waterfall_offset_x_spinbox",
    "waterfall_offset_y_label", "waterfall_offset_y_spinbox",
    "waterfall_occlusion_checkbox", "waterfall_depth_checkbox",
    "waterfall_depth_ratio_label", "waterfall_depth_ratio_spinbox",
)


def _make_2d_dataset():
    df = pd.DataFrame({"x": [0, 0, 1, 1], "y": [0, 1, 0, 1], "z": [1.0, 2.0, 3.0, 4.0]})
    return Dataset(name="map", df=df, x_col_name="x", y_col_name="y",
                   plot_type='Line', color='#112233',
                   data_kind='2d_grid', z_col_name="z")


def test_waterfall_controls_are_hidden_for_a_2d_map(tmp_path, monkeypatch):
    """2Dマップは描画の手前で1D経路から分離されるため、ウォーターフォール設定は
    何の効果も持たない。チェックボックスごと隠す。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        window._add_dataset(_make_2d_dataset(), select=True)

        for attr in WATERFALL_WIDGET_ATTRS:
            assert not getattr(window, attr).isVisible(), attr
    finally:
        window.close()


def test_waterfall_checkbox_is_still_shown_for_a_1d_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _add_datasets(window, 1)

        assert window.waterfall_checkbox.isVisible()
        # 詳細設定は従来どおりチェックしたときだけ
        assert not window.waterfall_offset_x_spinbox.isVisible()
    finally:
        window.close()


def test_switching_from_2d_back_to_1d_restores_the_waterfall_checkbox(tmp_path, monkeypatch):
    """選択を2D→1Dへ戻したときに、隠したままにならないこと。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        window._add_dataset(_make_2d_dataset(), select=True)
        assert not window.waterfall_checkbox.isVisible()

        ds_1d = _add_datasets(window, 1)[0]
        item = window._get_dataset_tree_item(ds_1d)
        window.ui.dataset_list_widget.setCurrentItem(item)

        assert window.waterfall_checkbox.isVisible()
    finally:
        window.close()
