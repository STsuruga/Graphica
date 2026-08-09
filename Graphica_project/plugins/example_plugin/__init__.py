# plugins/example_plugin/__init__.py
"""
Graphicaプラグインのサンプル実装。

プラグインの作り方を示すための最小限の例:
- カーブフィットの選択肢に「二重指数減衰」を追加する
- 「プラグイン」メニューに、選択中データセットの点数を表示するアクションを追加する

このファイル(と隣の plugin.json / register()）が、プラグインとして
認識されるために必要な最小構成のすべて(項目F-1: マニフェストは
plugin.jsonに分離、__init__.pyにPLUGIN_INFO辞書は不要)。他のプラグインを
作る際は、plugins/ 配下に別のサブフォルダをコピーして書き換えればよい。
"""
import numpy as np
from PySide6.QtWidgets import QMessageBox


def _double_exp_func(x, a, b, c, d):
    """二重指数減衰: y = a * exp(-b*x) + c * exp(-d*x)"""
    return a * np.exp(-b * x) + c * np.exp(-d * x)


def _double_exp_p0(x_data, y_data):
    amplitude = float(np.nanmax(np.abs(y_data))) or 1.0
    return [amplitude, 1.0, amplitude, 0.1]


def _show_dataset_point_count(main_window):
    """「プラグイン」メニューのアクション: 選択中データセットの点数をダイアログで表示する"""
    dataset = main_window._get_current_dataset()
    if dataset is None:
        QMessageBox.information(main_window, "Example Plugin", "データセットが選択されていません。")
        return
    QMessageBox.information(
        main_window, "Example Plugin",
        f"「{dataset.name}」の表示中の点数: {len(dataset.visible_df)}"
    )


def register(api):
    api.register_fit_function(
        "二重指数減衰 (y = a*exp(-bx) + c*exp(-dx))",
        _double_exp_func,
        ["a", "b", "c", "d"],
        p0=_double_exp_p0,
    )
    api.register_menu_action("選択中データセットの点数を表示", _show_dataset_point_count)
