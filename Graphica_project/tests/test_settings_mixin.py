# tests/test_settings_mixin.py
"""
gui/mixins/settings_mixin.py(1,058行)に対するテスト(改善ボード B-4)。

このファイルには専用テストが無く、`test_main_window.py`等が間接的に触れて
いるだけだった。軸設定の収集(`_gather_settings_from_ui`)と適用
(`_apply_settings_to_ui_controls`)は、壊れると「サブプロットを切り替えた
だけで設定が失われる」「プロジェクトを開き直すと書式が変わる」という形で
効いてくるため、**この2つの往復(ラウンドトリップ)を軸に固める**。

★ 整備中に実際にバグを1件見つけた: `_apply_settings_to_ui_controls`が
末尾で`_on_x_autoscale_changed()`(ユーザーがチェックを外した瞬間用に、
現在表示中の軸範囲をスピンボックスへシードするハンドラ)を呼んでいたため、
**オートスケールOFFで保存した軸範囲が復元のたびに失われていた**。
`test_axis_range_survives_a_round_trip_with_autoscale_off`がその回帰テスト。
"""
import contextlib

import matplotlib
matplotlib.use("Agg")
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

import graphica.gui.notify as notify_module
import graphica.gui.app_settings as app_settings_module
from graphica.gui.axis_bindings import AXIS_BINDINGS, CARRIED_AXIS_KEYS
from graphica.gui.main_window import PlotterApp


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
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


# UIコントロールを持たず、呼び出しのたびに現在のプロジェクトから引き継がれるキー。
# (_gather_settings_from_ui の末尾参照。注釈・凡例順・自由配置の矩形は
#  ドラッグ操作等から直接 all_plot_settings へ書かれる)
NON_UI_KEYS = {"annotations", "legend_order", "free_rect", "legend_position"}


@contextlib.contextmanager
def _without_live_redraw(window):
    """
    UIを一通り書き換える間だけ、再描画を止める(改善ボード E-3)。

    軸設定のウィジェットはどれも `_on_axis_setting_changed` に繋がっており、
    そのハンドラは「①UIから設定を収集 → ②プロジェクトへ保存 → ③
    `_update_plot_appearance()`(tight_layout + draw)」を行う。下の
    `_mutate_every_control` は約90個のコントロールを順に書き換えるため、
    ③が90回走って **1テストあたり35〜42秒** かかっていた。このファイルだけで
    234秒、フルスイート全体の約11%を占めていた(実測)。

    ラウンドトリップのテストが見ているのは `_gather_settings_from_ui` と
    `_apply_settings_to_ui_controls` であって、書き換え途中の再描画ではない。
    ①②(プロジェクトへの保存)は従来どおり走らせ、③だけを止める。
    """
    window._update_plot_appearance = lambda *args, **kwargs: None
    try:
        yield
    finally:
        # クラス側のメソッドが再び見えるよう、インスタンス属性を外す
        window.__dict__.pop("_update_plot_appearance", None)


def _mutate_every_control(window):
    """
    既定値とは違う値を、UIコントロールへ一通り書き込む。
    ラウンドトリップのテストは「既定値のまま往復した」だけでは通ってしまう
    (何もしなくても一致する)ため、必ず既定から動かしてから往復させる。

    書き換えの間は再描画を止める(`_without_live_redraw` の説明を参照)。
    """
    with _without_live_redraw(window):
        _write_every_control(window)


