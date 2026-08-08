# gui/mathtext_preview.py
"""
タイトル/軸ラベル欄の生テキスト(matplotlibのmathtext記法、例:
"$\\alpha$ vs time")を、実際に描画した見た目のQPixmapへ変換する共通ヘルパー。

実機フィードバック(項目H-2-4追加分: 「画像のテキストボックスではmathtextを
翻訳した形式をプレビューしといて」)を受けて追加した。プロット本体のタイトル/
軸ラベル描画(gui/canvas.py)と同じmatplotlibのテキストレンダリングを流用する
ことで、実際にグラフへ反映されたときと同じ見た目を確認できるようにしている。
"""
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtGui import QImage, QPixmap

# プレビュー描画用のFigureの初期サイズ(インチ)。文字列が長くてもここからは
# み出した分は単に描画され続けるだけで実害はない(bbox_inches='tight'相当の
# 処理を自前で行い、実際に描画された範囲だけを後段でクロップするため)。
_CANVAS_SIZE_INCHES = (6.0, 0.6)
_CROP_PADDING_PX = 3

# matplotlibのデフォルトフォント(DejaVu Sans)は日本語グリフを含まないため、
# プレースホルダ文字列("タイトルを入力"等)や日本語タイトルがtofuボックスに
# なってしまう(実機確認: UserWarning: Glyph ... missing from font(s) DejaVu Sans)。
# main.py のAPP_FONT_FAMILIESはQtのフォント名("Yu Gothic UI"等)でmatplotlibの
# font_managerには見つからないため、ここではmatplotlib側で実在が確認できる
# 名前("Yu Gothic"/"Meiryo"、"UI"サフィックス無し)を別途指定する。matplotlib
# 3.6+のフォントフォールバック機構により、リストの先頭から順にグリフを持つ
# フォントが使われる(英数字はDejaVu Sansのまま、日本語だけYu Gothicに自動で
# フォールバックする)。
#
# 既知の制限: このfamilyフォールバックは「$...$」を含まないプレーンテキストの
# 経路にのみ効く。"$\alpha$ vs 時間" のようにmathtext記法と日本語が同一文字列に
# 混在する場合、mathtextパーサはfamily指定を経由せず独自のフォントセット
# (mathtext.fontset rcParam)で描画するため、日本語部分がtofuボックスになる
# (matplotlibのmathtextエンジンがWindowsの.ttc書体からグリフを正しく解決できない
# ことに起因すると考えられる、freetype/mathtext側の既知の制約)。これは本プレビュー
# 機能固有の問題ではなく、実際のプロット本体(gui/canvas.py の ax.set_title 等、
# axis_label_fontが未設定の場合)も同じ制約を抱えている、アプリ全体の既存の制限。
# mathtext.fontsetはmatplotlibのrcParams(プロセス全体のグローバル状態)であり、
# ここを変更すると本プレビューだけでなく全ての実プロット描画に影響してしまうため、
# スコープ外として対応を見送る。
_JP_CAPABLE_FONT_FAMILIES = ["DejaVu Sans", "Yu Gothic", "Meiryo", "MS Gothic"]


def render_mathtext_to_pixmap(text, color="#000000", fontsize=13, dpi=150):
    """
    text(空文字列やプレーンテキストも許容)をmatplotlibでレンダリングし、
    実際に描画された範囲だけをクロップしたQPixmapとして返す。

    mathtext構文が壊れている($の対応が取れていない等)場合は例外を投げず、
    $をエスケープしてプレーンテキストとして描画し直す(あくまでプレビュー
    用途であり、入力を妨げるべきではないため)。
    """
    fig = Figure(figsize=_CANVAS_SIZE_INCHES, dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    fig.patch.set_alpha(0.0)
    display_text = text if text else " "
    try:
        fig.text(0.01, 0.5, display_text, fontsize=fontsize, color=color,
                  family=_JP_CAPABLE_FONT_FAMILIES, va='center', ha='left')
        canvas.draw()
    except Exception:
        fig = Figure(figsize=_CANVAS_SIZE_INCHES, dpi=dpi)
        canvas = FigureCanvasAgg(fig)
        fig.patch.set_alpha(0.0)
        fig.text(0.01, 0.5, display_text.replace("$", "\\$"), fontsize=fontsize,
                  color=color, family=_JP_CAPABLE_FONT_FAMILIES, va='center', ha='left')
        canvas.draw()

    buf = np.asarray(canvas.buffer_rgba())
    cropped = _crop_to_content(buf)
    cropped = np.ascontiguousarray(cropped)
    height, width, _ = cropped.shape
    image = QImage(cropped.data, width, height, width * 4, QImage.Format.Format_RGBA8888)
    # QImageはcropped(numpy配列)のバッファを直接参照しているだけなので、
    # 関数を抜けてcroppedがGCされるとダングリングポインタになる。copy()で
    # QPixmap側に独立したデータを持たせる。
    return QPixmap.fromImage(image.copy())


def _crop_to_content(rgba_array):
    """アルファチャンネルが立っているピクセルの外接矩形(+小さな余白)へクロップする。"""
    alpha = rgba_array[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not rows.any() or not cols.any():
        return rgba_array[:1, :1]

    row_indices = np.where(rows)[0]
    col_indices = np.where(cols)[0]
    row_min = max(0, row_indices[0] - _CROP_PADDING_PX)
    row_max = min(rgba_array.shape[0] - 1, row_indices[-1] + _CROP_PADDING_PX)
    col_min = max(0, col_indices[0] - _CROP_PADDING_PX)
    col_max = min(rgba_array.shape[1] - 1, col_indices[-1] + _CROP_PADDING_PX)
    return rgba_array[row_min:row_max + 1, col_min:col_max + 1]
