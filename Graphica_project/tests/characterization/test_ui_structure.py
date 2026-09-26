"""画面の組み立て結果を固定する: 起動直後のウィンドウ、プロパティ欄の状態ごとの見え方、ダイアログの初期状態。"""
import hashlib

import numpy as np
import pandas as pd
import pytest
from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import QApplication, QDockWidget, QToolBar

import recorder
from scenario import pump


def _theme_state(normalizer):
    app = QApplication.instance()
    palette = app.palette()
    roles = ("Window", "WindowText", "Base", "AlternateBase", "Text", "Button", "ButtonText", "Highlight",
             "HighlightedText", "ToolTipBase", "ToolTipText", "PlaceholderText", "Link")
    return {
        "style": app.style().name(),
        "stylesheet_sha256": hashlib.sha256(normalizer.text(app.styleSheet()).encode("utf-8")).hexdigest(),
        "palette": {role: palette.color(getattr(QPalette.ColorRole, role)).name(QColor.NameFormat.HexArgb)
                    for role in roles},
    }


def _toolbars(window):
    bars = []
    for bar in window.findChildren(QToolBar):
        actions = []
        for action in bar.actions():
            if action.isSeparator():
                actions.append({"separator": True})
                continue
            entry = {"text": action.text(), "tooltip": action.toolTip(), "enabled": action.isEnabled(),
                     "visible": action.isVisible()}
            if action.isCheckable():
                entry["checked"] = action.isChecked()
            if action.shortcut().toString():
                entry["shortcut"] = action.shortcut().toString()
            actions.append(entry)
        bars.append({"name": bar.objectName(), "title": bar.windowTitle(), "visible": not bar.isHidden(),
                     "area": window.toolBarArea(bar).name if bar.parent() is window else None,
                     "actions": actions})
    return bars


def _docks(window):
    docks = []
    for dock in window.findChildren(QDockWidget):
        if dock.parent() is not window:
            continue
        docks.append({
            "name": dock.objectName(),
            "title": dock.windowTitle(),
            "area": window.dockWidgetArea(dock).name,
            "floating": dock.isFloating(),
            "visible": not dock.isHidden(),
            "features": dock.features().name if hasattr(dock.features(), "name") else str(dock.features()),
            "tabified_with": [d.objectName() for d in window.tabifiedDockWidgets(dock)],
        })
    return docks


def _menus(window):
    return [{"title": action.text(), "items": recorder.menu_tree(action.menu(), signals=True)}
            for action in window.menuBar().actions() if action.menu() is not None]


def _window_snapshot(main, modal_log, normalizer):
    tab = main.tab_widget.widget(0)
    return {
        "modals": modal_log.take(),
        "title": main.windowTitle(),
        "tabs": [main.tab_widget.tabText(i) for i in range(main.tab_widget.count())],
        "theme": _theme_state(normalizer),
        "main_docks": _docks(main),
        "tab_docks": _docks(tab),
        "toolbars": _toolbars(tab),
        "menus": _menus(tab),
        "tree": recorder.widget_tree(main, signals=True),
    }


@pytest.mark.parametrize("language,dark", [("ja", False), ("ja", True), ("en", False), ("en", True)],
                         ids=["ja-light", "ja-dark", "en-light", "en-dark"])
def test_startup_window(app_env, modal_log, normalizer, language, dark):
    main = app_env.main_window(language=language, dark=dark)
    recorder.check(f"ui/startup_{language}_{'dark' if dark else 'light'}", _window_snapshot(main, modal_log, normalizer),
                   normalizer)


def test_startup_window_without_plugins(app_env, modal_log, normalizer):
    main = app_env.main_window(example_plugin=False)
    snapshot = _window_snapshot(main, modal_log, normalizer)
    recorder.check("ui/startup_ja_light_no_plugins", {k: snapshot[k] for k in ("modals", "menus", "tab_docks")},
                   normalizer)


def test_second_startup_does_not_show_the_welcome_again(app_env, modal_log, normalizer):
    app_env.main_window()
    first = modal_log.take()
    app_env.main_window()
    recorder.check("ui/startup_modals_first_and_second", {"first": first, "second": modal_log.take()}, normalizer)


# --- プロパティ欄: 状態ごとの見え方 ---

