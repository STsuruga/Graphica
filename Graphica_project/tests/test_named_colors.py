# tests/test_named_colors.py
"""
「よく使う色を名前付きで登録する」機能のテスト。

用途は「複数の種類のデータで、同じ物質には同じ色を使いたい」。試料名や条件名に
色を1つ結び付けて登録し、データセットの色欄からその名前で選べるようにする。

固めるのは3層:

1. **登録簿そのもの**(`core/named_colors.py`)。GUIにもQtにも依存しない純関数
   なので、ここを厚く固める。特に「壊れた設定ファイルを読んでも落ちない」と
   「登録名の重複を許さない」(ユーザー判断)を重点的に。
2. **色欄のポップアップ**(`gui/color_picker_widget.py`)。登録色が並ぶこと、
   選ぶと実際に色が変わりシグナルが1回だけ出ること。
3. **一括適用**(`gui/mixins/dataset_mixin.py`)。N件の変更が Undo 1回で戻ること、
   および「既にその色」のときに空のUndoを積まないこと。

★ ダイアログを開く経路は QColorDialog / QInputDialog を必ずモックする。
  offscreen環境でもモーダルの exec() はイベントループを無期限にブロックする
  (このリポジトリで実際に踏んでいる、docs/CORE_FEATURES_PROGRESS.md の C-407 参照)。
"""
import json

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog, QInputDialog

import gui.main_window as main_window_module
from core.dataset import Dataset
from core.named_colors import (
    MAX_NAME_LENGTH, NAMED_COLORS_SETTINGS_KEY, POPUP_LIMIT, NamedColorError,
    add_named_color, find_index_by_name, load_named_colors, move_named_color,
    normalize_color, normalize_name, remove_named_color, save_named_colors,
    update_named_color,
)
from gui.main_window import PlotterApp


# =============================================================================
# 1. 登録簿(純ロジック)
# =============================================================================

@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "named_colors.ini"), QSettings.Format.IniFormat)


@pytest.mark.parametrize("raw, expected", [
    ("#1f77b4", "#1f77b4"),
    ("#1F77B4", "#1f77b4"),
    ("  #1f77b4  ", "#1f77b4"),
    ("#abc", "#aabbcc"),
    ("#ABC", "#aabbcc"),
])
def test_normalize_color_accepts_and_lowercases(raw, expected):
    assert normalize_color(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "1f77b4", "#12345", "#gggggg", "red", "#1f77b4ff"])
def test_normalize_color_rejects_bad_input(raw):
    with pytest.raises(NamedColorError):
        normalize_color(raw)


def test_normalize_name_strips_and_rejects_empty():
    assert normalize_name("  試料A  ") == "試料A"
    for bad in ("", "   ", None):
        with pytest.raises(NamedColorError):
            normalize_name(bad)


def test_normalize_name_rejects_overly_long_names():
    """長すぎる名前はポップアップの幅を壊すだけなので上限を切る。"""
    assert normalize_name("あ" * MAX_NAME_LENGTH)
    with pytest.raises(NamedColorError):
        normalize_name("あ" * (MAX_NAME_LENGTH + 1))


def test_round_trip_through_settings(settings):
    entries = []
    entries = add_named_color(entries, "試料A", "#1f77b4")
    entries = add_named_color(entries, "試料B", "#D62728")
    save_named_colors(settings, entries)

    assert load_named_colors(settings) == [
        {"name": "試料A", "color": "#1f77b4"},
        {"name": "試料B", "color": "#d62728"},
    ]


def test_order_is_preserved_not_sorted(settings):
    """
    ★ 保存形式を辞書ではなくリストにしている理由。並び順はそのまま
    ポップアップの表示順になるので、名前順に並べ替えてはいけない。
    """
    entries = []
    for name in ("ん", "あ", "middle", "Zebra"):
        entries = add_named_color(entries, name, "#000000")
    save_named_colors(settings, entries)

    assert [e["name"] for e in load_named_colors(settings)] == ["ん", "あ", "middle", "Zebra"]


def test_empty_settings_gives_an_empty_list(settings):
    assert load_named_colors(settings) == []


