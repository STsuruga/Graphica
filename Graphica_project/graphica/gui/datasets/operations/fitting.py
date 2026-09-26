"""曲線フィット(単発・一括・多峰分離)と、フィット結果の再表示・注釈への焼き込みの本体。"""
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from graphica.gui import notify
from graphica.core.analysis import (calculate_confidence_band, calculate_curve_fit, fit_curve_task,
                                    get_fit_model_id, multi_peak_fit_task)
from graphica.core.dataset import Dataset
from graphica.core.fit_models import fit_type_label
from graphica.core.provenance import build_provenance
from graphica.gui.datasets.operations.runner import Operation
from graphica.gui.dialogs import FitDialog, MultiPeakFitDialog, ResultDialog
from graphica.gui.task_runner import TaskRunner


def build_fit_result_dict(fit_type, custom_formula, fit, weighted, x_range, source_dataset,
                          p0_overrides=None, fixed_params=None, bounds=None, loss='linear'):
    """Dataset.fit_result に保存する形。pickle と JSON の両方で往復できるよう素の Python 型にする。"""
    popt, pcov, perr = fit['popt'], fit['pcov'], fit['perr']
    return {
        'fit_type': fit_type,
        'fit_model_id': get_fit_model_id(fit_type),
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
        'p0_overrides': dict(p0_overrides) if p0_overrides else {},
        'fixed_params': dict(fixed_params) if fixed_params else {},
        'bounds': {k: [float(v[0]), float(v[1])] for k, v in bounds.items()} if bounds else {},
        'loss': loss,
    }


def build_multi_peak_fit_result_dict(fit, source_dataset):
    """多峰分離版。component_type / n_components は core/methods_text.py が参照するので名前を変えない。"""
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


def add_band_columns_to_fit_df(fit_df, fit, band_type):
    """
    信頼帯・予測帯の y_lower / y_upper 列を足し、足せた band_type を返す(Dataset.fit_band_display 用)。
    自由度不足などで計算できなければ列を足さず None。フィット自体は成功なので失敗にしない。
    """
    if band_type is None:
        return None
    try:
        band = calculate_confidence_band(
            fit['x_fit'], fit['fit_func'], fit['popt'], fit['pcov'], fit['residuals'], band_type=band_type,
        )
    except ValueError:
        return None
    fit_df['y_lower'] = band['y_lower']
    fit_df['y_upper'] = band['y_upper']
    return band_type


def _param_lines(param_names, params, errors, fixed_params=None):
    """「名前 = 値 ± 標準誤差」。固定したパラメータと、誤差を持たない古い結果は値だけ。"""
    fixed = fixed_params or {}
    if errors is None:
        errors = [None] * len(params)
    text = ""
    for name, value, err in zip(param_names, params, errors):
        if err is None or name in fixed:
            text += f"  {name} = {value: .4e}\n"
        else:
            text += f"  {name} = {value: .4e} ± {err:.1e}\n"
    return text


def _fit_summary_text(fit_type, custom_formula, param_names, params, param_errors, r_squared,
                      weighted, x_range, fixed_params, bounds, loss):
    fit_label = fit_type if custom_formula is None else f"{fit_type} {custom_formula}"
    text = f"[{fit_label}] のフィッティング結果:\n"
    text += _param_lines(param_names, params, param_errors, fixed_params)
    text += f"  R^2 = {r_squared: .5f}\n"
    if weighted:
        text += "  (Y誤差列を重みとして使用)\n"
    if x_range is not None:
        text += f"  (フィット範囲: {x_range[0]: .4g} 〜 {x_range[1]: .4g})\n"
    if fixed_params:
        text += f"  (固定: {fixed_params})\n"
    if bounds:
        text += f"  (範囲拘束: {bounds})\n"
    if loss != 'linear':
        text += f"  (ロバストフィット: {loss})\n"
    return text


def multi_peak_summary_text(component_label, n_components, param_names, params, param_errors, r_squared):
    text = f"[多峰分離({component_label} x{n_components})] のフィッティング結果:\n"
    text += _param_lines(param_names, params, param_errors)
    return text + f"  R^2 = {r_squared: .5f}\n"


