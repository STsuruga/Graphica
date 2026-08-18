# gui/mixins/dataset_mixin.py
"""
データセット (Dataset) の追加/削除/複製、プロパティ編集、フォルダ分け、
曲線フィット・ピーク検出、データエディタ連携をまとめた Mixin。

データセットリスト (self.ui.dataset_list_widget) は QTreeWidget であり、
データセットは「葉 (leaf)」、フォルダは「内部ノード」として表現される。
葉アイテムの Qt.ItemDataRole.UserRole には対応する Dataset オブジェクトそのものを、
フォルダには None を格納することで区別する (main_window.py の
_add_dataset_list_item / _add_dataset_folder_item 参照)。

「現在選択中の1件」や「選択中の全件」を取得する際は、行番号 (currentRow等) では
なく、main_window.py 側の _get_current_dataset() / _get_selected_datasets() を
経由する。これによりフォルダのネストがあっても正しくデータセットだけを扱える。
"""
import copy
import json
import logging
import os
import re
from datetime import datetime, timezone
import matplotlib as mpl
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QMessageBox, QColorDialog, QFileDialog, QInputDialog, QMenu,
                               QProgressDialog)

from core.analysis import (calculate_curve_fit, fit_curve_task, calculate_peak_quantification,
                           calculate_savgol,
                           calculate_baseline_als, calculate_baseline_polynomial,
                           calculate_baseline_rubberband, calculate_baseline_manual,
                           calculate_interval_integral, calculate_confidence_band,
                           calculate_resample_to_grid, multi_peak_fit_task)
from core.commands import SetDatasetPropertiesCommand, ReorderDatasetsCommand, SetAnnotationsCommand
from core.dataset import Dataset
from core.methods_text import generate_methods_text
from core.plugin_api import get_registered_importer_extensions
from core.plugin_types import AnalysisResult, PluginExecutionError
from core.safe_eval import safe_eval_column_formula
from gui.task_runner import TaskRunner
from gui.data_editor import DataEditorDialog
from gui.dialogs import (PeakSettingsDialog, FitDialog, ResultDialog, ColorPaletteDialog,
                         ColumnCalculatorDialog, DatasetArithmeticDialog, NewDatasetDialog,
                         NormalizeDatasetDialog, SavGolDialog, PluginParamDialog,
                         BaselineCorrectionDialog, IntervalIntegralDialog, ResampleDatasetDialog,
                         MultiPeakFitDialog)
from gui.dataset_style_icon import (
    make_dataset_style_icon, make_dataset_visibility_icon, apply_dataset_visibility_text_style,
    DATASET_TREE_VISIBILITY_COLUMN,
)
from gui.canvas import DEFAULT_POINT_LABEL_MAX_POINTS

logger = logging.getLogger(__name__)

# カスタム配色パレットをQSettingsに保存する際のキー
COLOR_PALETTES_SETTINGS_KEY = "custom_color_palettes_json"
ACTIVE_PALETTE_SETTINGS_KEY = "active_color_palette"

# エラーバー用の誤差列コンボボックスで「誤差列を使わない」ことを表す選択肢
NO_ERROR_COLUMN_LABEL = "(なし)"

# 「スタイルのコピー&ペースト」で複製対象とする、見た目に関する属性
# (凡例名・X/Y列・エラーバー列・描画先など、データ/構造に関わるものは含めない)。
# colormap/vmin/vmax/grid_interp_methodは2Dマップ(項目C-508)の見た目に関する
# 属性のため含めるが、data_kind/z_col_nameはX/Y列と同様に「どの列を使うか」という
# 構造の選択であり、他のデータセットへ無条件にコピーすると意図しない相手を
# 2Dグリッド扱いにしてしまうため、意図的に含めない。
STYLE_ATTRS = ('plot_type', 'color', 'linestyle', 'linewidth', 'marker', 'markersize', 'smoothing', 'alpha',
               'error_display', 'colormap', 'vmin', 'vmax', 'grid_interp_method')

# カラーマップからの自動配色(項目C-805)で選ばせる候補。連続データの系列を
# 表現するのに適した(知覚的に均一な、またはよく使われる)ものを厳選する。
RECOMMENDED_COLORMAPS = ['viridis', 'plasma', 'cividis', 'coolwarm', 'turbo', 'rainbow']

# データポイントラベルの「内容」コンボボックスで、Y値そのものを表示することを示す選択肢
POINT_LABEL_Y_VALUE_LABEL = "Y値"


