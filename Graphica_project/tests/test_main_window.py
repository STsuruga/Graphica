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
