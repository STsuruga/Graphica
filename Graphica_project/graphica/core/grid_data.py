"""(x, y, z) の点から 2D マップの格子を作る。GUI には依存しない。

(x, y) が完全な格子なら pivot でそのまま並べ(is_regular=True、値を変えない)、そうでなければ griddata で補間する。
"""
import numpy as np
import pandas as pd
from scipy.interpolate import griddata, RegularGridInterpolator
from typing import Any

# ドラッグでぴったり水平・垂直には引けないので、各軸の範囲に対するこの割合までは水平・垂直とみなす
SLICE_AXIS_ALIGNMENT_TOLERANCE = 0.01

GRID_INTERP_METHODS = ('linear', 'cubic', 'nearest')


class GridDataError(ValueError):
    """2D の格子を作れない。"""


def is_regular_grid(x: Any, y: Any) -> bool:
    """x と y の全部の組み合わせが、ちょうど1回ずつあるか。"""
    unique_x = np.unique(x)
    unique_y = np.unique(y)
    if len(unique_x) * len(unique_y) != len(x):
        return False
    pairs = set(zip(x.tolist(), y.tolist()))
    return len(pairs) == len(x)


def compute_z_grid(x: Any, y: Any, z: Any, interp_method: str = 'linear',
                   resolution: tuple[int, int] | list[int] | None = None) -> dict[str, Any]:
    """{'x_grid', 'y_grid'(ソート済みの1次元), 'z_grid'(shape=(len(y), len(x))、データの無い所は nan), 'is_regular'}。

    resolution=(nx, ny) は補間するときだけ使う(None なら点の数から決める)。interp_method も補間のときだけ。
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


def extract_slice(x_grid: Any, y_grid: Any, z_grid: Any, start: tuple[float, float], end: tuple[float, float],
                  n_points: int = 200) -> dict[str, Any]:
    """格子上の線分に沿った断面を返す({'axis_values', 'axis_kind', 'z_values'})。

    axis_kind はほぼ水平なら 'x'、ほぼ垂直なら 'y'、斜めなら 'distance'(始点からの距離)。格子の外は nan。
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
