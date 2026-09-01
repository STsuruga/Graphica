# tests/test_annotation_mixin.py
"""
gui/mixins/annotation_mixin.py のスナップ・トゥ・グリッド機能(項目84)に対するテスト。

- _snap_point_to_grid 単体のピクセル空間での丸め処理
- 注釈モードのドラッグ確定 (_on_annotation_press/_on_annotation_release) が
  スナップ有効/無効それぞれで期待どおりの位置をSetAnnotationsCommand経由で
  self.undo_stack にpushすることの回帰テスト
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from gui.mixins.annotation_mixin import (
    AnnotationMixin, DEFAULT_SNAP_TO_GRID_ENABLED, DEFAULT_SNAP_GRID_INTERVAL_PX,
)


class _SnapHost(AnnotationMixin):
    """_snap_point_to_grid だけを単体テストするための最小ホスト。"""
    def __init__(self, snap_to_grid_enabled, snap_grid_interval_px):
        self.snap_to_grid_enabled = snap_to_grid_enabled
        self.snap_grid_interval_px = snap_grid_interval_px


# --- _snap_point_to_grid (ピクセル空間での丸め) ---

def test_snap_point_to_grid_disabled_returns_exact_input():
    """スナップ無効時は、座標変換を経由せず入力をそのまま返す(既存挙動と完全一致)。"""
    fig, ax = plt.subplots()
    host = _SnapHost(snap_to_grid_enabled=False, snap_grid_interval_px=10)

    x, y = 1.23456789, 9.87654321
    result_x, result_y = host._snap_point_to_grid(ax, x, y)

    assert result_x == x
    assert result_y == y
    plt.close(fig)


def test_snap_point_to_grid_enabled_rounds_to_pixel_multiple():
    """スナップ有効時は、データ座標をピクセル空間へ変換した値が、設定した間隔の
    ちょうど倍数になっていること(=ピクセル単位で整列している)を確認する。"""
    fig, ax = plt.subplots()
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    interval = 10
    host = _SnapHost(snap_to_grid_enabled=True, snap_grid_interval_px=interval)

    # 任意の(グリッドに乗っていない)データ座標
    x, y = 37.3, 62.9
    snapped_x, snapped_y = host._snap_point_to_grid(ax, x, y)

    px, py = ax.transData.transform((snapped_x, snapped_y))
    assert px == pytest.approx(round(px / interval) * interval, abs=1e-6)
    assert py == pytest.approx(round(py / interval) * interval, abs=1e-6)
    # 実際にちょうど interval の倍数になっていること
    assert abs(px % interval) < 1e-6 or abs(px % interval - interval) < 1e-6
    assert abs(py % interval) < 1e-6 or abs(py % interval - interval) < 1e-6
    plt.close(fig)


def test_snap_point_to_grid_zero_interval_is_noop():
    """0以下の間隔はゼロ除算を避けるため、スナップせず入力をそのまま返す。"""
    fig, ax = plt.subplots()
    host = _SnapHost(snap_to_grid_enabled=True, snap_grid_interval_px=0)

    x, y = 5.5, 6.6
    result_x, result_y = host._snap_point_to_grid(ax, x, y)

    assert result_x == x
    assert result_y == y
    plt.close(fig)


# --- 注釈モードのドラッグ確定 (統合テスト: 実際のPlotterAppを使う) ---

class _FakeMplEvent:
    """matplotlibの button_press_event / button_release_event を模した最小オブジェクト。"""
    def __init__(self, inaxes, xdata, ydata, button=1):
        self.inaxes = inaxes
        self.xdata = xdata
        self.ydata = ydata
        self.button = button


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る
    (tests/test_main_window.py と同じパターン)。"""
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


