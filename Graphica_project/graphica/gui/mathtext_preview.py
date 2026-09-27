"""タイトルと軸ラベルのテキスト(mathtext を含む)を、グラフと同じ matplotlib の描画で QPixmap にする。"""
import re

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel

# 描いた範囲だけを後で切り取るので大きめでよい。ただし幅を超えた文字は切れ、縮小の判定を誤るので余裕を持たせる
_CANVAS_SIZE_INCHES = (10.0, 0.6)
_CROP_PADDING_PX = 3

# 日本語を描けるフォントの候補。matplotlib の既定(DejaVu Sans)には日本語が無い。Qt の UI 用の名前
# ("Yu Gothic UI")は matplotlib では見つからないので使わない。先頭から順にグリフのあるフォントが使われ、
# 無い名前は飛ばされるので OS ごとの候補を並べる(Yu Gothic などは Windows、Hiragino は macOS、Noto は Linux)。
# グラフ本体の既定フォント(main_window の PLOT_DEFAULT_FONT_FAMILIES)と注釈(rendering/annotations.py)もこれを使う。
# $...$ を含む文字列の数式の外の文字は、候補の先頭 1 つで描かれる(families_for_text)。mathtext.fontset は
# プロセス全体の設定で、変えると全部の描画に効くので触らない。
JP_CAPABLE_FONT_FAMILIES = [
    "DejaVu Sans", "Yu Gothic", "Hiragino Sans", "Hiragino Kaku Gothic ProN",
    "Meiryo", "MS Gothic", "Noto Sans CJK JP",
]

_CJK_PATTERN = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]")
# 数式の外の文字を描ける日本語の字体(DejaVu Sans は日本語を持たない)
_JAPANESE_FONT_FAMILIES = [f for f in JP_CAPABLE_FONT_FAMILIES if f != "DejaVu Sans"]


def _has_mathtext(text):
    """エスケープしていない $ が 2 つ以上あれば、matplotlib はその文字列を数式として描く。"""
    return len(re.findall(r"(?<!\\)\$", text)) >= 2


def families_for_text(text, families):
    """数式を含む文字列では、matplotlib は数式の外の文字を字体の候補の先頭 1 つだけで描く(ほかの候補に頼らない)。
    日本語と数式を混ぜたときだけ、日本語の字体を先頭に置いて □ にならないようにする。それ以外は families のまま。"""
    if not text or not _CJK_PATTERN.search(text) or not _has_mathtext(text):
        return families
    if isinstance(families, str):
        families = [families]
    families = list(families or [])
    if families and families[0].lower() in {f.lower() for f in _JAPANESE_FONT_FAMILIES}:
        return families
    return _JAPANESE_FONT_FAMILIES + [f for f in families if f not in _JAPANESE_FONT_FAMILIES]


def families_for_texts(texts, families):
    """凡例のように 1 つの字体で複数の文字列を描くとき。どれかが日本語と数式を混ぜていれば、その並びにする。"""
    for text in texts:
        adjusted = families_for_text(text, families)
        if adjusted is not families:
            return adjusted
    return families


def font_kwargs_for_text(text, font_kwargs):
    """ax.set_title(text, **font_kwargs) などに渡す字体の辞書を、families_for_text() に合わせて返す(元は変えない)。"""
    family = font_kwargs.get('family') if font_kwargs else None
    adjusted = families_for_text(text, family)
    if adjusted is family:
        return font_kwargs
    return dict(font_kwargs, family=adjusted)


# これより小さくすると読めないので、そこからは pixmap ごと縮める
_MIN_FONTSIZE = 7


def render_mathtext_to_pixmap(text, color="#000000", fontsize=13, dpi=150, max_width_px=None):
    """描いた範囲だけを切り取った QPixmap。

    mathtext の構文が壊れていれば、$ をエスケープして文字のまま描く(入力の邪魔をしない)。
    max_width_px を超えればフォントを小さくし、下限でも収まらなければ pixmap を縮める。
    """
    pixmap = _render_once(text, color, fontsize, dpi)
    if max_width_px and pixmap.width() > max_width_px > 0:
        # 幅はフォントサイズにほぼ比例するので、比例で縮めて1回だけ描き直す
        scaled_fontsize = max(_MIN_FONTSIZE, fontsize * (max_width_px / pixmap.width()) * 0.95)
        pixmap = _render_once(text, color, scaled_fontsize, dpi)
        if pixmap.width() > max_width_px > 0:
            pixmap = pixmap.scaledToWidth(
                max_width_px, Qt.TransformationMode.SmoothTransformation
            )
    return pixmap


def _render_once(text, color, fontsize, dpi):
    fig = Figure(figsize=_CANVAS_SIZE_INCHES, dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    fig.patch.set_alpha(0.0)
    display_text = text if text else " "
    try:
        fig.text(0.01, 0.5, display_text, fontsize=fontsize, color=color,
                  family=families_for_text(display_text, JP_CAPABLE_FONT_FAMILIES), va='center', ha='left')
        canvas.draw()
    except ValueError:  # mathtext の構文エラー。$ をそのまま文字として描き直す
        fig = Figure(figsize=_CANVAS_SIZE_INCHES, dpi=dpi)
        canvas = FigureCanvasAgg(fig)
        fig.patch.set_alpha(0.0)
        fig.text(0.01, 0.5, display_text.replace("$", "\\$"), fontsize=fontsize,
                  color=color, family=JP_CAPABLE_FONT_FAMILIES, va='center', ha='left')
        canvas.draw()

    buf = np.asarray(canvas.buffer_rgba())
    cropped = _crop_to_content(buf)
    cropped = np.ascontiguousarray(cropped)
    height, width, _ = cropped.shape
    image = QImage(cropped.data, width, height, width * 4, QImage.Format.Format_RGBA8888)
    # QImage は cropped の配列を参照しているだけなので、関数を抜けると宙に浮く。copy() する
    return QPixmap.fromImage(image.copy())


class FitWidthPixmapLabel(QLabel):
    """set_natural_pixmap() で渡した等倍の pixmap を、ラベルの幅に収まるよう縮めて出す。

    描く時点の width() は、非表示のタブなどでは確定していないので、resizeEvent で合わせ直す。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._natural_pixmap = None

    def set_natural_pixmap(self, pixmap):
        self._natural_pixmap = pixmap
        self._apply_fitted_pixmap()

    def _apply_fitted_pixmap(self):
        if self._natural_pixmap is None or self._natural_pixmap.isNull():
            return
        # QSS の枠と余白を除いた contentsRect() に合わせる(でないと端が欠ける)。
        # 幅だけでなく高さもはみ出していれば、はみ出した方に合わせて縮める。
        available_rect = self.contentsRect()
        available_width = available_rect.width()
        available_height = available_rect.height()
        natural = self._natural_pixmap
        if (available_width > 0 and natural.width() > available_width) or (
            available_height > 0 and natural.height() > available_height
        ):
            fitted = natural.scaled(
                max(available_width, 1), max(available_height, 1),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
        else:
            fitted = natural
        super().setPixmap(fitted)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_fitted_pixmap()


def _crop_to_content(rgba_array):
    """不透明なピクセルの外接矩形(と少しの余白)で切り取る。"""
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
