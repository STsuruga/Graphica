"""データセットのデータ処理(規格化・平滑化・ベースライン補正・積分・リサンプリング・データセット間の演算など)。"""
import logging
import numpy as np
import pandas as pd
from PySide6.QtWidgets import (QDialog, QMessageBox, QInputDialog)

from graphica.core.provenance import build_provenance
from graphica.core.analysis import (calculate_savgol,
                           calculate_baseline_als, calculate_baseline_polynomial,
                           calculate_baseline_rubberband, calculate_baseline_manual,
                           calculate_interval_integral, calculate_cumulative_integral,
                           calculate_average_duplicate_x,
                           calculate_zscore_outliers, calculate_iqr_outliers,
                           calculate_resample_to_grid, calculate_histogram, calculate_kde, calculate_error_propagation,
                           calculate_cross_correlation_alignment, split_dataframe_by_column)
from graphica.core.commands import (SetMaskedRowsCommand)
from graphica.core.dataset import Dataset
from graphica.core.safe_eval import safe_eval_column_formula
from graphica.gui.dialogs import (ResultDialog, ColumnCalculatorDialog, DatasetArithmeticDialog, NormalizeDatasetDialog, SavGolDialog, BaselineCorrectionDialog, IntervalIntegralDialog, CumulativeIntegralDialog,
                         ResampleDatasetDialog, DuplicateXDialog, RowFilterDialog, OutlierDetectionDialog,
                         HistogramKDEDialog, XAxisAlignmentDialog)

logger = logging.getLogger(__name__)

# カスタム配色パレットをQSettingsに保存する際のキー

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
SPLIT_BY_COLUMN_CONFIRM_THRESHOLD = 30


