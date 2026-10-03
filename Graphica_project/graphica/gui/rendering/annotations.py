"""注釈(文字・矢印・統計ラベル・範囲の強調・拡大図)とパネルラベルの描画。作り直しを省く鍵もここで作る。"""
import json
import logging
import numpy as np
from graphica.core.analysis import calculate_lttb_downsample
from graphica.core.axis_settings import axis_setting
from graphica.gui.mathtext_preview import JP_CAPABLE_FONT_FAMILIES, families_for_text
from graphica.gui.rendering.common import (
    DARK_TEXT_COLOR, LIGHT_TEXT_COLOR, LTTB_DOWNSAMPLE_TARGET_POINTS, LTTB_DOWNSAMPLE_THRESHOLD,
    REGION_HIGHLIGHT_DEFAULT_ALPHA, REGION_HIGHLIGHT_DEFAULT_COLOR, _ARROW_STYLE_MAP, _INSET_CORNER_ORIGINS,
    _NO_KEY, _compute_stat_label_text)
from mpl_toolkits.axes_grid1.inset_locator import mark_inset

logger = logging.getLogger(__name__)


def draw_panel_label(canvas, ax, index):
    """軸の左上に (a)(b)(c)… を描く。文字は保存せず並び順から毎回決めるので、並べ替えても振り直される。"""
    label = canvas._panel_label_for_index(index)
    text_color = DARK_TEXT_COLOR if canvas.dark_mode else LIGHT_TEXT_COLOR
    ax.text(
        -0.12, 1.08, f"({label})", transform=ax.transAxes,
        fontsize=12, fontweight='bold', color=text_color,
        ha='left', va='top', zorder=10,
    )


def panel_label_for_index(index):
    """0->a, …, 25->z, 26->aa, 27->ab, …(Excel の列名と同じ)"""
    letters = []
    n = index
    while True:
        n, remainder = divmod(n, 26)
        letters.append(chr(ord('a') + remainder))
        if n == 0:
            break
        n -= 1
    return ''.join(reversed(letters))


def downsample_for_inset(canvas, x_data, y_data, full_resolution=False):
    """
    拡大図の点列を本体と同じく LTTB で間引く(注釈は描き直しのたびに作り直すので、大きなデータで重くなる)。
    拡大図は種類に関わらず線で描くので、散布図を除く本体の条件は当てはまらない。X が昇順のときだけ間引く。
    """
    if full_resolution or len(x_data) <= LTTB_DOWNSAMPLE_THRESHOLD:
        return x_data, y_data
    if not np.all(np.diff(x_data) >= 0):
        return x_data, y_data
    indices = calculate_lttb_downsample(x_data, y_data, LTTB_DOWNSAMPLE_TARGET_POINTS)
    return x_data[indices], y_data[indices]


def fit_inset_y_range(ax, inset_ax, zoom_y_range=None):
    """
    拡大図の Y 範囲。指定があればそのまま使う。無ければ自動の範囲を親の軸の Y 範囲に収める
    (親に印す四角は拡大図の表示範囲そのものなので、収めないと親の軸の外へはみ出す)。
    収まっているときは触らない(自動の範囲のまま)。拡大範囲の点がすべて親の範囲外なら、点が見えるよう自動のまま。
    """
    if zoom_y_range is not None:
        lo, hi = zoom_y_range
        inset_ax.set_ylim(min(lo, hi), max(lo, hi))
        return
    lo, hi = inset_ax.get_ylim()
    parent_lo, parent_hi = sorted(ax.get_ylim())
    clipped_lo, clipped_hi = max(lo, parent_lo), min(hi, parent_hi)
    if (clipped_lo, clipped_hi) == (lo, hi) or clipped_lo >= clipped_hi:
        return
    inset_ax.set_ylim(clipped_lo, clipped_hi)


def _bbox_corners(x0, y0, x1, y1):
    """mark_inset の角の番号(1 右上・2 左上・3 左下・4 右下)-> 点。"""
    return {1: (x1, y1), 2: (x0, y1), 3: (x0, y0), 4: (x1, y0)}