@pytest.mark.parametrize("stored", [
    "not json", "{}", '"a string"', "42", "null",
])
def test_broken_settings_value_falls_back_to_empty(settings, stored):
    """設定ファイルが壊れていてもアプリが起動しなくなってはいけない。"""
    settings.setValue(NAMED_COLORS_SETTINGS_KEY, stored)
    assert load_named_colors(settings) == []


def test_individually_broken_entries_are_dropped_but_the_rest_survive(settings):
    settings.setValue(NAMED_COLORS_SETTINGS_KEY, json.dumps([
        {"name": "良い", "color": "#1f77b4"},
        {"name": "", "color": "#1f77b4"},          # 名前なし
        {"name": "色が変", "color": "not-a-color"},  # 色が不正
        "文字列",                                     # そもそも辞書でない
        {"name": "これも良い", "color": "#abc"},
    ]))
    assert load_named_colors(settings) == [
        {"name": "良い", "color": "#1f77b4"},
        {"name": "これも良い", "color": "#aabbcc"},
    ]


def test_duplicate_names_in_stored_data_are_collapsed(settings):
    settings.setValue(NAMED_COLORS_SETTINGS_KEY, json.dumps([
        {"name": "試料A", "color": "#111111"},
        {"name": "試料A", "color": "#222222"},
    ]))
    loaded = load_named_colors(settings)
    assert len(loaded) == 1
    assert loaded[0]["color"] == "#111111"  # 先に出てきた方を残す


def test_adding_a_duplicate_name_is_refused():
    """★ ユーザー判断: 登録名の重複は禁止(名前→色が1対1でないと一括適用で困る)。"""
    entries = add_named_color([], "試料A", "#1f77b4")
    with pytest.raises(NamedColorError, match="試料A"):
        add_named_color(entries, "試料A", "#d62728")
    with pytest.raises(NamedColorError):
        add_named_color(entries, "  試料A  ", "#d62728")  # 空白違いも同じ名前


def test_add_does_not_mutate_the_input_list():
    original = add_named_color([], "試料A", "#1f77b4")
    add_named_color(original, "試料B", "#d62728")
    assert [e["name"] for e in original] == ["試料A"]


def test_update_can_keep_its_own_name():
    entries = add_named_color([], "試料A", "#1f77b4")
    entries = add_named_color(entries, "試料B", "#d62728")

    updated = update_named_color(entries, 0, "試料A", "#000000")
    assert updated[0] == {"name": "試料A", "color": "#000000"}

    with pytest.raises(NamedColorError):
        update_named_color(entries, 0, "試料B", "#000000")  # 他の登録とは衝突する


def test_remove_and_out_of_range_indices():
    entries = add_named_color([], "試料A", "#1f77b4")
    assert remove_named_color(entries, 0) == []
    for bad in (-1, 1, 99):
        with pytest.raises(NamedColorError):
            remove_named_color(entries, bad)


def test_move_reorders_and_clamps_at_the_ends():
    entries = []
    for name in ("A", "B", "C"):
        entries = add_named_color(entries, name, "#000000")

    assert [e["name"] for e in move_named_color(entries, 2, -1)] == ["A", "C", "B"]
    assert [e["name"] for e in move_named_color(entries, 0, 1)] == ["B", "A", "C"]
    # 端を越える移動は何も起きない(ボタンを押しても無反応、という素直な挙動)
    assert [e["name"] for e in move_named_color(entries, 0, -1)] == ["A", "B", "C"]
    assert [e["name"] for e in move_named_color(entries, 2, 1)] == ["A", "B", "C"]


def test_find_index_by_name():
    entries = add_named_color([], "試料A", "#1f77b4")
    assert find_index_by_name(entries, "試料A") == 0
    assert find_index_by_name(entries, "  試料A ") == 0
    assert find_index_by_name(entries, "無い名前") == -1


def test_named_colors_use_a_separate_key_from_the_palette_manager():
    """
    ★ 配色パレット(順序付きの色のリスト)とは目的が違うので、同じキーに
    相乗りさせない。混ぜるとパレット管理側の意味が壊れる。
    """
    from gui.mixins.dataset_mixin import COLOR_PALETTES_SETTINGS_KEY
    assert NAMED_COLORS_SETTINGS_KEY != COLOR_PALETTES_SETTINGS_KEY