def format_fit_result_text(fit_result):
    """保存済みの fit_result だけから、フィット直後と同じ体裁の結果文を作る(再フィットしない)。"""
    return _fit_summary_text(
        fit_type_label(fit_result), fit_result.get('custom_formula'),
        fit_result.get('param_names', []), fit_result.get('params', []), fit_result.get('param_errors'),
        fit_result.get('r_squared', float('nan')), fit_result.get('weighted'), fit_result.get('x_range'),
        fit_result.get('fixed_params'), fit_result.get('bounds'), fit_result.get('loss', 'linear'),
    )


def _fit_dataset(source, fit, fit_type, custom_formula, sigma, x_range,
                 p0_overrides, fixed_params, bounds, band_type, loss, operation):
    """フィット結果から「Fit (元の名前)」のデータセットを作る。GUI に触れないのでワーカーからも呼べる。"""
    fit_result = build_fit_result_dict(
        fit_type=fit_type, custom_formula=custom_formula, fit=fit,
        weighted=sigma is not None, x_range=x_range, source_dataset=source,
        p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds, loss=loss,
    )
    text = _fit_summary_text(fit_type, custom_formula, fit['param_names'], fit['popt'], fit['perr'], fit['r_squared'],
                             sigma is not None, x_range, fixed_params, bounds, loss)
    fit_df = pd.DataFrame({'x_fit': fit['x_fit'], 'y_fit': fit['y_fit']})
    applied_band_type = add_band_columns_to_fit_df(fit_df, fit, band_type)
    dataset = Dataset(
        name=f"Fit ({source.name})", df=fit_df, x_col_name='x_fit', y_col_name='y_fit',
        color=source.color, linestyle='--', marker='None', linewidth=source.linewidth,
        use_secondary_y=source.use_secondary_y, subplot_target=source.subplot_target,
        fit_info=text, fit_result=fit_result, fit_band_display=applied_band_type,
        provenance=build_provenance(operation, fit_result, [source]),
    )
    return dataset, text


def batch_fit_worker(datasets, fit_type, custom_formula, use_weighted, x_range,
                     p0_overrides, fixed_params, bounds, band_type, loss='linear',
                     report_progress=None, is_cancelled=None):
    """
    一括フィットの計算(バックグラウンドのスレッドで動く。Qt には触れない)。
    1件のフィットは中断できないので、キャンセルは「残りを飛ばす」単位。
    """
    results = []
    total = len(datasets)
    for i, dataset in enumerate(datasets):
        if is_cancelled is not None and is_cancelled():
            break
        if report_progress is not None:
            report_progress(i, total, dataset.name)
        sigma = dataset.y_err_data if use_weighted else None
        try:
            fit = calculate_curve_fit(
                dataset.x_data, dataset.y_data, fit_type, custom_formula=custom_formula,
                sigma=sigma, x_range=x_range,
                p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds, loss=loss,
            )
        except Exception as e:
            results.append({'source_name': dataset.name, 'fit_dataset': None, 'error': str(e)})
            continue
        fit_dataset, _ = _fit_dataset(dataset, fit, fit_type, custom_formula, sigma, x_range,
                                      p0_overrides, fixed_params, bounds, band_type, loss, 'batch_curve_fit')
        results.append({'source_name': dataset.name, 'fit_dataset': fit_dataset, 'error': None})
    return results


def stop_runner(runner):
    """実行中の QThread を破棄すると Qt がプロセスを落とすので、切断してから終わるまで待つ。"""
    try:
        runner.succeeded.disconnect()
        runner.failed.disconnect()
    except (RuntimeError, TypeError):
        pass
    runner.requestInterruption()
    runner.wait()
    runner.deleteLater()


FIT_RESULT_WINDOW = "fit"
FIT_RUNNER = "fit_runner"
BATCH_FIT_RUNNER = "batch_fit_runner"
MULTI_PEAK_FIT_RUNNER = "multi_peak_fit_runner"
RUNNER_NAMES = (FIT_RUNNER, BATCH_FIT_RUNNER, MULTI_PEAK_FIT_RUNNER)

_BUSY_TITLE = "実行中"
_FIT_BUSY_TEXT = "別のフィット処理が実行中です。完了までお待ちください。"
_EXPORT_TITLE = "フィット結果のエクスポート"

