# tests/test_minimap_widget.py
"""
項目83「レンジスライダー(ミニマップ)」に対するテスト。

- MinimapWidget単体: データセットの概観描画・SpanSelector選択時のシグナル発火
- PlotterAppへの組み込み: plot_containerのレイアウトへの追加、選択範囲が
  全サブプロットのX軸ズームに反映されること、表示/非表示のQSettings永続化
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from gui.minimap_widget import MinimapWidget, DARK_AXES_FACECOLOR, LIGHT_AXES_FACECOLOR
from core.dataset import Dataset


def _make_dataset(name, n_points=5):
    df = pd.DataFrame({"x": range(n_points), "y": [v * v for v in range(n_points)]})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y")


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る
    (tests/test_main_window.py の同名ヘルパーと同じパターン)"""
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


# --- MinimapWidget単体 ---

@pytest.fixture
def minimap():
    m = MinimapWidget()
    yield m
    plt.close(m.fig)


def test_minimap_refresh_draws_one_line_per_dataset(minimap):
    """refresh() は各データセットにつき1本の折れ線を追加する
    (SpanSelectorのinteractiveハンドルも内部的にax.linesへ追加されるため、
    データセット追加前後の"差分"で数える)。"""
    minimap.refresh([], dark_mode=False)
    baseline = len(minimap.ax.lines)

    datasets = [_make_dataset("a"), _make_dataset("b")]
    minimap.refresh(datasets, dark_mode=False)

    assert len(minimap.ax.lines) - baseline == len(datasets)


def test_minimap_refresh_applies_dark_theme_colors(minimap):
    minimap.refresh([_make_dataset("a")], dark_mode=True)
    assert minimap.ax.get_facecolor() == pytest.approx(
        matplotlib.colors.to_rgba(DARK_AXES_FACECOLOR)
    )


def test_minimap_refresh_applies_light_theme_colors(minimap):
    minimap.refresh([_make_dataset("a")], dark_mode=False)
    assert minimap.ax.get_facecolor() == pytest.approx(
        matplotlib.colors.to_rgba(LIGHT_AXES_FACECOLOR)
    )


def test_minimap_refresh_does_not_leak_span_selector_event_connections(minimap):
    """
    回帰テスト: refresh() のたびに _create_span_selector() が新しい
    SpanSelector を作るが、古い方の canvas イベント接続(press/motion/
    release)を切断していなかったため、データセット追加やプロット設定変更の
    たびに毎回リークし、1回のドラッグ操作で range_selected がリーク数だけ
    重複発火するようになっていた。複数回 refresh() してもイベント接続数が
    増え続けないことを確認する。
    """
    minimap.refresh([_make_dataset("a")], dark_mode=False)
    counts_after_first = {
        event: len(callbacks)
        for event, callbacks in minimap.callbacks.callbacks.items()
    }

    for _ in range(4):
        minimap.refresh([_make_dataset("a")], dark_mode=False)

    counts_after_many = {
        event: len(callbacks)
        for event, callbacks in minimap.callbacks.callbacks.items()
    }

    assert counts_after_many == counts_after_first


def test_minimap_span_selection_emits_range_selected_signal(minimap):
    minimap.refresh([_make_dataset("a")], dark_mode=False)

    received = []
    minimap.range_selected.connect(lambda xmin, xmax: received.append((xmin, xmax)))

    minimap._on_select(1.5, 3.5)

    assert received == [(1.5, 3.5)]


def test_minimap_span_selection_ignores_zero_width_click(minimap):
    """ドラッグせず単にクリックしただけ(xmin==xmax)の場合は範囲選択とみなさない"""
    received = []
    minimap.range_selected.connect(lambda xmin, xmax: received.append((xmin, xmax)))

    minimap._on_select(2.0, 2.0)

    assert received == []


# --- PlotterAppへの組み込み ---

