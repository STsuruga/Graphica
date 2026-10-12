"""GUI 刷新の見本(docs/dev/mockups/gui_redesign/)と並べるためのスクリーンショットを撮る。

決まったサンプルを読み込んだメインウィンドウを、ライト/ダーク(とモード)ごとに PNG に保存する。
設定は一時フォルダの INI に向けるので、利用者の設定(レジストリ)には触れない。

    python scripts/screenshot_ui.py <出力フォルダ> [--theme-color #RRGGBB] [--size 1440x900]

ウィンドウは画面の外に出して撮る(一瞬も見えない)。cwd = Graphica_project/ で実行する。
"""
import argparse
import os
import sys
import tempfile

os.environ.setdefault("GRAPHICA_CONFIRM_UNSAVED_CHANGES", "0")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def _isolate_settings(folder):
    import graphica.gui.app_settings as app_settings
    ini_path = os.path.join(folder, "settings.ini")
    app_settings.QSettings = lambda *args, **kwargs: QSettings(ini_path, QSettings.Format.IniFormat)
    return app_settings


def _silence_modals():
    QDialog.exec = lambda self: 0
    for name in ("information", "warning", "critical"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)


def _sample_datasets():
    """見本と同じ顔ぶれ: 冷却曲線(線)と、少しずらした2本目(点)。"""
    import pandas as pd
    from graphica.core.dataset import Dataset
    from graphica.gui.resources import resource_path

    df = pd.read_csv(resource_path(os.path.join("sample_data", "cooling_curve_sample.csv")))
    x_col, y_col = df.columns[0], df.columns[1]
    first = Dataset(name="cooling_curve", df=df, x_col_name=x_col, y_col_name=y_col)
    shifted = df.copy()
    shifted[y_col] = shifted[y_col] + 3.0
    second = Dataset(name="cooling_curve_2", df=shifted, x_col_name=x_col, y_col_name=y_col, plot_type="Scatter",
                     color="#ff7f0e")
    return [first, second]


def _spectra(seed=1):
    """サイトの画像用の、ノイズの乗った2本のスペクトル(毎回同じ形になるよう乱数は固定)。"""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    wavelength = np.linspace(400.0, 700.0, 300)
    sample_a = np.exp(-((wavelength - 520.0) / 28.0) ** 2) + rng.normal(0, 0.012, wavelength.size)
    sample_b = 0.8 * np.exp(-((wavelength - 580.0) / 40.0) ** 2) + rng.normal(0, 0.012, wavelength.size)
    return pd.DataFrame({"波長 (nm)": wavelength, "試料A": sample_a, "試料B": sample_b})


def _new_scene(window, settle, width, height):
    """前の場面のタブを閉じた新しいタブ(タブの帯にタブが1つだけ写るように)。"""
    tab = window.add_new_project_tab()
    while window.tab_widget.count() > 1:
        window._on_tab_close_requested(0)
    window.set_ui_mode("advanced")
    tab._on_toggle_dark_mode(False)
    window.resize(width, height)
    settle()
    return tab