def test_annotation_drag_without_snap_produces_exact_unsnapped_position(tmp_path, monkeypatch):
    """回帰テスト: スナップ・トゥ・グリッドが無効(既定)の場合、ドラッグした通りの
    厳密なデータ座標で矢印注釈が追加されること。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.snap_to_grid_enabled is False  # 既定はOFF

    ax = window.all_axes[0]
    window.annotation_mode_enabled = True

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", True)))

    start_x, start_y = 1.0, 2.0
    end_x, end_y = 5.0, 8.0

    window._on_annotation_press(_FakeMplEvent(ax, start_x, start_y))
    window._on_annotation_release(_FakeMplEvent(ax, end_x, end_y))

    annotations = window.project.all_plot_settings[0]['annotations']
    assert len(annotations) == 1
    ann = annotations[0]
    assert ann['type'] == 'arrow'
    assert ann['xy'] == (end_x, end_y)
    assert ann['xytext'] == (start_x, start_y)


def test_annotation_drag_with_snap_enabled_snaps_pixel_position(tmp_path, monkeypatch):
    """スナップ・トゥ・グリッド有効時、ドラッグ先の任意のピクセル位置が、
    設定したグリッド間隔のちょうど倍数のピクセル座標に吸着すること。

    ★ 注意: 注釈追加後は SetAnnotationsCommand の on_applied
    (_update_plot_appearance -> canvas.update_appearance_only) が走り、
    レイアウトエンジンの再計算により同じAxesオブジェクトでも
    transData(データ座標→ピクセル座標の写像)自体がズレうる
    (fig.clf() は呼ばれないため CLAUDE.md の「Axesの参照が丸ごと無効になる」
    ケースには当たらないが、位置の再計算は起こりうる)。そのため、
    「実際にピクセル座標がグリッドの倍数になっているか」は、_snap_point_to_grid
    単体のテスト(test_snap_point_to_grid_enabled_rounds_to_pixel_multiple)で
    再描画の影響を受けない形ですでに検証済み。ここでは、ドラッグ確定処理が
    実装(_snap_point_to_grid)と全く同じ計算結果をコミットしていることだけを
    確認する(=ドラッグ確定前のtransDataを基準に独立計算した期待値と一致するか)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    interval = 20
    window.snap_to_grid_enabled = True
    window.snap_grid_interval_px = interval

    ax = window.all_axes[0]
    window.annotation_mode_enabled = True

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", True)))

    start_x, start_y = 1.0, 2.0
    end_x, end_y = 5.3, 8.7  # わざとグリッドに乗っていない任意の位置

    # ドラッグ確定(=軸の表示範囲がまだ変わっていない時点)で期待されるスナップ後の
    # データ座標・ピクセル座標を、実装と同じロジック(_snap_point_to_grid)を使い、
    # かつイベント発火(=再描画によるtransDataのズレ)より前にすべて計算しておく
    snap_host = _SnapHost(snap_to_grid_enabled=True, snap_grid_interval_px=interval)
    expected_end = snap_host._snap_point_to_grid(ax, end_x, end_y)
    expected_start = snap_host._snap_point_to_grid(ax, start_x, start_y)
    raw_head_px = ax.transData.transform((end_x, end_y))
    expected_head_px = ax.transData.transform(expected_end)

    window._on_annotation_press(_FakeMplEvent(ax, start_x, start_y))
    window._on_annotation_release(_FakeMplEvent(ax, end_x, end_y))

    annotations = window.project.all_plot_settings[0]['annotations']
    assert len(annotations) == 1
    ann = annotations[0]

    assert ann['xy'] == pytest.approx(expected_end)
    assert ann['xytext'] == pytest.approx(expected_start)

    # スナップにより、ドラッグした生のマウス位置とは異なる座標に補正されていること
    assert ann['xy'] != (end_x, end_y)
    assert ann['xytext'] != (start_x, start_y)

    # 期待値自体が「ドラッグ確定前」のピクセル空間でグリッド間隔のちょうど倍数に
    # なっていること(_snap_point_to_grid の計算結果としての整合性)
    assert expected_head_px[0] == pytest.approx(round(raw_head_px[0] / interval) * interval)
    assert expected_head_px[1] == pytest.approx(round(raw_head_px[1] / interval) * interval)

    # Undo/Redo経由であること(SetAnnotationsCommandがundo_stackへpushされている)
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert window.project.all_plot_settings[0]['annotations'] == []
    window.undo_stack.redo()
    assert len(window.project.all_plot_settings[0]['annotations']) == 1