def _line_dataset(name="ds"):
    from graphica.core.dataset import Dataset

    df = pd.DataFrame({"x": np.arange(10.0), "y": np.arange(10.0) ** 2, "z": np.arange(10.0)})
    return Dataset(df=df, name=name, x_col_name="x", y_col_name="y")


def _grid_dataset():
    from graphica.core.dataset import Dataset

    xs, ys = np.meshgrid(np.arange(4.0), np.arange(3.0))
    df = pd.DataFrame({"x": xs.ravel(), "y": ys.ravel(), "z": (xs * ys).ravel()})
    return Dataset(df=df, name="map", x_col_name="x", y_col_name="y", z_col_name="z", data_kind="2d_grid")


def _property_snapshot(tab):
    sections = {}
    for key, entry in tab._prop_sections.items():
        sections[key] = {
            "header_visible": not entry["section"].isHidden(),
            "expanded": entry["toggle"].isChecked(),
            "body_enabled": entry["body"].isEnabled(),
        }
    return {"sections": sections, "tree": recorder.widget_tree(tab.ui.properties_groupbox, signals=True)}


def _state_empty(tab):
    pass


def _state_1d(tab):
    tab._add_dataset(_line_dataset())


def _state_2d(tab):
    tab._add_dataset(_grid_dataset())


def _state_waterfall(tab):
    tab._add_dataset(_line_dataset("a"))
    tab._add_dataset(_line_dataset("b"))
    tab.waterfall_checkbox.setChecked(True)


def _state_gradient(tab):
    tab._add_dataset(_line_dataset())
    tab.ui.plot_type_combo.setCurrentText("Line")
    tab.gradient_checkbox.setChecked(True)


PROPERTY_STATES = {
    "empty": _state_empty,
    "1d": _state_1d,
    "2d": _state_2d,
    "waterfall": _state_waterfall,
    "gradient": _state_gradient,
}


@pytest.mark.parametrize("state", list(PROPERTY_STATES))
def test_property_panel_state(app_env, modal_log, normalizer, state):
    tab = app_env.tab()
    PROPERTY_STATES[state](tab)
    pump()
    snapshot = _property_snapshot(tab)
    snapshot["modals"] = modal_log.take()
    recorder.check(f"ui/property_panel_{state}", snapshot, normalizer)


# --- ダイアログの初期状態 ---

