"""データセットの処理の流れ(対象の確認 → ダイアログ → 入力の確認 → 計算 → 結果の追加)を担う実行役。

操作ごとの違い(確認の順番、警告の題と文言、例外を捕まえる範囲、Undo の有無)は操作の本体に残す。
ここで捕まえるのは本体が calculate() に渡した計算の ValueError だけで、それ以外の例外は今までどおり外に出る。
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np
from PySide6.QtWidgets import QDialog

from graphica.gui import notify

INPUT_ERROR_TITLE = "入力エラー"
EMPTY_OUTPUT_NAME_TEXT = "出力データセット名が空です。"


class OperationStopped(Exception):
    """流れを止める。知らせる必要があれば、止める前に知らせてある。"""


class OperationState:
    """操作をまたいで持つもの。非モーダルの結果の窓は、次に同じ処理をしたときに閉じる。"""

    def __init__(self):
        self.result_windows = {}
        self.copied_style = None  # スタイルのコピーの控え(貼り付けるまで持つ)
        self.runners = {}  # バックグラウンドで動いている計算。終わるまで同じ種類の計算は始めない


@dataclass(frozen=True)
class Operation:
    title: str  # 警告・お知らせの題
    body: Callable[["OperationContext"], None]


class OperationContext:
    """操作の本体に渡す。流れを止める手順と、結果の追加の手順を持つ。"""

    def __init__(self, host, state, title):
        self.host = host
        self.state = state
        self.title = title

    @property
    def parent(self):
        return self.host.parent_widget

    # --- 流れを止める ---

    def stop(self):
        raise OperationStopped

    def stop_with_warning(self, text, title=None):
        notify.warning(self.parent, title or self.title, text)
        raise OperationStopped

    def stop_with_information(self, text, title=None):
        notify.information(self.parent, title or self.title, text)
        raise OperationStopped

    def information(self, text, title=None):
        notify.information(self.parent, title or self.title, text)

    # --- 対象 ---

    def current_dataset(self):
        """今のデータセット。無ければ何も言わずに止める。"""
        dataset = self.host.current_dataset()
        if dataset is None:
            self.stop()
        return dataset

    def selected_datasets(self, *, exactly=None, at_least=None, message=None):
        """数が合わなければ止める。message が無ければ何も言わずに止める。"""
        selected = self.host.selected_datasets()
        if (exactly is not None and len(selected) != exactly) or (at_least is not None and len(selected) < at_least):
            if message is None:
                self.stop()
            self.stop_with_information(message)
        return selected

    def as_numbers(self, dataset, axis):
        """X か Y の列を数に直す。文字の列(カテゴリ軸)なら、その処理の題で知らせて止める。"""
        values, column = (dataset.x_data, dataset.x_col_name) if axis == "x" else (dataset.y_data, dataset.y_col_name)
        try:
            return np.asarray(values, dtype=float)
        except (TypeError, ValueError):
            if axis == "x":
                self.stop_with_warning(
                    f"X軸の列「{column}」が数値ではないため、この処理はできません"
                    "(文字の列はカテゴリ軸として表示だけできます)。")
            self.stop_with_warning(f"Y軸の列「{column}」が数値ではないため、この処理はできません。")

    def valid_points(self, dataset):
        """X と Y を数に直し、どちらかが NaN の点を除く。"""
        x = self.as_numbers(dataset, "x")
        y = self.as_numbers(dataset, "y")
        valid = ~(np.isnan(x) | np.isnan(y))
        return x[valid], y[valid]

    # --- ダイアログと入力 ---

    def ask(self, dialog):
        """取り消されたら止める。"""
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.stop()
        return dialog

    def require_output_name(self, output_name):
        if not output_name:
            self.stop_with_warning(EMPTY_OUTPUT_NAME_TEXT, title=INPUT_ERROR_TITLE)

    def calculate(self, compute):
        """compute() の ValueError は、その文言を警告にして止める。"""
        try:
            return compute()
        except ValueError as e:
            self.stop_with_warning(str(e))

    # --- 結果 ---

    def add(self, dataset):
        """Undo できる追加。Undo の名前はその処理の題。"""
        self.host.add_dataset_with_undo(dataset, self.host.target_folder_for_new_dataset(), description=self.title)

    def status(self, text, timeout_ms):
        self.host.show_status(text, timeout_ms)

    def add_and_report(self, dataset, timeout_ms=3000):
        self.add(dataset)
        self.status(f"「{dataset.name}」を追加しました", timeout_ms)

    def show_result_window(self, key, create_window):
        """同じ key の前の窓を閉じてから作って出す。"""
        previous = self.state.result_windows.get(key)
        if previous is not None:
            previous.close()
        window = create_window()
        self.state.result_windows[key] = window
        window.show()


def run_operation(operation, host, state):
    try:
        operation.body(OperationContext(host, state, operation.title))
    except OperationStopped:
        pass
