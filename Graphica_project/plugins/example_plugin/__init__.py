"""
Graphica のプラグインのサンプル。

- 曲線フィットの選択肢に「二重指数減衰」を追加する
- 「プラグイン」メニューに、選択中のデータセットの点数を表示する項目を追加する

プラグインに要るのは、このフォルダの __init__.py(register(api) を定義する)と plugin.json だけ。
本体とのやりとりは、callback に渡る窓口(ctx: PluginContext)だけを使う。
"""
import numpy as np


def _double_exp_func(x, a, b, c, d):
    """y = a*exp(-b*x) + c*exp(-d*x)"""
    return a * np.exp(-b * x) + c * np.exp(-d * x)


def _double_exp_p0(x_data, y_data):
    amplitude = float(np.nanmax(np.abs(y_data))) or 1.0
    return [amplitude, 1.0, amplitude, 0.1]


def _show_dataset_point_count(ctx):
    dataset = ctx.current_dataset()
    if dataset is None:
        ctx.show_message("データセットが選択されていません。")
        return
    ctx.show_message(f"「{dataset.name}」の表示中の点数: {len(dataset.visible_df)}")


def register(api):
    api.register_fit_function(
        "二重指数減衰 (y = a*exp(-bx) + c*exp(-dx))",
        _double_exp_func,
        ["a", "b", "c", "d"],
        p0=_double_exp_p0,
    )
    api.register_menu_action("選択中データセットの点数を表示", _show_dataset_point_count)
