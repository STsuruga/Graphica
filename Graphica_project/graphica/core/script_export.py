"""プロジェクトを matplotlib だけで動くスクリプトにする。GUI には依存しない。

再現するのはデータ、組み込みの種類、2D マップ、色・線・マーカー、タイトル・軸ラベル・範囲・対数軸・凡例・グリッド・
第2Y軸まで。グラデーション・ウォーターフォール・誤差・注釈などは対象外(生成したスクリプトの先頭にも書く)。
プラグインの種類はスクリプトに持ち出せないので Line で代わりに出す。
"""

from graphica.core.axis_settings import axis_setting
from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from graphica.core.dataset import Dataset
    from graphica.models.project import ProjectModel


def _to_native(value: Any) -> Any:
    """numpy 2 では np.float64 の repr が "np.float64(1.5)" になるので、Python の型にしてから repr する。"""
    if hasattr(value, 'item'):
        try:
            return value.item()
        except (ValueError, TypeError):
            return value
    return value


def _format_array_literal(values: Any) -> str:
    """数値のリストのリテラル。NaN は repr すると未定義の nan になるので float('nan') と書く。"""
    parts = []
    for v in values:
        v = _to_native(v)
        if isinstance(v, float) and v != v:  # NaN
            parts.append("float('nan')")
        else:
            parts.append(repr(v))
    return "[" + ", ".join(parts) + "]"


# 組み込みの種類(これ以外はプラグインのもの)
_BUILTIN_PLOT_TYPES = ('Line', 'Scatter', 'Line+Scatter', 'Area', 'Bar', 'Step',
                       COLOR_BY_COLUMN_PLOT_TYPE)


def _emit_dataset_plot_call(lines: list[str], ax_var: str, ds: "Dataset", mappable_var: str | None = None) -> bool:
    """1次元の系列を描く呼び出しを書く。カラーバー用の mappable を mappable_var に入れたら True。"""
    kwargs = f"color={ds.color!r}, alpha={ds.alpha!r}, label={ds.name!r}"
    plot_type = ds.plot_type if ds.plot_type in _BUILTIN_PLOT_TYPES else None

    if plot_type is None:
        lines.append(
            f"# plot_type {ds.plot_type!r} はプラグイン依存のため、Lineとして代替出力しています"
        )
        plot_type = 'Line'

    if plot_type == COLOR_BY_COLUMN_PLOT_TYPE:
        # scipy を使わない matplotlib だけの呼び出しなので、そのまま再現できる(Density Scatter は Line で代わりに出す)
        z_values = ds.z_data
        if z_values is None or len(z_values) != len(ds.x_data):
            lines.append(
                "# Z列が未設定/長さ不一致のため、単色のScatterとして出力しています"
            )
            lines.append(
                f"{ax_var}.scatter(x, y, marker={ds.marker!r}, s={ds.markersize!r} ** 2, {kwargs})"
            )
            return False
        assign = f"{mappable_var} = " if mappable_var else ""
        lines.append(
            f"{assign}{ax_var}.scatter(x, y, c=z, cmap={ds.colormap!r}, "
            f"vmin={_to_native(ds.vmin)!r}, vmax={_to_native(ds.vmax)!r}, "
            f"marker={ds.marker!r}, s={ds.markersize!r} ** 2, "
            f"alpha={ds.alpha!r}, label={ds.name!r})"
        )
        return bool(mappable_var)

    if plot_type == 'Line':
        lines.append(f"{ax_var}.plot(x, y, linestyle={ds.linestyle!r}, linewidth={ds.linewidth!r}, {kwargs})")
    elif plot_type == 'Scatter':
        lines.append(f"{ax_var}.scatter(x, y, marker={ds.marker!r}, s={ds.markersize!r} ** 2, {kwargs})")
    elif plot_type == 'Line+Scatter':
        lines.append(
            f"{ax_var}.plot(x, y, linestyle={ds.linestyle!r}, linewidth={ds.linewidth!r}, "
            f"marker={ds.marker!r}, markersize={ds.markersize!r}, {kwargs})"
        )
    elif plot_type == 'Area':
        lines.append(f"{ax_var}.fill_between(x, y, 0, color={ds.color!r}, alpha={ds.alpha!r} * 0.4, label={ds.name!r})")
        lines.append(f"{ax_var}.plot(x, y, linestyle={ds.linestyle!r}, linewidth={ds.linewidth!r}, color={ds.color!r}, alpha={ds.alpha!r})")
    elif plot_type == 'Bar':
        lines.append(f"{ax_var}.bar(x, y, {kwargs})")
    elif plot_type == 'Step':
        lines.append(f"{ax_var}.plot(x, y, drawstyle='steps-post', linestyle={ds.linestyle!r}, linewidth={ds.linewidth!r}, {kwargs})")
    return False


