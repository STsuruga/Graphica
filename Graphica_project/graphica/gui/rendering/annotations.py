"""注釈(文字・矢印・統計ラベル・範囲の強調・拡大図)とパネルラベルの描画。作り直しを省く鍵もここで作る。"""
import json
import logging
import numpy as np
from graphica.core.analysis import calculate_lttb_downsample
from graphica.core.axis_settings import axis_setting
from graphica.gui.mathtext_preview import JP_CAPABLE_FONT_FAMILIES
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


def annotation_render_key(canvas, axis_index, settings, datasets, full_resolution):
    """
    注釈の描き直しを省くかどうかのキー。描いた結果に影響するものを全部入れる:
    ダークモード(色が変わる)、統計値ラベルの計算後の文字列、拡大図が描くデータセットの色・線幅・透明度・表示。
    拡大図のデータそのものは入れない。これを使う update_appearance_only はデータが変わっていない前提の経路
    (データが変わる操作は cla() する別の経路を通り、そこでは使い回さない)。
    """
    annotations = axis_setting(settings, 'annotations')
    parts = [bool(canvas.dark_mode), bool(full_resolution), len(annotations)]
    if not annotations:
        return json.dumps(parts, default=str)

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
    render_key = canvas._annotation_render_key(axis_index, settings, datasets, full_resolution)
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
                    color=color, fontsize=9, family=JP_CAPABLE_FONT_FAMILIES
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
                # 拡大図は、種類やグラデーションは再現せず、範囲内の点を線で結ぶだけの概観
                x0, y0 = _INSET_CORNER_ORIGINS.get(ann.get('corner', '右上'), (0.55, 0.55))
                size = ann.get('size', 0.4)
                x_min, x_max = ann.get('zoom_x_range', (0, 1))
                color = canvas._effective_text_color(ann.get('color', '#000000'))
                inset_ax = ax.inset_axes((x0, y0, size, size))
                for target_ds in (datasets or ()):
                    if target_ds.subplot_target != axis_index or not target_ds.visible:
                        continue
                    tx = np.asarray(target_ds.x_data, dtype=float)
                    ty = np.asarray(target_ds.y_data, dtype=float)
                    in_range = (tx >= x_min) & (tx <= x_max)
                    if in_range.any():
                        inset_x, inset_y = canvas._downsample_for_inset(
                            tx[in_range], ty[in_range], full_resolution=full_resolution
                        )
                        inset_ax.plot(inset_x, inset_y, color=target_ds.color,
                                      linewidth=target_ds.linewidth, alpha=target_ds.alpha)
                inset_ax.set_xlim(x_min, x_max)
                inset_ax.tick_params(labelsize=7)
                pp, p1, p2 = mark_inset(ax, inset_ax, loc1=ann.get('loc1', 2), loc2=ann.get('loc2', 4),
                                        fc="none", ec=color)
                new_artists.extend([inset_ax, pp, p1, p2])
                artist = None
            elif ann_type == 'stat':
                # 軸に対する位置なので、拡大・移動しても同じ場所に留まる
                color = canvas._effective_text_color(ann.get('color', '#000000'))
                xy = ann.get('xy', (0.05, 0.95))
                dataset = datasets_by_id.get(ann.get('dataset_id'))
                label_text = _compute_stat_label_text(dataset, ann.get('stat'))
                artist = ax.text(
                    xy[0], xy[1], label_text, transform=ax.transAxes,
                    color=color, fontsize=9, family=JP_CAPABLE_FONT_FAMILIES, va='top', ha='left', zorder=10,
                )
            else:
                color = canvas._effective_text_color(ann.get('color', '#000000'))
                xy = ann.get('xy', (0, 0))
                artist = ax.text(xy[0], xy[1], text, color=color, fontsize=9, family=JP_CAPABLE_FONT_FAMILIES)
            if artist is not None:
                new_artists.append(artist)
        except Exception:
            logger.exception("注釈の描画に失敗しました: %s", ann)
    canvas._annotation_artists[axis_index] = new_artists
    # 使い回さない経路でもキーは更新する(直後の update_appearance_only が無駄に描き直さないように)
    canvas._annotation_render_keys[axis_index] = render_key
