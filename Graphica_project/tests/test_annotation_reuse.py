# tests/test_annotation_reuse.py
"""
注釈の「変わっていなければ作り直さない」最適化のテスト(改善ボード E-2)。

`_draw_annotations()` は毎回、そのAxesの注釈Artistを全て `remove()` してから
作り直していた。テキストや矢印だけなら軽いが、**インセット(拡大図)は中で
データセットを再プロットする**ため、「注釈数×データ点数」のコストが、軸の
書式をいじるたびに毎回かかっていた(E-1 でインセットの間引きは入れたが、
毎回作り直す構造自体は残っていた)。

実測(20万点、`_draw_annotations` 1回あたりの中央値):

| インセット | 従来 | E-2後 |
|---|---|---|
| 1個 | 8.6 ms | 0.01 ms |
| 2個 | 14.8 ms | 0.03 ms |
| 4個 | 41.8 ms | 0.03 ms |

★ このファイルで最も大事なのは **速度ではなく「再利用してはいけない場面で
再利用していないこと」**。取り違えると「ダークモードにしたのに注釈の色だけ
元のまま」「サブプロットを描き直したら注釈が消えた」という、目で見るまで
気づけない壊れ方をする。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from core.dataset import Dataset
from gui.canvas import MplCanvas


@pytest.fixture
def canvas():
    c = MplCanvas(width=4, height=3, dpi=80)
    yield c
    plt.close(c.fig)


def _make_dataset(name="ds", n=50, color="#112233", dataset_id=None):
    x = np.linspace(0.0, 100.0, n)
    dataset = Dataset(name=name, df=pd.DataFrame({"x": x, "y": np.sin(x)}),
                      x_col_name="x", y_col_name="y", color=color)
    if dataset_id is not None:
        dataset.dataset_id = dataset_id
    return dataset


def _text_settings(text="メモ", color="#000000"):
    return {'annotations': [{'type': 'text', 'xy': (1.0, 1.0),
                             'text': text, 'color': color}]}


def _inset_settings(x_min=0.0, x_max=100.0):
    return {'annotations': [{'type': 'inset', 'corner': '右上', 'size': 0.4,
                             'zoom_x_range': (x_min, x_max), 'color': '#000000'}]}


def _stat_settings(dataset_id, stat='mean'):
    return {'annotations': [{'type': 'stat', 'xy': (0.05, 0.95), 'color': '#000000',
                             'dataset_id': dataset_id, 'stat': stat}]}


def _draw(canvas, settings, datasets=(), allow_reuse=False, axis_index=0):
    ax = canvas.fig.gca()
    canvas.all_axes = [ax]
    canvas._draw_annotations(ax, axis_index, settings, datasets=datasets,
                             allow_reuse=allow_reuse)
    return list(canvas._annotation_artists.get(axis_index, []))


# --- 再利用が効く場合 ---

def test_unchanged_annotations_keep_the_same_artists(canvas):
    settings = _text_settings()
    first = _draw(canvas, settings)
    second = _draw(canvas, settings, allow_reuse=True)

    assert second, "注釈が消えている"
    assert [id(a) for a in first] == [id(a) for a in second], \
        "内容が同じなのにArtistが作り直されている"


def test_reuse_works_right_after_a_full_redraw(canvas):
    """
    再利用しない経路でもキーを更新しておくこと。更新しないと、全体再描画の
    直後の1回が必ず無駄に描き直しになる。
    """
    settings = _inset_settings()
    datasets = [_make_dataset()]
    first = _draw(canvas, settings, datasets)          # allow_reuse=False(全体再描画相当)
    second = _draw(canvas, settings, datasets, allow_reuse=True)

    assert [id(a) for a in first] == [id(a) for a in second]


def test_repeated_reuse_does_not_accumulate_artists(canvas):
    """
    そもそも毎回全削除していたのは重複描画を防ぐためだった。再利用で
    その保証が崩れていないこと(何度呼んでも注釈は1つぶんのまま)。
    """
    settings = _text_settings()
    _draw(canvas, settings)
    for _ in range(5):
        artists = _draw(canvas, settings, allow_reuse=True)

    assert len(artists) == 1
    assert len(canvas.fig.gca().texts) == 1


# --- 再利用してはいけない場合 ---

def test_changing_the_annotation_text_redraws(canvas):
    first = _draw(canvas, _text_settings("前"))
    second = _draw(canvas, _text_settings("後"), allow_reuse=True)

    assert [id(a) for a in first] != [id(a) for a in second]
    assert second[0].get_text() == "後"


def test_adding_an_annotation_redraws(canvas):
    settings = _text_settings()
    _draw(canvas, settings)

    more = {'annotations': settings['annotations'] + [
        {'type': 'text', 'xy': (2.0, 2.0), 'text': '2つ目', 'color': '#000000'}]}
    artists = _draw(canvas, more, allow_reuse=True)

    assert len(artists) == 2


def test_removing_every_annotation_redraws(canvas):
    _draw(canvas, _text_settings())
    artists = _draw(canvas, {'annotations': []}, allow_reuse=True)

    assert artists == []
    assert len(canvas.fig.gca().texts) == 0


def test_toggling_dark_mode_redraws(canvas):
    """
    ★ 一番踏みやすい罠。テキスト/矢印の色は _effective_text_color() を通るので、
    注釈リストが同一でもダークモードが変われば描画結果が変わる。キーに
    dark_mode を入れ忘れると「ダークモードにしたのに注釈の色だけ元のまま」になる。
    """
    settings = _text_settings(color="#000000")
    canvas.dark_mode = False
    first = _draw(canvas, settings)
    light_color = first[0].get_color()

    canvas.dark_mode = True
    second = _draw(canvas, settings, allow_reuse=True)

    assert [id(a) for a in first] != [id(a) for a in second], \
        "ダークモードが変わったのに再利用してしまっている"
    assert second[0].get_color() != light_color


def test_changing_a_stat_value_redraws(canvas):
    """
    統計値アンカーラベルは、この経路が datasets を受け取る唯一の理由
    (値の再計算)。値が変わったら描き直すこと。
    """
    dataset = _make_dataset(dataset_id="ds-1")
    settings = _stat_settings("ds-1")
    first = _draw(canvas, settings, [dataset])
    before_text = first[0].get_text()

    dataset.df = pd.DataFrame({"x": dataset.df["x"], "y": dataset.df["y"] + 1000.0})
    second = _draw(canvas, settings, [dataset], allow_reuse=True)

    assert [id(a) for a in first] != [id(a) for a in second]
    assert second[0].get_text() != before_text


def test_changing_an_inset_datasets_colour_redraws(canvas):
    dataset = _make_dataset(color="#112233")
    settings = _inset_settings()
    first = _draw(canvas, settings, [dataset])

    dataset.color = "#ff0000"
    second = _draw(canvas, settings, [dataset], allow_reuse=True)

    assert [id(a) for a in first] != [id(a) for a in second]


def test_hiding_an_inset_dataset_redraws(canvas):
    dataset = _make_dataset()
    settings = _inset_settings()
    first = _draw(canvas, settings, [dataset])

    dataset.visible = False
    second = _draw(canvas, settings, [dataset], allow_reuse=True)

    assert [id(a) for a in first] != [id(a) for a in second]


def test_changing_the_zoom_range_redraws(canvas):
    dataset = _make_dataset()
    first = _draw(canvas, _inset_settings(0.0, 50.0), [dataset])
    second = _draw(canvas, _inset_settings(0.0, 60.0), [dataset], allow_reuse=True)

    assert [id(a) for a in first] != [id(a) for a in second]


# --- 既定は「再利用しない」 ---

def test_reuse_is_opt_in(canvas):
    """
    ★ 既定をFalseにしてあるのは、Axesを作り直す経路(fig.clf() / ax.cla() /
    新規Axes)で再利用すると**注釈が消える**ため。将来の呼び出し元が何も
    考えずに安全側へ倒れるようにしておく。
    """
    import inspect
    signature = inspect.signature(MplCanvas._draw_annotations)
    assert signature.parameters['allow_reuse'].default is False

    settings = _text_settings()
    first = _draw(canvas, settings)
    second = _draw(canvas, settings)  # allow_reuse を指定しない

    assert [id(a) for a in first] != [id(a) for a in second]


def test_only_the_appearance_only_path_opts_in():
    """
    再利用してよいのは `update_appearance_only()` だけ(Axesを cla() しない
    唯一の経路)。他の3経路が allow_reuse を渡していないことを、呼び出し元の
    ソースを見て固定する。
    """
    import inspect
    for name in ("redraw_all", "_redraw_single_axis_no_draw", "add_free_axis"):
        source = inspect.getsource(getattr(MplCanvas, name))
        assert "_draw_annotations" in source, f"{name} が注釈を描いていない"
        assert "allow_reuse" not in source, \
            f"{name} は Axes を作り直すので再利用してはいけない"

    appearance_source = inspect.getsource(MplCanvas.update_appearance_only)
    assert "allow_reuse=True" in appearance_source


# --- キャッシュの後始末 ---

def test_single_axis_redraw_drops_the_cached_key(canvas):
    """
    ax.cla() で古いArtistは死ぬので、キーも一緒に捨てること。残すと、その後の
    update_appearance_only が「変わっていない」と判断して**注釈が消えたまま**になる。
    """
    import inspect
    source = inspect.getsource(MplCanvas._redraw_single_axis_no_draw)
    assert "_annotation_render_keys.pop" in source

    full_redraw_source = inspect.getsource(MplCanvas.redraw_all)
    assert "_annotation_render_keys.clear" in full_redraw_source

    remove_source = inspect.getsource(MplCanvas.remove_last_free_axis)
    assert "_annotation_render_keys.pop" in remove_source


def test_key_cache_is_per_axis(canvas):
    """別のAxesのキーと取り違えないこと。"""
    settings_a = _text_settings("A")
    settings_b = _text_settings("B")
    ax = canvas.fig.gca()
    canvas.all_axes = [ax]

    canvas._draw_annotations(ax, 0, settings_a)
    canvas._draw_annotations(ax, 1, settings_b)

    assert canvas._annotation_render_keys[0] != canvas._annotation_render_keys[1]


def test_a_fresh_axis_index_never_reuses(canvas):
    """一度も描いていないAxesで再利用が許可されても、ちゃんと描くこと。"""
    artists = _draw(canvas, _text_settings(), allow_reuse=True, axis_index=3)
    assert len(artists) == 1
