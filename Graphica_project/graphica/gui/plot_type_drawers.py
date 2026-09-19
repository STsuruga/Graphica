"""
組み込みの plot_type ごとの描き方。プラグインの register_plot_type と同じく「種類名 → 描画関数」の表で引く。

描画関数は (canvas, ax, ds, x, y, plot_kwargs, axis_index) を受け取り、ds.artist にする artist を返す。
x, y はウォーターフォールのずらし・欠損値の処理・表示用の間引きを済ませた点列。
plot_kwargs(ウォーターフォールの zorder)はグラデーションの線には渡さない。
"""
import logging

import numpy as np
from scipy.stats import gaussian_kde

from graphica.core.dataset import COLOR_BY_COLUMN_PLOT_TYPE

logger = logging.getLogger(__name__)


def _uses_line_gradient(ds):
    return ds.gradient_enabled and ds.gradient_target in ('line', 'both')


def _gradient_line(canvas, ax, ds, x, y):
    return canvas._add_gradient_line(
        ax, x, y, ds.color, ds.gradient_color2, ds.linewidth, ds.alpha, ds.linestyle, label=ds.name)


def _plain_line(ax, ds, x, y, plot_kwargs, **extra):
    (artist,) = ax.plot(x, y, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth,
                        alpha=ds.alpha, label=ds.name, **extra, **plot_kwargs)
    return artist


def _markers(ax, ds, x, y, plot_kwargs, **extra):
    return ax.scatter(x, y, color=ds.color, marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha,
                      **extra, **plot_kwargs)


def draw_line(canvas, ax, ds, x, y, plot_kwargs, axis_index):
    if _uses_line_gradient(ds):
        return _gradient_line(canvas, ax, ds, x, y)
    return _plain_line(ax, ds, x, y, plot_kwargs)


def draw_scatter(canvas, ax, ds, x, y, plot_kwargs, axis_index):
    return _markers(ax, ds, x, y, plot_kwargs, label=ds.name)


def draw_line_and_scatter(canvas, ax, ds, x, y, plot_kwargs, axis_index):
    if _uses_line_gradient(ds):
        # LineCollection はマーカーを描けないので、マーカーは単色で重ねる
        artist = _gradient_line(canvas, ax, ds, x, y)
        _markers(ax, ds, x, y, plot_kwargs)
        return artist
    (artist,) = ax.plot(x, y, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth,
                        marker=ds.marker, markersize=ds.markersize, alpha=ds.alpha, label=ds.name, **plot_kwargs)
    return artist


def draw_area(canvas, ax, ds, x, y, plot_kwargs, axis_index):
    """0 との間を塗り、輪郭が分かるよう上端に線も重ねる。"""
    if not ds.gradient_enabled:
        artist = ax.fill_between(x, y, 0, color=ds.color, alpha=ds.alpha * 0.4, label=ds.name, **plot_kwargs)
        ax.plot(x, y, color=ds.color, linestyle=ds.linestyle, linewidth=ds.linewidth, alpha=ds.alpha, **plot_kwargs)
        return artist
    if ds.gradient_target in ('fill', 'both'):
        artist = canvas._add_gradient_fill(ax, x, y, ds.color, ds.gradient_color2, ds.alpha * 0.4)
    else:
        artist = ax.fill_between(x, y, 0, color=ds.color, alpha=ds.alpha * 0.4, **plot_kwargs)
    if ds.gradient_target in ('line', 'both'):
        _gradient_line(canvas, ax, ds, x, y)
    else:
        _plain_line(ax, ds, x, y, plot_kwargs)
    return artist


def draw_bar(canvas, ax, ds, x, y, plot_kwargs, axis_index):
    return ax.bar(x, y, color=ds.color, alpha=ds.alpha, label=ds.name, **plot_kwargs)


def draw_step(canvas, ax, ds, x, y, plot_kwargs, axis_index):
    # 区間の左端の値を右端まで保つ(サンプリング・イベントデータの慣習)
    return _plain_line(ax, ds, x, y, plot_kwargs, drawstyle='steps-post')


def draw_density_scatter(canvas, ax, ds, x, y, plot_kwargs, axis_index):
    """各点の位置での2次元カーネル密度を色にする。点が少ない・全点が同じ座標だと KDE が失敗するので単色にする。"""
    try:
        if len(x) < 3:
            raise ValueError("点数不足")
        xy = np.vstack([x, y])
        density = gaussian_kde(xy)(xy)
        return ax.scatter(x, y, c=density, cmap=ds.colormap, marker=ds.marker, s=ds.markersize**2,
                          alpha=ds.alpha, label=ds.name, **plot_kwargs)
    except (np.linalg.LinAlgError, ValueError):
        return _markers(ax, ds, x, y, plot_kwargs, label=ds.name)


def draw_color_by_column(canvas, ax, ds, x, y, plot_kwargs, axis_index):
    """
    z_col_name の列の値で点を色分けする。z は visible_df 経由(ds.z_data)で取る
    (df から取ると、行を除外したとたん点と色が1つずつずれる)。
    """
    z_values = ds.z_data
    if z_values is not None and len(z_values) == len(x):
        artist = ax.scatter(x, y, c=z_values, cmap=ds.colormap, vmin=ds.vmin, vmax=ds.vmax,
                            marker=ds.marker, s=ds.markersize**2, alpha=ds.alpha, label=ds.name, **plot_kwargs)
        # カラーバーは1軸に1つ。2Dマップが先に登録していればそちらを優先する
        if axis_index not in canvas._axis_2d_mappables:
            canvas._axis_2d_mappables[axis_index] = artist
        return artist
    if z_values is not None:
        # 欠損値の方針 'drop' で点が減ったときなど。黙って単色になると理由が分からないのでログに残す
        logger.warning(
            "'%s' のZ列の長さ(%d)がプロット点数(%d)と一致しないため、"
            "単色のScatterとして描画します(欠損値の方針'drop'等で"
            "配列が短くなっている可能性があります)。",
            ds.name, len(z_values), len(x),
        )
    return _markers(ax, ds, x, y, plot_kwargs, label=ds.name)


BUILTIN_PLOT_TYPE_DRAWERS = {
    'Line': draw_line,
    'Scatter': draw_scatter,
    'Line+Scatter': draw_line_and_scatter,
    'Area': draw_area,
    'Bar': draw_bar,
    'Step': draw_step,
    'Density Scatter': draw_density_scatter,
    COLOR_BY_COLUMN_PLOT_TYPE: draw_color_by_column,
}