def choose_inset_connector_corners(box, inset):
    """
    引き出し線の角(loc1, loc2)。box は親に印す四角、inset は拡大図で、どちらも親の軸に対する座標の (x0, y0, x1, y1)(x0 < x1, y0 < y1)。
    同じ番号の角どうしを結ぶ線のうち、両方の四角が線の片側に収まる(=どちらの四角も横切らない)角を使う。
    今までの (2, 4) が使えるならそれを、次に (1, 3) を選ぶ。四角が重なっていて2つ見つからなければ (2, 4)。
    """
    box_corners, inset_corners = _bbox_corners(*box), _bbox_corners(*inset)
    points = list(box_corners.values()) + list(inset_corners.values())
    usable = []
    for loc in (1, 2, 3, 4):
        (px, py), (qx, qy) = box_corners[loc], inset_corners[loc]
        dx, dy = qx - px, qy - py
        if dx == 0 and dy == 0:
            continue
        sides = [dx * (ty - py) - dy * (tx - px) for tx, ty in points]
        tolerance = 1e-9 * max(abs(dx), abs(dy))
        if all(s >= -tolerance for s in sides) or all(s <= tolerance for s in sides):
            usable.append(loc)
    for pair in ((2, 4), (1, 3)):
        if all(loc in usable for loc in pair):
            return pair
    if len(usable) >= 2:
        return usable[0], usable[1]
    return 2, 4


def inset_connector_corners(ax, inset_ax, inset_rect):
    """
    拡大図の今の表示範囲(親に印す四角)と拡大図の位置から、引き出し線の角を見た目の位置で選ぶ。inset_rect は親の軸に対する (x0, y0, x1, y1)。
    """
    (x_lo, x_hi), (y_lo, y_hi) = inset_ax.get_xlim(), inset_ax.get_ylim()
    to_axes = ax.transData + ax.transAxes.inverted()
    (bx0, by0), (bx1, by1) = to_axes.transform([(x_lo, y_lo), (x_hi, y_hi)])
    box = (min(bx0, bx1), min(by0, by1), max(bx0, bx1), max(by0, by1))
    return choose_inset_connector_corners(box, inset_rect)


# mark_inset の四角は拡大図の表示範囲の向きで角を数えるので、拡大図を反転すると見た目の角と番号が入れ替わる
_MIRROR_X_CORNER = {1: 2, 2: 1, 3: 4, 4: 3}
_MIRROR_Y_CORNER = {1: 4, 4: 1, 2: 3, 3: 2}


def _box_corner_label(loc, inset_ax):
    """見た目で loc の位置にある、親に印す四角の角の番号。"""
    if inset_ax.xaxis_inverted():
        loc = _MIRROR_X_CORNER[loc]
    if inset_ax.yaxis_inverted():
        loc = _MIRROR_Y_CORNER[loc]
    return loc


def _secondary_axis(canvas, axis_index):
    secondary_axes = canvas.all_secondary_axes
    return secondary_axes[axis_index] if axis_index < len(secondary_axes) else None


def _map_between_y_axes(ax, from_ax, to_ax, y):
    """from_ax の Y の値 -> 親の図で同じ高さにある to_ax の Y の値(目盛りの種類・反転を含む)。"""
    y = np.asarray(y, dtype=float)
    # X は捨てるが、対数の X で 0 を変換すると nan が Y に混ざるので、軸の範囲内の値を使う
    x = np.full_like(y, ax.get_xlim()[0])
    display = from_ax.transData.transform(np.column_stack([x, y]))
    return to_ax.transData.inverted().transform(display)[:, 1]


def _inset_points(canvas, ds, x_min, x_max, full_resolution):
    """拡大範囲の点(間引いたもの)。範囲内に点が無ければ None。"""
    tx = np.asarray(ds.x_data, dtype=float)
    ty = np.asarray(ds.y_data, dtype=float)
    in_range = (tx >= x_min) & (tx <= x_max)
    if not in_range.any():
        return None
    return canvas._downsample_for_inset(tx[in_range], ty[in_range], full_resolution=full_resolution)


def _make_inset_secondary(ax, inset_ax, bounds, parent_secondary):
    """
    拡大図の右側の第2 Y 軸。twinx() は Figure に軸を足すので、軸だけ描き直す経路(cla())で消えずに残る。
    そのため親の子の軸として同じ場所に重ね、X を拡大図と共有する。
    """
    secondary = ax.inset_axes(bounds, sharex=inset_ax)
    secondary.patch.set_visible(False)
    secondary.xaxis.set_visible(False)
    secondary.yaxis.tick_right()
    if parent_secondary.get_yscale() != 'linear':
        secondary.set_yscale(parent_secondary.get_yscale())
    return secondary


