"""データセットのデータ処理(規格化・平滑化・ベースライン補正・積分・リサンプリング・データセット間の演算など)。"""
import logging
import numpy as np
import pandas as pd
from PySide6.QtWidgets import (QDialog, QMessageBox)

from graphica.gui import notify
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

# 列の値で分割したとき、これを超える数の系列ができるなら確認する(連続値の列を取り違えた疑い)。
SPLIT_BY_COLUMN_CONFIRM_THRESHOLD = 30


class ProcessingController:
    """現在のデータセット(または選択中の複数)から新しいデータセットを作る、または行を除外する処理。"""

    def __init__(self, host):
        self._host = host
        self.integral_result_dialog = None
        self.outlier_result_dialog = None

    def arithmetic(self):
        """選んだ2件 A・B の差・和・積・商を、B を A の X に線形補間してから計算し、新しいデータセットにする。"""
        selected = self._host.selected_datasets()
        if len(selected) != 2:
            notify.information(self._host.parent_widget, "データセット間演算", "演算対象として、データセットをちょうど2つ選択してください。")
            return
        ds_a, ds_b = selected[0], selected[1]

        dialog = DatasetArithmeticDialog(ds_a.name, ds_b.name, self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        operation, output_name = dialog.get_settings()
        if not output_name:
            notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        xa = np.asarray(ds_a.x_data, dtype=float)
        ya = np.asarray(ds_a.y_data, dtype=float)
        xb = np.asarray(ds_b.x_data, dtype=float)
        yb = np.asarray(ds_b.y_data, dtype=float)

        # 誤差は A・B の両方に誤差列があるときだけ伝播させる(片方だけだと不完全で誤解を招く)。
        # 誤差列は x_data/y_data と行が対応しているので、同じ絞り込みをそのまま掛けられる。
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
            notify.warning(self._host.parent_widget, "データセット間演算", "有効なデータ点がありません。")
            return

        lo, hi = max(np.min(xa), np.min(xb)), min(np.max(xa), np.max(xb))
        if lo > hi:
            notify.warning(self._host.parent_widget, "データセット間演算", "2つのデータセットのX軸の範囲が重なっていないため演算できません。")
            return

        mask = (xa >= lo) & (xa <= hi)
        xa_sub, ya_sub = xa[mask], ya[mask]
        if propagate_errors:
            err_a_sub = err_a_full[mask]
        if len(xa_sub) == 0:
            notify.warning(self._host.parent_widget, "データセット間演算", "重なる範囲にA側のデータ点がありません。")
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
        """選んだ2件のうち B を、A との相互相関で求めた X のずれだけ動かした新しいデータセットを作る(A が基準)。"""
        selected = self._host.selected_datasets()
        if len(selected) != 2:
            notify.information(self._host.parent_widget, "X軸アライメント", "位置合わせ対象として、データセットをちょうど2つ選択してください。")
            return
        ds_a, ds_b = selected[0], selected[1]

        dialog = XAxisAlignmentDialog(ds_a.name, ds_b.name, self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_name = dialog.get_settings()
        if not output_name:
            notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        xa = np.asarray(ds_a.x_data, dtype=float)
        ya = np.asarray(ds_a.y_data, dtype=float)
        xb = np.asarray(ds_b.x_data, dtype=float)
        yb = np.asarray(ds_b.y_data, dtype=float)

        try:
            result = calculate_cross_correlation_alignment(xa, ya, xb, yb)
        except ValueError as e:
            notify.warning(self._host.parent_widget, "X軸アライメント", str(e))
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
        選んだ2件以上を、X が重なる範囲の共通の格子へ線形補間し、点ごとの平均と標本標準偏差(ddof=1)を
        誤差列付きの新しいデータセットにする。格子の点数は最も点の多いデータセットに合わせる。
        """
        selected = self._host.selected_datasets()
        if len(selected) < 2:
            notify.information(self._host.parent_widget, "平均±SD生成", "平均±SDの生成には、データセットを2つ以上選択してください。")
            return

        x_arrays, y_arrays = [], []
        for ds in selected:
            x = np.asarray(ds.x_data, dtype=float)
            y = np.asarray(ds.y_data, dtype=float)
            valid = ~(np.isnan(x) | np.isnan(y))
            x, y = x[valid], y[valid]
            if len(x) < 2:
                notify.warning(
                    self._host.parent_widget, "平均±SD生成",
                    f"「{ds.name}」に有効なデータ点が不足しています(最低2点必要)。"
                )
                return
            x_arrays.append(x)
            y_arrays.append(y)

        x_min = max(float(np.min(x)) for x in x_arrays)
        x_max = min(float(np.max(x)) for x in x_arrays)
        if x_min >= x_max:
            notify.warning(self._host.parent_widget, "平均±SD生成", "選択したデータセット間でX軸の範囲が重なっていません。")
            return

        num_points = max(len(x) for x in x_arrays)
        common_x = np.linspace(x_min, x_max, num_points)

        resampled = []
        for x, y in zip(x_arrays, y_arrays):
            try:
                resampled.append(calculate_resample_to_grid(x, y, common_x, method='linear', extrapolate=False))
            except ValueError as e:
                notify.warning(self._host.parent_widget, "平均±SD生成", str(e))
                return
        stacked = np.vstack(resampled)  # (データセット数, num_points)

        mean_y = np.nanmean(stacked, axis=0)
        std_y = np.nanstd(stacked, axis=0, ddof=1)

        default_name = f"{selected[0].name} 他{len(selected) - 1}件の平均±SD"
        output_name, ok = notify.get_text(self._host.parent_widget, "平均±SD生成", "出力データセット名:", text=default_name)
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
        """今のデータセットの Y を、最大値か指定した X での値で割った新しいデータセットを作る。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) == 0:
            notify.warning(self._host.parent_widget, "規格化(ノーマライズ)", "有効なデータ点がありません。")
            return

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = NormalizeDatasetDialog(original_dataset.name, x_min=x_min, x_max=x_max, parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, reference_x, output_name = dialog.get_settings()
        if not output_name:
            notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        if mode == NormalizeDatasetDialog.MODE_MAX:
            reference_value = float(np.max(y_data))
        else:
            if reference_x < x_min or reference_x > x_max:
                notify.warning(
                    self._host.parent_widget, "規格化(ノーマライズ)",
                    f"指定されたX値 ({reference_x}) がデータセットのX軸範囲 "
                    f"({x_min} 〜 {x_max}) の外にあるため、規格化できません。"
                )
                return
            order = np.argsort(x_data)
            reference_value = float(np.interp(reference_x, x_data[order], y_data[order]))

        if abs(reference_value) < 1e-12:
            notify.warning(self._host.parent_widget, "規格化(ノーマライズ)", "基準値が0に近すぎるため、規格化できません。")
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
        """今のデータセットを Savitzky-Golay で平滑化(または微分)した新しいデータセットを作る。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 3:
            notify.warning(self._host.parent_widget, "Savitzky-Golayフィルタ", "有効なデータ点が不足しています。")
            return

        dialog = SavGolDialog(original_dataset.name, max_window=len(x_data), parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        window_length, polyorder, deriv, output_name = dialog.get_settings()
        if not output_name:
            notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        try:
            x_sorted, y_result = calculate_savgol(x_data, y_data, window_length, polyorder, deriv=deriv)
        except ValueError as e:
            notify.warning(self._host.parent_widget, "Savitzky-Golayフィルタ", str(e))
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
        """今のデータセットからベースラインを引いた新しいデータセットを作る(選べばベースライン自体も足す)。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 3:
            notify.warning(self._host.parent_widget, "ベースライン補正", "有効なデータ点が不足しています。")
            return

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = BaselineCorrectionDialog(original_dataset.name, x_min=x_min, x_max=x_max, parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method, params, output_name, add_baseline_dataset = dialog.get_settings()
        if not output_name:
            notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        try:
            if method == "als":
                x_sorted, baseline, corrected = calculate_baseline_als(x_data, y_data, **params)
            elif method == "polynomial":
                x_sorted, baseline, corrected = calculate_baseline_polynomial(x_data, y_data, **params)
            elif method == "rubberband":
                x_sorted, baseline, corrected = calculate_baseline_rubberband(x_data, y_data)
            else:  # "manual"
                # アンカー点は自由記入のテキストで来るので、ここで数に直す(書式の誤りも同じ警告で出す)
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
            notify.warning(self._host.parent_widget, "ベースライン補正", str(e))
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
        """今のデータセットの指定した X 範囲の積分値を、結果の窓(グラフを見ながら確かめられるよう非モーダル)に出す。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 2:
            notify.warning(self._host.parent_widget, "区間積分", "有効なデータ点が不足しています(最低2点必要)。")
            return

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = IntervalIntegralDialog(original_dataset.name, x_min=x_min, x_max=x_max, parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method, x_range, subtract_baseline = dialog.get_settings()

        try:
            result = calculate_interval_integral(
                x_data, y_data, x_range, method=method, subtract_baseline=subtract_baseline
            )
        except ValueError as e:
            notify.warning(self._host.parent_widget, "区間積分", str(e))
            return

        method_label = "台形則(Trapezoidal)" if method == "trapezoid" else "Simpson則"
        result_text = f"[{original_dataset.name}] の区間積分結果:\n"
        result_text += f"  積分方法: {method_label}\n"
        result_text += f"  積分範囲: {x_range[0]: .6g} 〜 {x_range[1]: .6g}\n"
        result_text += f"  ベースライン差し引き: {'あり(範囲両端を結ぶ直線)' if subtract_baseline else 'なし'}\n"
        result_text += f"  使用データ点数: {result['n_points']}\n"
        result_text += f"  積分値 = {result['integral']: .6e}\n"

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
        """今のデータセットの、X の各点までの積分値を新しいデータセットにする。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 2:
            notify.warning(self._host.parent_widget, "累積積分", "有効なデータ点が不足しています(最低2点必要)。")
            return

        dialog = CumulativeIntegralDialog(original_dataset.name, parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method, output_name = dialog.get_settings()
        if not output_name:
            notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        try:
            result = calculate_cumulative_integral(x_data, y_data, method=method)
        except ValueError as e:
            notify.warning(self._host.parent_widget, "累積積分", str(e))
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
        区分列(試料名・条件など)の値ごとに、今のデータセットを別々のデータセットに分ける。元は残す。
        Dataset.color の既定は全部同じ色なので、パレットから順に色を割り当てる。追加は Undo 1回分。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        columns = list(original_dataset.df.columns)
        if not columns:
            notify.warning(self._host.parent_widget, "系列に分割", "分割に使える列がありません。")
            return

        split_col, ok = notify.get_item(
            self._host.parent_widget, "列の値で系列に分割",
            "分割に使う列(この列の値ごとに別々の系列になります):",
            columns, 0, False,
        )
        if not ok or not split_col:
            return

        try:
            result = split_dataframe_by_column(original_dataset.df, split_col)
        except ValueError as e:
            notify.warning(self._host.parent_widget, "系列に分割", str(e))
            return

        groups = result['groups']
        if len(groups) < 2:
            notify.information(
                self._host.parent_widget, "系列に分割",
                f"列「{split_col}」の値は{len(groups)}種類しかないため、"
                "分割しても系列は増えません。",
            )
            return

        if len(groups) > SPLIT_BY_COLUMN_CONFIRM_THRESHOLD:
            answer = notify.question(
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
        """今のデータセットを、別のデータセットの X か等間隔の格子へ補間した新しいデータセットを作る。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_data = np.asarray(original_dataset.x_data, dtype=float)
        y_data = np.asarray(original_dataset.y_data, dtype=float)
        valid = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data, y_data = x_data[valid], y_data[valid]

        if len(x_data) < 2:
            notify.warning(self._host.parent_widget, "共通X格子へのリサンプリング/補間", "有効なデータ点が不足しています(最低2点必要)。")
            return

        other_dataset_names = [
            ds.name for ds in self._host.datasets() if ds is not original_dataset
        ]

        x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
        dialog = ResampleDatasetDialog(
            original_dataset.name, other_dataset_names, x_min=x_min, x_max=x_max, parent=self._host.parent_widget
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source, params, method, extrapolate, output_name = dialog.get_settings()
        if not output_name:
            notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

        if source == "dataset":
            target_dataset_name = params["dataset_name"]
            target_dataset = next(
                (ds for ds in self._host.datasets()
                 if ds is not original_dataset and ds.name == target_dataset_name),
                None
            )
            if target_dataset is None:
                notify.warning(
                    self._host.parent_widget, "共通X格子へのリサンプリング/補間",
                    "リサンプリング先のデータセットを選択してください。"
                )
                return
            target_x = np.asarray(target_dataset.x_data, dtype=float)
            target_x = target_x[~np.isnan(target_x)]
            if len(target_x) == 0:
                notify.warning(
                    self._host.parent_widget, "共通X格子へのリサンプリング/補間",
                    f"「{target_dataset_name}」に有効なX値がありません。"
                )
                return
        else:  # "linspace"
            start, stop, num_points = params["start"], params["stop"], params["num_points"]
            if start == stop:
                notify.warning(
                    self._host.parent_widget, "共通X格子へのリサンプリング/補間", "開始Xと終了Xが同じ値です。"
                )
                return
            target_x = np.linspace(start, stop, num_points)

        try:
            result_y = calculate_resample_to_grid(
                x_data, y_data, target_x, method=method, extrapolate=extrapolate
            )
        except ValueError as e:
            notify.warning(self._host.parent_widget, "共通X格子へのリサンプリング/補間", str(e))
            return

        # 選んだ格子の並び順をそのまま使う(並べ替えない)
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
        """今のデータセットの数値列1つのヒストグラムかカーネル密度推定を、新しいデータセットにする。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        numeric_columns = original_dataset.df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_columns:
            notify.warning(self._host.parent_widget, "ヒストグラム / KDE", "数値列がありません。")
            return
        default_column = original_dataset.y_col_name if original_dataset.y_col_name in numeric_columns else numeric_columns[0]

        dialog = HistogramKDEDialog(original_dataset.name, numeric_columns, default_column=default_column, parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.get_settings()
        if not settings['output_name']:
            notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
            return

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
            notify.warning(self._host.parent_widget, "ヒストグラム / KDE", str(e))
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
        同じ X の行を見つけ、平均した新しいデータセットを作るか、各 X の最初の行以外を除外(マスク)する。
        平均は除外済みの行を除いたデータから、除外する行の判定は df 全体から行う。
        """
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        x_col = original_dataset.x_col_name
        duplicated_mask = original_dataset.df[x_col].duplicated(keep=False)
        n_duplicate_rows = int(duplicated_mask.sum())
        if n_duplicate_rows == 0:
            notify.information(self._host.parent_widget, "重複X値の検出", "重複するX値を持つ行は見つかりませんでした。")
            return

        dialog = DuplicateXDialog(original_dataset.name, n_duplicate_rows, parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, output_name = dialog.get_settings()

        if mode == "average":
            if not output_name:
                notify.warning(self._host.parent_widget, "入力エラー", "出力データセット名が空です。")
                return
            x_data = np.asarray(original_dataset.x_data, dtype=float)
            y_data = np.asarray(original_dataset.y_data, dtype=float)
            try:
                result = calculate_average_duplicate_x(x_data, y_data)
            except ValueError as e:
                notify.warning(self._host.parent_widget, "重複X値の検出", str(e))
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
            to_mask_indices = original_dataset.df.index[original_dataset.df[x_col].duplicated(keep='first')].tolist()
            old_masked = list(original_dataset.masked_row_indices)
            new_masked = sorted(set(old_masked) | set(to_mask_indices))
            if new_masked == old_masked:
                notify.information(self._host.parent_widget, "重複X値の検出", "既にすべてマスク済みです。")
                return
            command = SetMaskedRowsCommand(
                original_dataset, old_masked, new_masked,
                description=f"重複X値の除去({len(to_mask_indices)}件をマスク)",
            )
            self._host.undo_stack.push(command)
            self._host.redraw()
            self._host.show_status(f"{len(to_mask_indices)}件をマスクしました", 3000)

    def filter_rows(self):
        """条件式を満たさない行を除外(マスク)する。今までの除外に足す。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        dialog = RowFilterDialog(original_dataset.df.columns.tolist(), parent=self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        formula = dialog.get_formula()
        if not formula:
            notify.warning(self._host.parent_widget, "入力エラー", "条件式が空です。")
            return

        try:
            match_result = safe_eval_column_formula(original_dataset.df, formula)
        except Exception as e:
            logger.exception("行フィルタの条件式を評価できませんでした")
            notify.warning(self._host.parent_widget, "行フィルタ", f"条件式の評価に失敗しました:\n{e}")
            return

        # 真偽値以外が返ったら pandas の規約で bool にする。NaN は偽(=除外する側)に倒す。
        try:
            match_bool = match_result.astype(bool)
        except (TypeError, ValueError):
            notify.warning(self._host.parent_widget, "行フィルタ", "条件式の結果を真偽値に変換できませんでした。")
            return
        match_bool = match_bool.fillna(False) if hasattr(match_bool, 'fillna') else match_bool

        to_mask_indices = original_dataset.df.index[~match_bool].tolist()
        old_masked = list(original_dataset.masked_row_indices)
        new_masked = sorted(set(old_masked) | set(to_mask_indices))
        if new_masked == old_masked:
            notify.information(self._host.parent_widget, "行フィルタ", "条件を満たさない(新たにマスクされる)行はありませんでした。")
            return

        command = SetMaskedRowsCommand(
            original_dataset, old_masked, new_masked,
            description=f"行フィルタ({formula})",
        )
        self._host.undo_stack.push(command)
        self._host.redraw()
        self._host.show_status(f"{len(new_masked) - len(old_masked)}件をマスクしました", 3000)

    def detect_outliers(self):
        """Y の外れ値を Z-score か IQR で探して結果を出す。除外(マスク)は利用者が選んだときだけ。"""
        original_dataset = self._host.current_dataset()
        if original_dataset is None:
            return

        y_data = np.asarray(original_dataset.y_data, dtype=float)
        if len(y_data) < 2:
            notify.warning(self._host.parent_widget, "外れ値検出", "有効なデータ点が不足しています(最低2点必要)。")
            return

        dialog = OutlierDetectionDialog(original_dataset.name, parent=self._host.parent_widget)
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
            notify.warning(self._host.parent_widget, "外れ値検出", str(e))
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
        """選んだデータセットすべてに同じ計算式で列を足す。データエディタの列計算と同じく Undo の対象ではない。"""
        selected = self._host.selected_datasets()
        if len(selected) < 2:
            notify.information(self._host.parent_widget, "バッチ列計算", "2つ以上のデータセットを選択してください。")
            return

        # 式の候補には、選んだデータセットすべてにある列だけを出す
        common_columns = set(selected[0].df.columns)
        for ds in selected[1:]:
            common_columns &= set(ds.df.columns)

        dialog = ColumnCalculatorDialog(sorted(str(c) for c in common_columns), self._host.parent_widget)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_col, formula = dialog.get_formula()
        if not output_col or not formula:
            notify.warning(self._host.parent_widget, "入力エラー", "出力列または計算式が空です。")
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
        notify.information(self._host.parent_widget, "バッチ列計算", message)
