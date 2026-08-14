# tests/test_layout_edit_mixin.py
"""
自由配置レイアウト(項目37)のマウスドラッグと、数値入力(項目85)の
回帰・整合性テスト。

数値入力(X/Y/幅/高さスピンボックス)とマウスドラッグは、どちらも最終的に
ax.set_position() + project.all_plot_settings[axis_index]['free_rect'] への
書き込みという同じ経路を通る設計になっている
(gui/mixins/layout_edit_mixin.py の _sync_free_layout_position_controls /
_on_free_layout_position_spinbox_changed を参照)。
このテストでは、その2つの経路が食い違わないことと、既存のマウスドラッグ
(press/motion/release) の挙動が数値入力の追加後も変わっていないことを確認する。

PlotterApp のインスタンス化パターンは tests/test_main_window.py と同じ
(QSettingsを一時ファイルにリダイレクトする)。
"""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 700)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _enable_free_layout_edit_mode(window):
    """自由配置レイアウトをONにし、レイアウト編集モードも有効化するヘルパー。"""
    window.free_layout_checkbox.setChecked(True)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    window.layout_edit_action.setChecked(True)
    window._toggle_layout_edit_mode(True)


def _press(window, axis_index, near_corner=False):
    """指定した軸のbbox内(既定は中心、near_corner=Trueなら右下端付近)をクリックする"""
    ax = window.canvas.all_axes[axis_index]
    bbox = ax.bbox
    if near_corner:
        x, y = bbox.x1 - 1, bbox.y0 + 1
    else:
        x, y = (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2
    window._on_layout_press(SimpleNamespace(x=x, y=y))


def test_numeric_input_updates_axis_and_settings(tmp_path, monkeypatch):
    """
    数値入力(X/Y/幅/高さ)で値を設定すると、ax.get_position()と
    project.all_plot_settings[axis_index]['free_rect']の両方が即座に更新されることを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _enable_free_layout_edit_mode(window)

    # クリックしてサブプロット0を「選択」状態にする
    _press(window, axis_index=0)
    assert window._layout_selected_axis_index == 0
    assert not window.free_layout_position_group.isHidden()

    window.free_layout_x_spinbox.setValue(0.2)
    window.free_layout_y_spinbox.setValue(0.15)
    window.free_layout_width_spinbox.setValue(0.5)
    window.free_layout_height_spinbox.setValue(0.4)

    pos = window.canvas.all_axes[0].get_position()
    assert pos.x0 == pytest.approx(0.2, abs=1e-6)
    assert pos.y0 == pytest.approx(0.15, abs=1e-6)
    assert pos.width == pytest.approx(0.5, abs=1e-6)
    assert pos.height == pytest.approx(0.4, abs=1e-6)

    saved_rect = window.project.all_plot_settings[0]['free_rect']
    assert saved_rect == pytest.approx((0.2, 0.15, 0.5, 0.4), abs=1e-6)


def test_numeric_input_roundtrip_after_mouse_drag(tmp_path, monkeypatch):
    """
    マウスドラッグで動かした後、数値入力欄を読み返すとドラッグ後の実際の位置が
    反映されていること(=数値入力とドラッグが同じ状態を共有していること)を確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _enable_free_layout_edit_mode(window)

    ax = window.canvas.all_axes[0]
    original_pos = ax.get_position()

    _press(window, axis_index=0, near_corner=False)  # moveモードで選択+ドラッグ開始
    start_x, start_y = window._layout_drag_state['start_mouse']
    dx_px, dy_px = 40, -20
    window._on_layout_motion(SimpleNamespace(x=start_x + dx_px, y=start_y + dy_px))
    window._on_layout_release(SimpleNamespace(x=start_x + dx_px, y=start_y + dy_px))

    moved_pos = ax.get_position()
    assert moved_pos.x0 != pytest.approx(original_pos.x0, abs=1e-6)

    # 数値入力欄を読み返すと、ドラッグ後の実際の位置と一致するはず(往復確認)
    assert window.free_layout_x_spinbox.value() == pytest.approx(moved_pos.x0, abs=1e-3)
    assert window.free_layout_y_spinbox.value() == pytest.approx(moved_pos.y0, abs=1e-3)
    assert window.free_layout_width_spinbox.value() == pytest.approx(moved_pos.width, abs=1e-3)
    assert window.free_layout_height_spinbox.value() == pytest.approx(moved_pos.height, abs=1e-3)

    # all_plot_settingsにも保存されている
    saved_rect = window.project.all_plot_settings[0]['free_rect']
    assert saved_rect[0] == pytest.approx(moved_pos.x0, abs=1e-6)
    assert saved_rect[1] == pytest.approx(moved_pos.y0, abs=1e-6)


def test_mouse_drag_press_motion_release_regression(tmp_path, monkeypatch):
    """
    回帰テスト: 既存のマウスドラッグ(リサイズ)挙動が、数値入力機能の追加後も
    変わっていないことを確認する。右下端付近をドラッグすると'resize'モードになり、
    幅・高さが変化し、リリース時にall_plot_settingsへ保存される。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _enable_free_layout_edit_mode(window)

    ax = window.canvas.all_axes[0]
    original_pos = ax.get_position()

    _press(window, axis_index=0, near_corner=True)
    assert window._layout_drag_state['mode'] == 'resize'

    start_x, start_y = window._layout_drag_state['start_mouse']
    window._on_layout_motion(SimpleNamespace(x=start_x + 30, y=start_y + 10))
    resized_pos = ax.get_position()
    assert resized_pos.width != pytest.approx(original_pos.width, abs=1e-6)
    assert resized_pos.height != pytest.approx(original_pos.height, abs=1e-6)
    # 左上角(left, top)が固定されたまま伸縮しているはず(既存仕様)
    assert resized_pos.x0 == pytest.approx(original_pos.x0, abs=1e-6)
    assert (resized_pos.y0 + resized_pos.height) == pytest.approx(
        original_pos.y0 + original_pos.height, abs=1e-6
    )

    window._on_layout_release(SimpleNamespace(x=start_x + 30, y=start_y + 10))
    assert window._layout_drag_state is None
    saved_rect = window.project.all_plot_settings[0]['free_rect']
    assert saved_rect[2] == pytest.approx(resized_pos.width, abs=1e-6)
    assert saved_rect[3] == pytest.approx(resized_pos.height, abs=1e-6)


def test_mouse_leaving_canvas_mid_drag_ends_the_drag_instead_of_leaving_a_phantom(tmp_path, monkeypatch):
    """
    回帰テスト: ドラッグ中にマウスカーソルがアプリウィンドウの外まで出て
    そこでボタンを離すと、canvasにはbutton_release_eventが届かず
    _layout_drag_stateが残留していた。その状態のままカーソルを(ボタンを
    押さずに)動かすだけで、_on_layout_motionが最後に触っていたサブプロット
    を勝手に動かし続けてしまう「幽霊ドラッグ」バグがあった。
    figure_leave_eventでドラッグ状態がきちんと確定・解除されることを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _enable_free_layout_edit_mode(window)

    ax = window.canvas.all_axes[0]
    original_pos = ax.get_position()

    _press(window, axis_index=0, near_corner=False)
    start_x, start_y = window._layout_drag_state['start_mouse']
    window._on_layout_motion(SimpleNamespace(x=start_x + 40, y=start_y - 20))
    dragged_pos = ax.get_position()
    assert dragged_pos.x0 != pytest.approx(original_pos.x0, abs=1e-6)

    # ボタンを離さないままマウスがfigure領域を出た(button_release_eventは届かない)
    window._on_layout_release(SimpleNamespace(x=None, y=None))  # figure_leave_eventに接続されたのと同じハンドラ
    assert window._layout_drag_state is None

    # この後、ボタンを押さずにマウスを動かしても(=ツールバーへ移動する等)、
    # 直前のサブプロットが勝手に動いてはいけない。
    settled_pos = ax.get_position()
    window._on_layout_motion(SimpleNamespace(x=start_x + 200, y=start_y + 200))
    assert ax.get_position().x0 == pytest.approx(settled_pos.x0, abs=1e-9)
    assert ax.get_position().y0 == pytest.approx(settled_pos.y0, abs=1e-9)


def test_clicking_outside_axis_deselects_and_hides_controls(tmp_path, monkeypatch):
    """
    サブプロット外をクリックすると選択が解除され、数値入力グループが隠れることを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _enable_free_layout_edit_mode(window)

    _press(window, axis_index=0)
    assert window._layout_selected_axis_index == 0
    assert not window.free_layout_position_group.isHidden()

    # Figureの外側(bboxに含まれない座標)をクリック
    window._on_layout_press(SimpleNamespace(x=-100, y=-100))
    assert window._layout_selected_axis_index is None
    assert window.free_layout_position_group.isHidden()


def test_removing_free_subplot_reassigns_datasets_instead_of_hiding_them(tmp_path, monkeypatch):
    """
    回帰テスト: 自由配置レイアウトで「- プロット削除」を押すと
    all_plot_settingsの末尾が削除されるが、削除された番号を
    subplot_targetに持つデータセットはそのままだと放置され、
    どの軸にも描画されずサイレントに消えていた
    (gui/mixins/settings_mixin.py の _on_layout_changed と同種のバグ)。
    """
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.free_layout_checkbox.setChecked(True)
    window._on_add_free_subplot()  # index 0, 1 の2枚構成にする
    assert len(window.project.all_plot_settings) == 2

    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
                 x_col_name="x", y_col_name="y", subplot_target=1)
    window.project.datasets.append(ds)
    window._update_plot()

    window._on_remove_free_subplot()  # 1枚(index 0)に戻す

    assert ds.subplot_target == 0
    assert len(window.canvas.all_axes) == 1


def test_numeric_controls_hidden_when_not_in_free_layout_mode(tmp_path, monkeypatch):
    """
    自由配置レイアウトがOFFの間(既定状態)は、数値入力グループが表示されないことを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.free_layout_position_group.isHidden()


# --- 項目C-601: 軸共有(sharex/sharey)チェックボックス ---

def test_share_axis_checkboxes_update_project_and_replot(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.project.share_x_axis is False
    assert window.project.share_y_axis is False

    window.share_x_checkbox.setChecked(True)
    assert window.project.share_x_axis is True

    window.share_y_checkbox.setChecked(True)
    assert window.project.share_y_axis is True

    window.share_x_checkbox.setChecked(False)
    assert window.project.share_x_axis is False


def test_share_axis_checkboxes_disabled_in_free_layout_mode(tmp_path, monkeypatch):
    """
    軸共有はグリッドレイアウト時のみ意味を持つため、自由配置レイアウトが
    ONの間はrows/colsスピンボックスと同様にチェックボックス自体を無効化する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.share_x_checkbox.isEnabled()
    assert window.share_y_checkbox.isEnabled()

    window.free_layout_checkbox.setChecked(True)
    assert not window.share_x_checkbox.isEnabled()
    assert not window.share_y_checkbox.isEnabled()

    window.free_layout_checkbox.setChecked(False)
    assert window.share_x_checkbox.isEnabled()
    assert window.share_y_checkbox.isEnabled()
