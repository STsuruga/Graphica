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
import logging
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFileDialog, QInputDialog, QMenu)

from graphica.core.analysis import (sample_standard_deviation)
from graphica.core.commands import (SetDatasetPropertiesCommand, ReorderDatasetsCommand)
from graphica.core.dataset import Dataset, COLOR_BY_COLUMN_PLOT_TYPE, linestyle_name
from graphica.core.label_utils import infer_axis_label_from_column_name
from graphica.gui.workers import BUILTIN_DATA_FILE_EXTENSIONS
from graphica.core.plugin_api import get_registered_importer_extensions
from graphica.gui.data_editor import DataEditorDialog
from graphica.gui.dialogs import (NewDatasetDialog)
from graphica.gui.dataset_style_icon import (
    make_dataset_style_icon, make_dataset_visibility_icon, apply_dataset_visibility_text_style,
    DATASET_TREE_VISIBILITY_COLUMN,
)

logger = logging.getLogger(__name__)

# エラーバー用の誤差列コンボボックスで「誤差列を使わない」ことを表す選択肢
NO_ERROR_COLUMN_LABEL = "(なし)"

# データポイントラベルの「内容」コンボボックスで、Y値そのものを表示することを示す選択肢
POINT_LABEL_Y_VALUE_LABEL = "Y値"