def _dialog_factories(tmp_path):
    from PySide6.QtCore import QSettings

    import graphica.gui.dialogs as d

    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0], "label": ["a", "b", "c"]})
    columns = list(df.columns)
    image = QImage(30, 20, QImage.Format.Format_ARGB32)
    image.fill(QColor("#c83c3c"))

    def actions():
        return []

    return {
        "AboutDialog": lambda: d.AboutDialog(),
        "ArrowAnnotationDialog": lambda: d.ArrowAnnotationDialog(),
        "AutosaveHistoryDialog": lambda: d.AutosaveHistoryDialog([]),
        "BaselineCorrectionDialog": lambda: d.BaselineCorrectionDialog("ds", 0.0, 10.0),
        "BatchExportDialog": lambda: d.BatchExportDialog(2),
        "CVDSimulationDialog": lambda: d.CVDSimulationDialog(image),
        "CalcHelpDialog": lambda: d.CalcHelpDialog(),
        "CaptionGeneratorDialog": lambda: d.CaptionGeneratorDialog("caption", "fig:1"),
        "ColorPaletteDialog": lambda: d.ColorPaletteDialog({"p": ["#ff0000", "#00ff00"]}, "p"),
        "ColumnCalculatorDialog": lambda: d.ColumnCalculatorDialog(columns),
        "ColumnPreviewDialog": lambda: d.ColumnPreviewDialog(df, "data.csv"),
        "ColumnStringOpsDialog": lambda: d.ColumnStringOpsDialog(columns),
        "ColumnTypeDialog": lambda: d.ColumnTypeDialog(df),
        "ColumnVisibilityDialog": lambda: d.ColumnVisibilityDialog(columns, ["label"]),
        "CommandPaletteDialog": lambda: d.CommandPaletteDialog(actions),
        "CumulativeIntegralDialog": lambda: d.CumulativeIntegralDialog("ds"),
        "DatasetArithmeticDialog": lambda: d.DatasetArithmeticDialog("a", "b"),
        "DuplicateXDialog": lambda: d.DuplicateXDialog("ds", 3),
        "ExcelMultiSheetDialog": lambda: d.ExcelMultiSheetDialog(["Sheet1", "Sheet2"]),
        "ExportDialog": lambda: d.ExportDialog(),
        "FindReplaceDialog": lambda: d.FindReplaceDialog(columns),
        "FitDialog": lambda: d.FitDialog(x_min=0.0, x_max=10.0),
        "FolderImportDialog": lambda: d.FolderImportDialog(str(tmp_path), ["a.csv", "b.txt"]),
        "HelpDialog": lambda: d.HelpDialog(),
        "HistogramKDEDialog": lambda: d.HistogramKDEDialog("ds", columns, "y"),
        "InsetDialog": lambda: d.InsetDialog(0.0, 10.0, 2.0, 4.0),
        "IntervalIntegralDialog": lambda: d.IntervalIntegralDialog("ds", 0.0, 10.0),
        "LabelEditDialog": lambda: d.LabelEditDialog("x ($\\mu$m)", "X軸ラベル", [("α", r"\alpha"), ("β", r"\beta")]),
        "LegendOrderDialog": lambda: d.LegendOrderDialog(["a", "b", "c"]),
        "MultiPeakFitDialog": lambda: d.MultiPeakFitDialog(x_data=np.arange(5.0), y_data=np.arange(5.0)),
        "NamedColorManagerDialog": lambda: d.NamedColorManagerDialog(QSettings("Graphica", "Graphica")),
        "NamedColorPickerDialog": lambda: d.NamedColorPickerDialog(QSettings("Graphica", "Graphica")),
        "NewDatasetDialog": lambda: d.NewDatasetDialog(),
        "NormalizeDatasetDialog": lambda: d.NormalizeDatasetDialog("ds", 0.0, 10.0),
        "OutlierDetectionDialog": lambda: d.OutlierDetectionDialog("ds"),
        "PeakSettingsDialog": lambda: d.PeakSettingsDialog(),
        "PluginParamDialog": lambda: d.PluginParamDialog(
            "設定", [{"name": "n", "type": "int", "default": 3, "label": "回数"},
                     {"name": "k", "type": "choice", "choices": ["a", "b"], "default": "b"},
                     {"name": "f", "type": "bool", "default": True, "label": "有効"}]),
        "PreferencesDialog": lambda: d.PreferencesDialog(False, 5),
        "QuickAccessManagerDialog": lambda: d.QuickAccessManagerDialog(actions, lambda *_: False, lambda *_: None),
        "ReplicateErrorDialog": lambda: d.ReplicateErrorDialog(columns),
        "ResampleDatasetDialog": lambda: d.ResampleDatasetDialog("ds", ["other"], 0.0, 10.0),
        "ResultDialog": lambda: d.ResultDialog("結果", "本文\n2行目"),
        "RowFilterDialog": lambda: d.RowFilterDialog(columns),
        "SavGolDialog": lambda: d.SavGolDialog("ds", 11),
        "ShortcutsDialog": lambda: d.ShortcutsDialog(actions),
        "WelcomeDialog": lambda: d.WelcomeDialog(recent_files=[]),
        "XAxisAlignmentDialog": lambda: d.XAxisAlignmentDialog("a", "b"),
    }


def test_every_dialog_has_a_scenario(tmp_path):
    import graphica.gui.dialogs as d

    assert sorted(_dialog_factories(tmp_path)) == sorted(d.__all__)


@pytest.mark.parametrize("language", ["ja", "en"])
def test_dialog_initial_states(app_env, modal_log, normalizer, tmp_path, language):
    from graphica.core import i18n

    i18n.set_language(language)
    normalizer.add_path(tmp_path, "<CASE>")
    # フィットのダイアログはプロセス全体のプラグインのフィット関数を並べるので、先に流れたテストの登録を持ち込まない
    app_env.use_plugins(example_plugin=False)
    states = {}
    for name, factory in _dialog_factories(tmp_path).items():
        try:
            dialog = factory()
        except Exception as error:  # 今の挙動として、組み立てで落ちること自体を記録する
            states[name] = {"error": f"{type(error).__name__}: {error}"}
            continue
        states[name] = {"tree": recorder.widget_tree(dialog), "modals": modal_log.take()}
        dialog.deleteLater()
    recorder.check(f"ui/dialogs_{language}", states, normalizer)
