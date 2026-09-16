# tests/test_palette_dialog_selection.py
"""
配色パレットの管理ダイアログの初期選択(v1.4.2)。

組み込みパレット(Okabe-Ito 等)を有効にしてから開き直すと、表示が
「Matplotlib既定」に戻っていた。利用者が作ったパレットしか初期選択の対象に
していなかったため。そのまま OK を押すと、アクティブなパレットが既定に
上書きされてしまう。
"""
import pytest

from core.color_palettes import BUILTIN_PALETTES
from gui.dialogs import ColorPaletteDialog


@pytest.mark.parametrize("builtin_name", sorted(BUILTIN_PALETTES))
def test_builtin_active_palette_is_preselected(builtin_name):
    dlg = ColorPaletteDialog({}, builtin_name)
    assert dlg.palette_combo.currentText() == builtin_name


def test_accepting_without_changes_keeps_the_builtin_palette_active():
    name = sorted(BUILTIN_PALETTES)[0]
    dlg = ColorPaletteDialog({"自作": ["#000000"]}, name)
    _palettes, active = dlg.get_result()
    assert active == name


def test_builtin_palette_shows_its_colors_read_only():
    name = sorted(BUILTIN_PALETTES)[0]
    dlg = ColorPaletteDialog({}, name)
    assert dlg.color_list.count() == len(BUILTIN_PALETTES[name])
    assert not dlg.add_color_button.isEnabled()


def test_user_palette_is_still_preselected():
    dlg = ColorPaletteDialog({"自作": ["#112233", "#445566"]}, "自作")
    assert dlg.palette_combo.currentText() == "自作"


def test_unknown_active_name_falls_back_to_the_default():
    dlg = ColorPaletteDialog({}, "削除済みのパレット")
    assert dlg.palette_combo.currentText() == ColorPaletteDialog.DEFAULT_PALETTE_NAME
