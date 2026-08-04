# tests/test_canvas_detach.py
"""
項目86「マルチモニター対応(Canvasの別ウィンドウ切り離し)」のテスト。

self.canvas (MplCanvas) はsetParent()で再親付けされるだけで、破棄・再生成は
一切行わない設計になっている。このテストでは:
  - 「切り離す」操作でself.canvasが独立したトップレベルウィンドウへ移動し、
    plot_containerのレイアウトから外れること
  - 「元に戻す」操作(メニューの再トグル、および切り離しウィンドウの
    ×ボタンを閉じた場合の両方)でself.canvasが元の位置へ正確に戻ること
  - 一連の操作を通してself.canvasのオブジェクト同一性(id())が
    変わらないこと(=第2のインスタンスが作られていないこと)
  - 切り離し状態・ウィンドウジオメトリがQSettingsに永続化され、
    新しいPlotterAppインスタンスへ再起動をまたいで復元されること
を確認する。QSettingsのリダイレクトはtests/test_quick_access_mixin.pyと
同じパターン(settings_pathを共有できるようにしたもの)を用いる。
"""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui.main_window as main_window_module
from gui.main_window import (
    PlotterApp,
    CANVAS_DETACHED_GEOMETRY_KEY,
    CANVAS_WAS_DETACHED_KEY,
)
from gui.detached_canvas_window import DetachedCanvasWindow


def _make_isolated_plotter_app(tmp_path, monkeypatch, settings_path=None):
    """
    QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る
    (tests/test_quick_access_mixin.py と同じパターン)。settings_pathを
    指定すると、複数のPlotterAppインスタンス間で同じ設定ファイルを共有でき、
    再起動をまたいだ永続化のラウンドトリップをテストできる。
    """
    if settings_path is None:
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
    return window, settings_path


def test_canvas_starts_attached_inside_plot_container(tmp_path, monkeypatch):
    """既定(未切り離し)では、従来通りcanvasがplot_containerのレイアウト内にあること"""
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        assert window.canvas_detached is False
        assert window.canvas.parent() is window.ui.plot_container
        assert window._plot_layout.indexOf(window.canvas) != -1
    finally:
        window.close()


def test_detach_reparents_canvas_to_new_top_level_window(tmp_path, monkeypatch):
    """「切り離す」操作で、canvasが独立したトップレベルウィンドウへ再親付けされ、plot_containerのレイアウトから外れること"""
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        canvas_id_before = id(window.canvas)

        window.canvas_detach_action.setChecked(True)

        assert window.canvas_detached is True
        assert window._canvas_detach_window is not None
        assert isinstance(window._canvas_detach_window, DetachedCanvasWindow)
        assert window._canvas_detach_window.isWindow()  # 独立したトップレベルウィンドウであること

        # 同じオブジェクトが再親付けされただけで、第2のインスタンスは作られていない
        assert id(window.canvas) == canvas_id_before
        assert window.canvas.parent() is window._canvas_detach_window

        # plot_containerのレイアウトからは外れている
        assert window._plot_layout.indexOf(window.canvas) == -1
    finally:
        window.close()


def test_reattach_restores_canvas_to_original_position(tmp_path, monkeypatch):
    """「元に戻す」操作(切り離しトグルの解除)で、canvasが元のレイアウト位置へ正確に戻ること"""
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        canvas_id_before = id(window.canvas)
        original_index = window._canvas_layout_index

        window.canvas_detach_action.setChecked(True)
        assert window.canvas_detached is True

        window.canvas_detach_action.setChecked(False)

        assert window.canvas_detached is False
        assert window._canvas_detach_window is None
        assert id(window.canvas) == canvas_id_before
        assert window.canvas.parent() is window.ui.plot_container
        assert window._plot_layout.indexOf(window.canvas) == original_index
    finally:
        window.close()


def test_closing_detached_window_via_close_event_triggers_reattach(tmp_path, monkeypatch):
    """
    切り離しウィンドウをOSの×ボタンで閉じた場合(closeEvent経由)も、
    メニューから「元に戻す」を選んだ場合と同じ再アタッチ処理が行われること。
    """
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        canvas_id_before = id(window.canvas)
        window.canvas_detach_action.setChecked(True)
        detach_window = window._canvas_detach_window
        assert detach_window is not None

        # OSの×ボタンが押されたことをシミュレートする
        detach_window.close()

        assert window.canvas_detached is False
        assert window._canvas_detach_window is None
        assert id(window.canvas) == canvas_id_before
        assert window.canvas.parent() is window.ui.plot_container
        assert window._plot_layout.indexOf(window.canvas) == window._canvas_layout_index
        # メニューのチェック状態も追従していること
        assert window.canvas_detach_action.isChecked() is False
    finally:
        window.close()


def test_detached_state_persists_to_qsettings(tmp_path, monkeypatch):
    """切り離し状態・ウィンドウジオメトリがQSettingsへ書き込まれること"""
    window, settings_path = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        window.canvas_detach_action.setChecked(True)
        window._canvas_detach_window.resize(640, 480)

        raw_settings = QSettings(settings_path, QSettings.Format.IniFormat)
        assert raw_settings.value(CANVAS_WAS_DETACHED_KEY, False, type=bool) is True
    finally:
        window.close()

    # closeEvent側でも(「元に戻す」を経由しない終了パスとして)ジオメトリ・
    # 状態が保存されていること
    raw_settings_after_close = QSettings(settings_path, QSettings.Format.IniFormat)
    assert raw_settings_after_close.value(CANVAS_WAS_DETACHED_KEY, False, type=bool) is True
    assert raw_settings_after_close.value(CANVAS_DETACHED_GEOMETRY_KEY) is not None


def test_detached_state_restores_into_a_fresh_plotter_app_instance(tmp_path, monkeypatch):
    """
    1つ目のPlotterAppで切り離した状態のまま終了した場合、同じQSettingsを見る
    2つ目の(新規に作られた)PlotterAppインスタンスが、起動時に自動的に
    切り離された状態で復元されること(#83のミニマップ表示設定などと同じ
    QSettings往復パターン)。
    """
    settings_path = str(tmp_path / "shared_settings.ini")
    window1, _ = _make_isolated_plotter_app(tmp_path, monkeypatch, settings_path=settings_path)
    window1.canvas_detach_action.setChecked(True)
    window1._canvas_detach_window.resize(720, 540)
    window1.close()

    window2, _ = _make_isolated_plotter_app(tmp_path, monkeypatch, settings_path=settings_path)
    try:
        app = QApplication.instance()
        # 起動時の復元はQTimer.singleShot(0, ...)経由の遅延処理のため、
        # イベントループを追加で回してから確認する。
        for _ in range(10):
            app.processEvents()

        assert window2.canvas_detached is True
        assert window2._canvas_detach_window is not None
        assert window2.canvas.parent() is window2._canvas_detach_window
        assert window2.canvas_detach_action.isChecked() is True
    finally:
        window2.close()


def test_default_launch_without_prior_detach_stays_attached(tmp_path, monkeypatch):
    """
    QSettingsに切り離し履歴が全く無い(既存ユーザー/初回起動)場合、
    従来通り常にアタッチされた状態で起動すること。
    """
    window, _ = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        app = QApplication.instance()
        for _ in range(10):
            app.processEvents()

        assert window.canvas_detached is False
        assert window._canvas_detach_window is None
        assert window.canvas.parent() is window.ui.plot_container
    finally:
        window.close()
