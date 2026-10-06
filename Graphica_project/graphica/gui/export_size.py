"""書き出しの大きさ(幅・高さ・単位・解像度)の換算と、描ける大きさかの確認。書き出しのダイアログとプレビューのドックで共有する。

単位はコンボの値(日本語の元の文字)で見分ける。
"""
from PySide6.QtWidgets import QMessageBox

from graphica.core.i18n import tr
from graphica.gui import notify

# 単位を切り替えたときの小数の桁と、入力できる最小値
UNIT_DECIMALS = {'px': 0, 'in': 2, 'cm': 2, 'mm': 1}
UNIT_MINIMUM = {'px': 1.0, 'in': 0.01, 'cm': 0.01, 'mm': 0.1}

# matplotlib(Agg)が描ける1辺の上限(2^16 未満)
MAX_RASTER_SIDE_PX = 65535
# これを超える画素数は、描くのに時間とメモリ(1画素 4 バイト)がかかるので確かめてから描く
LARGE_OUTPUT_PIXELS = 100_000_000
# プレビューは欄の大きさのこの倍の画素で描けば、縮めて見せても粗くならない
PREVIEW_OVERSAMPLE = 2.0
# これより下げると小さな文字が描けない(FreeType が文字の大きさ 1 画素未満を拒む。4pt の文字で 10 dpi 程度が下限)
MIN_PREVIEW_DPI = 20.0
# 下限の解像度でもこれを超える図は、プレビューを描かない(描いても文字が見えず、時間とメモリだけかかる)
MAX_PREVIEW_PIXELS = 4000 * 4000


def unit_key(unit):
    """コンボの値 -> 'px' / 'in' / 'cm' / 'mm'。分からなければ None。"""
    unit = unit or ''
    if "インチ" in unit:
        return 'in'
    if "ミリメートル" in unit:
        return 'mm'
    if "センチメートル" in unit:
        return 'cm'
    if "ピクセル" in unit:
        return 'px'
    return None


def _inches_per_unit(key, dpi):
    return {'in': 1.0, 'mm': 1 / 25.4, 'cm': 1 / 2.54, 'px': 1 / dpi}.get(key)


def size_in_inches(width, height, unit, dpi):
    """幅と高さをインチにする。分からない単位なら 8 × 6。"""
    factor = _inches_per_unit(unit_key(unit), dpi)
    if factor is None:
        return 8, 6
    return width * factor, height * factor


def convert_length(value, from_unit, to_unit, dpi):
    """同じ長さを別の単位で表した値。どちらかの単位が分からなければそのまま。"""
    source = _inches_per_unit(unit_key(from_unit), dpi)
    target = _inches_per_unit(unit_key(to_unit), dpi)
    if source is None or target is None:
        return value
    return value * source / target


def output_pixel_size(width_in, height_in, dpi):
    """ラスタで書き出したときの画素数(余白を詰める前のおおよその大きさ)。"""
    return round(width_in * dpi), round(height_in * dpi)


def preview_dpi(width_in, height_in, dpi, target_width_px, target_height_px):
    """プレビューを描く解像度。欄に合う画素数まで下げ、書き出しの解像度は超えない。大きすぎて描かないなら None。

    文字や線の太さはポイント単位なので、解像度を下げても見た目の比率は変わらない。
    """
    if width_in <= 0 or height_in <= 0:
        return dpi
    fit = min(target_width_px * PREVIEW_OVERSAMPLE / width_in, target_height_px * PREVIEW_OVERSAMPLE / height_in)
    chosen = min(float(dpi), max(MIN_PREVIEW_DPI, fit))
    width_px, height_px = output_pixel_size(width_in, height_in, chosen)
    if width_px * height_px > MAX_PREVIEW_PIXELS:
        return None
    return chosen


def preview_too_large_text(width_in, height_in, dpi):
    width_px, height_px = output_pixel_size(width_in, height_in, dpi)
    return tr("図が大きすぎるためプレビューを表示しません\n(画像にすると 約 {width} × {height} px)").format(
        width=f"{width_px:,}", height=f"{height_px:,}")