def draw_inset(canvas, ax, axis_index, ann, datasets, full_resolution):
    """
    拡大図を描いて、作った artist を返す。種類やグラデーションは再現せず、範囲内の点を線で結ぶだけの概観。
    目盛りの種類・反転は親と同じにし、第2 Y 軸のデータセットは右側の第2 Y 軸に、親の図と同じ高さで描く。
    """
    x0, y0 = _INSET_CORNER_ORIGINS.get(ann.get('corner', '右上'), (0.55, 0.55))
    size = ann.get('size', 0.4)
    x_min, x_max = ann.get('zoom_x_range', (0, 1))
    color = canvas._effective_text_color(ann.get('color', '#000000'))
    bounds = (x0, y0, size, size)
    inset_ax = ax.inset_axes(bounds)
    artists = [inset_ax]
    # set_xscale は 'linear' でも目盛りを既定に戻すので、対数のときだけ呼ぶ
    if ax.get_xscale() != 'linear':
        inset_ax.set_xscale(ax.get_xscale())
    if ax.get_yscale() != 'linear':
        inset_ax.set_yscale(ax.get_yscale())

    parent_secondary = _secondary_axis(canvas, axis_index)
    secondary_lines = []
    for target_ds in (datasets or ()):
        if target_ds.subplot_target != axis_index or not target_ds.visible:
            continue
        points = _inset_points(canvas, target_ds, x_min, x_max, full_resolution)
        if points is None:
            continue
        style = dict(color=target_ds.color, linewidth=target_ds.linewidth, alpha=target_ds.alpha)
        if target_ds.use_secondary_y and parent_secondary is not None:
            secondary_lines.append((points, style))
        else:
            inset_ax.plot(*points, **style)

    inset_secondary = None
    if secondary_lines:
        inset_secondary = _make_inset_secondary(ax, inset_ax, bounds, parent_secondary)
        artists.append(inset_secondary)
        for (sx, sy), style in secondary_lines:
            inset_secondary.plot(sx, sy, **style)
            # 拡大図の Y 範囲(=親に印す四角)は第1 Y 軸の値なので、親の図で同じ高さになる値に直して入れる
            inset_ax.update_datalim(np.column_stack([sx, _map_between_y_axes(ax, parent_secondary, ax, sy)]))
        inset_ax.autoscale_view(scalex=False)

    inset_ax.set_xlim(x_min, x_max)
    fit_inset_y_range(ax, inset_ax, ann.get('zoom_y_range'))
    if ax.xaxis_inverted():
        inset_ax.xaxis.set_inverted(True)
    if ax.yaxis_inverted():
        inset_ax.yaxis.set_inverted(True)
    inset_ax.tick_params(labelsize=7)
    if inset_secondary is not None:
        # 右側の範囲は、拡大図の範囲を親の左右の軸の対応で読み替えたもの(向きもこれで親と同じになる)
        inset_secondary.set_ylim(*_map_between_y_axes(ax, ax, parent_secondary, inset_ax.get_ylim()))
        inset_secondary.tick_params(labelsize=7)

    if 'loc1' in ann or 'loc2' in ann:
        corners = [(ann.get('loc1', 2), None), (ann.get('loc2', 4), None)]
    else:
        pair = inset_connector_corners(ax, inset_ax, (x0, y0, x0 + size, y0 + size))
        corners = [(loc, _box_corner_label(loc, inset_ax)) for loc in pair]
    pp, p1, p2 = mark_inset(ax, inset_ax, loc1=corners[0][0], loc2=corners[1][0], fc="none", ec=color)
    p1.loc2, p2.loc2 = corners[0][1], corners[1][1]
    return artists + [pp, p1, p2]


def annotation_render_key(canvas, axis_index, settings, datasets, full_resolution, parent_ax=None):
    """
    注釈の描き直しを省くかどうかのキー。描いた結果に影響するものを全部入れる:
    ダークモード(色が変わる)、統計値ラベルの計算後の文字列、拡大図が描くデータセットの色・線幅・透明度・表示、
    拡大図があれば親の軸(第2 Y 軸も)の範囲と目盛りの種類(拡大図の範囲・向き・引き出し線の角がこれで決まる)。
    拡大図のデータそのものは入れない。これを使う update_appearance_only はデータが変わっていない前提の経路
    (データが変わる操作は cla() する別の経路を通り、そこでは使い回さない)。
    """
    annotations = axis_setting(settings, 'annotations')
    parts = [bool(canvas.dark_mode), bool(full_resolution), len(annotations)]
    if not annotations:
        return json.dumps(parts, default=str)

    if parent_ax is not None and any(ann.get('type') == 'inset' for ann in annotations):
        parts.append([list(parent_ax.get_xlim()), list(parent_ax.get_ylim()),
                      parent_ax.get_xscale(), parent_ax.get_yscale()])
        secondary = _secondary_axis(canvas, axis_index)
        if secondary is not None:
            parts.append([list(secondary.get_ylim()), secondary.get_yscale()])
    datasets_by_id = {ds.dataset_id: ds for ds in (datasets or ())}
    for ann in annotations:
        parts.append(json.dumps(ann, sort_keys=True, default=str))
        ann_type = ann.get('type')
        if ann_type == 'stat':
            dataset = datasets_by_id.get(ann.get('dataset_id'))
            parts.append(_compute_stat_label_text(dataset, ann.get('stat')))
        elif ann_type == 'inset':
            for target_ds in (datasets or ()):
                if target_ds.subplot_target != axis_index or not target_ds.visible:
                    continue
                parts.append((target_ds.dataset_id, target_ds.color,
                              target_ds.linewidth, target_ds.alpha))
    return json.dumps(parts, default=str)


