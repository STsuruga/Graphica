"""1 つの軸のデータの描画: 軸ごとの振り分けと、1D のデータセットを決まった手順で描く。"""
import logging
import numpy as np
import pandas as pd
from graphica.core.analysis import (
    calculate_gaussian_smooth, calculate_lttb_downsample, calculate_median_smooth, calculate_moving_average_smooth)
from graphica.gui.plot_type_drawers import BUILTIN_PLOT_TYPE_DRAWERS
from graphica.gui.rendering.common import (
    DARK_AXES_FACECOLOR, LIGHT_AXES_FACECOLOR, LTTB_DOWNSAMPLE_TARGET_POINTS, LTTB_DOWNSAMPLE_THRESHOLD,
    WATERFALL_ZORDER_BASE, WATERFALL_ZORDER_TOP, _apply_nan_policy, _waterfall_depth_scale, _waterfall_layout)
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Polygon
from scipy.interpolate import CubicSpline

logger = logging.getLogger(__name__)


def draw_data(canvas, ax, axis_index, datasets, full_resolution=False):
    """
    その軸のデータセットを描く。full_resolution=True なら表示用の間引きをしない(エクスポートの「フル解像度」)。

    呼び出し側は非表示のデータセットも含めた全件を渡す。ウォーターフォールの段は非表示のものも数に入れて
    振る(1本隠しても後ろの段が繰り上がらないように)ので、ここで絞る。
    """
    on_this_axis = [ds for ds in datasets if ds.subplot_target == axis_index]
    # 2Dマップは長形式の生の列を持つので、1D の経路(軸の種類の判定・ウォーターフォール・間引きなど)を通さない
    datasets_2d = [ds for ds in on_this_axis if ds.data_kind == '2d_grid' and getattr(ds, 'visible', True)]
    datasets_1d_all = [ds for ds in on_this_axis if ds.data_kind != '2d_grid']
    shown_1d = [ds for ds in datasets_1d_all if getattr(ds, 'visible', True)]
    # 背景として先に描き、1D のデータが上に重なるようにする
    canvas._draw_2d_data(ax, axis_index, datasets_2d, full_resolution=full_resolution)

    # ウォーターフォールの変換は描くたびに登録し直す
    for ds in on_this_axis:
        canvas._waterfall_transforms.pop(ds.dataset_id, None)

    needs_secondary = any(ds.use_secondary_y for ds in shown_1d)
    is_category_x = canvas._record_x_axis_kind(axis_index, shown_1d)

    secondary_ax = None
    if needs_secondary:
        secondary_ax = ax.twinx()
        canvas.all_secondary_axes[axis_index] = secondary_ax

    waterfall = _waterfall_layout(datasets_1d_all)
    for ds in shown_1d:
        target_ax = secondary_ax if ds.use_secondary_y else ax
        if target_ax is None:
            continue
        canvas._draw_1d_dataset(target_ax, axis_index, ds, waterfall, is_category_x, full_resolution)


def record_x_axis_kind(canvas, axis_index, datasets):
    """X 軸が日時か文字列カテゴリかを記録する(目盛りの付け方に使う)。カテゴリなら True を返す。"""
    is_date_x = any(pd.api.types.is_datetime64_any_dtype(ds.df[ds.x_col_name]) for ds in datasets)
    while len(canvas.axis_is_date_x) <= axis_index:
        canvas.axis_is_date_x.append(False)
    canvas.axis_is_date_x[axis_index] = is_date_x

    is_category_x = (not is_date_x) and any(
        not pd.api.types.is_numeric_dtype(ds.df[ds.x_col_name]) for ds in datasets
    )
    while len(canvas.axis_is_category_x) <= axis_index:
        canvas.axis_is_category_x.append(False)
    canvas.axis_is_category_x[axis_index] = is_category_x
    return is_category_x


