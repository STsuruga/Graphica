# gui/theme.py
"""
アプリ全体 (Qt UI) のダークモード切り替え、およびフラット/ミニマルな
見た目 (QSS) の適用を担当するモジュール。
ベースは QPalette + Fusion スタイルの標準的な手法だが、それに加えて
QSS (Qtスタイルシート) でツールバー・ボタン・入力欄・リスト等の見た目を
角丸/フラットに統一し、よりモダンな印象にしている。
"""
import os
import re
import tempfile

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QProxyStyle, QStyle, QStyleFactory

from gui.icon_utils import icon as _svg_icon

# 起動時の元のパレット/スタイル名を保持し、ライトモードへの復帰に使う
_original_palette = None
_original_style_name = None
_wheel_value_change_disabled = False
_current_proxy_style = None  # QApplication.setStyle()に渡したオブジェクトへの参照を保持
_current_tokens = None  # 現在適用中のLIGHT_TOKENS/DARK_TOKENS(項目H-2-2:
                         # QSSだけでは表現できない選択ハイライトをカスタム
                         # デリゲートで描く際に、ライト/ダーク現在値を参照するため)
_last_applied_dark = None  # 直近にQApplicationへ実際に適用した dark 値(起動高速化:
                            # 同じ値でのapply_theme()再呼び出し時、高コストな
                            # setPalette()/setStyleSheet()の再実行を省略するため)

# データセットリストの角丸(選択ハイライト用デリゲートが、リスト自体の角丸
# (下のQTreeWidget, QListWidget, QTableWidget規則のborder-radius)と揃える
# ために参照する値。QSS文字列側の値を変更したら、こちらも合わせて変更すること。
DATASET_LIST_ITEM_RADIUS = 8

# スピンボックスの上下矢印アイコンのキャッシュ先。
# ★ QSpinBox::up-button/down-buttonにQSSで何かプロパティを指定すると
#   ウィジェット自体もQSSで角丸枠にしている都合上(QLineEdit等と共有の
#   入力欄スタイル)、Qtの内部実装(QStyleSheetStyle)がCC_SpinBoxの描画を
#   丸ごと引き取ってしまい、QProxyStyle側でdrawPrimitive/drawComplexControlを
#   オーバーライドしても矢印の描画に一貫して反映されないことを検証の上で確認した
#   (呼ばれたり呼ばれなかったりする再現性の低い挙動だった)。
#   一方 QSS の `::up-arrow`/`::down-arrow` に `image: url(...)` で
#   実ファイルの矢印画像を指定する方式は確実に反映される。このため、
#   矢印だけは小さなPNGとして生成しキャッシュし、QSSから参照する。
_ARROW_ICON_CACHE_DIR = os.path.join(tempfile.gettempdir(), "graphica_theme_icons")


def _spinbox_arrow_icon_url(direction: str, color: str) -> str:
    """
    上向き/下向きの三角矢印PNGを(未生成なら)描画してキャッシュし、
    QSSの `url(...)` にそのまま埋め込める形式のパス文字列を返す。
    """
    os.makedirs(_ARROW_ICON_CACHE_DIR, exist_ok=True)
    safe_color = color.lstrip("#")
    # ★ ファイル名にサイズを含めることで、実機フィードバックを受けて矢印を
    #   大きくした際(項目H-2-4)のような将来の寸法変更時に、キャッシュ
    #   ディレクトリに残った旧サイズのPNGを誤って使い回さないようにしている。
    size = 14
    filename = f"spin_arrow_{direction}_{safe_color}_{size}.png"
    path = os.path.join(_ARROW_ICON_CACHE_DIR, filename)

    if not os.path.exists(path):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))

        cx, cy = size / 2, size / 2
        aw, ah = 4.4, 3.3
        arrow_path = QPainterPath()
        if direction == "up":
            arrow_path.moveTo(cx - aw, cy + ah * 0.5)
            arrow_path.lineTo(cx + aw, cy + ah * 0.5)
            arrow_path.lineTo(cx, cy - ah * 0.5)
        else:
            arrow_path.moveTo(cx - aw, cy - ah * 0.5)
            arrow_path.lineTo(cx + aw, cy - ah * 0.5)
            arrow_path.lineTo(cx, cy + ah * 0.5)
        arrow_path.closeSubpath()
        painter.drawPath(arrow_path)
        painter.end()
        pixmap.save(path)

    # QSSのurl()はWindowsの円記号区切りパスを解釈できないため、
    # スラッシュ区切りに変換する。
    return path.replace(os.sep, "/")

