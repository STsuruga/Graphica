"""色覚のシミュレーション。GUI には依存しない。

sRGB に直接掛ける近似の行列(Brettel / Viénot を簡略化したもの)で、プレビュー用。各行の和が 1 なので白・黒・灰は変わらない。
"""
import numpy as np

# 1型(赤)・2型(緑)・3型(青)
CVD_MATRICES = {
    'protanopia': np.array([
        [0.567, 0.433, 0.000],
        [0.558, 0.442, 0.000],
        [0.000, 0.242, 0.758],
    ]),
    'deuteranopia': np.array([
        [0.625, 0.375, 0.000],
        [0.700, 0.300, 0.000],
        [0.000, 0.300, 0.700],
    ]),
    'tritanopia': np.array([
        [0.950, 0.050, 0.000],
        [0.000, 0.433, 0.567],
        [0.000, 0.475, 0.525],
    ]),
}

CVD_TYPE_LABELS = {
    'protanopia': '1型(P型、赤色覚異常)',
    'deuteranopia': '2型(D型、緑色覚異常)',
    'tritanopia': '3型(T型、青色覚異常)',
}


def simulate_rgb_array(rgb_array: np.ndarray, cvd_type: str) -> np.ndarray:
    """形が (..., 3) の RGB に行列を掛ける。0〜255 のままでよい(スケールは保たれる)。クリップと型の変換は呼び出し側。"""
    if cvd_type not in CVD_MATRICES:
        raise ValueError(f"未知の色覚タイプです: {cvd_type}")
    matrix = CVD_MATRICES[cvd_type]
    original_shape = rgb_array.shape
    flat = np.asarray(rgb_array, dtype=np.float64).reshape(-1, 3)
    simulated = flat @ matrix.T
    return simulated.reshape(original_shape)


def simulate_hex_color(hex_color: str, cvd_type: str) -> str:
    """#RRGGBB を1つ変換する(画像を介さない単色用)。"""
    hex_color = hex_color.lstrip('#')
    rgb = np.array([int(hex_color[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)
    simulated = np.clip(simulate_rgb_array(rgb, cvd_type), 0, 255).astype(np.uint8)
    return '#' + ''.join(f'{v:02x}' for v in simulated)