def draw_1d_dataset(canvas, target_ax, axis_index, ds, waterfall, is_category_x, full_resolution):
    plot_x_data, plot_y_data, plot_kwargs, occlusion_zorder = canvas._waterfall_shifted_points(
        ds, waterfall, is_category_x)

    # カテゴリ軸は下で文字列にするので対象外。
    # 'drop' は配列を短くするため、大量データで間引きと併用するとデータカーソルの行の対応がずれうる(既知の制約)。
    if not is_category_x and ds.nan_policy != 'gap':
        plot_x_data, plot_y_data = _apply_nan_policy(plot_x_data, plot_y_data, ds.nan_policy)

    if is_category_x:
        # matplotlib のカテゴリ軸は全要素が文字列でないと例外になる(数値や NaN が混ざった列)
        plot_x_data = np.array([v if isinstance(v, str) else str(v) for v in plot_x_data])

    plot_x_data, plot_y_data, downsample_indices = canvas._downsample_for_display(
        ds, plot_x_data, plot_y_data, is_category_x, full_resolution)

    # 平滑化は線で結ぶ種別だけ(ほかの種別では平滑化した線がマーカー・棒・塗りを置き換えてしまう)
    is_smoothed_artist = False
    if (ds.smoothing and ds.plot_type in ('Line', 'Line+Scatter')
            and len(plot_x_data) > 1 and not is_category_x):
        is_smoothed_artist = canvas._draw_smoothed(target_ax, ds, plot_x_data, plot_y_data, plot_kwargs)
    else:
        ds.artist = canvas._draw_plot_type(target_ax, axis_index, ds, plot_x_data, plot_y_data, plot_kwargs)

    # 手前のトレースが奥を隠すよう、トレースの下に軸の背景色を敷く。面は自分の塗りと重なるので除く
    if (ds.waterfall_enabled and ds.waterfall_occlusion_enabled
            and ds.plot_type != 'Area' and len(plot_x_data) > 0):
        bg_color = DARK_AXES_FACECOLOR if canvas.dark_mode else LIGHT_AXES_FACECOLOR
        target_ax.fill_between(
            plot_x_data, plot_y_data, waterfall.baseline,
            color=bg_color, alpha=1.0, zorder=occlusion_zorder, linewidth=0,
        )

    # 平滑化した曲線の点は元の行と対応しないので、クリックで選べないようにする。
    # データカーソルモードの一括 set_picker からも外すため、_non_pickable_dataset_ids にも入れる
    if is_smoothed_artist:
        canvas._non_pickable_dataset_ids.add(ds.dataset_id)
    else:
        canvas._non_pickable_dataset_ids.discard(ds.dataset_id)
    if ds.artist is not None and not is_smoothed_artist:
        canvas._enable_element_picking(ds.artist)

    canvas._draw_error_display(target_ax, ds, plot_x_data, plot_y_data, downsample_indices)

    # 曲線フィットの信頼帯・予測帯。帯の列があるときだけ描ける
    if ds.fit_band_display and 'y_lower' in ds.df.columns and 'y_upper' in ds.df.columns:
        band_df = ds.visible_df
        target_ax.fill_between(
            band_df[ds.x_col_name], band_df['y_lower'], band_df['y_upper'],
            color=ds.color, alpha=ds.alpha * 0.15, linewidth=0,
        )

    # 点数が上限を超えると描画で GUI が止まるので描かない。
    # ラベルの値は間引く前の並びなので、点と同じ downsample_indices で揃える
    if ds.show_point_labels and len(ds.visible_df) <= canvas.point_label_max_points:
        canvas._draw_point_labels(
            target_ax, ds, x_data=plot_x_data, y_data=plot_y_data,
            downsample_indices=downsample_indices,
        )


