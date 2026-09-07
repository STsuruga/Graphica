# core/cvd_simulation.py
"""
色覚多様性対応・CUDシミュレータ(項目140、C-803)。

GUIに一切依存しない純粋関数のみを置く(gui/dialogs.pyのCVDSimulationDialogが
描画済みのウィンドウのスクリーンショット(QImage)にこの変換を適用する想定)。

シミュレーション行列は、Web上の色覚シミュレーションツールで広く使われている
sRGB直接変換の近似行列(Brettel/Viénotのアルゴリズムを単純化したもの)を採用した。
線形RGB空間での厳密な変換ではなく、あくまでプレビュー用途の近似である
(各行の合計が1になる正規化された係数のため、白/黒/グレーは変化しない)。
"""
import numpy as np

# 1型(P型、赤色覚異常)・2型(D型、緑色覚異常)・3型(T型、青色覚異常)。
# 各行の合計が1になっている(sRGB値に対して直接乗算できる、簡易近似)。
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


def simulate_rgb_array(rgb_array, cvd_type):
    """
    RGB値の配列にCVDシミュレーション行列を適用する。

    Args:
        rgb_array (np.ndarray): 形状(..., 3)、0〜255のuint8またはfloat配列
            (0〜1に正規化されている必要はない、行列の各行の合計が1のため
            スケールをそのまま保てる)。
        cvd_type (str): CVD_MATRICESのキーのいずれか。

    Returns:
        np.ndarray: 入力と同じ形状・同じスケールのfloat配列(0〜255相当)。
            呼び出し側で必要ならクリップ+dtype変換すること。

    Raises:
        ValueError: cvd_typeが未知の場合。
    """
    if cvd_type not in CVD_MATRICES:
        raise ValueError(f"未知の色覚タイプです: {cvd_type}")
    matrix = CVD_MATRICES[cvd_type]
    original_shape = rgb_array.shape
    flat = np.asarray(rgb_array, dtype=np.float64).reshape(-1, 3)
    simulated = flat @ matrix.T
    return simulated.reshape(original_shape)


def simulate_hex_color(hex_color, cvd_type):
    """1つの#RRGGBB文字列をシミュレーションし、#RRGGBB文字列で返す(パレット
    プレビュー等、画像を介さず単色を変換したい場合に使う)。"""
    hex_color = hex_color.lstrip('#')
    rgb = np.array([int(hex_color[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)
    simulated = np.clip(simulate_rgb_array(rgb, cvd_type), 0, 255).astype(np.uint8)
    return '#' + ''.join(f'{v:02x}' for v in simulated)
