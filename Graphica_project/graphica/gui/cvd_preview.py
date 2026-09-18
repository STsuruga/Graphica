# gui/cvd_preview.py
"""
QImageに対する色覚シミュレーション変換(項目140、C-803)。
色空間の変換自体はcore/cvd_simulation.pyの純粋関数に委譲し、ここでは
QImageとnumpy配列の相互変換だけを担当する(Qt依存部分をcoreパッケージから
切り離すため、core/dataset.py等と同じ「coreはQtに依存しない」方針を踏襲)。
"""
import numpy as np
from PySide6.QtGui import QImage

from core.cvd_simulation import simulate_rgb_array


def simulate_qimage(image, cvd_type):
    """
    QImageの各ピクセルにCVDシミュレーションを適用した新しいQImageを返す
    (アルファチャンネルは変更しない、元のimageも変更しない)。
    """
    src = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = src.width(), src.height()
    # ★ 行間パディングを考慮し、bytesPerLine()幅で読んでからwidth*4に切り詰める
    #   (tests/test_gui_style_regression.pyの_qimage_to_arrayと同じ理由)。
    bytes_per_line = src.bytesPerLine()
    buf = bytes(src.constBits())
    arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, bytes_per_line))
    arr = arr[:, : width * 4].reshape((height, width, 4)).copy()

    rgb = arr[:, :, :3].astype(np.float64)
    simulated = np.clip(simulate_rgb_array(rgb, cvd_type), 0, 255).astype(np.uint8)
    arr[:, :, :3] = simulated

    result = QImage(arr.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888)
    return result.copy()  # arrのバッファの寿命から切り離す(tobytes()のコピーを保持させる)