def waterfall_shifted_points(canvas, ds, waterfall, is_category_x):
    """
    描く点列 (x, y, plot_kwargs, 背景を敷く zorder)。ウォーターフォールなら段の分だけずらし、
    逆変換(display_to_data)用に変換を記録する。カテゴリ軸では X はずらせないので Y だけずらす。
    """
    if not ds.waterfall_enabled:
        return ds.x_data, ds.y_data, {}, None
    w_idx = waterfall.index.get(ds.dataset_id, 0)
    depth_scale = _waterfall_depth_scale(
        w_idx, ds.waterfall_depth_shrink_enabled, ds.waterfall_depth_shrink_ratio)
    canvas._waterfall_transforms[ds.dataset_id] = {
        'index': w_idx,
        'offset_x': 0.0 if is_category_x else ds.waterfall_offset_x,
        'offset_y': ds.waterfall_offset_y,
        'depth_scale': depth_scale,
    }
    plot_x_data = ds.x_data if is_category_x else ds.x_data + w_idx * ds.waterfall_offset_x
    plot_y_data = ds.y_data * depth_scale + w_idx * ds.waterfall_offset_y
    # 手前(段が小さい)ほど上に重ねる。段の数によらず枠線・目盛(zorder 2.01〜2.5)より下に収める
    step = (WATERFALL_ZORDER_TOP - WATERFALL_ZORDER_BASE) / (waterfall.count + 1)
    zorder = WATERFALL_ZORDER_BASE + (waterfall.count - w_idx) * step
    return plot_x_data, plot_y_data, {'zorder': zorder}, zorder - step / 2


def downsample_for_display(canvas, ds, plot_x_data, plot_y_data, is_category_x, full_resolution):
    """
    点が多い 'Line' だけ LTTB で間引く(散布図などは点の疎密自体が情報)。X が昇順でないと
    LTTB が形を変えてしまうので、そのときは間引かない。戻り値の3つ目は間引きに使った添字(無ければ None)。
    """
    if not (ds.plot_type == 'Line' and not full_resolution and not is_category_x
            and len(plot_x_data) > LTTB_DOWNSAMPLE_THRESHOLD
            and np.all(np.diff(plot_x_data) >= 0)):
        return plot_x_data, plot_y_data, None
    indices = calculate_lttb_downsample(plot_x_data, plot_y_data, LTTB_DOWNSAMPLE_TARGET_POINTS)
    if len(indices) >= len(plot_x_data):
        return plot_x_data, plot_y_data, None
    # データカーソルが、間引いた後の添字を visible_df の行に戻すのに使う
    canvas.downsample_index_map[ds.dataset_id] = indices
    return plot_x_data[indices], plot_y_data[indices], indices


