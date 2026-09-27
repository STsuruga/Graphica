"""プロジェクトのファイル: 保存・読み込み・未保存の変更の確認・オートセーブと世代・最近使ったファイル。"""
import logging
import os
from PySide6.QtWidgets import QDialog, QMessageBox
from datetime import datetime
from graphica.core.app_paths import get_app_data_dir
from graphica.gui import app_settings, notify
from graphica.gui.dialogs import AutosaveHistoryDialog

logger = logging.getLogger(__name__)


AUTOSAVE_GENERATIONS = 3  # 最新の autosave.graphica を含む


MAX_RECENT_FILES = 10


# 未保存の変更の確認を出すか。テストはモーダルなダイアログで止まるので tests/conftest.py が "0" にする
UNSAVED_CHANGES_PROMPT_ENV = "GRAPHICA_CONFIRM_UNSAVED_CHANGES"


def _unsaved_changes_prompt_enabled():
    return os.environ.get(UNSAVED_CHANGES_PROMPT_ENV, "1") != "0"


def check_autosave_recovery(app):
    """前回が正常に終わらず、オートセーブが残っていれば、復元するか尋ねる(起動時に1回)。

    新しい形式のファイルが無ければ、古い版が残した .pkl を探す。
    """
    if app._had_clean_exit:
        return

    autosave_path = app._autosave_filename
    if not os.path.exists(autosave_path):
        legacy_path = os.path.splitext(app._autosave_filename)[0] + '.pkl'
        if os.path.exists(legacy_path):
            autosave_path = legacy_path
        else:
            return

    reply = notify.question(
        app, "オートセーブからの復元",
        "前回はプロジェクトが正常に終了しなかったようです。\n"
        "自動保存されていたデータを復元しますか?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes
    )
    if reply == QMessageBox.StandardButton.Yes:
        app._load_project_from_path(autosave_path, add_to_recent=False)


