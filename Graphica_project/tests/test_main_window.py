# tests/test_main_window.py
"""
gui/main_window.py (PlotterApp) の統合的なGUI挙動に対する、最小限の回帰テスト。

PlotterApp のインスタンス化にはQApplicationが必要(conftest.pyのqappフィクスチャで用意)。
QSettingsは実際のレジストリ/iniファイルを汚染しないよう、一時ファイルにリダイレクトする。
"""
import time

from PySide6.QtCore import QSettings, Qt, QUrl, QPointF, QMimeData
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QDialog, QToolButton

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
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


class _FakeAcceptedColumnPreviewDialog:
    """
    ColumnPreviewDialog の代わりに使う、実際にダイアログを表示しないダブル。
    常に「先頭2列をX/Y軸として選択し、OKした」ものとして振る舞う。
    """

    def __init__(self, df, file_name, parent=None, file_path=None):
        self._df = df
        self.sheet_combo = None

    def exec(self):
        return QDialog.DialogCode.Accepted

    def get_selected_columns(self):
        return self._df.columns[0], self._df.columns[1]

    def get_dataframe(self):
        return self._df


def _make_drop_event(file_paths):
    """指定したローカルファイルパス群を、ドロップされたものとして表すQDropEventを作る"""
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(p)) for p in file_paths])
    event = QDropEvent(
        QPointF(0, 0),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # QDropEvent はQMimeDataを生ポインタでしか保持しないため、Python側の参照が
    # なくなるとGCされてダングリングポインタになる。eventと寿命を揃えるため
    # 明示的に参照を保持しておく。
    event._mime_data_keepalive = mime_data
    return event


def _pump_events_until_queue_drained(window, max_iterations=300):
    """
    バックグラウンドの読み込みキューが完全に消化されるまでイベントループを回す。
    DataLoadWorker は実際の別スレッド(QThread)でファイルI/Oを行うため、
    processEvents() を呼ぶだけでなく、OS側にスレッドの実行機会を与えるための
    短いsleepを挟む(でないとメインスレッドがビジーループしてワーカースレッドの
    完了シグナルがなかなか配送されない)。
    """
    app = QApplication.instance()
    for _ in range(max_iterations):
        app.processEvents()
        if window._data_load_worker is None and not window._data_load_queue:
            return
        time.sleep(0.01)
    raise AssertionError("読み込みキューが時間内に消化されませんでした")


def test_drop_event_queues_and_loads_all_supported_files(tmp_path, monkeypatch):
    """
    項目77: 複数ファイルをドラッグ&ドロップすると、最初の1件だけでなく
    全ファイルが1つずつ順番に読み込まれ、データセットとして追加されること。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeAcceptedColumnPreviewDialog)

    csv1 = tmp_path / "a.csv"
    csv1.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    csv2 = tmp_path / "b.csv"
    csv2.write_text("x,y\n5,6\n7,8\n", encoding="utf-8")

    initial_count = len(window._flatten_dataset_tree())

    window.dropEvent(_make_drop_event([csv1, csv2]))
    _pump_events_until_queue_drained(window)

    assert len(window._flatten_dataset_tree()) == initial_count + 2


def test_drop_event_skips_unsupported_extension_but_loads_the_rest(tmp_path, monkeypatch):
    """
    項目77: 対応拡張子でないファイルがバッチの途中に混ざっていても、
    そのファイルだけ警告付きでスキップし、残りのファイルは読み込みが続行されること。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeAcceptedColumnPreviewDialog)

    warning_calls = []
    monkeypatch.setattr(
        main_window_module.QMessageBox, "warning",
        staticmethod(lambda *args, **kwargs: warning_calls.append(args))
    )

    csv1 = tmp_path / "a.csv"
    csv1.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("これはデータファイルではありません", encoding="utf-8")
    csv2 = tmp_path / "b.csv"
    csv2.write_text("x,y\n5,6\n7,8\n", encoding="utf-8")

    initial_count = len(window._flatten_dataset_tree())

    window.dropEvent(_make_drop_event([csv1, unsupported, csv2]))
    _pump_events_until_queue_drained(window)

    # 対応拡張子の2件は読み込まれ、非対応の1件はスキップされる
    assert len(window._flatten_dataset_tree()) == initial_count + 2
    # スキップの警告は(ファイルごとではなく)1回だけまとめて表示される
    assert len(warning_calls) == 1
    assert "notes.txt" in warning_calls[0][2]


# --- register_importer()由来の拡張子(項目B-1) ---

def test_all_supported_data_file_extensions_without_plugins():
    """_all_supported_data_file_extensionsはself.*を参照しないため、
    PlotterAppを組み立てずに直接呼び出せる。"""
    from gui.main_window import PlotterApp, SUPPORTED_DATA_FILE_EXTENSIONS
    assert PlotterApp._all_supported_data_file_extensions(None) == SUPPORTED_DATA_FILE_EXTENSIONS