# 計算の終わりを受ける関数は run_operation の外(Qt のシグナル)で呼ばれるので、流れを止める例外は投げない。


def _show_result(op, title, text, csv_data, residual_x, residual_y):
    op.show_result_window(FIT_RESULT_WINDOW, lambda: ResultDialog(
        title, text, op.parent, csv_data=csv_data, residual_x=residual_x, residual_y=residual_y))


def _ensure_idle(op, runner_name, text):
    if op.state.runners.get(runner_name) is not None:
        op.stop_with_information(text, title=_BUSY_TITLE)


def _finish_runner(op, runner_name):
    runner = op.state.runners.get(runner_name)
    if runner is not None:
        runner.wait()
        runner.deleteLater()
        op.state.runners[runner_name] = None


# --- 単発フィット ---

def fit_current_dataset(op):
    """設定はダイアログで集め、計算はバックグラウンドで行う。"""
    source = op.current_dataset()
    _ensure_idle(op, FIT_RUNNER, _FIT_BUSY_TEXT)
    x_data, y_data = source.x_data, source.y_data
    x_min = float(np.min(x_data)) if len(x_data) else None
    x_max = float(np.max(x_data)) if len(x_data) else None
    (fit_type, custom_formula, use_weighted, x_range,
     p0_overrides, fixed_params, bounds, band_type, loss) = FitDialog.get_fit_type(op.parent, x_min=x_min, x_max=x_max)
    if fit_type is None:
        op.stop()
    sigma = source.y_err_data if use_weighted else None

    runner = TaskRunner(
        fit_curve_task, x_data, y_data, fit_type, custom_formula=custom_formula,
        sigma=sigma, x_range=x_range,
        p0_overrides=p0_overrides, fixed_params=fixed_params, bounds=bounds, loss=loss,
    )
    runner.succeeded.connect(lambda fit: _on_fit_succeeded(
        op, source, fit_type, custom_formula, sigma, x_range, p0_overrides, fixed_params, bounds, band_type, loss, fit,
    ))
    runner.failed.connect(lambda error_message: _on_fit_failed(op, error_message))
    op.state.runners[FIT_RUNNER] = runner
    op.host.set_fit_button_enabled(False)
    runner.start()


def _finish_fit_runner(op):
    _finish_runner(op, FIT_RUNNER)
    op.host.set_fit_button_enabled(True)


def _on_fit_failed(op, error_message):
    _finish_fit_runner(op)
    notify.warning(op.parent, "フィットエラー", f"フィッティングに失敗しました:\n{error_message}")


def _on_fit_succeeded(op, source, fit_type, custom_formula, sigma, x_range,
                      p0_overrides, fixed_params, bounds, band_type, loss, fit):
    _finish_fit_runner(op)
    dataset, text = _fit_dataset(source, fit, fit_type, custom_formula, sigma, x_range,
                                 p0_overrides, fixed_params, bounds, band_type, loss, 'curve_fit')
    op.host.add_derived_dataset(dataset, source)
    csv_data = pd.DataFrame({
        'パラメータ': list(fit['param_names']) + ['R^2'],
        '値': list(fit['popt']) + [fit['r_squared']],
    })
    # 残差は NaN の除外とフィット範囲の適用後の点なので、x もそれに合わせる
    _show_result(op, "フィッティング完了", text, csv_data, fit['x_data_used'], fit['residuals'])


# --- 一括フィット ---

def batch_fit_selected(op):
    """選択中の各データセットに同じ設定でフィットする。結果はまとめて足し、描き直しは1回だけ。"""
    parent = op.parent
    selected = op.selected_datasets(at_least=2, message="2つ以上のデータセットを選択してください。")
    _ensure_idle(op, BATCH_FIT_RUNNER, "別のバッチフィット処理が実行中です。完了までお待ちください。")
    (fit_type, custom_formula, use_weighted, x_range,
     p0_overrides, fixed_params, bounds, band_type, loss) = FitDialog.get_fit_type(parent)
    if fit_type is None:
        op.stop()
    target_folder = op.host.target_folder_for_new_dataset()

    progress = QProgressDialog("バッチカーブフィットを実行中...", "キャンセル", 0, len(selected), parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)

    runner = TaskRunner(
        batch_fit_worker, selected, fit_type, custom_formula, use_weighted, x_range,
        p0_overrides, fixed_params, bounds, band_type, loss,
    )
    runner.progress.connect(lambda done, total, message: progress.setValue(done))
    progress.canceled.connect(runner.requestInterruption)
    runner.succeeded.connect(lambda results: _on_batch_succeeded(op, results, target_folder, progress))
    runner.failed.connect(lambda msg: _on_batch_failed(op, msg, progress))
    op.state.runners[BATCH_FIT_RUNNER] = runner
    runner.start()


