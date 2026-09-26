"""データセットをタブの外とやり取りする本体: データ表の書き出し、別のタブへのコピー・移動、スタイルのコピー、元ファイルからの再読み込み。"""
import copy
import logging
import os
import re
import uuid

import pandas as pd
from PySide6.QtWidgets import QApplication

from graphica.gui import notify
from graphica.core.methods_text import generate_methods_text
from graphica.gui.datasets.operations.runner import Operation

logger = logging.getLogger(__name__)

# スタイルのコピーで写す見た目の属性。data_kind/z_col_name は「どの列を使うか」という構造の選択なので含めない
# (写すと相手を意図せず2Dマップ扱いにしてしまう)。
STYLE_ATTRS = ('plot_type', 'color', 'linestyle', 'linewidth', 'marker', 'markersize', 'smoothing',
               'smoothing_method', 'alpha',
               'error_display', 'colormap', 'vmin', 'vmax', 'grid_interp_method')


def _write_failed(op, error):
    logger.exception("データセットの書き出しに失敗しました")
    op.stop_with_warning(f"ファイルの書き出しに失敗しました:\n{error}", title="書き出しエラー")


def _export_one(op, dataset):
    default_name = re.sub(r'[\\/:*?"<>|]', '_', dataset.name) or "dataset"
    file_path, selected_filter = notify.get_save_file_name(
        op.parent, "データ表を書き出す", default_name, "CSV Files (*.csv);;Excel Files (*.xlsx)"
    )
    if not file_path:
        op.stop()
    try:
        if file_path.lower().endswith('.xlsx') or "Excel" in selected_filter:
            if not file_path.lower().endswith('.xlsx'):
                file_path += '.xlsx'
            dataset.df.to_excel(file_path, index=False)
        else:
            if not file_path.lower().endswith('.csv'):
                file_path += '.csv'
            dataset.df.to_csv(file_path, index=False, encoding='utf-8-sig')
    except Exception as e:
        _write_failed(op, e)
    op.information(f"書き出しました:\n{file_path}", title="書き出し完了")


def _export_book(op, selected):
    file_path, _ = notify.get_save_file_name(op.parent, "データ表を書き出す", "datasets.xlsx", "Excel Files (*.xlsx)")
    if not file_path:
        op.stop()
    if not file_path.lower().endswith('.xlsx'):
        file_path += '.xlsx'
    used_sheet_names = set()
    try:
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            for dataset in selected:
                sheet_name = re.sub(r'[\\/:*?\[\]]', '_', dataset.name)[:31] or "Sheet"
                base_name, suffix = sheet_name, 1
                while sheet_name in used_sheet_names:
                    suffix += 1
                    sheet_name = f"{base_name[:28]}_{suffix}"
                used_sheet_names.add(sheet_name)
                dataset.df.to_excel(writer, sheet_name=sheet_name, index=False)
    except Exception as e:
        _write_failed(op, e)
    op.information(f"{len(selected)}件を書き出しました:\n{file_path}", title="書き出し完了")


def _export_folder(op, selected):
    dir_path = notify.get_existing_directory(op.parent, "書き出し先フォルダを選択")
    if not dir_path:
        op.stop()
    succeeded, failed = [], []
    used_names = set()
    for dataset in selected:
        base_name = re.sub(r'[\\/:*?"<>|]', '_', dataset.name) or "dataset"
        file_name, suffix = base_name, 1
        while file_name in used_names:
            suffix += 1
            file_name = f"{base_name}_{suffix}"
        used_names.add(file_name)
        try:
            dataset.df.to_csv(os.path.join(dir_path, f"{file_name}.csv"), index=False, encoding='utf-8-sig')
            succeeded.append(dataset.name)
        except Exception as e:
            failed.append(f"{dataset.name}: {e}")
    message = f"{len(succeeded)}件を書き出しました。"
    if failed:
        message += "\n\n失敗:\n" + "\n".join(failed)
    op.information(message, title="書き出し完了")


def export_data(op):
    """1件ならCSVかExcelの1ファイル、複数ならデータセットごとのCSVか、シートに分けた1つのExcelブックに書き出す。"""
    selected = op.selected_datasets(at_least=1)
    if len(selected) == 1:
        _export_one(op, selected[0])
        return

    format_choice, ok = notify.get_item(
        op.parent, "データ表を書き出す", "書き出し形式を選択してください:",
        ["CSV (データセットごとに別ファイル)", "Excel (1ブックにシート分け)"], 0, False
    )
    if not ok:
        op.stop()
    if format_choice.startswith("Excel"):
        _export_book(op, selected)
    else:
        _export_folder(op, selected)


