"""既定の書式テンプレート(環境設定)。新しいタブの軸に当て、そのタブで読み込んだデータセットにも順に当てる。

当て方は手動の「書式テンプレートを適用」と同じ経路(ProjectIOMixin._apply_plot_template)。
"""
import json

import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog

import graphica.gui.app_settings as app_settings_module
import graphica.gui.data_import_flow as data_import_flow
from graphica.core.dataset import Dataset
from graphica.gui.main_window import PlotterApp

TEMPLATE = {
    'format_version': 1,
    'subplot_styles': [{'grid_visible': True, 'title': 'テンプレートの題'}],
    'dataset_styles': [{'color': '#ff0000', 'linewidth': 3.0}, {'color': '#00aa00', 'linewidth': 0.5}],
}


def _window(tmp_path, monkeypatch, template_path=""):
    settings_path = str(tmp_path / "test_settings.ini")
    QSettings(settings_path, QSettings.Format.IniFormat).setValue("default_style_template", template_path)

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    for _ in range(3):
        QApplication.instance().processEvents()
    return window


@pytest.fixture
def template_path(tmp_path):
    path = tmp_path / "house.graphica-style"
    path.write_text(json.dumps(TEMPLATE, ensure_ascii=False), encoding='utf-8')
    return str(path)


def _paste(window, monkeypatch, text="x\ty\n1\t2\n3\t4\n"):
    """クリップボードからの貼り付け(列の選択画面はそのまま OK)。"""
    monkeypatch.setattr(QApplication.clipboard(), "text", lambda mode=None: text)

    class AcceptingPreview:
        def __init__(self, df, *args, **kwargs):
            self._df = df

        def exec(self):
            return QDialog.DialogCode.Accepted

        def get_selected_columns(self):
            return 'x', 'y'

        def get_dataframe(self):
            return self._df

    monkeypatch.setattr(data_import_flow, "ColumnPreviewDialog", AcceptingPreview)
    window._on_paste_data_from_clipboard()
    return window.project.datasets[-1]


def test_a_new_tab_gets_the_templates_axis_look(tmp_path, monkeypatch, template_path):
    window = _window(tmp_path, monkeypatch, template_path)

    settings = window.project.all_plot_settings[0]
    assert settings['grid_visible'] is True
    assert settings['title'] == 'テンプレートの題'
    assert window.ui.grid_visible_checkbox.isChecked()


def test_imported_datasets_get_the_templates_styles_in_order(tmp_path, monkeypatch, template_path):
    window = _window(tmp_path, monkeypatch, template_path)

    first = _paste(window, monkeypatch)
    second = _paste(window, monkeypatch)
    third = _paste(window, monkeypatch)

    assert (first.color, first.linewidth) == ('#ff0000', 3.0)
    assert (second.color, second.linewidth) == ('#00aa00', 0.5)
    assert third.color == '#ff0000'  # 保存した順に繰り返す(手動の適用と同じ)


def test_without_a_default_template_nothing_changes(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    default_color = Dataset(name="d", df=pd.DataFrame({"x": [1]}), x_col_name="x", y_col_name="x").color

    dataset = _paste(window, monkeypatch)

    assert dataset.color == default_color
    assert window.project.all_plot_settings[0].get('title', '') != 'テンプレートの題'


def test_a_missing_template_file_is_reported_not_raised(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch, str(tmp_path / "gone.graphica-style"))

    assert "gone.graphica-style" in window.statusBar().currentMessage()
    assert window._default_dataset_styles == []


def test_an_opened_project_keeps_its_own_look(tmp_path, monkeypatch, template_path):
    from graphica.gui import project_files

    source = _window(tmp_path / "a", monkeypatch)
    source.project.datasets.append(Dataset(name="d", df=pd.DataFrame({"x": [1.0], "y": [2.0]}),
                                           x_col_name="x", y_col_name="y"))
    project_path = str(tmp_path / "p.gra")
    source.project.save_project(project_path)
    window = _window(tmp_path / "b", monkeypatch, template_path)

    project_files.load_project_from_path(window, project_path, add_to_recent=False)
    pasted = _paste(window, monkeypatch)

    assert pasted.color != '#ff0000'


def test_the_preferences_dialog_offers_and_clears_the_template(qapp, monkeypatch):
    from graphica.gui import notify
    from graphica.gui.dialogs import PreferencesDialog

    dialog = PreferencesDialog(dark_mode=False, autosave_minutes=5, default_style_template="C:/old.graphica-style")
    try:
        assert dialog.default_style_template_edit.text() == "C:/old.graphica-style"
        monkeypatch.setattr(notify, "get_open_file_name", lambda *a, **k: ("C:/new.graphica-style", ""))
        dialog.default_style_template_browse_button.click()
        assert dialog.get_default_style_template() == "C:/new.graphica-style"
        dialog.default_style_template_clear_button.click()
        assert dialog.get_default_style_template() == ""
    finally:
        dialog.close()



# --- 読み込んだデータセットの自動配色(#111) ---

def test_imported_datasets_get_the_next_palette_colors(tmp_path, monkeypatch):
    from graphica.core.color_palettes import default_color_cycle
    window = _window(tmp_path, monkeypatch)
    cycle = default_color_cycle()

    colors = [_paste(window, monkeypatch).color for _ in range(3)]

    assert colors == cycle[:3]


def test_imported_colors_follow_the_active_palette(tmp_path, monkeypatch):
    from graphica.core.color_palettes import BUILTIN_PALETTES
    window = _window(tmp_path, monkeypatch)
    name = next(iter(BUILTIN_PALETTES))
    window.colors.set_active_palette(name)

    first = _paste(window, monkeypatch)
    second = _paste(window, monkeypatch)

    assert [first.color, second.color] == BUILTIN_PALETTES[name][:2]


def test_imported_colors_continue_after_existing_datasets(tmp_path, monkeypatch):
    from graphica.core.color_palettes import default_color_cycle
    window = _window(tmp_path, monkeypatch)
    for i in range(3):
        window.project.datasets.append(
            Dataset(name=f"old{i}", df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y"))

    dataset = _paste(window, monkeypatch)

    assert dataset.color == default_color_cycle()[3]


def test_the_template_color_wins_over_the_palette(tmp_path, monkeypatch, template_path):
    window = _window(tmp_path, monkeypatch, template_path)
    _paste(window, monkeypatch)

    second = _paste(window, monkeypatch)

    assert second.color == '#00aa00'
