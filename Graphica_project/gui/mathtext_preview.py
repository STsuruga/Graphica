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
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel

# プレビュー描画用のFigureの初期サイズ(インチ)。文字列が長くてもここからは
# み出した分は単に描画され続けるだけで実害はない(bbox_inches='tight'相当の
# 処理を自前で行い、実際に描画された範囲だけを後段でクロップするため)。
# ただしキャンバス自体の幅を超える長さのテキストは物理的に切れてしまうため、
# (max_width_px指定時の縮小判定を誤らせないよう)余裕を持った幅にしている。
_CANVAS_SIZE_INCHES = (10.0, 0.6)
_CROP_PADDING_PX = 3

# matplotlibのデフォルトフォント(DejaVu Sans)は日本語グリフを含まないため、
# プレースホルダ文字列("タイトルを入力"等)や日本語タイトルがtofuボックスに
# なってしまう(実機確認: UserWarning: Glyph ... missing from font(s) DejaVu Sans)。
# main.py のAPP_FONT_FAMILIESはQtのフォント名("Yu Gothic UI"等)でmatplotlibの
# font_managerには見つからないため、ここではmatplotlib側で実在が確認できる
# 名前("Yu Gothic"/"Meiryo"、"UI"サフィックス無し)を別途指定する。matplotlib
# 3.6+のフォントフォールバック機構により、リストの先頭から順にグリフを持つ
# フォントが使われる(英数字はDejaVu Sansのまま、日本語だけYu Gothicに自動で
# フォールバックする)。存在しないフォント名はfindfontが黙ってスキップするだけ
# なので、複数OS分の候補を1つのリストに並べておいて害はない
# ("Yu Gothic"はWindows専用、"Hiragino Sans"/"Hiragino Kaku Gothic ProN"は
# macOS専用、"Noto Sans CJK JP"はLinuxでの補完用)。
#
# gui/main_window.py の PLOT_DEFAULT_FONT_FAMILIES(グラフ本体のタイトル/軸
# ラベル/目盛/凡例の既定フォント)もこのリストをそのまま再利用している。
# 元々は本プレビュー機能専用のリストとしてWindows向けフォントのみだったが、
# macOS CIビルド対応の過程で「グラフ本体側にも同じ日本語文字化けの制約が
# ある」既知の限界(下記コメント参照)を解消するために、本プレビューと
# プロット本体の双方でこのリストを共有し、macOS向けフォントを追加した。
#
# 既知の制限: このfamilyフォールバックは「$...$」を含まないプレーンテキストの
# 経路にのみ効く。"$\alpha$ vs 時間" のようにmathtext記法と日本語が同一文字列に
# 混在する場合、mathtextパーサはfamily指定を経由せず独自のフォントセット
# (mathtext.fontset rcParam)で描画するため、日本語部分がtofuボックスになる
# (matplotlibのmathtextエンジンがWindowsの.ttc書体からグリフを正しく解決できない
# ことに起因すると考えられる、freetype/mathtext側の既知の制約)。これは本プレビュー
# 機能固有の問題ではなく、mathtext記法を含むタイトル/軸ラベルも同じ制約を
# 抱えている、アプリ全体の既存の制限。mathtext.fontsetはmatplotlibのrcParams
# (プロセス全体のグローバル状態)であり、ここを変更すると本プレビューだけでなく
# 全ての実プロット描画に影響してしまうため、スコープ外として対応を見送る。
JP_CAPABLE_FONT_FAMILIES = [
    "DejaVu Sans", "Yu Gothic", "Hiragino Sans", "Hiragino Kaku Gothic ProN",
    "Meiryo", "MS Gothic", "Noto Sans CJK JP",
]

# max_width_px指定時、フォントサイズを段階的に縮小して収めようとする下限
# (これ以上小さくすると判読できなくなるため、下限に達したらpixmap自体を
# scaledToWidth()で縮小する最終手段に切り替える)。
_MIN_FONTSIZE = 7