def confirm_output_size(parent, width_in, height_in, dpi):
    """描ける大きさなら True。1辺が上限を超えるなら知らせて False、とても大きいなら確かめる。"""
    width_px, height_px = output_pixel_size(width_in, height_in, dpi)
    if max(width_px, height_px) > MAX_RASTER_SIDE_PX:
        notify.warning(
            parent, tr("画像が大きすぎます"),
            tr("{width} × {height} px になり、1辺が {limit} px を超えるので描けません。\n"
               "幅・高さか解像度を小さくしてください。").format(
                width=f"{width_px:,}", height=f"{height_px:,}", limit=f"{MAX_RASTER_SIDE_PX:,}"))
        return False
    if width_px * height_px > LARGE_OUTPUT_PIXELS:
        reply = notify.question(
            parent, tr("大きな画像"),
            tr("{width} × {height} px(約 {megapixels:,.0f} 万画素)になります。\n"
               "時間がかかったり、メモリが足りなくなったりするおそれがあります。続けますか？").format(
                # 日本語は万画素、英語は百万画素で数える。format は使わない名前を無視する
                width=f"{width_px:,}", height=f"{height_px:,}",
                megapixels=width_px * height_px / 10_000, megapixels_m=width_px * height_px / 1_000_000),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes
    return True


class ExportSizeFields:
    """幅・高さ・単位・解像度の欄をまとめて扱う。単位を切り替えたら同じ大きさになるよう数字を換算し、出力の画素数を見せる。

    単位のコンボにほかの処理(プレビューの描き直しなど)をつなぐなら、これを作った後につなぐ(換算が先に済むように)。
    """

    def __init__(self, width_spinbox, height_spinbox, unit_combo, dpi_spinbox, pixel_label=None):
        self.width_spinbox = width_spinbox
        self.height_spinbox = height_spinbox
        self.unit_combo = unit_combo
        self.dpi_spinbox = dpi_spinbox
        self.pixel_label = pixel_label
        self._unit = unit_combo.currentData()
        self._apply_unit_format(self._unit)

        unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        if pixel_label is not None:
            for spin_box in (width_spinbox, height_spinbox, dpi_spinbox):
                spin_box.valueChanged.connect(self.update_pixel_label)
            unit_combo.currentIndexChanged.connect(self.update_pixel_label)
            self.update_pixel_label()

    def size_in_inches(self):
        return size_in_inches(self.width_spinbox.value(), self.height_spinbox.value(),
                              self.unit_combo.currentData(), self.dpi_spinbox.value())

    def _apply_unit_format(self, unit):
        key = unit_key(unit)
        if key is None:
            return
        for spin_box in (self.width_spinbox, self.height_spinbox):
            spin_box.setDecimals(UNIT_DECIMALS[key])
            spin_box.setMinimum(UNIT_MINIMUM[key])

    def _on_unit_changed(self, _index):
        new_unit = self.unit_combo.currentData()
        old_unit, self._unit = self._unit, new_unit
        dpi = self.dpi_spinbox.value()
        spin_boxes = (self.width_spinbox, self.height_spinbox)
        # 桁を変えると今の値が丸められるので、先に両方を読んでおく
        values = [convert_length(spin_box.value(), old_unit, new_unit, dpi) for spin_box in spin_boxes]
        # 換算の途中の値でプレビューが描き直されないよう、欄の通知を止める(描き直しは単位のコンボの通知で1回)
        blocked = [spin_box.blockSignals(True) for spin_box in spin_boxes]
        try:
            self._apply_unit_format(new_unit)
            for spin_box, value in zip(spin_boxes, values):
                spin_box.setValue(value)
        finally:
            for spin_box, was_blocked in zip(spin_boxes, blocked):
                spin_box.blockSignals(was_blocked)

    def update_pixel_label(self, *_args):
        width_in, height_in = self.size_in_inches()
        width_px, height_px = output_pixel_size(width_in, height_in, self.dpi_spinbox.value())
        self.pixel_label.setText(tr("画像にすると 約 {width} × {height} px").format(
            width=f"{width_px:,}", height=f"{height_px:,}"))
