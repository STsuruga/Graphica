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
import uuid
import matplotlib as mpl
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QMessageBox, QFileDialog, QInputDialog, QMenu)

from graphica.core.analysis import (sample_standard_deviation)
from graphica.core.commands import (SetDatasetPropertiesCommand, ReorderDatasetsCommand, SetAnnotationsCommand)
from graphica.core.color_palettes import BUILTIN_PALETTES
from graphica.core.named_colors import POPUP_LIMIT, load_named_colors
from graphica.core.dataset import Dataset, COLOR_BY_COLUMN_PLOT_TYPE, linestyle_name
from graphica.core.label_utils import infer_axis_label_from_column_name
from graphica.core.methods_text import generate_methods_text
from graphica.gui.workers import BUILTIN_DATA_FILE_EXTENSIONS
from graphica.core.plugin_api import get_registered_importer_extensions
from graphica.core.plugin_types import AnalysisResult, PluginExecutionError
from graphica.gui.data_editor import DataEditorDialog
from graphica.gui.dialogs import (ResultDialog, ColorPaletteDialog,
                         NewDatasetDialog,
                         PluginParamDialog,
                         InsetDialog)
from graphica.gui.dataset_style_icon import (
    make_dataset_style_icon, make_dataset_visibility_icon, apply_dataset_visibility_text_style,
    DATASET_TREE_VISIBILITY_COLUMN,
)

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
STYLE_ATTRS = ('plot_type', 'color', 'linestyle', 'linewidth', 'marker', 'markersize', 'smoothing',
               'smoothing_method', 'alpha',
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
            copy_style_action.triggered.connect(self._on_copy_dataset_style)

            paste_style_action = menu.addAction("スタイルを貼り付け")
            paste_style_action.setEnabled(self._copied_dataset_style is not None)
            paste_style_action.triggered.connect(self._on_paste_dataset_style)

            # 元ファイルからの再読み込み(項目C-103): ファイル読み込みで作成された
            # データセット(dataset.source_fileを保持)のみ有効。クリップボード貼り付け・
            # データセット間演算・プラグインprocessor/analyzerの生成物等、元ファイルを
            # 持たないデータセットではグレーアウトする。
            reload_action = menu.addAction("元ファイルから再読み込み")
            reload_action.setEnabled(bool(self._get_current_dataset().source_file))
            reload_action.triggered.connect(self._on_reload_dataset_from_source)

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
            add_stat_label_action.triggered.connect(self._on_add_stat_anchor_label)

            # インセット(拡大図)+拡大範囲の指示線(項目138、C-711)
            add_inset_action = analysis_menu.addAction("インセット(拡大図)を追加...")
            add_inset_action.triggered.connect(self._on_add_inset)

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
            copy_methods_text_action.triggered.connect(self._on_copy_methods_text)

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
            export_data_action.triggered.connect(self._on_export_dataset_data)

            # タブ間のデータセットコピー/移動(項目C-905): タブ=完全に独立した
            # プロジェクトという設計上、他のタブが無ければ意味を成さないため
            # 常に表示しつつハンドラ側で案内する(setEnabledで隠すより、
            # 「タブが無いから使えない」ことに気づける方が親切なため)。
            copy_to_tab_action = tab_menu.addAction("別のタブへコピー...")
            copy_to_tab_action.triggered.connect(lambda: self._on_copy_or_move_dataset_to_tab(move=False))

            move_to_tab_action = tab_menu.addAction("別のタブへ移動...")
            move_to_tab_action.triggered.connect(lambda: self._on_copy_or_move_dataset_to_tab(move=True))

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
                logger.exception("データセットの書き出しに失敗しました")
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
                logger.exception("データセットの書き出しに失敗しました")
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

    def _get_sibling_tabs(self):
        """
        自分以外のタブ(PlotterAppインスタンス)を、(タブのタイトル文字列, その
        PlotterAppインスタンス) のリストとして返す(項目C-905)。
        gui/main_app_window.pyのMainAppWindowが実際にタブを保持しているが、
        PlotterApp生成時には参照を渡されていないため、self.window()
        (Qt標準、自分が属する最上位ウィンドウを返す)経由で辿る。
        gui.main_app_windowをモジュールレベルでインポートすると循環インポートに
        なる(main_app_window.pyがgui.main_windowをインポートしているため)、
        ここで遅延インポートする。単体PlotterAppとして起動された場合
        (self.window()がMainAppWindowでない、主にテスト環境)は空リストを返す。
        """
        from graphica.gui.main_app_window import MainAppWindow
        top = self.window()
        if not isinstance(top, MainAppWindow):
            return []
        return [
            (top.tab_widget.tabText(i), top.tab_widget.widget(i))
            for i in range(top.tab_widget.count())
            if top.tab_widget.widget(i) is not self
        ]

    def _remove_datasets_without_confirmation(self, datasets, description=None):
        """
        指定したDatasetのリストを、確認ダイアログなしでこのタブから削除する
        (項目C-905の「別のタブへ移動」専用ヘルパー)。_on_remove_dataset
        (右クリック「削除」)と削除ロジック自体は同じだが、ツリーの選択状態では
        なく呼び出し元が渡した具体的なDatasetのリストを対象にする点が異なる。

        ★ 改善ボード A-3: こちらも RemoveDatasetCommand 経由でUndo可能にした。
        ただし「別のタブへ移動」から呼ばれた場合、Undoで元に戻るのは*このタブ側の
        削除だけ*である(タブ=独立したPlotterAppインスタンスで undo_stack も別、
        移動先タブへの追加は取り消されない)。そのため移動をUndoすると、
        両方のタブに1件ずつ存在する状態になる。復元手段が全く無い従来よりは
        マシだが、この非対称性は仕様として認識しておくこと。
        """
        items = [
            item for ds in datasets
            if (item := self._get_dataset_tree_item(ds)) is not None
        ]
        self._remove_dataset_items_with_undo(items, description=description)

    def _on_copy_or_move_dataset_to_tab(self, move):
        """
        「別のタブへコピー...」/「別のタブへ移動...」メニューの処理(項目C-905)。
        タブ=完全に独立したPlotterAppインスタンス(1プロジェクト)という設計上、
        選択中のデータセットを丸ごと複製し、対象タブのproject.datasetsへ
        直接追加する(ファイル保存/読込を経由しない、インメモリでの転送)。
        複製自体は「プロット複製」(_on_duplicate_dataset)と同じ
        copy.deepcopy()を使う(DataFrame等を含め完全に独立させる、既に
        確立済みの安全なDataset複製方法)。dataset_idだけは、コピー先タブで
        元と衝突しないよう新しく振り直す。
        移動の場合は、対象タブへの追加が成功した後に元タブから削除する。
        移動先タブへの追加はUndo非対応のまま(タブごとにundo_stackが独立して
        いるため、このタブのUndoから相手タブを巻き戻すことはできない)。
        元タブからの削除だけは改善ボード A-3 でUndo可能になっている
        (_remove_datasets_without_confirmation のdocstring参照)。
        """
        selected = self._get_selected_datasets()
        if not selected:
            return

        sibling_tabs = self._get_sibling_tabs()
        if not sibling_tabs:
            QMessageBox.information(self, "タブ間のデータセット転送", "コピー/移動先の他のタブがありません。")
            return

        tab_titles = [title for title, _ in sibling_tabs]
        action_label = "移動" if move else "コピー"
        choice, ok = QInputDialog.getItem(
            self, f"別のタブへ{action_label}", "転送先のタブ:", tab_titles, 0, False
        )
        if not ok:
            return
        target_window = sibling_tabs[tab_titles.index(choice)][1]

        for dataset in selected:
            new_dataset = copy.deepcopy(dataset)
            new_dataset.dataset_id = uuid.uuid4().hex
            target_window._add_dataset(new_dataset, target_window._get_target_folder_for_new_dataset())

        if move:
            self._remove_datasets_without_confirmation(
                selected, description=f"別のタブへ移動({len(selected)}件)"
            )

        self.statusBar().showMessage(
            f"{len(selected)}件のデータセットを「{choice}」へ{action_label}しました", 3000
        )

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

    def _on_reload_dataset_from_source(self):
        """
        「元ファイルから再読み込み」メニューの処理(項目C-103)。
        dataset.source_file(gui/main_window.pyの_import_loaded_dataframeが
        ファイル読み込み時に設定)からファイルを読み直し、書式・注釈・データセット名は
        そのままに df(データ本体)だけを差し替える。測定をやり直すたびに図を
        ゼロから作り直さずに済むようにする機能。

        X/Y軸・エラーバー・データ点ラベルの列選択(x_col_name等)は変更しない
        (ファイルの列構成が変わっていなければ引き続き正しく参照できるため)。
        ただし再読み込み後にそれらの列が見つからない場合は、壊れた状態で
        グラフが描画される前にエラーで中断する。

        ★ 既知の制約: インポートウィザード(項目C-101)で文字コード/区切り文字/
        ヘッダー行/固定長を個別に調整して読み込んだCSVについては、その調整内容は
        保持していないため、再読み込みは常に標準設定(自動判定)で読み直す。
        調整が必要なファイルで列が見つからない場合は、このメソッドではなく
        通常のインポート操作(ウィザードで再調整)でのデータセット追加をお勧めする
        メッセージを表示する。

        マスク済み行(masked_row_indices)は、旧データの行ラベルに紐づいた情報であり
        新しいデータでは無意味(むしろ別の行を誤って除外し続ける)になるため、
        再読み込みと同時にクリアする。
        """
        dataset = self._get_current_dataset()
        if dataset is None or not dataset.source_file:
            return

        if not os.path.exists(dataset.source_file):
            QMessageBox.warning(
                self, "再読み込み",
                f"元ファイルが見つかりません:\n{dataset.source_file}"
            )
            return

        from graphica.gui.workers import read_data_file, excel_engine_for
        try:
            if dataset.source_sheet:
                new_df = pd.read_excel(dataset.source_file, sheet_name=dataset.source_sheet,
                                       engine=excel_engine_for(dataset.source_file))
            else:
                new_df = read_data_file(dataset.source_file)
        except Exception as e:
            logger.exception("元ファイルからの再読み込みに失敗しました")
            QMessageBox.warning(self, "再読み込み", f"ファイルの読み込みに失敗しました:\n{e}")
            return

        required_columns = (
            dataset.x_col_name, dataset.y_col_name,
            dataset.x_err_col_name, dataset.y_err_col_name, dataset.point_label_col_name,
        )
        missing = [col for col in required_columns if col and col not in new_df.columns]
        if missing:
            QMessageBox.warning(
                self, "再読み込み",
                "再読み込みしたファイルに、現在使用中の列が見つかりませんでした:\n"
                + "\n".join(missing)
                + "\n\nファイルの構造(列名/区切り文字/ヘッダー行など)が変わった可能性があります。"
                "「データセット追加」から改めてインポートし直すことをお勧めします。"
                "再読み込みは中止しました。"
            )
            return

        old_values = {'df': dataset.df, 'masked_row_indices': list(dataset.masked_row_indices)}
        new_values = {'df': new_df, 'masked_row_indices': []}
        # ★ _push_dataset_property_command は old_values == new_values で変更なし判定を
        #   行うが、辞書にDataFrameが含まれると == の評価自体が
        #   ValueError("The truth value of a DataFrame is ambiguous") になるため、
        #   ここでは使わずSetDatasetPropertiesCommandを直接発行する。
        command = SetDatasetPropertiesCommand(
            dataset, old_values, new_values,
            on_applied=lambda: self._refresh_after_dataset_property_change(
                dataset, changed_keys=new_values.keys(), old_values=old_values, new_values=new_values
            ),
            description=f"「{dataset.name}」を再読み込み"
        )
        self.undo_stack.push(command)
        self.statusBar().showMessage(f"「{dataset.name}」を元ファイルから再読み込みしました", 3000)

    # 分割で一度に作るデータセット数の目安。これを超える場合は、連続値の列を
    # 誤って選んだ等の取り違えが疑われるため、作る前に確認を挟む。
    # 統計値アンカーラベル(項目C-708)の選択肢: 表示名 -> gui/canvas.pyの
    # _compute_stat_label_text/STAT_LABEL_TITLESが解釈する内部キー。
    STAT_ANCHOR_LABEL_CHOICES = {
        'R²': 'r_squared', 'Y平均': 'mean', 'Y標準偏差': 'std',
        'Y最大値': 'max', 'Y最小値': 'min',
    }

    def _on_add_stat_anchor_label(self):
        """
        「統計値アンカーラベルを追加...」メニューの処理(項目C-708)。
        カレントデータセットに紐づく統計値(R²/Y平均/Y標準偏差/Y最大値/Y最小値)を
        選ばせ、そのデータセットが描画されている軸のAxes相対座標(左上を起点に、
        既存の統計値ラベル件数ぶん縦にずらして重ならないようにする)に注釈として
        追加する。表示テキストは固定文字列ではなく、描画のたびに
        dataset.y_data/fit_resultから再計算される(gui/canvas.pyの
        _compute_stat_label_text)ため、R²を選んでからフィットを実行/更新しても
        自動的に値が反映される。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        choice, ok = QInputDialog.getItem(
            self, "統計値アンカーラベルの追加", "表示する統計値:",
            list(self.STAT_ANCHOR_LABEL_CHOICES.keys()), 0, False
        )
        if not ok:
            return
        stat = self.STAT_ANCHOR_LABEL_CHOICES[choice]

        axis_index = dataset.subplot_target
        settings = self.project.all_plot_settings[axis_index]
        existing_stat_count = sum(
            1 for ann in settings.get('annotations', []) if ann.get('type') == 'stat'
        )
        xy = (0.05, max(0.95 - 0.07 * existing_stat_count, 0.05))

        self._add_annotation(axis_index, {
            'type': 'stat', 'dataset_id': dataset.dataset_id, 'stat': stat,
            'xy': xy, 'color': '#000000',
        }, description="統計値アンカーラベルの追加")

    def _on_add_inset(self):
        """
        「インセット(拡大図)を追加...」メニューの処理(項目138、C-711)。
        カレントデータセットのX範囲を初期値として、拡大するX範囲・表示位置
        (コーナー+サイズ)をInsetDialogで選ばせ、そのデータセットが描画されて
        いる軸に注釈(type='inset')として追加する(gui/canvas.pyの
        _draw_annotationsが実際の描画とmark_insetによる指示線を担当)。
        """
        dataset = self._get_current_dataset()
        if dataset is None:
            return

        x_data = np.asarray(dataset.x_data, dtype=float)
        x_data = x_data[~np.isnan(x_data)]
        if len(x_data) < 2:
            QMessageBox.warning(self, "インセット(拡大図)", "有効なデータ点が不足しています(最低2点必要)。")
            return
        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        span = x_max - x_min
        default_zoom_min = x_min + span * 0.4
        default_zoom_max = x_min + span * 0.6

        dialog = InsetDialog(x_min, x_max, default_zoom_min, default_zoom_max, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.get_settings()

        axis_index = dataset.subplot_target
        self._add_annotation(axis_index, {
            'type': 'inset', 'corner': settings['corner'], 'size': settings['size'],
            'zoom_x_range': settings['zoom_x_range'], 'color': '#000000',
        }, description="インセット(拡大図)の追加")

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
            logger.exception("[plugin:%s] processor の実行に失敗しました", processor.plugin_name)
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
            logger.exception("[plugin:%s] analyzer の実行に失敗しました", analyzer.plugin_name)
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

    def _populate_named_color_apply_menu(self):
        """
        オーバーフローメニューの「登録した色を適用 ▶」の中身を詰め直す。

        登録内容は「色名の管理」でいつでも変わるので、開くたびに作り直す
        (データセットメニューと同じ方式)。1件も登録が無いときは、無効化した
        案内項目を1つだけ出す — 空のサブメニューを開いて何も無いより、
        「どこで登録するのか」が分かる方が親切なため。
        """
        menu = getattr(self, '_named_color_apply_menu', None)
        if menu is None:
            return
        menu.clear()
        entries = load_named_colors(self.settings)
        if not entries:
            empty_action = menu.addAction("(登録がありません)")
            empty_action.setEnabled(False)
            return
        # 色欄のポップアップと同じく、並べるのは先頭 POPUP_LIMIT 件まで。
        for entry in entries[:POPUP_LIMIT]:
            action = menu.addAction(
                _named_color_menu_icon(entry["color"]),
                f'{entry["name"]}	{entry["color"]}')
            action.triggered.connect(
                lambda checked=False, c=entry["color"], n=entry["name"]:
                    self._apply_named_color_to_selection(c, n))
        if len(entries) > POPUP_LIMIT:
            more_action = menu.addAction(f"すべての登録色... ({len(entries)}件)")
            more_action.triggered.connect(self._on_apply_named_color_from_list)

    def _on_apply_named_color_from_list(self):
        """登録が POPUP_LIMIT 件を超えたときに、検索欄付きの一覧から選んで適用する。"""
        from graphica.gui.dialogs import NamedColorPickerDialog
        dialog = NamedColorPickerDialog(self.settings, self, title="登録色を適用")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        entry = dialog.selected_entry()
        if entry:
            self._apply_named_color_to_selection(entry["color"], entry["name"])

    def _apply_named_color_to_selection(self, color, name):
        """
        登録した色を、選択中の(複数可)データセットへまとめて適用する。
        N件の変更が Undo 1回で戻るのは「自動配色」と同じ
        (_on_auto_assign_colors と同じ beginMacro の型)。
        """
        selected_datasets = self._get_selected_datasets()
        if not selected_datasets:
            self.statusBar().showMessage("データセットを選択してください。", 4000)
            return

        # ★ 既にその色のものを先に除く。空のままbeginMacro/endMacroすると、
        #   Qtは「中身ゼロのマクロ」をそのままスタックへ積むため、何も変わって
        #   いないのにUndoが1回分増える(押しても何も起きないUndoができてしまう)。
        targets = [ds for ds in selected_datasets if ds.color != color]
        if not targets:
            self.statusBar().showMessage(f"選択中のデータセットは既に「{name}」の色です。", 4000)
            return

        is_batch = len(targets) > 1
        if is_batch:
            self.undo_stack.beginMacro(f"「{name}」の色を適用 ({len(targets)}件)")
        for dataset in targets:
            self._push_dataset_property_command(
                dataset,
                {'color': dataset.color},
                {'color': color},
                description=f"「{name}」の色を適用",
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
        組み込みの論文向けパレット(項目141、C-804、BUILTIN_PALETTES)も
        ユーザーのカスタムパレットと同じ扱いで名前解決する。
        """
        active_name = self.settings.value(ACTIVE_PALETTE_SETTINGS_KEY, ColorPaletteDialog.DEFAULT_PALETTE_NAME)
        if active_name in BUILTIN_PALETTES:
            return BUILTIN_PALETTES[active_name]
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

def _named_color_menu_icon(color_name, size=16):
    """「登録した色を適用」メニューの色見本(色欄のポップアップと同じ描き方)。"""
    from graphica.gui.color_picker_widget import _color_icon
    return _color_icon(color_name, size=size)
