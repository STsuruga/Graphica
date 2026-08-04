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
from PySide6.QtWidgets import QApplication, QInputDialog

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
