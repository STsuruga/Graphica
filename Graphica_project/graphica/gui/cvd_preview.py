"""QImage と numpy 配列の変換(色の変換は Qt に依存しない core/cvd_simulation.py)。"""
import numpy as np
from PySide6.QtGui import QImage

from graphica.core.cvd_simulation import simulate_rgb_array


def simulate_qimage(image, cvd_type):
    """変換した新しい QImage(アルファと元の image は変えない)。"""
    src = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = src.width(), src.height()
    # 行の末尾に詰め物があるので、bytesPerLine() の幅で読んでから width*4 に切り詰める
    bytes_per_line = src.bytesPerLine()
    buf = bytes(src.constBits())
    arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, bytes_per_line))
    arr = arr[:, : width * 4].reshape((height, width, 4)).copy()

    rgb = arr[:, :, :3].astype(np.float64)
    simulated = np.clip(simulate_rgb_array(rgb, cvd_type), 0, 255).astype(np.uint8)
    arr[:, :, :3] = simulated

    result = QImage(arr.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888)
    return result.copy()  # arr のバッファの寿命から切り離す