# =============================================================================
# 2. 色欄のポップアップ / 3. 一括適用
# =============================================================================

def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "app_settings.ini")

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


@pytest.fixture
def window(tmp_path, monkeypatch):
    w = _make_isolated_plotter_app(tmp_path, monkeypatch)
    yield w
    w.close()


def _pump():
    app = QApplication.instance()
    for _ in range(4):
        app.processEvents()


def _seed(window, pairs):
    entries = []
    for name, color in pairs:
        entries = add_named_color(entries, name, color)
    save_named_colors(window.settings, entries)
    return entries


def _add_datasets(window, count):
    df = pd.DataFrame({"x": np.arange(5.0), "y": np.arange(5.0)})
    added = []
    for i in range(count):
        dataset = Dataset(df=df.copy(), name=f"d{i}", x_col_name="x", y_col_name="y")
        window._add_dataset(dataset)
        added.append(dataset)
    _pump()
    return added


# --- 色欄のポップアップ ---

def test_registering_the_current_color_from_the_picker(window, monkeypatch):
    picker = window.color_picker_widget
    picker.set_color(QColor("#123456"))
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("試料A", True)))

    picker._on_register_current_color()

    assert load_named_colors(window.settings) == [{"name": "試料A", "color": "#123456"}]


def test_registering_is_cancelled_cleanly(window, monkeypatch):
    picker = window.color_picker_widget
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("", False)))

    picker._on_register_current_color()

    assert load_named_colors(window.settings) == []


def test_registering_a_duplicate_name_warns_and_keeps_the_original(window, monkeypatch):
    _seed(window, [("試料A", "#1f77b4")])
    picker = window.color_picker_widget
    picker.set_color(QColor("#654321"))
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("試料A", True)))
    warned = []
    monkeypatch.setattr("gui.color_picker_widget.QMessageBox.warning",
                        staticmethod(lambda *a, **k: warned.append(a)))

    picker._on_register_current_color()

    assert warned, "重複登録が黙って通ってしまっている"
    assert load_named_colors(window.settings) == [{"name": "試料A", "color": "#1f77b4"}]


def test_choosing_a_named_color_applies_it_and_emits_once(window):
    picker = window.color_picker_widget
    picker.set_color(QColor("#000000"))
    received = []
    picker.colorChanged.connect(received.append)

    picker._apply_color_name("#1f77b4")

    assert picker.color_name() == "#1f77b4"
    assert received == ["#1f77b4"]


def test_choosing_the_colour_it_already_has_emits_nothing(window):
    """set_color と同じく、実際に変わったときだけ通知する既存の約束を守る。"""
    picker = window.color_picker_widget
    picker.set_color(QColor("#1f77b4"))
    received = []
    picker.colorChanged.connect(received.append)

    picker._apply_color_name("#1f77b4")

    assert received == []


def test_other_colors_still_reaches_the_colour_dialog(window, monkeypatch):
    """
    従来の自由な色選択が「その他の色...」から生きていること(登録色を
    前に出したせいで、任意の色が選べなくなっては本末転倒)。
    """
    picker = window.color_picker_widget
    picker.set_color(QColor("#000000"))
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor("#abcdef")))
    received = []
    picker.colorChanged.connect(received.append)

    picker._on_pick_other_color()

    assert picker.color_name() == "#abcdef"
    assert received == ["#abcdef"]


def test_the_gradient_end_colour_picker_gets_the_feature_too(window):
    """
    ColorPickerWidget はデータセットの色とグラデーション終端色の両方で
    使われているので、1箇所の実装で両方に効く。
    """
    assert hasattr(window.gradient_color2_picker, "_on_register_current_color")


# --- 一括適用 ---

def test_apply_menu_shows_a_disabled_hint_when_nothing_is_registered(window):
    window._populate_named_color_apply_menu()

    actions = window._named_color_apply_menu.actions()
    assert len(actions) == 1
    assert actions[0].isEnabled() is False