def test_snap_to_grid_settings_persist_and_restore_via_qsettings(tmp_path, monkeypatch):
    """環境設定で保存したスナップ・トゥ・グリッドの有効/無効・間隔(px)が、
    QSettingsのキー ("snap_to_grid_enabled", "snap_grid_interval_px") 経由で
    次回起動時のPlotterAppにも復元されること。"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)

    # 事前にQSettingsへ「有効・間隔25px」を書き込んでおく
    pre_settings = IsolatedQSettings()
    pre_settings.setValue("snap_to_grid_enabled", True)
    pre_settings.setValue("snap_grid_interval_px", 25)
    pre_settings.sync()

    window = PlotterApp(run_startup_checks=False, tab_id=2)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    assert window.snap_to_grid_enabled is True
    assert window.snap_grid_interval_px == 25


def test_snap_to_grid_defaults_match_module_constants():
    assert DEFAULT_SNAP_TO_GRID_ENABLED is False
    assert DEFAULT_SNAP_GRID_INTERVAL_PX == 10


# --------------------------------------------------------------------
# _toggle_annotation_mode
# --------------------------------------------------------------------

def test_toggle_annotation_mode_on_turns_off_cursor_mode_first(tmp_path, monkeypatch):
    """注釈モードとデータカーソルモードは排他: 注釈ONでカーソルモードが自動的にOFFになる"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.cursor_action.setChecked(True)
    window.cursor_mode_enabled = True

    window._toggle_annotation_mode(True)

    assert window.cursor_action.isChecked() is False
    assert window.cursor_mode_enabled is False
    assert window.annotation_mode_enabled is True
    assert window._annotation_press_cid is not None
    assert window._annotation_release_cid is not None
    assert window.statusBar().currentMessage() != ""


def test_toggle_annotation_mode_off_disconnects_and_clears_drag_state(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._toggle_annotation_mode(True)
    assert window._annotation_press_cid is not None
    window._annotation_drag_start = (window.all_axes[0], 1.0, 2.0)

    window._toggle_annotation_mode(False)

    assert window.annotation_mode_enabled is False
    assert window._annotation_press_cid is None
    assert window._annotation_release_cid is None
    assert window._annotation_drag_start is None


# --------------------------------------------------------------------
# _find_axis_index
# --------------------------------------------------------------------

def test_find_axis_index_returns_secondary_axis_position(tmp_path, monkeypatch):
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
                 x_col_name="x", y_col_name="y", use_secondary_y=True)
    window.project.datasets.append(ds)
    window._update_plot()
    sec_ax = window.all_secondary_axes[0]
    assert sec_ax is not None

    assert window._find_axis_index(sec_ax) == 0


def test_find_axis_index_returns_none_for_unknown_axes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    stray_fig, stray_ax = plt.subplots()
    try:
        assert window._find_axis_index(stray_ax) is None
    finally:
        plt.close(stray_fig)


# --------------------------------------------------------------------
# _on_annotation_press / _on_annotation_release: 早期returnとガード条件
# --------------------------------------------------------------------