# フラット/ミニマルテーマの配色トークン(項目H-1: 唯一の定義箇所)。
# チェックリスト(ロードマップ)アーティファクトで使ったものと近い、
# ニュートラルグレー+ティール系アクセントの配色に揃えている。
# 公開名(LIGHT_TOKENS/DARK_TOKENS)はロードマップH-1の完了条件に合わせたもの。
# 現状これらを上書きするユーザー設定(QSettings)は存在しない
# (docs/gui_style_audit.md 6節: 「カスタムカラーパレット」機能はデータセットの
# 線色サイクルであり、このUIテーマのアクセントカラーとは無関係)。
LIGHT_TOKENS = {
    # ★ 実機フィードバック: 「背景色が若干黄色っぽい」との指摘を受け、
    # bg/surface_2を寒色寄りのニュートラルグレーに変更した(旧値:
    # bg=#F7F7F5, surface_2=#EFF1EF。両方ともG成分がわずかに高く、
    # 暖色/黄み寄りだった)。3案(ニュートラル/寒色寄り/濃いめ寒色)を提示し、
    # 「B: 寒色寄りグレー」が選ばれた。
    "bg": "#F6F7F9", "surface": "#FFFFFF", "surface_2": "#EEF0F3",
    "border": "#DFE2E1", "border_strong": "#C9CDCB",
    "text_primary": "#1B1F1E", "text_secondary": "#5B6462", "text_muted": "#8B938F",
    "accent": "#1F6F78", "accent_soft": "#E4F0EF", "accent_text": "#FFFFFF",
    # データセットリストの選択ハイライト専用(項目H-2-2)。アプリ全体のアクセント
    # 色(ティール系)とは別に、実機フィードバックで明示的に要望された「青」を
    # 使う専用トークン(他の淡いリスト/テーブルが使うaccent_softとは意図的に
    # 別トークンにしている)。accent_softは不透明な淡色だが、こちらは実際に
    # rgbaの透過を持たせている(以前の「はっきりしたアクセント色の塗りつぶし」
    # という意図的な差別化が濃すぎると判断され、この色に変更した経緯がある)。
    "selection_highlight": "rgba(37, 99, 235, 0.12)",
    # selection_highlightと同じ青相のopaque版(項目H-2-4、実機フィードバック:
    # 「フォーカス時の色が緑のまま」「チェックボックスの塗りつぶしの色も」
    # 「タブの選択色も」)。selection_highlightは枠線・チェックボックスの
    # 塗りつぶしのような「完全に不透明であるべき」用途には透過が邪魔になるため、
    # 同じ色相のopaque版を別トークンとして用意した。
    "selection_accent": "#2563EB",
    # 欠損値(NaN)セルの可視化(項目C-201)。データセットリストの選択ハイライト
    # (青系)・アプリ全体のアクセント(ティール系)のどちらとも被らない、
    # 「注意を引くが警告/エラーではない」ニュートラルな琥珀系の淡色。
    # 将来のC-210(テーブルの条件付き書式)でも同系統の用途に再利用できるよう、
    # 単発のハードコード値ではなくトークンとして定義する。
    "warning_soft": "#FDF1D8",
}
DARK_TOKENS = {
    "bg": "#14171A", "surface": "#1B1F22", "surface_2": "#21262A",
    "border": "#2C3236", "border_strong": "#3A4147",
    "text_primary": "#EDEFEF", "text_secondary": "#A6AEB2", "text_muted": "#6E777B",
    "accent": "#5FB6BE", "accent_soft": "rgba(95, 182, 190, 0.16)", "accent_text": "#0E1113",
    "selection_highlight": "rgba(59, 130, 246, 0.22)",
    "selection_accent": "#3B82F6",
    "warning_soft": "rgba(250, 204, 21, 0.16)",
}

