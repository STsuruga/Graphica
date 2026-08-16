# core/script_export.py
"""
プロジェクトを、matplotlib単体で完結するスタンドアロンのPythonスクリプトとして
書き出すためのコード生成ロジック(項目C-1103)。gui/canvas.pyのGUI依存コードは
一切importせず、project.datasets/project.all_plot_settingsだけを読んで文字列と
してソースコードを組み立てる純粋関数群(GUIから独立してテストできるようにする、
将来のC-1105バッチ/CLIモードとも設計を共有できるようにするための意図的な分離)。

★ スコープ(意図的な簡略化、既知の制限として生成スクリプトの先頭コメントにも
明記する): データ・基本的なプロット種別(Line/Scatter/Line+Scatter/Area/Bar)・
2Dグリッドデータ(ヒートマップ、項目C-508、pcolormesh+カラーバー)・
色/線種/線幅/マーカー/透明度・タイトル/軸ラベル/軸範囲/対数軸/凡例表示/
グリッド表示/第2Y軸(twinx)の主要な見た目は再現するが、グラデーション・
ウォーターフォール・エラーバー・注釈・パネルラベル・第2X軸の単位変換・
グリッド線の詳細カスタマイズ・フォント/配色トークン・日付軸/カテゴリ軸の
専用フォーマットは対象外。プラグイン提供のplot_type(register_plot_type)は
スクリプト側にプラグインを持ち出せないため、コメント付きでLineとして代替出力する。
"""


def _to_native(value):
    """
    numpyのスカラ型(np.float64等)をPythonの素の型に変換する。
    numpy>=2.0ではnp.float64のrepr()が"np.float64(1.5)"のようになり、
    生成スクリプトの可読性を損なう(構文としては動くが冗長)ため、
    .item()で素のPython型に落としてからrepr()する。
    """
    if hasattr(value, 'item'):
        try:
            return value.item()
        except (ValueError, TypeError):
            return value
    return value


def _format_array_literal(values):
    """
    数値配列を、Pythonソース上のリストリテラル文字列として整形する。
    NaNはrepr()すると"nan"という未定義の識別子になってしまう(構文エラーに
    なる)ため、float('nan')という有効なPython式に明示的に変換する。
    """
    parts = []
    for v in values:
        v = _to_native(v)
        if isinstance(v, float) and v != v:  # NaNの判定(NaNは自分自身と等しくない)
            parts.append("float('nan')")
        else:
            parts.append(repr(v))
    return "[" + ", ".join(parts) + "]"


# plot_type(core/dataset.py の Dataset.plot_type)のうち、プラグインを介さず
# 組み込みでサポートしている値の一覧(未知の値=プラグイン提供として扱う)。
_BUILTIN_PLOT_TYPES = ('Line', 'Scatter', 'Line+Scatter', 'Area', 'Bar')


def _emit_dataset_plot_call(lines, ax_var, ds):
    kwargs = f"color={ds.color!r}, alpha={ds.alpha!r}, label={ds.name!r}"
    plot_type = ds.plot_type if ds.plot_type in _BUILTIN_PLOT_TYPES else None

    if plot_type is None:
        lines.append(
            f"# plot_type {ds.plot_type!r} はプラグイン依存のため、Lineとして代替出力しています"
        )
        plot_type = 'Line'

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


_VALID_MAP_DISPLAY_MODES = ('heatmap', 'contour', 'contour_filled', 'heatmap_contour')


def _emit_2d_dataset_plot_call(lines, ax_var, mesh_var, ds):
    """
    2Dグリッドデータセット(項目C-508、data_kind='2d_grid')をpcolormesh/contour/
    contourfとして出力する。_emit_dataset_plot_call()(plot_type分岐)とは
    独立した経路(gui/canvas.pyの_draw_data()がdata_kindで2D/1Dを振り分ける
    のと同じ設計)。Dataset.z_grid(core/dataset.py、規則格子/散在データの補間
    どちらも同じ形の辞書を返す)が既に計算済みのグリッドをそのまま埋め込む。

    ds.map_display_mode(項目C-509)で描画方式を切り替える。gui/canvas.pyの
    _draw_2d_data()と同じく、塗りを伴うモード(heatmap/contour_filled/
    heatmap_contour)の場合のみカラーバー用のmesh_var(呼び出し側が
    fig.colorbar()の対象として使う)を組み立てる。

    Returns:
        bool: カラーバーの対象になるmappable(pcolormesh/contourfの戻り値)を
        出力できたか。線のみのcontourモード、または有効なグリッドが
        構築できなかった場合はFalseを返す(呼び出し側はカラーバー出力を
        スキップする)。
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


def _emit_appearance_calls(lines, ax_var, settings, mesh_var=None):
    if settings.get('title'):
        lines.append(f"{ax_var}.set_title({settings['title']!r})")
    if settings.get('x_label'):
        lines.append(f"{ax_var}.set_xlabel({settings['x_label']!r})")
    if settings.get('y_label'):
        lines.append(f"{ax_var}.set_ylabel({settings['y_label']!r})")
    if settings.get('x_log'):
        lines.append(f"{ax_var}.set_xscale('log')")
    if settings.get('y_log'):
        lines.append(f"{ax_var}.set_yscale('log')")
    if not settings.get('x_autoscale', True):
        lines.append(f"{ax_var}.set_xlim({settings.get('x_min', 0)!r}, {settings.get('x_max', 1)!r})")
    if not settings.get('y_autoscale', True):
        lines.append(f"{ax_var}.set_ylim({settings.get('y_min', 0)!r}, {settings.get('y_max', 1)!r})")
    if settings.get('grid_visible'):
        lines.append(f"{ax_var}.grid(True)")
    if settings.get('legend_visible', True):
        lines.append(f"{ax_var}.legend()")

    # カラーバー(項目C-501): このサブプロットに2Dマップ(項目C-508)が
    # 描画されていた場合のみ(mesh_varは呼び出し側がgenerate_python_script内で
    # _emit_2d_dataset_plot_call()が成功した軸だけに渡す)。
    if mesh_var is not None and settings.get('colorbar_enabled', True):
        position = settings.get('colorbar_position', 'right')
        if position not in ('right', 'left', 'top', 'bottom'):
            position = 'right'
        fraction = settings.get('colorbar_width_fraction', 0.05)
        lines.append(
            f"cbar = fig.colorbar({mesh_var}, ax={ax_var}, location={position!r}, "
            f"fraction={fraction!r}, pad=0.04)"
        )
        if settings.get('colorbar_label'):
            lines.append(f"cbar.set_label({settings['colorbar_label']!r})")


def generate_python_script(project) -> str:
    """
    project(models/project.py の ProjectModel)から、matplotlib単体で実行できる
    スタンドアロンのPythonスクリプトのソースコードを文字列として組み立てる
    (項目C-1103)。データは外部ファイルを参照せず、np.array([...])としてスクリプト
    内に直接埋め込む(単一ファイルでの再現性を優先する意図的な設計、大量点数の
    データセットではファイルサイズが大きくなる既知のトレードオフ)。
    """
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
            rect = settings.get('free_rect') or (0.1, 0.1, 0.8, 0.8)
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

    mesh_var_by_axis = {}
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
            _emit_dataset_plot_call(lines, ax_var, ds)
        lines.append('')

    for i, settings in enumerate(all_plot_settings[:subplot_count]):
        _emit_appearance_calls(lines, f'axes[{i}]', settings, mesh_var_by_axis.get(i))
    lines.append('')

    lines.append('plt.tight_layout()')
    lines.append('plt.show()')
    lines.append('')

    return '\n'.join(lines)
