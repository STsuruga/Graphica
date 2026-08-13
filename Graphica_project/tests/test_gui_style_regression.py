# tests/test_gui_style_regression.py
"""
H-5: 画像回帰テスト。

docs/Graphica_ROADMAP_PLUGIN_AND_GUI.md のH-5節に基づく。pytest-mplは新規依存を
増やすため採用せず、既存のH-2各フェーズで使ってきた「QWidget.grab() -> QPixmap」
パターンをそのまま流用し、ベースラインPNG(tests/baseline_images/)とのピクセル差分を
許容閾値付きで比較する自前の仕組みにする(ロードマップの「pytest-mplまたは類似の
仕組み」という表現の範囲内)。

対象は、ロードマップが名指しする3画面(メインウィンドウ、環境設定ダイアログ、
エクスポートプレビュー)のライト/ダーク各モード、計6ベースライン。

【許容差分について】
同一環境(同一Qt/matplotlibバージョン、同一OS)での再実行は本来ピクセル完全一致に
なるはずだが、matplotlibのフォントレンダリング(フォントヒンティング等)が将来の
バージョン更新でわずかに変わる可能性を見込み、ロードマップの「CIで差分が閾値を
超えたら警告」という考え方に合わせて、小さな許容差分(1ピクセルあたりのチャンネル差と、
全体に対する差分ピクセル比率)を設けている。閾値を超えた場合は、意図した見た目の
変更かどうかをまず確認し、意図した変更であれば tests/baseline_images/ 配下の該当
PNGを新しい見た目で差し替えること。

【ベースライン画像が無い場合】
このファイルを新規追加した時点でベースラインPNGが存在しない場合は、比較の代わりに
その場でベースラインとして保存しテストをスキップする(2回目の実行から実際の比較が
行われる)。意図的にベースラインを更新したい場合は、対象のPNGを削除してから
再実行すればよい。
"""
import sys

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from pathlib import Path

import gui.main_window as main_window_module
from gui.main_window import PlotterApp
from gui.dialogs import PreferencesDialog
from core.dataset import Dataset

BASELINE_DIR = Path(__file__).parent / "baseline_images"

# tests/baseline_images/ 配下のPNGはWindows上で生成したもので、フォント
# ヒンティング/サブピクセルレンダリングがOSごとに異なるため、他OSではピクセル
# 差分が MAX_DIFF_RATIO を超えて誤検出する(macOS版CI追加時に実際に6件とも
# 失敗することを確認済み)。プラットフォームごとに別ベースラインを持つ運用は
# まだ導入していないため、当面はWindows以外をスキップする。
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="baseline_images/のPNGはWindows専用のため、他OSでは比較しない",
)

# 全体に対する差分ピクセル比率の許容上限(この比率を超えたら回帰とみなす)
MAX_DIFF_RATIO = 0.02
# 1ピクセルあたり、この値を超えるチャンネル差(0-255)があって初めて「差分ピクセル」と数える
# (アンチエイリアシングやフォントヒンティングの1階調程度の揺れを無視するため)
PIXEL_CHANNEL_TOLERANCE = 24

WINDOW_SIZE = (1200, 750)


def _make_dataset(name, n_points=8):
    x = np.linspace(0, 10, n_points)
    y = np.sin(x) * (n_points - np.arange(n_points))
    df = pd.DataFrame({"x": x, "y": y})
    return Dataset(name=name, df=df, x_col_name="x", y_col_name="y")


def _make_isolated_plotter_app(tmp_path, monkeypatch):
    """QSettingsを一時ファイルにリダイレクトした状態でPlotterAppを1つ作る
    (tests/test_main_window.py・tests/test_minimap_widget.py の同名ヘルパーと同じパターン)。"""
    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(*WINDOW_SIZE)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


def _populate_sample_plot(window):
    """代表的な見た目(データ1系列+凡例+軸ラベル)を持たせる。空のグラフだと
    見た目の回帰(配色・グリッド・凡例の有無等)を検出しにくいため。"""
    ds = _make_dataset("sample")
    window.project.datasets.append(ds)
    window._update_plot()
    window._rebuild_dataset_tree_widget()


def _set_dark_mode(window, dark: bool):
    window.dark_mode_action.setChecked(dark)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()


