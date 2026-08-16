# core/grid_data.py
"""
2Dマップ(ヒートマップ/等高線、項目C-508/C-509)のための、散布(x, y, z)データ
→ 2Dグリッド変換ロジック。GUI(gui/canvas.py)には一切依存しない純粋関数群とし、
core/dataset.pyのDataset.z_gridプロパティ(キャッシュ層)から呼ばれる想定。

測定データの(x, y)が完全な直積格子(全てのユニークなxとyの組み合わせが
ちょうど1回ずつ存在する)であれば、pandas.pivotでそのままZグリッドを組み立てる
(is_regular=True、実データそのまま、補間による値の改変が無い)。そうでない
散在データ(不規則な格子、欠損の多い測定等)は、項目C-510の
scipy.interpolate.griddataで規則格子へ補間する(is_regular=False)。
呼び出し側(Dataset.z_grid)がこの2ケースを意識せず同じ形の戻り値を使えるように
統一している。
"""
import numpy as np
import pandas as pd
from scipy.interpolate import griddata

# griddataのmethod引数として有効な値(項目C-510)
GRID_INTERP_METHODS = ('linear', 'cubic', 'nearest')


class GridDataError(ValueError):
    """2Dグリッドデータの構築に失敗した場合に送出する。"""


def is_regular_grid(x, y):
    """
    (x, y)の組み合わせが完全な直積格子かどうかを判定する。
    「ユニークなxの数 × ユニークなyの数 == 全体の点数」かつ「全ての(x,y)組み合わせが
    重複なくちょうど1回ずつ存在する」の両方を満たす場合のみTrue。
    """
    unique_x = np.unique(x)
    unique_y = np.unique(y)
    if len(unique_x) * len(unique_y) != len(x):
        return False
    pairs = set(zip(x.tolist(), y.tolist()))
    return len(pairs) == len(x)


def compute_z_grid(x, y, z, interp_method='linear', resolution=None):
    """
    散布(x, y, z)データから、pcolormesh/imshow等の2D描画にそのまま使える
    グリッドを構築する(項目C-508、散在データは項目C-510のgriddata補間を
    自動的に経由する)。

    Args:
        x, y, z (array-like): 同じ長さの1次元配列。
        interp_method (str): 'linear'/'cubic'/'nearest'
            (scipy.interpolate.griddataのmethod引数、散在データの補間時のみ使用、
            規則格子の場合は無視される)。
        resolution (tuple[int, int] | None): 散在データを補間する際の出力グリッドの
            解像度(nx, ny)。Noneならデータの点数から自動決定する
            (点数の平方根の2倍、最低10点)。

    Returns:
        dict: {
            'x_grid': np.ndarray (1次元、ソート済みのX軸グリッド座標),
            'y_grid': np.ndarray (1次元、ソート済みのY軸グリッド座標),
            'z_grid': np.ndarray (2次元、shape=(len(y_grid), len(x_grid))、
                補間grid点でデータが無い場所はnp.nan),
            'is_regular': bool (Trueなら実測データそのままの格子、
                Falseならgriddataによる補間結果),
        }

    Raises:
        GridDataError: 有効なデータ点が1つも無い場合、またはinterp_methodが不明な場合。
    """
    if interp_method not in GRID_INTERP_METHODS:
        raise GridDataError(f"不明な補間方法です: {interp_method}")

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)

    valid = ~(np.isnan(x) | np.isnan(y) | np.isnan(z))
    x, y, z = x[valid], y[valid], z[valid]

    if len(x) == 0:
        raise GridDataError("有効なデータ点がありません(すべて欠損値です)。")

    if is_regular_grid(x, y):
        x_grid = np.unique(x)
        y_grid = np.unique(y)
        pivot = pd.DataFrame({'x': x, 'y': y, 'z': z}).pivot(index='y', columns='x', values='z')
        pivot = pivot.reindex(index=y_grid, columns=x_grid)
        return {
            'x_grid': x_grid,
            'y_grid': y_grid,
            'z_grid': pivot.values,
            'is_regular': True,
        }

    if resolution is None:
        n = max(int(np.sqrt(len(x)) * 2), 10)
        nx, ny = n, n
    else:
        nx, ny = resolution
        if nx < 2 or ny < 2:
            raise GridDataError("補間グリッドの解像度は2以上である必要があります。")

    if len(x) < 3:
        raise GridDataError(
            "散在データの補間には最低3点が必要です(規則格子ではない点が"
            f"{len(x)}点しかありません)。"
        )

    x_grid = np.linspace(x.min(), x.max(), nx)
    y_grid = np.linspace(y.min(), y.max(), ny)
    xx, yy = np.meshgrid(x_grid, y_grid)
    z_grid = griddata((x, y), z, (xx, yy), method=interp_method)

    return {
        'x_grid': x_grid,
        'y_grid': y_grid,
        'z_grid': z_grid,
        'is_regular': False,
    }