def _shoot_site_images(window, out_dir, settle):
    """README(docs/images/main_window.png)とサイト(docs/site/images/fit.png・baseline.png)の画像。"""
    import numpy as np
    import pandas as pd
    from graphica.core.analysis import calculate_baseline_als, calculate_curve_fit
    from graphica.core.dataset import Dataset
    from graphica.core.provenance import build_provenance
    from graphica.gui.datasets.operations.fitting import _fit_dataset

    saved = []
    df = _spectra()

    tab = _new_scene(window, settle, 1400, 860)
    first = Dataset(name="試料A", df=df, x_col_name="波長 (nm)", y_col_name="試料A", color="#1f77b4")
    second = Dataset(name="試料B", df=df.copy(), x_col_name="波長 (nm)", y_col_name="試料B", color="#d62728")
    for dataset in (first, second):
        tab._add_dataset(dataset)
    tab.ui.dataset_list_widget.setCurrentItem(tab._get_dataset_tree_item(second))
    tab._update_plot()
    settle()
    saved.append(_save(window, out_dir, "main_window.png"))

    tab = _new_scene(window, settle, 1400, 1080)
    points = df.iloc[::2].reset_index(drop=True)
    source = Dataset(name="試料A", df=points, x_col_name="波長 (nm)", y_col_name="試料A", plot_type="Scatter",
                     marker="o", color="#1f77b4")
    tab._add_dataset(source)
    fit_type = "ガウシアン"
    fit = calculate_curve_fit(source.x_data, source.y_data, fit_type)
    fit_dataset, _text = _fit_dataset(source, fit, fit_type, None, None, None, None, None, None, None,
                                      "linear", "curve_fit")
    tab._add_dataset(fit_dataset)
    tab.ui.dataset_list_widget.setCurrentItem(tab._get_dataset_tree_item(source))
    tab.bottom_panel.show_page("residual")
    tab.center_splitter.setSizes([10000, 300])
    tab._update_plot()
    settle()
    saved.append(_save(window, out_dir, "fit.png"))

    tab = _new_scene(window, settle, 1400, 860)
    rng = np.random.default_rng(7)
    x = np.linspace(0.0, 100.0, 400)
    background = 0.1 + 0.006 * x + 0.12 * np.sin(x / 25.0)
    peaks = 0.8 * np.exp(-((x - 40.0) / 5.0) ** 2) + 0.45 * np.exp(-((x - 56.0) / 7.0) ** 2)
    spectrum = Dataset(name="スペクトル", df=pd.DataFrame({"x": x, "y": background + peaks + rng.normal(0, 0.015, x.size)}),
                       x_col_name="x", y_col_name="y", color="#1f77b4")
    tab._add_dataset(spectrum)
    x_sorted, baseline, corrected = calculate_baseline_als(spectrum.x_data, spectrum.y_data)
    tab._add_dataset(Dataset(name="スペクトル_ベースライン", df=pd.DataFrame({"x": x_sorted, "y": baseline}),
                             x_col_name="x", y_col_name="y", color="#7f7f7f", linestyle="--"))
    corrected_dataset = Dataset(name="スペクトル_補正後", df=pd.DataFrame({"x": x_sorted, "y": corrected}),
                                x_col_name="x", y_col_name="y", color="#d62728",
                                provenance=build_provenance("baseline_als", {"lam": 1e5, "p": 0.01}, [spectrum]))
    tab._add_dataset(corrected_dataset)
    tab.ui.dataset_list_widget.setCurrentItem(tab._get_dataset_tree_item(corrected_dataset))
    tab.bottom_panel.show_page("provenance")
    tab._update_plot()
    settle()
    saved.append(_save(window, out_dir, "baseline.png"))
    return saved


def _save(window, out_dir, name):
    path = os.path.join(out_dir, name)
    window.grab().save(path)
    return path


def _shoot_settings_popover(window, tab, out_dir, settle):
    """⚙ のポップアップ。ポップアップは別の窓なので、それ自体を撮る。"""
    from graphica.gui.shell.settings_popover import toggle_settings_popover
    saved = []
    for dark in (False, True):
        tab._on_toggle_dark_mode(dark)
        for name, color in (("default", "#0F4C5C"), ("yellow", "#FACC15")):
            tab.set_theme_color(color)
            toggle_settings_popover(tab, tab.settings_rail_button)
            settle()
            path = os.path.join(out_dir, f"settings_{name}_{'dark' if dark else 'light'}.png")
            tab.settings_popover.grab().save(path)
            saved.append(path)
            if name == "yellow":
                path = os.path.join(out_dir, f"{'dark' if dark else 'light'}_yellow.png")
                window.grab().save(path)
                saved.append(path)
            tab.settings_popover.hide()
    tab.set_theme_color("#0F4C5C")
    return saved


