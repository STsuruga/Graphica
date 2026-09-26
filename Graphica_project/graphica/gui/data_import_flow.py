"""データファイルの読み込みの流れ: ドロップ・複数ファイルの待ち行列・バックグラウンドの読み込み・列の選択・Excel のシート・フォルダからの一括読み込み・クリップボード。"""
import io
import logging
import os
import pandas as pd
import re
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from graphica.core.dataset import Dataset
from graphica.core.plugin_api import get_registered_importer_extensions
from graphica.gui import notify
from graphica.gui.dialogs import ColumnPreviewDialog, ExcelMultiSheetDialog, FolderImportDialog
from graphica.gui.task_runner import TaskRunner
from graphica.gui.workers import BUILTIN_DATA_FILE_EXTENSIONS, excel_engine_for, is_excel_file, load_data_file_task
from pathlib import Path

logger = logging.getLogger(__name__)


SUPPORTED_DATA_FILE_EXTENSIONS = BUILTIN_DATA_FILE_EXTENSIONS


def find_unevaluated_formula_cells(file_path, sheet_name=None, max_examples=5, max_scan_cells=200_000):
    """openpyxl の読み込み(約350ms)を起動時に払わないよう、呼ぶときに import する。

    テストがこのモジュール属性を monkeypatch で差し替えるので、名前を変えない。
    """
    from graphica.core.excel_utils import find_unevaluated_formula_cells as _impl
    return _impl(file_path, sheet_name, max_examples, max_scan_cells)


def dragEnterEvent(app, event):
    if event.mimeData().hasUrls():
        event.acceptProposedAction()


def dropEvent(app, event):
    urls = event.mimeData().urls()
    file_paths = [url.toLocalFile() for url in urls if url.toLocalFile()]
    if file_paths:
        app._queue_data_files(file_paths)


def all_supported_data_file_extensions(app):
    """組み込みの拡張子に、プラグインの読み込み機能の拡張子を足したもの。"""
    extensions = list(SUPPORTED_DATA_FILE_EXTENSIONS)
    for ext in get_registered_importer_extensions():
        if ext not in extensions:
            extensions.append(ext)
    return tuple(extensions)


def queue_data_files(app, file_paths):
    """対応していない拡張子はまとめて1回だけ知らせ、残りを待ち行列に積む。"""
    valid_paths = []
    skipped_names = []
    allowed_extensions = app._all_supported_data_file_extensions()
    for file_path in file_paths:
        if file_path.lower().endswith(allowed_extensions):
            valid_paths.append(file_path)
        else:
            skipped_names.append(os.path.basename(file_path))

    if skipped_names:
        notify.warning(
            app, "非対応のファイル形式",
            "以下のファイルは対応していない形式のため読み込みをスキップしました:\n"
            + "\n".join(skipped_names)
        )

    if not valid_paths:
        return

    app._data_load_queue.extend(valid_paths)
    app._data_load_queue_total += len(valid_paths)

    if app._data_load_task_runner is None:
        app._process_next_queued_file()


def process_next_queued_file(app):
    """読み込みの成否によらず、1件終わるたびに呼ばれる。"""
    if not app._data_load_queue:
        app._data_load_queue_total = 0
        app._data_load_queue_done = 0
        # 待ち行列を使い切ったら戻す(この後の普通の取り込みに引き継がない)
        app._batch_import_filename_regex = None
        return

    next_path = app._data_load_queue.pop(0)
    app._data_load_queue_done += 1
    app.load_data(next_path, queue_progress=(app._data_load_queue_done, app._data_load_queue_total))


def load_data(app, file_path, queue_progress=None):
    """別スレッドで読み込み、終わったらデータセットとして加える(大きいファイルで画面を止めない)。

    queue_progress=(何件目, 総数) はステータスバーの表示に使う。
    """
    if app._data_load_task_runner is not None:
        notify.information(app, "読み込み中", "他のファイルを読み込み中です。完了までお待ちください。")
        return

    app.ui.add_dataset_button.setEnabled(False)
    if queue_progress is not None:
        done, total = queue_progress
        app.statusBar().showMessage(f"読み込み中 ({done}/{total}): {os.path.basename(file_path)} ...")
    else:
        app.statusBar().showMessage(f"読み込み中: {file_path} ...")

    runner = TaskRunner(load_data_file_task, file_path, parent=app)
    runner.succeeded.connect(lambda df: app._on_data_load_succeeded(df, file_path))
    runner.failed.connect(lambda msg: app._on_data_load_failed(msg, file_path))
    app._data_load_task_runner = runner
    runner.start()