def test_all_supported_data_file_extensions_includes_plugin_extensions(monkeypatch):
    import core.plugin_api as plugin_api_module
    from core.plugin_api import GraphicaPluginAPI
    from gui.main_window import PlotterApp, SUPPORTED_DATA_FILE_EXTENSIONS

    api = GraphicaPluginAPI()
    api.register_importer([".testfmt"], lambda fp: None, name="X")
    monkeypatch.setattr(plugin_api_module, "_singleton_api", api)

    extensions = PlotterApp._all_supported_data_file_extensions(None)
    assert set(extensions) == set(SUPPORTED_DATA_FILE_EXTENSIONS) | {".testfmt"}


def test_drop_event_loads_file_with_plugin_registered_extension(tmp_path, monkeypatch):
    """D&D一括取込(項目77)の対応拡張子判定が、register_importer()で
    登録した拡張子でも動くこと(項目B-1)。"""
    import core.plugin_api as plugin_api_module
    from core.plugin_api import GraphicaPluginAPI
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeAcceptedColumnPreviewDialog)

    api = GraphicaPluginAPI()
    api.register_importer(
        [".testfmt"], lambda fp: pd.DataFrame({'a': [1.0, 2.0], 'b': [3.0, 4.0]}), name="X"
    )
    monkeypatch.setattr(plugin_api_module, "_singleton_api", api)

    custom_file = tmp_path / "sample.testfmt"
    custom_file.write_text("dummy", encoding="utf-8")

    initial_count = len(window._flatten_dataset_tree())
    window.dropEvent(_make_drop_event([custom_file]))
    _pump_events_until_queue_drained(window)

    assert len(window._flatten_dataset_tree()) == initial_count + 1


def test_properties_dock_has_no_horizontal_scrollbar(tmp_path, monkeypatch):
    """
    バグ回帰テスト: 「データセットのプロパティ」「プロットのプロパティ」を
    折りたたみ可能にした際(項目102)、縦スクロールバー分の幅を差し引いた
    ビューポート幅に対して中身がわずかにはみ出し、意図しない横スクロールバーが
    常時表示されてしまっていた。CONTROL_DOCK_WIDTHの拡幅とレイアウト余白の
    圧縮で解消済み。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    scroll_area = window.ui.control_dock_widget.widget()

    assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll_area.horizontalScrollBar().maximum() == 0
    # 中身の最小幅は、スクロールバー分を差し引いたビューポート幅に収まっているべき
    assert scroll_area.widget().minimumSizeHint().width() <= scroll_area.viewport().width()


def test_properties_dock_vertical_scroll_still_works_after_collapse(tmp_path, monkeypatch):
    """
    折りたたみアコーディオン(項目102)のトグル後も、縦スクロールバーの範囲が
    正しく再計算されることを確認する(横スクロールバー修正の副作用がないことの確認)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    scroll_area = window.ui.control_dock_widget.widget()
    vbar = scroll_area.verticalScrollBar()
    max_before = vbar.maximum()
    assert max_before > 0

    toggle_buttons = [
        b for b in window.ui.control_dock_widget.findChildren(QToolButton)
        if b.objectName() == "collapsible_section_toggle"
    ]
    assert len(toggle_buttons) == 2
    toggle_buttons[0].setChecked(False)

    app = QApplication.instance()
    for _ in range(10):
        app.processEvents()

    assert vbar.maximum() < max_before


# --- ギリシャ文字/記号パレット(項目81: mathtext拡充) ---

def test_label_symbol_palette_has_sixteen_unique_entries():
    palette = main_window_module.LABEL_SYMBOL_PALETTE
    assert len(palette) == 16
    glyphs = [glyph for glyph, _ in palette]
    macros = [macro for _, macro in palette]
    assert len(set(glyphs)) == len(glyphs)
    assert len(set(macros)) == len(macros)


def test_label_symbol_click_inserts_at_cursor_when_no_selection(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    line_edit = window.ui.title_text_edit
    line_edit.setText("VT")
    line_edit.setCursorPosition(1)  # "V|T"
    window._capture_label_format_selection('title', line_edit)

    window._on_label_symbol_clicked('title', 'alpha')

    assert line_edit.text() == r"V$\alpha$T"


def test_label_symbol_click_replaces_selection(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    line_edit = window.ui.title_text_edit
    line_edit.setText("Peak XYZ")
    line_edit.setSelection(5, 3)  # "XYZ"
    window._capture_label_format_selection('title', line_edit)

    window._on_label_symbol_clicked('title', 'Omega')

    assert line_edit.text() == r"Peak $\Omega$"