def _write_every_control(window):
    ui = window.ui
    ui.title_text_edit.setText("タイトル")
    ui.x_label_text_edit.setText("X軸ラベル")
    ui.y_label_text_edit.setText("Y軸ラベル")
    window.x_label_visible_checkbox.setChecked(False)
    window.y_label_visible_checkbox.setChecked(False)
    window.y2_label_text_edit.setText("第2Y軸")

    # X軸(オートスケールはONのまま。OFF時の往復は専用テストで見る)
    ui.x_log_checkbox.setChecked(True)
    ui.x_invert_checkbox.setChecked(True)
    ui.x_major_tick_mode_combo.setCurrentIndex(1)
    ui.x_major_tick_interval_spinbox.setValue(2.5)
    ui.x_minor_ticks_visible_checkbox.setChecked(True)
    ui.x_minor_tick_interval_spinbox.setValue(0.25)
    window.x_log_minor_subs_combo.setCurrentIndex(1)
    window.x_log_minor_labels_checkbox.setChecked(True)
    window.x_tick_format_combo.setCurrentIndex(1)
    window.x_tick_decimals_spinbox.setValue(3)
    window.x_secondary_axis_source_unit_combo.setCurrentIndex(1)
    window.x_secondary_axis_target_unit_combo.setCurrentIndex(2)

    # Y軸
    ui.y_log_checkbox.setChecked(True)
    ui.y_invert_checkbox.setChecked(True)
    ui.y_major_tick_mode_combo.setCurrentIndex(1)
    ui.y_major_tick_interval_spinbox.setValue(3.5)
    ui.y_minor_ticks_visible_checkbox.setChecked(True)
    ui.y_minor_tick_interval_spinbox.setValue(0.75)
    window.y_log_minor_subs_combo.setCurrentIndex(1)
    window.y_log_minor_labels_checkbox.setChecked(True)
    window.y_tick_format_combo.setCurrentIndex(1)
    window.y_tick_decimals_spinbox.setValue(4)

    # 凡例・グリッド
    ui.legend_visible_checkbox.setChecked(False)
    window.legend_loc_combo.setCurrentIndex(2)
    ui.grid_visible_checkbox.setChecked(True)
    ui.minor_grid_visible_checkbox.setChecked(True)
    for prefix in ("x_major", "x_minor", "y_major", "y_minor"):
        getattr(window, f"{prefix}_grid_linestyle_combo").setCurrentIndex(2)
        getattr(window, f"{prefix}_grid_width_spinbox").setValue(1.75)
        getattr(window, f"{prefix}_grid_alpha_spinbox").setValue(0.35)
    window.major_tick_direction_combo.setCurrentText("in")
    window.minor_tick_direction_combo.setCurrentText("in")
    window.major_tick_direction_y2_combo.setCurrentText("in")
    window.minor_tick_direction_y2_combo.setCurrentText("in")
    window.x_ticks_visible_checkbox.setChecked(False)
    window.x_tick_labels_visible_checkbox.setChecked(False)
    window.y_ticks_visible_checkbox.setChecked(False)
    window.y_tick_labels_visible_checkbox.setChecked(False)

    # 内部変数(フォント・色・太さ)
    font = QFont("Arial")
    font.setPointSize(17)
    font.setBold(True)
    font.setItalic(True)
    window._tick_font = QFont(font)
    window._axis_label_font = QFont(font)
    window._legend_font = QFont(font)
    window._tick_color = "#112233"
    window._axis_label_color = "#445566"
    window._legend_color = "#778899"
    window._spine_color = "#aabbcc"
    ui.tick_width_spinbox.setValue(2.25)
    window.major_tick_length_spinbox.setValue(6.5)
    window.minor_tick_length_spinbox.setValue(4.0)
    ui.spine_width_spinbox.setValue(3.25)

    # カラーバー
    window.colorbar_enabled_checkbox.setChecked(False)
    window.colorbar_position_combo.setCurrentIndex(1)
    window.colorbar_width_spinbox.setValue(0.12)
    window.colorbar_label_edit.setText("カラーバー")


# =============================================================================
# ラウンドトリップ(このファイルの中心)
# =============================================================================

def test_round_trip_preserves_every_setting(window):
    """collect → apply → collect で、全キーが一致すること。"""
    _mutate_every_control(window)
    original = window._gather_settings_from_ui()

    window._apply_settings_to_ui_controls(original)
    restored = window._gather_settings_from_ui()

    assert restored == original


def test_round_trip_actually_moved_away_from_defaults(window):
    """上のテストが「既定値のまま往復しただけ」で通っていないことの確認。
    _mutate_every_control が実際に多数のキーを既定から動かしていること。"""
    defaults = window._gather_settings_from_ui()
    _mutate_every_control(window)
    mutated = window._gather_settings_from_ui()

    differing = [k for k in defaults if defaults[k] != mutated[k]]
    assert len(differing) >= 40, f"既定から動いたキーが少なすぎる: {len(differing)}"


def test_applying_settings_from_one_axis_does_not_leak_into_another(window):
    """サブプロットを切り替えても、それぞれの設定が独立に保たれること。"""
    first = window._gather_settings_from_ui()
    _mutate_every_control(window)
    second = window._gather_settings_from_ui()
    assert first != second

    window._apply_settings_to_ui_controls(first)
    assert window._gather_settings_from_ui() == first

    window._apply_settings_to_ui_controls(second)
    assert window._gather_settings_from_ui() == second