def test_minimap_widget_created_and_added_to_plot_container(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    assert isinstance(window.minimap, MinimapWidget)
    layout = window.ui.plot_container.layout()
    assert layout.indexOf(window.minimap) >= 0
    assert layout.indexOf(window.minimap_separator) >= 0


def test_minimap_range_selection_updates_all_subplot_xlims(tmp_path, monkeypatch):
    """ミニマップでのドラッグ選択が、全サブプロットのX軸ズーム範囲に一括反映されること"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_rows_spinbox.setValue(1)
    window.subplot_cols_spinbox.setValue(2)

    ds1 = _make_dataset("a")
    ds1.subplot_target = 0
    ds2 = _make_dataset("b")
    ds2.subplot_target = 1
    window.project.datasets.extend([ds1, ds2])
    window._update_plot()

    assert len(window.canvas.all_axes) == 2

    window._on_minimap_range_selected(1.0, 3.0)

    for ax in window.canvas.all_axes:
        assert ax.get_xlim() == pytest.approx((1.0, 3.0))


def test_minimap_range_selection_does_not_trigger_full_redraw(tmp_path, monkeypatch):
    """set_xlim + draw_idle()のみで済ませ、fig.clf()を伴うredraw_all()は呼ばないこと
    (呼ぶとAxesが作り直されて同一性が変わってしまう)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = _make_dataset("a")
    window.project.datasets.append(ds)
    window._update_plot()

    ax_before = window.canvas.all_axes[0]
    window._on_minimap_range_selected(1.0, 3.0)
    ax_after = window.canvas.all_axes[0]

    assert ax_before is ax_after


def test_minimap_toggle_updates_visibility(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    window.minimap_action.setChecked(False)
    assert window.minimap.isVisible() is False
    assert window.minimap_separator.isVisible() is False

    window.minimap_action.setChecked(True)
    assert window.minimap.isVisible() is True
    assert window.minimap_separator.isVisible() is True


def test_minimap_visibility_persists_and_restores_via_qsettings(tmp_path, monkeypatch):
    """表示メニューでの表示/非表示切り替えが、QSettingsの "minimap_visible" キー
    経由で次回起動時のPlotterAppにも復元されること
    (tests/test_main_window.py の snap_to_grid 永続化テストと同じパターン)。"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)

    window1 = PlotterApp(run_startup_checks=False, tab_id=2)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    assert window1.minimap_visible is True  # 既定はON

    window1.minimap_action.setChecked(False)
    assert window1.minimap_visible is False

    window2 = PlotterApp(run_startup_checks=False, tab_id=3)
    for _ in range(5):
        app.processEvents()

    assert window2.minimap_visible is False
    assert window2.minimap_action.isChecked() is False
    assert window2.minimap.isVisible() is False


# --- ミニマップの配色をアプリ全体のテーマと揃える(実機フィードバック:
#     「ミニマップの灰色も他の所の背景と色のテイストをそろえて、同じ色には
#     しないで少しだけ暗い色にして」) ---

def test_minimap_axes_facecolor_is_not_a_flat_neutral_gray():
    """
    以前の#f2f2f2(ライト)/#1e1e1e(ダーク)は R=G=B の無彩色グレーで、
    gui/theme.pyの寒色寄りトークン(R<G<Bの傾向)と色味が揃っていなかった。
    """
    from gui.theme import LIGHT_TOKENS, DARK_TOKENS
    from PySide6.QtGui import QColor

    for hex_color in (LIGHT_AXES_FACECOLOR, DARK_AXES_FACECOLOR):
        color = QColor(hex_color)
        assert color.isValid()
        # 無彩色(R=G=B)ではなく、bg/surface_2トークンと同じ寒色寄りの傾向
        # (R <= G <= B)を持つことを確認する。
        assert not (color.red() == color.green() == color.blue())
        assert color.red() <= color.green() <= color.blue()


def test_minimap_axes_facecolor_is_darker_than_nearest_theme_surface():
    """
    「他の所の背景と同じ色にはしないで少しだけ暗い色に」の回帰テスト。
    ライトはsurface_2(#EEF0F3)より、ダークはbg(#14171A)より暗いことを確認する。
    """
    from gui.theme import LIGHT_TOKENS, DARK_TOKENS
    from PySide6.QtGui import QColor

    def luminance(hex_color):
        c = QColor(hex_color)
        return c.red() + c.green() + c.blue()

    assert luminance(LIGHT_AXES_FACECOLOR) < luminance(LIGHT_TOKENS["surface_2"])
    assert luminance(DARK_AXES_FACECOLOR) < luminance(DARK_TOKENS["bg"])