def copy_or_move_to_tab(op, move):
    """
    選んだデータセットを複製して別のタブに足す(移動なら、足した後でこのタブから消す)。
    タブごとに Undo の履歴が別なので、相手のタブへの追加は Undo できない。移動を Undo しても
    このタブの削除だけが戻り、両方のタブにある状態になる。
    """
    selected = op.selected_datasets(at_least=1)
    sibling_tabs = op.host.sibling_tabs()
    if not sibling_tabs:
        op.stop_with_information("コピー/移動先の他のタブがありません。")

    tab_titles = [title for title, _ in sibling_tabs]
    action_label = "移動" if move else "コピー"
    choice, ok = notify.get_item(op.parent, f"別のタブへ{action_label}", "転送先のタブ:", tab_titles, 0, False)
    if not ok:
        op.stop()
    target = sibling_tabs[tab_titles.index(choice)][1]

    for dataset in selected:
        new_dataset = copy.deepcopy(dataset)
        new_dataset.dataset_id = uuid.uuid4().hex
        target.add_dataset(new_dataset, target.target_folder_for_new_dataset())

    if move:
        op.host.remove_datasets(selected, description=f"別のタブへ移動({len(selected)}件)")

    op.host.show_status(f"{len(selected)}件のデータセットを「{choice}」へ{action_label}しました")


def copy_style(op):
    """今のデータセットの見た目を値で控える(後で元を変えても控えは変わらない)。"""
    dataset = op.current_dataset()
    op.state.copied_style = {attr: getattr(dataset, attr) for attr in STYLE_ATTRS}
    op.host.show_status(f"「{dataset.name}」のスタイルをコピーしました")


def paste_style(op):
    """控えた見た目を選んだデータセットすべてに当てる(Undo 1回分)。"""
    copied_style = op.state.copied_style
    if copied_style is None:
        op.stop()
    selected_datasets = op.selected_datasets(at_least=1)

    with op.host.undo_macro(f"スタイルの貼り付け ({len(selected_datasets)}件)", enabled=len(selected_datasets) > 1):
        for dataset in selected_datasets:
            old_values = {attr: getattr(dataset, attr) for attr in STYLE_ATTRS}
            op.host.push_property_change(dataset, old_values, dict(copied_style), description="スタイルの貼り付け")


def reload_from_source(op):
    """
    元のファイルを読み直して df だけを差し替える。書式・注釈・使う列の選択はそのまま。
    取り込みウィザードでの調整(文字コード・区切り等)は保存していないので、自動判定で読み直す。
    使っている列が無くなっていたら何も変えずに止める。除外した行は古いデータの行番号なので消す。
    """
    dataset = op.current_dataset()
    if not dataset.source_file:
        op.stop()

    if not os.path.exists(dataset.source_file):
        op.stop_with_warning(f"元ファイルが見つかりません:\n{dataset.source_file}")

    from graphica.gui.workers import read_data_file, excel_engine_for
    try:
        if dataset.source_sheet:
            new_df = pd.read_excel(dataset.source_file, sheet_name=dataset.source_sheet,
                                   engine=excel_engine_for(dataset.source_file))
        else:
            new_df = read_data_file(dataset.source_file)
    except Exception as e:
        logger.exception("元ファイルからの再読み込みに失敗しました")
        op.stop_with_warning(f"ファイルの読み込みに失敗しました:\n{e}")

    required_columns = (
        dataset.x_col_name, dataset.y_col_name,
        dataset.x_err_col_name, dataset.y_err_col_name, dataset.point_label_col_name,
    )
    missing = [col for col in required_columns if col and col not in new_df.columns]
    if missing:
        op.stop_with_warning(
            "再読み込みしたファイルに、現在使用中の列が見つかりませんでした:\n"
            + "\n".join(missing)
            + "\n\nファイルの構造(列名/区切り文字/ヘッダー行など)が変わった可能性があります。"
            "「データセット追加」から改めてインポートし直すことをお勧めします。"
            "再読み込みは中止しました。"
        )

    old_values = {'df': dataset.df, 'masked_row_indices': list(dataset.masked_row_indices)}
    new_values = {'df': new_df, 'masked_row_indices': []}
    # DataFrame を含む辞書は == で比べられないので、変化の有無は確かめずに積む。
    op.host.push_property_change(dataset, old_values, new_values,
                                 f"「{dataset.name}」を再読み込み", skip_if_unchanged=False)
    op.host.show_status(f"「{dataset.name}」を元ファイルから再読み込みしました")


def copy_methods_text(op):
    """今のデータセットの処理履歴から「方法」節向けの説明文を作り、クリップボードに写す。"""
    dataset = op.current_dataset()
    if dataset.provenance is None:
        op.stop()
    QApplication.clipboard().setText(generate_methods_text(dataset, op.host.project))
    op.host.show_status("「方法」文をクリップボードにコピーしました")


TRANSFER_OPERATIONS = {
    "export_data": Operation("データ表を書き出す", export_data),
    "copy_to_tab": Operation("タブ間のデータセット転送", lambda op: copy_or_move_to_tab(op, move=False)),
    "move_to_tab": Operation("タブ間のデータセット転送", lambda op: copy_or_move_to_tab(op, move=True)),
    "copy_style": Operation("スタイルのコピー", copy_style),
    "paste_style": Operation("スタイルの貼り付け", paste_style),
    "reload_from_source": Operation("再読み込み", reload_from_source),
    "copy_methods_text": Operation("「方法」文のコピー", copy_methods_text),
}
