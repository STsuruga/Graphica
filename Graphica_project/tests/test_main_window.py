# tests/test_main_window.py
"""
gui/main_window.py (PlotterApp) の統合的なGUI挙動に対する、最小限の回帰テスト。

PlotterApp のインスタンス化にはQApplicationが必要(conftest.pyのqappフィクスチャで用意)。
QSettingsは実際のレジストリ/iniファイルを汚染しないよう、一時ファイルにリダイレクトする。
"""
import os
import time

import pandas as pd
from PySide6.QtCore import QSettings, Qt, QUrl, QPoint, QPointF, QMimeData
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QToolButton

import gui.main_window as main_window_module
from core.dataset import Dataset
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


class _FakeRejectedColumnPreviewDialog:
    """ColumnPreviewDialog の代わりに使う、常にキャンセルされたものとして振る舞うダブル。"""

    def __init__(self, df, file_name, parent=None, file_path=None):
        self._df = df
        self.sheet_combo = None

    def exec(self):
        return QDialog.DialogCode.Rejected

    def get_selected_columns(self):
        raise AssertionError("キャンセルされたダイアログのget_selected_columns()は呼ばれないはず")

    def get_dataframe(self):
        raise AssertionError("キャンセルされたダイアログのget_dataframe()は呼ばれないはず")


def _make_fake_multi_sheet_dialog(accepted=True, selected_sheets=None):
    """ExcelMultiSheetDialog の代わりに使うダブルを返すファクトリ。"""

    class _FakeMultiSheetDialog:
        def __init__(self, sheet_names, parent=None):
            self.sheet_names = list(sheet_names)

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        def get_selected_sheets(self):
            return selected_sheets if selected_sheets is not None else list(self.sheet_names)

    return _FakeMultiSheetDialog


class _FakeSheetCombo:
    """ColumnPreviewDialog.sheet_combo の代わりに使う最小限のダブル。"""

    def __init__(self):
        self.blocked_calls = []
        self.current_text = None

    def blockSignals(self, blocked):
        self.blocked_calls.append(blocked)

    def setCurrentText(self, text):
        self.current_text = text


class _FakeColumnPreviewDialogWithSheetCombo:
    """sheet_comboを持つ点だけが_FakeAcceptedColumnPreviewDialogと異なるダブル。"""

    def __init__(self, df, file_name, parent=None, file_path=None):
        self._df = df
        self.sheet_combo = _FakeSheetCombo()

    def exec(self):
        return QDialog.DialogCode.Accepted

    def get_selected_columns(self):
        return self._df.columns[0], self._df.columns[1]

    def get_dataframe(self):
        return self._df


def _write_multi_sheet_excel(path, sheet_data):
    """{シート名: DataFrame} から複数シートのExcelファイルを実際に書き出す。"""
    with pd.ExcelWriter(str(path), engine='openpyxl') as writer:
        for name, df in sheet_data.items():
            df.to_excel(writer, sheet_name=name, index=False)


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
    ファイル読み込みは実際の別スレッド(TaskRunner、項目C-004フェーズ4)で行うため、
    processEvents() を呼ぶだけでなく、OS側にスレッドの実行機会を与えるための
    短いsleepを挟む(でないとメインスレッドがビジーループしてワーカースレッドの
    完了シグナルがなかなか配送されない)。
    """
    app = QApplication.instance()
    for _ in range(max_iterations):
        app.processEvents()
        if window._data_load_task_runner is None and not window._data_load_queue:
            return
        time.sleep(0.01)
    raise AssertionError("読み込みキューが時間内に消化されませんでした")


def test_close_event_waits_for_in_flight_data_load_task_runner_instead_of_crashing(tmp_path, monkeypatch):
    """
    回帰テスト: バックグラウンドでファイル読み込み中(TaskRunnerがまだ
    isRunning())にウィンドウを閉じると、実行中のQThreadがそのまま破棄され、
    Qtが例外機構を経由しないfail-fastアボートでプロセスごとクラッシュさせて
    いた(元はDataLoadWorker専用の問題だったが、closeEventが
    _data_load_task_runnerを一切見ていなければ同じ問題が再発しうる)。
    closeEventが読み込み完了までブロッキング待機し、TaskRunnerを片付けてから
    閉じることを確認する。
    """
    import pandas as pd
    import gui.workers as workers_module

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    def _slow_read_data_file(file_path):
        time.sleep(0.3)
        return pd.DataFrame({"x": [1, 2], "y": [3, 4]})

    monkeypatch.setattr(workers_module, "read_data_file", _slow_read_data_file)

    csv1 = tmp_path / "slow.csv"
    csv1.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    window.load_data(str(csv1))

    app = QApplication.instance()
    app.processEvents()
    assert window._data_load_task_runner is not None
    assert window._data_load_task_runner.isRunning()

    # 読み込み中にウィンドウを閉じてもクラッシュしない(このassert群まで
    # 到達すること自体がプロセスが生き残っている証拠)。
    window.close()

    assert window._data_load_task_runner is None


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

# --- 個別のプラグイン無効化(項目F-2) ---

def test_disabled_plugin_names_empty_by_default(tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    assert main_window_module.disabled_plugin_names(settings) == set()


def test_disabled_plugin_names_reads_stored_list(tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue(main_window_module.DISABLED_PLUGINS_SETTINGS_KEY, ["plugin_a", "plugin_b"])
    assert main_window_module.disabled_plugin_names(settings) == {"plugin_a", "plugin_b"}


def test_disabled_plugin_names_handles_single_item_stored_as_string(tmp_path):
    """QSettingsは要素数1のリストを単一の文字列として返すことがある(get_recent_filesと同じ罠)。"""
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue(main_window_module.DISABLED_PLUGINS_SETTINGS_KEY, ["plugin_a"])
    assert main_window_module.disabled_plugin_names(settings) == {"plugin_a"}


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


# --- ギリシャ文字/記号パレット(項目81: mathtext拡充、H-2-4で算術/数学記号を追加) ---

def test_label_symbol_palette_has_thirty_two_unique_entries():
    """
    項目81のギリシャ文字16個に加え、実機フィードバック(「四則演算の記号とか
    プロットでよく使う数学記号があるといいかも」)を受けて算術・数学記号16個を
    追加し、合計32個になった。
    """
    palette = main_window_module.LABEL_SYMBOL_PALETTE
    assert len(palette) == 32
    glyphs = [glyph for glyph, _ in palette]
    macros = [macro for _, macro in palette]
    assert len(set(glyphs)) == len(glyphs)
    assert len(set(macros)) == len(macros)


def test_label_symbol_palette_macros_are_valid_matplotlib_mathtext():
    """
    パレットの全マクロが、$\\macro$という単純な埋め込み方式(引数不要)で
    実際にmatplotlibのmathtextパーサーを通ることを確認する(\\sqrtのように
    引数を必須とするマクロは、この挿入方式と相性が悪いため収録していない
    ことの裏付け)。
    """
    from matplotlib.mathtext import MathTextParser

    parser = MathTextParser('path')
    for glyph, macro in main_window_module.LABEL_SYMBOL_PALETTE:
        parser.parse(f"$\\{macro}$", dpi=100)  # 例外が出ないことを確認するだけでよい


# --- データセットリスト・検索ボックス(項目H-2-2) ---

def test_dataset_list_widget_uses_selection_delegate(tmp_path, monkeypatch):
    """
    選択ハイライトをアイコン列+テキスト列にまたがる単一の角丸矩形として
    描画するため、専用デリゲート(_DatasetTreeSelectionDelegate)が
    dataset_list_widgetに設定されていることを確認する(実機フィードバックで
    QSSだけでは実現できないことが判明した経緯は_DatasetTreeSelectionDelegate
    のdocstring、およびgui/theme.pyの該当コメントを参照)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    delegate = window.ui.dataset_list_widget.itemDelegate()
    assert isinstance(delegate, main_window_module._DatasetTreeSelectionDelegate)