def render_mathtext_to_pixmap(text, color="#000000", fontsize=13, dpi=150, max_width_px=None):
    """
    text(空文字列やプレーンテキストも許容)をmatplotlibでレンダリングし、
    実際に描画された範囲だけをクロップしたQPixmapとして返す。

    mathtext構文が壊れている($の対応が取れていない等)場合は例外を投げず、
    $をエスケープしてプレーンテキストとして描画し直す(あくまでプレビュー
    用途であり、入力を妨げるべきではないため)。

    Args:
        max_width_px (int, optional): 指定すると、描画結果の幅がこれを
            超える場合にフォントサイズを縮小して収めようとする(実機
            フィードバック: 「ここの文字サイズを枠内に収まるようにして」、
            長いmathtext文字列がプレビュー欄の枠からはみ出していた不具合)。
            フォントサイズの下限(_MIN_FONTSIZE)に達してもなお収まらない
            場合は、pixmap自体をscaledToWidth()で縮小する。
    """
    pixmap = _render_once(text, color, fontsize, dpi)
    if max_width_px and pixmap.width() > max_width_px > 0:
        # 文字幅とフォントサイズはおおむね比例するため、まず比例縮小した
        # サイズで一度だけ再描画する(厳密な二分探索まではせず、実用上
        # 十分な近似で済ませる)。
        scaled_fontsize = max(_MIN_FONTSIZE, fontsize * (max_width_px / pixmap.width()) * 0.95)
        pixmap = _render_once(text, color, scaled_fontsize, dpi)
        if pixmap.width() > max_width_px > 0:
            # フォントサイズの下限に達してもまだ収まらない場合の最終手段。
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
                  family=JP_CAPABLE_FONT_FAMILIES, va='center', ha='left')
        canvas.draw()
    except Exception:
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
    # QImageはcropped(numpy配列)のバッファを直接参照しているだけなので、
    # 関数を抜けてcroppedがGCされるとダングリングポインタになる。copy()で
    # QPixmap側に独立したデータを持たせる。
    return QPixmap.fromImage(image.copy())


class FitWidthPixmapLabel(QLabel):
    """
    setPixmap()の代わりにset_natural_pixmap()で「等倍」のpixmapを渡すと、
    ウィジェット自身の実際の幅に収まるよう自動的に縮小して表示するQLabel。

    実機フィードバック(「ここの文字サイズを枠内に収まるようにして」)対応。
    render_mathtext_to_pixmap()呼び出し時点のウィジェット幅(widget.width())
    を頼りに事前にフォントサイズを決めるやり方は、QTabWidgetの非アクティブ
    タブ内のウィジェットやまだ一度もshow()されていないウィジェットでは
    width()が実際のレイアウト確定後の値と一致しない(0や不正確な値になる)
    ことがあり、タブ切り替え直後などに文字が枠からはみ出したまま更新
    されない不具合の原因になっていた。resizeEvent()で改めてフィットし直す
    ことで、実際に幅が確定したタイミング(初回表示・タブ切り替え・ウィンドウ
    リサイズ等)に必ず追従するようにしている。
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
        # ★ self.width()/height()はウィジェットの外枠(QSSのborder/padding
        #   込み)のサイズであり、実際にpixmapを描画できる内側の領域はそれより
        #   狭い。contentsRect()はスタイル(QSSのborder/padding)を考慮した
        #   実際の描画可能領域を返すため、こちらを基準に合わせないと、
        #   ぴったり合わせたつもりのpixmapの端がpadding/borderの分だけ
        #   欠けて見えてしまう(実機で発覚: 縮小後のpixmapの右端が
        #   わずかに切れていた)。
        #   ★ 実機フィードバック(続報): 幅だけを見て縮小するかどうかを
        #   判定していたため、"タイトルを入力"等の短いプレースホルダ
        #   (横には十分収まるが、天地(高さ)がラベルの高さより大きい)は
        #   幅方向の縮小条件に一度も引っかからず、縦方向にはみ出したまま
        #   放置されていた(実際に入力したテキストは、mathtext記法込みで
        #   横幅が長くなりやすく、その際は縮小のついでに高さも縮んでいた
        #   ため気づかれなかった)。幅・高さ両方の超過を見て、はみ出して
        #   いる方に合わせてアスペクト比を保ったまま縮小する。
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
