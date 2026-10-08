"""対数軸で表示されない値(0 以下)を、対数のチェックの下で知らせる。

matplotlib は対数軸の 0 以下の点を黙って消し、0 以下の最小値も黙って無視するので、何も描かれない理由が分からなくなる。
"""
import numpy as np
import pandas as pd

from graphica.core.axis_settings import axis_setting
from graphica.core.i18n import tr

# 軸のキー -> (対数の設定, 自動スケールの設定, 最小値の設定, 説明の欄の名前)
_AXES = {
    'x': ('x_log', 'x_autoscale', 'x_min', 'x_log_note'),
    'y': ('y_log', 'y_autoscale', 'y_min', 'y_log_note'),
    'y2': ('y2_log', 'y2_autoscale', 'y2_min', 'y2_log_note'),
}


def _numbers(values):
    return pd.to_numeric(pd.Series(np.asarray(values).ravel()), errors='coerce').to_numpy(dtype=float)


def nonpositive_point_count(canvas, datasets, axis_index, axis_key):
    """axis_index のサブプロットで、axis_key の軸に描く値が 0 以下の点の数(描かれる位置で数える)。"""
    count = 0
    for ds in datasets:
        if not ds.visible or ds.data_kind == '2d_grid' or ds.subplot_target != axis_index:
            continue
        if axis_key == 'y' and ds.use_secondary_y or axis_key == 'y2' and not ds.use_secondary_y:
            continue
        # 文字の X(カテゴリ軸)は数にならないので数えない
        x, y = _numbers(ds.x_data), _numbers(ds.y_data)
        x, y = canvas.data_to_display(ds, x, y)
        values = np.asarray(x if axis_key == 'x' else y, dtype=float)
        count += int(np.count_nonzero(values <= 0))
    return count


def log_note_text(count, min_ignored):
    """説明の文。知らせることが無ければ空。"""
    lines = []
    if count:
        lines.append(tr("0 以下の値の点が {count} 個あり、対数軸では表示されません。").format(count=f"{count:,}"))
    if min_ignored:
        lines.append(tr("最小値が 0 以下なので、対数軸では無視されます。"))
    return "\n".join(lines)


def update_log_axis_notes(app, _event=None):
    """表示中の軸の設定で、X・Y・第 2 Y 軸の説明を出し入れする。描くたびと、表示中の軸を切り替えたときに呼ぶ。"""
    settings_list = app.project.all_plot_settings
    index = app.project.active_axis_index
    settings = settings_list[index] if 0 <= index < len(settings_list) else None
    for axis_key, (log_key, autoscale_key, min_key, note_name) in _AXES.items():
        note = getattr(app, note_name, None)
        if note is None:
            continue
        text = ""
        if settings is not None and axis_setting(settings, log_key):
            min_ignored = not axis_setting(settings, autoscale_key) and axis_setting(settings, min_key) <= 0
            count = nonpositive_point_count(app.canvas, app.project.datasets, index, axis_key)
            text = log_note_text(count, min_ignored)
        note.setText(text)
        note.setVisible(bool(text))