def test_dataset_search_edit_has_object_name_for_qss_scoping(tmp_path, monkeypatch):
    """
    検索ボックス単体の枠線を消すQSS(#dataset_search_edit)をスコープするため、
    objectNameが設定されていることを確認する。リストとの統合ではなく、
    検索ボックス自身の見た目調整のためのobjectNameであることに注意
    (実機フィードバックで「統合することじゃない」と明確に区別された)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.dataset_search_edit.objectName() == "dataset_search_edit"


def test_dataset_search_edit_and_list_remain_separate_boxes_with_spacing(tmp_path, monkeypatch):
    """
    検索ボックスとリストは統合された1つの箱ではなく、間に余白を持つ独立した
    箱のままであることを確認する(実機フィードバックで「隙間を1.5倍くらい
    広く」と指定され、4px→6pxに変更した経緯がある)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    container_layout = window.dataset_search_edit.parentWidget().layout()
    assert container_layout.spacing() == 6


# --- ドックのフォーカス時強調(項目H-2-3) ---

def test_control_dock_gets_focus_highlight_installed(tmp_path, monkeypatch):
    """
    theme.install_dock_focus_highlight()がPlotterApp.__init__内で
    (プラグイン製パネルの構築後、_connect_signals()より前に)呼ばれており、
    プロパティドックにフォーカスが入るとdockActiveプロパティが立つことを
    確認する。
    """
    from PySide6.QtWidgets import QLineEdit, QWidget

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    # データセット未選択だと大半のプロパティ欄はdisabledで(disabledな
    # ウィジェットはフォーカスを受け取れずno-opになる)、常にenabledな欄を
    # 探して使う(タイトル/軸ラベル欄など、プロット全体設定は選択不要のため)。
    candidates = window.ui.control_dock_widget.findChildren(QWidget)
    field = next(
        (w for w in candidates if isinstance(w, QLineEdit) and w.isEnabled() and w.isVisible()), None
    )
    assert field is not None
    field.setFocus()

    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    assert window.ui.control_dock_widget.property("dockActive") is True


def test_dataset_tree_selection_delegate_paint_does_not_raise_when_selected(qapp):
    """
    _DatasetTreeSelectionDelegate.paint()が選択状態でも例外を出さず、
    Qt標準の選択背景描画(State_Selected)を自前描画に置き換えた後も
    基底実装への委譲が正常に完了することを確認する回帰テスト。
    """
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem

    from gui import theme
    theme.apply_theme(qapp, dark=False)

    tree = QTreeWidget()
    tree.setColumnCount(1)
    item = QTreeWidgetItem(["sample_dataset.csv"])
    tree.addTopLevelItem(item)
    delegate = main_window_module._DatasetTreeSelectionDelegate(tree)
    tree.setItemDelegate(delegate)

    pixmap = QPixmap(200, 30)
    painter = QPainter(pixmap)
    try:
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 200, 30)
        option.state = QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_Enabled
        delegate.paint(painter, option, tree.indexFromItem(item))
    finally:
        painter.end()


# --- タイトル/軸ラベルのポップアップ編集ダイアログ(項目H-2-4、実機フィード
#     バック: 「軸ラベル、タイトルは入力画面がポップアップウィンドウとして
#     出てくるような形がいい」でLabelEditDialog(gui/dialogs.py)に置き換え) ---

def test_open_label_edit_dialog_writes_back_accepted_text(tmp_path, monkeypatch):
    """
    「Aa」ボタン相当の_open_label_edit_dialog()が、ダイアログでOKされた結果を
    実際のline_editへ書き戻すことを確認する(ダイアログのexec()は実際には
    モーダルループを回してしまうため、LabelEditDialog.execを差し替えてテストする)。
    """
    from gui.dialogs import LabelEditDialog
    from PySide6.QtWidgets import QDialog

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    line_edit = window.ui.title_text_edit
    line_edit.setText("orig title")

    def fake_exec(self):
        self.text_edit.setText(r"edited $\alpha$")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(LabelEditDialog, "exec", fake_exec)
    window._open_label_edit_dialog(line_edit, "タイトルを編集")

    assert line_edit.text() == r"edited $\alpha$"


def test_open_label_edit_dialog_leaves_text_unchanged_when_cancelled(tmp_path, monkeypatch):
    from gui.dialogs import LabelEditDialog
    from PySide6.QtWidgets import QDialog

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    line_edit = window.ui.title_text_edit
    line_edit.setText("orig title")

    def fake_exec(self):
        self.text_edit.setText("should not be used")
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(LabelEditDialog, "exec", fake_exec)
    window._open_label_edit_dialog(line_edit, "タイトルを編集")

    assert line_edit.text() == "orig title"


def test_label_edit_dialog_symbol_click_inserts_at_cursor_when_no_selection(qapp):
    from gui.dialogs import LabelEditDialog

    dialog = LabelEditDialog("VT", "タイトルを編集", main_window_module.LABEL_SYMBOL_PALETTE)
    dialog.text_edit.setCursorPosition(1)  # "V|T"
    dialog._capture_pending_selection()  # ボタンのpressedで起きる処理を模擬

    dialog._insert_symbol('alpha')

    assert dialog.get_text() == r"V$\alpha$T"


def test_label_edit_dialog_symbol_click_replaces_selection(qapp):
    from gui.dialogs import LabelEditDialog

    dialog = LabelEditDialog("Peak XYZ", "タイトルを編集", main_window_module.LABEL_SYMBOL_PALETTE)
    dialog.text_edit.setSelection(5, 3)  # "XYZ"
    dialog._capture_pending_selection()

    dialog._insert_symbol('Omega')

    assert dialog.get_text() == r"Peak $\Omega$"


def test_label_edit_dialog_bold_wraps_selection(qapp):
    from gui.dialogs import LabelEditDialog

    dialog = LabelEditDialog("Peak XYZ", "タイトルを編集", main_window_module.LABEL_SYMBOL_PALETTE)
    dialog.text_edit.setSelection(0, 4)  # "Peak"
    dialog._capture_pending_selection()

    dialog._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}")

    assert dialog.get_text() == r"$\mathbf{Peak}$ XYZ"


def test_label_edit_dialog_wrap_without_selection_shows_message(qapp, monkeypatch):
    from gui.dialogs import LabelEditDialog
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(True)))

    dialog = LabelEditDialog("Peak XYZ", "タイトルを編集", main_window_module.LABEL_SYMBOL_PALETTE)
    dialog._capture_pending_selection()  # 選択なしの状態を確定させる
    dialog._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}")

    assert shown == [True]
    assert dialog.get_text() == "Peak XYZ"  # 変更されない


def test_label_edit_dialog_pressed_signal_captures_selection_before_focus_moves(qapp):
    """
    バグ回帰テスト: 「文字選択してハイライトされてからボタン押しても文字を
    選択してって出る」。装飾ボタンのpressedシグナルが実際に
    _capture_pending_selectionへ配線されており、text_editの選択範囲を
    正しく捕捉することを、シグナルを実際に発火させて確認する
    (_capture_pending_selectionを手動で呼ぶ他のテストと異なり、配線自体の
    誤りも検出できる)。
    """
    from gui.dialogs import LabelEditDialog

    dialog = LabelEditDialog("Peak XYZ", "タイトルを編集", main_window_module.LABEL_SYMBOL_PALETTE)
    dialog.text_edit.setSelection(0, 4)  # "Peak"

    # 装飾ボタンはローカル変数のみで、インスタンス属性としては保持していない
    # ため、ツールチップで特定してpressedを発火させる。
    from PySide6.QtWidgets import QPushButton
    bold_button = next(
        b for b in dialog.findChildren(QPushButton) if b.toolTip() == "太字"
    )
    bold_button.pressed.emit()

    assert dialog._pending_selection == (0, "Peak")


# --- タイトル/軸ラベル欄クリックでダイアログを開く + mathtextライブプレビュー
#     (項目H-2-4追加分、実機フィードバック: 「画像のテキスト欄をクリックしたら
#     さっき作成したポップアップが展開するように」「画像のテキストボックスでは
#     mathtextを翻訳した形式をプレビューしといて」) ---