_VALID_MAP_DISPLAY_MODES = ('heatmap', 'contour', 'contour_filled', 'heatmap_contour')


def _emit_2d_dataset_plot_call(lines: list[str], ax_var: str, mesh_var: str, ds: "Dataset") -> bool:
    """2D マップを pcolormesh / contour / contourf で書く。Dataset.z_grid の格子をそのまま埋め込む。

    カラーバーの対象(塗りのあるモード)を mesh_var に作れたら True。線だけの contour や格子が作れないときは False。
    """
    grid = ds.z_grid
    if grid is None:
        lines.append(
            f"# {ds.name!r} は2Dグリッドデータですが、有効なグリッドを構築できなかったため出力をスキップしています"
        )
        return False
    x_grid, y_grid, z_grid = grid['x_grid'], grid['y_grid'], grid['z_grid']
    lines.append(f"x = np.array({_format_array_literal(list(x_grid))})")
    lines.append(f"y = np.array({_format_array_literal(list(y_grid))})")
    z_rows = ", ".join(_format_array_literal(list(row)) for row in z_grid)
    lines.append(f"z = np.array([{z_rows}])")

    mode = ds.map_display_mode if ds.map_display_mode in _VALID_MAP_DISPLAY_MODES else 'heatmap'
    vmin_kw = f", vmin={_to_native(ds.vmin)!r}" if ds.vmin is not None else ""
    vmax_kw = f", vmax={_to_native(ds.vmax)!r}" if ds.vmax is not None else ""
    has_mappable = False

    if mode in ('heatmap', 'heatmap_contour'):
        lines.append(
            f"{mesh_var} = {ax_var}.pcolormesh(x, y, z, cmap={ds.colormap!r}, "
            f"alpha={ds.alpha!r}, shading='auto'{vmin_kw}{vmax_kw})"
        )
        has_mappable = True
    elif mode == 'contour_filled':
        lines.append(
            f"{mesh_var} = {ax_var}.contourf(x, y, z, levels={ds.contour_levels!r}, "
            f"cmap={ds.colormap!r}, alpha={ds.alpha!r}{vmin_kw}{vmax_kw})"
        )
        has_mappable = True
    if mode in ('contour', 'heatmap_contour'):
        lines.append(
            f"{ax_var}.contour(x, y, z, levels={ds.contour_levels!r}, colors={ds.color!r}, "
            f"alpha={ds.alpha!r}, linewidths={ds.linewidth!r})"
        )
    return has_mappable


def _emit_appearance_calls(lines: list[str], ax_var: str, settings: dict[str, Any], mesh_var: str | None = None) -> None:
    if axis_setting(settings, 'title'):
        lines.append(f"{ax_var}.set_title({settings['title']!r})")
    if axis_setting(settings, 'x_label') and axis_setting(settings, 'x_label_visible'):
        lines.append(f"{ax_var}.set_xlabel({settings['x_label']!r})")
    if axis_setting(settings, 'y_label') and axis_setting(settings, 'y_label_visible'):
        lines.append(f"{ax_var}.set_ylabel({settings['y_label']!r})")
    if axis_setting(settings, 'x_log'):
        lines.append(f"{ax_var}.set_xscale('log')")
    if axis_setting(settings, 'y_log'):
        lines.append(f"{ax_var}.set_yscale('log')")
    if not axis_setting(settings, 'x_autoscale'):
        lines.append(f"{ax_var}.set_xlim({axis_setting(settings, 'x_min')!r}, {axis_setting(settings, 'x_max')!r})")
    if not axis_setting(settings, 'y_autoscale'):
        lines.append(f"{ax_var}.set_ylim({axis_setting(settings, 'y_min')!r}, {axis_setting(settings, 'y_max')!r})")
    if axis_setting(settings, 'grid_visible'):
        lines.append(f"{ax_var}.grid(True)")
    if axis_setting(settings, 'legend_visible'):
        lines.append(f"{ax_var}.legend()")

    if mesh_var is not None and axis_setting(settings, 'colorbar_enabled'):
        position = axis_setting(settings, 'colorbar_position')
        if position not in ('right', 'left', 'top', 'bottom'):
            position = 'right'
        fraction = axis_setting(settings, 'colorbar_width_fraction')
        lines.append(
            f"cbar = fig.colorbar({mesh_var}, ax={ax_var}, location={position!r}, "
            f"fraction={fraction!r}, pad=0.04)"
        )
        if axis_setting(settings, 'colorbar_label'):
            lines.append(f"cbar.set_label({settings['colorbar_label']!r})")