class DatasetMixin:
    def _on_add_dataset(self):
        """「データセット追加」ボタンからの読み込み（Excel対応版）"""
        # ★ .xls と .xlsx をフィルターに追加
        # プラグインがregister_importer()(項目B-1)で登録した拡張子も追加する
        plugin_extensions = get_registered_importer_extensions()
        plugin_pattern = ''.join(f' *{ext}' for ext in plugin_extensions)
        builtin_pattern = ' '.join(f'*{ext}' for ext in BUILTIN_DATA_FILE_EXTENSIONS)
        file_path, _ = QFileDialog.getOpenFileName(
            self, "データファイルを選択", "",
            f"Data Files ({builtin_pattern}{plugin_pattern});;All Files (*)"
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

    def _set_all_datasets_visibility(self, visible):
        """
        プロジェクト全体の全データセットの表示/非表示をまとめて切り替える
        (項目150、C-907の一括表示切替)。フォルダ限定の
        _set_folder_datasets_visibility とは異なり、フォルダ構造に関わらず
        プロジェクト内の全データセットを対象にする。
        """
        datasets = list(self.project.datasets)
        if not datasets:
            return
        is_batch = len(datasets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"全データセットの表示/非表示切替 ({len(datasets)}件)")
        for ds in datasets:
            self._push_dataset_property_command(
                ds, {'visible': ds.visible}, {'visible': visible},
                description="データセットの表示/非表示切替"
            )
        if is_batch:
            self.undo_stack.endMacro()

    def _on_show_all_datasets(self):
        """「すべて表示」メニューの処理(項目150、C-907)。"""
        self._set_all_datasets_visibility(True)

    def _on_hide_all_datasets(self):
        """「すべて非表示」メニューの処理(項目150、C-907)。"""
        self._set_all_datasets_visibility(False)

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
        """
        データセットツリーを右クリックしたときのコンテキストメニュー。

        中身の構築は _populate_dataset_actions_menu() が持つ。同じメニューを
        ツールバーの「データセット操作」ボタンからも開けるようにするため
        (実機フィードバック: 右クリックでしか辿り着けないのが分かりにくい)、
        「どこに出すか」だけをこちらが決める。
        """
        menu = QMenu(self)
        self._populate_dataset_actions_menu(menu)
        menu.exec(self.ui.dataset_list_widget.viewport().mapToGlobal(pos))

    def _populate_dataset_actions_menu(self, menu):
        """
        データセット操作メニューの中身を menu に構築する(右クリック用と
        ツールバー用で共有)。

        ★ 改善ボード C-2: 以前は約30項目がほぼフラットに並んでおり(区切り線は4本)、
        特にデータ処理系9項目が他と同列にずらりと続いて目的の操作を探しにくかった。
        内容が自然に分かれる5つのサブメニューにまとめる:
        「データ処理 ▶」「解析・注釈 ▶」「複数データセット ▶」
        「エクスポート ▶」「タブ操作 ▶」。
        フォルダ操作・スタイルのコピー/貼り付け・再読み込み・削除といった
        「1クリックで終わる頻出操作」はトップレベルに残す。

        ★ 開くたびに作り直す(選択状態で出し入れする項目があるため)。
        右クリック側は毎回新しい QMenu を渡す使い捨て、ツールバー側は永続
        QMenu を aboutToShow のたびに clear() して詰め直す。どちらも
        メニューバー側のサブメニューのような self.xxx への永続参照は要らないが、
        PySide6 が作ったサブメニューを途中で回収しないよう、Python側の参照は
        メニュー自身に持たせておく(下の _graphica_submenus)。
        """
        menu.clear()
        submenus = []

        def add_submenu(title):
            """空のまま残さないよう、実際に項目を足したものだけ後で menu へ繋ぐ。"""
            sub = QMenu(title, menu)
            submenus.append(sub)
            return sub

        data_proc_menu = add_submenu("データ処理")
        analysis_menu = add_submenu("解析・注釈")
        multi_menu = add_submenu("複数データセット")
        export_menu = add_submenu("エクスポート")
        tab_menu = add_submenu("タブ操作")
        new_folder_action = menu.addAction("新しいフォルダ")
        new_folder_action.triggered.connect(self._on_new_folder)

        # 一括表示切替(項目150、C-907): フォルダ内限定の下記アクション群とは別に、
        # プロジェクト全体を対象にした版を常に(フォルダ選択の有無に関わらず)出す。
        if self.project.datasets:
            show_all_datasets_action = menu.addAction("すべて表示")
            show_all_datasets_action.triggered.connect(self._on_show_all_datasets)

            hide_all_datasets_action = menu.addAction("すべて非表示")
            hide_all_datasets_action.triggered.connect(self._on_hide_all_datasets)

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
            copy_style_action.triggered.connect(self.transfer.copy_style)

            paste_style_action = menu.addAction("スタイルを貼り付け")
            paste_style_action.setEnabled(self.transfer.copied_style is not None)
            paste_style_action.triggered.connect(self.transfer.paste_style)

            # 元ファイルからの再読み込み(項目C-103): ファイル読み込みで作成された
            # データセット(dataset.source_fileを保持)のみ有効。クリップボード貼り付け・
            # データセット間演算・プラグインprocessor/analyzerの生成物等、元ファイルを
            # 持たないデータセットではグレーアウトする。
            reload_action = menu.addAction("元ファイルから再読み込み")
            reload_action.setEnabled(bool(self._get_current_dataset().source_file))
            reload_action.triggered.connect(self.transfer.reload_from_source)

            # 規格化(ノーマライズ、項目78): 曲線フィット/ピーク検出と同様、1つの
            # データセット(フォーカス中のカレントアイテム)に対する操作なので、
            # 複数選択かどうかに関わらずこのブロック(カレントデータセットが
            # 存在する場合)に置く。データセット間演算(2件選択が必須)とは異なる。
            normalize_action = data_proc_menu.addAction("規格化(ノーマライズ)...")
            normalize_action.triggered.connect(self.processing.normalize)

            # Savitzky-Golayフィルタ(平滑化/微分、項目C-301/C-302): 規格化と同じく
            # カレント1件のデータセットから新しいデータセットを1つ作る操作。
            savgol_action = data_proc_menu.addAction("Savitzky-Golayフィルタ(平滑化/微分)...")
            savgol_action.triggered.connect(self.processing.savgol_smooth)

            # ベースライン補正(ALS/多項式/ラバーバンド/手動点、項目C-308):
            # 上記と同じく「カレント1件から新しいデータセットを1つ作る」操作。
            baseline_action = data_proc_menu.addAction("ベースライン補正...")
            baseline_action.triggered.connect(self.processing.baseline_correction)

            # 区間積分(台形則/Simpson則、任意でベースライン差し引き、項目C-311):
            # 上記と同じく「カレント1件」を対象にするが、新しいデータセットではなく
            # 積分値(スカラー)をResultDialogで表示する点がSavitzky-Golay/
            # ベースライン補正と異なる(ピーク検出のResultDialog表示に近い)。
            integral_action = data_proc_menu.addAction("区間積分(台形則/Simpson則)...")
            integral_action.triggered.connect(self.processing.interval_integral)

            # 累積積分(項目C-303): 区間積分と同じ台形則/Simpson則だが、こちらは
            # スカラー1個ではなく、Xの各点までの積分値を新しいデータセットとして
            # 追加する(Savitzky-Golay/ベースライン補正と同じ「カレント1件から
            # 新しいデータセットを1つ作る」パターン)。
            cumulative_integral_action = data_proc_menu.addAction("累積積分(台形則/Simpson則)...")
            cumulative_integral_action.triggered.connect(self.processing.cumulative_integral)

            # フィット結果のエクスポート(項目C-413): カレントデータセットが
            # 曲線フィットの結果(dataset.fit_result、項目C-401で永続化)を
            # 持っている場合のみ有効にする。「スタイルを貼り付け」
            # (paste_style_action, 上記)と同じく、常時メニューには出すが
            # 対象外の状態ではグレーアウトするパターンに合わせる。
            # ハンドラ自身も fit_result が無い場合に備えて防御的にチェックする
            # (万一 setEnabled が効かない呼び出し経路があっても親切な警告を出す)。
            export_fit_action = export_menu.addAction("フィット結果のエクスポート...")
            export_fit_action.setEnabled(self._get_current_dataset().fit_result is not None)
            export_fit_action.triggered.connect(self.fitting.show_fit_result)

            # 共通X格子へのリサンプリング/補間(項目C-305): 上記のSavitzky-Golay/
            # ベースライン補正と同じく「カレント1件から新しいデータセットを1つ作る」操作。
            resample_action = data_proc_menu.addAction("共通X格子へのリサンプリング/補間...")
            resample_action.triggered.connect(self.processing.resample)

            # 重複X値の検出(項目C-203): 平均化(新規データセット)または
            # 除去(先頭以外をマスク)を選ばせる。
            duplicate_x_action = data_proc_menu.addAction("重複X値の検出...")
            duplicate_x_action.triggered.connect(self.processing.detect_duplicate_x)

            # 行フィルタ(項目C-204): 条件式を満たさない行をマスク(項目36、非破壊)する。
            row_filter_action = data_proc_menu.addAction("行フィルタ...")
            row_filter_action.triggered.connect(self.processing.filter_rows)

            # カテゴリ列による系列の自動分割(改善ボード D-1): long形式データの
            # 取り込み。行フィルタを条件の数だけ手作業で繰り返す代わりになる
            # 操作なので、その隣に置く。
            split_by_column_action = data_proc_menu.addAction("列の値で系列に分割...")
            split_by_column_action.triggered.connect(self.processing.split_by_column)

            # 統計的外れ値検出(項目C-306): 検出のみ/マスクへの適用はユーザーが
            # ダイアログのチェックボックスで明示的に選ぶ(自動では適用しない)。
            outlier_action = data_proc_menu.addAction("外れ値検出(Z-score/IQR)...")
            outlier_action.triggered.connect(self.processing.detect_outliers)

            # 統計値アンカーラベル(項目C-708): カレントデータセットのR²/Y平均/
            # Y標準偏差/Y最大値/Y最小値のいずれかを、データ座標ではなくAxes相対
            # 座標(左上起点に縦積み)に追加する。固定テキストではなく描画のたびに
            # 再計算される(gui/canvas.pyの_compute_stat_label_text)ため、
            # データやフィットを更新すると値が自動的に追従する。
            add_stat_label_action = analysis_menu.addAction("統計値アンカーラベルを追加...")
            add_stat_label_action.triggered.connect(self.overlays.add_stat_label)

            # インセット(拡大図)+拡大範囲の指示線(項目138、C-711)
            add_inset_action = analysis_menu.addAction("インセット(拡大図)を追加...")
            add_inset_action.triggered.connect(self.overlays.add_inset)

            # ピーク位置へのスマート自動ラベル(項目134、C-707)
            add_peak_labels_action = analysis_menu.addAction("ピーク位置に自動ラベルを追加...")
            add_peak_labels_action.triggered.connect(self.peaks.add_peak_labels)

            # ヒストグラム / カーネル密度推定(項目115、C-505): カレント1件の
            # 任意の数値列を集計し、新しいデータセットを1つ作る(上記の
            # Savitzky-Golay/ベースライン補正/累積積分と同じ「カレント1件から
            # 新しいデータセットを1つ作る」パターン)。
            histogram_action = analysis_menu.addAction("ヒストグラム / KDE...")
            histogram_action.triggered.connect(self.processing.histogram_or_kde)

            # 「方法」文の自動生成(項目C-1102): カレントデータセットが処理履歴
            # (dataset.provenance、項目C-1101)を持っている場合のみ有効にする
            # (export_fit_actionと同じ、常時メニューには出すが対象外の状態では
            # グレーアウトするパターン)。元データ(provenance無し)には
            # 生成する意味のある「方法」が無いため対象外。
            copy_methods_text_action = export_menu.addAction("「方法」文をコピー...")
            copy_methods_text_action.setEnabled(self._get_current_dataset().provenance is not None)
            copy_methods_text_action.triggered.connect(self.transfer.copy_methods_text)

        selected_count = len(self._get_selected_datasets())
        if selected_count >= 2:
            if selected_count == 2:
                arithmetic_action = multi_menu.addAction("データセット間演算...")
                arithmetic_action.triggered.connect(self.processing.arithmetic)

                # X軸アライメント(項目105、C-307): データセット間演算と同じ
                # 「ちょうど2件」限定の操作(A=基準、B=位置合わせ対象は選択順)。
                align_action = multi_menu.addAction("X軸アライメント(相互相関)...")
                align_action.triggered.connect(self.processing.align_selected)

            # 複数データセットの平均±SD生成(項目C-312): 2件以上を対象にする
            # (「ちょうど2件」限定のデータセット間演算とは異なる)。
            mean_sd_action = multi_menu.addAction("平均±SD生成...")
            mean_sd_action.triggered.connect(self.processing.mean_and_sd_of_selected)

            batch_calc_action = multi_menu.addAction("バッチ列計算...")
            batch_calc_action.triggered.connect(self.processing.batch_column_calculate)

            batch_fit_action = multi_menu.addAction("バッチカーブフィット...")
            batch_fit_action.triggered.connect(self.fitting.batch_fit_selected)

        if self._get_selected_datasets():
            export_data_action = export_menu.addAction("データ表をファイルに書き出す...")
            export_data_action.triggered.connect(self.transfer.export_data)

            # タブ間のデータセットコピー/移動(項目C-905): タブ=完全に独立した
            # プロジェクトという設計上、他のタブが無ければ意味を成さないため
            # 常に表示しつつハンドラ側で案内する(setEnabledで隠すより、
            # 「タブが無いから使えない」ことに気づける方が親切なため)。
            copy_to_tab_action = tab_menu.addAction("別のタブへコピー...")
            copy_to_tab_action.triggered.connect(lambda: self.transfer.copy_or_move_to_tab(move=False))

            move_to_tab_action = tab_menu.addAction("別のタブへ移動...")
            move_to_tab_action.triggered.connect(lambda: self.transfer.copy_or_move_to_tab(move=True))

        # ★ 改善ボード C-2: 上の各ブロックで中身を詰めたサブメニューを、ここで
        # まとめて menu に繋ぐ。選択状態によっては1項目も入らないもの
        # (例: 1件だけ選択しているときの「複数データセット」)があるため、
        # 空のサブメニューは出さない(開いても何も無いメニューは邪魔なだけ)。
        attached_any = False
        for sub in submenus:
            if sub.actions():
                if not attached_any:
                    menu.addSeparator()
                    attached_any = True
                menu.addMenu(sub)

        if self.ui.dataset_list_widget.selectedItems():
            menu.addSeparator()
            remove_action = menu.addAction("削除")
            remove_action.triggered.connect(self._on_remove_dataset)

        # サブメニューのPython参照をメニュー自身に持たせる(上のdocstring参照)。
        # 次回の clear() で古い方はまとめて差し替わる。
        menu._graphica_submenus = submenus
        return menu

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

        ★ 改善ボード A-3: 以前はここで project.datasets を直接書き換えており
        Undo できなかった(誤削除するとデータ・スタイル・フィット結果・マスク・
        注釈がまとめて復旧不能になっていた)。実際の削除・復元処理は
        main_window._remove_dataset_items_with_undo() に集約し、
        RemoveDatasetCommand 経由で undo_stack に載せる。
        """
        selected_items = self.ui.dataset_list_widget.selectedItems()
        if not selected_items:
            return # 何も選択されていない

        # 選択された最上位アイテムだけを対象にする
        # (子アイテムも同時に選択されていても、親を消せば一緒に消えるため二重削除は避ける)
        self._remove_dataset_items_with_undo(self._top_level_selected_items(selected_items))

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
          複製などと同様、現状 Undo 非対応の単純な操作として扱う
          (フォルダ構造ごとのUndoは対象外)。削除は改善ボード A-3 で
          RemoveDatasetCommand によりUndo可能になっている。
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
        self._notify_plugins_datasets_changed()

    def _push_dataset_property_command(self, dataset, old_values: dict, new_values: dict, description: str,
                                       skip_if_unchanged=True):
        """
        Dataset のプロパティ変更を Undo/Redo 可能なコマンドとして発行する共通ヘルパー。
        old_values と new_values が同じ (実質的に変更なし) 場合は何もしない。
        値に DataFrame を含むときは == で比べられないので skip_if_unchanged=False で呼ぶ。
        """
        if skip_if_unchanged and old_values == new_values:
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
        self._update_ui_state()  # 選んだデータセットのプロパティをパネルに読み込む
        self._notify_plugins_selection_changed()

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

        ★ v1.4.2 で確認ポップアップを廃止した。以前は点数が環境設定の上限を超えると
          「表示しますか?」と確認していたが、「はい」を選んでも描画側
          (MplCanvas._draw_data)が上限でラベルを省くため、何も表示されなかった。
          実測では ax.annotate() 1件あたり約2.5msかかり、しかもプロパティを変える
          たびの再描画で毎回その時間がかかる(1,000点で約2.5秒、20,000点で約68秒、
          GUIスレッドを止める)。上限を超えて描画させると操作不能になりうるため、
          上限超過時は描かないまま、理由をパネルに表示する(_update_point_labels_limit_note)。
        """
        self._on_property_changed()
        self._update_point_labels_limit_note()

    def _update_point_labels_limit_note(self):
        """
        選択中のデータセットのうち、ラベル表示が有効なのに点数が表示上限を超えて
        いるものがあれば、その理由をチェックボックスの下に表示する。
        """
        note = getattr(self, 'point_labels_limit_note', None)
        if note is None:
            return
        max_points = self.canvas.point_label_max_points
        over_limit = [ds for ds in self._get_selected_datasets()
                      if ds.show_point_labels and len(ds.visible_df) > max_points]
        if not over_limit:
            note.setVisible(False)
            return
        largest = max(len(ds.visible_df) for ds in over_limit)
        note.setText(
            f"点数({largest:,}件)が表示上限({max_points:,}件)を超えているため、"
            "ラベルは表示されません。上限は「環境設定」で変更できますが、"
            "点数が多いと描画に時間がかかります(1,000件で約2秒)。"
        )
        note.setVisible(True)

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
            self.smoothing_method_combo: ('smoothing_method', self.smoothing_method_combo.currentData()),
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
            # 斜向/立体風トグル(項目120、C-514)
            self.waterfall_depth_checkbox: (
                'waterfall_depth_shrink_enabled', self.waterfall_depth_checkbox.isChecked()
            ),
            self.waterfall_depth_ratio_spinbox: (
                'waterfall_depth_shrink_ratio', self.waterfall_depth_ratio_spinbox.value()
            ),
            # 誤差の表示形式(項目C-502)
            self.error_display_combo: ('error_display', self.error_display_combo.currentData()),
            # 欠損値(NaN)の方針設定(項目C-201)
            self.nan_policy_combo: ('nan_policy', self.nan_policy_combo.currentData()),
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
        # C-1: 中身が全部隠れたサブセクションは見出しごと畳む
        self._update_property_section_visibility()

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
        is_smoothable_type = plot_type in ('Line', 'Line+Scatter')
        self.ui.smoothing_checkbox.setVisible(is_smoothable_type)
        # 平滑化の手法コンボ(項目C-304)は、平滑化チェックボックス自体が
        # 隠れる場合は当然隠す。表示対象のplot_typeでも、チェックがOFFの間は
        # 手法を選ぶ意味がないため無効化はするが非表示にはしない
        # (見えなくなったり出てきたりでレイアウトが揺れるのを避けるため)。
        self.smoothing_method_label.setVisible(is_smoothable_type)
        self.smoothing_method_combo.setVisible(is_smoothable_type)
        self.smoothing_method_combo.setEnabled(self.ui.smoothing_checkbox.isChecked())
        self._update_property_section_visibility()

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

        ★ 改善ボード A-5: 2Dマップ(data_kind='2d_grid')は gui/canvas.py の
        _draw_data() が描画の手前で1D経路から分離する(_draw_2d_data へ振り分ける)
        ため、ウォーターフォール設定は何の効果も持たない。それでもチェックボックスを
        含む最大6行が表示され続けていたので、2Dのときは丸ごと隠す
        (グラデーション設定を plot_type で出し分けている
        _update_gradient_controls_visibility と挙動を揃える)。
        """
        dataset = self._get_current_dataset()
        # 2Dマップではウォーターフォールは効かないので、チェックボックスごと隠す。
        # 選択なし(None)の場合は従来どおり表示する(他の 1D 系コントロールと同じ扱い)。
        is_2d = dataset is not None and dataset.data_kind == '2d_grid'
        if is_2d:
            for widget in (
                self.waterfall_checkbox,
                self.waterfall_offset_x_label, self.waterfall_offset_x_spinbox,
                self.waterfall_offset_y_label, self.waterfall_offset_y_spinbox,
                self.waterfall_occlusion_checkbox, self.waterfall_depth_checkbox,
                self.waterfall_depth_ratio_label, self.waterfall_depth_ratio_spinbox,
            ):
                widget.setVisible(False)
            self._update_property_section_visibility()
            return

        self.waterfall_checkbox.setVisible(True)
        show_offsets = self.waterfall_checkbox.isChecked()

        self.waterfall_offset_x_label.setVisible(show_offsets)
        self.waterfall_offset_x_spinbox.setVisible(show_offsets)
        self.waterfall_offset_y_label.setVisible(show_offsets)
        self.waterfall_offset_y_spinbox.setVisible(show_offsets)
        # オクルージョンON/OFF・斜向/立体風トグル(項目120)も、有効時だけ意味を
        # 持つ設定のため同じ条件で表示する
        self.waterfall_occlusion_checkbox.setVisible(show_offsets)
        self.waterfall_depth_checkbox.setVisible(show_offsets)

        # 縮小率スピンボックスは、さらに奥行き効果トグル自体がONの時だけ
        # 意味を持つ設定のため、_update_gradient_controls_visibilityの
        # 「詳細設定はチェック後にだけ見せる」パターンと同じ2段階の表示条件にする。
        show_depth_ratio = show_offsets and self.waterfall_depth_checkbox.isChecked()
        self.waterfall_depth_ratio_label.setVisible(show_depth_ratio)
        self.waterfall_depth_ratio_spinbox.setVisible(show_depth_ratio)
        self._update_property_section_visibility()

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

        # 「データセットプロパティ」の入力欄。★ セクションの開閉トグルは
        # 選択の有無に関わらず常に押せるよう、ここでは無効化しない
        # (詳細は main_window._set_dataset_property_fields_enabled)。
        self._set_dataset_property_fields_enabled(has_dataset_selection)

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
        self.nan_policy_combo.setEnabled(has_dataset_selection)

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
            self.smoothing_method_combo.blockSignals(True)
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
            self.waterfall_depth_checkbox.blockSignals(True)
            self.waterfall_depth_ratio_spinbox.blockSignals(True)
            self.error_display_combo.blockSignals(True)
            self.nan_policy_combo.blockSignals(True)
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
            # 保存値は '--' と 'dashed' のような表記ゆれを含むため、表示名に揃えて選ぶ。
            # 線を描かない値('None')はどの項目にも当たらないので、選択なしにする
            # (直前のデータセットの表示が残って誤解されるのを防ぐ)。
            shown_linestyle = linestyle_name(dataset.linestyle)
            if shown_linestyle is None:
                self.ui.linestyle_combo.setCurrentIndex(-1)
            else:
                self.ui.linestyle_combo.setCurrentText(shown_linestyle)
            self.ui.linewidth_spinbox.setValue(dataset.linewidth)
            self.ui.marker_combo.setCurrentText(dataset.marker if dataset.marker is not None else 'None')
            self.ui.markersize_spinbox.setValue(dataset.markersize)
            self.color_picker_widget.set_color(dataset.color)
            self.ui.smoothing_checkbox.setChecked(dataset.smoothing)
            smoothing_method_index = self.smoothing_method_combo.findData(dataset.smoothing_method)
            self.smoothing_method_combo.setCurrentIndex(smoothing_method_index if smoothing_method_index != -1 else 0)
            self.alpha_spinbox.setValue(dataset.alpha)
            self.gradient_checkbox.setChecked(dataset.gradient_enabled)
            self.gradient_color2_picker.set_color(dataset.gradient_color2)
            gradient_target_index = self.gradient_target_combo.findData(dataset.gradient_target)
            self.gradient_target_combo.setCurrentIndex(gradient_target_index if gradient_target_index != -1 else 0)
            self.waterfall_checkbox.setChecked(dataset.waterfall_enabled)
            self.waterfall_offset_x_spinbox.setValue(dataset.waterfall_offset_x)
            self.waterfall_offset_y_spinbox.setValue(dataset.waterfall_offset_y)
            self.waterfall_occlusion_checkbox.setChecked(dataset.waterfall_occlusion_enabled)
            self.waterfall_depth_checkbox.setChecked(dataset.waterfall_depth_shrink_enabled)
            self.waterfall_depth_ratio_spinbox.setValue(dataset.waterfall_depth_shrink_ratio)
            self.point_labels_checkbox.setChecked(dataset.show_point_labels)
            self.point_label_col_combo.clear()
            self.point_label_col_combo.addItems([POINT_LABEL_Y_VALUE_LABEL] + dataset.df.columns.tolist())
            self.point_label_col_combo.setCurrentText(dataset.point_label_col_name or POINT_LABEL_Y_VALUE_LABEL)
            self.use_secondary_y_checkbox.setChecked(dataset.use_secondary_y)
            self.subplot_target_combo.setCurrentIndex(dataset.subplot_target)
            error_display_index = self.error_display_combo.findData(dataset.error_display)
            self.error_display_combo.setCurrentIndex(error_display_index if error_display_index != -1 else 0)
            nan_policy_index = self.nan_policy_combo.findData(dataset.nan_policy)
            self.nan_policy_combo.setCurrentIndex(nan_policy_index if nan_policy_index != -1 else 0)
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
            self.smoothing_method_combo.blockSignals(False)
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
            self.waterfall_depth_checkbox.blockSignals(False)
            self.waterfall_depth_ratio_spinbox.blockSignals(False)
            self.error_display_combo.blockSignals(False)
            self.nan_policy_combo.blockSignals(False)
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
            self._update_point_labels_limit_note()

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
            self.waterfall_depth_checkbox.setVisible(False)
            self.waterfall_depth_ratio_label.setVisible(False)
            self.waterfall_depth_ratio_spinbox.setVisible(False)

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
            # 標本標準偏差(n−1)。1点しか無いと定義できないので「-」と表示する。
            std = sample_standard_deviation(valid)
            std_text = "-" if np.isnan(std) else f"{std:.4g}"
            self.stats_summary_label.setText(
                f"件数: {len(valid)}   平均: {np.mean(valid):.4g}   "
                f"標準偏差: {std_text}   最小: {np.min(valid):.4g}   最大: {np.max(valid):.4g}"
            )
            self.dataset_mini_stats_label.setText(
                f"{dataset.name} 〈n={len(valid)}, 平均={np.mean(valid):.4g}, "
                f"SD={std_text}〉"
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

        # 列の単位メタデータ → 軸ラベル自動生成(項目127、C-608): 選んだ列名が
        # 「ラベル (単位)」形式に見える場合、このデータセットの描画先(subplot_target)
        # の軸ラベルが「まだ空」であれば自動的に埋める(ユーザーが既に手で入力した
        # ラベルは上書きしない)。ラベル自体はUndo対象に含めない(軸設定のUndoは
        # 別の仕組み(all_plot_settingsのスナップショット)で扱っており、ここに
        # 巻き込むと既存の挙動を変えてしまうため)。
        if 'x_col_name' in new_values:
            self._maybe_autofill_axis_label(dataset.subplot_target, 'x_label', new_values['x_col_name'])
        if 'y_col_name' in new_values:
            self._maybe_autofill_axis_label(dataset.subplot_target, 'y_label', new_values['y_col_name'])

    def _maybe_autofill_axis_label(self, subplot_index, label_key, column_name):
        """
        _on_plot_column_changedのヘルパー(項目127、C-608)。指定した軸の
        指定ラベル(x_label/y_label)が空の場合のみ、列名から推測したラベルで
        埋める。編集対象として現在UIに表示中の軸(project.active_axis_index)と
        一致する場合はテキスト欄経由で(既存の_on_axis_setting_changedの保存
        経路にそのまま乗せて)反映し、一致しない場合はall_plot_settingsを
        直接更新してから再描画する(UIに表示されていない軸の設定を、表示中の
        軸のテキスト欄に書き込んでしまう誤動作を避けるため)。
        """
        if subplot_index is None or not (0 <= subplot_index < len(self.project.all_plot_settings)):
            return
        inferred = infer_axis_label_from_column_name(column_name)
        if not inferred:
            return
        current_settings = self.project.all_plot_settings[subplot_index]
        if current_settings.get(label_key):
            return  # 既存のラベルは上書きしない

        if subplot_index == self.project.active_axis_index:
            label_edit = self.ui.x_label_text_edit if label_key == 'x_label' else self.ui.y_label_text_edit
            if not label_edit.text():
                label_edit.setText(inferred)  # textChanged経由で_on_axis_setting_changedが保存・再描画する
        else:
            current_settings[label_key] = inferred
            self._update_plot()

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

        ★ 改善ボード D-2: Z列・カラーマップ・値域の3つは、1Dの
        'Z-Color Scatter'(3列目の値で点を配色する散布図)でも使う
        ため、data_kind='2d_grid' でなくてもこのplot_typeなら表示する。
        残り(表示モード・等高線レベル・グリッド補間方法)はグリッド固有なので
        2Dのときだけ表示する。
        """
        dataset = self._get_current_dataset()
        # ★ 選択なし(None)の場合は常に非表示にする(data_2d_checkboxのチェック状態は
        # 直前に選択していたデータセットの値が残ったままなので、それにフォール
        # バックすると選択解除後も2D系コントロールが表示されたままになるバグになる)。
        is_2d = dataset is not None and dataset.data_kind == '2d_grid'
        is_color_by_column = (
            dataset is not None
            and dataset.data_kind != '2d_grid'
            and dataset.plot_type == COLOR_BY_COLUMN_PLOT_TYPE
        )
        # Z列・カラーマップ・値域: 2Dグリッド と 色分け散布図 の共用
        shared_with_color_scatter = is_2d or is_color_by_column
        for widget in (
            self.z_col_label, self.z_col_combo,
            self.colormap_label, self.colormap_combo,
            self.color_range_auto_checkbox,
            self.vmin_label, self.vmin_spinbox,
            self.vmax_label, self.vmax_spinbox,
        ):
            widget.setVisible(shared_with_color_scatter)

        # グリッド固有の設定は2Dのときだけ
        for widget in (
            self.map_display_mode_label, self.map_display_mode_combo,
            self.contour_levels_label, self.contour_levels_spinbox,
            self.grid_interp_method_label, self.grid_interp_method_combo,
        ):
            widget.setVisible(is_2d)

        self._update_property_section_visibility()

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