def draw_smoothed(canvas, target_ax, ds, plot_x_data, plot_y_data, plot_kwargs):
    """平滑化した曲線を描く。平滑化できなければ元の点のまま線で結び、False を返す。"""
    sort_indices = np.argsort(plot_x_data)
    x_sorted = plot_x_data[sort_indices]
    y_sorted = plot_y_data[sort_indices]
    use_line_gradient = ds.gradient_enabled and ds.gradient_target in ('line', 'both')
    smoothing_method = getattr(ds, 'smoothing_method', 'cubic_spline')
    try:
        # cubic_spline は200点に補間して滑らかにする。ほかはノイズを減らすのが目的なので点数はそのまま
        if smoothing_method == 'moving_average':
            x_smooth, y_smooth = calculate_moving_average_smooth(x_sorted, y_sorted)
        elif smoothing_method == 'median':
            x_smooth, y_smooth = calculate_median_smooth(x_sorted, y_sorted)
        elif smoothing_method == 'gaussian':
            x_smooth, y_smooth = calculate_gaussian_smooth(x_sorted, y_sorted)
        else:
            f = CubicSpline(x_sorted, y_sorted)
            x_smooth = np.linspace(x_sorted.min(), x_sorted.max(), 200)
            y_smooth = f(x_smooth)
        if use_line_gradient:
            ds.artist = canvas._add_gradient_line(
                target_ax, x_smooth, y_smooth, ds.color, ds.gradient_color2,
                ds.linewidth, ds.alpha, ds.linestyle, label=ds.name
            )
        else:
            (artist_line,) = target_ax.plot(x_smooth, y_smooth, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
            ds.artist = artist_line
        if ds.plot_type == 'Line+Scatter':
            target_ax.scatter(plot_x_data, plot_y_data, color=ds.color, marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha, **plot_kwargs)
        return True
    except ValueError:
        if use_line_gradient:
            ds.artist = canvas._add_gradient_line(
                target_ax, plot_x_data, plot_y_data, ds.color, ds.gradient_color2,
                ds.linewidth, ds.alpha, ds.linestyle, label=ds.name
            )
        else:
            (artist,) = target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
            ds.artist = artist
        return False


def draw_plot_type(canvas, target_ax, axis_index, ds, plot_x_data, plot_y_data, plot_kwargs):
    """
    plot_type の描画関数で描き、ds.artist にするものを返す。組み込みに無ければプラグインの種類を探し、
    それも無ければ線で描く。プラグインの描画にはウォーターフォールの zorder などは渡らない(既知の制限)。
    """
    drawer = BUILTIN_PLOT_TYPE_DRAWERS.get(ds.plot_type)
    if drawer is not None:
        return drawer(canvas, target_ax, ds, plot_x_data, plot_y_data, plot_kwargs, axis_index)

    from graphica.core.plugin_api import get_plugin_api
    api = get_plugin_api()
    plugin_plot_type = api.get_plot_type(ds.plot_type) if api is not None else None
    if plugin_plot_type is None:
        logger.warning("未知のplot_type '%s' です。Lineとして描画します。", ds.plot_type)
        (artist,) = target_ax.plot(plot_x_data, plot_y_data, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, label=ds.name, **plot_kwargs)
        return artist
    try:
        artist = plugin_plot_type.drawer(ds, target_ax, plot_x_data, plot_y_data)
    except Exception as e:
        logger.warning(
            "[plugin:%s] plot_type '%s' の描画に失敗しました: %s",
            plugin_plot_type.plugin_name, ds.plot_type, e,
        )
        return ds.artist
    return artist if artist is not None else ds.artist


def draw_error_display(canvas, target_ax, ds, plot_x_data, plot_y_data, downsample_indices):
    """誤差棒と誤差の帯を、描いた点(ずらし・間引きの後)の位置に重ねる。帯は Y の誤差だけ。"""
    if not (ds.x_err_col_name or ds.y_err_col_name):
        return
    # 誤差列は間引く前の長さなので、点と同じ添字で揃える(揃えないと長さ違いで例外)
    x_err = ds.x_err_data
    y_err_full = ds.y_err_data
    if downsample_indices is not None:
        if x_err is not None:
            x_err = x_err[downsample_indices]
        if y_err_full is not None:
            y_err_full = y_err_full[downsample_indices]

    if ds.error_display in ('bar', 'both'):
        target_ax.errorbar(
            plot_x_data, plot_y_data,
            xerr=x_err, yerr=y_err_full,
            fmt='none', ecolor=ds.color, elinewidth=ds.linewidth, alpha=ds.alpha, capsize=3
        )
    if ds.error_display in ('band', 'both') and y_err_full is not None:
        y_arr = np.asarray(plot_y_data)
        y_err = np.asarray(y_err_full)
        target_ax.fill_between(
            plot_x_data, y_arr - y_err, y_arr + y_err,
            color=ds.color, alpha=ds.alpha * 0.25, linewidth=0,
        )


def draw_point_labels(canvas, ax, ds, x_data=None, y_data=None, downsample_indices=None):
    """
    各点の脇に Y 値(point_label_col_name があればその列の値)を書く。
    x_data/y_data を渡せばその位置に書く(ウォーターフォールでずらした位置)。
    downsample_indices は点の間引きに使った添字で、ラベルの値も同じく間引く
    (揃えないと zip が短い方で切れ、点と無関係な行のラベルが付く)。
    """
    if x_data is None:
        x_data = ds.x_data
    if y_data is None:
        y_data = ds.y_data

    if ds.point_label_col_name and ds.point_label_col_name in ds.df.columns:
        # 点と同じ行になるよう visible_df から取る
        label_values = ds.visible_df[ds.point_label_col_name].values
    else:
        label_values = ds.y_data
    if downsample_indices is not None:
        label_values = label_values[downsample_indices]

    for x, y, label_value in zip(x_data, y_data, label_values):
        if pd.isna(x) or pd.isna(y):
            continue
        if isinstance(label_value, (int, float, np.floating, np.integer)) and not isinstance(label_value, bool):
            text = f"{label_value:.4g}" if not pd.isna(label_value) else ""
        else:
            text = "" if pd.isna(label_value) else str(label_value)
        if not text:
            continue
        ax.annotate(
            text, (x, y), textcoords="offset points", xytext=(5, 5),
            fontsize=8, color=ds.color, alpha=ds.alpha,
            # Text の既定は clip_on=False で、範囲外の点のラベルだけが枠の外に残り SVG/PDF に出てしまう
            clip_on=True,
        )


def enable_element_picking(canvas, artist):
    """クリックで選べるようにする。棒グラフは Rectangle の集まりなので、1本ずつ設定する。"""
    try:
        if hasattr(artist, 'patches'):  # BarContainer
            for patch in artist.patches:
                patch.set_picker(5)
        else:
            artist.set_picker(5)
    except AttributeError:
        pass


def add_gradient_line(canvas, ax, x, y, color1, color2, linewidth, alpha, linestyle, label=None):
    """
    線を区間に分けて、始点の色から終点の色へ変わる LineCollection として描く。
    add_collection は軸の表示範囲を広げないことがあるので、データ範囲を明示的に足しておく。
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if len(x) < 2:
        # 区間が作れないので普通の線にする
        (line,) = ax.plot(x, y, color=color1, linestyle=linestyle, linewidth=linewidth, alpha=alpha, label=label)
        return line

    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    cmap = LinearSegmentedColormap.from_list('graphica_line_gradient', [color1, color2])
    lc = LineCollection(
        segments, cmap=cmap, norm=Normalize(0, 1),
        linewidths=linewidth, linestyles=linestyle, alpha=alpha, label=label,
        zorder=2,
    )
    # 区間ごとに始点からの位置(0〜1)を割り当てる
    lc.set_array(np.linspace(0, 1, len(segments)))
    ax.add_collection(lc)
    ax.update_datalim(np.column_stack([x, y]))
    return lc


def add_gradient_fill(canvas, ax, x, y, color1, color2, alpha, baseline=0.0):
    """fill_between と同じ形の多角形で、imshow のグラデーション画像を切り抜いて塗る。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # origin='lower' で先頭行が下端になるので、上端が color1 になるよう色を逆に並べる
    gradient = np.linspace(0, 1, 256).reshape(-1, 1)
    cmap = LinearSegmentedColormap.from_list('graphica_fill_gradient', [color2, color1])

    x_min, x_max = float(np.nanmin(x)), float(np.nanmax(x))
    y_min = float(min(np.nanmin(y), baseline))
    y_max = float(max(np.nanmax(y), baseline))
    # 全点が同じ座標だと extent が潰れるので幅を持たせる
    if x_min == x_max:
        x_min, x_max = x_min - 0.5, x_max + 0.5
    if y_min == y_max:
        y_min, y_max = y_min - 0.5, y_max + 0.5

    im = ax.imshow(
        gradient, cmap=cmap, aspect='auto', origin='lower',
        extent=(x_min, x_max, y_min, y_max), alpha=alpha, zorder=1,
    )

    verts = list(zip(x, y)) + [(x[-1], baseline), (x[0], baseline)]
    clip_poly = Polygon(verts, closed=True, transform=ax.transData)
    im.set_clip_path(clip_poly)

    # imshow は軸の範囲を広げないので、明示的に足す
    ax.update_datalim(np.array([[x_min, y_min], [x_max, y_max]]))
    return im