def on_data_load_succeeded(app, df, file_path):
    """途中でキャンセルされても、必ず待ち行列の次へ進む。"""
    app._cleanup_data_load_task_runner()
    try:
        app._import_loaded_dataframe(df, file_path)
    finally:
        app._process_next_queued_file()


def import_loaded_dataframe(app, df, file_path):
    """Excel でシートを複数選ぶと、シートごとに別のデータセットにする。"""
    dataset_name = os.path.basename(file_path)
    is_excel = is_excel_file(file_path)

    sheet_names = []
    if is_excel:
        try:
            sheet_names = pd.ExcelFile(file_path, engine=excel_engine_for(file_path)).sheet_names
        except Exception as e:
            logger.warning("Excelのシート一覧取得に失敗しました: %s", e)

    # None は「読み込み済みの df をそのまま使う」
    sheets_to_import = [None]
    if is_excel and len(sheet_names) > 1:
        multi_dialog = ExcelMultiSheetDialog(sheet_names, app)
        if multi_dialog.exec() != QDialog.DialogCode.Accepted:
            app.statusBar().showMessage("読み込みをキャンセルしました", 3000)
            return
        selected_sheets = multi_dialog.get_selected_sheets()
        if not selected_sheets:
            app.statusBar().showMessage("シートが選択されなかったため読み込みをキャンセルしました", 3000)
            return
        sheets_to_import = selected_sheets

    target_folder = app._get_target_folder_for_new_dataset()
    added_count = 0

    for sheet_name in sheets_to_import:
        if sheet_name is None:
            sheet_df = df
            preview_name = dataset_name
        else:
            try:
                sheet_df = pd.read_excel(file_path, sheet_name=sheet_name, engine=excel_engine_for(file_path))
            except Exception as e:
                logger.exception("シート「%s」の読み込みに失敗しました", sheet_name)
                notify.warning(app, "読み込みエラー", f"シート「{sheet_name}」の読み込みに失敗しました:\n{e}")
                continue
            if sheet_df.shape[1] < 2:
                notify.warning(
                    app, "読み込みエラー",
                    f"シート「{sheet_name}」には少なくとも2列必要です。スキップします。"
                )
                continue
            preview_name = f"{dataset_name} [{sheet_name}]" if len(sheets_to_import) > 1 else dataset_name

        if is_excel:
            checked_sheet = sheet_name if sheet_name is not None else (sheet_names[0] if sheet_names else None)
            found, examples, scanned_all = find_unevaluated_formula_cells(file_path, checked_sheet)
            if found:
                example_text = "\n".join(examples)
                more_note = "" if scanned_all else "\n(他にも存在する可能性があります)"
                reply = notify.warning(
                    app, "数式セルの警告",
                    f"シート「{checked_sheet}」に、計算済みの値を持たない数式セルが見つかりました:\n"
                    f"{example_text}{more_note}\n\n"
                    "これらのセルは空欄(NaN)として読み込まれます。Excelで開いて再計算・保存してから"
                    "読み込み直すことをお勧めします。このまま続行しますか?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply != QMessageBox.StandardButton.Yes:
                    continue

        # 列の多いファイルで意図しない列が選ばれないよう、プレビューを見せて X/Y の列を選ばせる
        preview_dialog = ColumnPreviewDialog(sheet_df, preview_name, app, file_path=file_path)
        if sheet_name is not None and preview_dialog.sheet_combo is not None:
            preview_dialog.sheet_combo.blockSignals(True)
            preview_dialog.sheet_combo.setCurrentText(sheet_name)
            preview_dialog.sheet_combo.blockSignals(False)

        if preview_dialog.exec() != QDialog.DialogCode.Accepted:
            continue

        x_col, y_col = preview_dialog.get_selected_columns()
        final_df = preview_dialog.get_dataframe()

        # 再読み込みのために元ファイルとシートを持つ。シートはダイアログで最後に選ばれたもの
        source_sheet = (
            preview_dialog.sheet_combo.currentText()
            if (is_excel and preview_dialog.sheet_combo is not None) else None
        )
        if app._batch_import_filename_regex:
            final_df = app._apply_filename_regex_columns(
                final_df, file_path, app._batch_import_filename_regex
            )
        new_dataset = Dataset(
            name=preview_name, df=final_df, x_col_name=x_col, y_col_name=y_col,
            source_file=os.path.abspath(file_path), source_sheet=source_sheet,
        )
        app._add_dataset(new_dataset, target_folder)
        added_count += 1

    if added_count > 0:
        app.statusBar().showMessage(f"読み込み完了: {file_path} ({added_count}件)", 3000)
        app._add_recent_file(file_path)
    else:
        app.statusBar().showMessage("読み込みをキャンセルしました", 3000)


def apply_filename_regex_columns(df, file_path, pattern):
    """フォルダ一括取り込みの正規表現の名前付きグループを、ファイル名から取り出して列にする。

    数値にできれば float の列。パターンが合わなくても取り込みは続けたいので、そのときは df をそのまま返す。
    """
    try:
        match = re.search(pattern, os.path.basename(file_path))
    except re.error as e:
        logger.warning("正規表現が不正なため、ファイル名からの列抽出をスキップしました: %s", e)
        return df
    if match is None:
        return df
    groups = match.groupdict()
    if not groups:
        return df

    df = df.copy()
    for name, value in groups.items():
        if value is None:
            continue
        try:
            df[name] = float(value)
        except (TypeError, ValueError):
            df[name] = value
    return df


def on_import_folder(app):
    """フォルダ内(サブフォルダは除く)の対応ファイルを、確認させてからドラッグ&ドロップと同じ待ち行列に積む。"""
    dir_path = notify.get_existing_directory(app, "フォルダから一括インポート", "")
    if not dir_path:
        return

    allowed_extensions = app._all_supported_data_file_extensions()
    try:
        file_paths = sorted(
            str(p) for p in Path(dir_path).iterdir()
            if p.is_file() and p.suffix.lower() in allowed_extensions
        )
    except OSError as e:
        notify.warning(app, "フォルダから一括インポート", f"フォルダの読み取りに失敗しました:\n{e}")
        return

    if not file_paths:
        notify.information(
            app, "フォルダから一括インポート",
            "対応する形式のファイルがフォルダ内に見つかりませんでした。"
        )
        return

    file_names = [os.path.basename(p) for p in file_paths]
    dialog = FolderImportDialog(dir_path, file_names, parent=app)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    app._batch_import_filename_regex = dialog.get_regex_pattern()
    app._queue_data_files(file_paths)


def on_paste_data_from_clipboard(app):
    """区切り文字はファイル読み込みと同じ判定で決める(Excel からのコピーはタブ区切り)。"""
    text = QApplication.clipboard().text()
    if not text.strip():
        notify.information(app, "クリップボードから貼り付け", "クリップボードにテキストデータがありません。")
        return

    from graphica.gui.workers import detect_clipboard_delimiter
    delimiter = detect_clipboard_delimiter(text)
    try:
        df = pd.read_csv(io.StringIO(text), sep=delimiter, engine='python')
    except Exception as e:
        logger.exception("クリップボードの内容を表として読めませんでした")
        notify.warning(
            app, "貼り付けエラー",
            f"クリップボードの内容を表として解釈できませんでした:\n{e}"
        )
        return

    if df.shape[1] < 2:
        notify.warning(app, "貼り付けエラー", "クリップボードのデータには少なくとも2列必要です。")
        return

    app._clipboard_paste_counter = getattr(app, '_clipboard_paste_counter', 0) + 1
    dataset_name = f"クリップボード貼り付け {app._clipboard_paste_counter}"

    preview_dialog = ColumnPreviewDialog(df, dataset_name, app, file_path=None)
    if preview_dialog.exec() != QDialog.DialogCode.Accepted:
        app.statusBar().showMessage("貼り付けをキャンセルしました", 3000)
        return

    x_col, y_col = preview_dialog.get_selected_columns()
    final_df = preview_dialog.get_dataframe()
    new_dataset = Dataset(name=dataset_name, df=final_df, x_col_name=x_col, y_col_name=y_col)
    app._add_dataset(new_dataset, app._get_target_folder_for_new_dataset())
    app.statusBar().showMessage("クリップボードからデータを貼り付けました", 3000)


def on_data_load_failed(app, error_message, file_path):
    app._cleanup_data_load_task_runner()
    app.statusBar().clearMessage()
    notify.critical(app, "エラー", f"読み込みエラー: {error_message}")
    app._process_next_queued_file()


def cleanup_data_load_task_runner(app):
    app.ui.add_dataset_button.setEnabled(True)
    if app._data_load_task_runner is not None:
        app._data_load_task_runner.wait()
        app._data_load_task_runner.deleteLater()
        app._data_load_task_runner = None
