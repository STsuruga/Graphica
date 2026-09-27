"""日本語と数式($...$)を混ぜたラベル: 数式の外の文字を描く字体の先頭が日本語の字体になる。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from graphica.gui.mathtext_preview import (JP_CAPABLE_FONT_FAMILIES, families_for_text,  # noqa: E402
                                           families_for_texts, font_kwargs_for_text)

DEFAULT = ["DejaVu Sans", "Yu Gothic"]


@pytest.mark.parametrize("text", ["強度 (a.u.)", "$I_0$ / cm$^{-1}$", "価格 \$5", "", None])
def test_labels_without_both_japanese_and_math_are_left_alone(text):
    assert families_for_text(text, DEFAULT) is DEFAULT


def test_mixed_labels_put_a_japanese_font_first_and_keep_the_rest():
    families = families_for_text("強度 $I_0$ (a.u.)", ["Arial"])
    assert families[0] != "Arial" and families[0] in JP_CAPABLE_FONT_FAMILIES
    assert families[-1] == "Arial"
    assert "DejaVu Sans" not in families[:-1]


def test_a_japanese_font_the_user_chose_first_is_kept():
    assert families_for_text("強度 $I_0$", ["Meiryo"]) == ["Meiryo"]


def test_font_kwargs_are_copied_only_when_changed():
    kwargs = {"family": ["DejaVu Sans"], "size": 10}
    assert font_kwargs_for_text("x $y$", kwargs) is kwargs
    changed = font_kwargs_for_text("強度 $I$", kwargs)
    assert changed is not kwargs and changed["size"] == 10 and kwargs["family"] == ["DejaVu Sans"]


def test_a_legend_uses_the_japanese_order_if_any_entry_needs_it():
    assert families_for_texts(["A", "B"], DEFAULT) is DEFAULT
    assert families_for_texts(["A", "試料 $x_1$"], DEFAULT)[0] != "DejaVu Sans"


def _has_a_japanese_font():
    from matplotlib import font_manager

    for family in JP_CAPABLE_FONT_FAMILIES[1:]:
        try:
            font_manager.findfont(font_manager.FontProperties(family=family), fallback_to_default=False)
            return True
        except ValueError:
            continue
    return False


@pytest.mark.skipif(not _has_a_japanese_font(), reason="日本語の字体が入っていない環境")
@pytest.mark.parametrize("fixed, missing_expected", [(True, False), (False, True)])
def test_a_mixed_title_draws_without_missing_glyphs(caplog, fixed, missing_expected):
    """この PC の日本語の字体で描けること。□ になると mathtext が「glyph が無い」と記録する(直さなければ出る)。"""
    fig, ax = plt.subplots()
    try:
        title = "強度 $I_0$ / cm$^{-1}$"
        families = list(JP_CAPABLE_FONT_FAMILIES)
        ax.set_title(title, family=families_for_text(title, families) if fixed else families)
        with caplog.at_level("WARNING"):
            fig.canvas.draw()
        missing = [r for r in caplog.records if "does not have a glyph" in r.getMessage()]
        assert bool(missing) is missing_expected
    finally:
        plt.close(fig)
