# tests/test_mathtext_preview.py
"""gui/mathtext_preview.py のテスト(項目H-2-4追加分)。"""
from PySide6.QtGui import QPixmap

from gui.mathtext_preview import render_mathtext_to_pixmap, FitWidthPixmapLabel


def test_render_mathtext_to_pixmap_returns_nonempty_pixmap_for_plain_text():
    pixmap = render_mathtext_to_pixmap("タイトルを入力")
    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_render_mathtext_to_pixmap_returns_nonempty_pixmap_for_empty_text():
    # 空文字列でも(プレースホルダ用途で)クラッシュせず、最低限のピクセルを返す
    pixmap = render_mathtext_to_pixmap("")
    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_render_mathtext_to_pixmap_handles_valid_mathtext_syntax():
    pixmap = render_mathtext_to_pixmap(r"$\alpha$ vs time")
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_render_mathtext_to_pixmap_falls_back_to_plain_text_on_broken_mathtext_syntax():
    # $の対応が取れていない壊れたmathtext構文でも例外を投げず、
    # プレーンテキストとして描画し直してピクスマップを返す
    pixmap = render_mathtext_to_pixmap(r"$\alpha$\leftarrow$")
    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_render_mathtext_to_pixmap_wider_for_longer_text():
    short_pixmap = render_mathtext_to_pixmap("A")
    long_pixmap = render_mathtext_to_pixmap("A much longer piece of title text")
    assert long_pixmap.width() > short_pixmap.width()


def test_render_mathtext_to_pixmap_renders_japanese_without_glyph_warning(recwarn):
    render_mathtext_to_pixmap("タイトルを入力")
    glyph_warnings = [
        w for w in recwarn.list if "missing from font" in str(w.message)
    ]
    assert not glyph_warnings


# --- FitWidthPixmapLabel(実機フィードバック: 「ここの文字サイズを枠内に
#     収まるようにして」、長いmathtext文字列がプレビュー欄の枠からはみ出して
#     いた不具合。続報: 「入力したあとの文字は治ったけど入力する前の
#     『～を入力』はまだボックスにおさまってない」→ 幅だけでなく高さの
#     超過も見る必要があった、下記test_fit_width_pixmap_label_shrinks_when_
#     only_height_overflows参照) ---

def test_fit_width_pixmap_label_keeps_natural_pixmap_when_it_already_fits(qapp):
    label = FitWidthPixmapLabel()
    label.resize(300, 40)
    pixmap = render_mathtext_to_pixmap("short")
    assert pixmap.width() < 300

    label.set_natural_pixmap(pixmap)

    assert label.pixmap().width() == pixmap.width()
    assert label.pixmap().height() == pixmap.height()


def test_fit_width_pixmap_label_shrinks_pixmap_wider_than_widget(qapp):
    label = FitWidthPixmapLabel()
    label.resize(120, 30)
    pixmap = render_mathtext_to_pixmap("a much longer piece of preview text than fits")
    assert pixmap.width() > 120

    label.set_natural_pixmap(pixmap)

    assert label.pixmap().width() <= 120
    # 幅だけでなく高さもアスペクト比を保って縮小されていること
    expected_height = round(pixmap.height() * (label.pixmap().width() / pixmap.width()))
    assert abs(label.pixmap().height() - expected_height) <= 1


def test_fit_width_pixmap_label_shrinks_when_only_height_overflows(qapp):
    """
    バグ回帰テスト: 「入力したあとの文字は治ったけど入力する前の
    『～を入力』はまだボックスにおさまってない」。プレースホルダのような
    短い(=幅は十分収まる)テキストは、幅方向の縮小条件に一度も引っかからず、
    天地(高さ)がラベルの高さを超えたまま放置されていた(実際に入力した
    テキストはmathtext記法込みで横幅が長くなりやすく、その際は幅方向の
    縮小のついでに高さも縮んでいたため気づかれなかった)。
    幅には十分収まるが高さだけがラベルより大きいpixmapでも、正しく
    縮小されることを確認する。
    """
    label = FitWidthPixmapLabel()
    label.resize(300, 18)  # 幅は十分だが高さが18pxしかない
    pixmap = render_mathtext_to_pixmap("短いテキスト", fontsize=20)  # 幅<300、高さ>18
    assert pixmap.width() < 300
    assert pixmap.height() > 18

    label.set_natural_pixmap(pixmap)

    assert label.pixmap().width() <= 300
    assert label.pixmap().height() <= 18


def test_fit_width_pixmap_label_refits_on_resize(qapp):
    """
    実機フィードバックの真因(タブ切り替え直後などset_natural_pixmap()呼び出し
    時点のwidth()が実際のレイアウト確定値と一致しないケース)に対応する
    resizeEvent()での再フィットを確認する。
    """
    from PySide6.QtWidgets import QApplication

    label = FitWidthPixmapLabel()
    label.show()
    label.resize(50, 30)  # まだ狭い状態でセット
    QApplication.instance().processEvents()
    pixmap = render_mathtext_to_pixmap("a somewhat long preview text")
    label.set_natural_pixmap(pixmap)
    assert label.pixmap().width() <= 50

    label.resize(600, 40)  # 実際のレイアウト確定後、幅・高さとも広がったと仮定
    QApplication.instance().processEvents()
    assert label.pixmap().width() == pixmap.width()  # 十分広いので等倍に戻る
    label.close()


def test_fit_width_pixmap_label_does_nothing_before_natural_pixmap_is_set(qapp):
    label = FitWidthPixmapLabel()
    label.resize(200, 40)  # クラッシュしないことのみ確認
    assert label.pixmap() is None or label.pixmap().isNull()