# =============================================================================
# ★ 回帰テスト: オートスケールOFFの軸範囲が復元で失われる(B-4で発見)
# =============================================================================

def test_axis_range_survives_a_round_trip_with_autoscale_off(window):
    """
    ★ 回帰テスト。以前は _apply_settings_to_ui_controls が末尾で
    _on_x_autoscale_changed()(ユーザーがチェックを外した瞬間用に、現在
    表示中の軸範囲をスピンボックスへシードするハンドラ)を呼んでいたため、
    **オートスケールOFFで保存した軸範囲が、復元のたびに「いま画面に出ている
    範囲」で上書きされて失われていた**。

    しかも X 側だけが壊れ Y 側は無事という順序依存の壊れ方をしていた
    (先に走るX側のハンドラが再描画を起こし、その時点で軸にはまだ復元前の
    範囲が入っている。Y側はその再描画で既に復元後の値が軸へ反映済みなので
    シードしても値が変わらなかった)。X/Y の両方を確認する。
    """
    saved = window._gather_settings_from_ui()
    saved.update({
        'x_autoscale': False, 'x_min': 111.0, 'x_max': 222.0,
        'y_autoscale': False, 'y_min': 333.0, 'y_max': 444.0,
    })

    window._apply_settings_to_ui_controls(saved)
    restored = window._gather_settings_from_ui()

    assert restored['x_min'] == pytest.approx(111.0)
    assert restored['x_max'] == pytest.approx(222.0)
    assert restored['y_min'] == pytest.approx(333.0)
    assert restored['y_max'] == pytest.approx(444.0)


def test_toggling_autoscale_off_by_hand_still_seeds_the_spinboxes(window):
    """★ 上の修正で、ユーザー操作時のシード(実機フィードバック由来の既存の
    バグ修正)まで壊していないこと。チェックを外すと、現在表示中の軸範囲が
    スピンボックスへ入る。"""
    axis = window.canvas.all_axes[0]
    axis.set_xlim(7.0, 9.0)
    window.ui.x_autoscale_checkbox.setChecked(False)

    window._on_x_autoscale_changed()

    assert window.ui.x_min_spinbox.value() == pytest.approx(7.0)
    assert window.ui.x_max_spinbox.value() == pytest.approx(9.0)


def test_autoscale_state_controls_whether_the_spinboxes_are_enabled(window):
    window.ui.x_autoscale_checkbox.setChecked(True)
    window._refresh_x_autoscale_enabled_state()
    assert not window.ui.x_min_spinbox.isEnabled()

    window.ui.x_autoscale_checkbox.setChecked(False)
    window._refresh_x_autoscale_enabled_state()
    assert window.ui.x_min_spinbox.isEnabled()


def test_refreshing_the_enabled_state_never_touches_the_values(window):
    """値を書き換えないことが、この関数の存在理由そのもの。"""
    window.ui.x_autoscale_checkbox.setChecked(False)
    window.ui.x_min_spinbox.setValue(55.0)
    window.ui.x_max_spinbox.setValue(66.0)

    window._refresh_x_autoscale_enabled_state()
    window._refresh_y_autoscale_enabled_state()

    assert window.ui.x_min_spinbox.value() == pytest.approx(55.0)
    assert window.ui.x_max_spinbox.value() == pytest.approx(66.0)


# =============================================================================
# 構造的な検査(キーの取りこぼしを機械的に防ぐ)
# =============================================================================

def test_every_gathered_key_is_restored_by_the_table(window):
    """集めるキーはどれも表の行が戻す。戻さないキーは、サブプロットを切り替えた瞬間に既定値へ戻って静かに失われる。"""
    gathered = window._gather_settings_from_ui()
    restored = [binding.key for binding in AXIS_BINDINGS]

    assert len(restored) == len(set(restored))
    missing = [key for key in gathered if key not in NON_UI_KEYS and key not in restored]
    assert not missing, f"表に戻す行が無いキー: {missing}"
    assert set(NON_UI_KEYS) == set(CARRIED_AXIS_KEYS)


def test_applying_settings_does_not_fire_the_change_handler(window, monkeypatch):
    """
    ★ apply 中にUIの変更シグナルが飛ぶと、_on_axis_setting_changed が走って
    「復元途中の中途半端な状態」がプロジェクトへ書き戻されてしまう。
    _block_all_signals の取りこぼし(collect が読む widget を block し忘れる)を
    検出する、振る舞い側からの検査。
    """
    _mutate_every_control(window)
    settings = window._gather_settings_from_ui()
    window._apply_settings_to_ui_controls(window._gather_settings_from_ui())

    calls = []
    monkeypatch.setattr(window, "_on_axis_setting_changed", lambda: calls.append(True))

    window._apply_settings_to_ui_controls(settings)

    assert calls == [], "apply 中に _on_axis_setting_changed が呼ばれた(signalの取りこぼし)"