def draw_annotations(canvas, ax, axis_index, settings, datasets=None, full_resolution=False,
                      allow_reuse=False):
    """
    軸の注釈(テキスト・矢印・領域ハイライト・統計値ラベル・拡大図)を、前回の分を消してから描く。

    allow_reuse=True なら、内容が前回と同じとき描き直しを省く(拡大図はデータを描き直すので重い)。
    使ってよいのは update_appearance_only() だけ。ほかの経路は前回の artist が既に消えている
    (fig.clf() / ax.cla() / 新しい軸)ので、使い回すと注釈が消える。既定は False。
    datasets は統計値ラベルと拡大図が使う(省略すると「データセットなし」)。
    """
    render_key = canvas._annotation_render_key(axis_index, settings, datasets, full_resolution, parent_ax=ax)
    if allow_reuse and canvas._annotation_render_keys.get(axis_index, _NO_KEY) == render_key:
        return

    for artist in canvas._annotation_artists.get(axis_index, []):
        try:
            artist.remove()
        except (ValueError, NotImplementedError):
            pass

    datasets_by_id = {ds.dataset_id: ds for ds in (datasets or ())}

    new_artists = []
    for ann in axis_setting(settings, 'annotations'):
        ann_type = ann.get('type')
        text = ann.get('text', '')
        try:
            if ann_type == 'arrow':
                color = canvas._effective_text_color(ann.get('color', '#000000'))
                arrowstyle = _ARROW_STYLE_MAP.get(ann.get('arrow_style', 'single'), '->')
                curvature = ann.get('arrow_curvature', 0.0)
                arrow_props = dict(arrowstyle=arrowstyle, color=color)
                if curvature:
                    arrow_props['connectionstyle'] = f'arc3,rad={curvature}'
                artist = ax.annotate(
                    text, xy=ann['xy'], xytext=ann['xytext'],
                    arrowprops=arrow_props,
                    color=color, fontsize=9, family=families_for_text(text, JP_CAPABLE_FONT_FAMILIES)
                )
            elif ann_type in ('vspan', 'hspan'):
                # 利用者が選んだ色をそのまま使う(ダークモードの読み替えはしない)
                lo, hi = ann.get('range', (0, 0))
                color = ann.get('color', REGION_HIGHLIGHT_DEFAULT_COLOR)
                alpha = ann.get('alpha', REGION_HIGHLIGHT_DEFAULT_ALPHA)
                if ann_type == 'vspan':
                    artist = ax.axvspan(lo, hi, color=color, alpha=alpha, zorder=0.5)
                else:
                    artist = ax.axhspan(lo, hi, color=color, alpha=alpha, zorder=0.5)
            elif ann_type == 'inset':
                new_artists.extend(draw_inset(canvas, ax, axis_index, ann, datasets, full_resolution))
                artist = None
            elif ann_type == 'stat':
                # 軸に対する位置なので、拡大・移動しても同じ場所に留まる
                color = canvas._effective_text_color(ann.get('color', '#000000'))
                xy = ann.get('xy', (0.05, 0.95))
                dataset = datasets_by_id.get(ann.get('dataset_id'))
                label_text = _compute_stat_label_text(dataset, ann.get('stat'))
                artist = ax.text(
                    xy[0], xy[1], label_text, transform=ax.transAxes,
                    color=color, fontsize=9, family=families_for_text(label_text, JP_CAPABLE_FONT_FAMILIES),
                    va='top', ha='left', zorder=10,
                )
            else:
                color = canvas._effective_text_color(ann.get('color', '#000000'))
                xy = ann.get('xy', (0, 0))
                artist = ax.text(xy[0], xy[1], text, color=color, fontsize=9,
                                 family=families_for_text(text, JP_CAPABLE_FONT_FAMILIES))
            if artist is not None:
                new_artists.append(artist)
        except Exception:
            logger.exception("注釈の描画に失敗しました: %s", ann)
    canvas._annotation_artists[axis_index] = new_artists
    # 使い回さない経路でもキーは更新する(直後の update_appearance_only が無駄に描き直さないように)
    canvas._annotation_render_keys[axis_index] = render_key