class ProcessingController:
    """現在のデータセット(または選択中の複数)から新しいデータセットを作る、または行を除外する処理。"""

    def __init__(self, host):
        self._host = host
        self.integral_result_dialog = None
        self.outlier_result_dialog = None

    def arithmetic(self):
        """
        「データセット間演算...」メニューの処理。
        選択中のちょうど2つのデータセット(A, B)について、B側のY値をA側のX値に
        線形補間してから差・和・積・商を計算し、新しいデータセットとして追加する。
        2つのデータセットのX軸が完全には一致しないケースを想定している。
        """
        selected = self._host.selected_datasets()
        if len(selected) != 2:
            QMessageBox.information(self._host.parent_widget, "データセット間演算", "演算対象として、データセットをちょうど2つ選択してください。")
            return
        ds_a, ds_b = selected[0], selected[1]

        dialog = DatasetArithmeticDialog(ds_a.name, ds_b.name, self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        operation, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        xa = np.asarray(ds_a.x_data, dtype=float)
        ya = np.asarray(ds_a.y_data, dtype=float)
        xb = np.asarray(ds_b.x_data, dtype=float)
        yb = np.asarray(ds_b.y_data, dtype=float)

        # 誤差伝播(項目109、C-313): A・B両方にY誤差列がある場合のみ計算する
        # (片方だけしか無い場合は不完全な伝播になり誤解を招くため、従来どおり
        # 誤差列なしの結果にする)。err_a_full/err_b_fullはx_data/y_dataと同じ
        # visible_df由来で行が対応しているため、この後のxa/xbと同じ
        # valid_a/valid_b・mask・order_bでそのまま追従させられる。
        err_a_full = ds_a.y_err_data
        err_b_full = ds_b.y_err_data
        propagate_errors = err_a_full is not None and err_b_full is not None
        if propagate_errors:
            err_a_full = np.asarray(err_a_full, dtype=float)
            err_b_full = np.asarray(err_b_full, dtype=float)

        valid_a = ~(np.isnan(xa) | np.isnan(ya))
        valid_b = ~(np.isnan(xb) | np.isnan(yb))
        xa, ya = xa[valid_a], ya[valid_a]
        xb, yb = xb[valid_b], yb[valid_b]
        if propagate_errors:
            err_a_full = err_a_full[valid_a]
            err_b_full = err_b_full[valid_b]

        if len(xa) == 0 or len(xb) == 0:
            QMessageBox.warning(self._host.parent_widget, "データセット間演算", "有効なデータ点がありません。")
            return

        lo, hi = max(np.min(xa), np.min(xb)), min(np.max(xa), np.max(xb))
        if lo > hi:
            QMessageBox.warning(self._host.parent_widget, "データセット間演算", "2つのデータセットのX軸の範囲が重なっていないため演算できません。")
            return

        mask = (xa >= lo) & (xa <= hi)
        xa_sub, ya_sub = xa[mask], ya[mask]
        if propagate_errors:
            err_a_sub = err_a_full[mask]
        if len(xa_sub) == 0:
            QMessageBox.warning(self._host.parent_widget, "データセット間演算", "重なる範囲にA側のデータ点がありません。")
            return

        order_b = np.argsort(xb)
        yb_interp = np.interp(xa_sub, xb[order_b], yb[order_b])
        if propagate_errors:
            err_b_interp = np.interp(xa_sub, xb[order_b], err_b_full[order_b])

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

        result_data = {'x': xa_sub, 'y': result}
        if propagate_errors:
            result_data['y_err'] = calculate_error_propagation(operation, ya_sub, err_a_sub, yb_interp, err_b_interp)
        result_df = pd.DataFrame(result_data)
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            y_err_col_name='y_err' if propagate_errors else None,
            provenance=build_provenance(
                'arithmetic', {'operation_symbol': operation, 'error_propagated': propagate_errors}, [ds_a, ds_b],
            ),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
        self._host.show_status(f"「{output_name}」を追加しました", 3000)

    def align_selected(self):
        """
        「X軸アライメント(相互相関)...」メニューの処理(項目105、C-307)。
        選択中のちょうど2つのデータセット(A=基準/移動しない、B=位置合わせ
        対象/移動する、選択順)について、相互相関(calculate_cross_correlation_
        alignment)でBに加えるべきXシフト量を推定し、Bのxをシフトした新しい
        データセットを追加する(A自体・元のB自体は変更しない、非破壊。
        _on_dataset_arithmeticと同じ「ちょうど2件」パターン)。複数測定を
        重ね合わせる際のピーク位置/起点合わせを想定。
        """
        selected = self._host.selected_datasets()
        if len(selected) != 2:
            QMessageBox.information(self._host.parent_widget, "X軸アライメント", "位置合わせ対象として、データセットをちょうど2つ選択してください。")
            return
        ds_a, ds_b = selected[0], selected[1]

        dialog = XAxisAlignmentDialog(ds_a.name, ds_b.name, self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        xa = np.asarray(ds_a.x_data, dtype=float)
        ya = np.asarray(ds_a.y_data, dtype=float)
        xb = np.asarray(ds_b.x_data, dtype=float)
        yb = np.asarray(ds_b.y_data, dtype=float)

        try:
            result = calculate_cross_correlation_alignment(xa, ya, xb, yb)
        except ValueError as e:
            QMessageBox.warning(self._host.parent_widget, "X軸アライメント", str(e))
            return

        shift = result['shift']
        valid_b = ~(np.isnan(xb) | np.isnan(yb))
        result_df = pd.DataFrame({'x': xb[valid_b] + shift, 'y': yb[valid_b]})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=build_provenance(
                'xaxis_alignment', {'shift': shift, 'grid_step': result['grid_step']}, [ds_a, ds_b],
            ),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
        self._host.show_status(f"「{output_name}」を追加しました(シフト量: {shift:+.4g})", 4000)

    def mean_and_sd_of_selected(self):
        """
        「平均±SD生成...」メニューの処理(項目C-312)。選択中の2件以上の
        データセットを、全データセットのXレンジが重なる範囲内の共通X格子
        (点数は選択中で最も点数の多いデータセットに合わせる)へリサンプリング
        (core.analysis.calculate_resample_to_grid、項目C-305と共有)してから、
        行ごとの平均と標本標準偏差(ddof=1)を計算し、誤差列(SD)付きの新しい
        データセットとして追加する。同一条件の反復測定を1本の「平均±SD」曲線に
        まとめる、論文図の定番の表現(項目C-312、#12誤差自動計算の一般化)。
        """
        selected = self._host.selected_datasets()
        if len(selected) < 2:
            QMessageBox.information(self._host.parent_widget, "平均±SD生成", "平均±SDの生成には、データセットを2つ以上選択してください。")
            return

        x_arrays, y_arrays = [], []
        for ds in selected:
            x = np.asarray(ds.x_data, dtype=float)
            y = np.asarray(ds.y_data, dtype=float)
            valid = ~(np.isnan(x) | np.isnan(y))
            x, y = x[valid], y[valid]
            if len(x) < 2:
                QMessageBox.warning(
                    self._host.parent_widget, "平均±SD生成",
                    f"「{ds.name}」に有効なデータ点が不足しています(最低2点必要)。"
                )
                return
            x_arrays.append(x)
            y_arrays.append(y)

        x_min = max(float(np.min(x)) for x in x_arrays)
        x_max = min(float(np.max(x)) for x in x_arrays)
        if x_min >= x_max:
            QMessageBox.warning(self._host.parent_widget, "平均±SD生成", "選択したデータセット間でX軸の範囲が重なっていません。")
            return

        num_points = max(len(x) for x in x_arrays)
        common_x = np.linspace(x_min, x_max, num_points)

        resampled = []
        for x, y in zip(x_arrays, y_arrays):
            try:
                resampled.append(calculate_resample_to_grid(x, y, common_x, method='linear', extrapolate=False))
            except ValueError as e:
                QMessageBox.warning(self._host.parent_widget, "平均±SD生成", str(e))
                return
        stacked = np.vstack(resampled)  # (データセット数, num_points)

        mean_y = np.nanmean(stacked, axis=0)
        std_y = np.nanstd(stacked, axis=0, ddof=1)

        default_name = f"{selected[0].name} 他{len(selected) - 1}件の平均±SD"
        output_name, ok = QInputDialog.getText(self._host.parent_widget, "平均±SD生成", "出力データセット名:", text=default_name)
        if not ok or not output_name.strip():
            return

        result_df = pd.DataFrame({'x': common_x, 'y_mean': mean_y, 'y_sd': std_y})
        new_dataset = Dataset(
            name=output_name.strip(), df=result_df, x_col_name='x', y_col_name='y_mean',
            y_err_col_name='y_sd',
            provenance=build_provenance(
                'mean_sd', {'method': 'linear', 'n_source': len(selected)}, selected,
            ),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
        self._host.show_status(f"「{output_name.strip()}」を追加しました", 3000)

    def normalize(self):
        """
        「規格化(ノーマライズ)...」メニューの処理(項目78)。
        カレントの(フォーカス中の)1つのデータセットについて、Y値を
        最大値基準または特定X値での強度基準で規格化し、新しいデータセットとして
        追加する。元のデータセットは変更しない(非破壊)。

        単一/複数選択の扱いについて: データセット間演算(_on_dataset_arithmetic)は
        「ちょうど2件」の選択を要求するが、規格化は曲線フィットや
        ピーク検出と同じく「1つのデータセットから新しいデータセットを
        1つ作る」操作であるため、それらと同様に _get_selected_datasets() ではなく
        _get_current_dataset() (フォーカス中の1件)を対象にする。これにより、
        複数選択中でも常にカレントアイテム1件に対して迷いなく動作する。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) == 0:
            QMessageBox.warning(self._host.parent_widget, "規格化(ノーマライズ)", "有効なデータ点がありません。")
            return

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = NormalizeDatasetDialog(original_dataset.name, x_min=x_min, x_max=x_max, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, reference_x, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        if mode == NormalizeDatasetDialog.MODE_MAX:
            reference_value = float(np.max(y_data))
        else:
            if reference_x < x_min or reference_x > x_max:
                QMessageBox.warning(
                    self._host.parent_widget, "規格化(ノーマライズ)",
                    f"指定されたX値 ({reference_x}) がデータセットのX軸範囲 "
                    f"({x_min} 〜 {x_max}) の外にあるため、規格化できません。"
                )
                return
            order = np.argsort(x_data)
            reference_value = float(np.interp(reference_x, x_data[order], y_data[order]))

        if abs(reference_value) < 1e-12:
            QMessageBox.warning(self._host.parent_widget, "規格化(ノーマライズ)", "基準値が0に近すぎるため、規格化できません。")
            return

        result_df = pd.DataFrame({'x': x_data, 'y': y_data / reference_value})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=build_provenance(
                'normalize',
                {'mode': mode, 'reference_x': reference_x, 'reference_value': reference_value},
                [original_dataset],
            ),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
        self._host.show_status(f"「{output_name}」を追加しました", 3000)

    def savgol_smooth(self):
        """
        「Savitzky-Golayフィルタ(平滑化/微分)...」メニューの処理(項目C-301/C-302)。
        カレントの1つのデータセットに対して平滑化(deriv=0)または微分
        (deriv=1/2)を行い、新しいデータセットとして追加する(非破壊)。
        _on_normalize_dataset と同じ「カレント1件」パターン。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 3:
            QMessageBox.warning(self._host.parent_widget, "Savitzky-Golayフィルタ", "有効なデータ点が不足しています。")
            return

        dialog = SavGolDialog(original_dataset.name, max_window=len(x_data), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        window_length, polyorder, deriv, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        try:
            x_sorted, y_result = calculate_savgol(x_data, y_data, window_length, polyorder, deriv=deriv)
        except ValueError as e:
            QMessageBox.warning(self._host.parent_widget, "Savitzky-Golayフィルタ", str(e))
            return

        result_df = pd.DataFrame({'x': x_sorted, 'y': y_result})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=build_provenance(
                'savgol',
                {'window_length': window_length, 'polyorder': polyorder, 'deriv': deriv},
                [original_dataset],
            ),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
        self._host.show_status(f"「{output_name}」を追加しました", 3000)

    def baseline_correction(self):
        """
        「ベースライン補正...」メニューの処理(項目C-308)。
        カレントの1つのデータセットに対してALS/多項式/ラバーバンド/手動点の
        いずれかの手法でベースラインを推定し、ベースライン差し引き後のデータを
        新しいデータセットとして追加する(非破壊)。_on_savgol_dataset/
        _on_normalize_datasetと同じ「カレント1件」パターン。
        ダイアログで「ベースライン曲線も追加する」が有効な場合は、推定した
        ベースライン自体も別データセットとして追加する(任意、既定は追加しない)。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 3:
            QMessageBox.warning(self._host.parent_widget, "ベースライン補正", "有効なデータ点が不足しています。")
            return

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = BaselineCorrectionDialog(original_dataset.name, x_min=x_min, x_max=x_max, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method, params, output_name, add_baseline_dataset = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
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
                    raise ValueError("アンカー点のX座標は数値をカンマ区切りで入力してください。") from None
                x_sorted, baseline, corrected = calculate_baseline_manual(
                    x_data, y_data, anchor_x=anchor_x, method=params["method"]
                )
        except ValueError as e:
            QMessageBox.warning(self._host.parent_widget, "ベースライン補正", str(e))
            return

        result_df = pd.DataFrame({'x': x_sorted, 'y': corrected})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=build_provenance(f'baseline_{method}', dict(params), [original_dataset]),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())

        if add_baseline_dataset:
            baseline_df = pd.DataFrame({'x': x_sorted, 'y': baseline})
            baseline_dataset = Dataset(
                name=f"{output_name}_baseline", df=baseline_df, x_col_name='x', y_col_name='y'
            )
            self._host.add_dataset(baseline_dataset, self._host.target_folder_for_new_dataset())

        self._host.show_status(f"「{output_name}」を追加しました", 3000)

    def interval_integral(self):
        """
        「区間積分(台形則/Simpson則)...」メニューの処理(項目C-311)。
        カレントの1つのデータセットについて、指定したXの範囲でYを台形則または
        Simpson則で定積分する。_on_savgol_dataset/_on_baseline_correction_dataset
        と同じ「カレント1件」パターンだが、結果は新しいデータセットではなく
        スカラー1個(積分値)のため、ピーク検出と同じく
        非モーダル・スクロール可能なResultDialogで結果を表示する。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 2:
            QMessageBox.warning(self._host.parent_widget, "区間積分", "有効なデータ点が不足しています(最低2点必要)。")
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
            QMessageBox.warning(self._host.parent_widget, "区間積分", str(e))
            return

        method_label = "台形則(Trapezoidal)" if method == "trapezoid" else "Simpson則"
        result_text = f"[{original_dataset.name}] の区間積分結果:\n"
        result_text += f"  積分方法: {method_label}\n"
        result_text += f"  積分範囲: {x_range[0]: .6g} 〜 {x_range[1]: .6g}\n"
        result_text += f"  ベースライン差し引き: {'あり(範囲両端を結ぶ直線)' if subtract_baseline else 'なし'}\n"
        result_text += f"  使用データ点数: {result['n_points']}\n"
        result_text += f"  積分値 = {result['integral']: .6e}\n"

        # ★ グラフを見ながら結果を確認できるよう、非モーダル・スクロール可能なダイアログで表示する
        # (ピーク検出・曲線フィットと同じ方針)
        if self.integral_result_dialog is not None:
            self.integral_result_dialog.close()
        integral_csv_data = pd.DataFrame({
            'X': result['x_used'],
            'Y(元データ)': result['y_raw_used'],
            'Y(積分に使用)': result['y_used'],
        })
        self.integral_result_dialog = ResultDialog(
            "区間積分完了", result_text, self._host.parent_widget, csv_data=integral_csv_data
        )
        self.integral_result_dialog.show()

    def cumulative_integral(self):
        """
        「累積積分(台形則/Simpson則)...」メニューの処理(項目C-303)。
        カレントの1つのデータセットについて、Xの各点までの積分値
        (calculate_cumulative_integral)を計算し、新しいデータセットとして
        追加する。_on_savgol_dataset/_on_baseline_correction_datasetと同じ
        「カレント1件から新しいデータセットを1つ作る」パターン(区間積分
        _on_interval_integral_datasetとは異なり、結果はスカラーではなく系列)。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 2:
            QMessageBox.warning(self._host.parent_widget, "累積積分", "有効なデータ点が不足しています(最低2点必要)。")
            return

        dialog = CumulativeIntegralDialog(original_dataset.name, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        try:
            result = calculate_cumulative_integral(x_data, y_data, method=method)
        except ValueError as e:
            QMessageBox.warning(self._host.parent_widget, "累積積分", str(e))
            return

        result_df = pd.DataFrame({'x': result['x_used'], 'y': result['y_cumulative']})
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=build_provenance(
                'cumulative_integral', {'method': method}, [original_dataset],
            ),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
        self._host.show_status(f"「{output_name}」を追加しました", 3000)

    def split_by_column(self):
        """
        「列の値で系列に分割...」メニューの処理(改善ボード D-1)。

        1つのファイルに「試料名」「条件」「測定日」のような区分列があり、
        その値ごとに系列を分けたい(long形式データの取り込み)ケースに対応する。
        従来は「行フィルタ」を条件の数だけ手作業で繰り返すしかなかった。

        分割列を選ぶと groupby で分け、各グループを新しいデータセットとして
        一括追加する。名前は「元の名前 (値)」。X/Y列の選択は元のデータセットを
        引き継ぐ。

        - 元のデータセットは**残す**(非破壊)。不要なら削除すればよく、
          削除も改善ボード A-3 でUndo可能になっている。
        - 色はアクティブなパレットから順に割り当てる。Dataset.colorの既定値は
          固定の'#1f77b4'なので、そのままだと全系列が同じ色になり分割した意味が
          ほとんど無くなるため(グラデーションにしたい場合は追加後に
          「カラーマップから自動配色」(項目C-805)を掛ければよい)。
        - 追加は AddDatasetCommand 経由で、全体を1つのマクロにまとめる。
          N件の追加が Undo 1回で元に戻る。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        columns = list(original_dataset.df.columns)
        if not columns:
            QMessageBox.warning(self._host.parent_widget, "系列に分割", "分割に使える列がありません。")
            return

        split_col, ok = QInputDialog.getItem(
            self._host.parent_widget, "列の値で系列に分割",
            "分割に使う列(この列の値ごとに別々の系列になります):",
            columns, 0, False,
        )
        if not ok or not split_col:
            return

        try:
            result = split_dataframe_by_column(original_dataset.df, split_col)
        except ValueError as e:
            QMessageBox.warning(self._host.parent_widget, "系列に分割", str(e))
            return

        groups = result['groups']
        if len(groups) < 2:
            QMessageBox.information(
                self._host.parent_widget, "系列に分割",
                f"列「{split_col}」の値は{len(groups)}種類しかないため、"
                "分割しても系列は増えません。",
            )
            return

        if len(groups) > SPLIT_BY_COLUMN_CONFIRM_THRESHOLD:
            answer = QMessageBox.question(
                self._host.parent_widget, "系列に分割",
                f"列「{split_col}」の値は{len(groups)}種類あります。\n"
                f"同じ数({len(groups)}件)のデータセットを追加しますが、よろしいですか?\n\n"
                "(連続値の列を選んでいる場合は、意図しない大量の系列になります)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        color_cycle = self._host.active_color_cycle()
        target_folder = self._host.target_folder_for_new_dataset()

        self._host.undo_stack.beginMacro(f"列「{split_col}」で系列に分割 ({len(groups)}件)")
        try:
            for i, (label, sub_df) in enumerate(groups):
                new_dataset = Dataset(
                    name=f"{original_dataset.name} ({label})",
                    df=sub_df,
                    x_col_name=original_dataset.x_col_name,
                    y_col_name=original_dataset.y_col_name,
                    color=color_cycle[i % len(color_cycle)],
                    provenance=build_provenance(
                        'split_by_column',
                        {'split_column': split_col, 'group_value': label},
                        [original_dataset],
                    ),
                )
                self._host.add_dataset_with_undo(
                    new_dataset, target_folder,
                    description=f"「{new_dataset.name}」の追加",
                )
        finally:
            self._host.undo_stack.endMacro()

        message = f"列「{split_col}」の値で{len(groups)}件の系列に分割しました"
        if result['n_dropped']:
            message += f"(「{split_col}」が空の{result['n_dropped']}行は除外)"
        self._host.show_status(message, 5000)

    def resample(self):
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
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 2:
            QMessageBox.warning(self._host.parent_widget, "共通X格子へのリサンプリング/補間", "有効なデータ点が不足しています(最低2点必要)。")
            return

        other_dataset_names = [
            ds.name for ds in self._host.datasets() if ds is not original_dataset
        ]

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = ResampleDatasetDialog(
            original_dataset.name, other_dataset_names, x_min=x_min, x_max=x_max, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source, params, method, extrapolate, output_name = dialog.get_settings()
        if not output_name:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        if source == "dataset":
            target_dataset_name = params["dataset_name"]
            target_dataset = next(
                (ds for ds in self._host.datasets()
                 if ds is not original_dataset and ds.name == target_dataset_name),
                None
            )
            if target_dataset is None:
                QMessageBox.warning(
                    self._host.parent_widget, "共通X格子へのリサンプリング/補間",
                    "リサンプリング先のデータセットを選択してください。"
                )
                return
            target_x = np.asarray(target_dataset.x_data, dtype=float)
            target_x = target_x[~np.isnan(target_x)]
            if len(target_x) == 0:
                QMessageBox.warning(
                    self._host.parent_widget, "共通X格子へのリサンプリング/補間",
                    f"「{target_dataset_name}」に有効なX値がありません。"
                )
                return
        else:  # "linspace"
            start, stop, num_points = params["start"], params["stop"], params["num_points"]
            if start == stop:
                QMessageBox.warning(
                    self._host.parent_widget, "共通X格子へのリサンプリング/補間", "開始Xと終了Xが同じ値です。"
                )
                return
            target_x = np.linspace(start, stop, num_points)

        try:
            result_y = calculate_resample_to_grid(
                x_data, y_data, target_x, method=method, extrapolate=extrapolate
            )
        except ValueError as e:
            QMessageBox.warning(self._host.parent_widget, "共通X格子へのリサンプリング/補間", str(e))
            return

        # target_xは(dataset経由の場合)ソート済み・重複除去済みとは限らないため、
        # 出力データセットのXの並びとしてはtarget_xの並び順をそのまま使う
        # (calculate_savgol等と異なり「Xの昇順に正規化する」責務はここにはない —
        # ユーザーが選んだ格子の並び順をそのまま尊重する)。
        result_df = pd.DataFrame({'x': target_x, 'y': result_y})
        provenance_sources = [original_dataset] + ([target_dataset] if source == "dataset" else [])
        new_dataset = Dataset(
            name=output_name, df=result_df, x_col_name='x', y_col_name='y',
            provenance=build_provenance(
                'resample', {'source': source, 'method': method, 'extrapolate': extrapolate},
                provenance_sources,
            ),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
        self._host.show_status(f"「{output_name}」を追加しました", 3000)

    def histogram_or_kde(self):
        """
        「ヒストグラム / KDE...」メニューの処理(項目115、C-505)。カレントの
        1つのデータセットについて、任意の数値列を集計し(マスクされた行は
        visible_dfの慣例どおり除く)、ヒストグラム(区間ごとの度数/確率密度)
        またはカーネル密度推定(KDE)のどちらかを新しいデータセットとして
        追加する。_on_cumulative_integral_dataset等と同じ「カレント1件から
        新しいデータセットを1つ作る」パターン。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        numeric_columns = original_dataset.df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_columns:
            QMessageBox.warning(self._host.parent_widget, "ヒストグラム / KDE", "数値列がありません。")
            return
        default_column = original_dataset.y_col_name if original_dataset.y_col_name in numeric_columns else numeric_columns[0]

        dialog = HistogramKDEDialog(original_dataset.name, numeric_columns, default_column=default_column, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.get_settings()
        if not settings['output_name']:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        # マスクされた行はvisible_dfの慣例(core/dataset.pyのvisible_df参照)どおり
        # 集計対象から除く。
        column_data = original_dataset.visible_df[settings['column']]

        try:
            if settings['mode'] == 'histogram':
                result = calculate_histogram(column_data, bins=settings['bins'], density=settings['density'])
                result_df = pd.DataFrame({'x': result['bin_centers'], 'y': result['counts']})
                params = {'column': settings['column'], 'bins': settings['bins'], 'density': settings['density']}
                plot_type = 'Bar'
            else:
                result = calculate_kde(column_data, n_points=settings['n_points'])
                result_df = pd.DataFrame({'x': result['x_grid'], 'y': result['density']})
                params = {'column': settings['column'], 'n_points': settings['n_points']}
                plot_type = 'Line'
        except ValueError as e:
            QMessageBox.warning(self._host.parent_widget, "ヒストグラム / KDE", str(e))
            return

        new_dataset = Dataset(
            name=settings['output_name'], df=result_df, x_col_name='x', y_col_name='y',
            plot_type=plot_type,
            provenance=build_provenance(settings['mode'], params, [original_dataset]),
        )
        self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
        self._host.show_status(f"「{settings['output_name']}」を追加しました", 3000)

    def detect_duplicate_x(self):
        """
        「重複X値の検出...」メニューの処理(項目C-203)。カレントの1つの
        データセットについて、同じX値を持つ行を検出し、「平均化」(重複を
        集約した新しいデータセットを追加)または「除去」(先頭以外をマスク、
        項目36の非破壊マスク機構をそのまま使う)のどちらかを行う。

        重複検出自体はdataset.dfの全行(既にマスク済みの行も含む)を対象に
        行う(_on_filter_rows/_on_detect_outliersと違い「平均化」は
        dataset.x_data/y_data、つまり現在有効な=マスク済みを除いたデータを
        入力に使うが、「除去」でどの行をマスクするかの判定はdataset.df全体を
        対象にする、既存のrange_select_mixin.pyのマスク操作と同じ「df.index
        ラベルに対する集合演算」の考え方)。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_col = original_dataset.x_col_name
        duplicated_mask = original_dataset.df[x_col].duplicated(keep=False)
        n_duplicate_rows = int(duplicated_mask.sum())
        if n_duplicate_rows == 0:
            QMessageBox.information(self._host.parent_widget, "重複X値の検出", "重複するX値を持つ行は見つかりませんでした。")
            return

        dialog = DuplicateXDialog(original_dataset.name, n_duplicate_rows, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, output_name = dialog.get_settings()

        if mode == "average":
            if not output_name:
                QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
                return
            x_data = np.asarray(original_dataset.x_data, dtype=float)
            y_data = np.asarray(original_dataset.y_data, dtype=float)
            try:
                result = calculate_average_duplicate_x(x_data, y_data)
            except ValueError as e:
                QMessageBox.warning(self._host.parent_widget, "重複X値の検出", str(e))
                return
            result_df = pd.DataFrame({'x': result['x_used'], 'y': result['y_averaged']})
            new_dataset = Dataset(
                name=output_name, df=result_df, x_col_name='x', y_col_name='y',
                provenance=build_provenance(
                    'average_duplicate_x',
                    {'n_duplicate_groups': result['n_duplicate_groups'],
                     'n_points_in': result['n_points_in'], 'n_points_out': result['n_points_out']},
                    [original_dataset],
                ),
            )
            self._host.add_dataset(new_dataset, self._host.target_folder_for_new_dataset())
            self._host.show_status(f"「{output_name}」を追加しました", 3000)
        else:  # "remove"
            # keep='first': 各X値グループのうち最初に出現した行だけを残し、
            # 残りをマスクする(非破壊、いつでもDataEditorDialogから解除できる)。
            to_mask_indices = original_dataset.df.index[original_dataset.df[x_col].duplicated(keep='first')].tolist()
            old_masked = list(original_dataset.masked_row_indices)
            new_masked = sorted(set(old_masked) | set(to_mask_indices))
            if new_masked == old_masked:
                QMessageBox.information(self._host.parent_widget, "重複X値の検出", "既にすべてマスク済みです。")
                return
            command = SetMaskedRowsCommand(
                original_dataset, old_masked, new_masked,
                description=f"重複X値の除去({len(to_mask_indices)}件をマスク)",
            )
            self._host.undo_stack.push(command)
            self._host.redraw()
            self._host.show_status(f"{len(to_mask_indices)}件をマスクしました", 3000)

    def filter_rows(self):
        """
        「行フィルタ...」メニューの処理(項目C-204)。条件式(例: "y > 0.5")を
        core/safe_eval.pyのsafe_eval_column_formula()で評価し、条件を
        満たさない行をマスクする(項目36、非破壊)。既存のマスクとは
        union(和集合)で合成する(range_select_mixin.py等、他のマスク操作と
        同じ規約)。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        dialog = RowFilterDialog(original_dataset.df.columns.tolist(), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        formula = dialog.get_formula()
        if not formula:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "条件式が空です。")
            return

        try:
            match_result = safe_eval_column_formula(original_dataset.df, formula)
        except Exception as e:
            logger.exception("行フィルタの条件式を評価できませんでした")
            QMessageBox.warning(self._host.parent_widget, "行フィルタ", f"条件式の評価に失敗しました:\n{e}")
            return

        # 条件式が真偽値以外(数値計算式など)を返した場合、boolへのキャストで
        # 0/NaN以外を真として扱う(pandasのbool変換規約に委ねる)。NaNはFalse
        # 扱いになるようfillna(False)しておく(比較演算でNaNが混入した場合に
        # 「マスクしない」側へ誤って倒れるのを防ぐ)。
        try:
            match_bool = match_result.astype(bool)
        except (TypeError, ValueError):
            QMessageBox.warning(self._host.parent_widget, "行フィルタ", "条件式の結果を真偽値に変換できませんでした。")
            return
        match_bool = match_bool.fillna(False) if hasattr(match_bool, 'fillna') else match_bool

        to_mask_indices = original_dataset.df.index[~match_bool].tolist()
        old_masked = list(original_dataset.masked_row_indices)
        new_masked = sorted(set(old_masked) | set(to_mask_indices))
        if new_masked == old_masked:
            QMessageBox.information(self._host.parent_widget, "行フィルタ", "条件を満たさない(新たにマスクされる)行はありませんでした。")
            return

        command = SetMaskedRowsCommand(
            original_dataset, old_masked, new_masked,
            description=f"行フィルタ({formula})",
        )
        self._host.undo_stack.push(command)
        self._host.redraw()
        self._host.show_status(f"{len(new_masked) - len(old_masked)}件をマスクしました", 3000)

    def detect_outliers(self):
        """
        「外れ値検出(Z-score/IQR)...」メニューの処理(項目C-306)。Y値を
        基準にcore.analysis.calculate_zscore_outliers/calculate_iqr_outliersで
        外れ値候補を検出する。検出結果は常にResultDialogで表示し、ダイアログの
        「検出した外れ値をマスクに適用する」チェックボックスがONの場合のみ
        SetMaskedRowsCommandで実際にマスクする(自動では適用しない — ユーザー
        からの明示的な要望による設計)。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        y_data = np.asarray(original_dataset.y_data, dtype=float)
        if len(y_data) < 2:
            QMessageBox.warning(self._host.parent_widget, "外れ値検出", "有効なデータ点が不足しています(最低2点必要)。")
            return

        dialog = OutlierDetectionDialog(original_dataset.name, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method, value, apply_to_mask = dialog.get_settings()

        try:
            if method == "zscore":
                result = calculate_zscore_outliers(y_data, threshold=value)
                method_label = f"Z-score(しきい値 |Z| > {value:g})"
            else:
                result = calculate_iqr_outliers(y_data, multiplier=value)
                method_label = f"IQR(係数 {value:g})"
        except ValueError as e:
            QMessageBox.warning(self._host.parent_widget, "外れ値検出", str(e))
            return

        is_outlier = result['is_outlier']
        x_data = np.asarray(original_dataset.x_data, dtype=float)
        visible_index = original_dataset.visible_df.index

        result_text = f"[{original_dataset.name}] の外れ値検出結果:\n"
        result_text += f"  検出方法: {method_label}\n"
        result_text += f"  検出件数: {int(np.sum(is_outlier))}件 / 全{len(y_data)}件\n"

        if apply_to_mask and is_outlier.any():
            to_mask_indices = visible_index[is_outlier].tolist()
            old_masked = list(original_dataset.masked_row_indices)
            new_masked = sorted(set(old_masked) | set(to_mask_indices))
            command = SetMaskedRowsCommand(
                original_dataset, old_masked, new_masked,
                description=f"外れ値の自動マスク({method_label})",
            )
            self._host.undo_stack.push(command)
            self._host.redraw()
            result_text += f"  → {len(to_mask_indices)}件をマスクに追加しました。\n"
        elif apply_to_mask:
            result_text += "  (マスク対象の行はありませんでした)\n"
        else:
            result_text += "  (プレビューのみ、マスクは適用していません)\n"

        outlier_csv_data = pd.DataFrame({
            'X': x_data[is_outlier],
            'Y': y_data[is_outlier],
        })
        if self.outlier_result_dialog is not None:
            self.outlier_result_dialog.close()
        self.outlier_result_dialog = ResultDialog(
            "外れ値検出完了", result_text, self._host.parent_widget, csv_data=outlier_csv_data
        )
        self.outlier_result_dialog.show()

    def batch_column_calculate(self):
        """
        「バッチ列計算...」メニューの処理。
        選択中の複数データセットに、同じ計算式(safe_eval_column_formula)を一括で適用する。
        列計算は既存の _on_calculate_column (data_editor.py) と同様、
        Undo/Redoスタックを経由しない (df を直接書き換える) 点に注意。
        """
        selected = self._host.selected_datasets()
        if len(selected) < 2:
            QMessageBox.information(self._host.parent_widget, "バッチ列計算", "2つ以上のデータセットを選択してください。")
            return

        # 計算式の候補として、選択中の全データセットに共通する列名を提示する
        common_columns = set(selected[0].df.columns)
        for ds in selected[1:]:
            common_columns &= set(ds.df.columns)

        dialog = ColumnCalculatorDialog(sorted(str(c) for c in common_columns), self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_col, formula = dialog.get_formula()
        if not output_col or not formula:
            QMessageBox.warning(self._host.parent_widget, "入力エラー", "出力列または計算式が空です。")
            return

        succeeded, failed = [], []
        for dataset in selected:
            try:
                dataset.df[output_col] = safe_eval_column_formula(dataset.df, formula)
                dataset.invalidate_visible_df_cache()
                succeeded.append(dataset.name)
            except Exception as e:
                failed.append(f"{dataset.name}: {e}")

        self._host.refresh_ui_state()
        self._host.redraw()

        message = f"{len(succeeded)}件のデータセットに適用しました。"
        if failed:
            message += "\n\n失敗:\n" + "\n".join(failed)
        QMessageBox.information(self._host.parent_widget, "バッチ列計算", message)
