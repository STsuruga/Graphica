"""マウスのモードが共通に使う、マウス位置の扱い。"""


def legend_at(canvas, event):
    """event の位置にある凡例(どのサブプロットの、主・第2のどちらの軸のものでも)。無ければ None。

    凡例はモードが無くてもドラッグで動かせるので、凡例の上で押した操作はモードの側で使わない。
    """
    if event.x is None or event.y is None:
        return None
    secondary_axes = getattr(canvas, 'all_secondary_axes', [])
    for ax in list(getattr(canvas, 'all_axes', [])) + [ax for ax in secondary_axes if ax is not None]:
        legend = ax.get_legend()
        if legend is not None and legend.get_visible() and legend.contains(event)[0]:
            return legend
    return None


def clamped_data_point(ax, event):
    """event の位置を ax の枠の中に寄せて、ax のデータ座標で返す。位置が無ければ None。

    ドラッグを軸の外で離したり、外へはみ出して動かしたりしたときも、縁で止めた位置として扱う。
    """
    # 中ならイベントの値をそのまま使う(ピクセルから計算し直すと誤差が出て、クリックがドラッグに見える)
    if event.inaxes is ax and event.xdata is not None and event.ydata is not None:
        return float(event.xdata), float(event.ydata)
    if event.x is None or event.y is None:
        return None
    box = ax.bbox
    x = min(max(event.x, box.x0), box.x1)
    y = min(max(event.y, box.y0), box.y1)
    data_x, data_y = ax.transData.inverted().transform((x, y))
    # 縁で止めた向きは表示範囲の端の値そのものにする(ピクセルから戻すと誤差で端の点が漏れる)。枠の始め側が範囲の始め側
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    if event.x <= box.x0:
        data_x = xlim[0]
    elif event.x >= box.x1:
        data_x = xlim[1]
    if event.y <= box.y0:
        data_y = ylim[0]
    elif event.y >= box.y1:
        data_y = ylim[1]
    return float(data_x), float(data_y)