def test_label_preview_widgets_registered_for_title_and_both_axis_labels(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert len(window._label_preview_widgets) == 3
    line_edits = {le for _preview, le, _placeholder in window._label_preview_widgets}
    assert line_edits == {
        window.ui.title_text_edit,
        window.ui.x_label_text_edit,
        window.ui.y_label_text_edit,
    }


def test_label_preview_widget_visible_while_backing_line_edit_is_hidden(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    preview, line_edit, _placeholder = window._label_preview_widgets[0]
    assert line_edit.isHidden()
    assert not preview.isHidden()


def test_clicking_label_preview_opens_label_edit_dialog(tmp_path, monkeypatch):
    from gui.dialogs import LabelEditDialog
    from PySide6.QtWidgets import QDialog

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    preview, line_edit, _placeholder = window._label_preview_widgets[0]
    line_edit.setText("orig title")

    opened = []

    def fake_exec(self):
        opened.append(self.get_text())
        self.text_edit.setText("clicked and edited")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(LabelEditDialog, "exec", fake_exec)
    preview.clicked.emit()

    assert opened == ["orig title"]
    assert line_edit.text() == "clicked and edited"


def test_label_preview_pixmap_updates_when_backing_text_changes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    preview, line_edit, _placeholder = window._label_preview_widgets[0]

    empty_pixmap = preview.pixmap()
    assert empty_pixmap is not None and not empty_pixmap.isNull()

    line_edit.setText("新しいタイトル")

    filled_pixmap = preview.pixmap()
    assert filled_pixmap is not None and not filled_pixmap.isNull()
    # プレースホルダ("タイトルを入力")と実テキストとでは描画結果(サイズ)が
    # 異なるはずで、textChanged→_refresh_label_preview の配線を検証できる
    assert (filled_pixmap.width(), filled_pixmap.height()) != (
        empty_pixmap.width(), empty_pixmap.height(),
    )


def test_refresh_all_label_previews_updates_every_registered_widget(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.ui.title_text_edit.setText("タイトル")
    window.ui.x_label_text_edit.setText("X軸")
    window.ui.y_label_text_edit.setText("Y軸")

    before = [preview.pixmap().toImage() for preview, _le, _ph in window._label_preview_widgets]
    window._refresh_all_label_previews()
    after = [preview.pixmap().toImage() for preview, _le, _ph in window._label_preview_widgets]

    for before_img, after_img in zip(before, after):
        assert before_img.size() == after_img.size()


def test_clickable_math_preview_label_emits_clicked_on_left_click(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QMouseEvent
    from gui.main_window import _ClickableMathPreviewLabel

    label = _ClickableMathPreviewLabel()
    received = []
    label.clicked.connect(lambda: received.append(True))

    pos = QPoint(5, 5)
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, pos, pos, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    label.mousePressEvent(event)

    assert received == [True]


def test_clickable_math_preview_label_has_hover_attribute_enabled(qapp):
    from PySide6.QtCore import Qt
    from gui.main_window import _ClickableMathPreviewLabel

    label = _ClickableMathPreviewLabel()
    assert label.testAttribute(Qt.WidgetAttribute.WA_Hover)


def test_properties_dock_content_actually_renders_bg_token_color(tmp_path, monkeypatch):
    """
    実際にウィジェットをレンダリングしてピクセル色を確認する統合テスト
    (実機フィードバック「プロパティウィンドウの背景色が他と違う」の回帰、
    QDockWidgetにbackgroundを追加した後も再発した2回目の修正)。

    QSSの文字列に`background: {bg}`が含まれているかどうかを確認するだけの
    テスト(test_theme.pyのgenerated_qss系)では、実際に画面へ出る色までは
    検証できず、本バグ(QScrollAreaの中身のwidgetがアプリ全体QSSの副作用で
    OSネイティブパレット色に不透明に塗りつぶされ、QSSの指定が実際には
    見えなくなっていた)を検出できなかった実例。QWidget.grab()で実際に
    描画させ、ピクセル色がbgトークンと一致することを直接確認する。
    """
    from PySide6.QtGui import QColor
    from gui import theme

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    theme.apply_theme(QApplication.instance(), dark=False)
    app = QApplication.instance()
    for _ in range(3):
        app.processEvents()

    scroll_area = window.ui.control_dock_widget.widget()
    content_widget = scroll_area.widget()
    image = content_widget.grab().toImage()
    # 左上の余白部分(データセットのプロパティグループボックスの枠外)をサンプル
    sample = image.pixelColor(2, 2)
    expected = QColor(theme.LIGHT_TOKENS["bg"])
    assert (sample.red(), sample.green(), sample.blue()) == (
        expected.red(), expected.green(), expected.blue(),
    )


def test_toggling_dark_mode_refreshes_label_previews(tmp_path, monkeypatch):
    """
    ダークモード切り替え時にプレビューが再レンダリングされないと、テーマ変更前
    (旧配色)の見た目のまま残ってしまう回帰を防ぐ(_on_toggle_dark_modeから
    _refresh_all_label_previews()が呼ばれていることの確認)。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(window, "_refresh_all_label_previews", lambda: calls.append(True))

    window._on_toggle_dark_mode(True)

    assert calls == [True]


def test_toggling_dark_mode_refreshes_color_picker_swatch_borders(tmp_path, monkeypatch):
    """
    項目H-2-6の回帰テスト: ColorPickerWidgetのスウォッチ枠線もテーマの
    border_strongトークンを参照するようになったため、ダークモード切り替え時に
    再描画(refresh_theme())されないと旧テーマの枠線色のまま残ってしまう。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(window.color_picker_widget, "refresh_theme", lambda: calls.append("main"))
    monkeypatch.setattr(window.gradient_color2_picker, "refresh_theme", lambda: calls.append("gradient"))

    window._on_toggle_dark_mode(True)

    assert set(calls) == {"main", "gradient"}


# --- 項目H-4(アイコンセットの見直し): 永続的なウィジェットのアイコンは
#     テーマ切り替え時に明示的に再読み込みしないと、構築時のテーマの色の
#     まま残ってしまう ---

def test_toggling_dark_mode_refreshes_mpl_toolbar_and_custom_icons(tmp_path, monkeypatch):
    """
    _on_toggle_dark_modeが_refresh_mpl_toolbar_icons/_refresh_custom_svg_icons
    の両方を呼ぶことを確認する。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(window, "_refresh_mpl_toolbar_icons", lambda: calls.append("mpl"))
    monkeypatch.setattr(window, "_refresh_custom_svg_icons", lambda: calls.append("custom"))

    window._on_toggle_dark_mode(True)

    assert set(calls) == {"mpl", "custom"}


def test_mpl_toolbar_attribute_is_the_navigation_toolbar(tmp_path, monkeypatch):
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert isinstance(window.mpl_toolbar, NavigationToolbar2QT)


def test_refresh_mpl_toolbar_icons_updates_action_icons_without_raising(tmp_path, monkeypatch):
    from gui import theme

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    theme.apply_theme(QApplication.instance(), dark=False)  # 実行順序に依らず既知の状態から開始
    window._refresh_mpl_toolbar_icons()
    home_action = window.mpl_toolbar._actions.get('home')
    assert home_action is not None
    before = home_action.icon().pixmap(24, 24).toImage()

    window._on_toggle_dark_mode(True)

    after = home_action.icon().pixmap(24, 24).toImage()
    # ダークモードへの切り替えでピクセル内容(色)が実際に変わっていること
    assert before != after


def test_refresh_custom_svg_icons_updates_tracked_widgets_without_raising(tmp_path, monkeypatch):
    from gui import theme

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    theme.apply_theme(QApplication.instance(), dark=False)  # 実行順序に依らず既知の状態から開始
    window._refresh_custom_svg_icons()
    before = window.cursor_action.icon().pixmap(20, 20).toImage()

    window._on_toggle_dark_mode(True)

    after = window.cursor_action.icon().pixmap(20, 20).toImage()
    assert before != after


def test_constructing_with_dark_mode_already_saved_uses_dark_icon_colors_from_the_start(tmp_path, monkeypatch):
    """
    回帰テスト: 以前はQApplication側の配色適用(theme.apply_theme)を
    _create_menu_bar()まで先送りしていたため、それより前(ツールバーの
    カーソル/注釈/レイアウト編集ボタン等)に構築されるアイコンは、
    theme._current_tokensがまだNoneでLIGHT_TOKENSにフォールバックした
    状態で焼き込まれていた。「前回起動時はダークモードだった」設定を
    QSettingsに保存した状態で新規construction すると、__init__の
    早い段階で既にダーク用の色になっていることを確認する
    (_on_toggle_dark_modeで手動に切り替え直す必要がないこと)。
    """
    from gui import theme

    settings_path = str(tmp_path / "test_settings.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window_module, "QSettings", IsolatedQSettings)
    IsolatedQSettings().setValue("dark_mode", True)  # 「前回はダークモードだった」を再現

    theme.apply_theme(QApplication.instance(), dark=False)  # プロセスの残留状態をリセット
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 500)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    at_construction = window.cursor_action.icon().pixmap(20, 20).toImage()

    # 既に正しいダーク用の色であれば、明示的な再読み込みをしても見た目は変わらないはず
    window._refresh_custom_svg_icons()
    after_explicit_dark_refresh = window.cursor_action.icon().pixmap(20, 20).toImage()
    assert at_construction == after_explicit_dark_refresh

    # 対照確認: ライトへ切り替えた場合は実際に見た目が変わる(比較自体が
    # 意味のあるものであることの確認)
    theme.apply_theme(app, dark=False)
    window._refresh_custom_svg_icons()
    light_icon = window.cursor_action.icon().pixmap(20, 20).toImage()
    assert light_icon != at_construction
    theme.apply_theme(app, dark=False)


def test_turning_off_cursor_mode_does_not_disable_click_to_select(tmp_path, monkeypatch):
    """
    回帰テスト: データカーソルモードをOFFにすると、以前は全Artistに
    set_picker(False) していたため、データカーソルとは無関係な「クリックで
    データセットを選択」機能(項目35、gui/canvas.pyのpicker管理により常時
    有効)まで巻き添えで反応しなくなっていた(次のフル再描画まで直らない)。
    データカーソルをON→OFFしても、線のpickerが有効(truthy)なまま残る
    ことを確認する。
    """
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2, 3], "y": [1, 4, 9]}),
                 x_col_name="x", y_col_name="y")
    window.project.datasets.append(ds)
    window._update_plot()

    line = window.canvas.all_axes[0].get_lines()[0]
    assert line.get_picker()  # 項目35: 常時クリック選択可能なはず

    window._toggle_cursor_mode(True)
    window._toggle_cursor_mode(False)

    line_after = window.canvas.all_axes[0].get_lines()[0]
    assert line_after.get_picker(), (
        "データカーソルをOFFにした後も、クリックでデータセットを選択する"
        "機能(項目35)のpickerは有効なままであるべき"
    )


def test_reopening_data_editor_deletes_the_previous_dialog_instance(tmp_path, monkeypatch):
    """
    回帰テスト: 別のデータセットに切り替えて「データ表示/編集」を開き直すと、
    古いDataEditorDialogインスタンスはclose()されるだけでC++オブジェクトは
    破棄されず、非表示のままメインウィンドウにぶら下がり続けていた
    (開き直すたびに蓄積するメモリリーク)。deleteLater()により、次のイベント
    ループで実際に破棄されることを確認する。
    """
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
                  x_col_name="x", y_col_name="y")
    ds2 = Dataset(name="d2", df=pd.DataFrame({"x": [5, 6], "y": [7, 8]}),
                  x_col_name="x", y_col_name="y")
    window.project.datasets.extend([ds1, ds2])
    window._add_dataset_list_item(ds1)
    window._add_dataset_list_item(ds2)
    window._update_plot()

    window.ui.dataset_list_widget.setCurrentItem(window._get_dataset_tree_item(ds1))
    window._on_show_data_editor()
    first_dialog = window.data_editor_dialog

    delete_later_calls = []
    monkeypatch.setattr(
        first_dialog, 'deleteLater',
        lambda: delete_later_calls.append(True)
    )

    window.ui.dataset_list_widget.setCurrentItem(window._get_dataset_tree_item(ds2))
    window._on_show_data_editor()

    assert delete_later_calls == [True]


def test_shrinking_subplot_grid_reassigns_datasets_instead_of_hiding_them(tmp_path, monkeypatch):
    """
    回帰テスト: 2x2グリッドの4枚目(subplot_target=3)にデータセットを配置した
    状態で1x1に縮小すると、all_plot_settingsは切り詰められるのに
    dataset.subplot_targetはそのまま(=3)残っていたため、どの軸にも
    描画されず、エクスポート画像からもサイレントに消えていた
    (グリッドを再び広げると復活するため気づきにくい)。縮小時に、
    存在しなくなった番号のデータセットは最後のサブプロットへ
    割り当て直されることを確認する。
    """
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.subplot_rows_spinbox.setValue(2)
    window.subplot_cols_spinbox.setValue(2)

    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
                 x_col_name="x", y_col_name="y", subplot_target=3)
    window.project.datasets.append(ds)

    window.subplot_rows_spinbox.setValue(1)
    window.subplot_cols_spinbox.setValue(1)

    assert ds.subplot_target == 0  # 唯一残ったサブプロット(index 0)に割り当て直される
    assert len(window.canvas.all_axes) == 1
    assert window.canvas.all_axes[0].get_lines()  # 実際にどこかの軸に描画されている


def test_refresh_custom_svg_icons_updates_collapsible_toggle_buttons(tmp_path, monkeypatch):
    from gui import theme

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    theme.apply_theme(QApplication.instance(), dark=False)  # 実行順序に依らず既知の状態から開始
    assert len(window._collapsible_toggle_buttons) > 0
    btn = window._collapsible_toggle_buttons[0]
    window._refresh_custom_svg_icons()
    before = btn.icon().pixmap(14, 14).toImage()

    window._on_toggle_dark_mode(True)

    after = btn.icon().pixmap(14, 14).toImage()
    assert before != after


# --- フォームラベルの末尾コロン除去(項目H-2-4、実機フィードバック:
#     「各設定項目のあとの：はなくして」) ---

class TestStripTrailingColonFromLabels:
    def test_strips_trailing_fullwidth_colon(self, qapp):
        from PySide6.QtWidgets import QLabel, QWidget

        parent = QWidget()
        label = QLabel("凡例名：", parent)
        main_window_module._strip_trailing_colon_from_labels(parent)

        assert label.text() == "凡例名"

    def test_leaves_labels_without_trailing_colon_unchanged(self, qapp):
        from PySide6.QtWidgets import QLabel, QWidget

        parent = QWidget()
        label = QLabel("X軸の列", parent)
        main_window_module._strip_trailing_colon_from_labels(parent)

        assert label.text() == "X軸の列"

    def test_only_strips_trailing_colon_not_colon_mid_text(self, qapp):
        from PySide6.QtWidgets import QLabel, QWidget

        parent = QWidget()
        label = QLabel("「Speed」と表示したい場合：例", parent)
        main_window_module._strip_trailing_colon_from_labels(parent)

        assert label.text() == "「Speed」と表示したい場合：例"

    def test_real_app_form_labels_have_no_trailing_colon(self, tmp_path, monkeypatch):
        """
        ui_main_window.py(Qt Designer生成物)に焼き込まれたコロン付き
        ラベルが、実際のPlotterApp構築後には除去されていることを確認する
        (回帰テスト)。
        """
        window = _make_isolated_plotter_app(tmp_path, monkeypatch)
        assert window.ui.legend_name_label.text() == "凡例名"
        assert window.ui.color_label.text() == "色"


# ============================================================================
# 以下、カバレッジギャップ埋め (missing lines) のための追加テスト。
# ============================================================================

# --- _scientific_validate(): 指数表記の入力途中状態の許容 ---

def test_scientific_validate_empty_or_sign_only_is_intermediate():
    state, _text, _pos = main_window_module._scientific_validate(None, "", 0)
    assert state == main_window_module.QValidator.State.Intermediate
    state, _text, _pos = main_window_module._scientific_validate(None, "-", 1)
    assert state == main_window_module.QValidator.State.Intermediate
    state, _text, _pos = main_window_module._scientific_validate(None, "+", 1)
    assert state == main_window_module.QValidator.State.Intermediate


def test_scientific_validate_partial_exponent_is_intermediate_not_invalid():
    """正規表現にはマッチするがfloat()には変換できない入力途中の状態
    (例: "1e", "1e-")は、Invalidではなく Intermediate として許容される。"""
    state, _text, _pos = main_window_module._scientific_validate(None, "1e", 2)
    assert state == main_window_module.QValidator.State.Intermediate
    state, _text, _pos = main_window_module._scientific_validate(None, "1e-", 3)
    assert state == main_window_module.QValidator.State.Intermediate


# --- disabled_plugin_names(): QSettingsが単一文字列を返すケースの補正 ---

def test_disabled_plugin_names_handles_qsettings_returning_bare_string():
    class _FakeStringSettings:
        def value(self, key, default=None):
            return "solo_plugin"

    assert main_window_module.disabled_plugin_names(_FakeStringSettings()) == {"solo_plugin"}


# --- __init__: control_dock_widgetの中身が見つからない防御分岐 ---

def test_missing_control_dock_contents_logs_warning_instead_of_crashing(tmp_path, monkeypatch, caplog):
    from PySide6.QtWidgets import QDockWidget
    monkeypatch.setattr(QDockWidget, "widget", lambda self: None)
    with caplog.at_level("WARNING"):
        _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert any("control_dock_widget の中身が見つかりません" in r.message for r in caplog.records)


# --- _restore_dock_layout() ---

def test_restore_dock_layout_restores_saved_state_when_version_matches(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    saved_state = window.saveState()
    window._run_startup_checks = True
    window.settings.setValue("dock_layout_version", main_window_module.DOCK_LAYOUT_VERSION)
    window.settings.setValue("window_state", saved_state)

    # 例外なく完了すること(restoreState()の成功パス)を確認する
    window._restore_dock_layout()


def test_restore_dock_layout_swallows_resizedocks_exception(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(window, "resizeDocks", _raise)
    # run_startup_checks=False (既定) のため常に「未復元」分岐に入る
    window._restore_dock_layout()


# --- closeEvent() ---

def test_close_event_swallows_signal_disconnect_error(tmp_path, monkeypatch):
    """
    実際のQt Signalは「何も接続されていない状態でdisconnect()」してもRuntimeWarning
    止まりで例外を送出しないPySide6バージョンがあるため、except節を確実に踏ませる
    には disconnect() 自体が例外を送出するダブルに差し替える必要がある。
    """
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    class _FakeSignal:
        def connect(self, *a, **k):
            pass

        def disconnect(self, *a, **k):
            raise TypeError("nothing connected")

    class _FakeTaskRunner:
        def __init__(self):
            self.succeeded = _FakeSignal()
            self.failed = _FakeSignal()
            self.waited = False

        def requestInterruption(self):
            pass

        def wait(self):
            self.waited = True

        def deleteLater(self):
            pass

    fake_runner = _FakeTaskRunner()
    window._data_load_task_runner = fake_runner
    window.closeEvent(QCloseEvent())  # disconnect()の失敗が例外を伝播させないことを確認
    assert window._data_load_task_runner is None
    assert fake_runner.waited is True


def test_close_event_saves_settings_when_run_startup_checks_true(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._run_startup_checks = True
    window.closeEvent(QCloseEvent())
    assert window.settings.value("clean_exit", False, type=bool) is True
    assert window.settings.value("dock_layout_version", 0, type=int) == main_window_module.DOCK_LAYOUT_VERSION


# --- _check_autosave_recovery() ---

def test_check_autosave_recovery_no_file_returns_silently(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._had_clean_exit = False
    window._autosave_filename = str(tmp_path / "no_such_autosave.graphica")

    def _fail_if_called(*a, **k):
        raise AssertionError("オートセーブファイルが無いのに確認ダイアログが出た")

    monkeypatch.setattr(main_window_module.QMessageBox, "question", staticmethod(_fail_if_called))
    window._check_autosave_recovery()  # 例外なく静かに戻ることを確認


def test_check_autosave_recovery_falls_back_to_legacy_pkl_and_loads_on_yes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._had_clean_exit = False
    window._autosave_filename = str(tmp_path / "autosave.graphica")  # 新形式は存在しない
    legacy_path = str(tmp_path / "autosave.pkl")
    with open(legacy_path, "wb") as f:
        f.write(b"dummy")

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question",
        staticmethod(lambda *a, **k: main_window_module.QMessageBox.StandardButton.Yes),
    )
    calls = []
    monkeypatch.setattr(
        window, "_load_project_from_path",
        lambda path, add_to_recent=True: calls.append((path, add_to_recent)),
    )

    window._check_autosave_recovery()

    assert calls == [(legacy_path, False)]


def test_check_autosave_recovery_reply_no_does_not_load(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._had_clean_exit = False
    autosave_path = str(tmp_path / "autosave.graphica")
    with open(autosave_path, "wb") as f:
        f.write(b"{}")
    window._autosave_filename = autosave_path

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question",
        staticmethod(lambda *a, **k: main_window_module.QMessageBox.StandardButton.No),
    )

    def _fail_if_called(*a, **k):
        raise AssertionError("Noと答えたのに読み込みが行われた")

    monkeypatch.setattr(window, "_load_project_from_path", _fail_if_called)
    window._check_autosave_recovery()


# --- _check_first_launch() / _load_sample_data() ---

def test_check_first_launch_skips_when_already_shown(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.settings.setValue("has_shown_welcome", True)

    def _fail(*a, **k):
        raise AssertionError("既に表示済みなのにWelcomeDialogが出た")

    monkeypatch.setattr(main_window_module, "WelcomeDialog", _fail)
    window._check_first_launch()


def test_check_first_launch_loads_sample_when_requested(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.settings.setValue("has_shown_welcome", False)

    class _FakeWelcomeDialog:
        def __init__(self, parent=None):
            self.load_sample_requested = True

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "WelcomeDialog", _FakeWelcomeDialog)
    calls = []
    monkeypatch.setattr(window, "_load_sample_data", lambda: calls.append(True))

    window._check_first_launch()

    assert calls == [True]
    assert window.settings.value("has_shown_welcome", False, type=bool) is True


def test_load_sample_data_missing_file_shows_warning_and_does_not_load(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module, "resource_path", lambda *a, **k: str(tmp_path / "does_not_exist.csv"))
    warn_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(a)))
    load_calls = []
    monkeypatch.setattr(window, "load_data", lambda path: load_calls.append(path))

    window._load_sample_data()

    assert len(warn_calls) == 1
    assert load_calls == []


def test_load_sample_data_existing_file_calls_load_data(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    sample_path = tmp_path / "sample.csv"
    sample_path.write_text("x,y\n1,2\n", encoding="utf-8")
    monkeypatch.setattr(main_window_module, "resource_path", lambda *a, **k: str(sample_path))
    load_calls = []
    monkeypatch.setattr(window, "load_data", lambda path: load_calls.append(path))

    window._load_sample_data()

    assert load_calls == [str(sample_path)]


# --- _update_autosave_path() ---

def test_update_autosave_path_makedirs_failure_falls_back_to_base_filename(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    target_dir = str(tmp_path / "some_autosave_dir")
    window.settings.setValue("autosave_dir", target_dir)

    real_makedirs = os.makedirs

    def _flaky_makedirs(path, exist_ok=False):
        if os.path.normpath(path) == os.path.normpath(target_dir):
            raise OSError("permission denied")
        return real_makedirs(path, exist_ok=exist_ok)

    monkeypatch.setattr(main_window_module.os, "makedirs", _flaky_makedirs)
    window._update_autosave_path()

    assert window._autosave_filename == window._autosave_base_filename


# --- manual_save() / manual_load() ---

def test_manual_save_cancelled_dialog_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    calls = []
    monkeypatch.setattr(window.project, "save_project", lambda path: calls.append(path))
    window.manual_save()
    assert calls == []


def test_manual_save_success_infers_graphica_extension_and_adds_recent_file(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    target = str(tmp_path / "myproject")  # 拡張子なし
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (target, "Graphica Project (*.graphica)")),
    )
    saved_paths = []
    monkeypatch.setattr(window.project, "save_project", lambda path: saved_paths.append(path))

    window.manual_save()

    assert saved_paths == [target + ".graphica"]
    assert window._get_recent_files()[0] == os.path.abspath(target + ".graphica")


def test_manual_save_exception_shows_critical_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    target = str(tmp_path / "myproject.graphica")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (target, "Graphica Project (*.graphica)")),
    )

    def _raise(path):
        raise RuntimeError("disk full")

    monkeypatch.setattr(window.project, "save_project", _raise)
    critical_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window.manual_save()

    assert len(critical_calls) == 1


def test_manual_load_cancelled_dialog_does_nothing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    calls = []
    monkeypatch.setattr(window, "_load_project_from_path", lambda *a, **k: calls.append(a))
    window.manual_load()
    assert calls == []


def test_manual_load_selected_file_delegates_to_load_project_from_path(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    target = str(tmp_path / "myproject.graphica")
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (target, "")))
    calls = []
    monkeypatch.setattr(window, "_load_project_from_path", lambda path: calls.append(path))
    window.manual_load()
    assert calls == [target]


# --- _load_project_from_path() ---

def test_load_project_from_path_success_rebuilds_ui_and_updates_recent_files(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y")
    window.project.datasets.append(ds)
    window._add_dataset_list_item(ds)
    window.project.dataset_group_tree = window._capture_dataset_group_tree()
    save_path = str(tmp_path / "proj.graphica")
    window.project.save_project(save_path)

    window._load_project_from_path(save_path)

    assert len(window.project.datasets) == 1
    assert window.project.datasets[0].name == "d"
    assert window._get_recent_files()[0] == os.path.abspath(save_path)


def test_load_project_from_path_exception_shows_critical_dialog(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    def _raise(path):
        raise RuntimeError("corrupt file")

    monkeypatch.setattr(window.project, "load_project", _raise)
    critical_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window._load_project_from_path(str(tmp_path / "bad.graphica"))

    assert len(critical_calls) == 1


# --- _reset_zoom() / _update_plot()の早期return / _refresh_minimap() / _on_toggle_panel_labels() ---

def test_reset_zoom_calls_update_plot(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(window, "_update_plot", lambda: calls.append(True))
    window._reset_zoom()
    assert calls == [True]


def test_update_plot_free_layout_with_no_settings_returns_early(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    called = []
    monkeypatch.setattr(window.canvas, "redraw_all", lambda *a, **k: called.append(True))
    window.project.layout_mode = 'free'
    window.project.all_plot_settings = []
    count_before = len(called)
    window._update_plot()
    assert len(called) == count_before


def test_update_plot_grid_layout_with_zero_rows_or_cols_returns_early(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    called = []
    monkeypatch.setattr(window.canvas, "redraw_all", lambda *a, **k: called.append(True))
    window.subplot_cols_spinbox.setRange(0, 10)
    window.subplot_cols_spinbox.setValue(0)
    count_before = len(called)
    window._update_plot()
    assert len(called) == count_before


def test_refresh_minimap_noop_when_minimap_widget_not_yet_created(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    delattr(window, "minimap")
    window._refresh_minimap()  # 例外が出ないことを確認


def test_on_toggle_panel_labels_updates_project_and_replots(tmp_path, monkeypatch):
    """項目C-003フェーズ2: パネルラベル切替は軽量パス(light=True)を使う。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(window, "_update_plot", lambda light=False: calls.append(light))
    window._on_toggle_panel_labels(True)
    assert window.project.panel_labels_enabled is True
    assert calls == [True]


def test_update_plot_light_true_uses_lightweight_canvas_method_and_preserves_axes_identity(tmp_path, monkeypatch):
    """
    項目C-003フェーズ2の配線確認: _update_plot(light=True)は
    canvas.redraw_all()(fig.clf()でAxesを作り直す)ではなく
    canvas.update_all_axes_appearance_and_data()(既存Axesのまま)を呼ぶこと。
    Axesオブジェクトのアイデンティティが保たれることで間接的に確認する。
    """
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2, 3], "y": [1, 4, 9]}),
                 x_col_name="x", y_col_name="y")
    window.project.datasets.append(ds)
    window._update_plot()
    axis_before = window.canvas.all_axes[0]

    window._update_plot(light=True)

    assert window.canvas.all_axes[0] is axis_before