def on_show_autosave_history(app):
    """オートセーブの世代を新しい順に見せ、選んだものを読み込む(復元確認と同じく、最近使ったファイルに載せず、上書き保存の対象にもしない)。"""
    base, ext = os.path.splitext(app._autosave_filename)
    candidates = [(app._autosave_filename, "現在(最新)")]
    for gen in range(1, AUTOSAVE_GENERATIONS):
        candidates.append((f"{base}.{gen}{ext}", f"{gen}世代前"))

    generations = []
    for path, label in candidates:
        if not os.path.exists(path):
            continue
        try:
            mtime_text = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            mtime_text = "(更新日時不明)"
        generations.append((path, label, mtime_text))

    if not generations:
        notify.information(app, "自動バックアップ履歴", "自動バックアップファイルが見つかりませんでした。")
        return

    dialog = AutosaveHistoryDialog(generations, parent=app)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    selected_path = dialog.get_selected_path()
    if not selected_path:
        return

    reply = notify.question(
        app, "自動バックアップ履歴",
        "選択した世代の内容で復元します。現在の未保存の変更は失われます。よろしいですか?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    app._load_project_from_path(selected_path, add_to_recent=False)


def update_autosave_path(app):
    """autosave_dir(空なら get_app_data_dir())から保存先を決め、フォルダを作る。

    カレントディレクトリは使わない(macOS の .app では書き込めない場所になる)。
    """
    autosave_dir = app_settings.AUTOSAVE_DIR.read(app.settings)
    if autosave_dir:
        try:
            os.makedirs(autosave_dir, exist_ok=True)
        except OSError as e:
            logger.warning("オートセーブ保存先フォルダの作成に失敗しました: %s", e)
            autosave_dir = ""
    if not autosave_dir:
        autosave_dir = get_app_data_dir()
    app._autosave_filename = os.path.join(autosave_dir, app._autosave_base_filename)


def rotate_autosave_generations(app):
    """autosave.graphica を autosave.1.graphica, autosave.2.graphica, ... へ押し出す。"""
    base, ext = os.path.splitext(app._autosave_filename)

    oldest = f"{base}.{AUTOSAVE_GENERATIONS - 1}{ext}"
    if os.path.exists(oldest):
        os.remove(oldest)

    for gen in range(AUTOSAVE_GENERATIONS - 2, 0, -1):
        src = f"{base}.{gen}{ext}"
        dst = f"{base}.{gen + 1}{ext}"
        if os.path.exists(src):
            os.replace(src, dst)

    if os.path.exists(app._autosave_filename):
        os.replace(app._autosave_filename, f"{base}.1{ext}")


def sync_project_from_ui(app):
    """UI にしか無い状態(フォルダ構造、サブプロットの行数と列数)を、保存や比較の前に ProjectModel へ移す。"""
    app.project.dataset_group_tree = app._capture_dataset_group_tree()
    app.project.layout_rows = app.subplot_rows_spinbox.value()
    app.project.layout_cols = app.subplot_cols_spinbox.value()


def remember_saved_content(app):
    """いまの内容を保存済みとみなす(保存・読み込みの成功直後に呼ぶ)。"""
    app._sync_project_from_ui()
    app._saved_content_fingerprint = app.project.content_fingerprint()


def document_title(app):
    if app._current_project_path:
        return os.path.basename(app._current_project_path)
    if app._restored_unsaved:
        return "無題のプロジェクト(復元)"
    return "無題のプロジェクト"


def has_unsaved_changes(app):
    """データセットが無く、ファイルとも対応していない新しいタブは False。"""
    if not app.project.datasets and not app._current_project_path:
        return False
    if app._saved_content_fingerprint is None:
        return True
    app._sync_project_from_ui()
    return app.project.content_fingerprint() != app._saved_content_fingerprint


def confirm_unsaved_changes(app, action_text):
    """未保存の変更があれば「保存 / 保存しない / キャンセル」を尋ねる。続けてよければ True。"""
    if not _unsaved_changes_prompt_enabled() or not app.has_unsaved_changes():
        return True
    name = app.document_title()
    box = QMessageBox(app)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("保存されていない変更")
    box.setText(f"「{name}」には保存されていない変更があります。")
    box.setInformativeText(f"{action_text}前に保存しますか?")
    save_button = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
    discard_button = box.addButton("保存しない", QMessageBox.ButtonRole.DestructiveRole)
    cancel_button = box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(save_button)
    box.setEscapeButton(cancel_button)
    box.exec()
    clicked = box.clickedButton()
    if clicked is discard_button:
        return True
    if clicked is save_button:
        app.manual_save()
        return not app.has_unsaved_changes()
    return False


def auto_save(app):
    try:
        app._sync_project_from_ui()
        app._rotate_autosave_generations()
        app.project.save_project(app._autosave_filename)
        app.statusBar().showMessage("オートセーブ完了", 3000)
    except Exception as e:
        logger.exception("オートセーブに失敗しました")
        app.statusBar().showMessage(f"オートセーブ失敗: {e}", 3000)


def manual_save(app):
    """保存先が分かっていればそこへ上書きし、無ければ「名前を付けて保存」にする。"""
    if not app._current_project_path:
        app.manual_save_as()
        return
    app._save_project_to_path(app._current_project_path)


def manual_save_as(app):
    # 任意のコードを実行されない .graphica を既定にする。.pkl も選べる
    filepath, selected_filter = notify.get_save_file_name(
        app, "名前を付けて保存", "",
        "Graphica Project (*.graphica);;Project Files (*.pkl)"
    )
    if filepath:
        # 選んだ形式の拡張子を付けないファイルダイアログがある
        if not os.path.splitext(filepath)[1]:
            filepath += '.graphica' if 'graphica' in selected_filter else '.pkl'
        app._save_project_to_path(filepath)


def save_project_to_path(app, filepath):
    try:
        app._sync_project_from_ui()
        app.project.save_project(filepath)
        app._current_project_path = filepath
        app._restored_unsaved = False
        app._saved_content_fingerprint = app.project.content_fingerprint()
        app.statusBar().showMessage(f"保存しました: {filepath}", 3000)
        app._add_recent_file(filepath)
        app.project_state_changed.emit()
    except Exception as e:
        logger.exception("プロジェクトの保存に失敗しました: %s", filepath)
        notify.critical(app, "エラー", f"保存に失敗しました:\n{e}")


def manual_load(app):
    if not app.confirm_unsaved_changes("別のプロジェクトを開く"):
        return
    filepath, _ = notify.get_open_file_name(
        app, "プロジェクトを開く", "", "Project Files (*.graphica *.pkl)"
    )
    if filepath:
        app._load_project_from_path(filepath)


def load_project_from_path(app, filepath, add_to_recent=True):
    """add_to_recent=False はオートセーブからの復元。最近使ったファイルに載せず、上書き保存の対象にもしない。"""
    try:
        app.project.load_project(filepath)
        # 中身はもう入れ替わっている。この先で失敗したとき前のファイルが保存先に
        # 残っていると、上書き保存でそのファイルを別の内容で壊してしまう。
        app._current_project_path = None
        app._saved_content_fingerprint = None
        app._restored_unsaved = False

        app._rebuild_dataset_tree_widget()

        app._block_all_signals(True)
        app.subplot_rows_spinbox.setValue(app.project.layout_rows)
        app.subplot_cols_spinbox.setValue(app.project.layout_cols)
        is_free_layout = getattr(app.project, 'layout_mode', 'grid') == 'free'
        app.free_layout_checkbox.setChecked(is_free_layout)
        app.subplot_rows_spinbox.setEnabled(not is_free_layout)
        app.subplot_cols_spinbox.setEnabled(not is_free_layout)
        app.add_free_subplot_button.setEnabled(is_free_layout)
        app.remove_free_subplot_button.setEnabled(is_free_layout)
        app.layout_edit_action.setEnabled(is_free_layout)
        if not is_free_layout and app.layout_edit_action.isChecked():
            app.layout_edit_action.setChecked(False)
            app._toggle_layout_edit_mode(False)
        app.panel_labels_action.setChecked(app.project.panel_labels_enabled)
        app.share_x_checkbox.setChecked(getattr(app.project, 'share_x_axis', False))
        app.share_y_checkbox.setChecked(getattr(app.project, 'share_y_axis', False))
        app.share_x_checkbox.setEnabled(not is_free_layout)
        app.share_y_checkbox.setEnabled(not is_free_layout)
        app._block_all_signals(False)

        if app.project.all_plot_settings:
            app._apply_settings_to_ui_controls(
                app.project.all_plot_settings[app.project.active_axis_index]
            )

        # 前の文書へのコマンドは datasets をリストごと差し戻すので、残すと
        # Undo 1回で読み込んだ内容が前の文書に置き換わる。
        app.undo_stack.clear()

        app.property_panel.update_ui_state()
        app._update_plot()

        app.statusBar().showMessage("プロジェクトを読み込みました", 3000)
        if add_to_recent:
            app._add_recent_file(filepath)
            app._current_project_path = filepath
            app._remember_saved_content()
        else:
            app._restored_unsaved = True
        app.project_state_changed.emit()
    except Exception as e:
        logger.exception("プロジェクトの読み込みに失敗しました: %s", filepath)
        notify.critical(app, "エラー", f"読み込みに失敗しました:\n{e}")


def get_recent_files(app):
    return app_settings.as_list_keeping_empty_string(app_settings.RECENT_FILES.read(app.settings))


def add_recent_file(app, file_path):
    file_path = os.path.abspath(file_path)
    files = app._get_recent_files()
    if file_path in files:
        files.remove(file_path)
    files.insert(0, file_path)
    files = files[:MAX_RECENT_FILES]
    app_settings.RECENT_FILES.write(app.settings, files)
    app._update_recent_files_menu()


def update_recent_files_menu(app):
    try:
        app.recent_files_menu.clear()
        files = app._get_recent_files()

        if not files:
            empty_action = app.recent_files_menu.addAction("(履歴なし)")
            empty_action.setEnabled(False)
            return

        for file_path in files:
            action = app.recent_files_menu.addAction(file_path)
            action.triggered.connect(lambda checked=False, p=file_path: app._on_open_recent_file(p))

        app.recent_files_menu.addSeparator()
        clear_action = app.recent_files_menu.addAction("履歴をクリア")
        clear_action.triggered.connect(app._on_clear_recent_files)
    except RuntimeError:
        # まれにメニューの C++ 側が破棄済みのことがある(PySide6 の回収、原因は未特定)。表示が古いだけなので落とさない
        logger.warning("recent_files_menuの更新に失敗しました(既に破棄されている可能性があります)。", exc_info=True)


def on_open_recent_file(app, file_path):
    if not os.path.exists(file_path):
        notify.warning(app, "エラー", f"ファイルが見つかりません:\n{file_path}")
        files = app._get_recent_files()
        if file_path in files:
            files.remove(file_path)
            app_settings.RECENT_FILES.write(app.settings, files)
            app._update_recent_files_menu()
        return

    if file_path.lower().endswith(('.graphica', '.pkl')):
        if not app.confirm_unsaved_changes("別のプロジェクトを開く"):
            return
        app._load_project_from_path(file_path)
    else:
        app.load_data(file_path)


def on_clear_recent_files(app):
    app_settings.RECENT_FILES.write(app.settings, [])
    app._update_recent_files_menu()