_FLAT_QSS_TEMPLATE = """
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {text_primary};
    /* ★ 実機フィードバック: テキスト選択やポップアップの選択色が(アプリ全体の
       ティール系アクセントのままだと)緑っぽく見えるとの指摘を受け、データ
       セットリスト(H-2-2)で使っている薄い青のselection_highlightに揃えた。
       ボタンのhover/pressedやフォーカス枠など「選択」以外のアクセント表現は
       従来通りaccent(ティール系)のまま変えていない。 */
    selection-background-color: {selection_highlight};
    selection-color: {text_primary};
}}
QToolTip {{
    background: {surface};
    color: {text_primary};
    border: 1px solid {border_strong};
    padding: 4px 6px;
    border-radius: 4px;
}}

/* --- メニューバー / メニュー --- */
QMenuBar {{
    background: {surface};
    border-bottom: 1px solid {border};
    padding: 2px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {selection_highlight};
    color: {text_primary};
}}
QMenu {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {selection_highlight};
    color: {text_primary};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 8px;
}}

/* --- 操作ボタン行のグループ区切り(項目70) --- */
QFrame#button_row_separator {{
    background: {border};
    max-width: 1px;
    border: none;
    margin: 2px 4px;
}}

/* --- データセットリスト直下のミニ統計(項目69) --- */
QLabel#dataset_mini_stats_label {{
    color: {text_muted};
    font-size: 11.5px;
    padding: 2px 4px;
}}

/* --- キャンバス周り(項目72): プロット領域を1枚のカードとして視覚的に区切る ---
   ★ 実機フィードバック: 「プロットパネルの枠線も消して」。角丸の背景カード
   としての体裁(background/border-radius)は維持しつつ、枠線だけ削除する。 */
QWidget#plot_container {{
    background: {surface};
    border-radius: 8px;
}}
QFrame#canvas_separator {{
    background: {border};
    max-height: 1px;
    border: none;
}}

/* --- ツールバー / ステータスバー / ドック --- */
QToolBar {{
    background: {surface};
    border: none;
    border-bottom: 1px solid {border};
    spacing: 4px;
    padding: 4px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
}}
QToolButton:hover {{
    background: {surface_2};
}}
/* ★ 項目H-2-5(クイックアクセスツールバーの実機確認で発覚): QPushButton側は
   :hover/:pressed共にselection_accent系(青)へ統一済みだったが、
   QToolButton側は同じ更新が漏れておりティール系accent_softのままだった
   (ツールバーのボタンは全てQToolButton、QPushButtonの修正だけでは
   カバーされない)。他の選択/フォーカス/チェック状態と揃えて青に統一する。 */
QToolButton:pressed {{
    background: {selection_highlight};
}}
QToolButton:checked {{
    background: {selection_highlight};
    border: 1px solid {selection_accent};
}}
QStatusBar {{
    background: {surface};
    border-top: 1px solid {border};
}}
/* ★ 実機フィードバック: 「プロパティウィンドウの方に無駄に枠線がある」の
   正体。QScrollArea自体にQSSで何もスタイルしていなかったため、Qt(Fusion)の
   既定の枠線(sunkenフレーム)がそのまま出ていた。プロパティドックの中身は
   QScrollAreaでラップされている(gui/main_window.pyのmerged_scroll_area)が、
   エクスポートプレビューはラップされていないため、両者の見た目が
   意図せず不揃いになっていた。枠線を消してQDockWidget自体の枠(下記)だけに
   揃える。
   ★ 追加の実機フィードバック: 枠線を消した後も「プロパティウィンドウの
   背景色が他と違う」という指摘が続いた。実測(widgetAt()でピクセル座標の
   実ウィジェットを特定 + QWidget.grab()での分離検証)したところ、犯人は
   ビューポート(QAbstractScrollArea::viewport()、QScrollArea直下の子
   QWidget)そのものではなく、その中に`setWidget()`で入れている中身のwidget
   (gui/main_window.pyのmerged_properties_container、QScrollArea直下の
   孫QWidget)だった。app.setStyleSheet()でアプリ全体にQSSを適用すると
   (Qtの既知の挙動として)全QWidgetがWA_StyledBackground扱いになり、
   明示的なbackground指定が無いプレーンなQWidgetでもQPaletteのWindowロール
   色(このアプリではライトモードでOSネイティブパレットをそのまま使っている
   ため実測 #F0F0F0)で不透明に塗りつぶされてしまう。ビューポート自身は
   中身のwidgetに完全に覆われて見えなくなるため、ビューポートにだけ{bg}を
   指定しても効果が無かった。QScrollArea自体・ビューポート(直下の子)・
   中身のwidget(直下の孫)の3階層すべてに明示的に{bg}を指定して解消する。 */
QScrollArea {{
    border: none;
    background: {bg};
}}
QScrollArea > QWidget {{
    background: {bg};
}}
QScrollArea > QWidget > QWidget {{
    background: {bg};
}}
/* --- ドック全般(項目H-2-3): 境界線・タイトルバー・フォーカス時の強調 ---
   以前はQDockWidget自体に枠線が無く、タイトルバーの背景色だけが唯一の
   手がかりだったため、キャンバス周り(plot_container、1節参照)と違って
   「1枚のカード」として認識しにくかった。同じ考え方(枠+角丸)をドックにも
   適用し、見た目の一貫性を取る。上下に積み重なったドック同士の間には
   既存のQSplitter::handle(下記)による3pxの隙間が既にあるため、各ドックに
   フルの枠を付けても二重線が密着して見えることはない。 --- */
QDockWidget {{
    /* ★ 実機フィードバック: 「プロパティウィンドウの背景色がそのまま」の
       正体。QDockWidget自体にはbackgroundの指定が無く、OSネイティブの
       パレット既定色(Windowロール)がそのまま透けて見えていたため、背景色
       トークンを変更してもここだけ反映されていなかった。QMainWindow/
       QDialogと同じ{bg}を明示的に指定する。 */
    background: {bg};
    border: 1px solid {border};
    border-radius: 8px;
}}
QDockWidget::title {{
    background: {surface_2};
    padding: 6px 8px;
    border-bottom: 1px solid {border};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    letter-spacing: .01em;
}}
/* ★ フォーカス時の強調: QDockWidget自体には「アクティブ」を示すQt標準の
   状態が無いため、Python側(install_dock_focus_highlight()、このファイル内)
   でフォーカス移動を監視し、動的プロパティdockActiveを付け外ししている。
   ここではその結果を枠線として反映するだけ。色は他のフォーカス表現
   (下のQPushButton:focus等)と揃えてselection_accent(青)を使う
   (実機フィードバック: 「フォーカス時の色が緑のまま」)。 */
QDockWidget[dockActive="true"] {{
    border: 1px solid {selection_accent};
}}
QDockWidget[dockActive="true"]::title {{
    border-bottom: 1px solid {selection_accent};
}}

/* --- スプリッター(ドック/パネルの境界): 既定のOSハンドルはフラットテーマと
   馴染まないため、細く控えめなハンドルに置き換え、ホバー時のみアクセント色で
   「動かせる」ことを示す(GUI洗練) --- */
QSplitter::handle {{
    background: {border};
}}
QSplitter::handle:horizontal {{
    width: 3px;
    margin: 2px 0;
}}
QSplitter::handle:vertical {{
    height: 3px;
    margin: 0 2px;
}}
QSplitter::handle:hover {{
    background: {accent};
}}

/* --- グループボックス / ボタン --- */
QGroupBox {{
    background: transparent;
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 20px;
    padding-top: 14px;
    font-weight: 500;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    /* ★ 実機フィードバック(画像提示、環境設定・フォント選択ダイアログ):
       「外観/言語/保存...やEffect/Sampleのチップが見切れてる」。以前は
       top: -6pxで、グループボックスの外枠より上に6pxはみ出す形で「境界線に
       半分乗ったラベル」の見た目にしていた。この方式はグループボックスの
       margin-top(下記、20px)で確保した領域にチップが浮き出る前提だが、
       自前で構築するダイアログ(PreferencesDialog等)ではmargin-topが正しく
       効いていて問題なかった一方、QFontDialog/QColorDialogのようなQt標準の
       ダイアログ(内部レイアウトを直接制御できない)では、この上方向の
       突き出し分の余白が確保されず、チップの上端が周囲の要素に隠れて
       見切れていた(実機のスクリーンショットで確認)。外枠の外へ一切
       はみ出さない0pxに変更し、周囲のレイアウト側の余白に依存しない
       (=どんなダイアログでも安全な)配置にする。 */
    top: 0px;
    padding: 2px 8px;
    /* ★ 実機フィードバック: 「ポップアップウィンドウのボタンの色が緑の
       まま」と同様の指摘(画像提示、複数ダイアログ)。グループ見出しチップも
       ブランドアクセント(ティール系accent)のままだったのを、他の強調表現と
       揃えてselection_accent(青)に統一した。 */
    color: {selection_accent};
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: .02em;
    background: {selection_highlight};
    border-radius: 5px;
}}

/* --- ドック内のグループボックスは二重の箱にしない(GUI洗練) ---
   QDockWidget自体がすでに1枚のカードとして枠を持っているため、その中の
   グループボックスにも同じ枠+色付きチップの見出しを重ねると、箱の中に
   箱が入れ子になって窮屈に見える。ドック内では枠を取り払い、見出しは
   控えめなラベルのみにする(モーダルダイアログ側のグループボックスは
   従来どおりのチップ付きスタイルを維持) */
QDockWidget QGroupBox {{
    border: none;
    border-radius: 0;
    margin-top: 18px;
    padding-top: 6px;
}}
QDockWidget QGroupBox::title {{
    left: 0;
    /* ★ 実機フィードバック(画像提示、「グラフ全体レイアウト」「編集対象の
       プロット」の見出しチップ): 上のQGroupBox::title(モーダルダイアログ側)
       は同じ「見出しが見切れる」問題を既にtop: -6px→0pxで解消済みだったが、
       このドック専用ルールだけ古いtop: -4pxのまま残っていて見落とされていた
       (Win/Mac両方で発生、枠の外へはみ出す量に依存する問題のためOS非依存)。
       同じ理由・同じ直し方で0pxに揃える。 */
    top: 0px;
    padding: 0;
    color: {text_secondary};
    background: transparent;
    border-radius: 0;
}}

/* --- 折りたたみ可能なセクション見出し(項目102) ---
   「データセットのプロパティ」「プロットのプロパティ」の開閉トグルボタン。
   通常のQToolButtonとは見た目を変え、アコーディオンの見出し行らしく
   横幅いっぱい・左寄せ・太字にする。 */
QToolButton#collapsible_section_toggle {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 4px;
    text-align: left;
    font-weight: 600;
    font-size: 12.5px;
    color: {text_secondary};
}}
QToolButton#collapsible_section_toggle:hover {{
    background: {surface_2};
    color: {text_primary};
}}
QToolButton#collapsible_section_toggle:pressed {{
    background: {accent_soft};
}}
QPushButton {{
    background: {surface};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 5px 14px;
}}
QPushButton:hover {{
    background: {surface_2};
    /* ★ 実機フィードバック: 「クリックしてフォーカスしたときには青になって
       いるのに、マウスを合わせたときの色が緑のまま」。:focus(下記)は
       selection_accentに揃えたが、:hoverの枠線だけ旧来のティール系accentの
       ままだったため、同じselection_accentに揃えた。 */
    border-color: {selection_accent};
}}
QPushButton:pressed {{
    /* ★ 実機フィードバック: 「フォント選択/色選択ボタンのクリックした瞬間の
       色が緑のまま」。:hover/:focusは既にselection_accent系(青)に揃えて
       いたが、:pressed(実際に押し込んでいる間)の背景だけティール系
       accent_softのままだったため、同じ色相のselection_highlight(薄い青の
       半透明オーバーレイ)に統一した。 */
    background: {selection_highlight};
}}
QPushButton:disabled {{
    color: {text_muted};
    border-color: {border};
}}
QPushButton:default {{
    /* ★ 実機フィードバック(画像提示、複数のポップアップダイアログ):
       「実行/OK/Closeのようなデフォルトボタンの色が緑のまま」。フォーカス/
       選択/チェック状態は既に全てselection_accent(青)に統一済みだったが、
       ダイアログの主要アクションボタン(Enterキーで実行される既定ボタン)
       だけはブランドアクセント(ティール系accent)のまま意図的に残して
       いた。実機で複数のダイアログを横断的に見ると、この1箇所だけ色相が
       違うことがかえって「まだ緑が残っている」という印象を与えていたため、
       他の全ての強調表現と同じselection_accentに統一する。文字色は
       チェックボックスのチェック時塗りつぶし(_draw_checkbox_indicator)と
       同じ理由でaccent_textとの組み合わせを踏襲する(ライト/ダーク双方で
       selection_accent背景に対して十分なコントラストが取れることを実機で
       確認済み)。 */
    background: {selection_accent};
    border-color: {selection_accent};
    color: {accent_text};
}}
/* ★ フォーカス枠の色は、選択・入力欄フォーカス等の他の「フォーカス/選択」
   表現と揃えてselection_accent(青)を使う(実機フィードバック: 「スピン
   ボックスとかをフォーカスしたときの色が緑のまま」)。ボタンの通常時/hover/
   pressed/checkedの配色自体はアプリのブランドアクセント(ティール系accent)
   のまま変えていない。 */
QPushButton:focus, QToolButton:focus {{
    border: 1px solid {selection_accent};
}}

/* --- アイコンのみの正方形ボタン(データセット操作ボタン行、GUI洗練) ---
   テキストラベルを持たず、ツールチップで用途を示す。9個並んでも横幅を
   取らないよう正方形に固定する(実際のサイズ指定はPython側setFixedSize) */
QPushButton[iconOnly="true"] {{
    padding: 4px;
}}

/* --- 入力欄 --- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {selection_highlight};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    /* ★ 実機フィードバック: 「スピンボックスとかをフォーカスしたときの色が
       緑のまま」を受け、selection_highlight/selection_accent(青)と揃えた。 */
    border-color: {selection_accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {text_muted};
    background: {surface_2};
}}

/* --- タイトル/軸ラベルのmathtextプレビューラベル(項目H-2-4追加分) ---
   クリックでLabelEditDialogを開くトリガーを兼ねるため、QLineEditと同じ
   見た目(背景・枠線・角丸・パディング)にして「入力欄に見える」ようにし、
   hover時だけ枠線をselection_accentにして「クリックできる」ことを示す。 */
QLabel#mathtext_preview_label {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
}}
QLabel#mathtext_preview_label:hover {{
    border-color: {selection_accent};
}}

/* --- スピンボックスの上下ボタン(GUI洗練) ---
   ボックス自体(背景・区切り線)はQSSで問題なくスタイルできるが、矢印
   (::up-arrow/::down-arrow)は `width`/`height` の指定だけでも描画されなく
   なることを確認した(QLineEdit等と共有の角丸入力欄スタイルがQSpinBox
   自体にも掛かっているため、Qt内部でCC_SpinBoxの描画がQStyleSheetStyleに
   丸ごと引き取られ、QProxyStyle側のdrawPrimitive/drawComplexControlの
   オーバーライドが安定して反映されないことを検証済み)。矢印だけは実際の
   画像ファイル(image: url(...))として与えることで確実に表示される。 */
QSpinBox, QDoubleSpinBox {{
    padding-right: 20px;
}}
/* ★ GUI洗練(実機フィードバック、参考イメージ提示): 以前は上下ボタンが
   フィールドの右端に直接くっついた「外側の角だけ丸い」1つの帯だったが、
   参考イメージに合わせて、それぞれが独立した小さな角丸ボックスに見えるよう
   全4隅を丸め、marginで枠線・フィールドの双方から少し離した。矢印画像
   (::up-arrow/::down-arrow)の扱いは変更なし(上のコメント参照、実ファイル
   画像で確実に表示する方式のまま)。さらに実機フィードバックを受け、
   ボタン自体の背景・枠線は常時は透明にし、矢印アイコンだけが浮いて見える
   ミニマルな見た目にした(hover/pressed時のみ背景色を出して、押せる場所だと
   分かるようにする)。 */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    height: 13px;
    margin: 1px 2px 1px 1px;
    border: 1px solid transparent;
    border-radius: 4px;
    background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    height: 13px;
    margin: 1px 2px 1px 1px;
    border: 1px solid transparent;
    border-radius: 4px;
    background: transparent;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {border_strong};
}}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background: {accent_soft};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({spin_up_arrow_url});
    width: 12px;
    height: 12px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({spin_down_arrow_url});
    width: 12px;
    height: 12px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    /* スピンボックスと同じ理由(QSSでwidth/heightを指定するだけで矢印自体が
       描画されなくなる)により、画像として与える。サイズもスピンボックスの
       矢印(上記::up-arrow/::down-arrow)と揃えている(実機フィードバック)。 */
    image: url({spin_down_arrow_url});
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background: {surface};
    border: 1px solid {border};
    selection-background-color: {selection_highlight};
    selection-color: {text_primary};
    outline: none;
}}

/* --- リスト / ツリー / テーブル --- */
QTreeWidget, QListWidget, QTableWidget {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 8px;
    alternate-background-color: {surface_2};
}}
QHeaderView::section {{
    background: {surface_2};
    color: {text_secondary};
    border: none;
    border-bottom: 1px solid {border};
    padding: 4px 6px;
}}
QTreeWidget::item, QListWidget::item, QTableWidget::item {{
    padding: 3px;
}}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
    background: {selection_highlight};
    color: {text_primary};
}}
QTreeWidget::item, QListWidget::item {{
    padding: 5px 4px;
    border-radius: 5px;
}}

/* --- データセットリストの選択ハイライト(項目H-2-2、実機フィードバックで
   複数回調整): 当初はQSSの ::item:selected 規則(background/border-radius)だけで
   実現しようとしたが、Qt(Fusionスタイル)はCE_ItemViewItemの描画時に
   デコレーション(アイコン)列とテキスト(display)列を“別々の矩形”として扱い、
   background/border-radiusもそれぞれ独立に適用する。そのためアイコン列と
   テキスト列の角丸が微妙にズレて隙間から地の色が透けて見える、あるいは
   border-radiusを0にすれば隙間は消えるがリスト自体の角丸(下のQTreeWidget/
   QListWidget/QTableWidget規則のborder-radius: 8px)と揃わない、という
   問題が残った(実機でピクセルを直接比較して確認済み)。QSSの
   show-decoration-selectedプロパティで1矩形に統合できないか試したが、
   PySide6のQTreeView/QTreeWidgetにはこのプロパティに対応する公開APIが無く
   (hasattr確認済み)、QSS指定も実機で効果が無かった。
   最終的に、選択時の背景描画だけは_DatasetTreeSelectionDelegate
   (gui/main_window.py)が自前で行うようにした: 1つのQPainterPathでリストと
   同じ角丸(DATASET_LIST_ITEM_RADIUS)の矩形を1回だけ塗り、Qt標準の選択背景
   描画はoption.stateからState_Selectedを外すことで無効化している。
   ただし「分岐(展開矢印)用インデント列」だけはこのState_Selected解除の
   影響を受けない: QTreeViewはインデント列をdelegate.paint()とは別の
   drawBranches()という独自の経路で描画しており、こちらはモデル側の実際の
   選択状態を見るため、汎用のリスト共通スタイル(上の
   QTreeWidget::item:selected, QListWidget::item:selected,
   QTableWidget::item:selected 規則、背景にaccent_softを使うもの)が
   そのままインデント列に滲み出てしまう(実機で確認: このリストのアイテムのみ
   薄いティール色の四角がインデント列に残っていた)。下のbackground:
   transparentは、このリストに限ってその汎用ルールを打ち消すための指定。 --- */
QTreeWidget#dataset_list_widget {{
    selection-background-color: transparent;
    selection-color: {text_primary};
    /* ★ outline: none が無いと、選択+キーボードフォーカス時にQtが項目の
       テキスト周りへ点線のフォーカス矩形を描画し、デリゲートの角丸ハイライトの
       上にもう1つ四角い枠が重なって見えてしまう(実機フィードバックで発見)。
       QComboBox QAbstractItemViewの選択済み項目でも同じ理由でoutline: none
       を使っている(このファイル内の別箇所を参照)。 */
    outline: none;
    /* ★ 項目H-2-2(実機フィードバック): リスト自体の枠線を消してほしい、
       という指示を受けての指定。検索ボックスと統合するわけではなく、
       あくまで「それぞれの箱の線を消す/背景色と同じにする」ため、
       枠線だけを消して背景・角丸(上のQTreeWidget/QListWidget/QTableWidget
       規則のborder-radius: 8px)はそのまま活かす。 */
    border: none;
}}
/* ★ 上のコメント(drawBranches()の件)で説明した、汎用::item:selectedルールの
   インデント列への滲み出しを、このリストに限って打ち消す。デリゲートが背景を
   自前描画するため、item本体の見た目には影響しない。 */
QTreeWidget#dataset_list_widget::item:selected {{
    background: transparent;
}}

/* --- データセット検索ボックスの枠線を消す(項目H-2-2、実機フィードバック):
   リストと統合する意図ではなく、検索ボックス単体の枠線を消して背景色との
   境目を目立たなくするための指定(下のリストの枠線消しと対になる)。 --- */
QLineEdit#dataset_search_edit {{
    border: none;
}}

/* --- タブ --- */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
}}
QTabBar::tab {{
    background: transparent;
    color: {text_secondary};
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{
    background: {surface_2};
    color: {text_primary};
}}
QTabBar::tab:selected {{
    background: {surface};
    /* ★ 実機フィードバック(画像提示): 選択中タブの下線・文字色が緑っぽい
       ティール系accentのままだったのを、他の選択/フォーカス表現と揃えて
       selection_accent(青)に変更した。 */
    border-bottom: 2px solid {selection_accent};
    color: {selection_accent};
    font-weight: 600;
}}
/* ★ QTabBar::close-button に何かひとつでもプロパティを指定すると(paddingや
   border-radiusだけでも)、Qtがこのサブコントロールを「スタイルシートで
   カスタム描画される」ものとみなし、アイコン自体が一切描画されなくなる
   (QProxyStyleでstandardIcon/standardPixmapを差し替えても効果が無い)。
   そのため、閉じるボタンにはQSSを一切当てず、アイコンの見た目は
   _TabCloseIconStyle (QProxyStyle) 側だけで制御する。 */

QToolButton#add_tab_button {{
    margin: 3px 6px 3px 2px;
    border-radius: 13px;
    padding: 5px;
}}
QToolButton#add_tab_button:hover {{
    background: {accent_soft};
}}

/* --- チェックボックス / ラジオボタン ---
   ★ QCheckBox::indicator はQSSで何もスタイルしない。タブの閉じるボタンと
   同様に、サブコントロールにQSSで何かひとつでもプロパティ(width/height/
   border等)を指定すると、Qtがチェックマーク自体を描画しなくなり、
   ただの塗りつぶし四角になってしまう(実際にこれで報告された)。
   見た目(枠・塗りつぶし・チェックマーク)はすべて _FlatThemeProxyStyle の
   drawPrimitive(PE_IndicatorCheckBox) で自前描画する。 */
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border_strong};
    border-radius: 7px;
    background: {surface};
}}
QRadioButton::indicator:checked {{
    /* ★ チェックボックス(下のPE_IndicatorCheckBox自前描画)のチェック時の
       塗りつぶしと揃えて、selection_accent(青)を使う(実機フィードバック:
       「チェックボックスの塗りつぶしの色も」と同じ理由での統一)。 */
    background: {selection_accent};
    border-color: {selection_accent};
}}

/* --- プログレスバー --- */
QProgressBar {{
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    background: {surface_2};
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 6px;
}}

/* --- スクロールバー --- */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {border_strong};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed {{
    /* ★ 実機フィードバック: 「スクロールバーを動かすときの色が緑のまま
       だから他のとこの青で統一」。hover/focus/選択等の他の強調表現は
       既にselection_accent(青)へ統一済みだったが、ここだけ取り残されて
       いた(ブランドアクセントのaccentのまま)。ドラッグ中はQtの挙動上
       :hoverスタイルが適用され続けるため、:pressedも明示して揃える。 */
    background: {selection_accent};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {border_strong};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:pressed {{
    background: {selection_accent};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""


def build_qss(tokens: dict) -> str:
    """
    トークン辞書(LIGHT_TOKENS/DARK_TOKENS、または将来の任意のカスタムトークン)
    から、_FLAT_QSS_TEMPLATEの`{token_name}`プレースホルダを埋めた最終的な
    QSS文字列を返す(項目H-1)。矢印アイコンのURLはトークンの`text_primary`色から
    動的に生成して付加する。
    """
    format_args = dict(tokens)
    format_args["spin_up_arrow_url"] = _spinbox_arrow_icon_url("up", tokens["text_primary"])
    format_args["spin_down_arrow_url"] = _spinbox_arrow_icon_url("down", tokens["text_primary"])
    return _FLAT_QSS_TEMPLATE.format(**format_args)


def _build_dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.ColorRole.Link, QColor(90, 160, 230))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(60, 120, 200))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    return palette


class _FlatThemeProxyStyle(QProxyStyle):
    """
    QSSだけでは実現できない(あるいはQtの既知の癖により逆に壊れる)、いくつかの
    描画をQProxyStyle側で肩代わりするための共通スタイル。

    ★ 共通する根本原因: Qtは、あるサブコントロールにQSSで何かひとつでも
    プロパティ(padding, border-radius, width...)を指定すると、そのサブ
    コントロールを「スタイルシートでカスタム描画されるもの」とみなし、
    アイコンやチェックマークなどの「中身」を一切描画しなくなることがある。
    - タブを閉じる「×」ボタン: QTabBar::close-buttonにQSSを当てると、
      アイコン自体が完全に消える(実機で報告され、調査の上で発見)。
      → QSSは一切当てず、標準アイコンをここで差し替える。
    - チェックボックス: QCheckBox::indicatorにQSSを当てると、チェック時に
      ただの塗りつぶし四角になり、チェックマークが描画されない
      (同じく実機で報告)。
      → QSSは一切当てず、枠・塗りつぶし・チェックマークをすべてここで
      自前描画する。
    """
    def __init__(self, base_style, tokens):
        super().__init__(base_style)
        self.update_tokens(tokens)

    def update_tokens(self, tokens):
        """
        ダーク/ライト切り替え時に、既存のインスタンスの色情報だけを
        更新する(新しいインスタンスをapp.setStyle()で差し替えない)。
        理由はapply_theme()側のコメント参照。
        """
        self._tokens = tokens
        self._close_icon = _svg_icon("x", color=tokens["text_secondary"], size=14)
        self._close_pixmap = self._close_icon.pixmap(14, 14)

    def standardIcon(self, standard_icon, option=None, widget=None):
        if standard_icon == QStyle.StandardPixmap.SP_TabCloseButton:
            return self._close_icon
        return super().standardIcon(standard_icon, option, widget)

    def standardPixmap(self, standard_pixmap, option=None, widget=None):
        # ★ Qt内部のタブ「閉じる」ボタン(private CloseButton)は、実際には
        #   standardIcon()ではなくこちらのstandardPixmap()経由でアイコンを
        #   取得している。standardIcon()だけをオーバーライドしても効果が
        #   無かったため、両方をオーバーライドする必要がある。
        if standard_pixmap == QStyle.StandardPixmap.SP_TabCloseButton:
            return self._close_pixmap
        return super().standardPixmap(standard_pixmap, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            self._draw_checkbox_indicator(option, painter)
            return
        if element == QStyle.PrimitiveElement.PE_FrameTabBarBase:
            # ★ 実機フィードバック(画像提示): 「プロパティ/エクスポート
            #   プレビュー」タブ(タブ化したQDockWidget)の上に、灰色の横線が
            #   残っていた。これはQTabBar::tab等のQSSでは制御できない別の
            #   プリミティブ(タブバーを内容ペインに接続する「土台」線、
            #   Fusionスタイルが独自に描画する)が原因で、QSSからは一切
            #   スタイルできない(チェックボックスの項目と同じ理由でここに
            #   実装している)。何も描画せずに抑制することで解消する。
            return
        super().drawPrimitive(element, option, painter, widget)

    def _draw_checkbox_indicator(self, option, painter):
        tokens = self._tokens
        checked = bool(option.state & QStyle.StateFlag.State_On)
        tristate = bool(option.state & QStyle.StateFlag.State_NoChange)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)

        if not enabled:
            fill = QColor(tokens["surface_2"])
            border = QColor(tokens["border"])
        elif checked or tristate:
            # ★ 実機フィードバック: 「チェックボックスの塗りつぶしの色も」
            #   緑(ティール系accent)から、他の選択/フォーカス表現と揃えた
            #   selection_accent(青)に変更した。
            fill = QColor(tokens["selection_accent"])
            border = fill
        else:
            fill = QColor(tokens["surface"])
            border = QColor(tokens["border_strong"])

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(border)
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.setBrush(fill)
        rect = QRectF(option.rect).adjusted(0.75, 0.75, -0.75, -0.75)
        painter.drawRoundedRect(rect, 3, 3)

        if checked or tristate:
            check_color = QColor(tokens["accent_text"]) if enabled else QColor(tokens["text_muted"])
            check_pen = QPen(check_color)
            check_pen.setWidthF(1.6)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            r = option.rect
            path = QPainterPath()
            if tristate:
                # 部分選択状態: 横棒のみ
                path.moveTo(r.x() + r.width() * 0.22, r.y() + r.height() * 0.5)
                path.lineTo(r.x() + r.width() * 0.78, r.y() + r.height() * 0.5)
            else:
                # チェックマーク(レ点)
                path.moveTo(r.x() + r.width() * 0.20, r.y() + r.height() * 0.52)
                path.lineTo(r.x() + r.width() * 0.42, r.y() + r.height() * 0.74)
                path.lineTo(r.x() + r.width() * 0.82, r.y() + r.height() * 0.26)
            painter.drawPath(path)

        painter.restore()


def apply_theme(app, dark: bool):
    """
    QApplication 全体にダーク/ライトのテーマを適用する。

    ライト/ダークどちらのときも常に Fusion スタイルを使い、パレット(色)だけを
    切り替える。スタイル自体をネイティブ⇔Fusionで切り替えると、ツールバーの
    ボタンサイズや余白などQStyle依存の見た目がモードごとに変わってしまうため、
    スタイルは固定してモード間の見た目の一貫性を保つ。
    """
    global _original_palette, _original_style_name, _current_proxy_style, _current_tokens
    global _last_applied_dark
    if _original_palette is None:
        _original_palette = QPalette(app.palette())
        _original_style_name = app.style().objectName()

    tokens = DARK_TOKENS if dark else LIGHT_TOKENS
    _current_tokens = tokens

    # ★ 起動高速化: PlotterApp.__init__は同じ dark 値でapply_theme()を2回
    #   呼ぶ(アイコン構築前の早期反映用と、_create_menu_bar()側の冪等性
    #   確保用)。複数タブを開いた場合もタブごとに同じ値で再度呼ばれる。
    #   setPalette()/app.setStyleSheet()はQApplication配下の全ウィジェットに
    #   対する処理でQt側のコストが大きい(実測: 1回あたり約130ms)ため、
    #   直前に適用済みの値と変わらない場合は完全にスキップする。
    #   _on_toggle_dark_mode等、実際にモードが変わる呼び出しでは
    #   _last_applied_dark と異なる値が渡るため、従来通りフルに適用される。
    if _current_proxy_style is not None and _last_applied_dark == dark:
        return
    _last_applied_dark = dark

    # ★ バグ修正: 以前は呼び出しのたびに新しい QProxyStyle(+ラップ元の新しい
    # Fusionスタイル)を作ってapp.setStyle()で丸ごと差し替えていた。
    # QApplication.setStyle()は「差し替え前の古いスタイルオブジェクトを
    # 削除する」仕様のため、その古いスタイルオブジェクトを、まだ生きている
    # 他のウィンドウ/ウィジェット(このアプリは複数タブ=複数の独立した
    # PlotterAppを同一QApplication上で同時に持つ設計、CLAUDE.md参照)が
    # 参照し続けていると、削除済みオブジェクトへのアクセスで
    # "Windows fatal exception: access violation" のようなネイティブ
    # クラッシュを起こす(実際にCI上のフルテスト実行で複数タブ相当の
    # ウィンドウが多数生きた状態のままダークモード切替を繰り返した際に
    # 再現した)。スタイルオブジェクト自体はQApplicationにつき1つだけ生成し
    # (app.setStyle()も一度だけ呼ぶ)、ダーク/ライト切替時はその既存
    # インスタンスの色情報だけをupdate_tokens()で書き換える。
    if _current_proxy_style is None:
        base_style = QStyleFactory.create('Fusion')
        _current_proxy_style = _FlatThemeProxyStyle(base_style, tokens)
        app.setStyle(_current_proxy_style)
    else:
        _current_proxy_style.update_tokens(tokens)
    if dark:
        app.setPalette(_build_dark_palette())
    else:
        app.setPalette(_original_palette)

    # パレットに加えて QSS を適用し、ツールバー/ボタン/入力欄/リスト等を
    # 角丸・フラットな見た目に統一する(モダンなミニマルテーマ)。
    app.setStyleSheet(build_qss(tokens))


def current_tokens() -> dict:
    """
    現在適用中(ライト/ダーク)のトークン辞書(LIGHT_TOKENSまたはDARK_TOKENS)を
    そのまま返す(項目H-2-4追加分: mathtextプレビュー(gui/mathtext_preview.py)
    の文字色をテーマに追従させるため等、Python側から任意のトークン値を
    参照したい場面向けの汎用アクセサ)。apply_theme()より前に呼ばれた場合
    (通常は起こらない)はLIGHT_TOKENSにフォールバックする。
    """
    return _current_tokens or LIGHT_TOKENS


def current_selection_highlight_qcolor() -> QColor:
    """
    現在適用中(ライト/ダーク)のselection_highlightトークンをQColorとして返す
    (項目H-2-2)。データセットリストの選択ハイライトはQSSのbackgroundだけでは
    行全体を単一の角丸矩形として描画できない(Qtがアイコン列とテキスト列を
    別々の矩形として描画するため、実機検証済み)ため、
    _DatasetTreeSelectionDelegate(gui/main_window.py)が自前で背景を描画している。
    トークン値は "rgba(r, g, b, a)" 形式のQSS埋め込み用文字列であり、
    QColor(str)コンストラクタでは解釈できない(QColorはCSSのrgba()関数記法を
    理解せず、不透明の黒に無効フォールバックしてしまうことを実機で確認した)ため、
    ここで正規表現パースしてQColorを直接返す。apply_theme()より前に呼ばれた
    場合(通常は起こらない)はLIGHT_TOKENSにフォールバックする。
    """
    tokens = _current_tokens or LIGHT_TOKENS
    raw = tokens["selection_highlight"]
    match = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", raw)
    if not match:
        return QColor(raw)
    r, g, b, a = match.groups()
    color = QColor(int(r), int(g), int(b))
    color.setAlphaF(float(a))
    return color


def install_dock_focus_highlight(window):
    """
    windowが持つQDockWidget群に、キーボード/クリックでフォーカスが当たって
    いる間だけ枠線をアクセント色で強調する仕組みを組み込む(項目H-2-3)。

    QDockWidget自体には「アクティブ」を示すQt標準の状態が無いため、
    `QApplication.focusChanged`信号でアプリ全体のフォーカス移動を監視し、
    フォーカスされたウィジェットの祖先をたどってQDockWidgetを特定した上で、
    動的プロパティ`dockActive`をQSSの属性セレクタ(`QDockWidget[dockActive=
    "true"]`、上の_FLAT_QSS_TEMPLATE参照)経由で反映する。プラグイン製パネル
    (項目D-1)のように後から追加されるQDockWidgetも、祖先を都度たどる方式
    のため個別登録なしで自動的にカバーされる。

    ★ 複数タブ(main_app_window.py)対応の注意点: `focusChanged`はプロセス内
    全体で共有される単一のシグナルであり、他のタブ/ウィンドウでのフォーカス
    移動でもこのハンドラは呼ばれる。見つかったドックが`window`の管轄でない
    場合は「このwindowにとってはフォーカスが外れた」ものとして扱い、
    自分のドックのハイライトだけを解除する(他のタブのドックには一切触れない)。
    各PlotterAppタブは完全に独立したウィンドウという設計方針
    (CLAUDE.mdのアーキテクチャ節参照)を、この機能でも守っている。
    """
    from PySide6.QtWidgets import QApplication, QDockWidget

    def _dock_ancestor(widget):
        while widget is not None and not isinstance(widget, QDockWidget):
            widget = widget.parentWidget()
        return widget

    def _set_active(dock, active):
        if dock is None:
            return
        dock.setProperty("dockActive", active)
        style = dock.style()
        style.unpolish(dock)
        style.polish(dock)

    state = {"active": None}

    def _on_focus_changed(old, new):
        dock = _dock_ancestor(new) if new is not None else None
        if dock is not None and dock.window() is not window:
            dock = None
        if dock is state["active"]:
            return
        _set_active(state["active"], False)
        _set_active(dock, True)
        state["active"] = dock

    app = QApplication.instance()
    app.focusChanged.connect(_on_focus_changed)
    # windowが破棄された後もconnectionが残ってゾンビハンドラにならないよう、
    # window自身の破棄時にdisconnectする。
    window.destroyed.connect(lambda: app.focusChanged.disconnect(_on_focus_changed))


def apply_form_spacing(widget, spacing=12):
    """
    設定/プロパティ系のダイアログ・パネルの項目間の余白を広げる
    (ユーザーフィードバックを受けて、QFormLayoutの既定の詰まった間隔を緩める)。
    widget配下の全QFormLayoutを対象に、垂直方向の間隔を最低spacingまで広げる。
    既にそれより広い間隔が明示的に設定されているレイアウトは縮めない。
    """
    from PySide6.QtWidgets import QFormLayout
    for form_layout in widget.findChildren(QFormLayout):
        if form_layout.verticalSpacing() < spacing:
            form_layout.setVerticalSpacing(spacing)


def disable_scroll_value_change():
    """
    QSpinBox/QDoubleSpinBox/QComboBoxは既定でマウスホイールで値が変わり、
    スクロール可能なドック/ダイアログの中でスクロールしようとしただけで
    意図せず値が変わる事故が起きやすい。

    ★ 当初は「フォーカスが無い間だけ無視する」という条件付きの実装を
    試したが、実際には効果がなかった: QAbstractSpinBoxの既定のフォーカス
    ポリシーは Qt.FocusPolicy.WheelFocus であり、フォームを開いた直後は
    フォーカス可能な最初のウィジェットに自動的にフォーカスが当たる上、
    一度どれかのフィールドにフォーカスが移ると、ユーザーがマウスを別の
    フィールドへ動かして単にスクロールしただけでは、フォーカス自体は
    そのフィールドに残ったままになる。つまり「マウスカーソルが今どこに
    あるか」と「hasFocus()が真かどうか」は一致しないため、フォーカスの
    有無では判定できない。そのため、ホイールによる値変更は常に無効化する
    (値の変更は上下矢印ボタン、またはキーボード入力/フォーカス後の
    キー操作で行う)。

    ホイールイベントを event.ignore() で無視すると (accept() せず、独自の
    処理も行わないと)、Qtはそのイベントを親ウィジェットへ伝播させるため、
    スピンボックスの上でマウスホイールを回してもスクロールエリア自体は
    問題なくスクロールできる。

    クラスのメソッドを直接書き換えるため、アプリ起動時に一度だけ呼び出す
    (QApplication生成後、最初のウィジェットが作られる前が望ましい)。
    """
    global _wheel_value_change_disabled
    if _wheel_value_change_disabled:
        return
    _wheel_value_change_disabled = True

    def _ignore_wheel_event(self, event):
        event.ignore()

    QAbstractSpinBox.wheelEvent = _ignore_wheel_event
    QComboBox.wheelEvent = _ignore_wheel_event