def test_on_annotation_press_ignored_when_mode_disabled(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = False
    ax = window.all_axes[0]

    window._on_annotation_press(_FakeMplEvent(ax, 1.0, 2.0))

    assert window._annotation_drag_start is None


def test_on_annotation_press_ignored_when_outside_axes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = True

    window._on_annotation_press(_FakeMplEvent(None, None, None))

    assert window._annotation_drag_start is None


def test_on_annotation_press_right_click_attempts_deletion_instead_of_starting_drag(tmp_path, monkeypatch):
    """右クリック(button==3)は既存注釈の削除を試み、ドラッグ開始状態を作らない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = True
    ax = window.all_axes[0]
    calls = []
    monkeypatch.setattr(window, "_try_delete_annotation_near", lambda event: calls.append(event))

    window._on_annotation_press(_FakeMplEvent(ax, 1.0, 2.0, button=3))

    assert len(calls) == 1
    assert window._annotation_drag_start is None


def test_on_annotation_release_ignored_when_mode_disabled(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = False
    window._annotation_drag_start = (window.all_axes[0], 1.0, 2.0)

    window._on_annotation_release(_FakeMplEvent(window.all_axes[0], 1.0, 2.0))

    # ガード節で即returnし、drag_startは(このメソッドによっては)変更されない
    assert window._annotation_drag_start == (window.all_axes[0], 1.0, 2.0)


def test_on_annotation_release_ignored_when_no_drag_in_progress(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = True
    window._annotation_drag_start = None

    window._on_annotation_release(_FakeMplEvent(window.all_axes[0], 1.0, 2.0))

    assert window.project.all_plot_settings[0]['annotations'] == []


def test_on_annotation_release_ignored_when_released_on_different_axes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.free_layout_checkbox.setChecked(True)
    window._on_add_free_subplot()
    assert len(window.all_axes) == 2
    window.annotation_mode_enabled = True

    window._on_annotation_press(_FakeMplEvent(window.all_axes[0], 1.0, 2.0))
    window._on_annotation_release(_FakeMplEvent(window.all_axes[1], 1.0, 2.0))

    assert window.project.all_plot_settings[0]['annotations'] == []
    assert window.project.all_plot_settings[1]['annotations'] == []
    assert window._annotation_drag_start is None  # 消費はされている


def test_on_annotation_release_ignored_when_axis_index_cannot_be_resolved(tmp_path, monkeypatch):
    """開始/終了したAxesがall_axes/all_secondary_axesのどちらにも属さない場合は何もしない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = True
    stray_fig, stray_ax = plt.subplots()
    try:
        window._on_annotation_press(_FakeMplEvent(stray_ax, 1.0, 2.0))
        window._on_annotation_release(_FakeMplEvent(stray_ax, 1.0, 2.0))
        assert window.project.all_plot_settings[0]['annotations'] == []
    finally:
        plt.close(stray_fig)


# --------------------------------------------------------------------
# _on_annotation_release: クリック(=テキスト注釈)経路の成功/キャンセル
# --------------------------------------------------------------------

def test_click_without_drag_adds_text_annotation(tmp_path, monkeypatch):
    """ほぼ動かないクリックはテキスト注釈として追加される(ドラッグでなくクリック判定の成功経路)"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = True
    ax = window.all_axes[0]
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("メモ", True)))

    window._on_annotation_press(_FakeMplEvent(ax, 1.0, 2.0))
    window._on_annotation_release(_FakeMplEvent(ax, 1.0, 2.0))  # 同じ位置=クリック扱い

    annotations = window.project.all_plot_settings[0]['annotations']
    assert len(annotations) == 1
    assert annotations[0]['type'] == 'text'
    assert annotations[0]['text'] == 'メモ'
    assert annotations[0]['xy'] == (1.0, 2.0)


def test_click_without_drag_cancelled_dialog_adds_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = True
    ax = window.all_axes[0]
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))

    window._on_annotation_press(_FakeMplEvent(ax, 1.0, 2.0))
    window._on_annotation_release(_FakeMplEvent(ax, 1.0, 2.0))

    assert window.project.all_plot_settings[0]['annotations'] == []


def test_drag_cancelled_arrow_dialog_adds_nothing(tmp_path, monkeypatch):
    """十分に動いた(ドラッグ)場合でも、ラベル入力ダイアログをキャンセルすれば何も追加されない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = True
    ax = window.all_axes[0]
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))

    window._on_annotation_press(_FakeMplEvent(ax, 1.0, 2.0))
    window._on_annotation_release(_FakeMplEvent(ax, 5.0, 8.0))

    assert window.project.all_plot_settings[0]['annotations'] == []


# --------------------------------------------------------------------
# _try_delete_annotation_near
# --------------------------------------------------------------------