def test_apply_menu_lists_registered_colors_in_order(window):
    _seed(window, [("試料B", "#d62728"), ("試料A", "#1f77b4")])
    window._populate_named_color_apply_menu()

    texts = [a.text() for a in window._named_color_apply_menu.actions()]
    assert texts == ["試料B\t#d62728", "試料A\t#1f77b4"]


def test_apply_menu_is_rebuilt_when_the_registry_changes(window):
    window._populate_named_color_apply_menu()
    _seed(window, [("試料A", "#1f77b4")])

    window._named_color_apply_menu.aboutToShow.emit()

    assert [a.text() for a in window._named_color_apply_menu.actions()] == ["試料A\t#1f77b4"]


def test_applying_to_several_datasets_is_one_undo_step(window):
    datasets = _add_datasets(window, 3)
    window.ui.dataset_list_widget.selectAll()
    _pump()
    before_colors = [d.color for d in datasets]
    before_count = window.undo_stack.count()

    window._apply_named_color_to_selection("#d62728", "試料B")
    _pump()

    assert [d.color for d in datasets] == ["#d62728"] * 3
    assert window.undo_stack.count() == before_count + 1

    window.undo_stack.undo()
    _pump()
    assert [d.color for d in datasets] == before_colors


def test_applying_a_colour_everything_already_has_does_not_push_an_undo(window):
    """
    ★ 空の beginMacro/endMacro は「中身ゼロのマクロ」としてそのまま積まれる。
    何も変わっていないのに「押しても何も起きないUndo」が増えてしまう。
    """
    datasets = _add_datasets(window, 2)
    window.ui.dataset_list_widget.selectAll()
    _pump()
    current = datasets[0].color
    before_count = window.undo_stack.count()

    window._apply_named_color_to_selection(current, "同じ色")
    _pump()

    assert window.undo_stack.count() == before_count


def test_applying_with_no_selection_does_nothing(window):
    _add_datasets(window, 1)
    window.ui.dataset_list_widget.clearSelection()
    _pump()
    before_count = window.undo_stack.count()

    window._apply_named_color_to_selection("#d62728", "試料B")
    _pump()

    assert window.undo_stack.count() == before_count


# --- 管理ダイアログ ---

def test_manager_dialog_lists_name_and_hex(window):
    from gui.dialogs import NamedColorManagerDialog
    _seed(window, [("試料A", "#1f77b4"), ("試料B", "#d62728")])

    dialog = NamedColorManagerDialog(window.settings, window)
    try:
        texts = [dialog.color_list.item(i).text()
                 for i in range(dialog.color_list.count())]
        assert texts == ["試料A    #1f77b4", "試料B    #d62728"]
        # 色プレビュー(アイコン)も付いていること
        assert not dialog.color_list.item(0).icon().isNull()
    finally:
        dialog.close()


def test_manager_dialog_saves_immediately(window, monkeypatch):
    """
    このダイアログは OK を待たずその場で保存する(登録簿を育てる操作であって、
    プロットの見た目を変えるものではないため)。
    """
    from gui.dialogs import NamedColorManagerDialog
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor("#0a0b0c")))
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("追加した色", True)))

    dialog = NamedColorManagerDialog(window.settings, window)
    try:
        dialog._on_add()
        assert load_named_colors(window.settings) == [
            {"name": "追加した色", "color": "#0a0b0c"}
        ]
    finally:
        dialog.close()


def test_manager_dialog_move_updates_both_list_and_settings(window):
    from gui.dialogs import NamedColorManagerDialog
    _seed(window, [("A", "#111111"), ("B", "#222222")])

    dialog = NamedColorManagerDialog(window.settings, window)
    try:
        dialog.color_list.setCurrentRow(1)
        dialog._on_move(-1)

        assert [e["name"] for e in load_named_colors(window.settings)] == ["B", "A"]
        assert dialog.color_list.item(0).text().startswith("B")
        assert dialog.color_list.currentRow() == 0
    finally:
        dialog.close()


def test_manager_dialog_delete(window):
    from gui.dialogs import NamedColorManagerDialog
    _seed(window, [("A", "#111111"), ("B", "#222222")])

    dialog = NamedColorManagerDialog(window.settings, window)
    try:
        dialog.color_list.setCurrentRow(0)
        dialog._on_delete()

        assert [e["name"] for e in load_named_colors(window.settings)] == ["B"]
        assert dialog.color_list.count() == 1
    finally:
        dialog.close()