class DatasetMixin:
    def _on_add_dataset(self):
        """「データセット追加」ボタンからの読み込み（Excel対応版）"""
        # ★ .xls と .xlsx をフィルターに追加
        # プラグインがregister_importer()(項目B-1)で登録した拡張子も追加する
        plugin_extensions = get_registered_importer_extensions()
        plugin_pattern = ''.join(f' *{ext}' for ext in plugin_extensions)
        file_path, _ = QFileDialog.getOpenFileName(
            self, "データファイルを選択", "",
            f"Data Files (*.csv *.txt *.xls *.xlsx{plugin_pattern});;All Files (*)"
        )
        if file_path:
            # 古い読み込み処理は捨てて、一番下にある load_data メソッドに処理を任せる
            self.load_data(file_path)

    def _on_create_new_dataset(self):
        """
        「新規データセット作成...」ボタンが押されたときの処理(項目63)。
        ファイル読み込みを介さず、名前・列名・初期行数を指定した空のDatasetを作成し、
        その場でデータエディタを開いて手入力できるようにする。
        """
        dialog = NewDatasetDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name = dialog.get_dataset_name()
        column_names = dialog.get_column_names()
        row_count = dialog.get_row_count()

        df = pd.DataFrame({col: [np.nan] * row_count for col in column_names})
        x_col_name = column_names[0]
        y_col_name = column_names[1] if len(column_names) > 1 else column_names[0]

        new_dataset = Dataset(name=name, df=df, x_col_name=x_col_name, y_col_name=y_col_name)
        self._add_dataset(new_dataset, self._get_target_folder_for_new_dataset())

        # 作成直後、そのままデータエディタを開いて手入力できるようにする
        self._on_show_data_editor()

    def _on_dataset_search_changed(self, text):
        """
        データセット検索ボックスの入力が変わるたびに呼ばれる。
        名前が検索文字列を含むデータセットだけを表示し、それ以外は非表示にする。
        フォルダは、中に一致するデータセットが1つでもあれば表示する
        (検索文字列が空のときはすべて表示する)。
        """
        query = text.strip().lower()

        def apply_filter(item):
            dataset = item.data(0, Qt.ItemDataRole.UserRole)
            if dataset is not None:
                visible = (not query) or (query in dataset.name.lower())
                item.setHidden(not visible)
                return visible
            else:
                any_child_visible = False
                for i in range(item.childCount()):
                    if apply_filter(item.child(i)):
                        any_child_visible = True
                item.setHidden(bool(query) and not any_child_visible)
                return any_child_visible or not query

        root = self.ui.dataset_list_widget.invisibleRootItem()
        for i in range(root.childCount()):
            apply_filter(root.child(i))

    def _on_new_folder(self):
        """
        「新しいフォルダ」ボタンが押されたときの処理。
        現在選択されているアイテムがフォルダなら、その子フォルダとして作成する
        (ネスト構造を作れる)。それ以外は最上位に作成する。
        """
        name, ok = QInputDialog.getText(self, "新しいフォルダ", "フォルダ名:", text="新しいフォルダ")
        if not ok or not name:
            return

        current_item = self.ui.dataset_list_widget.currentItem()
        parent_item = None
        if current_item is not None and current_item.data(0, Qt.ItemDataRole.UserRole) is None:
            parent_item = current_item # 選択中がフォルダなら、その子として作成

        self._add_dataset_folder_item(name, parent_item)

    def _on_rename_dataset_folder(self):
        """
        実機フィードバック(「データセットのフォルダ名編集」)。選択中のフォルダの
        名前を変更する。フォルダ構造自体はUndo/Redo管理の対象外(_on_new_folder
        によるフォルダ作成も同様に非対応)のため、リネームも同じ方針で扱う。
        _capture_dataset_group_tree()は保存の都度ツリーウィジェットの表示
        テキストを読み取って構築するだけなので、setText(0, ...)だけで
        永続化上も反映される。
        """
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None or current_item.data(0, Qt.ItemDataRole.UserRole) is not None:
            return  # データセット項目、または未選択なら対象外
        old_name = current_item.text(0)
        new_name, ok = QInputDialog.getText(self, "フォルダ名を変更", "新しいフォルダ名:", text=old_name)
        if not ok or not new_name:
            return
        current_item.setText(0, new_name)

    def _set_folder_datasets_visibility(self, folder_item, visible):
        """folder_item配下(再帰的に、サブフォルダも含む)の全データセットの
        表示/非表示をまとめて切り替える(項目C-907の一括版)。"""
        dataset_items = self._flatten_dataset_tree(folder_item)
        datasets = [item.data(0, Qt.ItemDataRole.UserRole) for item in dataset_items]
        if not datasets:
            return
        is_batch = len(datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"フォルダ内の表示/非表示切替 ({len(datasets)}件)")
        for ds in datasets:
            self._push_dataset_property_command(
                ds, {'visible': ds.visible}, {'visible': visible},
                description="データセットの表示/非表示切替"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_show_all_in_folder(self):
        """実機フィードバック(「フォルダの表示非表示追加」)。選択中のフォルダ内の
        全データセットを表示状態にする。"""
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None:
            return
        self._set_folder_datasets_visibility(current_item, True)

    def _on_hide_all_in_folder(self):
        """選択中のフォルダ内の全データセットを非表示状態にする。"""
        current_item = self.ui.dataset_list_widget.currentItem()
        if current_item is None:
            return
        self._set_folder_datasets_visibility(current_item, False)

    def _on_dataset_tree_context_menu(self, pos):
        """データセットツリーを右クリックしたときのコンテキストメニュー"""
        menu = QMenu(self)
        new_folder_action = menu.addAction("新しいフォルダ")
        new_folder_action.triggered.connect(self._on_new_folder)

        current_item = self.ui.dataset_list_widget.currentItem()
        is_folder_selected = (
            current_item is not None and current_item.data(0, Qt.ItemDataRole.UserRole) is None
        )
        if is_folder_selected:
            # 実機フィードバック: フォルダの名前変更、フォルダ内一括表示/非表示
            rename_folder_action = menu.addAction("フォルダ名を変更...")
            rename_folder_action.triggered.connect(self._on_rename_dataset_folder)

            show_all_action = menu.addAction("フォルダ内を全て表示")
            show_all_action.triggered.connect(self._on_show_all_in_folder)

            hide_all_action = menu.addAction("フォルダ内を全て非表示")
            hide_all_action.triggered.connect(self._on_hide_all_in_folder)

        if self._get_current_dataset() is not None:
            menu.addSeparator()
            copy_style_action = menu.addAction("スタイルをコピー")
            copy_style_action.triggered.connect(self._on_copy_dataset_style)

            paste_style_action = menu.addAction("スタイルを貼り付け")
            paste_style_action.setEnabled(self._copied_dataset_style is not None)
            paste_style_action.triggered.connect(self._on_paste_dataset_style)

            # 規格化(ノーマライズ、項目78): 曲線フィット/ピーク検出と同様、1つの
            # データセット(フォーカス中のカレントアイテム)に対する操作なので、
            # 複数選択かどうかに関わらずこのブロック(カレントデータセットが
            # 存在する場合)に置く。データセット間演算(2件選択が必須)とは異なる。
            normalize_action = menu.addAction("規格化(ノーマライズ)...")
            normalize_action.triggered.connect(self._on_normalize_dataset)

            # Savitzky-Golayフィルタ(平滑化/微分、項目C-301/C-302): 規格化と同じく
            # カレント1件のデータセットから新しいデータセットを1つ作る操作。
            savgol_action = menu.addAction("Savitzky-Golayフィルタ(平滑化/微分)...")
            savgol_action.triggered.connect(self._on_savgol_dataset)

            # ベースライン補正(ALS/多項式/ラバーバンド/手動点、項目C-308):
            # 上記と同じく「カレント1件から新しいデータセットを1つ作る」操作。
            baseline_action = menu.addAction("ベースライン補正...")
            baseline_action.triggered.connect(self._on_baseline_correction_dataset)

            # 区間積分(台形則/Simpson則、任意でベースライン差し引き、項目C-311):
            # 上記と同じく「カレント1件」を対象にするが、新しいデータセットではなく
            # 積分値(スカラー)をResultDialogで表示する点がSavitzky-Golay/
            # ベースライン補正と異なる(ピーク検出のResultDialog表示に近い)。
            integral_action = menu.addAction("区間積分(台形則/Simpson則)...")
            integral_action.triggered.connect(self._on_interval_integral_dataset)

            # フィット結果のエクスポート(項目C-413): カレントデータセットが
            # 曲線フィットの結果(dataset.fit_result、項目C-401で永続化)を
            # 持っている場合のみ有効にする。「スタイルを貼り付け」
            # (paste_style_action, 上記)と同じく、常時メニューには出すが
            # 対象外の状態ではグレーアウトするパターンに合わせる。
            # ハンドラ自身も fit_result が無い場合に備えて防御的にチェックする
            # (万一 setEnabled が効かない呼び出し経路があっても親切な警告を出す)。
            export_fit_action = menu.addAction("フィット結果のエクスポート...")
            export_fit_action.setEnabled(self._get_current_dataset().fit_result is not None)
            export_fit_action.triggered.connect(self._on_export_fit_result)

            # 共通X格子へのリサンプリング/補間(項目C-305): 上記のSavitzky-Golay/
            # ベースライン補正と同じく「カレント1件から新しいデータセットを1つ作る」操作。
            resample_action = menu.addAction("共通X格子へのリサンプリング/補間...")
            resample_action.triggered.connect(self._on_resample_dataset)

            # 「方法」文の自動生成(項目C-1102): カレントデータセットが処理履歴
            # (dataset.provenance、項目C-1101)を持っている場合のみ有効にする
            # (export_fit_actionと同じ、常時メニューには出すが対象外の状態では
            # グレーアウトするパターン)。元データ(provenance無し)には
            # 生成する意味のある「方法」が無いため対象外。
            copy_methods_text_action = menu.addAction("「方法」文をコピー...")
            copy_methods_text_action.setEnabled(self._get_current_dataset().provenance is not None)
            copy_methods_text_action.triggered.connect(self._on_copy_methods_text)

        selected_count = len(self._get_selected_datasets())
        if selected_count >= 2:
            menu.addSeparator()
            if selected_count == 2:
                arithmetic_action = menu.addAction("データセット間演算...")
                arithmetic_action.triggered.connect(self._on_dataset_arithmetic)

            batch_calc_action = menu.addAction("バッチ列計算...")
            batch_calc_action.triggered.connect(self._on_batch_column_calculate)

            batch_fit_action = menu.addAction("バッチカーブフィット...")
            batch_fit_action.triggered.connect(self._on_batch_curve_fit)

        if self._get_selected_datasets():
            menu.addSeparator()
            export_data_action = menu.addAction("データ表をファイルに書き出す...")
            export_data_action.triggered.connect(self._on_export_dataset_data)

        if self.ui.dataset_list_widget.selectedItems():
            menu.addSeparator()
            remove_action = menu.addAction("削除")
            remove_action.triggered.connect(self._on_remove_dataset)

        menu.exec(self.ui.dataset_list_widget.viewport().mapToGlobal(pos))

    def _on_export_dataset_data(self):
        """
        「データ表をファイルに書き出す...」メニューの処理。
        グラフ画像ではなく、加工済みのデータセットそのもの(DataFrame)を
        他のソフト(Excel等)で使えるようファイル出力する。
        1件選択時はCSVまたはExcelのファイルを直接選ばせ、複数選択時は
        フォルダを選ばせて各データセットを別々のCSVとして書き出すか、
        1つのExcelブックにシート分けしてまとめるかを選ばせる。
        """
        selected = self._get_selected_datasets()
        if not selected:
            return

        if len(selected) == 1:
            dataset = selected[0]
            default_name = re.sub(r'[\\/:*?"<>|]', '_', dataset.name) or "dataset"
            file_path, selected_filter = QFileDialog.getSaveFileName(
                self, "データ表を書き出す", default_name,
                "CSV Files (*.csv);;Excel Files (*.xlsx)"
            )
            if not file_path:
                return
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
                QMessageBox.warning(self, "書き出しエラー", f"ファイルの書き出しに失敗しました:\n{e}")
                return
            QMessageBox.information(self, "書き出し完了", f"書き出しました:\n{file_path}")
            return

        # --- 複数選択時 ---
        format_choice, ok = QInputDialog.getItem(
            self, "データ表を書き出す", "書き出し形式を選択してください:",
            ["CSV (データセットごとに別ファイル)", "Excel (1ブックにシート分け)"], 0, False
        )
        if not ok:
            return

        if format_choice.startswith("Excel"):
            file_path, _ = QFileDialog.getSaveFileName(
                self, "データ表を書き出す", "datasets.xlsx", "Excel Files (*.xlsx)"
            )
            if not file_path:
                return
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
                QMessageBox.warning(self, "書き出しエラー", f"ファイルの書き出しに失敗しました:\n{e}")
                return
            QMessageBox.information(self, "書き出し完了", f"{len(selected)}件を書き出しました:\n{file_path}")
        else:
            dir_path = QFileDialog.getExistingDirectory(self, "書き出し先フォルダを選択")
            if not dir_path:
                return
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
            QMessageBox.information(self, "書き出し完了", message)

    def _on_copy_dataset_style(self):
        """
        「スタイルをコピー」メニューが選ばれたときの処理。
        現在カレントのデータセット1件から、見た目に関する属性(STYLE_ATTRS)だけを
        値としてコピーしておく(オブジェクト参照ではなく値のコピーなので、
        コピー元を後から変更してもコピー内容には影響しない)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return
        self._copied_dataset_style = {attr: getattr(dataset, attr) for attr in STYLE_ATTRS}
        self.statusBar().showMessage(f"「{dataset.name}」のスタイルをコピーしました", 3000)

    def _on_paste_dataset_style(self):
        """
        「スタイルを貼り付け」メニューが選ばれたときの処理。
        コピーしておいたスタイルを、選択中の(複数可)データセットにまとめて適用する。
        複数選択時は1回のUndo/Redoでまとめて元に戻せるようにする。
        """
        if self._copied_dataset_style is None:
            return
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"スタイルの貼り付け ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            old_values = {attr: getattr(dataset, attr) for attr in STYLE_ATTRS}
            self._push_dataset_property_command(
                dataset, old_values, dict(self._copied_dataset_style),
                description="スタイルの貼り付け"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_dataset_arithmetic(self):
        """
        「データセット間演算...」メニューの処理。
        選択中のちょうど2つのデータセット(A, B)について、B側のY値をA側のX値に
        線形補間してから差・和・積・商を計算し、新しいデータセットとして追加する。
        2つのデータセットのX軸が完全には一致しないケースを想定している。
        """
        selected = self._get_selected_datasets()
        if len(selected) != 2:
            QMessageBox.information(self, "データセット間演算", "演算対象として、データセットをちょうど2つ選択してください。")
            return
        ds_a, ds_b = selected[0], selected[1]

        dialog = DatasetArithmeticDialog(ds_a.name, ds_b.name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        operation, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self, "入力エラー", "出力データセット名が空です。")
            return

        xa = np.asarray(ds_a.x_data, dtype=float)
        ya = np.asarray(ds_a.y_data, dtype=float)
        xb = np.asarray(ds_b.x_data, dtype=float)
        yb = np.asarray(ds_b.y_data, dtype=float)

        valid_a = ~(np.isnan(xa) | np.isnan(ya))
        valid_b = ~(np.isnan(xb) | np.isnan(yb))
        xa, ya = xa[valid_a], ya[valid_a]
        xb, yb = xb[valid_b], yb[valid_b]

        if len(xa) == 0 or len(xb) == 0:
            QMessageBox.warning(self, "データセット間演算", "有効なデータ点がありません。")
            return

        lo, hi = max(np.min(xa), np.min(xb)), min(np.max(xa), np.max(xb))
        if lo > hi:
            QMessageBox.warning(self, "データセット間演算", "2つのデータセットのX軸の範囲が重なっていないため演算できません。")
            return

        mask = (xa >= lo) & (xa <= hi)
        xa_sub, ya_sub = xa[mask], ya[mask]
        if len(xa_sub) == 0:
            QMessageBox.warning(self, "データセット間演算", "重なる範囲にA側のデータ点がありません。")
            return

        order_b = np.argsort(xb)
        yb_interp = np.interp(xa_sub, xb[order_b], yb[order_b])

        if operation == "A - B":
            result = ya_sub - yb_interp
        elif operation == "B - A":
            result = yb_interp - ya_sub
        elif operation == "A + B":
            result = ya_sub + yb_interp
        elif operation == "A × B":
            result = ya_sub * yb_interp
        elif operation == "A ÷ B":
            with np.errstate(divide='ignore', invalid='ignore'):
                result = ya_sub / yb_interp
        else:  # "B ÷ A"
            with np.errstate(divide='ignore', invalid='ignore'):
                result = yb_interp / ya_sub

        result_df = pd.DataFrame({'x': xa_sub, 'y': result})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=self._build_provenance('arithmetic', {'operation_symbol': operation}, [ds_a, ds_b]),
        )
        self._add_dataset(new_dataset, self._get_target_folder_for_new_dataset())
        self.statusBar().showMessage(f"「{output_name}」を追加しました", 3000)

    def _on_normalize_dataset(self):
        """
        「規格化(ノーマライズ)...」メニューの処理(項目78)。
        カレントの(フォーカス中の)1つのデータセットについて、Y値を
        最大値基準または特定X値での強度基準で規格化し、新しいデータセットとして
        追加する。元のデータセットは変更しない(非破壊)。

        単一/複数選択の扱いについて: データセット間演算(_on_dataset_arithmetic)は
        「ちょうど2件」の選択を要求するが、規格化は曲線フィット(_on_fit_curve)や
        ピーク検出(_on_find_peaks)と同じく「1つのデータセットから新しいデータセットを
        1つ作る」操作であるため、それらと同様に _get_selected_datasets() ではなく
        _get_current_dataset() (フォーカス中の1件)を対象にする。これにより、
        複数選択中でも常にカレントアイテム1件に対して迷いなく動作する。
        """
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) == 0:
            QMessageBox.warning(self, "規格化(ノーマライズ)", "有効なデータ点がありません。")
            return

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = NormalizeDatasetDialog(original_dataset.name, x_min=x_min, x_max=x_max, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, reference_x, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self, "入力エラー", "出力データセット名が空です。")
            return

        if mode == NormalizeDatasetDialog.MODE_MAX:
            reference_value = float(np.max(y_data))
        else:
            if reference_x < x_min or reference_x > x_max:
                QMessageBox.warning(
                    self, "規格化(ノーマライズ)",
                    f"指定されたX値 ({reference_x}) がデータセットのX軸範囲 "
                    f"({x_min} 〜 {x_max}) の外にあるため、規格化できません。"
                )
                return
            order = np.argsort(x_data)
            reference_value = float(np.interp(reference_x, x_data[order], y_data[order]))

        if abs(reference_value) < 1e-12:
            QMessageBox.warning(self, "規格化(ノーマライズ)", "基準値が0に近すぎるため、規格化できません。")
            return

        result_df = pd.DataFrame({'x': x_data, 'y': y_data / reference_value})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=self._build_provenance(
                'normalize',
                {'mode': mode, 'reference_x': reference_x, 'reference_value': reference_value},
                [original_dataset],
            ),
        )
        self._add_dataset(new_dataset, self._get_target_folder_for_new_dataset())
        self.statusBar().showMessage(f"「{output_name}」を追加しました", 3000)

    def _on_savgol_dataset(self):
        """
        「Savitzky-Golayフィルタ(平滑化/微分)...」メニューの処理(項目C-301/C-302)。
        カレントの1つのデータセットに対して平滑化(deriv=0)または微分
        (deriv=1/2)を行い、新しいデータセットとして追加する(非破壊)。
        _on_normalize_dataset と同じ「カレント1件」パターン。
        """
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 3:
            QMessageBox.warning(self, "Savitzky-Golayフィルタ", "有効なデータ点が不足しています。")
            return

        dialog = SavGolDialog(original_dataset.name, max_window=len(x_data), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        window_length, polyorder, deriv, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self, "入力エラー", "出力データセット名が空です。")
            return

        try:
            x_sorted, y_result = calculate_savgol(x_data, y_data, window_length, polyorder, deriv=deriv)
        except ValueError as e:
            QMessageBox.warning(self, "Savitzky-Golayフィルタ", str(e))
            return

        result_df = pd.DataFrame({'x': x_sorted, 'y': y_result})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=self._build_provenance(
                'savgol',
                {'window_length': window_length, 'polyorder': polyorder, 'deriv': deriv},
                [original_dataset],
            ),
        )
        self._add_dataset(new_dataset, self._get_target_folder_for_new_dataset())
        self.statusBar().showMessage(f"「{output_name}」を追加しました", 3000)

    def _on_baseline_correction_dataset(self):
        """
        「ベースライン補正...」メニューの処理(項目C-308)。
        カレントの1つのデータセットに対してALS/多項式/ラバーバンド/手動点の
        いずれかの手法でベースラインを推定し、ベースライン差し引き後のデータを
        新しいデータセットとして追加する(非破壊)。_on_savgol_dataset/
        _on_normalize_datasetと同じ「カレント1件」パターン。
        ダイアログで「ベースライン曲線も追加する」が有効な場合は、推定した
        ベースライン自体も別データセットとして追加する(任意、既定は追加しない)。
        """
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 3:
            QMessageBox.warning(self, "ベースライン補正", "有効なデータ点が不足しています。")
            return

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = BaselineCorrectionDialog(original_dataset.name, x_min=x_min, x_max=x_max, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method, params, output_name, add_baseline_dataset = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self, "入力エラー", "出力データセット名が空です。")
            return

        try:
            if method == "als":
                x_sorted, baseline, corrected = calculate_baseline_als(x_data, y_data, **params)
            elif method == "polynomial":
                x_sorted, baseline, corrected = calculate_baseline_polynomial(x_data, y_data, **params)
            elif method == "rubberband":
                x_sorted, baseline, corrected = calculate_baseline_rubberband(x_data, y_data)
            else:  # "manual"
                # アンカー点のX座標はダイアログでは自由記入のテキストのまま
                # 受け取っており(BaselineCorrectionDialog.get_settings参照)、
                # ここで数値パースする。書式エラーもcalculate_baseline_manualの
                # 入力エラーと同じ警告ダイアログにまとめて表示する。
                anchor_text = params["anchor_x_text"]
                try:
                    anchor_x = [
                        float(token) for token in anchor_text.replace("\n", ",").split(",")
                        if token.strip()
                    ]
                except ValueError:
                    raise ValueError("アンカー点のX座標は数値をカンマ区切りで入力してください。")
                x_sorted, baseline, corrected = calculate_baseline_manual(
                    x_data, y_data, anchor_x=anchor_x, method=params["method"]
                )
        except ValueError as e:
            QMessageBox.warning(self, "ベースライン補正", str(e))
            return

        result_df = pd.DataFrame({'x': x_sorted, 'y': corrected})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=self._build_provenance(f'baseline_{method}', dict(params), [original_dataset]),
        )
        self._add_dataset(new_dataset, self._get_target_folder_for_new_dataset())

        if add_baseline_dataset:
            baseline_df = pd.DataFrame({'x': x_sorted, 'y': baseline})
            baseline_dataset = Dataset(
                name=f"{output_name}_baseline", df=baseline_df, x_col_name='x', y_col_name='y'
            )
            self._add_dataset(baseline_dataset, self._get_target_folder_for_new_dataset())

        self.statusBar().showMessage(f"「{output_name}」を追加しました", 3000)

    def _on_interval_integral_dataset(self):
        """
        「区間積分(台形則/Simpson則)...」メニューの処理(項目C-311)。
        カレントの1つのデータセットについて、指定したXの範囲でYを台形則または
        Simpson則で定積分する。_on_savgol_dataset/_on_baseline_correction_dataset
        と同じ「カレント1件」パターンだが、結果は新しいデータセットではなく
        スカラー1個(積分値)のため、ピーク検出(_on_find_peaks)と同じく
        非モーダル・スクロール可能なResultDialogで結果を表示する。
        """
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 2:
            QMessageBox.warning(self, "区間積分", "有効なデータ点が不足しています(最低2点必要)。")
            return

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = IntervalIntegralDialog(original_dataset.name, x_min=x_min, x_max=x_max, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method, x_range, subtract_baseline = dialog.get_settings()

        try:
            result = calculate_interval_integral(
                x_data, y_data, x_range, method=method, subtract_baseline=subtract_baseline
            )
        except ValueError as e:
            QMessageBox.warning(self, "区間積分", str(e))
            return

        method_label = "台形則(Trapezoidal)" if method == "trapezoid" else "Simpson則"
        result_text = f"[{original_dataset.name}] の区間積分結果:\n"
        result_text += f"  積分方法: {method_label}\n"
        result_text += f"  積分範囲: {x_range[0]: .6g} 〜 {x_range[1]: .6g}\n"
        result_text += f"  ベースライン差し引き: {'あり(範囲両端を結ぶ直線)' if subtract_baseline else 'なし'}\n"
        result_text += f"  使用データ点数: {result['n_points']}\n"
        result_text += f"  積分値 = {result['integral']: .6e}\n"

        # ★ グラフを見ながら結果を確認できるよう、非モーダル・スクロール可能なダイアログで表示する
        # (_on_find_peaks/_on_fit_curveと同じ方針)
        if self.integral_result_dialog is not None:
            self.integral_result_dialog.close()
        integral_csv_data = pd.DataFrame({
            'X': result['x_used'],
            'Y(元データ)': result['y_raw_used'],
            'Y(積分に使用)': result['y_used'],
        })
        self.integral_result_dialog = ResultDialog(
            "区間積分完了", result_text, self, csv_data=integral_csv_data
        )
        self.integral_result_dialog.show()

    def _on_resample_dataset(self):
        """
        「共通X格子へのリサンプリング/補間...」メニューの処理(項目C-305)。

        カレントの1つのデータセットのY値を、別のX格子(他のロード済み
        データセットのX格子、または等間隔グリッド)へ線形/3次スプライン補間で
        リサンプリングし、新しいデータセットとして追加する(非破壊)。
        _on_savgol_dataset/_on_baseline_correction_datasetと同じ「カレント1件」
        パターン。

        _on_dataset_arithmetic (「データセット間演算...」) は2データセットの
        重なる範囲のみを対象に線形補間だけを内部で行う限定版だが、これは
        任意のtarget_x・線形/3次スプライン・外挿あり/なしを選べる一般版
        (core.analysis.calculate_resample_to_grid)であり、_on_dataset_arithmetic
        自体は変更しない(既存の動作・テストに触れないため)。
        """
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 2:
            QMessageBox.warning(self, "共通X格子へのリサンプリング/補間", "有効なデータ点が不足しています(最低2点必要)。")
            return

        other_dataset_names = [
            ds.name for ds in self.project.datasets if ds is not original_dataset
        ]

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = ResampleDatasetDialog(
            original_dataset.name, other_dataset_names, x_min=x_min, x_max=x_max, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source, params, method, extrapolate, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self, "入力エラー", "出力データセット名が空です。")
            return

        if source == "dataset":
            target_dataset_name = params["dataset_name"]
            target_dataset = next(
                (ds for ds in self.project.datasets
                 if ds is not original_dataset and ds.name == target_dataset_name),
                None
            )
            if target_dataset is None:
                QMessageBox.warning(
                    self, "共通X格子へのリサンプリング/補間",
                    "リサンプリング先のデータセットを選択してください。"
                )
                return
            target_x = np.asarray(target_dataset.x_data, dtype=float)
            target_x = target_x[~np.isnan(target_x)]
            if len(target_x) == 0:
                QMessageBox.warning(
                    self, "共通X格子へのリサンプリング/補間",
                    f"「{target_dataset_name}」に有効なX値がありません。"
                )
                return
        else:  # "linspace"
            start, stop, num_points = params["start"], params["stop"], params["num_points"]
            if start == stop:
                QMessageBox.warning(
                    self, "共通X格子へのリサンプリング/補間", "開始Xと終了Xが同じ値です。"
                )
                return
            target_x = np.linspace(start, stop, num_points)

        try:
            result_y = calculate_resample_to_grid(
                x_data, y_data, target_x, method=method, extrapolate=extrapolate
            )
        except ValueError as e:
            QMessageBox.warning(self, "共通X格子へのリサンプリング/補間", str(e))
            return

        # target_xは(dataset経由の場合)ソート済み・重複除去済みとは限らないため、
        # 出力データセットのXの並びとしてはtarget_xの並び順をそのまま使う
        # (calculate_savgol等と異なり「Xの昇順に正規化する」責務はここにはない —
        # ユーザーが選んだ格子の並び順をそのまま尊重する)。
        result_df = pd.DataFrame({'x': target_x, 'y': result_y})
        provenance_sources = [original_dataset] + ([target_dataset] if source == "dataset" else [])
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=self._build_provenance(
                'resample', {'source': source, 'method': method, 'extrapolate': extrapolate},
                provenance_sources,
            ),
        )
        self._add_dataset(new_dataset, self._get_target_folder_for_new_dataset())
        self.statusBar().showMessage(f"「{output_name}」を追加しました", 3000)

    def _on_run_plugin_processor(self, processor):
        """
        プラグインの「データ処理」メニュー項目が選択されたときの処理(項目C-1)。
        カレントの1つのデータセットに対して processor.fn を実行し、返された
        新しいDatasetを非破壊に追加する。既存の規格化/Savitzky-Golayとは異なり、
        _add_dataset_with_undo() 経由でAddDatasetCommandをpushするため、
        追加した直後にUndoで取り消せる(プラグイン側はUndoを一切意識しない)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            QMessageBox.information(self, processor.name, "データセットを選択してください。")
            return

        params = {}
        if processor.param_schema:
            dialog = PluginParamDialog(processor.name, processor.param_schema, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            params = dialog.get_values()

        try:
            new_dataset = processor.fn(dataset, params)
            if not isinstance(new_dataset, Dataset):
                raise TypeError(f"Datasetを返しませんでした(型: {type(new_dataset).__name__})。")
        except Exception as e:
            QMessageBox.critical(
                self, "データ処理エラー",
                str(PluginExecutionError(processor.plugin_name, f"「{processor.name}」の実行に失敗しました: {e}"))
            )
            return

        # 生成元プラグインをメタデータとして残す(項目C-3)
        new_dataset.source_plugin = processor.plugin_name
        self._add_dataset_with_undo(
            new_dataset, self._get_target_folder_for_new_dataset(),
            description=f"データ処理: {processor.name}"
        )
        self.statusBar().showMessage(f"「{new_dataset.name}」を追加しました", 3000)

    def _on_run_plugin_analyzer(self, analyzer):
        """
        プラグインの「解析」メニュー項目が選択されたときの処理(項目C-2)。
        analyzer.fn が返す AnalysisResult (表・注釈・派生データセット) を、
        それぞれ既存の表示/Undo経路にそのまま反映する
        (7章-7準拠: 結果は文字列ではなく構造化データとして保持する)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            QMessageBox.information(self, analyzer.name, "データセットを選択してください。")
            return

        params = {}
        if analyzer.param_schema:
            dialog = PluginParamDialog(analyzer.name, analyzer.param_schema, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            params = dialog.get_values()

        try:
            result = analyzer.fn(dataset, params)
            if not isinstance(result, AnalysisResult):
                raise TypeError(f"AnalysisResultを返しませんでした(型: {type(result).__name__})。")
        except Exception as e:
            QMessageBox.critical(
                self, "解析エラー",
                str(PluginExecutionError(analyzer.plugin_name, f"「{analyzer.name}」の実行に失敗しました: {e}"))
            )
            return

        if result.new_datasets:
            target_folder = self._get_target_folder_for_new_dataset()
            for new_dataset in result.new_datasets:
                new_dataset.source_plugin = analyzer.plugin_name  # 項目C-3
                self._add_dataset_with_undo(
                    new_dataset, target_folder, description=f"解析による追加: {analyzer.name}"
                )

        if result.annotations:
            active_index = self.project.active_axis_index
            if active_index < len(self.project.all_plot_settings):
                old_annotations = list(self.project.all_plot_settings[active_index].get('annotations', []))
                new_annotations = old_annotations + list(result.annotations)
                command = SetAnnotationsCommand(
                    self.project, active_index, old_annotations, new_annotations,
                    self._update_plot_appearance, description=f"解析による注釈追加: {analyzer.name}"
                )
                self.undo_stack.push(command)

        if result.table is not None:
            if self.plugin_analysis_result_dialog is not None:
                self.plugin_analysis_result_dialog.close()
            self.plugin_analysis_result_dialog = ResultDialog(
                analyzer.name, f"[{analyzer.name}] の解析結果", self, csv_data=result.table
            )
            self.plugin_analysis_result_dialog.show()

        self.statusBar().showMessage(f"「{analyzer.name}」を実行しました", 3000)

    def _on_batch_column_calculate(self):
        """
        「バッチ列計算...」メニューの処理。
        選択中の複数データセットに、同じ計算式(safe_eval_column_formula)を一括で適用する。
        列計算は既存の _on_calculate_column (data_editor.py) と同様、
        Undo/Redoスタックを経由しない (df を直接書き換える) 点に注意。
        """
        selected = self._get_selected_datasets()
        if len(selected) < 2:
            QMessageBox.information(self, "バッチ列計算", "2つ以上のデータセットを選択してください。")
            return

        # 計算式の候補として、選択中の全データセットに共通する列名を提示する
        common_columns = set(selected[0].df.columns)
        for ds in selected[1:]:
            common_columns &= set(ds.df.columns)

        dialog = ColumnCalculatorDialog(sorted(str(c) for c in common_columns), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_col, formula = dialog.get_formula()
        if not output_col or not formula:
            QMessageBox.warning(self, "入力エラー", "出力列または計算式が空です。")
            return

        succeeded, failed = [], []
        for dataset in selected:
            try:
                dataset.df[output_col] = safe_eval_column_formula(dataset.df, formula)
                dataset.invalidate_visible_df_cache()
                succeeded.append(dataset.name)
            except Exception as e:
                failed.append(f"{dataset.name}: {e}")

        self._update_ui_state()
        self._update_plot()

        message = f"{len(succeeded)}件のデータセットに適用しました。"
        if failed:
            message += "\n\n失敗:\n" + "\n".join(failed)
        QMessageBox.information(self, "バッチ列計算", message)

    def _on_batch_curve_fit(self):
        """
        「バッチカーブフィット...」メニューの処理(項目C-004フェーズ2で
        バックグラウンドスレッド化)。選択中の複数データセットそれぞれに、
        同じフィット関数(FitDialogで1回だけ選択)を適用し、成功したものごとに
        "Fit (元の名前)" というデータセットを追加する。

        ★ 以前はループ内で1件ずつ_add_dataset()(内部で毎回_update_plot()を
        呼ぶ)を呼んでおり、N件のフィットでN回のフル再描画が起きていた。
        フェーズ2では全件の計算をバックグラウンドスレッド(_batch_fit_worker)
        で行い、成功結果をメインスレッド側でまとめて追加してから
        _update_plot()を1回だけ呼ぶことでこの問題を解消する
        (この修正自体はC-003の有無に関係なく単独で価値がある)。
        QProgressDialogでキャンセル可能にする(初のUI進捗表示)。
        """
        selected = self._get_selected_datasets()
        if len(selected) < 2:
            QMessageBox.information(self, "バッチカーブフィット", "2つ以上のデータセットを選択してください。")
            return
        if self._batch_fit_task_runner is not None:
            QMessageBox.information(self, "実行中", "別のバッチフィット処理が実行中です。完了までお待ちください。")
            return

        # 項目C-402(重み付け)/C-404(フィット範囲)/C-403(初期値上書き・固定・
        # 範囲拘束)/C-405(信頼帯・予測帯)は選択中の全データセットに共通の設定
        # として1回だけ選ばせ、各データセットに同じ条件で適用する。
        (fit_type, custom_formula, use_weighted, x_range,
         p0_overrides, fixed_params, bounds, band_type) = FitDialog.get_fit_type(self)
        if fit_type is None:
            return

        target_folder = self._get_target_folder_for_new_dataset()

        progress_dialog = QProgressDialog("バッチカーブフィットを実行中...", "キャンセル", 0, len(selected), self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)

        runner = TaskRunner(
            self._batch_fit_worker, selected, fit_type, custom_formula, use_weighted, x_range,
            p0_overrides, fixed_params, bounds, band_type,
        )
        runner.progress.connect(lambda done, total, message: progress_dialog.setValue(done))
        progress_dialog.canceled.connect(runner.requestInterruption)
        runner.succeeded.connect(
            lambda results: self._on_batch_curve_fit_succeeded(results, target_folder, progress_dialog)
        )
        runner.failed.connect(lambda msg: self._on_batch_curve_fit_failed(msg, progress_dialog))
        self._batch_fit_task_runner = runner
        runner.start()

    def _cleanup_batch_fit_task_runner(self):
        if self._batch_fit_task_runner is not None:
            self._batch_fit_task_runner.wait()
            self._batch_fit_task_runner.deleteLater()
            self._batch_fit_task_runner = None

    def _on_batch_curve_fit_failed(self, error_message, progress_dialog):
        self._cleanup_batch_fit_task_runner()
        progress_dialog.close()
        QMessageBox.warning(self, "バッチカーブフィット", f"バッチフィット処理に失敗しました:\n{error_message}")

    def _on_batch_curve_fit_succeeded(self, results, target_folder, progress_dialog):
        """
        _batch_fit_worker() の結果(dataset_name/fit_dataset/errorのdictのリスト、
        キャンセル時は完了済み分のみ)をメインスレッド側で適用する。
        """
        self._cleanup_batch_fit_task_runner()
        progress_dialog.close()

        succeeded, failed = [], []
        for result in results:
            if result['fit_dataset'] is not None:
                self.project.datasets.append(result['fit_dataset'])
                self._add_dataset_list_item(result['fit_dataset'], target_folder)
                succeeded.append(result['source_name'])
            elif result['error'] is not None:
                failed.append(f"{result['source_name']}: {result['error']}")

        if succeeded:
            self._update_plot()  # ★ ループの外で1回だけ(フェーズ2の主眼)

        if not succeeded and not failed:
            return  # 1件も処理されないうちにキャンセルされた場合、通知不要

        message = f"{len(succeeded)}件のフィットに成功しました。"
        if failed:
            message += "\n\n失敗:\n" + "\n".join(failed)
        QMessageBox.information(self, "バッチカーブフィット", message)

    def _batch_fit_worker(self, datasets, fit_type, custom_formula, use_weighted, x_range,
                           p0_overrides, fixed_params, bounds, band_type,
                           report_progress=None, is_cancelled=None):
        """
        TaskRunnerからバックグラウンドスレッドで呼ばれる、バッチフィットの実計算部分。
        Qt/GUIオブジェクトには一切触れない(Datasetはプレーンなdataclassのため
        ここで安全に構築できる。_build_fit_result_dict/_add_band_columns_to_fit_df
        もstaticmethodで同様にQt非依存)。is_cancelled()はアイテム間でのみ
        チェックする(1件のcalculate_curve_fit自体は中断できないため、
        キャンセルの粒度は「バッチの残り未処理分をスキップする」まで)。
        """
        results = []
        total = len(datasets)
        for i, dataset in enumerate(datasets):
            if is_cancelled is not None and is_cancelled():
                break
            if report_progress is not None:
                report_progress(i, total, dataset.name)

            x_data, y_data = dataset.x_data, dataset.y_data
            sigma = dataset.y_err_data if use_weighted else None
            try:
                fit = calculate_curve_fit(
                    x_data, y_data, fit_type, custom_formula=custom_formula,
                    sigma=sigma, x_range=x_range,
                    p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds,
                )
            except Exception as e:
                results.append({'source_name': dataset.name, 'fit_dataset': None, 'error': str(e)})
                continue

            popt, params_info = fit['popt'], fit['param_names']
            x_fit, y_fit = fit['x_fit'], fit['y_fit']
            r_squared = fit['r_squared']

            fit_label = fit_type if custom_formula is None else f"{fit_type} {custom_formula}"
            result_text = f"[{fit_label}] のフィッティング結果:\n"
            for param_name, param_value in zip(params_info, popt):
                result_text += f"  {param_name} = {param_value: .4e}\n"
            result_text += f"  R^2 = {r_squared: .5f}\n"
            if sigma is not None:
                result_text += "  (Y誤差列を重みとして使用)\n"
            if x_range is not None:
                result_text += f"  (フィット範囲: {x_range[0]: .4g} 〜 {x_range[1]: .4g})\n"
            if fixed_params:
                result_text += f"  (固定: {fixed_params})\n"
            if bounds:
                result_text += f"  (範囲拘束: {bounds})\n"

            fit_result = self._build_fit_result_dict(
                fit_type=fit_type, custom_formula=custom_formula, fit=fit,
                weighted=sigma is not None, x_range=x_range,
                source_dataset=dataset,
                p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds,
            )

            fit_df = pd.DataFrame({'x_fit': x_fit, 'y_fit': y_fit})
            applied_band_type = self._add_band_columns_to_fit_df(fit_df, fit, band_type)
            fit_dataset = Dataset(
                name=f"Fit ({dataset.name})",
                df=fit_df,
                x_col_name='x_fit', y_col_name='y_fit',
                color=dataset.color, linestyle='--', marker='None',
                linewidth=dataset.linewidth,
                use_secondary_y=dataset.use_secondary_y,
                subplot_target=dataset.subplot_target,
                fit_info=result_text,
                fit_result=fit_result,
                fit_band_display=applied_band_type,
                provenance=self._build_provenance('batch_curve_fit', fit_result, [dataset]),
            )
            results.append({'source_name': dataset.name, 'fit_dataset': fit_dataset, 'error': None})

        return results

    def _top_level_selected_items(self, items):
        """
        選択されたアイテムのうち、他の選択アイテムの子孫であるものを除いた
        「実質的に一番上位にある」アイテムだけを返す。
        (フォルダとその中のデータセットが同時に選択されている場合に、
         フォルダの削除だけで子も一緒に消えるようにするため)
        """
        item_set = {id(it) for it in items}
        result = []
        for item in items:
            ancestor = item.parent()
            nested_under_selected = False
            while ancestor is not None:
                if id(ancestor) in item_set:
                    nested_under_selected = True
                    break
                ancestor = ancestor.parent()
            if not nested_under_selected:
                result.append(item)
        return result

    def _on_remove_dataset(self):
        """
        「データセット削除」ボタンが押されたときの処理。
        選択中の(複数可)データセット・フォルダをリストとUIから削除する。
        フォルダを削除すると、その中のデータセットもまとめて削除される。
        """
        selected_items = self.ui.dataset_list_widget.selectedItems()
        if not selected_items:
            return # 何も選択されていない

        # フォルダの中身も含め、削除対象のデータセットをすべて収集する
        datasets_to_remove = []

        def collect(item):
            dataset = item.data(0, Qt.ItemDataRole.UserRole)
            if dataset is not None:
                datasets_to_remove.append(dataset)
            else:
                for i in range(item.childCount()):
                    collect(item.child(i))

        for item in selected_items:
            collect(item)

        # 【★ 重要 ★】
        # これからUIツリーを操作する。操作中に currentItemChanged が
        # 意図せず発行されるのを防ぐため、シグナルを一時的にブロックする。
        self.ui.dataset_list_widget.blockSignals(True)

        # project.datasets から削除 (インデックスがずれないよう降順で処理)
        rows_to_remove = sorted(
            {row for ds in datasets_to_remove if (row := self._find_dataset_row(ds)) != -1},
            reverse=True
        )
        for row in rows_to_remove:
            del self.project.datasets[row]

        # UIツリーから、選択された最上位アイテムだけを削除する
        # (子アイテムも同時に選択されていても、親を消せば一緒に消えるため二重削除は避ける)
        for item in self._top_level_selected_items(selected_items):
            parent = item.parent()
            if parent is not None:
                parent.removeChild(item)
            else:
                idx = self.ui.dataset_list_widget.indexOfTopLevelItem(item)
                if idx != -1:
                    self.ui.dataset_list_widget.takeTopLevelItem(idx)

        self.ui.dataset_list_widget.blockSignals(False)

        # UIの状態を更新 (プロパティ欄などを無効化)
        self._update_ui_state()

        # グラフを再描画
        self._update_plot()

    def _find_dataset_row(self, dataset):
        """
        project.datasets の中で、指定した Dataset インスタンスが何行目にあるかを返す。
        (Dataset は dataclass で値ベースの __eq__ を持ち、フィールドに DataFrame を
         含むため `list.index()` は使えない (DataFrame の真偽値判定でエラーになる)。
         そのため `is` によるオブジェクト同一性で検索する。)
        """
        for i, ds in enumerate(self.project.datasets):
            if ds is dataset:
                return i
        return -1

    def _on_dataset_rows_moved(self, source_parent, source_start, source_end, dest_parent, dest_row):
        """
        dataset_list_widget (ツリー) 内でドラッグ&ドロップによる移動が行われた後に
        呼ばれるスロット (ツリーの内部モデルの rowsMoved シグナルに接続)。

        project.datasets の順序がそのままプロットの描画順(=重なり順。後から描画された
        ものが手前に表示される)を決めているため、ツリーの表示順 (先行順に辿った
        データセットの並び) に合わせて project.datasets を並べ替える。

        - 同じ親 (フォルダ) 内での並べ替えの場合のみ、Undo/Redo 可能な
          ReorderDatasetsCommand として発行する。
        - フォルダをまたぐ移動 (フォルダ構造そのものの変更) は、データセットの
          追加/削除/複製と同様、現状 Undo 非対応の単純な操作として扱う
          (フォルダ構造ごとのUndoは対象外)。
        """
        reordered = [item.data(0, Qt.ItemDataRole.UserRole) for item in self._flatten_dataset_tree()]

        if len(reordered) != len(self.project.datasets):
            logger.warning(
                "データセットの並べ替え同期に失敗しました (表示数 %d, 実際 %d)。",
                len(reordered), len(self.project.datasets)
            )
            return

        old_order = list(self.project.datasets)
        # Dataset は値ベースの __eq__ (DataFrameを含む) を持つため、順序の比較は
        # `==` ではなくオブジェクト同一性 (id) のリストで行う。
        if [id(d) for d in reordered] == [id(d) for d in old_order]:
            return # 実質的な順序変化なし (誤検知の rowsMoved など)

        if source_parent == dest_parent:
            # 同じ親内での純粋な並べ替え -> Undo/Redo可能に
            command = ReorderDatasetsCommand(
                self.project, old_order, reordered,
                on_applied=self._on_dataset_order_applied,
                description="データセットの並べ替え"
            )
            self.undo_stack.push(command)
        else:
            # フォルダをまたぐ移動 -> 直接反映 (Undo非対応)
            self.project.datasets = reordered
            self._update_plot()

    def _on_dataset_order_applied(self):
        """
        ReorderDatasetsCommand の redo/undo 後に呼ばれるコールバック。
        ドラッグ&ドロップ操作自身の呼び出しスタックの中で dataset_list_widget を
        直接いじると再入 (Qt内部のドロップ処理と衝突) の恐れがあるため、
        ウィジェットの同期とプロット再描画は次のイベントループに遅延させる。
        """
        QTimer.singleShot(0, self._sync_dataset_list_and_replot)

    def _sync_dataset_list_and_replot(self):
        self._sync_dataset_list_widget_order()
        self._update_plot()

    def _refresh_after_dataset_property_change(self, dataset, changed_keys=(), old_values=None, new_values=None):
        """
        Undo/Redo でデータセットのプロパティが変更された後の共通後処理。
        - 変更されたデータセットがリストに表示されている名前と食い違っていれば同期
        - 変更されたデータセットが現在選択中なら、プロパティパネルにも反映
        - グラフを再描画(軽量な該当Axesのみの更新で足りる)

        ★ 項目C-003フェーズ3a: 以前は`subplot_target`/`use_secondary_y`の
        変更を「軸の所属自体が変わる構造的な変更」として一律フルの
        `_update_plot()`(`redraw_all`、全Axes再構築)に振り分けていたが、
        実際には`use_secondary_y`は現在の`subplot_target`軸1つだけで完結し、
        `subplot_target`自体の変更も「旧軸から消える・新軸に現れる」という
        2つのAxesだけで完結する(Axesの枚数・GridSpec配置自体は変わらない)
        ため、`update_single_axis()`を対象Axesの数ぶん呼ぶだけで軽量に
        対応できる。`SetDatasetPropertiesCommand.on_applied`はredo/undo
        どちらの後でも同じコールバックが呼ばれる(方向を教えてくれない)ため、
        `old_values`/`new_values`の両方から`subplot_target`の候補値を集め、
        現在値(`dataset.subplot_target`)と合わせて集合として重複排除する
        ことで、redo/undoのどちら向きでも新旧両方のAxesを正しく更新できる。
        """
        item = self._get_dataset_tree_item(dataset)
        if item is not None:
            if item.text(0) != dataset.name:
                item.setText(0, dataset.name)
            item.setIcon(0, make_dataset_style_icon(dataset))
            # ★ 項目C-907: visible属性は変わっていなくても、目アイコン/文字色の
            #   再同期はコストが小さいためプロパティ変更のたびに毎回行う
            #   (visibleだけ選んで特別扱いする分岐を増やさないほうがシンプル)。
            item.setIcon(DATASET_TREE_VISIBILITY_COLUMN, make_dataset_visibility_icon(dataset))
            apply_dataset_visibility_text_style(item, dataset)
            if item is self.ui.dataset_list_widget.currentItem():
                self._update_ui_state()

        axis_index = dataset.subplot_target
        if axis_index >= len(self.canvas.all_axes) or axis_index >= len(self.project.all_plot_settings):
            self._update_plot()
            return

        axis_indices_to_refresh = {axis_index}
        if 'subplot_target' in changed_keys:
            if old_values and 'subplot_target' in old_values:
                axis_indices_to_refresh.add(old_values['subplot_target'])
            if new_values and 'subplot_target' in new_values:
                axis_indices_to_refresh.add(new_values['subplot_target'])
        axis_indices_to_refresh = {
            i for i in axis_indices_to_refresh
            if i < len(self.canvas.all_axes) and i < len(self.project.all_plot_settings)
        }

        layout_mode = getattr(self.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            rows, cols = 0, 0
        else:
            rows = self.subplot_rows_spinbox.value()
            cols = self.subplot_cols_spinbox.value()

        for idx in axis_indices_to_refresh:
            self.canvas.update_single_axis(
                idx, self.project.datasets, self.project.all_plot_settings[idx],
                rows=rows, cols=cols,
                share_x_axis=getattr(self.project, 'share_x_axis', False),
                share_y_axis=getattr(self.project, 'share_y_axis', False),
                panel_labels_enabled=self.project.panel_labels_enabled,
            )
        is_secondary_visible = any(sa is not None for sa in self.canvas.all_secondary_axes)
        self.tick_direction_y2_label.setVisible(is_secondary_visible)
        self.major_tick_direction_y2_combo.setVisible(is_secondary_visible)
        self.minor_tick_direction_y2_combo.setVisible(is_secondary_visible)
        self.y2_label_text_label.setVisible(is_secondary_visible)
        self.y2_label_text_edit.setVisible(is_secondary_visible)

        self._reapply_editor_row_highlight()
        self._refresh_minimap()
        if hasattr(self, 'export_preview_panel'):
            self.export_preview_panel.refresh_preview()

    def _push_dataset_property_command(self, dataset, old_values: dict, new_values: dict, description: str):
        """
        Dataset のプロパティ変更を Undo/Redo 可能なコマンドとして発行する共通ヘルパー。
        old_values と new_values が同じ (実質的に変更なし) 場合は何もしない。
        """
        if old_values == new_values:
            return
        command = SetDatasetPropertiesCommand(
            dataset, old_values, new_values,
            on_applied=lambda: self._refresh_after_dataset_property_change(
                dataset, changed_keys=new_values.keys(), old_values=old_values, new_values=new_values
            ),
            description=description
        )
        self.undo_stack.push(command)

    def _on_subplot_target_changed(self, index):
        """
        データセットの「描画先プロット」コンボボックスが変更されたときに呼び出されます。

        Args:
            index (int): 新しく選択された描画先の軸インデックス。
        """
        dataset = self._get_current_dataset()
        if dataset is None or index == -1:
            return
        if dataset.subplot_target == index:
            return

        # Dataset オブジェクトが持つ描画先インデックスを更新
        # (データが移動するため、外観のみの更新ではなく _update_plot による全体再描画が必要。
        #  これは _refresh_after_dataset_property_change 内で行われる)
        self._push_dataset_property_command(
            dataset,
            {'subplot_target': dataset.subplot_target},
            {'subplot_target': index},
            description="描画先プロットの変更"
        )

    def _on_dataset_selected(self, current_item, previous_item):
        """
        UIのデータセットリスト (dataset_list_widget) で選択されている項目が
        変更されたときに呼び出されるスロット。

        Args:
            current_item (QTreeWidgetItem): 新しく選択されたアイテム。
            previous_item (QTreeWidgetItem): 以前選択されていたアイテム。
        """
        # 選択状態が変わったので、UI全体の状態を更新するヘルパーメソッドを呼ぶ
        # (_update_ui_state が、選択されたデータセットのプロパティをUIにロードする)
        self._update_ui_state()

    def _on_legend_name_changed(self):
        """
        「凡例名」テキストボックス (legend_name_edit) の編集が完了したときに
        呼び出されるスロット (editingFinished シグナル)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        new_name = self.ui.legend_name_edit.text()

        # Dataset オブジェクトの name 属性を更新 (Undo/Redo可能にする)
        # リスト表示の同期とプロット再描画は _refresh_after_dataset_property_change が行う
        self._push_dataset_property_command(
            dataset,
            {'name': dataset.name},
            {'name': new_name},
            description="凡例名の変更"
        )

    def _on_point_labels_toggled(self, checked):
        """
        「データ点にラベルを表示」チェックボックスが切り替えられたときの処理(項目105)。
        データ点が多いデータセットにラベルを表示すると、点の数だけ ax.annotate() が
        呼ばれるため描画が重くなり、アプリがフリーズする場合がある。有効化しようと
        しているときに、選択中データセットの点数が環境設定の上限を超えていれば、
        確認ポップアップを表示し、キャンセルされたらチェックボックスを元に戻して
        プロパティ変更自体を行わない(この場合 _on_property_changed は呼ばない)。
        無効化(OFF)にする場合や、点数が上限以内の場合は、そのまま通常の
        プロパティ変更処理(_on_property_changed、self.sender()で判定)に進む。
        """
        if checked:
            selected_datasets = self._get_selected_datasets()
            max_points = self.settings.value(
                "point_label_max_points", DEFAULT_POINT_LABEL_MAX_POINTS, type=int)
            over_limit = [ds for ds in selected_datasets if len(ds.visible_df) > max_points]
            if over_limit:
                max_count = max(len(ds.visible_df) for ds in over_limit)
                reply = QMessageBox.question(
                    self, "データ点ラベルの表示",
                    f"選択中のデータセットには最大{max_count}件のデータ点があります"
                    f"(環境設定の上限: {max_points}件)。\n"
                    "データ点が多い状態でラベルを表示すると、描画が遅くなったり"
                    "アプリがフリーズする場合があります。\n\nラベルを表示しますか？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.point_labels_checkbox.blockSignals(True)
                    self.point_labels_checkbox.setChecked(False)
                    self.point_labels_checkbox.blockSignals(False)
                    return

        self._on_property_changed()

    def _on_property_changed(self):
        """
        データセットのプロパティ (プロットタイプ、線種、マーカー、平滑化など) の
        UIコントロールが変更されたときに呼び出されるスロット。
        6つの異なるUIコントロールがすべてこのスロットに接続されているため、
        self.sender() でどのウィジェットが変更されたかを特定し、
        「そのプロパティだけ」を選択中の(複数可)全データセットに一括適用する。
        (仮に全プロパティを常に一括適用してしまうと、複数選択時に選択されている
        データセット同士でプロパティ値が異なる場合、触っていないプロパティまで
        1つの値に揃えられてしまうため)
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        marker_text = self.ui.marker_combo.currentText()
        # ウィジェット -> (属性名, 現在のUI値) の対応表
        field_by_widget = {
            self.ui.plot_type_combo: ('plot_type', self.ui.plot_type_combo.currentText()),
            self.ui.linestyle_combo: ('linestyle', self.ui.linestyle_combo.currentText()),
            self.ui.linewidth_spinbox: ('linewidth', self.ui.linewidth_spinbox.value()),
            # ★ UIで "None" が選択されたら、属性には None を設定
            self.ui.marker_combo: ('marker', None if marker_text == 'None' else marker_text),
            self.ui.markersize_spinbox: ('markersize', self.ui.markersize_spinbox.value()),
            self.ui.smoothing_checkbox: ('smoothing', self.ui.smoothing_checkbox.isChecked()),
            self.alpha_spinbox: ('alpha', self.alpha_spinbox.value()),
            self.point_labels_checkbox: ('show_point_labels', self.point_labels_checkbox.isChecked()),
            self.point_label_col_combo: (
                'point_label_col_name',
                None if self.point_label_col_combo.currentText() == POINT_LABEL_Y_VALUE_LABEL
                else self.point_label_col_combo.currentText()
            ),
            # プロットへのグラデーション適用(項目79)
            self.gradient_checkbox: ('gradient_enabled', self.gradient_checkbox.isChecked()),
            self.gradient_target_combo: ('gradient_target', self.gradient_target_combo.currentData()),
            # ウォーターフォールプロット(項目80、項目109でplot_typeとは独立したフラグに変更)
            self.waterfall_checkbox: ('waterfall_enabled', self.waterfall_checkbox.isChecked()),
            self.waterfall_offset_x_spinbox: ('waterfall_offset_x', self.waterfall_offset_x_spinbox.value()),
            self.waterfall_offset_y_spinbox: ('waterfall_offset_y', self.waterfall_offset_y_spinbox.value()),
            self.waterfall_occlusion_checkbox: (
                'waterfall_occlusion_enabled', self.waterfall_occlusion_checkbox.isChecked()
            ),
            # 誤差の表示形式(項目C-502)
            self.error_display_combo: ('error_display', self.error_display_combo.currentData()),
            # 2Dグリッドデータ(ヒートマップ、項目C-508)のカラーマップ・補間方法。
            # data_kind/z_col_name/vmin/vmaxはそれぞれ専用ハンドラ
            # (_on_data_2d_toggled/_on_z_column_changed/_on_2d_value_range_changed)
            # が個別に扱うため、ここには含めない。
            self.colormap_combo: ('colormap', self.colormap_combo.currentText()),
            self.grid_interp_method_combo: ('grid_interp_method', self.grid_interp_method_combo.currentText()),
            # 2Dマップの表示方式・等高線レベル数(項目C-509)
            self.map_display_mode_combo: ('map_display_mode', self.map_display_mode_combo.currentData()),
            self.contour_levels_spinbox: ('contour_levels', self.contour_levels_spinbox.value()),
        }

        changed = field_by_widget.get(self.sender())
        if changed is None:
            return # 想定外の呼び出し元 (通常は発生しない)
        attr_name, new_value = changed

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"プロパティの一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._push_dataset_property_command(
                dataset, {attr_name: getattr(dataset, attr_name)}, {attr_name: new_value},
                description="プロパティ変更"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_dataset_color_changed(self, new_color):
        """
        データセットの色選択ウィジェット (color_picker_widget、項目65) で
        色が変更されたときの処理。スウォッチのパレット展開・カラーコード欄への
        直接入力のどちらの経路でも呼ばれる (色選択・表示更新自体はウィジェット側で
        完結済みのため、ここでは選ばれた色をDatasetに適用するだけでよい)。
        複数のデータセットが選択されている場合は、全てに同じ色を適用し、
        1回のUndo/Redoでまとめて元に戻せるようにする。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        # Undo/Redo可能なコマンドとして発行
        #    複数選択時は beginMacro/endMacro で1つの操作としてまとめる
        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"データセットの色を一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._push_dataset_property_command(
                dataset,
                {'color': dataset.color},
                {'color': new_color},
                description="データセットの色変更"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_gradient_color2_changed(self, new_color):
        """
        グラデーション終端色ウィジェット (gradient_color2_picker、項目79) で
        色が変更されたときの処理。_on_dataset_color_changed (開始色=color) と
        同様のUndo/Redo・複数選択一括適用パターンを、gradient_color2に対して行う。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"グラデーション終端色を一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._push_dataset_property_command(
                dataset,
                {'gradient_color2': dataset.gradient_color2},
                {'gradient_color2': new_color},
                description="グラデーション終端色の変更"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _update_gradient_controls_visibility(self):
        """
        プロットへのグラデーション適用(項目79)のUIコントロールの表示/非表示を、
        現在選択中データセットの plot_type に応じて更新する。
        - グラデーション自体(チェックボックス・終端色)は 'Line'/'Line+Scatter'/'Area'
          でのみ意味を持つ('Scatter'/'Bar'では線も塗りも無いため隠す)。
        - 対象(線/塗り/両方)コンボは、複数の対象から選べる 'Area' でのみ表示する
          ('Line'/'Line+Scatter' では常に「線」一択のため、コンボを見せる意味がない)。
        """
        dataset = self._get_current_dataset()
        plot_type = dataset.plot_type if dataset is not None else self.ui.plot_type_combo.currentText()
        supports_gradient = plot_type in ('Line', 'Line+Scatter', 'Area')

        self.gradient_checkbox.setVisible(supports_gradient)

        show_detail = supports_gradient and self.gradient_checkbox.isChecked()
        self.gradient_color2_label.setVisible(show_detail)
        self.gradient_color2_picker.setVisible(show_detail)

        show_target_combo = show_detail and plot_type == 'Area'
        self.gradient_target_label.setVisible(show_target_combo)
        self.gradient_target_combo.setVisible(show_target_combo)

    def _update_smoothing_control_visibility(self):
        """
        平滑化(CubicSpline)チェックボックスの表示/非表示を、現在選択中データセットの
        plot_type に応じて更新する(_update_gradient_controls_visibilityと同じ
        パターン)。平滑化は「線で結んだ曲線」を滑らかにする機能のため
        'Line'/'Line+Scatter' でのみ意味を持つ。Scatter/Bar/Areaに適用すると、
        平滑化した線がマーカー/棒/塗りつぶしを完全に置き換えてしまう実害が
        あったため、対象外のplot_typeではチェックボックス自体を隠す
        (gui/canvas.pyの_draw_data側でも同じ条件を独立に再チェックしている、
        二重ガード方針)。
        """
        dataset = self._get_current_dataset()
        plot_type = dataset.plot_type if dataset is not None else self.ui.plot_type_combo.currentText()
        self.ui.smoothing_checkbox.setVisible(plot_type in ('Line', 'Line+Scatter'))

    def _update_error_display_control_items(self):
        """
        誤差表示コンボ(エラーバー/誤差バンド/両方)のうち「誤差バンド」
        (fill_betweenによる連続的な帯)を選べるplot_typeを制限する。
        Bar(離散的な棒)には連続的な帯が視覚的に合わず、Areaは自身の
        塗りつぶしと二重に重なって煩雑になるため、これら2種別では
        「誤差バンド」「両方」の項目を無効化する(グラデーション/平滑化と
        同じ「状況に応じて選択肢を制限する」方針だが、コンボ全体ではなく
        個別項目の有効/無効化のため setVisible ではなく QStandardItem の
        setEnabled を使う)。既に保存済みの値は変更しない(選び直しは
        ユーザーに委ねる、_update_gradient_controls_visibilityと同じ方針)。
        """
        dataset = self._get_current_dataset()
        plot_type = dataset.plot_type if dataset is not None else self.ui.plot_type_combo.currentText()
        band_ok = plot_type not in ('Bar', 'Area')
        model = self.error_display_combo.model()
        for value in ('band', 'both'):
            index = self.error_display_combo.findData(value)
            if index != -1:
                model.item(index).setEnabled(band_ok)

    def _update_waterfall_controls_visibility(self):
        """
        ウォーターフォールプロット(項目80)のオフセット量スピンボックスの表示/非表示を
        更新する。項目109で「plot_type=='Waterfall'という専用種別」から「どの
        plot_typeとも組み合わせられる独立チェックボックス」に変更したため、
        チェックボックス自体は常に表示し、オフセット量スピンボックスだけを
        チェック状態に応じて表示/非表示にする(_update_gradient_controls_visibility の
        「詳細設定はチェック後にだけ見せる」パターンと同じ)。
        """
        self.waterfall_checkbox.setVisible(True)
        show_offsets = self.waterfall_checkbox.isChecked()

        self.waterfall_offset_x_label.setVisible(show_offsets)
        self.waterfall_offset_x_spinbox.setVisible(show_offsets)
        self.waterfall_offset_y_label.setVisible(show_offsets)
        self.waterfall_offset_y_spinbox.setVisible(show_offsets)
        # オクルージョンON/OFFも、有効時だけ意味を持つ設定のため同じ条件で表示する
        self.waterfall_occlusion_checkbox.setVisible(show_offsets)

    def _on_auto_assign_colors(self):
        """
        「自動配色」ボタンが押されたときの処理。
        選択中の(複数可)データセットに、現在アクティブなカラーパレット
        (ユーザーが「パレット管理」で作成したもの、または既定のmatplotlibの
        カラーサイクル) を順番に自動で割り当てる。
        手動で1つずつ色を選ぶ手間を省くための一括操作。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        color_cycle = self._get_active_color_cycle()

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"配色の自動割り当て ({len(selected_datasets)}件)")
        for i, dataset in enumerate(selected_datasets):
            new_color = color_cycle[i % len(color_cycle)]
            self._push_dataset_property_command(
                dataset,
                {'color': dataset.color},
                {'color': new_color},
                description="配色の自動割り当て"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_auto_assign_colors_from_colormap(self):
        """
        「カラーマップから自動配色...」メニューの処理(項目C-805)。
        _on_auto_assign_colors が離散パレットを順番に割り当てるのに対し、
        こちらは連続カラーマップ(viridis等)から選択中のデータセット数ぶんを
        均等サンプリングして割り当てる。時系列/濃度変化など、順序に意味のある
        系列をグラデーションで表現したい場合向け。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        cmap_name, ok = QInputDialog.getItem(
            self, "カラーマップから自動配色", "使用するカラーマップを選択してください:",
            RECOMMENDED_COLORMAPS, 0, False
        )
        if not ok:
            return

        cmap = mpl.colormaps[cmap_name]
        n = len(selected_datasets)
        # n==1のときの0除算を避ける(1件ならカラーマップの中央値を使う)
        positions = [0.5] if n == 1 else [i / (n - 1) for i in range(n)]
        new_colors = [mpl.colors.to_hex(cmap(p)) for p in positions]

        is_batch = n > 1
        if is_batch:
            self.undo_stack.beginMacro(f"カラーマップからの配色 ({n}件)")
        for dataset, new_color in zip(selected_datasets, new_colors):
            self._push_dataset_property_command(
                dataset, {'color': dataset.color}, {'color': new_color},
                description="カラーマップからの配色"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _load_color_palettes(self):
        """QSettingsに保存されているカスタム配色パレット一式を辞書として読み込む"""
        raw = self.settings.value(COLOR_PALETTES_SETTINGS_KEY, "")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("カスタム配色パレットの読み込みに失敗しました。空として扱います。")
            return {}

    def _save_color_palettes(self, palettes: dict):
        """カスタム配色パレット一式をQSettingsに保存する"""
        self.settings.setValue(COLOR_PALETTES_SETTINGS_KEY, json.dumps(palettes))

    def _get_active_color_cycle(self):
        """
        現在アクティブなパレットの色リストを返す。
        パレットが未設定、または空の場合はmatplotlibの既定カラーサイクルにフォールバックする。
        """
        active_name = self.settings.value(ACTIVE_PALETTE_SETTINGS_KEY, ColorPaletteDialog.DEFAULT_PALETTE_NAME)
        palettes = self._load_color_palettes()
        if active_name != ColorPaletteDialog.DEFAULT_PALETTE_NAME and palettes.get(active_name):
            return palettes[active_name]
        return mpl.rcParams['axes.prop_cycle'].by_key()['color']

    def _on_manage_color_palettes(self):
        """「パレット管理...」ボタンが押されたときの処理。ダイアログで編集後、設定に保存する。"""
        palettes = self._load_color_palettes()
        active_name = self.settings.value(ACTIVE_PALETTE_SETTINGS_KEY, ColorPaletteDialog.DEFAULT_PALETTE_NAME)

        dialog = ColorPaletteDialog(palettes, active_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_palettes, new_active_name = dialog.get_result()
            self._save_color_palettes(new_palettes)
            self.settings.setValue(ACTIVE_PALETTE_SETTINGS_KEY, new_active_name)

    def _update_ui_state(self):
        """
        アプリケーションの現在の状態 (主にデータセットの選択状態) に基づいて、
        UIの有効/無効、表示/非表示、および内容を更新する。
        _on_dataset_selected や _on_remove_dataset などから呼び出される。
        """

        # 1. サブプロット関連のコンボボックス（選択肢）を更新
        self._update_subplot_combos()

        # 2. データセットリストの選択状態を取得
        # ★ フォルダも選択可能なため、「何か選択されているか」(フォルダ含む。主に
        #   削除ボタン用) と「データセットが選択されているか」(色変更等、
        #   データセット固有の操作用) を分けて扱う。
        current_dataset = self._get_current_dataset()
        selected_datasets = self._get_selected_datasets()
        has_any_selection = bool(self.ui.dataset_list_widget.selectedItems())
        has_dataset_selection = bool(selected_datasets)

        # 3. 選択状態に基づいて、UIの有効/無効を一括設定

        # 「データセットプロパティ」ドックウィジェット (中身の GroupBox)
        self.ui.properties_groupbox.setEnabled(has_dataset_selection)

        # データセットリストタブのボタン
        self.ui.remove_dataset_button.setEnabled(has_any_selection) # フォルダの削除も許可
        self.duplicate_dataset_button.setEnabled(has_dataset_selection)
        self.view_edit_data_button.setEnabled(has_dataset_selection)
        self.auto_color_button.setEnabled(has_dataset_selection)

        # (フィット/ピークボタン)
        self.fit_curve_button.setEnabled(has_dataset_selection)
        self.find_peaks_button.setEnabled(has_dataset_selection)

        # プロパティタブ内のコンボボックス (setEnabled(has_dataset_selection) に含まれるが明示)
        self.subplot_target_combo.setEnabled(has_dataset_selection)
        self.use_secondary_y_checkbox.setEnabled(has_dataset_selection)
        self.x_col_combo.setEnabled(has_dataset_selection)
        self.y_col_combo.setEnabled(has_dataset_selection)
        self.x_err_col_combo.setEnabled(has_dataset_selection)
        self.y_err_col_combo.setEnabled(has_dataset_selection)
        self.error_display_combo.setEnabled(has_dataset_selection)

        # 4. 【選択中】の場合: 選択された Dataset の内容をUIにロード
        #    (current_dataset は「カレント」アイテムがフォルダの場合や、
        #     何も選択されていない場合は None になる)
        if current_dataset is not None:
            dataset = current_dataset

            # 4b. ★★★ シグナルを一時的にブロック ★★★
            # (これからコードでUIの値をセットするため、シグナルが発火するのを防ぐ)
            self.ui.legend_name_edit.blockSignals(True)
            self.ui.plot_type_combo.blockSignals(True)
            self.color_picker_widget.blockSignals(True)
            self.ui.linestyle_combo.blockSignals(True)
            self.ui.linewidth_spinbox.blockSignals(True)
            self.ui.marker_combo.blockSignals(True)
            self.ui.markersize_spinbox.blockSignals(True)
            self.ui.smoothing_checkbox.blockSignals(True)
            self.alpha_spinbox.blockSignals(True)
            self.point_labels_checkbox.blockSignals(True)
            self.point_label_col_combo.blockSignals(True)
            self.use_secondary_y_checkbox.blockSignals(True)
            self.subplot_target_combo.blockSignals(True)
            self.gradient_checkbox.blockSignals(True)
            self.gradient_color2_picker.blockSignals(True)
            self.gradient_target_combo.blockSignals(True)
            self.waterfall_checkbox.blockSignals(True)
            self.waterfall_offset_x_spinbox.blockSignals(True)
            self.waterfall_offset_y_spinbox.blockSignals(True)
            self.waterfall_occlusion_checkbox.blockSignals(True)
            self.error_display_combo.blockSignals(True)
            self.data_2d_checkbox.blockSignals(True)
            self.colormap_combo.blockSignals(True)
            self.map_display_mode_combo.blockSignals(True)
            self.contour_levels_spinbox.blockSignals(True)
            self.grid_interp_method_combo.blockSignals(True)
            self.color_range_auto_checkbox.blockSignals(True)
            self.vmin_spinbox.blockSignals(True)
            self.vmax_spinbox.blockSignals(True)

            # 4c. Dataset オブジェクトの値をUIにロード
            self.ui.legend_name_edit.setText(dataset.name)
            self.ui.plot_type_combo.setCurrentText(dataset.plot_type)
            self.ui.linestyle_combo.setCurrentText(dataset.linestyle)
            self.ui.linewidth_spinbox.setValue(dataset.linewidth)
            self.ui.marker_combo.setCurrentText(dataset.marker if dataset.marker is not None else 'None')
            self.ui.markersize_spinbox.setValue(dataset.markersize)
            self.color_picker_widget.set_color(dataset.color)
            self.ui.smoothing_checkbox.setChecked(dataset.smoothing)
            self.alpha_spinbox.setValue(dataset.alpha)
            self.gradient_checkbox.setChecked(dataset.gradient_enabled)
            self.gradient_color2_picker.set_color(dataset.gradient_color2)
            gradient_target_index = self.gradient_target_combo.findData(dataset.gradient_target)
            self.gradient_target_combo.setCurrentIndex(gradient_target_index if gradient_target_index != -1 else 0)
            self.waterfall_checkbox.setChecked(dataset.waterfall_enabled)
            self.waterfall_offset_x_spinbox.setValue(dataset.waterfall_offset_x)
            self.waterfall_offset_y_spinbox.setValue(dataset.waterfall_offset_y)
            self.waterfall_occlusion_checkbox.setChecked(dataset.waterfall_occlusion_enabled)
            self.point_labels_checkbox.setChecked(dataset.show_point_labels)
            self.point_label_col_combo.clear()
            self.point_label_col_combo.addItems([POINT_LABEL_Y_VALUE_LABEL] + dataset.df.columns.tolist())
            self.point_label_col_combo.setCurrentText(dataset.point_label_col_name or POINT_LABEL_Y_VALUE_LABEL)
            self.use_secondary_y_checkbox.setChecked(dataset.use_secondary_y)
            self.subplot_target_combo.setCurrentIndex(dataset.subplot_target)
            error_display_index = self.error_display_combo.findData(dataset.error_display)
            self.error_display_combo.setCurrentIndex(error_display_index if error_display_index != -1 else 0)
            self.data_2d_checkbox.setChecked(dataset.data_kind == '2d_grid')
            colormap_index = self.colormap_combo.findText(dataset.colormap)
            self.colormap_combo.setCurrentIndex(colormap_index if colormap_index != -1 else 0)
            display_mode_index = self.map_display_mode_combo.findData(dataset.map_display_mode)
            self.map_display_mode_combo.setCurrentIndex(display_mode_index if display_mode_index != -1 else 0)
            self.contour_levels_spinbox.setValue(dataset.contour_levels)
            interp_index = self.grid_interp_method_combo.findText(dataset.grid_interp_method)
            self.grid_interp_method_combo.setCurrentIndex(interp_index if interp_index != -1 else 0)
            is_range_auto = dataset.vmin is None and dataset.vmax is None
            self.color_range_auto_checkbox.setChecked(is_range_auto)
            self.vmin_spinbox.setValue(dataset.vmin if dataset.vmin is not None else 0.0)
            self.vmax_spinbox.setValue(dataset.vmax if dataset.vmax is not None else 1.0)
            self.vmin_spinbox.setEnabled(not is_range_auto)
            self.vmax_spinbox.setEnabled(not is_range_auto)

            # 4d. ★★★ シグナルを解除 ★★★
            self.ui.legend_name_edit.blockSignals(False)
            self.ui.plot_type_combo.blockSignals(False)
            self.color_picker_widget.blockSignals(False)
            self.ui.linestyle_combo.blockSignals(False)
            self.ui.linewidth_spinbox.blockSignals(False)
            self.ui.marker_combo.blockSignals(False)
            self.ui.markersize_spinbox.blockSignals(False)
            self.ui.smoothing_checkbox.blockSignals(False)
            self.alpha_spinbox.blockSignals(False)
            self.point_labels_checkbox.blockSignals(False)
            self.point_label_col_combo.blockSignals(False)
            self.use_secondary_y_checkbox.blockSignals(False)
            self.subplot_target_combo.blockSignals(False)
            self.gradient_checkbox.blockSignals(False)
            self.gradient_color2_picker.blockSignals(False)
            self.gradient_target_combo.blockSignals(False)
            self.waterfall_checkbox.blockSignals(False)
            self.waterfall_offset_x_spinbox.blockSignals(False)
            self.waterfall_offset_y_spinbox.blockSignals(False)
            self.waterfall_occlusion_checkbox.blockSignals(False)
            self.error_display_combo.blockSignals(False)
            self.data_2d_checkbox.blockSignals(False)
            self.colormap_combo.blockSignals(False)
            self.map_display_mode_combo.blockSignals(False)
            self.contour_levels_spinbox.blockSignals(False)
            self.grid_interp_method_combo.blockSignals(False)
            self.color_range_auto_checkbox.blockSignals(False)
            self.vmin_spinbox.blockSignals(False)
            self.vmax_spinbox.blockSignals(False)
            self._update_gradient_controls_visibility()
            self._update_waterfall_controls_visibility()
            self._update_smoothing_control_visibility()
            self._update_error_display_control_items()
            self._update_2d_controls_visibility()

            # 4e. X/Y軸コンボボックスの更新処理 (シグナルブロックを含む)
            self.x_col_combo.blockSignals(True)
            self.y_col_combo.blockSignals(True)

            all_columns = dataset.df.columns.tolist()
            self.x_col_combo.clear()
            self.y_col_combo.clear()
            self.x_col_combo.addItems(all_columns)
            self.y_col_combo.addItems(all_columns)

            # 現在の列名を選択状態にする
            self.x_col_combo.setCurrentText(dataset.x_col_name)
            self.y_col_combo.setCurrentText(dataset.y_col_name)

            self.x_col_combo.blockSignals(False)
            self.y_col_combo.blockSignals(False)

            # 4e-2. エラーバー用の誤差列コンボボックス ("(なし)" を先頭に追加)
            self.x_err_col_combo.blockSignals(True)
            self.y_err_col_combo.blockSignals(True)

            self.x_err_col_combo.clear()
            self.y_err_col_combo.clear()
            self.x_err_col_combo.addItems([NO_ERROR_COLUMN_LABEL] + all_columns)
            self.y_err_col_combo.addItems([NO_ERROR_COLUMN_LABEL] + all_columns)
            self.x_err_col_combo.setCurrentText(dataset.x_err_col_name or NO_ERROR_COLUMN_LABEL)
            self.y_err_col_combo.setCurrentText(dataset.y_err_col_name or NO_ERROR_COLUMN_LABEL)

            self.x_err_col_combo.blockSignals(False)
            self.y_err_col_combo.blockSignals(False)

            # 4e-3. Z軸列コンボボックス(2Dグリッドデータ、項目C-508)
            self.z_col_combo.blockSignals(True)
            self.z_col_combo.clear()
            self.z_col_combo.addItems(all_columns)
            if dataset.z_col_name:
                self.z_col_combo.setCurrentText(dataset.z_col_name)
            self.z_col_combo.blockSignals(False)

            # 4f. フィット情報UIの更新
            if dataset.fit_info:
                self.fit_info_label.setVisible(True)
                self.fit_info_textedit.setVisible(True)
                self.fit_info_textedit.setText(dataset.fit_info)
            else:
                self.fit_info_label.setVisible(False)
                self.fit_info_textedit.setVisible(False)
                self.fit_info_textedit.clear()

            # 4g. 統計サマリー (Y列の件数・平均・標準偏差・最小/最大) の更新
            self._update_stats_summary_label(dataset)

            # 4h. 残差プロットパネルの更新(項目C-406)。dataset.fit_resultが
            # 無ければパネル側がプレースホルダ表示に戻す(再計算はしない)。
            self.residual_panel.refresh(dataset)

            # 4i. 処理履歴(provenance)ツリーパネルの更新(項目C-1101)。
            self.provenance_panel.refresh(dataset, self.project)

        # 5. 【非選択中 (またはフォルダ選択中)】の場合: UIをクリア
        else:
            self.x_col_combo.clear()
            self.y_col_combo.clear()
            self.x_err_col_combo.clear()
            self.y_err_col_combo.clear()
            self.point_label_col_combo.clear()
            self.z_col_combo.clear()
            self._update_2d_controls_visibility()

            self.fit_info_label.setVisible(False)
            self.fit_info_textedit.setVisible(False)
            self.fit_info_textedit.clear()
            self.residual_panel.refresh(None)
            self.provenance_panel.refresh(None, self.project)

            self.gradient_checkbox.setVisible(False)
            self.gradient_color2_label.setVisible(False)
            self.gradient_color2_picker.setVisible(False)
            self.gradient_target_label.setVisible(False)
            self.gradient_target_combo.setVisible(False)

            self.waterfall_checkbox.setVisible(False)
            self.waterfall_offset_x_label.setVisible(False)
            self.waterfall_offset_x_spinbox.setVisible(False)
            self.waterfall_offset_y_label.setVisible(False)
            self.waterfall_offset_y_spinbox.setVisible(False)
            self.waterfall_occlusion_checkbox.setVisible(False)

            self.stats_summary_label.setText("-")
            self.dataset_mini_stats_label.setText("-")

    def _update_stats_summary_label(self, dataset):
        """
        選択中データセットのY列について、件数・平均・標準偏差・最小/最大の
        要約統計量を計算し、プロパティパネルのラベル(詳細版)と、
        データセットリスト直下のミニ統計ラベル(項目69、1行の簡易版)の
        両方に表示する。NaNは集計から除外する。数値に変換できない列の場合は "-" を表示する。
        """
        try:
            y = np.asarray(dataset.y_data, dtype=float)
            valid = y[~np.isnan(y)]
            if len(valid) == 0:
                self.stats_summary_label.setText("-")
                self.dataset_mini_stats_label.setText(dataset.name)
                return
            self.stats_summary_label.setText(
                f"件数: {len(valid)}   平均: {np.mean(valid):.4g}   "
                f"標準偏差: {np.std(valid):.4g}   最小: {np.min(valid):.4g}   最大: {np.max(valid):.4g}"
            )
            self.dataset_mini_stats_label.setText(
                f"{dataset.name} 〈n={len(valid)}, 平均={np.mean(valid):.4g}, "
                f"σ={np.std(valid):.4g}〉"
            )
        except (TypeError, ValueError):
            self.stats_summary_label.setText("-")
            self.dataset_mini_stats_label.setText(dataset.name)

    def _on_duplicate_dataset(self):
        """
        「プロット複製」ボタンが押されたときの処理。選択中の(複数可)データセットを複製する。
        複製先は元のデータセットと同じフォルダ (兄弟) にする。
        """
        selected_items = [
            item for item in self.ui.dataset_list_widget.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole) is not None
        ]
        if not selected_items:
            return

        self.ui.dataset_list_widget.blockSignals(True)
        new_items = []
        for item in selected_items:
            original_dataset = item.data(0, Qt.ItemDataRole.UserRole)

            # ★★★ deepcopy が重要 ★★★
            # Dataset オブジェクト (特に中の DataFrame df) を完全に複製する
            new_dataset = copy.deepcopy(original_dataset)

            # 新しい名前を付ける (例: "data.csv (copy)")
            new_dataset.name = f"{original_dataset.name} (copy)"

            # リストとUIに追加 (元のデータセットと同じ親フォルダに)
            self.project.datasets.append(new_dataset)
            new_item = self._add_dataset_list_item(new_dataset, item.parent())
            new_items.append(new_item)

        # 複製されたアイテムをまとめて選択状態にする
        self.ui.dataset_list_widget.clearSelection()
        for item in new_items:
            item.setSelected(True)
        self.ui.dataset_list_widget.setCurrentItem(new_items[-1])
        self.ui.dataset_list_widget.blockSignals(False)

        # UIの状態とグラフを更新
        self._update_ui_state()
        self._update_plot()

    def _on_show_data_editor(self):
        """「データ表示/編集」ボタンが押されたときの処理。DataEditorDialog を表示する"""
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        # 0. 実機フィードバック(「データエディタが背面に行くと表に出すのが
        #    面倒」、ユーザー選択: 「タスクバー化+再クリックで最前面」):
        #    既に同じデータセットのエディタが開いている場合、閉じて作り直す
        #    (=ソート状態・スクロール位置・選択中の行が失われる)のではなく、
        #    既存のウィンドウをそのまま最前面に呼び戻すだけにする。
        if self.data_editor_dialog is not None and self.data_editor_dialog.dataset is dataset:
            self.data_editor_dialog.show()
            self.data_editor_dialog.raise_()
            self.data_editor_dialog.activateWindow()
            return

        # 1. もし別のデータセット用の古いダイアログが画面に残っていれば、閉じて削除する
        #    (これにより、常に選択中のデータセットに対応したエディタが表示される)
        if self.data_editor_dialog:
            self.data_editor_dialog.close() # ウィンドウを閉じる
            # ★ バグ修正: close()はQDialogを非表示にするだけでC++オブジェクトは
            # 破棄しない。このダイアログはself(メインウィンドウ)を親に持つため、
            # 別のデータセットに切り替えるたびに古いインスタンス(QTableWidgetや
            # 自身のQUndoStackごと)が非表示のまま親にぶら下がり続け、プロセス
            # 終了までメモリに残っていた(データエディタを開き直すたびに蓄積する
            # リーク)。deleteLater()で実際の破棄をスケジュールする。
            self.data_editor_dialog.deleteLater()
            del self.data_editor_dialog
            self.data_editor_dialog = None # 参照をクリア

        # 2. 新しい DataEditorDialog を作成し、インスタンス変数に保持する
        self.data_editor_dialog = DataEditorDialog(dataset, self)

        # 3. ダイアログの dataChanged シグナルを、メインウィンドウの
        #    _on_data_structure_changed スロットに接続する。
        #    (エディタでの変更を検知するため)
        self.data_editor_dialog.dataChanged.connect(self._on_data_structure_changed)

        # 3b. データエディタで選択した行 <-> グラフ上のハイライトを連動させる
        self.data_editor_dialog.rowsHighlighted.connect(self._on_editor_rows_highlighted)

        # 4. exec() (モーダル) の代わりに show() (非モーダル) で表示する
        #    (エディタを開いたままメインウィンドウを操作できるようにするため)
        self.data_editor_dialog.show()

    def _on_plot_column_changed(self):
        """
        「X軸の列」または「Y軸の列」コンボボックスが変更されたときに呼び出される。
        Dataset オブジェクトの x_col_name / y_col_name を更新し、プロットを再描画する。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        # 新しい列名を取得
        new_x_col = self.x_col_combo.currentText()
        new_y_col = self.y_col_combo.currentText()

        # 実際に変更がある列だけを old/new_values に含める
        # (コンボボックスが空の場合もあるため、空でないかチェック)
        old_values, new_values = {}, {}
        if new_x_col and new_x_col in dataset.df.columns and new_x_col != dataset.x_col_name:
            old_values['x_col_name'] = dataset.x_col_name
            new_values['x_col_name'] = new_x_col
        if new_y_col and new_y_col in dataset.df.columns and new_y_col != dataset.y_col_name:
            old_values['y_col_name'] = dataset.y_col_name
            new_values['y_col_name'] = new_y_col

        # Undo/Redo可能なコマンドとして発行 (X/Yが同時に変わった場合は1つの操作としてまとめる)
        self._push_dataset_property_command(dataset, old_values, new_values, description="プロット列の変更")

    def _on_data_2d_toggled(self, checked):
        """
        「2Dグリッドデータとして扱う」チェックボックス(項目C-508)が切り替えられた
        ときの処理。data_kindを'2d_grid'/'1d'に切り替える。ONにする際、
        z_col_nameが未設定ならX/Y列以外の最初の列を自動選択する(候補が無ければ
        未設定のままにし、ユーザーに手動選択を促す)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return
        new_data_kind = '2d_grid' if checked else '1d'
        if dataset.data_kind == new_data_kind:
            self._update_2d_controls_visibility()
            return

        old_values = {'data_kind': dataset.data_kind}
        new_values = {'data_kind': new_data_kind}
        if new_data_kind == '2d_grid' and not dataset.z_col_name:
            candidates = [
                c for c in dataset.df.columns
                if c not in (dataset.x_col_name, dataset.y_col_name)
            ]
            if candidates:
                old_values['z_col_name'] = dataset.z_col_name
                new_values['z_col_name'] = candidates[0]

        self._push_dataset_property_command(dataset, old_values, new_values, description="2Dグリッドデータの切り替え")
        self._update_2d_controls_visibility()

    def _on_z_column_changed(self):
        """
        「Z軸の列」コンボボックスが変更されたときに呼び出される
        (_on_plot_column_changedのZ列版)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return
        new_z_col = self.z_col_combo.currentText()
        if not new_z_col or new_z_col not in dataset.df.columns or new_z_col == dataset.z_col_name:
            return
        self._push_dataset_property_command(
            dataset, {'z_col_name': dataset.z_col_name}, {'z_col_name': new_z_col},
            description="Z軸列の変更"
        )

    def _on_2d_value_range_changed(self):
        """
        「値域を自動」チェックボックス、または値域の最小/最大スピンボックスが
        変更されたときの処理(項目C-508)。自動が有効な間はvmin/vmaxを
        Noneにする(core/dataset.pyのz_gridプロパティ・gui/canvas.pyの
        _draw_2d_dataがNoneの場合は実データの最小/最大値を使う)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return
        is_auto = self.color_range_auto_checkbox.isChecked()
        self.vmin_spinbox.setEnabled(not is_auto)
        self.vmax_spinbox.setEnabled(not is_auto)

        new_vmin = None if is_auto else self.vmin_spinbox.value()
        new_vmax = None if is_auto else self.vmax_spinbox.value()
        if new_vmin == dataset.vmin and new_vmax == dataset.vmax:
            return
        self._push_dataset_property_command(
            dataset,
            {'vmin': dataset.vmin, 'vmax': dataset.vmax},
            {'vmin': new_vmin, 'vmax': new_vmax},
            description="値域の変更"
        )

    def _update_2d_controls_visibility(self):
        """
        2Dグリッドデータ関連のコントロール(Z列・カラーマップ・補間方法・値域)の
        表示/非表示を、現在選択中データセットのdata_kindに応じて更新する
        (_update_gradient_controls_visibilityと同じパターン)。
        """
        dataset = self._get_current_dataset()
        # ★ 選択なし(None)の場合は常に非表示にする(data_2d_checkboxのチェック状態は
        # 直前に選択していたデータセットの値が残ったままなので、それにフォール
        # バックすると選択解除後も2D系コントロールが表示されたままになるバグになる)。
        is_2d = dataset is not None and dataset.data_kind == '2d_grid'

        for widget in (
            self.z_col_label, self.z_col_combo,
            self.colormap_label, self.colormap_combo,
            self.map_display_mode_label, self.map_display_mode_combo,
            self.contour_levels_label, self.contour_levels_spinbox,
            self.grid_interp_method_label, self.grid_interp_method_combo,
            self.color_range_auto_checkbox,
            self.vmin_label, self.vmin_spinbox,
            self.vmax_label, self.vmax_spinbox,
        ):
            widget.setVisible(is_2d)

    def _on_error_column_changed(self):
        """
        「X誤差列」または「Y誤差列」コンボボックスが変更されたときに呼び出される。
        Dataset オブジェクトの x_err_col_name / y_err_col_name を更新し、
        エラーバー付きでプロットを再描画する。"(なし)" が選択された場合は
        None (エラーバー非表示) を設定する。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        new_x_err = self.x_err_col_combo.currentText()
        new_y_err = self.y_err_col_combo.currentText()
        new_x_err_col = None if (not new_x_err or new_x_err == NO_ERROR_COLUMN_LABEL) else new_x_err
        new_y_err_col = None if (not new_y_err or new_y_err == NO_ERROR_COLUMN_LABEL) else new_y_err

        old_values, new_values = {}, {}
        if new_x_err_col != dataset.x_err_col_name:
            old_values['x_err_col_name'] = dataset.x_err_col_name
            new_values['x_err_col_name'] = new_x_err_col
        if new_y_err_col != dataset.y_err_col_name:
            old_values['y_err_col_name'] = dataset.y_err_col_name
            new_values['y_err_col_name'] = new_y_err_col

        self._push_dataset_property_command(dataset, old_values, new_values, description="誤差列(エラーバー)の変更")

    def _on_data_structure_changed(self):
        """
        DataEditorDialog から dataChanged シグナルを受け取ったときに呼び出されるスロット。
        データの構造 (値/列/行) が変更された可能性があるため、UIとプロットを更新する。
        """
        if self._get_current_dataset() is None:
            return # (通常はエディタが開いている＝選択中のはずだが念のため)

        # ★ UIの状態(主にX/Y列コンボボックス)を最新のDataFrame情報で更新
        self._update_ui_state()
        # ★ プロットを最新のデータで更新
        self._update_plot()

    def _on_fit_curve(self):
        """
        「曲線フィット」ボタンが押されたときの処理(項目C-004フェーズ1で
        バックグラウンドスレッド化)。ダイアログでの入力収集まではメイン
        スレッド上で同期的に行い、実際の計算(calculate_curve_fit)だけを
        TaskRunner(gui/task_runner.py)経由でバックグラウンドスレッドに委ねる。
        scipy.optimize.curve_fit自体は中断不能なため、このフェーズの主目的は
        キャンセル機能ではなく「スレッド起動→シグナル配送→GUIスレッドでの
        適用→closeEventでの中断待機」という配線を最もリスクの低い対象
        (単発フィット)で検証すること。
        """
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return
        if self._fit_task_runner is not None:
            QMessageBox.information(self, "実行中", "別のフィット処理が実行中です。完了までお待ちください。")
            return
        x_data, y_data = original_dataset.x_data, original_dataset.y_data

        # ダイアログからフィットの種類を取得(カスタム数式選択時は数式文字列も一緒に返る、
        # 項目C-402: 重み付けを使うか、項目C-404: フィット範囲、項目C-403: 初期値
        # 上書き・パラメータ固定・範囲拘束 も併せて返る)
        x_min = float(np.min(x_data)) if len(x_data) else None
        x_max = float(np.max(x_data)) if len(x_data) else None
        (fit_type, custom_formula, use_weighted, x_range,
         p0_overrides, fixed_params, bounds, band_type) = FitDialog.get_fit_type(
            self, x_min=x_min, x_max=x_max
        )
        if fit_type is None:
            return

        sigma = original_dataset.y_err_data if use_weighted else None

        runner = TaskRunner(
            fit_curve_task, x_data, y_data, fit_type, custom_formula=custom_formula,
            sigma=sigma, x_range=x_range,
            p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds,
        )
        runner.succeeded.connect(
            lambda fit: self._on_fit_curve_succeeded(
                original_dataset, fit_type, custom_formula, sigma, x_range,
                p0_overrides, fixed_params, bounds, band_type, fit,
            )
        )
        runner.failed.connect(self._on_fit_curve_failed)
        self._fit_task_runner = runner
        self.fit_curve_button.setEnabled(False)
        runner.start()

    def _cleanup_fit_task_runner(self):
        """
        _fit_task_runner の後始末。gui/main_window.py の _data_load_task_runner と
        同じ「wait()でブロッキング待機→deleteLater()→参照をNoneに戻す」手順
        (closeEventからの再利用も想定、詳細はclose_event側のコメント参照)。
        """
        if self._fit_task_runner is not None:
            self._fit_task_runner.wait()
            self._fit_task_runner.deleteLater()
            self._fit_task_runner = None
        self.fit_curve_button.setEnabled(True)

    def _on_fit_curve_failed(self, error_message):
        self._cleanup_fit_task_runner()
        QMessageBox.warning(self, "フィットエラー", f"フィッティングに失敗しました:\n{error_message}")

    def _on_fit_curve_succeeded(self, original_dataset, fit_type, custom_formula, sigma, x_range,
                                 p0_overrides, fixed_params, bounds, band_type, fit):
        """
        バックグラウンドで完了したフィット計算(fit dict、calculate_curve_fitの
        戻り値と同じ形)をメインスレッド側で適用する。以前は_on_fit_curve()の
        続きとして同期的に実行していたロジックそのもの(振る舞いは無改修)。
        """
        self._cleanup_fit_task_runner()

        popt, params_info = fit['popt'], fit['param_names']
        x_fit, y_fit = fit['x_fit'], fit['y_fit']
        r_squared, residuals = fit['r_squared'], fit['residuals']
        # 残差(residuals)はNaN除外・x_range適用後の点数になるため、
        # 残差プロット用のxもそれに揃える(ResultDialogは長さが一致している前提)。
        residual_x = fit['x_data_used']

        # 結果文字列の作成 (カスタム数式の場合は入力された数式も表示する)
        fit_label = fit_type if custom_formula is None else f"{fit_type} {custom_formula}"
        result_text = f"[{fit_label}] のフィッティング結果:\n"
        for param_name, param_value in zip(params_info, popt):
            result_text += f"  {param_name} = {param_value: .4e}\n"
        result_text += f"  R^2 = {r_squared: .5f}\n"
        if sigma is not None:
            result_text += "  (Y誤差列を重みとして使用)\n"
        if x_range is not None:
            result_text += f"  (フィット範囲: {x_range[0]: .4g} 〜 {x_range[1]: .4g})\n"
        if fixed_params:
            result_text += f"  (固定: {fixed_params})\n"
        if bounds:
            result_text += f"  (範囲拘束: {bounds})\n"

        # 項目C-401: 後続の機能(信頼帯・残差プロット・結果出力・provenance記録)が
        # 再計算なしで再利用できるよう、構造化した形でも結果を保持する。
        fit_result = self._build_fit_result_dict(
            fit_type=fit_type, custom_formula=custom_formula, fit=fit,
            weighted=sigma is not None, x_range=x_range,
            source_dataset=original_dataset,
            p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds,
        )

        # UI/Modelへの反映 (Datasetの追加。元のデータセットと同じフォルダに追加する)
        fit_df = pd.DataFrame({'x_fit': x_fit, 'y_fit': y_fit})
        applied_band_type = self._add_band_columns_to_fit_df(fit_df, fit, band_type)
        fit_dataset = Dataset(
            name=f"Fit ({original_dataset.name})",
            df=fit_df,
            x_col_name='x_fit', y_col_name='y_fit',
            color=original_dataset.color, linestyle='--', marker='None',
            linewidth=original_dataset.linewidth,
            use_secondary_y=original_dataset.use_secondary_y,
            subplot_target=original_dataset.subplot_target,
            fit_info=result_text,
            fit_result=fit_result,
            fit_band_display=applied_band_type,
            provenance=self._build_provenance('curve_fit', fit_result, [original_dataset]),
        )

        self.project.datasets.append(fit_dataset)
        original_item = self._get_dataset_tree_item(original_dataset)
        self._add_dataset_list_item(fit_dataset, original_item.parent() if original_item else None)
        self._update_plot()

        # ★ グラフを見ながら結果を確認できるよう、非モーダル・スクロール可能なダイアログで表示する
        if self.fit_result_dialog is not None:
            self.fit_result_dialog.close()
        fit_csv_data = pd.DataFrame({
            'パラメータ': list(params_info) + ['R^2'],
            '値': list(popt) + [r_squared],
        })
        self.fit_result_dialog = ResultDialog(
            "フィッティング完了", result_text, self, csv_data=fit_csv_data,
            residual_x=residual_x, residual_y=residuals
        )
        self.fit_result_dialog.show()

    def _on_multi_peak_fit(self):
        """
        「多峰フィット」ボタンが押されたときの処理(項目C-409/C-410)。
        _on_fit_curve()と同じ「ダイアログでの入力収集はメインスレッド、
        実計算(calculate_multi_peak_fit)はTaskRunner経由でバックグラウンド」
        という配線を踏襲する。ピーク配置クリックモード(項目C-410、
        gui/mixins/peak_placement_mixin.py)で集めた self._pending_peak_guesses を
        ダイアログの初期値テーブルへ引き継ぎ、ダイアログを閉じた時点(OK/Cancel
        いずれでも)でクリアする(ダイアログ内でさらに編集・追加された内容は
        ダイアログのテーブルにのみ残る、ペンディング状態と重複保持しない)。
        """
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return
        if self._multi_peak_fit_task_runner is not None:
            QMessageBox.information(self, "実行中", "別のフィット処理が実行中です。完了までお待ちください。")
            return
        x_data, y_data = original_dataset.x_data, original_dataset.y_data

        component_type, baseline_type, initial_guesses = MultiPeakFitDialog.get_multi_peak_fit_settings(
            self, x_data=x_data, y_data=y_data, initial_guesses=list(self._pending_peak_guesses)
        )
        self._clear_pending_peak_guesses()
        if getattr(self, 'peak_placement_mode_enabled', False):
            self.peak_placement_action.setChecked(False)
            self._toggle_peak_placement_mode(False)
        if component_type is None:
            return

        runner = TaskRunner(
            multi_peak_fit_task, x_data, y_data, component_type, initial_guesses,
            baseline_type=baseline_type,
        )
        runner.succeeded.connect(
            lambda fit: self._on_multi_peak_fit_succeeded(original_dataset, fit)
        )
        runner.failed.connect(self._on_multi_peak_fit_failed)
        self._multi_peak_fit_task_runner = runner
        self.multi_peak_fit_button.setEnabled(False)
        runner.start()

    def _cleanup_multi_peak_fit_task_runner(self):
        """_multi_peak_fit_task_runner の後始末(_cleanup_fit_task_runnerと同じ手順)。"""
        if self._multi_peak_fit_task_runner is not None:
            self._multi_peak_fit_task_runner.wait()
            self._multi_peak_fit_task_runner.deleteLater()
            self._multi_peak_fit_task_runner = None
        self.multi_peak_fit_button.setEnabled(True)

    def _on_multi_peak_fit_failed(self, error_message):
        self._cleanup_multi_peak_fit_task_runner()
        QMessageBox.warning(self, "多峰分離フィットエラー", f"フィッティングに失敗しました:\n{error_message}")

    def _on_multi_peak_fit_succeeded(self, original_dataset, fit):
        """
        バックグラウンドで完了した多峰分離フィット計算(fit dict、
        calculate_multi_peak_fit()の戻り値と同じ形)をメインスレッド側で適用する。
        _on_fit_curve_succeeded()と対になる処理だが、今回のスコープでは
        C-403のp0上書き/固定/範囲拘束UI・重み付け・フィット範囲・信頼帯は
        含めない(パラメータ名が成分数に応じて動的になるためC-403の
        テーブルとは噛み合わず、いずれも単峰版で既にカバー済みの機能である
        ため、多峰版での再現は将来の拡張とする)。
        """
        self._cleanup_multi_peak_fit_task_runner()

        popt, params_info = fit['popt'], fit['param_names']
        x_fit, y_fit = fit['x_fit'], fit['y_fit']
        r_squared, residuals = fit['r_squared'], fit['residuals']
        residual_x = fit['x_data_used']

        component_label = dict(MultiPeakFitDialog.COMPONENT_TYPES).get(
            fit['component_type'], fit['component_type']
        )
        fit_label = f"多峰分離({component_label} x{fit['n_components']})"
        result_text = f"[{fit_label}] のフィッティング結果:\n"
        for param_name, param_value in zip(params_info, popt):
            result_text += f"  {param_name} = {param_value: .4e}\n"
        result_text += f"  R^2 = {r_squared: .5f}\n"

        fit_result = self._build_multi_peak_fit_result_dict(fit, source_dataset=original_dataset)

        fit_df = pd.DataFrame({'x_fit': x_fit, 'y_fit': y_fit})
        fit_dataset = Dataset(
            name=f"MultiPeakFit ({original_dataset.name})",
            df=fit_df,
            x_col_name='x_fit', y_col_name='y_fit',
            color=original_dataset.color, linestyle='--', marker='None',
            linewidth=original_dataset.linewidth,
            use_secondary_y=original_dataset.use_secondary_y,
            subplot_target=original_dataset.subplot_target,
            fit_info=result_text,
            fit_result=fit_result,
            provenance=self._build_provenance('multi_peak_fit', fit_result, [original_dataset]),
        )

        self.project.datasets.append(fit_dataset)
        original_item = self._get_dataset_tree_item(original_dataset)
        self._add_dataset_list_item(fit_dataset, original_item.parent() if original_item else None)
        self._update_plot()

        if self.fit_result_dialog is not None:
            self.fit_result_dialog.close()
        fit_csv_data = pd.DataFrame({
            'パラメータ': list(params_info) + ['R^2'],
            '値': list(popt) + [r_squared],
        })
        self.fit_result_dialog = ResultDialog(
            "多峰分離フィット完了", result_text, self, csv_data=fit_csv_data,
            residual_x=residual_x, residual_y=residuals
        )
        self.fit_result_dialog.show()

    @staticmethod
    def _build_multi_peak_fit_result_dict(fit, source_dataset):
        """
        calculate_multi_peak_fit()の戻り値から、Dataset.fit_result(項目C-401)に
        保持するプレーンなdictを組み立てる(_build_fit_result_dictの多峰版)。
        'component_type'/'n_components' は core/methods_text.py の
        describe_operation() がそのままprovenance['params']経由で参照するキー名
        のため、勝手にリネームしないこと。
        """
        popt, pcov, perr = fit['popt'], fit['pcov'], fit['perr']
        return {
            'fit_type': 'multi_peak',
            'component_type': fit['component_type'],
            'n_components': fit['n_components'],
            'baseline_type': fit['baseline_type'],
            'components': fit['components'],
            'param_names': list(fit['param_names']),
            'params': [float(v) for v in popt],
            'param_errors': [float(v) for v in perr],
            'covariance': [[float(v) for v in row] for row in pcov],
            'r_squared': float(fit['r_squared']),
            'residuals': [float(v) for v in fit['residuals']],
            'residual_x': [float(v) for v in fit['x_data_used']],
            'source_dataset_id': source_dataset.dataset_id,
            'source_dataset_name': source_dataset.name,
        }

    @staticmethod
    def _build_provenance(operation, params, source_datasets):
        """
        派生データセット生成時にDataset.provenanceへ設定する共通ヘルパー
        (項目C-1101)。source_datasetsは親となったDatasetオブジェクトの
        リスト(1個なら単純な派生、複数ならデータセット間演算のような
        合成処理)。paramsは素のPython型のみで構成すること(pickle/JSON
        双方でそのまま往復できるようにするため、Dataset.fit_result等と
        同じ制約)。
        """
        return {
            'operation': operation,
            'params': params,
            'source_dataset_ids': [ds.dataset_id for ds in source_datasets],
            'source_dataset_names': [ds.name for ds in source_datasets],
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _build_fit_result_dict(fit_type, custom_formula, fit, weighted, x_range, source_dataset,
                                p0_overrides=None, fixed_params=None, bounds=None):
        """
        calculate_curve_fit() の戻り値(numpy配列を含む)から、Dataset.fit_result
        (項目C-401)に保持する、pickle/JSON双方でそのまま往復できるプレーンな
        dictを組み立てる(numpy.float64等はJSON非対応のため、ここで素のPython
        型に変換しておく)。

        p0_overrides/fixed_params/boundsは項目C-403(パラメータの初期値・固定・
        範囲拘束UI)。何もカスタマイズしなかった場合は空dict/Noneのどちらでも
        呼び出せるが、provenance(このフィットがどう設定されたか)としては
        空dictのまま保持する(Noneに正規化しない — 「未指定」と「空dict」を
        区別する必要はないため、単純にdict(...)へ通すだけで良い)。
        """
        popt, pcov, perr = fit['popt'], fit['pcov'], fit['perr']
        return {
            'fit_type': fit_type,
            'custom_formula': custom_formula,
            'param_names': list(fit['param_names']),
            'params': [float(v) for v in popt],
            'param_errors': [float(v) for v in perr],
            'covariance': [[float(v) for v in row] for row in pcov],
            'r_squared': float(fit['r_squared']),
            'residuals': [float(v) for v in fit['residuals']],
            'residual_x': [float(v) for v in fit['x_data_used']],
            'weighted': bool(weighted),
            'x_range': [float(x_range[0]), float(x_range[1])] if x_range is not None else None,
            'source_dataset_id': source_dataset.dataset_id,
            'source_dataset_name': source_dataset.name,
            # 項目C-403: どのパラメータをどう上書き/固定/拘束してこの結果が
            # 得られたかのprovenance(すべて素のPython型なので変換不要)。
            'p0_overrides': dict(p0_overrides) if p0_overrides else {},
            'fixed_params': dict(fixed_params) if fixed_params else {},
            'bounds': {k: [float(v[0]), float(v[1])] for k, v in bounds.items()} if bounds else {},
        }

    @staticmethod
    def _add_band_columns_to_fit_df(fit_df, fit, band_type):
        """
        項目C-405: band_type("confidence"/"prediction")が指定されていれば、
        calculate_confidence_band()を呼んでfit_dfに'y_lower'/'y_upper'列を追加する
        (gui/canvas.pyがDataset.fit_band_displayとあわせてfill_betweenで描画する)。
        band_typeがNone、または自由度不足等でcalculate_confidence_band()が
        ValueErrorを送出した場合は、列を追加せずNoneを返す(フィット自体は
        成功しているため、信頼帯が計算できないという理由だけでフィット結果の
        追加全体を失敗させない)。

        Returns:
            str | None: 実際に列を追加できた場合はband_typeそのまま、
                できなかった場合はNone(呼び出し側はこれをDataset.fit_band_display
                にそのまま渡せる)。
        """
        if band_type is None:
            return None
        try:
            band = calculate_confidence_band(
                fit['x_fit'], fit['fit_func'], fit['popt'], fit['pcov'], fit['residuals'],
                band_type=band_type,
            )
        except ValueError:
            return None
        fit_df['y_lower'] = band['y_lower']
        fit_df['y_upper'] = band['y_upper']
        return band_type

    @staticmethod
    def _format_fit_result_text(fit_result):
        """
        Dataset.fit_result (項目C-401で永続化された構造化フィット結果) だけから、
        _on_fit_curve() が表示している結果テキストと同じ体裁の文字列を組み立てる。

        _on_fit_curve() 内のインライン文字列組み立てロジック(popt/params_infoなど
        フィット直後のローカル変数を参照する)を直接extractしたものではなく、
        fit_result辞書のキーだけを参照するよう書き直した別関数として用意した
        (fit_resultはfit_type/params/param_names/r_squared/weighted/x_range/
        fixed_params/boundsをすべて素のPython型で保持しているため、同じ体裁を
        再現するのに再計算・再フィットは一切不要)。_on_fit_curve()側の
        既存コード・既存テストには一切手を入れず、フィット直後の表示と
        エクスポート時の再表示の両方が将来的にズレないよう、書式のロジックは
        ここに一本化してある。
        """
        fit_type = fit_result.get('fit_type')
        custom_formula = fit_result.get('custom_formula')
        fit_label = fit_type if custom_formula is None else f"{fit_type} {custom_formula}"
        result_text = f"[{fit_label}] のフィッティング結果:\n"
        for param_name, param_value in zip(fit_result.get('param_names', []), fit_result.get('params', [])):
            result_text += f"  {param_name} = {param_value: .4e}\n"
        result_text += f"  R^2 = {fit_result.get('r_squared', float('nan')): .5f}\n"
        if fit_result.get('weighted'):
            result_text += "  (Y誤差列を重みとして使用)\n"
        x_range = fit_result.get('x_range')
        if x_range is not None:
            result_text += f"  (フィット範囲: {x_range[0]: .4g} 〜 {x_range[1]: .4g})\n"
        if fit_result.get('fixed_params'):
            result_text += f"  (固定: {fit_result['fixed_params']})\n"
        if fit_result.get('bounds'):
            result_text += f"  (範囲拘束: {fit_result['bounds']})\n"
        return result_text

    def _on_copy_methods_text(self):
        """
        「「方法」文をコピー...」メニューの処理(項目C-1102)。
        カレントデータセットのprovenanceチェーン(項目C-1101)から
        generate_methods_text()で組み立てた日本語の説明文をクリップボードへ
        コピーする(論文の「方法」節にそのまま使える体裁を意図している)。
        """
        dataset = self._get_current_dataset()
        if dataset is None or dataset.provenance is None:
            return
        text = generate_methods_text(dataset, self.project)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("「方法」文をクリップボードにコピーしました", 3000)

    def _on_export_fit_result(self):
        """
        「フィット結果のエクスポート...」メニューの処理(項目C-413)。

        「曲線の新規データセット化」「表CSV」は項目C-401の時点で既に
        _on_fit_curve() 実行直後に一度提供済みなので、このメニューが埋める
        本当のギャップは (a) フィットをやり直さずに後から何度でも表/CSVを
        再表示できること、(b) フィット結果の要約をグラフ上の注釈として
        焼き込めること、の2点(項目C-413のdocstring/ロードマップ参照)。

        カレントデータセットの dataset.fit_result (項目C-401で永続化済みの
        構造化結果) だけから結果を再構成する。calculate_curve_fit() は
        一切呼び出さない(再フィットしない)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        fit_result = dataset.fit_result
        if fit_result is None:
            # メニュー項目はsetEnabledでグレーアウトしているが、それでも
            # 呼び出された場合(あるいは将来別経路から呼ばれた場合)に備えた
            # 防御的なフォールバック。
            QMessageBox.information(
                self, "フィット結果のエクスポート",
                "このデータセットは曲線フィットの結果を持っていません。\n"
                "曲線フィットで生成されたデータセット(名前が「Fit (...)」の\n"
                "もの、またはfit_resultを保持しているもの)を選択してください。"
            )
            return

        result_text = self._format_fit_result_text(fit_result)
        csv_data = pd.DataFrame({
            'パラメータ': list(fit_result.get('param_names', [])) + ['R^2'],
            '値': list(fit_result.get('params', [])) + [fit_result.get('r_squared')],
        })

        # ★ _on_fit_curve() と同じく、非モーダル・スクロール可能なダイアログで表示する
        # (self.fit_result_dialog を使い回すのも_on_fit_curve()と同じ挙動)
        if self.fit_result_dialog is not None:
            self.fit_result_dialog.close()
        self.fit_result_dialog = ResultDialog(
            "フィット結果のエクスポート", result_text, self, csv_data=csv_data,
            residual_x=fit_result.get('residual_x'), residual_y=fit_result.get('residuals'),
        )
        self.fit_result_dialog.show()

        # 「注釈焼込」(項目C-413のもう一つの柱)は、CSV再エクスポートとは
        # 独立した任意操作として、確認ダイアログ経由で提供する
        # (ダイアログを重ねるのではなく、この1つのメニュー操作の流れの中で
        # 完結させることで、新しい設定ダイアログを追加しないシンプルな設計にする)。
        reply = QMessageBox.question(
            self, "フィット結果のエクスポート",
            "このフィット結果の要約(パラメータ値±誤差・R^2)を、\n"
            "グラフ上のテキスト注釈として焼き込みますか?\n"
            "(焼き込み後は注釈モードで通常の注釈と同様に移動・編集・削除できます)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._burn_fit_result_annotation(dataset, fit_result)

    def _burn_fit_result_annotation(self, dataset, fit_result):
        """
        フィット結果の要約(フィット式・パラメータ値±誤差・R^2)を、既存の
        注釈システム(gui/mixins/annotation_mixin.py)と全く同じデータモデル
        (project.all_plot_settings[axis_index]['annotations'] に積む
        {'type':'text', 'text', 'xy', 'xytext', 'color'} 辞書)へ追加する
        (項目C-413「注釈焼込」)。手動でクリック配置する注釈と同じ
        _add_annotation() 経由・同じ SetAnnotationsCommand 経由で追加するため、
        Undo/Redoが効き、焼き込み後は注釈モードで通常どおり移動・編集・削除できる
        (このハンドラ専用の特別な描画経路は一切持たない)。

        アンカー位置: フィット対象データセット(dataset、フィット曲線
        x_fit/y_fit を持つDatasetそのもの)のデータ点の中央インデックスを採用する。
        ピーク位置(argmax)やカーブの端ではなく中央点を選んだのは、線形/指数/
        対数など単調な形状のフィットではargmaxが曲線の端に寄ってしまい、
        逆にグラフ全体のどのフィット形状でもそこそこ無難な位置になるのは
        中央点だと判断したため(項目C-413の指示にある「固定オフセット」案より、
        曲線の存在するx範囲の中で確実に曲線上に乗る点であることを優先した)。
        """
        axis_index = dataset.subplot_target
        if axis_index is None or axis_index >= len(self.project.all_plot_settings):
            QMessageBox.warning(
                self, "フィット結果のエクスポート",
                "注釈を追加する対象のプロットが見つかりませんでした。"
            )
            return

        x_data, y_data = dataset.x_data, dataset.y_data
        if len(x_data) == 0:
            QMessageBox.warning(
                self, "フィット結果のエクスポート",
                "フィット曲線にデータ点が無いため、注釈を追加できませんでした。"
            )
            return
        mid_index = len(x_data) // 2
        anchor_x, anchor_y = float(x_data[mid_index]), float(y_data[mid_index])

        fit_type = fit_result.get('fit_type', '')
        summary_lines = [f"フィット: {fit_type}"]
        param_names = fit_result.get('param_names', [])
        params = fit_result.get('params', [])
        param_errors = fit_result.get('param_errors', [None] * len(params))
        for name, value, err in zip(param_names, params, param_errors):
            if err is not None:
                summary_lines.append(f"{name} = {value:.4g} ± {err:.4g}")
            else:
                summary_lines.append(f"{name} = {value:.4g}")
        r_squared = fit_result.get('r_squared')
        if r_squared is not None:
            summary_lines.append(f"R^2 = {r_squared:.5f}")
        summary_text = "\n".join(summary_lines)

        annotation = {
            'type': 'text', 'text': summary_text,
            'xy': (anchor_x, anchor_y), 'xytext': (anchor_x, anchor_y),
            'color': '#000000',
        }
        self._add_annotation(axis_index, annotation, description="フィット結果の注釈焼き込み")
        self.statusBar().showMessage("フィット結果を注釈として焼き込みました", 3000)

    def _on_secondary_y_changed(self):
        """
        「第2Y軸 (右側) を使用」チェックボックスが変更されたときの処理。
        複数選択時は選択中の全データセットに一括適用する。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            return

        new_value = self.use_secondary_y_checkbox.isChecked()

        # Dataset オブジェクトの use_secondary_y 属性を Undo/Redo可能に更新
        # (軸の割り当てが変わるため、プロット全体の再描画が必要。
        #  これは _refresh_after_dataset_property_change 内で行われる)
        is_batch = len(selected_datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"第2Y軸使用の一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._push_dataset_property_command(
                dataset,
                {'use_secondary_y': dataset.use_secondary_y},
                {'use_secondary_y': new_value},
                description="第2Y軸使用の変更"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_dataset_tree_item_clicked(self, item, column):
        """
        データセットリスト(ツリー)のアイテムがクリックされたときの処理(項目C-907)。
        目アイコン専用列(DATASET_TREE_VISIBILITY_COLUMN)のクリックだけを拾い、
        対応するデータセットの表示/非表示 (visible) を Undo/Redo 可能にトグルする。
        削除ではなく非表示化なので、データやスタイル設定はそのまま保持される。

        複数選択中に、その選択に含まれるアイテムの目アイコンをクリックした場合は
        (_on_secondary_y_changed 等、既存の一括変更と同じ方針で) 選択中の全データセットへ
        まとめて適用する。選択に含まれないアイテムを単独クリックした場合は
        そのデータセット1件だけを切り替える。
        """
        if column != DATASET_TREE_VISIBILITY_COLUMN:
            return
        dataset = item.data(0, Qt.ItemDataRole.UserRole)
        if dataset is None:
            # フォルダアイテムには目アイコン列は無い(表示/非表示の対象外)
            return

        new_value = not dataset.visible

        # ★ Dataset は値ベースの __eq__ を持つ dataclass (df列を含むため
        #   `in` 演算子で == 比較されると DataFrame の真偽値判定エラーになる、
        #   _find_dataset_row のコメント参照)。選択中に含まれるかどうかは
        #   オブジェクト同一性(is)で判定する。
        selected_datasets = self._get_selected_datasets()
        is_part_of_multi_selection = len(selected_datasets) > 1 and any(
            ds is dataset for ds in selected_datasets
        )
        targets = selected_datasets if is_part_of_multi_selection else [dataset]

        is_batch = len(targets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"表示/非表示の一括切替 ({len(targets)}件)")
        for ds in targets:
            self._push_dataset_property_command(
                ds,
                {'visible': ds.visible},
                {'visible': new_value},
                description="データセットの表示/非表示切替"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_find_peaks(self):
        """「ピーク検出」ボタンが押されたときの処理"""
        original_dataset = self._get_current_dataset()
        if original_dataset is None:
            return

        x_data, y_data = original_dataset.x_data, original_dataset.y_data

        if len(x_data) < 3:
            QMessageBox.warning(self, "ピーク検出", "データ点数が少なすぎます (最低3点必要)。")
            return

        settings = PeakSettingsDialog.get_peak_settings(self)
        if settings is None:
            return

        peak_type = settings.get("peak_type", "上に凸 (Peaks)")

        try:
            # ★ 計算はモジュールに丸投げ。項目C-411: 位置(X,Y)だけでなく
            # FWHM/面積/重心も一括で定量化する(calculate_peaksの単純な
            # (x, y)版はcalculate_peak_quantificationが内部で共有ロジック
            # (_peak_detection_signal_and_kwargs)を使って計算するため、
            # 検出結果自体は従来と完全に同じ)。
            quant = calculate_peak_quantification(x_data, y_data, peak_type, settings)
        except Exception as e:
            QMessageBox.warning(self, "ピーク検出エラー", f"エラーが発生しました:\n{e}")
            return

        peak_x, peak_y = quant['peak_x'], quant['peak_y']
        fwhm, area, centroid = quant['fwhm'], quant['area'], quant['centroid']

        if len(peak_x) == 0:
            QMessageBox.information(self, "ピーク検出", f"指定された条件で {peak_type} は見つかりませんでした。")
            return

        # 結果文字列の作成 (X座標順にソート)
        sort_order = np.argsort(peak_x)
        result_text = (
            f"検出された {peak_type} ({len(peak_x)}個):\n"
            "  X座標\t\tY座標\t\tFWHM\t\t面積\t\t重心X\n" + "-" * 70 + "\n"
        )
        for i in sort_order:
            result_text += (
                f"  {peak_x[i]:.4g}\t\t{peak_y[i]:.4g}\t\t{fwhm[i]:.4g}"
                f"\t\t{area[i]:.4g}\t\t{centroid[i]:.4g}\n"
            )

        # UI/Modelへの反映 (元のデータセットと同じフォルダに追加する)
        peak_marker = 'v' if "下に凸" not in peak_type else '^'
        peak_color = 'red' if "下に凸" not in peak_type else 'blue'

        peaks_df = pd.DataFrame({'peak_x': peak_x, 'peak_y': peak_y})
        peak_dataset = Dataset(
            name=f"{peak_type.split(' ')[0]} ({original_dataset.name})",
            df=peaks_df,
            x_col_name='peak_x', y_col_name='peak_y',
            plot_type='Scatter', color=peak_color, linestyle='None',
            marker=peak_marker, markersize=8,
            use_secondary_y=original_dataset.use_secondary_y,
            subplot_target=original_dataset.subplot_target
        )

        self.project.datasets.append(peak_dataset)
        original_item = self._get_dataset_tree_item(original_dataset)
        self._add_dataset_list_item(peak_dataset, original_item.parent() if original_item else None)
        self._update_plot()

        # ★ グラフを見ながら結果を確認できるよう、非モーダル・スクロール可能なダイアログで表示する
        # (検出数が多いと行数が非常に多くなりうるため、スクロールできることが重要)
        if self.peak_result_dialog is not None:
            self.peak_result_dialog.close()
        peak_csv_data = pd.DataFrame({
            'X座標': peak_x[sort_order],
            'Y座標': peak_y[sort_order],
            'FWHM': fwhm[sort_order],
            '面積': area[sort_order],
            '重心X': centroid[sort_order],
        })
        self.peak_result_dialog = ResultDialog("ピーク検出完了", result_text, self, csv_data=peak_csv_data)
        self.peak_result_dialog.show()