def test_delete_annotation_near_ignored_when_axis_unresolvable(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    stray_fig, stray_ax = plt.subplots()
    try:
        window._try_delete_annotation_near(_FakeMplEvent(stray_ax, 1.0, 2.0))  # 例外なく何もしない
    finally:
        plt.close(stray_fig)


def test_delete_annotation_near_ignored_when_no_annotations_exist(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ax = window.all_axes[0]
    assert window.project.all_plot_settings[0].get('annotations', []) == []

    window._try_delete_annotation_near(_FakeMplEvent(ax, 1.0, 2.0))  # 例外なく何もしない


def _seed_annotation(window, axis_index=0, xy=(1.0, 2.0), text="消す注釈"):
    window.project.all_plot_settings[axis_index]['annotations'] = [{
        'id': 'test-id', 'type': 'text', 'text': text,
        'xy': xy, 'xytext': xy, 'color': '#000000',
    }]


def test_delete_annotation_near_confirmed_removes_it_via_undoable_command(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ax = window.all_axes[0]
    _seed_annotation(window, xy=(1.0, 2.0))
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    window._try_delete_annotation_near(_FakeMplEvent(ax, 1.0, 2.0))

    assert window.project.all_plot_settings[0]['annotations'] == []
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert len(window.project.all_plot_settings[0]['annotations']) == 1


def test_delete_annotation_near_declined_keeps_it(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ax = window.all_axes[0]
    _seed_annotation(window, xy=(1.0, 2.0))
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))

    window._try_delete_annotation_near(_FakeMplEvent(ax, 1.0, 2.0))

    assert len(window.project.all_plot_settings[0]['annotations']) == 1


def test_delete_annotation_near_too_far_is_ignored(tmp_path, monkeypatch):
    """クリック位置が許容ピクセル距離より遠い場合は削除しない"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ax = window.all_axes[0]
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    _seed_annotation(window, xy=(1.0, 1.0))
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    window._try_delete_annotation_near(_FakeMplEvent(ax, 99.0, 99.0))  # 遠く離れた位置

    assert len(window.project.all_plot_settings[0]['annotations']) == 1


def test_delete_annotation_near_skips_region_highlight_entries_without_crashing(tmp_path, monkeypatch):
    """
    回帰テスト(項目C-701で作り込んだバグ): 領域ハイライト(vspan/hspan、
    'xy'/'xytext'キーを持たない)が同じannotationsリストに混在していると、
    以前は ax.transData.transform(None) がValueErrorでクラッシュしていた。
    領域ハイライトの削除は領域ハイライトモード側の責務のため、注釈モードでの
    右クリックでは黙ってスキップされ、他のテキスト注釈は問題なく削除できること。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ax = window.all_axes[0]
    window.project.all_plot_settings[0]['annotations'] = [
        {'id': 'region-id', 'type': 'vspan', 'range': (1.0, 3.0), 'color': '#F2A72B', 'alpha': 0.18},
        {'id': 'text-id', 'type': 'text', 'text': '消す注釈', 'xy': (1.0, 2.0), 'xytext': (1.0, 2.0),
         'color': '#000000'},
    ]
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    window._try_delete_annotation_near(_FakeMplEvent(ax, 1.0, 2.0))  # 例外にならない

    remaining = window.project.all_plot_settings[0]['annotations']
    assert len(remaining) == 1
    assert remaining[0]['type'] == 'vspan'  # テキスト注釈だけ削除され、領域ハイライトは残る


def _seed_stat_annotation(window, axis_index=0, xy=(0.05, 0.95), dataset_id='ds-id', stat='mean'):
    window.project.all_plot_settings[axis_index]['annotations'] = [{
        'id': 'stat-id', 'type': 'stat', 'dataset_id': dataset_id, 'stat': stat,
        'xy': xy, 'color': '#000000',
    }]


def test_delete_annotation_near_matches_stat_label_via_axes_transform(tmp_path, monkeypatch):
    """統計値アンカーラベル(項目C-708)はAxes相対座標を持つため、クリック位置との
    距離判定にtransAxes(transDataではなく)を使うこと。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ax = window.all_axes[0]
    # xlim/ylimをAxes相対座標(0〜1)とは異なる範囲にしておく: transData(データ座標)
    # とtransAxes(Axes相対座標)を取り違えていたら、この設定ではヒットしなくなる。
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    _seed_stat_annotation(window, xy=(0.05, 0.95))
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    window._try_delete_annotation_near(_FakeMplEvent(ax, 5.0, 95.0))  # Axes相対(0.05, 0.95)相当のデータ座標

    assert window.project.all_plot_settings[0]['annotations'] == []


def test_delete_annotation_near_stat_label_confirmation_message(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ax = window.all_axes[0]
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    _seed_stat_annotation(window, xy=(0.05, 0.95))
    calls = []
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: calls.append(a) or QMessageBox.StandardButton.No),
    )

    window._try_delete_annotation_near(_FakeMplEvent(ax, 5.0, 95.0))

    assert len(calls) == 1
    assert "統計値アンカーラベル" in calls[0][2]


def test_right_click_press_deletes_nearest_annotation_end_to_end(tmp_path, monkeypatch):
    """_on_annotation_pressから右クリック経由で削除まで通しで動くことを確認する統合テスト"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.annotation_mode_enabled = True
    ax = window.all_axes[0]
    _seed_annotation(window, xy=(1.0, 2.0))
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    window._on_annotation_press(_FakeMplEvent(ax, 1.0, 2.0, button=3))

    assert window.project.all_plot_settings[0]['annotations'] == []
    assert window._annotation_drag_start is None