# =============================================================================
# 4. 件数が増えたときの見せ方(ポップアップは上位 POPUP_LIMIT 件まで)
# =============================================================================

def _seed_many(window, count):
    entries = []
    for i in range(count):
        entries = add_named_color(entries, f"色{i:02d}", "#%02x0000" % i)
    save_named_colors(window.settings, entries)
    return entries


def test_apply_menu_shows_all_entries_when_within_the_limit(window):
    _seed_many(window, POPUP_LIMIT)
    window._populate_named_color_apply_menu()

    actions = window._named_color_apply_menu.actions()
    assert len(actions) == POPUP_LIMIT
    assert not any("すべての登録色" in a.text() for a in actions)


def test_apply_menu_caps_the_list_and_offers_the_rest(window):
    """
    ★ 登録は際限なく増やせるので、メニューに全件並べると縦に伸び続ける。
    先頭 POPUP_LIMIT 件だけ並べ、残りは検索欄付きの一覧へ逃がす。
    """
    total = POPUP_LIMIT + 7
    _seed_many(window, total)
    window._populate_named_color_apply_menu()

    actions = window._named_color_apply_menu.actions()
    assert len(actions) == POPUP_LIMIT + 1
    assert [a.text().split("\t")[0] for a in actions[:POPUP_LIMIT]] == \
        [f"色{i:02d}" for i in range(POPUP_LIMIT)]
    # 件数が分かるようにしておく(何件隠れているのか見えないと押す気にならない)
    assert f"({total}件)" in actions[-1].text()


def test_picker_dialog_lists_every_entry_regardless_of_the_popup_limit(window):
    from gui.dialogs import NamedColorPickerDialog
    total = POPUP_LIMIT + 4
    _seed_many(window, total)

    dialog = NamedColorPickerDialog(window.settings, window)
    try:
        assert dialog.color_list.count() == total
    finally:
        dialog.close()


def test_picker_dialog_filters_by_name_and_by_hex(window):
    from gui.dialogs import NamedColorPickerDialog
    _seed(window, [("試料A", "#1f77b4"), ("試料B", "#d62728"), ("ブランク", "#7f7f7f")])

    dialog = NamedColorPickerDialog(window.settings, window)
    try:
        dialog.filter_edit.setText("試料")
        assert dialog.color_list.count() == 2

        dialog.filter_edit.setText("7f7f")   # 色コードでも引ける
        assert dialog.color_list.count() == 1
        assert dialog.color_list.item(0).text().startswith("ブランク")

        dialog.filter_edit.setText("")
        assert dialog.color_list.count() == 3
    finally:
        dialog.close()


def test_picker_dialog_returns_the_selected_entry(window):
    from gui.dialogs import NamedColorPickerDialog
    _seed(window, [("試料A", "#1f77b4"), ("試料B", "#d62728")])

    dialog = NamedColorPickerDialog(window.settings, window)
    try:
        dialog.color_list.setCurrentRow(1)
        dialog.accept()
        assert dialog.selected_entry() == {"name": "試料B", "color": "#d62728"}
    finally:
        dialog.close()


def test_picker_dialog_returns_nothing_when_the_filter_matches_nothing(window):
    """絞り込みで0件になった状態でOKを押しても、選択が無いので何も返さない。"""
    from gui.dialogs import NamedColorPickerDialog
    _seed(window, [("試料A", "#1f77b4")])

    dialog = NamedColorPickerDialog(window.settings, window)
    try:
        dialog.filter_edit.setText("該当なし")
        dialog.accept()
        assert dialog.selected_entry() is None
    finally:
        dialog.close()


def test_swatch_popup_also_caps_at_the_limit(window):
    """色欄のポップアップも同じ上限で揃っていること(片方だけ直す事故を防ぐ)。"""
    import inspect
    source = inspect.getsource(type(window.color_picker_widget)._on_swatch_clicked)
    assert "POPUP_LIMIT" in source
    assert "_on_choose_from_all_named_colors" in source
