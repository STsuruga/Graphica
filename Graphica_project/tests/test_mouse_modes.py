# tests/test_mouse_modes.py
"""
7つの排他マウスモード(改善ボード A-2 / B-1)に対するテスト。

- 登録簿 MOUSE_MODES が実際の PlotterApp の属性と一致していること
- 42通り(7×6)の全順序対で「Xを有効にするとYが解除される」こと
  ★ A-2 の回帰テスト: 以前は annotation→layout_edit と cursor→layout_edit の
    2通りだけが解除されず、両モードが同時に有効なままになっていた。
- 解除された側の後始末(mpl_connect の解除)まで行われていること
"""
import itertools

import matplotlib
matplotlib.use("Agg")
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from gui.mixins.mouse_mode_mixin import MOUSE_MODES, MOUSE_MODES_BY_NAME

MODE_NAMES = [mode.name for mode in MOUSE_MODES]


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る
    (tests/test_annotation_mixin.py と同じパターン)。"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _activate(window, name):
    """ツールバーのボタンを押したのと同じ経路でモードを有効にする。

    QAction は toggled ではなく triggered に接続されているため、実アプリでは
    「setChecked された上でスロットが呼ばれる」。その順序をそのまま再現する。
    """
    mode = MOUSE_MODES_BY_NAME[name]
    getattr(window, mode.action_attr).setChecked(True)
    getattr(window, mode.toggle_method)(True)


# --- 登録簿そのものの健全性 ---

def test_registry_covers_seven_modes_without_duplicates():
    assert len(MOUSE_MODES) == 7
    assert len(set(MODE_NAMES)) == 7
    assert len({m.flag_attr for m in MOUSE_MODES}) == 7
    assert len({m.action_attr for m in MOUSE_MODES}) == 7
    assert len({m.toggle_method for m in MOUSE_MODES}) == 7


def test_registry_attributes_exist_on_plotter_app(tmp_path, monkeypatch):
    """登録簿の属性名/メソッド名が実際の PlotterApp と一致していること。
    綴り間違いがあっても getattr のデフォルトで静かに素通りしてしまうため、
    ここで明示的に突き合わせる。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        for mode in MOUSE_MODES:
            assert hasattr(window, mode.action_attr), mode.action_attr
            assert callable(getattr(window, mode.toggle_method, None)), mode.toggle_method
            # フラグは有効化して初めて生えるモードもあるため、
            # 一度ONにしてから属性の存在を確認する
            _activate(window, mode.name)
            assert getattr(window, mode.flag_attr) is True, mode.flag_attr
            getattr(window, mode.toggle_method)(False)
    finally:
        window.close()


# --- 排他性(42通りの全順序対) ---

@pytest.mark.parametrize("first,second", [
    pair for pair in itertools.permutations(MODE_NAMES, 2)
])
def test_activating_a_mode_deactivates_every_other_mode(first, second, tmp_path, monkeypatch):
    """A-2 の回帰テスト: firstを有効にした状態でsecondを有効にすると、
    firstは必ず解除される(フラグもツールバーのチェック状態も)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        first_mode = MOUSE_MODES_BY_NAME[first]
        second_mode = MOUSE_MODES_BY_NAME[second]

        _activate(window, first)
        assert getattr(window, first_mode.flag_attr) is True

        _activate(window, second)

        assert getattr(window, second_mode.flag_attr) is True
        assert getattr(window, first_mode.flag_attr) is False, (
            "%s を有効にしても %s が解除されていない" % (second, first)
        )
        assert getattr(window, first_mode.action_attr).isChecked() is False, (
            "%s を有効にしても %s のツールバーボタンがONのまま" % (second, first)
        )
        assert window._active_mouse_mode() == second
    finally:
        window.close()


def test_annotation_mode_deactivates_layout_edit_mode(tmp_path, monkeypatch):
    """A-2 そのもの(注釈モードが自由配置編集モードを解除しない)の直接の回帰テスト。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _activate(window, "layout_edit")
        assert window.layout_edit_mode_enabled is True

        _activate(window, "annotation")

        assert window.annotation_mode_enabled is True
        assert window.layout_edit_mode_enabled is False
        assert window.layout_edit_action.isChecked() is False
        # 解除側の後始末: ドラッグ用の button_press_event 接続が残っていないこと
        assert getattr(window, "_layout_edit_press_cid", None) is None
        assert getattr(window, "_layout_drag_state", None) is None
    finally:
        window.close()


def test_cursor_mode_deactivates_layout_edit_mode(tmp_path, monkeypatch):
    """A-2 の調査中に見つかった同種の抜け(データカーソルモードも自由配置編集
    モードを解除していなかった)の直接の回帰テスト。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _activate(window, "layout_edit")
        assert window.layout_edit_mode_enabled is True

        _activate(window, "cursor")

        assert window.cursor_mode_enabled is True
        assert window.layout_edit_mode_enabled is False
        assert window.layout_edit_action.isChecked() is False
        assert getattr(window, "_layout_edit_press_cid", None) is None
    finally:
        window.close()


def test_at_most_one_mode_is_active_after_a_sequence_of_toggles(tmp_path, monkeypatch):
    """全モードを順に有効化していっても、常に有効なのは1つだけであること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        for name in MODE_NAMES:
            _activate(window, name)
            active = [m.name for m in MOUSE_MODES if getattr(window, m.flag_attr, False)]
            assert active == [name], "同時に有効なモードが複数あります: %s" % active
    finally:
        window.close()


def test_deactivating_the_last_mode_leaves_none_active(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _activate(window, "range_select")
        window._toggle_range_select_mode(False)
        assert window._active_mouse_mode() is None
    finally:
        window.close()


def test_unknown_mode_name_is_logged_but_still_clears_others(tmp_path, monkeypatch, caplog):
    """登録簿への追加漏れ(未登録の名前)は警告を出しつつ、他モードの解除は行う。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        _activate(window, "cursor")
        with caplog.at_level("WARNING"):
            window._deactivate_other_mouse_modes("not_registered")
        assert window.cursor_mode_enabled is False
        assert any("not_registered" in record.getMessage() for record in caplog.records)
    finally:
        window.close()