def _finish_batch_runner(op, progress):
    _finish_runner(op, BATCH_FIT_RUNNER)
    progress.close()


def _on_batch_failed(op, error_message, progress):
    _finish_batch_runner(op, progress)
    notify.warning(op.parent, op.title, f"バッチフィット処理に失敗しました:\n{error_message}")


def _on_batch_succeeded(op, results, target_folder, progress):
    """キャンセルされたときは、終わった分だけが results に入っている。"""
    _finish_batch_runner(op, progress)
    added = [r['fit_dataset'] for r in results if r['fit_dataset'] is not None]
    succeeded = [r['source_name'] for r in results if r['fit_dataset'] is not None]
    failed = [f"{r['source_name']}: {r['error']}" for r in results
              if r['fit_dataset'] is None and r['error'] is not None]
    if added:
        op.host.add_datasets_to_folder(added, target_folder)
    if not succeeded and not failed:
        return
    message = f"{len(succeeded)}件のフィットに成功しました。"
    if failed:
        message += "\n\n失敗:\n" + "\n".join(failed)
    notify.information(op.parent, op.title, message)


# --- 多峰分離フィット ---

def multi_peak_fit_current_dataset(op):
    """
    グラフ上のクリックで置いたピークの初期値をダイアログに引き継ぐ。ダイアログを閉じたら
    (OK でもキャンセルでも)置いた初期値は消し、配置モードも抜ける。
    """
    source = op.current_dataset()
    _ensure_idle(op, MULTI_PEAK_FIT_RUNNER, _FIT_BUSY_TEXT)
    x_data, y_data = source.x_data, source.y_data
    component_type, baseline_type, initial_guesses = MultiPeakFitDialog.get_multi_peak_fit_settings(
        op.parent, x_data=x_data, y_data=y_data, initial_guesses=op.host.pending_peak_guesses(),
    )
    op.host.finish_peak_placement()
    if component_type is None:
        op.stop()

    runner = TaskRunner(multi_peak_fit_task, x_data, y_data, component_type, initial_guesses,
                        baseline_type=baseline_type)
    runner.succeeded.connect(lambda fit: _on_multi_peak_fit_succeeded(op, source, fit))
    runner.failed.connect(lambda error_message: _on_multi_peak_fit_failed(op, error_message))
    op.state.runners[MULTI_PEAK_FIT_RUNNER] = runner
    op.host.set_multi_peak_fit_button_enabled(False)
    runner.start()


def _finish_multi_peak_runner(op):
    _finish_runner(op, MULTI_PEAK_FIT_RUNNER)
    op.host.set_multi_peak_fit_button_enabled(True)


def _on_multi_peak_fit_failed(op, error_message):
    _finish_multi_peak_runner(op)
    notify.warning(op.parent, "多峰分離フィットエラー", f"フィッティングに失敗しました:\n{error_message}")


def _on_multi_peak_fit_succeeded(op, source, fit):
    _finish_multi_peak_runner(op)
    popt, param_names, r_squared = fit['popt'], fit['param_names'], fit['r_squared']
    component_label = dict(MultiPeakFitDialog.COMPONENT_TYPES).get(fit['component_type'], fit['component_type'])
    text = multi_peak_summary_text(component_label, fit['n_components'], param_names, popt, fit['perr'], r_squared)

    fit_result = build_multi_peak_fit_result_dict(fit, source_dataset=source)
    op.host.add_derived_dataset(Dataset(
        name=f"MultiPeakFit ({source.name})",
        df=pd.DataFrame({'x_fit': fit['x_fit'], 'y_fit': fit['y_fit']}),
        x_col_name='x_fit', y_col_name='y_fit',
        color=source.color, linestyle='--', marker='None', linewidth=source.linewidth,
        use_secondary_y=source.use_secondary_y, subplot_target=source.subplot_target,
        fit_info=text, fit_result=fit_result,
        provenance=build_provenance('multi_peak_fit', fit_result, [source]),
    ), source)
    csv_data = pd.DataFrame({'パラメータ': list(param_names) + ['R^2'], '値': list(popt) + [r_squared]})
    _show_result(op, "多峰分離フィット完了", text, csv_data, fit['x_data_used'], fit['residuals'])