def test_update_plot_default_is_full_redraw_and_recreates_axes(tmp_path, monkeypatch):
    """light引数を省略した従来通りの呼び出しは、フルの再描画(canvas.redraw_all())
    のままであること(Axesオブジェクトが作り直される)を確認する回帰テスト。"""
    from core.dataset import Dataset
    import pandas as pd

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2, 3], "y": [1, 4, 9]}),
                 x_col_name="x", y_col_name="y")
    window.project.datasets.append(ds)
    window._update_plot()
    axis_before = window.canvas.all_axes[0]

    window._update_plot()

    assert window.canvas.all_axes[0] is not axis_before


# --- キャンバス切り離し/再アタッチの早期return分岐 ---

def test_sync_canvas_detach_action_noop_when_action_not_yet_created(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    delattr(window, "canvas_detach_action")
    window._sync_canvas_detach_action()  # 例外なく戻ることを確認


def test_detach_canvas_is_noop_when_already_detached(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._detach_canvas()
    detach_window_first = window._canvas_detach_window
    window._detach_canvas()  # 2回目は何もしない
    assert window._canvas_detach_window is detach_window_first
    window._reattach_canvas()  # 後片付け


def test_reattach_canvas_is_noop_when_not_detached(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.canvas_detached is False
    window._reattach_canvas()  # 何もしない(例外が出ないことを確認)
    assert window.canvas_detached is False


# --- データエディタ行ハイライトの反映 ---

def test_on_editor_rows_highlighted_noop_when_no_dialog_open(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    assert window.data_editor_dialog is None
    window._on_editor_rows_highlighted([0, 1])  # 例外なく戻ることを確認


def test_reapply_editor_row_highlight_calls_set_highlighted_points_when_dialog_open(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x_col_name="x", y_col_name="y")
    window.project.datasets.append(ds)
    window._update_plot()

    class _FakeEditorDialog:
        dataset = ds

        def get_selected_master_indices(self):
            return [0]

    window.data_editor_dialog = _FakeEditorDialog()
    calls = []
    monkeypatch.setattr(window.canvas, "set_highlighted_points", lambda ds_, idx: calls.append((ds_, idx)))

    window._reapply_editor_row_highlight()

    assert calls == [(ds, [0])]


# --- データセットツリーのヘルパー群 ---

def test_replace_dataset_list_with_tree_second_call_falls_back_to_plain_addwidget(tmp_path, monkeypatch):
    """2回目の呼び出し時は親レイアウトがQGridLayoutではなくなっているため、
    row指定なしのaddWidget()にフォールバックする(else分岐)。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._replace_dataset_list_with_tree()
    assert window.ui.dataset_list_widget is not None


def test_add_dataset_list_item_under_folder_adds_as_child(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("フォルダ1")
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y")
    item = window._add_dataset_list_item(ds, folder)
    assert item.parent() is folder
    assert folder.childCount() == 1


def test_get_target_folder_for_new_dataset_returns_selected_folder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("フォルダ1")
    window.ui.dataset_list_widget.setCurrentItem(folder)
    assert window._get_target_folder_for_new_dataset() is folder


def test_add_dataset_with_undo_removes_from_folder_on_undo(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("フォルダ1")
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y")

    window._add_dataset_with_undo(ds, parent_folder=folder)
    assert folder.childCount() == 1
    assert ds in window.project.datasets

    window.undo_stack.undo()
    assert folder.childCount() == 0
    assert ds not in window.project.datasets


def test_add_dataset_folder_item_nested_under_parent_folder(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    parent_folder = window._add_dataset_folder_item("親")
    child_folder = window._add_dataset_folder_item("子", parent_folder)
    assert child_folder.parent() is parent_folder


def test_flatten_dataset_tree_recurses_into_nested_folders(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds1 = Dataset(name="d1", df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y")
    ds2 = Dataset(name="d2", df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y")
    window._add_dataset_list_item(ds1)  # トップレベル(先頭)
    folder = window._add_dataset_folder_item("フォルダ1")  # トップレベル(2番目)
    window._add_dataset_list_item(ds2, folder)  # フォルダの中

    items = window._flatten_dataset_tree()
    datasets = [it.data(0, Qt.ItemDataRole.UserRole) for it in items]
    assert datasets == [ds1, ds2]


def test_get_dataset_tree_item_returns_none_when_dataset_not_in_tree(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="orphan", df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y")
    assert window._get_dataset_tree_item(ds) is None


def test_capture_dataset_group_tree_includes_folder_structure(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    folder = window._add_dataset_folder_item("フォルダ1")
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y")
    window._add_dataset_list_item(ds, folder)

    tree = window._capture_dataset_group_tree()

    assert tree['children'][0]['name'] == "フォルダ1"
    assert tree['children'][0]['children'][0]['dataset'] is ds


def test_rebuild_dataset_tree_widget_restores_dataset_and_folder_nodes(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y")
    window.project.dataset_group_tree = {
        'name': '', 'children': [
            {'dataset': ds},
            {'name': 'フォルダ1', 'children': [{'dataset': ds}]},
        ]
    }

    window._rebuild_dataset_tree_widget()

    assert window.ui.dataset_list_widget.topLevelItemCount() == 2
    folder_item = window.ui.dataset_list_widget.topLevelItem(1)
    assert folder_item.text(0) == "フォルダ1"
    assert folder_item.childCount() == 1


def test_sync_dataset_list_widget_order_reorders_datasets_within_folders(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)

    def _ds(name):
        return Dataset(name=name, df=pd.DataFrame({"x": [1], "y": [1]}), x_col_name="x", y_col_name="y")

    ds_a, ds_b, ds_c, ds_d = _ds("A"), _ds("B"), _ds("C"), _ds("D")
    folder = window._add_dataset_folder_item("フォルダ1")  # トップレベル index 0
    window._add_dataset_list_item(ds_a)  # トップレベル index 1
    window._add_dataset_list_item(ds_b)  # トップレベル index 2
    window._add_dataset_list_item(ds_c, folder)
    window._add_dataset_list_item(ds_d, folder)
    window.project.datasets.extend([ds_a, ds_b, ds_c, ds_d])

    # project.datasets側の順序を変更してから、ウィジェット側をそれに同期させる
    window.project.datasets = [ds_b, ds_a, ds_d, ds_c]
    window._sync_dataset_list_widget_order()

    tree = window.ui.dataset_list_widget
    assert tree.topLevelItem(0).text(0) == "フォルダ1"
    assert tree.topLevelItem(1).text(0) == "B"
    assert tree.topLevelItem(2).text(0) == "A"
    folder_item = tree.topLevelItem(0)
    child_names = [folder_item.child(i).text(0) for i in range(folder_item.childCount())]
    assert child_names == ["D", "C"]


def test_drag_enter_event_accepts_when_mime_has_urls(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(tmp_path / "x.csv"))])
    event = QDragEnterEvent(
        QPoint(0, 0), Qt.DropAction.CopyAction, mime_data,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    event._mime_data_keepalive = mime_data
    window.dragEnterEvent(event)
    assert event.isAccepted()


# --- ファイル読み込みキュー ---

def test_queue_data_files_all_invalid_extensions_returns_without_queuing(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    warn_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(a)))
    bad_file = tmp_path / "data.unsupported_ext"
    bad_file.write_text("dummy", encoding="utf-8")

    window._queue_data_files([str(bad_file)])

    assert len(warn_calls) == 1
    assert window._data_load_queue == []


def test_load_data_while_already_loading_shows_information_and_returns(tmp_path, monkeypatch):
    from gui.task_runner import TaskRunner
    from gui.workers import load_data_file_task

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    dummy_runner = TaskRunner(load_data_file_task, "dummy.csv", parent=window)
    window._data_load_task_runner = dummy_runner
    info_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    window.load_data(str(tmp_path / "another.csv"))

    assert len(info_calls) == 1
    assert window._data_load_task_runner is dummy_runner  # 新しいTaskRunnerに置き換わっていない


# --- _import_loaded_dataframe(): Excel複数シート・数式警告・列不足まわり ---

def test_import_loaded_dataframe_excel_sheet_list_fetch_failure_falls_back_to_single_sheet(tmp_path, monkeypatch):
    """pd.ExcelFile(...).sheet_names の取得に失敗しても(壊れたファイル等)、
    ワーカーが既に読み込み済みのdfをそのまま単一データセットとして追加できる。"""
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeAcceptedColumnPreviewDialog)
    bad_excel_path = str(tmp_path / "corrupt.xlsx")
    with open(bad_excel_path, "wb") as f:
        f.write(b"not a real xlsx file")

    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    initial_count = len(window._flatten_dataset_tree())

    window._import_loaded_dataframe(df, bad_excel_path)

    assert len(window._flatten_dataset_tree()) == initial_count + 1


def test_import_loaded_dataframe_multi_sheet_dialog_rejected_cancels_import(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    excel_path = tmp_path / "multi.xlsx"
    _write_multi_sheet_excel(excel_path, {
        "Sheet1": pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
        "Sheet2": pd.DataFrame({"x": [5, 6], "y": [7, 8]}),
    })
    monkeypatch.setattr(main_window_module, "ExcelMultiSheetDialog", _make_fake_multi_sheet_dialog(accepted=False))

    initial_count = len(window._flatten_dataset_tree())
    window._import_loaded_dataframe(pd.DataFrame(), str(excel_path))
    assert len(window._flatten_dataset_tree()) == initial_count


def test_import_loaded_dataframe_multi_sheet_dialog_no_sheets_selected_cancels_import(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    excel_path = tmp_path / "multi.xlsx"
    _write_multi_sheet_excel(excel_path, {
        "Sheet1": pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
        "Sheet2": pd.DataFrame({"x": [5, 6], "y": [7, 8]}),
    })
    monkeypatch.setattr(
        main_window_module, "ExcelMultiSheetDialog",
        _make_fake_multi_sheet_dialog(accepted=True, selected_sheets=[]),
    )

    initial_count = len(window._flatten_dataset_tree())
    window._import_loaded_dataframe(pd.DataFrame(), str(excel_path))
    assert len(window._flatten_dataset_tree()) == initial_count


def test_import_loaded_dataframe_multi_sheet_success_with_formula_warning_and_sheet_combo(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    excel_path = tmp_path / "multi.xlsx"
    _write_multi_sheet_excel(excel_path, {
        "Sheet1": pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
        "Sheet2": pd.DataFrame({"x": [5, 6], "y": [7, 8]}),
    })
    monkeypatch.setattr(
        main_window_module, "ExcelMultiSheetDialog",
        _make_fake_multi_sheet_dialog(accepted=True, selected_sheets=["Sheet1", "Sheet2"]),
    )
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeColumnPreviewDialogWithSheetCombo)

    def _fake_find_unevaluated(file_path, checked_sheet):
        # Sheet1では見つかる(Yesと答えて続行)、Sheet2では見つからない
        if checked_sheet == "Sheet1":
            return True, ["Sheet1!A1"], True
        return False, [], True

    monkeypatch.setattr(main_window_module, "find_unevaluated_formula_cells", _fake_find_unevaluated)
    monkeypatch.setattr(
        main_window_module.QMessageBox, "warning",
        staticmethod(lambda *a, **k: main_window_module.QMessageBox.StandardButton.Yes),
    )

    initial_count = len(window._flatten_dataset_tree())
    window._import_loaded_dataframe(pd.DataFrame(), str(excel_path))

    assert len(window._flatten_dataset_tree()) == initial_count + 2


def test_import_loaded_dataframe_formula_warning_reply_no_skips_sheet(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    excel_path = tmp_path / "single.xlsx"
    _write_multi_sheet_excel(excel_path, {"Sheet1": pd.DataFrame({"x": [1, 2], "y": [3, 4]})})
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeAcceptedColumnPreviewDialog)
    monkeypatch.setattr(
        main_window_module, "find_unevaluated_formula_cells",
        lambda file_path, checked_sheet: (True, ["Sheet1!A1"], True),
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "warning",
        staticmethod(lambda *a, **k: main_window_module.QMessageBox.StandardButton.No),
    )

    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    initial_count = len(window._flatten_dataset_tree())
    window._import_loaded_dataframe(df, str(excel_path))

    assert len(window._flatten_dataset_tree()) == initial_count


def test_import_loaded_dataframe_multi_sheet_skips_sheet_with_read_error_and_insufficient_columns(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    excel_path = tmp_path / "multi.xlsx"
    _write_multi_sheet_excel(excel_path, {
        "Good": pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
        "Bad": pd.DataFrame({"x": [1, 2], "y": [3, 4]}),  # 読み込み時にエラーにする
        "TooFewCols": pd.DataFrame({"only": [1, 2]}),
    })
    monkeypatch.setattr(
        main_window_module, "ExcelMultiSheetDialog",
        _make_fake_multi_sheet_dialog(accepted=True, selected_sheets=["Good", "Bad", "TooFewCols"]),
    )
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeAcceptedColumnPreviewDialog)
    monkeypatch.setattr(main_window_module, "find_unevaluated_formula_cells", lambda *a, **k: (False, [], True))

    real_read_excel = pd.read_excel

    def _flaky_read_excel(file_path, sheet_name=None, **kwargs):
        if sheet_name == "Bad":
            raise ValueError("corrupt sheet")
        return real_read_excel(file_path, sheet_name=sheet_name, **kwargs)

    monkeypatch.setattr(main_window_module.pd, "read_excel", _flaky_read_excel)
    warn_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(a)))

    initial_count = len(window._flatten_dataset_tree())
    window._import_loaded_dataframe(pd.DataFrame(), str(excel_path))

    # 3シート中「Good」だけが実際に追加される
    assert len(window._flatten_dataset_tree()) == initial_count + 1
    assert len(warn_calls) == 2  # Bad(読み込みエラー) + TooFewCols(列不足)


def test_import_loaded_dataframe_column_preview_dialog_rejected_shows_cancelled_message(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeRejectedColumnPreviewDialog)
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("x,y\n1,2\n", encoding="utf-8")
    df = pd.DataFrame({"x": [1], "y": [2]})

    initial_count = len(window._flatten_dataset_tree())
    window._import_loaded_dataframe(df, str(csv_path))

    assert len(window._flatten_dataset_tree()) == initial_count
    assert window.statusBar().currentMessage() == "読み込みをキャンセルしました"


# --- _on_paste_data_from_clipboard() ---

def test_paste_from_clipboard_empty_shows_information(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(QApplication.clipboard(), "text", lambda mode=None: "   ")
    info_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    window._on_paste_data_from_clipboard()

    assert len(info_calls) == 1


def test_paste_from_clipboard_invalid_data_shows_warning(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(QApplication.clipboard(), "text", lambda mode=None: "x\ty\n1\t2\n")

    def _raise(*a, **k):
        raise ValueError("cannot parse")

    monkeypatch.setattr(main_window_module.pd, "read_csv", _raise)
    warn_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_paste_data_from_clipboard()

    assert len(warn_calls) == 1


def test_paste_from_clipboard_insufficient_columns_shows_warning(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(QApplication.clipboard(), "text", lambda mode=None: "onlyonecolumn\n1\n2\n")
    warn_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_paste_data_from_clipboard()

    assert len(warn_calls) == 1


def test_paste_from_clipboard_dialog_cancelled_shows_status_message(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(QApplication.clipboard(), "text", lambda mode=None: "x\ty\n1\t2\n")
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeRejectedColumnPreviewDialog)

    initial_count = len(window._flatten_dataset_tree())
    window._on_paste_data_from_clipboard()

    assert len(window._flatten_dataset_tree()) == initial_count
    assert window.statusBar().currentMessage() == "貼り付けをキャンセルしました"


def test_paste_from_clipboard_success_adds_dataset(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    monkeypatch.setattr(QApplication.clipboard(), "text", lambda mode=None: "x\ty\n1\t2\n3\t4\n")
    monkeypatch.setattr(main_window_module, "ColumnPreviewDialog", _FakeAcceptedColumnPreviewDialog)

    initial_count = len(window._flatten_dataset_tree())
    window._on_paste_data_from_clipboard()

    assert len(window._flatten_dataset_tree()) == initial_count + 1


# --- _on_data_load_failed() ---

def test_on_data_load_failed_shows_critical_and_processes_next_queued_file(tmp_path, monkeypatch):
    from gui.task_runner import TaskRunner
    from gui.workers import load_data_file_task

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    runner = TaskRunner(load_data_file_task, "dummy.csv", parent=window)
    window._data_load_task_runner = runner
    critical_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))
    next_calls = []
    monkeypatch.setattr(window, "_process_next_queued_file", lambda: next_calls.append(True))

    window._on_data_load_failed("読み込みエラー詳細", "dummy.csv")

    assert len(critical_calls) == 1
    assert next_calls == [True]
    assert window._data_load_task_runner is None


# --- 最近使ったファイル一覧 ---

def test_get_recent_files_handles_qsettings_returning_bare_string(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window.settings.setValue("recent_files", "solo_file.csv")
    assert window._get_recent_files() == ["solo_file.csv"]


def test_add_recent_file_moves_existing_entry_to_front_without_duplicating(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    path_a = str(tmp_path / "a.csv")
    path_b = str(tmp_path / "b.csv")
    window._add_recent_file(path_a)
    window._add_recent_file(path_b)
    window._add_recent_file(path_a)  # 既存パスの再追加 -> 先頭に移動するだけ

    files = window._get_recent_files()
    assert files[0] == os.path.abspath(path_a)
    assert files.count(os.path.abspath(path_a)) == 1


def test_on_open_recent_file_missing_file_warns_and_removes_from_list(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    missing_path = str(tmp_path / "gone.csv")
    window._add_recent_file(missing_path)
    warn_calls = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(a)))

    window._on_open_recent_file(missing_path)

    assert len(warn_calls) == 1
    assert os.path.abspath(missing_path) not in window._get_recent_files()


def test_on_open_recent_file_project_file_delegates_to_load_project_from_path(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    project_path = tmp_path / "proj.graphica"
    project_path.write_text("{}", encoding="utf-8")
    calls = []
    monkeypatch.setattr(window, "_load_project_from_path", lambda path: calls.append(path))

    window._on_open_recent_file(str(project_path))

    assert calls == [str(project_path)]


def test_on_open_recent_file_data_file_delegates_to_load_data(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    data_path = tmp_path / "data.csv"
    data_path.write_text("x,y\n1,2\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(window, "load_data", lambda path: calls.append(path))

    window._on_open_recent_file(str(data_path))

    assert calls == [str(data_path)]


def test_on_clear_recent_files_empties_settings_list(tmp_path, monkeypatch):
    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    window._add_recent_file(str(tmp_path / "a.csv"))
    window._on_clear_recent_files()
    assert window._get_recent_files() == []
