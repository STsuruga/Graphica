"""2D マップ(ヒートマップ・等高線)の描画。"""
import logging
import numpy as np
from graphica.gui.rendering.common import GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS

logger = logging.getLogger(__name__)


def draw_2d_data(canvas, ax, axis_index, datasets_2d, full_resolution=False):
    """
    2Dマップを描く。規則格子でも補間した格子でも同じ形の z_grid なので、等間隔を前提にする imshow ではなく
    pcolormesh を使う。map_display_mode: 'heatmap' / 'contour'(線だけ、色と太さはデータセットの線) /
    'contour_filled' / 'heatmap_contour'。カラーバーの対象は塗りのある方式だけ(線だけの等高線には付けない慣習)。
    """
    canvas._axis_2d_mappables.pop(axis_index, None)
    for ds in datasets_2d:
        grid = ds.z_grid
        if grid is None:
            continue
        x_grid, y_grid, z_grid = grid['x_grid'], grid['y_grid'], grid['z_grid']

        if not full_resolution and len(x_grid) > GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS:
            step = int(np.ceil(len(x_grid) / GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS))
            x_grid = x_grid[::step]
            z_grid = z_grid[:, ::step]
        if not full_resolution and len(y_grid) > GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS:
            step = int(np.ceil(len(y_grid) / GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS))
            y_grid = y_grid[::step]
            z_grid = z_grid[::step, :]

        vmin = ds.vmin if ds.vmin is not None else (
            float(np.nanmin(z_grid)) if np.any(~np.isnan(z_grid)) else None
        )
        vmax = ds.vmax if ds.vmax is not None else (
            float(np.nanmax(z_grid)) if np.any(~np.isnan(z_grid)) else None
        )

        mode = ds.map_display_mode if ds.map_display_mode in canvas._VALID_MAP_DISPLAY_MODES else 'heatmap'

        try:
            mappable = None
            contour_set = None
            # label は付けない。QuadMesh/ContourSet は凡例に載らず、凡例を作るたびに警告が出る
            if mode in ('heatmap', 'heatmap_contour'):
                mappable = ax.pcolormesh(
                    x_grid, y_grid, z_grid, cmap=ds.colormap, vmin=vmin, vmax=vmax,
                    shading='auto', alpha=ds.alpha,
                )
            elif mode == 'contour_filled':
                mappable = ax.contourf(
                    x_grid, y_grid, z_grid, levels=ds.contour_levels, cmap=ds.colormap,
                    vmin=vmin, vmax=vmax, alpha=ds.alpha,
                )
            if mode in ('contour', 'heatmap_contour'):
                contour_set = ax.contour(
                    x_grid, y_grid, z_grid, levels=ds.contour_levels, colors=ds.color,
                    alpha=ds.alpha, linewidths=ds.linewidth,
                )
        except ValueError as e:
            # 知らないカラーマップ名など。このデータセットだけ飛ばす
            logger.warning("2Dマップの描画に失敗しました(%s): %s", ds.name, e)
            continue

        ds.artist = mappable if mappable is not None else contour_set
        if mappable is not None:
            canvas._axis_2d_mappables[axis_index] = mappable