# --- 保存済みのフィット結果 ---

def show_fit_result(op):
    """
    現在のデータセットに保存されたフィット結果(fit_result)を、再フィットせずに表と残差で出し直す。
    続けて、要約をグラフの注釈として焼き込むかを尋ねる。
    """
    dataset = op.current_dataset()
    fit_result = dataset.fit_result
    if fit_result is None:
        # メニューは無効化しているが、別の経路から呼ばれたときのため
        op.stop_with_information(
            "このデータセットは曲線フィットの結果を持っていません。\n"
            "曲線フィットで生成されたデータセット(名前が「Fit (...)」の\n"
            "もの、またはfit_resultを保持しているもの)を選択してください。"
        )

    csv_data = pd.DataFrame({
        'パラメータ': list(fit_result.get('param_names', [])) + ['R^2'],
        '値': list(fit_result.get('params', [])) + [fit_result.get('r_squared')],
    })
    _show_result(op, op.title, format_fit_result_text(fit_result), csv_data,
                 fit_result.get('residual_x'), fit_result.get('residuals'))

    reply = notify.question(
        op.parent, op.title,
        "このフィット結果の要約(パラメータ値±誤差・R^2)を、\n"
        "グラフ上のテキスト注釈として焼き込みますか?\n"
        "(焼き込み後は注釈モードで通常の注釈と同様に移動・編集・削除できます)",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    if reply == QMessageBox.StandardButton.Yes:
        burn_fit_result_annotation(op, dataset, fit_result)


def burn_fit_result_annotation(op, dataset, fit_result):
    """
    フィット結果の要約を、手で置く注釈と同じテキスト注釈として足す(Undo でき、あとから編集できる)。
    置き場所はフィット曲線の中央の点。端やピークより、どの形の曲線でも曲線上の無難な位置になる。
    """
    axis_index = dataset.subplot_target
    if axis_index is None or axis_index >= op.host.axis_count():
        op.stop_with_warning("注釈を追加する対象のプロットが見つかりませんでした。")
    x_data, y_data = dataset.x_data, dataset.y_data
    if len(x_data) == 0:
        op.stop_with_warning("フィット曲線にデータ点が無いため、注釈を追加できませんでした。")
    mid = len(x_data) // 2
    anchor = (float(x_data[mid]), float(y_data[mid]))

    lines = [f"フィット: {fit_type_label(fit_result, '')}"]
    params = fit_result.get('params', [])
    errors = fit_result.get('param_errors', [None] * len(params))
    for name, value, err in zip(fit_result.get('param_names', []), params, errors):
        lines.append(f"{name} = {value:.4g} ± {err:.4g}" if err is not None else f"{name} = {value:.4g}")
    r_squared = fit_result.get('r_squared')
    if r_squared is not None:
        lines.append(f"R^2 = {r_squared:.5f}")

    op.host.add_annotation(axis_index, {
        'type': 'text', 'text': "\n".join(lines), 'xy': anchor, 'xytext': anchor, 'color': '#000000',
    }, description="フィット結果の注釈焼き込み")
    op.host.show_status("フィット結果を注釈として焼き込みました")


FITTING_OPERATIONS = {
    "fit_current_dataset": Operation("カーブフィット", fit_current_dataset),
    "batch_fit_selected": Operation("バッチカーブフィット", batch_fit_selected),
    "multi_peak_fit_current_dataset": Operation("多峰分離フィット", multi_peak_fit_current_dataset),
    "show_fit_result": Operation(_EXPORT_TITLE, show_fit_result),
}


def burn_operation(dataset, fit_result):
    return Operation(_EXPORT_TITLE, lambda op: burn_fit_result_annotation(op, dataset, fit_result))