def generate_python_script(project: "ProjectModel") -> str:
    """スクリプトのソースを返す。データは np.array としてスクリプトに埋め込む(1ファイルで再現できるが、点が多いと大きくなる)。"""
    lines = [
        '"""',
        'Graphicaから書き出されたスタンドアロンのPythonスクリプト(項目C-1103)。',
        'matplotlib/numpyのみで実行できます(Graphica本体は不要です)。',
        '',
        '★ 既知の制限: グラデーション・ウォーターフォール・エラーバー・注釈・',
        'パネルラベル・第2X軸の単位変換・グリッド線の詳細設定・日付軸/カテゴリ軸の',
        '専用フォーマット・プラグイン提供の描画方式は再現されません',
        '(未対応のplot_typeはLineとして代替出力されます)。',
        '"""',
        'import numpy as np',
        'import matplotlib.pyplot as plt',
        '',
    ]

    all_plot_settings = project.all_plot_settings or [{}]
    layout_mode = getattr(project, 'layout_mode', 'grid')

    if layout_mode == 'free':
        subplot_count = len(all_plot_settings)
        lines.append('fig = plt.figure(figsize=(10, 8))')
        lines.append('axes = []')
        for settings in all_plot_settings:
            rect = axis_setting(settings, 'free_rect') or (0.1, 0.1, 0.8, 0.8)
            lines.append(f'axes.append(fig.add_axes({tuple(rect)!r}))')
    else:
        rows = getattr(project, 'layout_rows', 1) or 1
        cols = getattr(project, 'layout_cols', 1) or 1
        subplot_count = rows * cols
        lines.append(f'fig, axes_grid = plt.subplots({rows}, {cols}, figsize=({6 * cols}, {4 * rows}))')
        lines.append('axes = list(np.atleast_1d(axes_grid).flatten())')
    lines.append('')

    visible_datasets = [ds for ds in project.datasets if getattr(ds, 'visible', True)]
    secondary_axis_indices = sorted({
        ds.subplot_target for ds in visible_datasets
        if ds.use_secondary_y and ds.subplot_target < subplot_count
    })
    for idx in secondary_axis_indices:
        lines.append(f'ax{idx}_secondary = axes[{idx}].twinx()')
    if secondary_axis_indices:
        lines.append('')

    mesh_var_by_axis: dict[int, str | None] = {}
    # 1つの軸にカラーバーは1つなので、2D マップがある軸では2D マップを優先する(画面と同じ)。
    # 系列の順に書くので、先にこの集合を作らないと順序次第で画面と食い違う
    axes_with_2d = {
        d.subplot_target for d in visible_datasets if d.data_kind == '2d_grid'
    }
    for ds in visible_datasets:
        if ds.subplot_target >= subplot_count:
            continue
        ax_var = (
            f'ax{ds.subplot_target}_secondary'
            if (ds.use_secondary_y and ds.subplot_target in secondary_axis_indices)
            else f'axes[{ds.subplot_target}]'
        )
        lines.append(f'# --- {ds.name} ---')
        if ds.data_kind == '2d_grid':
            mesh_var = f'mesh{ds.subplot_target}'
            if _emit_2d_dataset_plot_call(lines, ax_var, mesh_var, ds):
                mesh_var_by_axis[ds.subplot_target] = mesh_var
        else:
            lines.append(f'x = np.array({_format_array_literal(list(ds.x_data))})')
            lines.append(f'y = np.array({_format_array_literal(list(ds.y_data))})')
            # visible_df 経由なので、マスクした行があっても点と色がずれない
            if ds.plot_type == COLOR_BY_COLUMN_PLOT_TYPE:
                z_values = ds.z_data
                if z_values is not None and len(z_values) == len(ds.x_data):
                    lines.append(f'z = np.array({_format_array_literal(list(z_values))})')
            # 2D マップがある軸ではカラーバーを譲る(mesh{N} を上書きしないよう変数名も分ける)
            wants_colorbar = ds.subplot_target not in axes_with_2d
            scatter_mesh_var = f'scatter_mesh{ds.subplot_target}' if wants_colorbar else None
            if _emit_dataset_plot_call(lines, ax_var, ds, mappable_var=scatter_mesh_var):
                mesh_var_by_axis[ds.subplot_target] = scatter_mesh_var
        lines.append('')

    for i, settings in enumerate(all_plot_settings[:subplot_count]):
        _emit_appearance_calls(lines, f'axes[{i}]', settings, mesh_var_by_axis.get(i))
    lines.append('')

    lines.append('plt.tight_layout()')
    lines.append('plt.show()')
    lines.append('')

    return '\n'.join(lines)
