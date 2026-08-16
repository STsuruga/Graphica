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
from scipy.interpolate import griddata, RegularGridInterpolator

# 始点/終点がほぼ水平/垂直とみなす許容誤差(各軸の範囲に対する割合)。
# ドラッグ操作でピクセル単位の完全な水平/垂直はまず出せないため、
# 「見た目上は水平/垂直に引いたつもり」を汲み取るための閾値。
SLICE_AXIS_ALIGNMENT_TOLERANCE = 0.01

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


def extract_slice(x_grid, y_grid, z_grid, start, end, n_points=200):
    """
    2Dグリッド上の任意の線分に沿って1次元の断面(スライス)を抽出する
    (項目C-511)。x_grid/y_gridは常に規則的な1次元配列(compute_z_grid()の
    戻り値、実測データそのまま/補間結果のどちらでも同じ形)であるため、
    scipy.interpolate.RegularGridInterpolatorで線分上の任意の点をサンプリング
    できる。

    Args:
        x_grid, y_grid (array-like): compute_z_grid()の'x_grid'/'y_grid'
            (1次元、ソート済み)。
        z_grid (array-like): compute_z_grid()の'z_grid'(2次元、
            shape=(len(y_grid), len(x_grid)))。
        start, end (tuple[float, float]): 線分の始点・終点(x, y)。
        n_points (int): サンプリングする点数。

    Returns:
        dict: {
            'axis_values': np.ndarray (1次元、長さn_points。線分がほぼ水平なら
                サンプリング点のX座標、ほぼ垂直ならY座標、それ以外(斜めの線分)
                なら始点からの距離),
            'axis_kind': str ('x'/'y'/'distance'、axis_valuesが何を表すか。
                呼び出し側が新規データセットのX軸ラベルを決める材料),
            'z_values': np.ndarray (1次元、長さn_points。線分上の各点でのZ値。
                線分がグリッド範囲外に出た区間はnp.nan),
        }

    Raises:
        GridDataError: 始点と終点が同一の場合(線分の長さが0)。
    """
    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    if x0 == x1 and y0 == y1:
        raise GridDataError("始点と終点が同じ位置です(長さ0の線分は抽出できません)。")

    x_grid = np.asarray(x_grid, dtype=float)
    y_grid = np.asarray(y_grid, dtype=float)
    z_grid = np.asarray(z_grid, dtype=float)

    x_range = x_grid.max() - x_grid.min() if len(x_grid) > 1 else 1.0
    y_range = y_grid.max() - y_grid.min() if len(y_grid) > 1 else 1.0

    is_horizontal = abs(y1 - y0) <= SLICE_AXIS_ALIGNMENT_TOLERANCE * (y_range or 1.0)
    is_vertical = abs(x1 - x0) <= SLICE_AXIS_ALIGNMENT_TOLERANCE * (x_range or 1.0)

    if is_horizontal and not is_vertical:
        axis_kind = 'x'
        axis_values = np.linspace(x0, x1, n_points)
        sample_x, sample_y = axis_values, np.full(n_points, y0)
    elif is_vertical and not is_horizontal:
        axis_kind = 'y'
        axis_values = np.linspace(y0, y1, n_points)
        sample_x, sample_y = np.full(n_points, x0), axis_values
    else:
        axis_kind = 'distance'
        sample_x = np.linspace(x0, x1, n_points)
        sample_y = np.linspace(y0, y1, n_points)
        axis_values = np.sqrt((sample_x - x0) ** 2 + (sample_y - y0) ** 2)

    interpolator = RegularGridInterpolator(
        (y_grid, x_grid), z_grid, method='linear', bounds_error=False, fill_value=np.nan,
    )
    z_values = interpolator(np.column_stack([sample_y, sample_x]))

    return {'axis_values': axis_values, 'axis_kind': axis_kind, 'z_values': z_values}