def _shoot_bottom_panel(window, tab, out_dir, settle):
    """1本目のデータに指数関数でフィットした曲線を足し、元のデータを選んで下のパネルのタブを撮る。"""
    from PySide6.QtCore import QPoint, QRect
    from graphica.core.analysis import calculate_curve_fit
    from graphica.gui.datasets.operations.fitting import _fit_dataset

    source = tab.project.datasets[0]
    fit = calculate_curve_fit(source.x_data, source.y_data, "指数関数")
    fit_dataset, _text = _fit_dataset(source, fit, "指数関数", None, None, None, None, None, None, None,
                                      "linear", "curve_fit")
    tab._add_dataset(fit_dataset)
    tab.ui.dataset_list_widget.setCurrentItem(tab._get_dataset_tree_item(source))
    window.set_ui_mode("advanced")
    tab._update_plot()
    saved = []
    panel = tab.bottom_panel
    for dark in (False, True):
        tab._on_toggle_dark_mode(dark)
        for key in ("table", "fit", "residual", "provenance", "log"):
            panel.show_page(key)
            settle()
            top_left = panel.mapTo(window, QPoint(0, 0))
            rect = QRect(top_left.x(), top_left.y(), panel.width(), panel.height())
            path = os.path.join(out_dir, f"bottom_{key}_{'dark' if dark else 'light'}.png")
            window.grab(rect).save(path)
            saved.append(path)
        path = os.path.join(out_dir, f"{'dark' if dark else 'light'}_advanced_fit.png")
        panel.show_page("table")
        settle()
        window.grab().save(path)
        saved.append(path)
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir")
    parser.add_argument("--theme-color", default=None)
    parser.add_argument("--size", default="1440x900")
    parser.add_argument("--inspector", action="store_true",
                        help="右のインスペクタの各タブも撮る(アドバンスド、インスペクタの所だけ)")
    parser.add_argument("--bottom", action="store_true",
                        help="1本目に指数関数でフィットし、グラフの下のパネルの各タブも撮る(アドバンスド、パネルの所だけ)")
    parser.add_argument("--site", action="store_true",
                        help="README とサイトの画面全体の画像(main_window / fit / baseline.png、アドバンスド・ライト)も撮る")
    parser.add_argument("--settings", action="store_true",
                        help="⚙ のテーマカラーのポップアップも撮る(既定の色と、調整が入る黄色)")
    parser.add_argument("--pages", action="store_true",
                        help="左パネルの各ページ(帯の切り替え先)も撮る(帯と左パネルの所だけ)")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    width, height = (int(v) for v in args.size.lower().split("x"))

    work_dir = tempfile.mkdtemp(prefix="graphica-screenshot-")
    app_settings = _isolate_settings(work_dir)
    _silence_modals()

    app = QApplication(sys.argv)
    from graphica.__main__ import APP_FONT_FAMILIES, APP_FONT_POINT_SIZE
    font = QFont()
    font.setFamilies(APP_FONT_FAMILIES)
    font.setPointSizeF(APP_FONT_POINT_SIZE)
    app.setFont(font)

    settings = app_settings.open_settings()
    app_settings.HAS_SHOWN_WELCOME.write(settings, True)
    app_settings.CLEAN_EXIT.write(settings, True)
    if args.theme_color:
        app_settings.THEME_COLOR.write(settings, args.theme_color)
    settings.sync()

    from graphica.gui.main_app_window import MainAppWindow
    from graphica.gui.theme import disable_scroll_value_change
    disable_scroll_value_change()

    window = MainAppWindow()
    window.resize(width, height)
    window.move(-width - 4000, 0)
    window.show()
    tab = window.tab_widget.currentWidget()
    for dataset in _sample_datasets():
        tab._add_dataset(dataset)
    tab._update_plot()

    def settle():
        for _ in range(30):
            app.processEvents()

    saved = []
    # モードの切り替え(GUI 刷新 PR 3 から)。無い版でも動くように
    modes = ("lite", "advanced") if hasattr(window, "set_ui_mode") else (None,)
    for dark in (False, True):
        tab._on_toggle_dark_mode(dark)
        for mode in modes:
            if mode is not None:
                window.set_ui_mode(mode)
            settle()
            suffix = "" if mode is None else f"_{mode}"
            path = os.path.join(args.out_dir, f"{'dark' if dark else 'light'}{suffix}.png")
            window.grab().save(path)
            saved.append(path)
    if args.pages and hasattr(tab, "activity_rail"):
        from PySide6.QtCore import QPoint, QRect
        for dark in (False, True):
            tab._on_toggle_dark_mode(dark)
            for key in ("datasets", "analysis", "notes", "plugins", "layout"):
                tab.activity_rail.select_page(key)
                settle()
                top_left = tab.activity_rail.mapTo(window, QPoint(0, 0))
                width = tab.activity_rail.width() + tab.left_panel.width()
                rect = QRect(top_left.x(), top_left.y(), width, tab.activity_rail.height())
                path = os.path.join(args.out_dir, f"page_{key}_{'dark' if dark else 'light'}.png")
                window.grab(rect).save(path)
                saved.append(path)
        tab.activity_rail.select_page("datasets")
    if args.inspector and hasattr(tab, "inspector"):
        from PySide6.QtCore import QPoint, QRect
        if hasattr(window, "set_ui_mode"):
            window.set_ui_mode("advanced")
        dock = tab.properties_dock_widget
        for dark in (False, True):
            tab._on_toggle_dark_mode(dark)
            for key in ("properties", "axes", "legend", "export"):
                tab.inspector.show_page(key)
                settle()
                top_left = dock.mapTo(window, QPoint(0, 0))
                rect = QRect(top_left.x(), top_left.y(), dock.width(), dock.height())
                path = os.path.join(args.out_dir, f"inspector_{key}_{'dark' if dark else 'light'}.png")
                window.grab(rect).save(path)
                saved.append(path)
        tab.inspector.show_page("properties")
    if args.site:
        saved += _shoot_site_images(window, args.out_dir, settle)
    if args.settings and hasattr(tab, "settings_rail_button"):
        saved += _shoot_settings_popover(window, tab, args.out_dir, settle)
    if args.bottom and hasattr(tab, "bottom_panel"):
        saved += _shoot_bottom_panel(window, tab, args.out_dir, settle)
    for path in saved:
        print(path, flush=True)
    # 終了処理(自動保存や設定の書き込み)は要らないので、そのまま抜ける
    os._exit(0)


if __name__ == "__main__":
    main()