def test_signals_are_unblocked_after_apply(window):
    _mutate_every_control(window)
    window._apply_settings_to_ui_controls(window._gather_settings_from_ui())

    assert not window.ui.x_min_spinbox.signalsBlocked()
    assert not window.ui.title_text_edit.signalsBlocked()
    assert not window.colorbar_label_edit.signalsBlocked()


def test_signals_are_unblocked_even_when_apply_raises(window, monkeypatch):
    """apply は例外を握りつぶして警告ダイアログを出す作りなので、
    その場合でも finally でシグナルが必ず戻ること(戻らないとUIが無反応になる)。"""
    shown = []
    monkeypatch.setattr(
        notify_module.QMessageBox, "warning",
        staticmethod(lambda *a, **k: shown.append(a)),
    )
    monkeypatch.setattr(
        window.ui.title_text_edit, "setText",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    window._apply_settings_to_ui_controls({})

    assert shown, "例外時は警告ダイアログを出すこと"
    assert not window.ui.x_min_spinbox.signalsBlocked()


# =============================================================================
# 既定値と後方互換
# =============================================================================

def test_applying_an_empty_dict_falls_back_to_documented_defaults(window):
    """空の辞書(=キーを1つも持たない古いプロジェクト)でも例外にならず、
    既定値が入ること。"""
    _mutate_every_control(window)

    window._apply_settings_to_ui_controls({})
    settings = window._gather_settings_from_ui()

    assert settings['title'] == ''
    assert settings['x_autoscale'] is True
    assert settings['x_log'] is False
    assert settings['legend_visible'] is True
    assert settings['legend_loc'] == 'best'
    assert settings['grid_visible'] is False
    assert settings['x_major_grid_linestyle'] == '-'
    assert settings['x_minor_grid_linestyle'] == '--'
    assert settings['x_major_grid_width'] == pytest.approx(0.8)
    assert settings['x_minor_grid_width'] == pytest.approx(0.5)
    assert settings['major_tick_direction'] == 'out'
    assert settings['major_tick_length'] == pytest.approx(3.5)
    assert settings['minor_tick_length'] == -1
    assert settings['colorbar_enabled'] is True
    assert settings['colorbar_position'] == 'right'


def test_legacy_shared_tick_visibility_keys_seed_both_axes(window):
    """v1.3.2で導入した軸共通の ticks_visible / tick_labels_visible しか持たない
    既存プロジェクトでは、その値をX/Y両方の既定値として使う
    (gui/canvas.py の _apply_appearance と同じフォールバック方針)。"""
    window._apply_settings_to_ui_controls(
        {'ticks_visible': False, 'tick_labels_visible': False})
    settings = window._gather_settings_from_ui()

    assert settings['x_ticks_visible'] is False
    assert settings['y_ticks_visible'] is False
    assert settings['x_tick_labels_visible'] is False
    assert settings['y_tick_labels_visible'] is False


def test_per_axis_tick_visibility_wins_over_the_legacy_key(window):
    window._apply_settings_to_ui_controls(
        {'ticks_visible': False, 'x_ticks_visible': True})
    settings = window._gather_settings_from_ui()

    assert settings['x_ticks_visible'] is True
    assert settings['y_ticks_visible'] is False


def test_unknown_combo_values_fall_back_to_the_first_entry(window):
    """保存値が現在の選択肢に無い(将来の値/壊れたファイル)場合でも
    例外にせず先頭へフォールバックすること。"""
    window._apply_settings_to_ui_controls({
        'x_log_minor_subs': 'no-such-value',
        'colorbar_position': 'no-such-position',
        'x_secondary_axis_source_unit': 'no-such-unit',
    })
    settings = window._gather_settings_from_ui()

    assert settings['x_log_minor_subs'] == window.x_log_minor_subs_combo.itemData(0)
    assert settings['colorbar_position'] == window.colorbar_position_combo.itemData(0)


# =============================================================================
# UIコントロールを持たないキーの引き継ぎ
# =============================================================================

def test_annotations_and_legend_order_are_carried_over_from_the_project(window):
    """★ collect は辞書を毎回「総入れ替え」するため、UIコントロールを持たない
    これらを明示的に引き継がないと、軸設定を1つ変えただけで注釈が消える。"""
    index = window.project.active_axis_index
    window.project.all_plot_settings[index]['annotations'] = [{'type': 'text', 'text': 'メモ'}]
    window.project.all_plot_settings[index]['legend_order'] = ['b', 'a']
    window.project.all_plot_settings[index]['free_rect'] = (0.1, 0.2, 0.3, 0.4)

    settings = window._gather_settings_from_ui()

    assert settings['annotations'] == [{'type': 'text', 'text': 'メモ'}]
    assert settings['legend_order'] == ['b', 'a']
    assert settings['free_rect'] == (0.1, 0.2, 0.3, 0.4)


def test_non_ui_keys_default_to_empty_when_the_axis_index_is_out_of_range(window):
    window.project.active_axis_index = len(window.project.all_plot_settings) + 5

    settings = window._gather_settings_from_ui()

    assert settings['annotations'] == []
    assert settings['legend_order'] == []
    assert settings['free_rect'] is None


# =============================================================================
# 小さなヘルパー
# =============================================================================

@pytest.mark.parametrize("code", ['-', '--', '-.', ':'])
def test_grid_linestyle_code_and_index_round_trip(window, code):
    index = window._grid_linestyle_index(code)
    assert window._grid_linestyle_code(index) == code


def test_font_props_to_dict_keeps_the_whole_fallback_list(window):
    """★ family は単一名ではなく qfont.families() のフォールバック候補リスト
    として保存する。先頭1件に潰すと、macOSに存在しないフォント名だけが残って
    日本語が文字化けする(既存のコメント参照)。"""
    font = QFont()
    font.setFamilies(["Yu Gothic", "Hiragino Sans", "sans-serif"])
    font.setPointSize(13)
    font.setBold(True)
    font.setItalic(False)

    props = window._font_props_to_dict(font)

    assert isinstance(props['family'], list)
    assert len(props['family']) == 3
    assert props['size'] == 13
    assert props['weight'] == 'bold'
    assert props['style'] == 'normal'


def test_font_props_survive_the_settings_round_trip(window):
    font = QFont("Arial")
    font.setPointSize(19)
    font.setBold(True)
    font.setItalic(True)
    window._tick_font = QFont(font)

    settings = window._gather_settings_from_ui()
    window._apply_settings_to_ui_controls(settings)

    assert window._tick_font.pointSize() == 19
    assert window._tick_font.bold() is True
    assert window._tick_font.italic() is True


# =============================================================================
# シグナル配線が繋がっているか(端から端まで)
# =============================================================================

def test_changing_any_control_reaches_the_project_settings(window):
    """
    ★ ウィジェットを操作したら、その値が
    project.all_plot_settings[active_axis_index] まで届くこと。

    これは gui/mixins/ui_setup_mixin.py の _connect_signals() が、
    _gather_settings_from_ui() が読む各ウィジェットをちゃんと
    _on_axis_setting_changed へ繋いでいるかの検査でもある。繋ぎ忘れると
    「操作しても何も起きない(プロットは変わるのに保存されない)」という
    分かりにくい壊れ方をする。

    改善ボード C-1(プロパティパネルのサブセクション化)でパネルを組み直す
    際、再配線の漏れをここで検出できる。

    1ウィンドウを使い回して全ウィジェットを順に確認する(PlotterAppの生成は
    1回あたり1〜2秒かかるため、パラメータ化して毎回作り直すと遅すぎる)。
    """
    ui = window.ui
    # (設定キー, 変更を行う関数, 期待値)
    cases = [
        ('title', lambda: ui.title_text_edit.setText("T"), "T"),
        ('x_label', lambda: ui.x_label_text_edit.setText("XL"), "XL"),
        ('y_label', lambda: ui.y_label_text_edit.setText("YL"), "YL"),
        ('y2_label', lambda: window.y2_label_text_edit.setText("Y2"), "Y2"),
        ('x_label_visible', lambda: window.x_label_visible_checkbox.setChecked(False), False),
        ('y_label_visible', lambda: window.y_label_visible_checkbox.setChecked(False), False),
        ('x_log', lambda: ui.x_log_checkbox.setChecked(True), True),
        ('x_invert', lambda: ui.x_invert_checkbox.setChecked(True), True),
        ('x_major_tick_mode', lambda: ui.x_major_tick_mode_combo.setCurrentIndex(1), 1),
        ('x_major_tick_interval', lambda: ui.x_major_tick_interval_spinbox.setValue(2.5), 2.5),
        ('x_minor_ticks_visible', lambda: ui.x_minor_ticks_visible_checkbox.setChecked(True), True),
        ('x_minor_tick_interval', lambda: ui.x_minor_tick_interval_spinbox.setValue(0.25), 0.25),
        ('x_log_minor_labels', lambda: window.x_log_minor_labels_checkbox.setChecked(True), True),
        ('x_tick_format_mode', lambda: window.x_tick_format_combo.setCurrentIndex(1), 1),
        ('x_tick_decimals', lambda: window.x_tick_decimals_spinbox.setValue(3), 3),
        ('y_log', lambda: ui.y_log_checkbox.setChecked(True), True),
        ('y_invert', lambda: ui.y_invert_checkbox.setChecked(True), True),
        ('y_major_tick_mode', lambda: ui.y_major_tick_mode_combo.setCurrentIndex(1), 1),
        ('y_major_tick_interval', lambda: ui.y_major_tick_interval_spinbox.setValue(3.5), 3.5),
        ('y_minor_ticks_visible', lambda: ui.y_minor_ticks_visible_checkbox.setChecked(True), True),
        ('y_minor_tick_interval', lambda: ui.y_minor_tick_interval_spinbox.setValue(0.75), 0.75),
        ('y_log_minor_labels', lambda: window.y_log_minor_labels_checkbox.setChecked(True), True),
        ('y_tick_format_mode', lambda: window.y_tick_format_combo.setCurrentIndex(1), 1),
        ('y_tick_decimals', lambda: window.y_tick_decimals_spinbox.setValue(4), 4),
        ('legend_visible', lambda: ui.legend_visible_checkbox.setChecked(False), False),
        ('grid_visible', lambda: ui.grid_visible_checkbox.setChecked(True), True),
        ('minor_grid_visible', lambda: ui.minor_grid_visible_checkbox.setChecked(True), True),
        # ★ グリッド幅のスピンボックスは小数1桁に丸めるため、1.75のような値を
        # 入れると1.8になる(ウィジェット側の仕様)。刻みに乗る値を使う。
        ('x_major_grid_width', lambda: window.x_major_grid_width_spinbox.setValue(1.8), 1.8),
        ('x_major_grid_alpha', lambda: window.x_major_grid_alpha_spinbox.setValue(0.35), 0.35),
        ('y_minor_grid_width', lambda: window.y_minor_grid_width_spinbox.setValue(1.3), 1.3),
        ('major_tick_direction', lambda: window.major_tick_direction_combo.setCurrentText("in"), "in"),
        ('minor_tick_direction', lambda: window.minor_tick_direction_combo.setCurrentText("in"), "in"),
        ('major_tick_direction_y2', lambda: window.major_tick_direction_y2_combo.setCurrentText("in"), "in"),
        ('x_ticks_visible', lambda: window.x_ticks_visible_checkbox.setChecked(False), False),
        ('x_tick_labels_visible', lambda: window.x_tick_labels_visible_checkbox.setChecked(False), False),
        ('y_ticks_visible', lambda: window.y_ticks_visible_checkbox.setChecked(False), False),
        ('y_tick_labels_visible', lambda: window.y_tick_labels_visible_checkbox.setChecked(False), False),
        ('tick_width', lambda: ui.tick_width_spinbox.setValue(2.25), 2.25),
        ('spine_width', lambda: ui.spine_width_spinbox.setValue(3.25), 3.25),
        ('colorbar_enabled', lambda: window.colorbar_enabled_checkbox.setChecked(False), False),
        ('colorbar_width_fraction', lambda: window.colorbar_width_spinbox.setValue(0.12), 0.12),
        ('colorbar_label', lambda: window.colorbar_label_edit.setText("CB"), "CB"),
    ]

    not_wired = []
    for key, mutate, expected in cases:
        mutate()
        index = window.project.active_axis_index
        stored = window.project.all_plot_settings[index].get(key)
        if isinstance(expected, float):
            ok = stored is not None and abs(stored - expected) < 1e-9
        else:
            ok = stored == expected
        if not ok:
            not_wired.append(f"{key}: 期待 {expected!r} / 実際 {stored!r}")

    assert not not_wired, "操作がプロジェクト設定へ届いていないキー:\n" + "\n".join(not_wired)
