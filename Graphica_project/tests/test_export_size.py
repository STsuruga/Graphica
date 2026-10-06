"""gui/export_size.py: 書き出しの大きさの換算、単位を切り替えたときの数字の換算、プレビューの解像度、大きすぎる画像の確認。"""
import pytest
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel, QMessageBox, QSpinBox

import graphica.gui.export_size as export_size
from graphica.gui.export_size import (
    LARGE_OUTPUT_PIXELS, MAX_RASTER_SIDE_PX, ExportSizeFields, confirm_output_size, convert_length,
    output_pixel_size, preview_dpi, size_in_inches)

PX, IN, CM, MM = "ピクセル (px)", "インチ (in)", "センチメートル (cm)", "ミリメートル (mm)"


@pytest.mark.parametrize("unit, expected", [
    (PX, (8.0, 6.0)), (IN, (1200, 900)), (CM, (1200 / 2.54, 900 / 2.54)), (MM, (1200 / 25.4, 900 / 25.4)),
    ("bogus", (8, 6)),
])
def test_size_in_inches(unit, expected):
    assert size_in_inches(1200, 900, unit, 150) == pytest.approx(expected)


@pytest.mark.parametrize("unit, divide", [(PX, lambda v: v / 300), (CM, lambda v: v / 2.54), (MM, lambda v: v / 25.4)])
def test_size_in_inches_divides_exactly_like_before(unit, divide):
    """逆数を掛けると最後のビットが変わり、書き出す PDF の中身まで変わる(特性テストが CI で落ちた)。"""
    width, height = size_in_inches(800, 600, unit, 300)
    assert (width, height) == (divide(800), divide(600))


def test_convert_length_keeps_the_physical_size():
    assert convert_length(800, PX, CM, 150) == pytest.approx(800 / 150 * 2.54)
    assert convert_length(800 / 150 * 2.54, CM, PX, 150) == pytest.approx(800)
    assert convert_length(2.54, CM, MM, 300) == pytest.approx(25.4)
    assert convert_length(5, "bogus", CM, 150) == 5


def test_output_pixel_size():
    assert output_pixel_size(8, 6, 150) == (1200, 900)


def test_preview_dpi_fits_the_preview_area_for_a_large_figure():
    dpi = preview_dpi(30, 20, 150, 400, 300)
    assert 30 * dpi <= 400 * export_size.PREVIEW_OVERSAMPLE + 1
    assert 20 * dpi <= 300 * export_size.PREVIEW_OVERSAMPLE + 1


def test_preview_dpi_never_exceeds_the_export_dpi():
    assert preview_dpi(1, 1, 150, 400, 300) == 150


def test_preview_dpi_does_not_go_below_what_text_needs():
    """下げすぎると小さな文字が描けない(FreeType が拒む)。"""
    assert preview_dpi(100, 80, 150, 400, 300) == export_size.MIN_PREVIEW_DPI


def test_preview_is_skipped_when_even_the_floor_is_too_large():
    """800 cm × 600 cm(単位を切り替えて数字がそのまま残ったときの大きさ)。"""
    assert preview_dpi(800 / 2.54, 600 / 2.54, 150, 400, 300) is None


# --- 大きすぎる画像の確認 ---

def _patch_dialogs(monkeypatch, answer=QMessageBox.StandardButton.No):
    calls = {"warning": [], "question": []}
    monkeypatch.setattr(export_size.notify, "warning", lambda *a, **k: calls["warning"].append(a))

    def question(*a, **k):
        calls["question"].append(a)
        return answer
    monkeypatch.setattr(export_size.notify, "question", question)
    return calls


def test_normal_size_needs_no_confirmation(monkeypatch):
    calls = _patch_dialogs(monkeypatch)
    assert confirm_output_size(None, 8, 6, 300) is True
    assert calls == {"warning": [], "question": []}


def test_a_side_over_the_limit_is_refused(monkeypatch):
    calls = _patch_dialogs(monkeypatch, answer=QMessageBox.StandardButton.Yes)
    width_in = (MAX_RASTER_SIDE_PX + 10) / 100
    assert confirm_output_size(None, width_in, 1, 100) is False
    assert len(calls["warning"]) == 1 and calls["question"] == []


@pytest.mark.parametrize("answer, expected", [
    (QMessageBox.StandardButton.Yes, True), (QMessageBox.StandardButton.No, False)])
def test_a_very_large_image_asks_first(monkeypatch, answer, expected):
    calls = _patch_dialogs(monkeypatch, answer=answer)
    side_in = (LARGE_OUTPUT_PIXELS ** 0.5 + 100) / 100
    assert confirm_output_size(None, side_in, side_in, 100) is expected
    assert len(calls["question"]) == 1 and calls["warning"] == []


# --- 欄のまとまり ---

@pytest.fixture
def fields():
    width, height, dpi = QDoubleSpinBox(), QDoubleSpinBox(), QSpinBox()
    for spin_box in (width, height):
        spin_box.setRange(1, 10000)
        spin_box.setDecimals(1)
    width.setValue(800)
    height.setValue(600)
    dpi.setRange(50, 1200)
    dpi.setValue(150)
    unit = QComboBox()
    for text in (PX, IN, CM, MM):
        unit.addItem(text, text)
    label = QLabel()
    sizes = ExportSizeFields(width, height, unit, dpi, label)
    yield sizes
    for widget in (width, height, dpi, unit, label):
        widget.deleteLater()


def _select(sizes, unit):
    sizes.unit_combo.setCurrentIndex(sizes.unit_combo.findData(unit))


def test_switching_unit_converts_the_numbers(fields):
    _select(fields, CM)
    assert fields.width_spinbox.value() == pytest.approx(13.55)
    assert fields.height_spinbox.value() == pytest.approx(10.16)
    assert fields.width_spinbox.decimals() == 2

    _select(fields, PX)
    assert fields.width_spinbox.value() == pytest.approx(800)
    assert fields.height_spinbox.value() == pytest.approx(600)
    assert fields.width_spinbox.decimals() == 0


def test_switching_unit_keeps_the_size_in_inches(fields):
    before = fields.size_in_inches()
    for unit in (IN, MM, CM, PX):
        _select(fields, unit)
        assert fields.size_in_inches() == pytest.approx(before, rel=5e-3)


def test_switching_unit_does_not_emit_intermediate_value_changes(fields):
    changes = []
    fields.width_spinbox.valueChanged.connect(changes.append)
    fields.height_spinbox.valueChanged.connect(changes.append)
    _select(fields, CM)
    assert changes == []


def test_unit_change_handlers_connected_later_see_the_converted_numbers(fields):
    seen = []
    fields.unit_combo.currentIndexChanged.connect(lambda _i: seen.append(fields.width_spinbox.value()))
    _select(fields, IN)
    assert seen == [pytest.approx(5.33)]


def test_pixel_label_follows_size_and_dpi(fields):
    assert fields.pixel_label.text() == "画像にすると 約 800 × 600 px"
    fields.dpi_spinbox.setValue(300)  # ピクセル指定なら画素数は変わらない
    assert fields.pixel_label.text() == "画像にすると 約 800 × 600 px"
    _select(fields, IN)  # 800 px @ 300 dpi = 2.67 in(小数2桁)
    fields.dpi_spinbox.setValue(600)  # 長さの指定なら解像度に比例する
    assert fields.pixel_label.text() == "画像にすると 約 1,602 × 1,200 px"