def _qimage_to_array(qimage: QImage) -> np.ndarray:
    qimage = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = qimage.width(), qimage.height()
    # PySide6のQImage.constBits()は、行間にパディングが無ければwidth*height*4バイトの
    # 連続バッファを返す。bytesPerLine()がwidth*4と一致することを前提にできない環境の
    # ために、行ごとにコピーして詰め直す。
    bytes_per_line = qimage.bytesPerLine()
    buf = bytes(qimage.constBits())
    arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, bytes_per_line))
    arr = arr[:, : width * 4].reshape((height, width, 4))
    return arr.copy()


def _assert_matches_baseline(widget, baseline_name):
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    pixmap = widget.grab()
    assert not pixmap.isNull(), f"{baseline_name}: grab()が空のQPixmapを返した(サイズ0の可能性)"
    image = pixmap.toImage()
    actual = _qimage_to_array(image)

    baseline_path = BASELINE_DIR / f"{baseline_name}.png"
    if not baseline_path.exists():
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        image.save(str(baseline_path))
        pytest.skip(f"ベースライン画像が無かったため新規作成した: {baseline_path.name}")

    baseline_image = QImage(str(baseline_path))
    assert not baseline_image.isNull(), f"{baseline_name}: ベースライン画像の読み込みに失敗した"
    baseline = _qimage_to_array(baseline_image)

    if baseline.shape != actual.shape:
        pytest.fail(
            f"{baseline_name}: サイズがベースラインと異なる "
            f"(baseline={baseline.shape[1]}x{baseline.shape[0]}, "
            f"actual={actual.shape[1]}x{actual.shape[0]})。"
            f"ウィンドウ/ダイアログのサイズが変わった可能性がある。"
        )

    diff = np.abs(actual.astype(np.int16) - baseline.astype(np.int16))
    differing_pixels = np.any(diff > PIXEL_CHANNEL_TOLERANCE, axis=-1)
    diff_ratio = float(differing_pixels.mean())

    assert diff_ratio <= MAX_DIFF_RATIO, (
        f"{baseline_name}: 見た目がベースラインから{diff_ratio:.2%}変化した"
        f"(許容閾値{MAX_DIFF_RATIO:.0%})。意図した見た目の変更であれば "
        f"tests/baseline_images/{baseline_name}.png を最新の見た目で差し替えること。"
    )


# --- メインウィンドウ ---

def test_main_window_light_matches_baseline(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _populate_sample_plot(window)
    _assert_matches_baseline(window, "main_window_light")


def test_main_window_dark_matches_baseline(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _populate_sample_plot(window)
    _set_dark_mode(window, True)
    _assert_matches_baseline(window, "main_window_dark")


# --- 環境設定ダイアログ ---

def test_preferences_dialog_light_matches_baseline(tmp_path, monkeypatch):
    from gui import theme

    # ★ gui.theme._current_tokens はプロセス全体で共有されるグローバル状態のため、
    #   フルスイート実行時に実行順序次第で別のテストがダークのまま残している
    #   ことがある(docs/CURRENT_STATE.mdの既知の注意点と同根)。ダイアログ自体は
    #   PreferencesDialogの引数(dark_mode=False)ではなく、その時点でQApplicationに
    #   適用済みのQSS/パレットをそのまま継承するだけなので、明示的にライトへ
    #   戻してから開く。
    theme.apply_theme(QApplication.instance(), dark=False)
    dlg = PreferencesDialog(dark_mode=False, autosave_minutes=5)
    dlg.resize(640, 560)
    dlg.show()
    _assert_matches_baseline(dlg, "preferences_dialog_light")


def test_preferences_dialog_dark_matches_baseline(tmp_path, monkeypatch):
    from gui import theme

    theme.apply_theme(QApplication.instance(), dark=True)
    try:
        dlg = PreferencesDialog(dark_mode=True, autosave_minutes=5)
        dlg.resize(640, 560)
        dlg.show()
        _assert_matches_baseline(dlg, "preferences_dialog_dark")
    finally:
        theme.apply_theme(QApplication.instance(), dark=False)


# --- エクスポートプレビューパネル ---

def test_export_preview_panel_light_matches_baseline(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _populate_sample_plot(window)
    window.export_preview_dock_widget.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    window.export_preview_panel._render_preview()
    _assert_matches_baseline(window.export_preview_panel, "export_preview_light")


def test_export_preview_panel_dark_matches_baseline(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    _populate_sample_plot(window)
    _set_dark_mode(window, True)
    window.export_preview_dock_widget.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    window.export_preview_panel._render_preview()
    _assert_matches_baseline(window.export_preview_panel, "export_preview_dark")
