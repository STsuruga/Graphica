import logging
import re
import numpy as np
import pandas as pd
import matplotlib as mpl
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTextBrowser,
                               QDialogButtonBox, QFormLayout, QComboBox,
                               QDoubleSpinBox, QLabel, QLineEdit, QSpinBox,
                               QPushButton, QHBoxLayout, QPlainTextEdit,
                               QApplication, QFileDialog, QMessageBox, QGroupBox,
                               QTableWidget, QTableWidgetItem, QListWidget,
                               QListWidgetItem, QColorDialog, QInputDialog,
                               QCheckBox, QStackedWidget, QWidget, QTabWidget,
                               QToolButton, QGridLayout, QMenu, QWidgetAction)
from PySide6.QtCore import Qt, QTimer, QEvent, QUrl
from PySide6.QtGui import QPixmap, QFont, QColor, QKeySequence, QDesktopServices

from gui import icon_utils
from gui.theme import apply_form_spacing
from gui.mathtext_preview import FitWidthPixmapLabel

logger = logging.getLogger(__name__)


#==============================================================================
# カスタムダイアログクラス (0): このソフトについて
#==============================================================================
class AboutDialog(QDialog):
    """
    「このソフトについて」ダイアログ。
    バージョン番号 (core/version.py で一元管理) と、使用しているOSSライブラリの
    ライセンス表記をまとめて表示する。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.version import APP_NAME, __version__
        from core.i18n import tr

        self.setWindowTitle(tr("{app} について").format(app=APP_NAME))
        self.resize(420, 380)

        layout = QVBoxLayout(self)

        if parent is not None:
            icon_label = QLabel()
            pixmap = parent.windowIcon().pixmap(64, 64)
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap)
                icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                layout.addWidget(icon_label)

        title_label = QLabel(f"<h2>{APP_NAME}</h2>")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"{tr('バージョン')} {__version__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(version_label)

        credits_browser = QTextBrowser()
        credits_browser.setOpenExternalLinks(True)
        credits_browser.setHtml(r"""
        <p>Graphica は、CSV/Excelファイルからデータを読み込み、グラフの作成・編集・
        エクスポートを行うためのデータ可視化ソフトウェアです。</p>
        <h3>使用ライブラリ</h3>
        <ul>
            <li>PySide6 (LGPLv3)</li>
            <li>Matplotlib (PSFベースのライセンス)</li>
            <li>NumPy (BSD 3-Clause)</li>
            <li>pandas (BSD 3-Clause)</li>
            <li>SciPy (BSD 3-Clause)</li>
            <li>openpyxl (MIT)</li>
        </ul>
        <p>各ライブラリの詳細なライセンス条文は、それぞれの配布元をご確認ください。</p>
        """)
        layout.addWidget(credits_browser)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


#==============================================================================
# カスタムダイアログクラス: 初回起動時のウェルカム画面
#==============================================================================
class WelcomeDialog(QDialog):
    """
    初回起動時にだけ表示するウェルカムダイアログ。
    簡単な操作ガイドと、すぐに試せるサンプルデータの読み込みボタンを提供する。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.version import APP_NAME
        from core.i18n import tr

        self.setWindowTitle(tr("{app} へようこそ").format(app=APP_NAME))
        self.resize(460, 420)
        self.load_sample_requested = False

        layout = QVBoxLayout(self)

        if parent is not None:
            icon_label = QLabel()
            pixmap = parent.windowIcon().pixmap(64, 64)
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap)
                icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                layout.addWidget(icon_label)

        title_label = QLabel(f"<h2>{tr('{app} へようこそ').format(app=APP_NAME)}</h2>")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title_label)

        guide_browser = QTextBrowser()
        guide_browser.setHtml(r"""
        <p>{app}は、CSV/Excelファイルからデータを読み込み、グラフの作成・編集・
        エクスポートを行うためのデータ可視化ソフトウェアです。</p>
        <h3>はじめの一歩</h3>
        <ol>
            <li><b>「データ追加」</b>ボタンでCSV/Excelファイルを読み込む
                (下の「サンプルデータを開く」からすぐに試すこともできます)</li>
            <li>X軸・Y軸に使う列を選択する</li>
            <li>右側の「データセットのプロパティ」パネルで色・線種・マーカーなどを調整する</li>
            <li>「曲線フィット」「ピーク検出」などの解析機能を試す</li>
            <li>「ファイル」メニューの「名前を付けてエクスポート」で画像として保存する</li>
        </ol>
        <p>このガイドは初回起動時にのみ表示されます。「ヘルプ」メニューからいつでも
        各種リファレンスを確認できます。</p>
        """.format(app=APP_NAME))
        layout.addWidget(guide_browser)

        button_row = QHBoxLayout()
        self.load_sample_button = QPushButton(tr("サンプルデータを開く"))
        self.load_sample_button.clicked.connect(self._on_load_sample_clicked)
        button_row.addWidget(self.load_sample_button)
        button_row.addStretch()

        close_button = QPushButton(tr("閉じる"))
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def _on_load_sample_clicked(self):
        self.load_sample_requested = True
        self.accept()


#==============================================================================
# カスタムダイアログクラス (1)
#==============================================================================
class HelpDialog(QDialog):
    """
    Matplotlib の mathtext (数式表示機能) の簡易リファレンスを表示する
    ヘルプダイアログクラスです。
    """

    def __init__(self, parent=None):
        """
        ダイアログの初期化を行います。
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("mathtext クイックリファレンス")
        self.resize(600, 700) # ウィンドウサイズを固定（リサイズ可能にする場合は resize の代わりに setMinimumSize なども検討）

        # メインレイアウトとして QVBoxLayout (垂直レイアウト) を設定
        layout = QVBoxLayout(self)

        # HTML を表示するための QTextBrowser を作成
        text_browser = QTextBrowser()
        text_browser.setReadOnly(True) # 閲覧専用に設定
        text_browser.setOpenExternalLinks(True) # (もしHTML内にリンクがあれば) 外部ブラウザで開く

        # --- リファレンスの内容をHTMLで定義 ---
        # r"""...""" (Raw Triple-Quoted String) を使うことで、
        # バックスラッシュ '\' をエスケープシーケンスとして解釈させず、
        # LaTeX のコマンド (例: \mathbf) をそのまま記述できます。
        help_html = r"""
        <h1>Matplotlib Mathtext クイックリファレンス</h1>
        <p>
            <code>mathtext</code> は、プロットラベル（タイトル、軸ラベル、凡例など）に、LaTeXのような数式や特殊文字を簡単に入力するための機能です。
        </p>
        <p>
            テキストボックスに入力する文字列を <b>$</b>（ドルマーク）で囲むと、その中身が数式として解釈されます。
        </p>
        
        <hr>
        
        <h2>1. 基本的な書式 (太字・イタリック) 🎨</h2>
        <p>ラベルの一部分、または全体を特定の書式に変更できます。</p>
        <ul>
            <li><b>太字 (Bold)</b>: <code>$\mathbf{...}$</code></li>
            <li><b>イタリック (Italic)</b>: <code>$\mathit{...}$</code></li>
            <li><b>立体 (Roman/標準)</b>: <code>$\mathrm{...}$</code></li>
        </ul>
        
        <h4>✅ 組み合わせの例</h4>
        <p>「<b>Speed</b> (<i>v</i>)」と表示したい場合：</p>
        <p><b>入力</b>: <code>$\mathbf{Speed}\ \mathit{(v)}$</code></p>
        <p>
            <ul>
                <li><code>\ </code> (バックスラッシュ + スペース) は、数式内で強制的にスペースを入れたい場合に使います。</li>
            </ul>
        </p>
        <p>「Velocity (m/s)」のように、イタリックにしたくない単位（立体にしたい）場合：</p>
        <p><b>入力</b>: <code>$\mathrm{Velocity\ (m/s)}$</code></p>

        <hr>

        <h2>2. 上付き文字 と 下付き文字</h2>
        <ul>
            <li><b>上付き文字</b>: <code>^</code> （ハット）</li>
            <li><b>下付き文字</b>: <code>_</code> （アンダースコア）</li>
        </ul>
        <p>文字が1文字以上の場合は、<code>{}</code>（中括弧）で囲みます。</p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい文字</th>
                <th>入力するテキスト</th>
            </tr>
            <tr>
                <td>10<sup>3</sup></td>
                <td><code>$10^3$</code></td>
            </tr>
            <tr>
                <td>10<sup>-3</sup></td>
                <td><code>$10^{-3}$</code></td>
            </tr>
            <tr>
                <td>V<sub>max</sub></td>
                <td><code>$V_{\mathrm{max}}$</code></td>
            </tr>
            <tr>
                <td>k<sub>B</sub></td>
                <td><code>$k_{\mathrm{B}}$</code></td>
            </tr>
        </table>
        
        <hr>
        
        <h2>3. よく使う特殊文字・記号 🇬🇷</h2>
        
        <h4>ギリシャ文字</h4>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい文字</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>&alpha; (アルファ)</td><td><code>$\alpha$</code></td></tr>
            <tr><td>&beta; (ベータ)</td><td><code>$\beta$</code></td></tr>
            <tr><td>&gamma; (ガンマ)</td><td><code>$\gamma$</code></td></tr>
            <tr><td>&Delta; (デルタ大文字)</td><td><code>$\Delta$</code></td></tr>
            <tr><td>&delta; (デルタ小文字)</td><td><code>$\delta$</code></td></tr>
            <tr><td>&epsilon; (イプシロン)</td><td><code>$\epsilon$</code></td></tr>
            <tr><td>&mu; (ミュー)</td><td><code>$\mu$</code></td></tr>
            <tr><td>&pi; (パイ)</td><td><code>$\pi$</code></td></tr>
            <tr><td>&rho; (ロー)</td><td><code>$\rho$</code></td></tr>
            <tr><td>&Sigma; (シグマ大文字)</td><td><code>$\Sigma$</code></td></tr>
            <tr><td>&sigma; (シグマ小文字)</td><td><code>$\sigma$</code></td></tr>
            <tr><td>&tau; (タウ)</td><td><code>$\tau$</code></td></tr>
            <tr><td>&Omega; (オメガ大文字)</td><td><code>$\Omega$</code></td></tr>
            <tr><td>&omega; (オメガ小文字)</td><td><code>$\omega$</code></td></tr>
        </table>

        <h4>単位・記号</h4>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい文字</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>°C (温度)</td><td><code>$^{\circ}$C</code></td></tr>
            <tr><td>&pm; (プラスマイナス)</td><td><code>$\pm$</code></td></tr>
            <tr><td>&middot; (中点ドット)</td><td><code>$\cdot$</code></td></tr>
            <tr><td>&times; (掛ける)</td><td><code>$\times$</code></td></tr>
            <tr><td>&approx; (ほぼイコール)</td><td><code>$\approx$</code></td></tr>
        </table>

        <hr>
        
        <h2>4. 分数 と 根号</h2>
        <ul>
            <li><b>分数</b>: <code>$\frac{分子}{分母}$</code> (例: <code>$\frac{1}{2}$</code>)</li>
            <li><b>平方根 (ルート)</b>: <code>$\sqrt{...}$</code> (例: <code>$\sqrt{2}$</code>)</li>
        </ul>

        <hr>

        <h2>5. 総和・積分・極限などの演算子</h2>
        <p>
            <code>^</code>・<code>_</code>と組み合わせて、上下に添え字を付けられます。
        </p>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい記号</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>&sum; (総和)</td><td><code>$\sum_{i=0}^{n}$</code></td></tr>
            <tr><td>&prod; (総乗)</td><td><code>$\prod_{i=1}^{n}$</code></td></tr>
            <tr><td>&int; (積分)</td><td><code>$\int_{0}^{\infty}$</code></td></tr>
            <tr><td>&part; (偏微分)</td><td><code>$\partial$</code></td></tr>
            <tr><td>&nabla; (ナブラ)</td><td><code>$\nabla$</code></td></tr>
            <tr><td>&infin; (無限大)</td><td><code>$\infty$</code></td></tr>
        </table>

        <h4>矢印・比較演算子</h4>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい記号</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>&rarr; (右矢印)</td><td><code>$\rightarrow$</code></td></tr>
            <tr><td>&harr; (両矢印)</td><td><code>$\leftrightarrow$</code></td></tr>
            <tr><td>&le; (以下)</td><td><code>$\leq$</code></td></tr>
            <tr><td>&ge; (以上)</td><td><code>$\geq$</code></td></tr>
            <tr><td>&ne; (等しくない)</td><td><code>$\neq$</code></td></tr>
        </table>

        <h4>文字の上に記号を付ける</h4>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい記号</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>x&#772; (上線・平均値など)</td><td><code>$\overline{x}$</code></td></tr>
            <tr><td>x&#8407; (ベクトル)</td><td><code>$\vec{x}$</code></td></tr>
            <tr><td>x&#770; (ハット)</td><td><code>$\hat{x}$</code></td></tr>
        </table>

        <p style="color:#888; margin-top: 12px;">
            ※ ここに載っている記法は、いずれもタイトル/軸ラベル欄にそのまま
            半角文字で入力すれば動作します(<code>Aa</code>ボタンの装飾メニューに
            あるΩボタンからも、よく使うギリシャ文字を選択部分の挿入なしでカーソル
            位置に差し込めます)。<br>
            なお、これは matplotlib 内蔵の軽量な数式パーサー(mathtext)であり、
            <code>\begin{matrix}</code> のような複雑なLaTeX環境や外部LaTeXパッケージ
            には対応していません。
        </p>
        """
        # ★ 項目H-2-6(実機での目視確認で発覚): 表内の見出し行はHTML内に
        #   `background-color: #f0f0f0`のような固定の薄いグレーをハード
        #   コードしていたため、ダークモードでは見出しセルがほぼ見えない
        #   薄グレーの塊になり、文字も読めなくなっていた(ライトモードは
        #   問題なかった)。見出し行はクラス名(class="header-row")だけを
        #   HTML側に残し、実際の色はQTextDocumentのdefault stylesheetで
        #   現在のテーマトークンから注入することで、ダーク/ライト両方で
        #   読めるようにする。
        from gui import theme
        _tokens = theme.current_tokens()
        text_browser.document().setDefaultStyleSheet(
            f"tr.header-row {{ background-color: {_tokens['surface_2']}; "
            f"color: {_tokens['text_primary']}; }}"
        )
        # HTMLコンテンツを QTextBrowser にセット
        text_browser.setHtml(help_html)
        # --- HTML定義ここまで ---

        # レイアウトにテキストブラウザを追加
        layout.addWidget(text_browser)
        
        # --- 閉じるボタンの追加 ---
        # QDialogButtonBox を使うと、プラットフォーム標準のボタン配置（OK, Cancel, Closeなど）
        # を簡単に実現できます。
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        
        # 'rejected' シグナル（CloseボタンやEscキー押下で発生）を、
        # QDialog の標準スロット 'reject'（ダイアログを閉じる処理）に接続します。
        button_box.rejected.connect(self.reject)
        
        # レイアウトにボタンボックスを追加
        layout.addWidget(button_box)


#==============================================================================
# カスタムダイアログクラス (2)
#==============================================================================
class CalcHelpDialog(QDialog):
    """
    データエディタの「列計算」機能のリファレンスを表示するヘルプダイアログクラスです。
    core/safe_eval.py の safe_eval_column_formula() で使用できる構文について説明します。
    """
    
    def __init__(self, parent=None):
        """
        ダイアログの初期化を行います。
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("列計算機能 リファレンス")
        self.resize(600, 700) # ウィンドウサイズを指定

        # メインレイアウト (垂直)
        layout = QVBoxLayout(self)
        
        # HTML表示用のテキストブラウザ
        text_browser = QTextBrowser()
        text_browser.setReadOnly(True)
        # ★ HTML内のリンクをクリックしたときに外部ブラウザで開くように設定
        text_browser.setOpenExternalLinks(True) 
        
        # --- リファレンスの内容をHTMLで定義 ---
        help_html = r"""
        <h1>列計算機能 リファレンス</h1>
        <p>
            計算式を使って、列データをまとめて計算します。
            「出力先の列」に指定した列に、計算式の結果が一度に適用されます（Excelのオートフィルのように、全行に適用されます）。
        </p>
        
        <hr>
        
        <h2>1. 基本的な算術演算子 🧮</h2>
        <p>列名（例: <code>A</code>, <code>B</code>）や数値をそのまま使えます。</p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row"><th>計算式 (入力例)</th><th>実行内容</th></tr>
            <tr><td><code>A + B</code></td><td>A列とB列の各行を足し算します。</td></tr>
            <tr><td><code>A * 100</code></td><td>A列の全データを100倍します。</td></tr>
            <tr><td><code>(A + B) / 2</code></td><td>A列とB列の平均値を計算します。</td></tr>
            <tr><td><code>A ** 2</code></td><td>A列の値を2乗します。</td></tr>
            <tr><td><code>A % 5</code></td><td>A列の値を5で割った余りを計算します。</td></tr>
        </table>
        
        <hr>
        
        <h2>2. 一般的な数学関数 📈</h2>
        <p>
            以下の関数が利用可能です。
        </p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row"><th>関数 (入力例)</th><th>意味</th></tr>
            <tr><td><code>sqrt(A)</code></td><td>Aの平方根 (&radic;A)</td></tr>
            <tr><td><code>log(A)</code></td><td>Aの自然対数 (ln A)</td></tr>
            <tr><td><code>log10(A)</code></td><td>Aの常用対数 (log₁₀ A)</td></tr>
            <tr><td><code>exp(A)</code></td><td>Aの指数関数 (e<sup>A</sup>)</td></tr>
            <tr><td><code>abs(A)</code></td><td>Aの絶対値</td></tr>
            <tr><td><code>sin(A)</code></td><td>Aのサイン (ラジアン)</td></tr>
            <tr><td><code>cos(A)</code></td><td>Aのコサイン (ラジアン)</td></tr>
            <tr><td><code>tan(A)</code></td><td>Aのタンジェント (ラジアン)</td></tr>
        </table>

        <hr>
        
        <h2>3. 比較・論理演算子 🔍</h2>
        <p>
            条件に合うかどうかを <code>True</code> / <code>False</code> で返す新しい列を作成できます。
            複数の条件を組み合わせる場合は <code>and</code>, <code>or</code>, <code>not</code> を使います。
        </p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row"><th>計算式 (入力例)</th><th>実行内容</th></tr>
            <tr><td><code>A > 10</code></td><td>A列の値が10より大きい行はTrueになります。</td></tr>
            <tr><td><code>A == B</code></td><td>A列とB列の値が等しい行はTrueになります。</td></tr>
            <tr><td><code>A > 5 and B < 3</code></td><td>Aが5より大きく、<b>かつ</b> Bが3未満の行だけTrueになります。</td></tr>
            <tr><td><code>A < 0 or A > 10</code></td><td>Aが0未満、<b>または</b> Aが10より大きい行がTrueになります。</td></tr>
            <tr><td><code>not (A > 5)</code></td><td>Aが5より大きい、という条件を否定します (A <= 5 と同じ)。</td></tr>
        </table>
        """
        # ★ 項目H-2-6(実機での目視確認で発覚): HelpDialogと同じく、見出し行の
        #   背景色をハードコードせずテーマトークンから注入する
        #   (詳しい経緯はHelpDialog.__init__のコメント参照)。
        from gui import theme
        _tokens = theme.current_tokens()
        text_browser.document().setDefaultStyleSheet(
            f"tr.header-row {{ background-color: {_tokens['surface_2']}; "
            f"color: {_tokens['text_primary']}; }}"
        )
        text_browser.setHtml(help_html)
        # --- HTML定義ここまで ---

        layout.addWidget(text_browser)

        # 閉じるボタン
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class ResultDialog(QDialog):
    """
    曲線フィット/ピーク検出などの結果テキストを表示するための汎用ダイアログ。

    ピーク検出結果は検出数が多いと行数が非常に多くなりうるため、
    QMessageBox (スクロール不可、画面からはみ出る) ではなく、
    スクロール可能な QPlainTextEdit で表示する。
    csv_data (DataFrame) を渡すと「CSVとして保存」ボタンも表示される。
    """

    def __init__(self, title, text, parent=None, csv_data=None, residual_x=None, residual_y=None):
        """
        Args:
            title (str): ウィンドウタイトル。
            text (str): 表示する結果テキスト (複数行可)。
            parent (QWidget, optional): 親ウィジェット。
            csv_data (pandas.DataFrame, optional): CSV保存用の構造化データ。
                None の場合は「CSVとして保存」ボタンを表示しない
                (表示テキストをそのままパースするのではなく、呼び出し側が
                 意味のある表形式データを渡す設計にしている)。
            residual_x (array-like, optional): 曲線フィットの残差プロット用のX座標。
            residual_y (array-like, optional): 曲線フィットの残差 (実測値-フィット値)。
                residual_x/residual_y を両方渡すと、当てはまりの良し悪しを視覚的に
                確認できる残差プロット(0を基準にした散布図)を追加表示する。
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(480, 420)
        self.csv_data = csv_data

        layout = QVBoxLayout(self)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(text)
        # 等幅フォントにすることで、タブ区切りのX/Y座標の桁が揃って見やすくなる
        mono_font = QFont("Consolas")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self.text_edit.setFont(mono_font)
        layout.addWidget(self.text_edit)

        if residual_x is not None and residual_y is not None and len(residual_x) > 0:
            self.resize(480, 620)
            layout.addWidget(QLabel("残差プロット (実測値 - フィット値)"))
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            fig = Figure(figsize=(4, 2.2), dpi=100, tight_layout=True)
            canvas = FigureCanvasQTAgg(fig)
            canvas.setFixedHeight(200)
            ax = fig.add_subplot(111)
            ax.axhline(0, color='gray', linewidth=0.8, linestyle='--')
            ax.scatter(residual_x, residual_y, s=14, color='#1F6F78')
            ax.set_xlabel("X", fontsize=8)
            ax.set_ylabel("残差", fontsize=8)
            ax.tick_params(labelsize=7)
            layout.addWidget(canvas)

        button_layout = QHBoxLayout()

        self.copy_button = QPushButton("コピー")
        self.copy_button.clicked.connect(self._on_copy)
        button_layout.addWidget(self.copy_button)

        if csv_data is not None:
            save_csv_button = QPushButton("CSVとして保存...")
            save_csv_button.clicked.connect(self._on_save_csv)
            button_layout.addWidget(save_csv_button)

        button_layout.addStretch()

        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.reject)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

    def _on_copy(self):
        """表示中のテキストをクリップボードにコピーし、ボタンに一時的なフィードバックを表示する"""
        QApplication.clipboard().setText(self.text_edit.toPlainText())
        original_text = self.copy_button.text()
        self.copy_button.setText("コピーしました ✓")
        self.copy_button.setEnabled(False)

        def _restore():
            self.copy_button.setText(original_text)
            self.copy_button.setEnabled(True)

        QTimer.singleShot(1200, _restore)

    def _on_save_csv(self):
        """csv_data (DataFrame) をCSVファイルとして保存する"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "CSVとして保存", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return
        try:
            self.csv_data.to_csv(file_path, index=False, encoding='utf-8-sig')
            QMessageBox.information(self, "保存完了", f"CSVファイルとして保存しました:\n{file_path}")
        except Exception as e:
            QMessageBox.warning(self, "保存エラー", f"CSV保存中にエラーが発生しました:\n{e}")


#==============================================================================
# カスタムダイアログクラス (3)
#==============================================================================
class PeakSettingsDialog(QDialog):
    """
    ピーク検出 (find_peaks) のパラメータを入力するためのダイアログクラスです。
    
    scipy.signal.find_peaks の height, distance, prominence に対応する値を
    ユーザーが入力できるようにします。
    """
    
    def __init__(self, parent=None):
        """
        ダイアログのUIコンポーネントを初期化します。
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("ピーク検出 設定")
        
        # UIのレイアウトとして QFormLayout を使用 (ラベル: [入力欄] の形式に最適)
        layout = QFormLayout(self)

        # --- 検出タイプの選択 ---
        self.type_combo = QComboBox()
        self.type_combo.addItems(["上に凸 (Peaks)", "下に凸 (Valleys)"])
        # insertRow(0, ...) で、レイアウトの先頭 (0行目) に挿入
        layout.insertRow(0, "検出タイプ", self.type_combo)

        # --- 最小高さ (height) ---
        self.height_spinbox = QDoubleSpinBox()
        self.height_spinbox.setToolTip("検出するピーク/谷の最小高さ (Y値)。\n例: 5 を指定すると Y > 5 のピークのみ検出。\n例: -10 を指定すると Y < -10 の谷のみ検出。")
        self.height_spinbox.setDecimals(4) # 小数点以下4桁まで
        self.height_spinbox.setRange(-np.inf, np.inf) # 負の値（谷の閾値）も許容
        self.height_spinbox.setValue(0.0) # デフォルト値
        
        # --- 最小距離 (distance) ---
        self.distance_spinbox = QDoubleSpinBox()
        self.distance_spinbox.setToolTip("隣接するピーク/谷の間の最小距離 (X軸の値)。\n近すぎるピーク/谷を間引きます。")
        self.distance_spinbox.setDecimals(4)
        self.distance_spinbox.setRange(0.0001, np.inf) # 0より大きい値である必要がある
        self.distance_spinbox.setValue(1.0) # デフォルト値
        
        # --- 突出度 (prominence) ---
        self.prominence_spinbox = QDoubleSpinBox()
        self.prominence_spinbox.setToolTip("ピーク/谷の突出度 (周囲のデータからの際立ち)。\nノイズのような小さなピーク/谷を除去するのに有効です。")
        self.prominence_spinbox.setDecimals(4)
        self.prominence_spinbox.setRange(0.0, np.inf) # 0以上
        self.prominence_spinbox.setValue(0.0) # デフォルトは 0 (無効)
        
        # --- フォームに行を追加 ---
        layout.addRow("Y値の閾値 (Height)", self.height_spinbox)
        layout.addRow("最小X距離 (Distance)", self.distance_spinbox)
        layout.addRow("最小突出度 (Prominence)", self.prominence_spinbox)
        
        # --- OK / Cancel ボタン ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept) # OK が押されたら accept
        button_box.rejected.connect(self.reject) # Cancel が押されたら reject
        layout.addRow(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        ダイアログで入力された設定値を辞書として返します。
        
        Returns:
            dict: ユーザーが入力した設定値。
        """
        # distance は find_peaks 関数では「データ点数(index)」で指定する必要があるため、
        # ここではX軸の値を "distance_x" として返し、呼び出し側 (_on_find_peaks) で
        # データ点数に変換する設計になっています。
        
        # prominence が 0 の場合は、None (無効) として返す
        prominence_value = self.prominence_spinbox.value()
        
        return {
            "peak_type": self.type_combo.currentText(),
            "height": self.height_spinbox.value(),
            "distance_x": self.distance_spinbox.value(), # X軸での距離
            "prominence": prominence_value if prominence_value > 0 else None
        }

    @staticmethod
    def get_peak_settings(parent=None):
        """
        【スタティックメソッド】
        ダイアログをモーダルで表示し、OKが押された場合は設定辞書を、
        Cancelが押された場合は None を返します。
        
        これにより、呼び出し側は以下の1行で済みます。
        settings = PeakSettingsDialog.get_peak_settings(self)
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
        
        Returns:
            dict or None: 設定辞書、または None。
        """
        dialog = PeakSettingsDialog(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_settings()
        return None


#==============================================================================
# カスタムダイアログクラス (4)
#==============================================================================
class FitDialog(QDialog):
    """
    曲線フィット (Curve Fitting) を行う際に、
    どの関数モデル（線形、多項式など）を使用するかをユーザーに選択させるダイアログクラスです。
    """
    
    def __init__(self, parent=None, x_min=None, x_max=None):
        """
        ダイアログのUIコンポーネントを初期化します。

        Args:
            parent (QWidget, optional): 親ウィジェット。
            x_min (float, optional): フィット範囲指定欄の初期値(最小X)。
                通常は対象データセットの実際のXの最小値を渡す。
            x_max (float, optional): フィット範囲指定欄の初期値(最大X)。
        """
        super().__init__(parent)
        self.setWindowTitle("曲線フィット")

        # メインレイアウト (垂直)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("フィットする関数の種類を選択してください:"))
        
        # --- 関数選択のコンボボックス ---
        self.fit_type_combo = QComboBox()
        self.fit_type_combo.addItems([
            "線形 (y = ax + b)",
            "2次多項式 (y = ax^2 + bx + c)",
            "3次多項式 (y = ax^3 + bx^2 + cx + d)",
            "指数関数 (y = a * exp(bx))",
            "対数 (y = a * ln(x) + b)",
            "べき乗 (y = a * x^b)",
            "ガウシアン (y = a * exp(-(x-b)^2 / (2c^2)) + d)",
            "シグモイド (y = a / (1 + exp(-b(x-c))))",
        ])
        # プラグインが追加したフィット関数を、組み込みの選択肢と
        # 「カスタム数式...」の間に挿入する
        from core.analysis import get_plugin_fit_type_names
        self.fit_type_combo.addItems(get_plugin_fit_type_names())
        self.fit_type_combo.addItem("カスタム数式...")
        self.fit_type_combo.currentTextChanged.connect(self._on_fit_type_changed)
        layout.addWidget(self.fit_type_combo)

        # --- カスタム数式入力欄 (「カスタム数式...」選択時のみ表示) ---
        self.custom_formula_label = QLabel("数式 (xとパラメータ名を使って入力、例: a*exp(-b*x)+c)")
        self.custom_formula_edit = QLineEdit()
        self.custom_formula_edit.setPlaceholderText("a*exp(-b*x)+c")
        self.custom_formula_label.setVisible(False)
        self.custom_formula_edit.setVisible(False)
        layout.addWidget(self.custom_formula_label)
        layout.addWidget(self.custom_formula_edit)

        # --- 重み付きフィット(項目C-402) ---
        self.weighted_checkbox = QCheckBox("Y誤差列を重みとして使用する(設定されている場合)")
        self.weighted_checkbox.setToolTip(
            "誤差が大きい点ほどフィットへの影響を小さくする(scipy.optimize.curve_fitのsigma)。\n"
            "対象データセットにY誤差列が設定されていない場合はチェックしても効果がありません。"
        )
        layout.addWidget(self.weighted_checkbox)

        # --- フィット範囲の指定(項目C-404) ---
        self.range_checkbox = QCheckBox("フィット範囲を指定する")
        layout.addWidget(self.range_checkbox)

        range_form = QFormLayout()
        self.range_min_spinbox = QDoubleSpinBox()
        self.range_min_spinbox.setRange(-1e12, 1e12)
        self.range_min_spinbox.setDecimals(6)
        self.range_min_spinbox.setEnabled(False)
        if x_min is not None:
            self.range_min_spinbox.setValue(x_min)
        range_form.addRow("最小X", self.range_min_spinbox)

        self.range_max_spinbox = QDoubleSpinBox()
        self.range_max_spinbox.setRange(-1e12, 1e12)
        self.range_max_spinbox.setDecimals(6)
        self.range_max_spinbox.setEnabled(False)
        if x_max is not None:
            self.range_max_spinbox.setValue(x_max)
        range_form.addRow("最大X", self.range_max_spinbox)
        layout.addLayout(range_form)

        self.range_checkbox.toggled.connect(self.range_min_spinbox.setEnabled)
        self.range_checkbox.toggled.connect(self.range_max_spinbox.setEnabled)

        # --- OK / Cancel ボタン ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_fit_type_changed(self, text):
        """フィット関数の選択が変わったときに、カスタム数式入力欄の表示/非表示を切り替える"""
        is_custom = "カスタム数式" in text
        self.custom_formula_label.setVisible(is_custom)
        self.custom_formula_edit.setVisible(is_custom)

    def get_weighted(self):
        """Y誤差列を重みとして使うかどうか"""
        return self.weighted_checkbox.isChecked()

    def get_x_range(self):
        """
        Returns:
            tuple(float, float) | None: フィット範囲指定が有効なら(最小X, 最大X)、
            無効ならNone。
        """
        if not self.range_checkbox.isChecked():
            return None
        return (self.range_min_spinbox.value(), self.range_max_spinbox.value())

    @staticmethod
    def get_fit_type(parent=None, x_min=None, x_max=None):
        """
        【スタティックメソッド】
        ダイアログをモーダルで表示し、OKが押された場合は
        (フィットタイプ名, カスタム数式またはNone, 重み付けを使うか, フィット範囲
        またはNone) のタプルを、Cancelが押された場合は (None, None, False, None) を
        返します。

        Args:
            parent (QWidget, optional): 親ウィジェット。
            x_min (float, optional): フィット範囲指定欄の初期値(最小X)。
            x_max (float, optional): フィット範囲指定欄の初期値(最大X)。

        Returns:
            tuple (str|None, str|None, bool, tuple(float,float)|None):
            (フィットタイプ名, カスタム数式, 重み付けを使うか, フィット範囲)
        """
        dialog = FitDialog(parent, x_min=x_min, x_max=x_max)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            fit_type = dialog.fit_type_combo.currentText()
            custom_formula = dialog.custom_formula_edit.text().strip() if "カスタム数式" in fit_type else None
            return fit_type, custom_formula, dialog.get_weighted(), dialog.get_x_range()
        return None, None, False, None


#==============================================================================
# カスタムダイアログクラス (5)
#==============================================================================
class ColumnCalculatorDialog(QDialog):
    """
    データエディタの「列の計算」機能で使用するダイアログクラスです。
    出力先（新規または既存）の列名と、safe_eval_column_formula() で実行する
    計算式をユーザーに入力させます。
    """
    
    def __init__(self, column_names, parent=None):
        """
        ダイアログのUIコンポーネントを初期化します。
        
        Args:
            column_names (list[str]): 
                現在の DataFrame に存在する列名のリスト。コンボボックスの選択肢として使用されます。
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("列の計算")
        
        self.column_names = column_names
        
        # --- UIコンポーネントの作成 ---
        
        self.output_col_label = QLabel("出力先の列 (既存または新規)")
        
        # --- 出力先コンボボックス ---
        self.output_col_combo = QComboBox()
        self.output_col_combo.addItems(self.column_names) # 既存の列を選択肢に追加
        # ★ setEditable(True) が重要
        # これにより、ユーザーは既存の列を選択するだけでなく、
        # テキストボックスのように新しい列名を自由に入力できます。
        self.output_col_combo.setEditable(True) 
        
        self.formula_label = QLabel("計算式 (例: A + B * 2)")

        # --- 計算式入力欄 ---
        self.formula_edit = QLineEdit()
        # ★ (入力例をプレースホルダーとして表示)
        self.formula_edit.setPlaceholderText("例: (A + B) / 2 や log(C)")

        # --- ヘルプテキスト ---
        help_text = QLabel("列名はそのまま使えます (例: `A`)。\n数値や `log(A)`, `sin(A)` なども利用可能です。")
        help_text.setStyleSheet("font-size: 9pt; color: gray;") # 少し小さく灰色で表示

        # --- プリセット (よく使う計算をボタン一つで挿入) ---
        preset_group = QGroupBox("プリセット (対象列を選んでボタンを押すと計算式が自動入力されます)")
        preset_layout = QVBoxLayout()

        preset_source_row = QHBoxLayout()
        preset_source_row.addWidget(QLabel("対象列"))
        self.preset_source_combo = QComboBox()
        self.preset_source_combo.addItems(self.column_names)
        preset_source_row.addWidget(self.preset_source_combo)
        preset_source_row.addWidget(QLabel("移動平均の窓幅"))
        self.preset_window_spinbox = QSpinBox()
        self.preset_window_spinbox.setRange(2, 100000)
        self.preset_window_spinbox.setValue(5)
        preset_source_row.addWidget(self.preset_window_spinbox)
        preset_layout.addLayout(preset_source_row)

        preset_button_row = QHBoxLayout()
        moving_avg_button = QPushButton("移動平均")
        moving_avg_button.clicked.connect(self._apply_preset_moving_average)
        diff_button = QPushButton("微分(差分)")
        diff_button.clicked.connect(self._apply_preset_diff)
        normalize_button = QPushButton("正規化")
        normalize_button.clicked.connect(self._apply_preset_normalize)
        cumsum_button = QPushButton("累積和")
        cumsum_button.clicked.connect(self._apply_preset_cumsum)
        for btn in (moving_avg_button, diff_button, normalize_button, cumsum_button):
            preset_button_row.addWidget(btn)
        preset_layout.addLayout(preset_button_row)

        preset_group.setLayout(preset_layout)

        # --- OK / Cancel ボタン ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # --- レイアウト ---
        # (このダイアログは QFormLayout ではなく QVBoxLayout (垂直) を使用)
        layout = QVBoxLayout(self)
        layout.addWidget(self.output_col_label)
        layout.addWidget(self.output_col_combo)
        layout.addWidget(self.formula_label)
        layout.addWidget(self.formula_edit)
        layout.addWidget(help_text)
        layout.addWidget(preset_group)
        layout.addWidget(button_box)

    def _apply_preset_moving_average(self):
        """「移動平均」プリセットボタン: 選択列に rolling().mean() の式を入力する"""
        col = self.preset_source_combo.currentText()
        if not col:
            return
        window = self.preset_window_spinbox.value()
        self.formula_edit.setText(f"{col}.rolling({window}).mean()")
        self.output_col_combo.setCurrentText(f"{col}_moving_avg{window}")

    def _apply_preset_diff(self):
        """「微分(差分)」プリセットボタン: 選択列に diff() の式を入力する"""
        col = self.preset_source_combo.currentText()
        if not col:
            return
        self.formula_edit.setText(f"{col}.diff()")
        self.output_col_combo.setCurrentText(f"{col}_diff")

    def _apply_preset_normalize(self):
        """「正規化」プリセットボタン: 選択列を平均0・標準偏差1に正規化する式を入力する"""
        col = self.preset_source_combo.currentText()
        if not col:
            return
        self.formula_edit.setText(f"({col} - {col}.mean()) / {col}.std()")
        self.output_col_combo.setCurrentText(f"{col}_normalized")

    def _apply_preset_cumsum(self):
        """「累積和」プリセットボタン: 選択列に cumsum() の式を入力する"""
        col = self.preset_source_combo.currentText()
        if not col:
            return
        self.formula_edit.setText(f"{col}.cumsum()")
        self.output_col_combo.setCurrentText(f"{col}_cumsum")

    def get_formula(self):
        """
        ダイアログで入力された「出力先列名」と「計算式」をタプルで返します。
        
        Returns:
            tuple (str, str): (出力先列名, 計算式)
        """
        # QComboBox が setEditable(True) の場合、
        # currentText() は、選択されたアイテムまたは入力されたテキストを返します。
        output_column_name = self.output_col_combo.currentText()
        formula_string = self.formula_edit.text()
        
        return output_column_name, formula_string


#==============================================================================
# カスタムダイアログクラス (6)
#==============================================================================
class ExportDialog(QDialog):
    """
    プロット（Matplotlib の Figure）を画像ファイルとしてエクスポートする際に、
    出力サイズ、単位、解像度(DPI)を指定するためのカスタムダイアログクラスです。
    
    プレビュー表示用のUIも持ちますが、プレビューの生成ロジック自体は
    呼び出し側 (PlotterApp._generate_preview) が担当します。
    """
    def __init__(self, parent=None):
        """
        ダイアログのUIコンポーネントを初期化します。
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("プロットのエクスポート")

        # --- UIコンポーネントの作成 ---

        # 幅 (Width)
        self.width_spinbox = QDoubleSpinBox()
        self.width_spinbox.setRange(1, 10000) # 1から10000の範囲
        self.width_spinbox.setValue(800)      # デフォルト値 800
        self.width_spinbox.setDecimals(1)     # ★ 小数点以下1桁まで許可 (インチ指定などのため)

        # 高さ (Height)
        self.height_spinbox = QDoubleSpinBox()
        self.height_spinbox.setRange(1, 10000)
        self.height_spinbox.setValue(600)
        self.height_spinbox.setDecimals(1)     # ★ 小数点以下1桁まで許可

        # 単位 (Unit)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["ピクセル (px)", "インチ (in)", "センチメートル (cm)"])

        # 解像度 (DPI)
        self.dpi_spinbox = QSpinBox() # DPIは整数値なので QSpinBox
        self.dpi_spinbox.setRange(50, 1200) # 50から1200 DPI
        self.dpi_spinbox.setValue(300)      # デフォルト値 300 (印刷用途を想定)
        self.dpi_spinbox.setSuffix(" dpi")  # " dpi" という接尾辞を表示

        # 背景の透過(項目108): 以前は常にtransparent=Trueで固定していたが、
        # スライド資料等で背景色を保ちたい場合もあるため選択可能にする
        self.transparent_checkbox = QCheckBox("背景を透過")
        self.transparent_checkbox.setChecked(True)

        # SVG出力時の文字の扱い(項目88): 既定はテキスト要素として保持(検索・
        # 再編集がしやすい)。フォントが無い環境での文字化けを避けたい場合のみ
        # チェックしてアウトライン化(パス化)する。PNG/PDFには影響しない。
        self.svg_text_as_path_checkbox = QCheckBox("文字をアウトライン化する(SVG)")
        self.svg_text_as_path_checkbox.setToolTip(
            "SVG出力時、目盛りの数字やラベルの文字をテキスト要素ではなく"
            "パス(輪郭線)として出力します。フォントが無い環境でも見た目が"
            "崩れませんが、テキストとしての検索・編集はできなくなります。"
        )

        # --- プレビュー関連 ---
        self.preview_button = QPushButton("プレビュー更新")
        self.preview_button.setToolTip("現在の設定でプレビュー画像を生成します。")
        
        self.preview_label = QLabel("プレビューがここに表示されます")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # 中央揃え
        self.preview_label.setFixedSize(400, 300) # プレビュー表示エリアのサイズを固定
        self.preview_label.setFrameShape(QLabel.Shape.StyledPanel) # 枠線を表示

        # --- ボタン ---
        # QDialogButtonBox.Save は "保存" ボタンを表示します。
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | 
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # --- レイアウト ---
        
        # 1. 入力欄用のフォームレイアウト (ラベル: [入力欄])
        form_layout = QFormLayout()
        form_layout.addRow("幅", self.width_spinbox)
        form_layout.addRow("高さ", self.height_spinbox)
        form_layout.addRow("単位", self.unit_combo)
        form_layout.addRow("解像度", self.dpi_spinbox)
        form_layout.addRow(self.transparent_checkbox)
        form_layout.addRow(self.svg_text_as_path_checkbox)

        # 2. 全体をまとめる垂直レイアウト
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)      # フォームレイアウトを追加
        main_layout.addWidget(self.preview_button) # プレビューボタンを追加
        main_layout.addWidget(self.preview_label)  # プレビュー表示エリアを追加
        main_layout.addWidget(button_box)       # 保存/Cancelボタンを追加
        
        self.setLayout(main_layout)

        apply_form_spacing(self)

    def get_options(self):
        """
        ダイアログで入力された設定値を辞書として返します。
        
        Returns:
            dict: ユーザーが入力したエクスポート設定。
        """
        return {
            "width": self.width_spinbox.value(),
            "height": self.height_spinbox.value(),
            "unit": self.unit_combo.currentText(),
            "dpi": self.dpi_spinbox.value(),
            "transparent": self.transparent_checkbox.isChecked(),
            "svg_text_as_path": self.svg_text_as_path_checkbox.isChecked(),
        }


#==============================================================================
# カスタムダイアログクラス (7)
#==============================================================================
class ColumnPreviewDialog(QDialog):
    """
    データファイル (CSV/Excel) 読み込み時に、内容をプレビュー表示しつつ
    X軸・Y軸に使う列をユーザーに選択させるダイアログ。

    これまでは常に先頭2列を自動でX/Y軸に割り当てていたが、
    列数の多いファイルでは意図しない列が選ばれることがあるため、
    読み込み前に確認・選択できるようにする。

    Excelファイルの場合は、シートの切り替えとヘッダー行の指定にも対応する
    (どちらも変更するとファイルからその場で再読み込みしてプレビューを更新する)。
    """

    def __init__(self, df, file_name, parent=None, file_path=None):
        """
        Args:
            df (pandas.DataFrame): 読み込んだファイルのデータ (プレビュー表示用、
                先頭シート・1行目ヘッダーで読み込んだ初期状態)。
            file_name (str): 表示用のファイル名。
            parent (QWidget, optional): 親ウィジェット。
            file_path (str, optional): 実ファイルパス。Excelファイルの場合、
                シート切り替え・ヘッダー行変更時の再読み込みに使う。
        """
        super().__init__(parent)
        self.setWindowTitle(f"列の選択: {file_name}")
        self.resize(600, 480)

        self.file_path = file_path
        self.current_df = df
        self.is_excel = bool(file_path) and file_path.lower().endswith(('.xlsx', '.xls'))
        # 「列の型を確認...」で設定された、列ごとの型上書き ({列名: "数値"/"文字列"/"日付"})
        self.type_overrides = {}

        self.sheet_names = []
        if self.is_excel:
            try:
                self.sheet_names = pd.ExcelFile(file_path).sheet_names
            except Exception as e:
                logger.warning("Excelのシート一覧取得に失敗しました: %s", e)

        layout = QVBoxLayout(self)

        # --- Excel専用: シート選択・ヘッダー行指定 ---
        if self.is_excel:
            excel_form = QFormLayout()
            if self.sheet_names:
                self.sheet_combo = QComboBox()
                self.sheet_combo.addItems(self.sheet_names)
                self.sheet_combo.currentIndexChanged.connect(self._on_sheet_or_header_changed)
                excel_form.addRow("シート", self.sheet_combo)
            else:
                self.sheet_combo = None

            self.header_row_spinbox = QSpinBox()
            self.header_row_spinbox.setRange(1, 100)
            self.header_row_spinbox.setValue(1)
            self.header_row_spinbox.setToolTip("列名として使う行を指定します(データの上に説明行がある場合など)")
            self.header_row_spinbox.valueChanged.connect(self._on_sheet_or_header_changed)
            excel_form.addRow("ヘッダー行", self.header_row_spinbox)

            # 使用する列 (pandasのusecolsは "A,C:E" のようなExcel列表記の文字列を
            # そのまま受け付けるため、パース処理を自前で書く必要がない)
            self.usecols_edit = QLineEdit()
            self.usecols_edit.setPlaceholderText("例: A,C:E (空欄で全列)")
            self.usecols_edit.setToolTip("読み込む列をExcelの列表記で指定します(空欄なら全列を読み込みます)")
            self.usecols_edit.editingFinished.connect(self._on_sheet_or_header_changed)
            excel_form.addRow("使用する列 (usecols)", self.usecols_edit)

            self.nrows_spinbox = QSpinBox()
            self.nrows_spinbox.setRange(0, 10_000_000)
            self.nrows_spinbox.setValue(0)
            self.nrows_spinbox.setSpecialValueText("全行")
            self.nrows_spinbox.setToolTip("ヘッダー行より下で読み込む最大行数(0で全行)")
            self.nrows_spinbox.valueChanged.connect(self._on_sheet_or_header_changed)
            excel_form.addRow("読み込む最大行数", self.nrows_spinbox)

            layout.addLayout(excel_form)

            self.check_types_button = QPushButton("列の型を確認...")
            self.check_types_button.clicked.connect(self._on_check_column_types)
            layout.addWidget(self.check_types_button)
        else:
            self.sheet_combo = None
            self.header_row_spinbox = None
            self.usecols_edit = None
            self.nrows_spinbox = None

        self.info_label = QLabel()
        layout.addWidget(self.info_label)

        # --- プレビューテーブル (先頭最大20行、読み取り専用) ---
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # --- X/Y列選択 ---
        form = QFormLayout()
        self.x_col_combo = QComboBox()
        self.y_col_combo = QComboBox()
        form.addRow("X軸の列", self.x_col_combo)
        form.addRow("Y軸の列", self.y_col_combo)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

        self._rebuild_preview_table()

    def _on_sheet_or_header_changed(self):
        """
        シート選択、ヘッダー行、使用する列(usecols)、最大行数(nrows) のいずれかが
        変更されたときに呼ばれる。指定された条件でファイルから再読み込みし、
        プレビュー全体を更新する。
        """
        sheet_name = self.sheet_combo.currentText() if self.sheet_combo else 0
        header_row = self.header_row_spinbox.value() - 1  # UIは1始まり、pandasは0始まり
        usecols = self.usecols_edit.text().strip() or None if self.usecols_edit else None
        nrows = (self.nrows_spinbox.value() or None) if self.nrows_spinbox else None
        try:
            new_df = pd.read_excel(
                self.file_path, sheet_name=sheet_name, header=header_row,
                usecols=usecols, nrows=nrows
            )
        except Exception as e:
            QMessageBox.warning(
                self, "読み込みエラー",
                f"指定した条件(シート/ヘッダー行/使用する列/最大行数)では読み込めませんでした:\n{e}"
            )
            return
        self.current_df = new_df
        self._apply_type_overrides()
        self._rebuild_preview_table()

    def _on_check_column_types(self):
        """「列の型を確認...」ボタンの処理。ColumnTypeDialogを表示し、上書き設定を反映する"""
        dialog = ColumnTypeDialog(self.current_df, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.type_overrides = dialog.get_overrides()
            self._apply_type_overrides()
            self._rebuild_preview_table()

    def _apply_type_overrides(self):
        """
        self.type_overrides に設定されている列の型上書きを self.current_df に適用する。
        シート/ヘッダー行等の変更で current_df が新しく読み直された場合も、
        同じ列名がまだ存在すれば上書き設定を再適用する(呼び出し元で毎回呼ばれる)。
        """
        for col_name, override in self.type_overrides.items():
            if col_name not in self.current_df.columns:
                continue
            try:
                if override == "数値":
                    self.current_df[col_name] = pd.to_numeric(self.current_df[col_name], errors='coerce')
                elif override == "文字列":
                    self.current_df[col_name] = self.current_df[col_name].astype(str)
                elif override == "日付":
                    self.current_df[col_name] = pd.to_datetime(self.current_df[col_name], errors='coerce')
            except Exception as e:
                logger.warning("列「%s」の型変換(%s)に失敗しました: %s", col_name, override, e)

    def _rebuild_preview_table(self):
        """現在の self.current_df の内容で、情報ラベル・プレビュー表・X/Y列コンボを再構築する"""
        df = self.current_df
        columns = [str(c) for c in df.columns]

        self.info_label.setText(
            f"{len(df)}行 × {len(columns)}列 が見つかりました。"
            "プレビューを確認し、X軸・Y軸に使う列を選択してください。"
        )

        preview_row_count = min(len(df), 20)
        self.table.clear()
        self.table.setRowCount(preview_row_count)
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        for r in range(preview_row_count):
            for c in range(len(columns)):
                value = df.iloc[r, c]
                text = "" if pd.isna(value) else str(value)
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

        # X/Y列の選択肢を更新 (できる限り元の選択を維持し、無ければ先頭2列にフォールバック)
        prev_x = self.x_col_combo.currentText()
        prev_y = self.y_col_combo.currentText()
        self.x_col_combo.blockSignals(True)
        self.y_col_combo.blockSignals(True)
        self.x_col_combo.clear()
        self.y_col_combo.clear()
        self.x_col_combo.addItems(columns)
        self.y_col_combo.addItems(columns)
        if prev_x in columns:
            self.x_col_combo.setCurrentText(prev_x)
        elif len(columns) >= 1:
            self.x_col_combo.setCurrentIndex(0)
        if prev_y in columns:
            self.y_col_combo.setCurrentText(prev_y)
        elif len(columns) >= 2:
            self.y_col_combo.setCurrentIndex(1)
        self.x_col_combo.blockSignals(False)
        self.y_col_combo.blockSignals(False)

    def get_selected_columns(self):
        """
        選択された (X軸の列名, Y軸の列名) をタプルで返す。

        Returns:
            tuple (str, str): (x_col_name, y_col_name)
        """
        return self.x_col_combo.currentText(), self.y_col_combo.currentText()

    def get_dataframe(self):
        """
        現在プレビュー表示しているDataFrameを返す。
        Excelでシート/ヘッダー行を変更した場合は、その内容を反映したものになる。
        """
        return self.current_df


#==============================================================================
# カスタムダイアログクラス (8)
#==============================================================================
class ColorPaletteDialog(QDialog):
    """
    「自動配色」ボタンで使うカラーサイクル(パレット)を、ユーザーが複数
    定義・保存・切り替えできるようにするダイアログ。
    「Matplotlib既定」は常に選べる読み取り専用のパレットとして扱う。
    """

    DEFAULT_PALETTE_NAME = "Matplotlib既定"

    def __init__(self, palettes: dict, active_name: str, parent=None):
        """
        Args:
            palettes (dict[str, list[str]]): パレット名 -> 16進カラーコードのリスト。
            active_name (str): 現在アクティブなパレット名 (初期選択に使う)。
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("配色パレットの管理")
        self.resize(420, 440)

        # 呼び出し側の辞書を直接変更しない (Cancel時に元の状態を保つため)
        self.palettes = {name: list(colors) for name, colors in palettes.items()}

        layout = QVBoxLayout(self)

        combo_layout = QHBoxLayout()
        combo_layout.addWidget(QLabel("パレット"))
        self.palette_combo = QComboBox()
        self.palette_combo.addItem(self.DEFAULT_PALETTE_NAME)
        self.palette_combo.addItems(sorted(self.palettes.keys()))
        combo_layout.addWidget(self.palette_combo, stretch=1)
        layout.addLayout(combo_layout)

        palette_button_layout = QHBoxLayout()
        self.new_palette_button = QPushButton("新規パレット...")
        self.rename_palette_button = QPushButton("名前を変更...")
        self.delete_palette_button = QPushButton("削除")
        palette_button_layout.addWidget(self.new_palette_button)
        palette_button_layout.addWidget(self.rename_palette_button)
        palette_button_layout.addWidget(self.delete_palette_button)
        layout.addLayout(palette_button_layout)

        self.color_list = QListWidget()
        layout.addWidget(self.color_list)

        color_button_layout = QHBoxLayout()
        self.add_color_button = QPushButton("色を追加...")
        self.remove_color_button = QPushButton("選択した色を削除")
        color_button_layout.addWidget(self.add_color_button)
        color_button_layout.addWidget(self.remove_color_button)
        color_button_layout.addStretch()
        layout.addLayout(color_button_layout)

        info_label = QLabel("「OK」を押すと、選択中のパレットが以後「自動配色」ボタンで使われます。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.palette_combo.currentTextChanged.connect(self._on_palette_selected)
        self.new_palette_button.clicked.connect(self._on_new_palette)
        self.rename_palette_button.clicked.connect(self._on_rename_palette)
        self.delete_palette_button.clicked.connect(self._on_delete_palette)
        self.add_color_button.clicked.connect(self._on_add_color)
        self.remove_color_button.clicked.connect(self._on_remove_color)

        if active_name in self.palettes:
            self.palette_combo.setCurrentText(active_name)
        else:
            self.palette_combo.setCurrentText(self.DEFAULT_PALETTE_NAME)
        self._refresh_color_list()
        self._update_button_states()

    def _is_default_selected(self):
        return self.palette_combo.currentText() == self.DEFAULT_PALETTE_NAME

    def _update_button_states(self):
        # 既定パレットは読み取り専用 (名前変更・削除・色の追加/削除は不可)
        editable = not self._is_default_selected()
        self.rename_palette_button.setEnabled(editable)
        self.delete_palette_button.setEnabled(editable)
        self.add_color_button.setEnabled(editable)
        self.remove_color_button.setEnabled(editable)

    def _refresh_color_list(self):
        # ★ 項目H-2-6(実機での目視確認で発覚): 以前はQListWidgetItem.
        #   setBackground()/setForeground()で行全体を色のパレットで塗り、
        #   明るさに応じて文字色を白/黒に切り替えることで常に読めるように
        #   していた。ところがQSSで::item(padding指定のみ)に何かひとつでも
        #   プロパティを当てると、Qtはそのサブコントロールを「スタイル
        #   シートでカスタム描画されるもの」とみなし、setBackground()/
        #   setForeground()で設定したBackgroundRole/ForegroundRoleを描画時に
        #   無視するようになる(本コードベースで既に複数回踏んでいる既知の
        #   Qt/QSSの癖、QTabBar::close-buttonのアイコン消失やチェックボックスの
        #   チェックマーク消失と同じ原因)。結果として実機では常にリストの
        #   地の色(surfaceトークン)がそのまま描画され、明るい色(例: 青・緑)は
        #   白文字と、暗い背景では逆に暗い色(黒文字)の行が、それぞれ
        #   ほぼ同化して読めなくなっていた。
        #   対策として、行の描画をQSSに委ねず、setItemWidget()で小さな
        #   スウォッチ(色見本)+通常のテーマ文字色のテキストラベルという
        #   専用ウィジェットに置き換えた(ColorPickerWidgetのスウォッチと
        #   同じ意匠)。テキストが常にテーマの通常文字色で描画されるため、
        #   スウォッチの色がどんな明るさでも可読性が保たれる。
        self.color_list.clear()
        name = self.palette_combo.currentText()
        if name == self.DEFAULT_PALETTE_NAME:
            colors = list(mpl.rcParams['axes.prop_cycle'].by_key()['color'])
        else:
            colors = self.palettes.get(name, [])
        from gui import theme
        border_color = theme.current_tokens()["border_strong"]
        for color_hex in colors:
            item = QListWidgetItem()
            self.color_list.addItem(item)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(6, 2, 6, 2)
            row_layout.setSpacing(8)

            swatch = QLabel()
            swatch.setFixedSize(20, 20)
            swatch.setStyleSheet(
                f"background-color: {color_hex}; border: 1px solid {border_color}; "
                f"border-radius: 4px;"
            )
            row_layout.addWidget(swatch)
            row_layout.addWidget(QLabel(color_hex), 1)

            item.setSizeHint(row_widget.sizeHint())
            self.color_list.setItemWidget(item, row_widget)

    def _on_palette_selected(self, _name):
        self._refresh_color_list()
        self._update_button_states()

    def _on_new_palette(self):
        name, ok = QInputDialog.getText(self, "新規パレット", "パレット名")
        if not ok or not name:
            return
        if name == self.DEFAULT_PALETTE_NAME or name in self.palettes:
            QMessageBox.warning(self, "エラー", f"パレット名 '{name}' は既に使われています。")
            return
        self.palettes[name] = []
        self.palette_combo.addItem(name)
        self.palette_combo.setCurrentText(name)

    def _on_rename_palette(self):
        old_name = self.palette_combo.currentText()
        if old_name == self.DEFAULT_PALETTE_NAME:
            return
        new_name, ok = QInputDialog.getText(self, "名前を変更", "新しいパレット名", text=old_name)
        if not ok or not new_name or new_name == old_name:
            return
        if new_name == self.DEFAULT_PALETTE_NAME or new_name in self.palettes:
            QMessageBox.warning(self, "エラー", f"パレット名 '{new_name}' は既に使われています。")
            return
        self.palettes[new_name] = self.palettes.pop(old_name)
        self.palette_combo.setItemText(self.palette_combo.currentIndex(), new_name)

    def _on_delete_palette(self):
        name = self.palette_combo.currentText()
        if name == self.DEFAULT_PALETTE_NAME:
            return
        reply = QMessageBox.question(
            self, "パレットを削除", f"パレット '{name}' を削除しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del self.palettes[name]
        self.palette_combo.removeItem(self.palette_combo.currentIndex())  # 既定パレットに自動的に切り替わる

    def _on_add_color(self):
        name = self.palette_combo.currentText()
        if name == self.DEFAULT_PALETTE_NAME:
            return
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        self.palettes.setdefault(name, []).append(color.name())
        self._refresh_color_list()

    def _on_remove_color(self):
        name = self.palette_combo.currentText()
        if name == self.DEFAULT_PALETTE_NAME:
            return
        row = self.color_list.currentRow()
        if row < 0:
            return
        del self.palettes[name][row]
        self._refresh_color_list()

    def get_result(self):
        """
        (パレット辞書, アクティブにするパレット名) のタプルを返す。
        QSettingsへの実際の保存は呼び出し側が行う。
        """
        return self.palettes, self.palette_combo.currentText()


#==============================================================================
# カスタムダイアログクラス (9)
#==============================================================================
class ReplicateErrorDialog(QDialog):
    """
    同一条件で複数回測定した列 (反復測定列) から、行ごとの平均と誤差
    (標準偏差/標準誤差/95%信頼区間) を自動計算するための列を選ばせるダイアログ。
    データエディタの「誤差の自動計算...」ボタンから使われる。
    """

    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("誤差の自動計算 (反復測定)")
        self.resize(360, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("反復測定として扱う列を2つ以上選んでください:"))

        self.column_list = QListWidget()
        self.column_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for name in column_names:
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.column_list.addItem(item)
        layout.addWidget(self.column_list)

        form = QFormLayout()
        self.stat_combo = QComboBox()
        self.stat_combo.addItems(["SD (標準偏差)", "SEM (標準誤差)", "95%CI (信頼区間)"])
        form.addRow("誤差の種類", self.stat_combo)

        self.base_name_edit = QLineEdit("measurement")
        form.addRow("出力列名 (ベース)", self.base_name_edit)
        layout.addLayout(form)

        info_label = QLabel(
            "「平均」列と「誤差」列の2つが追加されます (例: measurement_mean, measurement_SD)。"
            "NaNを含む行は、その行にある有効な測定値だけで計算します。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        Returns:
            tuple (list[str], str, str): (選択された列名のリスト,
                誤差の種類 ('SD'/'SEM'/'95%CI'), 出力列名のベース名)
        """
        selected = []
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        stat_type = self.stat_combo.currentText().split(" ")[0]  # "SD (標準偏差)" -> "SD"
        return selected, stat_type, self.base_name_edit.text().strip()


#==============================================================================
# カスタムダイアログクラス: Excel列の型自動判定確認
#==============================================================================
class ColumnTypeDialog(QDialog):
    """
    読み込んだ表の各列について、pandasが自動判定した型を一覧表示し、
    必要であれば「数値」「文字列」「日付」に強制変換できるようにするダイアログ。
    日付列が数値(Excelのシリアル値)として誤認識される、といったケースへの対策として、
    読み込み前にユーザー自身が気づいて修正できるようにする。
    """

    OVERRIDE_CHOICES = ["自動 (変換しない)", "数値", "文字列", "日付"]

    def __init__(self, df, parent=None):
        super().__init__(parent)
        self.setWindowTitle("列の型を確認")
        self.resize(480, 400)

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "各列について、現在検出されている型を表示しています。"
            "日付が数値として読み込まれている場合など、意図と異なる場合は"
            "「上書き後の型」で変換方法を選択してください。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["列名", "検出された型", "上書き後の型"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setRowCount(len(df.columns))

        self._override_combos = {}
        for row, col_name in enumerate(df.columns):
            self.table.setItem(row, 0, QTableWidgetItem(str(col_name)))

            detected_item = QTableWidgetItem(str(df[col_name].dtype))
            detected_item.setFlags(detected_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, detected_item)

            combo = QComboBox()
            combo.addItems(self.OVERRIDE_CHOICES)
            self.table.setCellWidget(row, 2, combo)
            self._override_combos[str(col_name)] = combo

        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_overrides(self):
        """
        「自動」以外が選択された列だけを対象に、{列名: 上書き後の型} の辞書を返す。
        上書き後の型は "数値" / "文字列" / "日付" のいずれか。
        """
        overrides = {}
        for col_name, combo in self._override_combos.items():
            text = combo.currentText()
            if text != "自動 (変換しない)":
                overrides[col_name] = text
        return overrides


#==============================================================================
# カスタムダイアログクラス: Excel複数シートの一括インポート
#==============================================================================
class ExcelMultiSheetDialog(QDialog):
    """
    複数シートを持つExcelファイルを読み込む際に、どのシートを
    データセットとして取り込むかチェックボックスで選択させるダイアログ。
    2つ以上チェックした場合は、シートごとに別々のデータセットとして追加される
    (シートごとにX/Y列の選択プレビューが続けて表示される)。
    """

    def __init__(self, sheet_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("シートの選択")
        self.resize(320, 380)

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "読み込むシートを選択してください(複数選択可)。\n"
            "2つ以上選択すると、シートごとに別々のデータセットとして追加されます。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.sheet_list = QListWidget()
        self.sheet_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for i, name in enumerate(sheet_names):
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if i == 0 else Qt.CheckState.Unchecked)
            self.sheet_list.addItem(item)
        layout.addWidget(self.sheet_list)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_selected_sheets(self):
        """チェックされたシート名のリストを、シート一覧に現れる順序で返す"""
        result = []
        for i in range(self.sheet_list.count()):
            item = self.sheet_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result


#==============================================================================
# カスタムダイアログクラス: データセット間演算
#==============================================================================
class DatasetArithmeticDialog(QDialog):
    """
    2つのデータセット (A, B) 間で差・和・積・商を計算し、新しいデータセットを
    生成するための設定を入力させるダイアログ。
    X軸の値が完全には一致しない2つのデータセットを対象にするため、実際の計算は
    B側のY値をA側のX値に線形補間してから行う (呼び出し側の責務)。
    """

    OPERATIONS = ["A - B", "B - A", "A + B", "A × B", "A ÷ B", "B ÷ A"]

    def __init__(self, name_a, name_b, parent=None):
        super().__init__(parent)
        self.setWindowTitle("データセット間演算")
        self.resize(360, 200)

        layout = QVBoxLayout(self)
        label = QLabel(f"A: {name_a}\nB: {name_b}")
        layout.addWidget(label)

        form = QFormLayout()
        self.operation_combo = QComboBox()
        self.operation_combo.addItems(self.OPERATIONS)
        form.addRow("演算", self.operation_combo)

        self.output_name_edit = QLineEdit(f"{name_a} vs {name_b}")
        form.addRow("出力データセット名", self.output_name_edit)
        layout.addLayout(form)

        info_label = QLabel(
            "B側のY値を、A側のX値に線形補間してから演算します。"
            "2つのデータセットのX軸の値が重なる範囲のみが対象になります。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        Returns:
            tuple (str, str): (演算の種類 (OPERATIONSのいずれか), 出力データセット名)
        """
        return self.operation_combo.currentText(), self.output_name_edit.text().strip()


#==============================================================================
# カスタムダイアログクラス: 規格化(ノーマライズ)
#==============================================================================
class NormalizeDatasetDialog(QDialog):
    """
    規格化(ノーマライズ、項目78)の設定を入力させるダイアログ。
    最大値基準(Yの最大値を1.0にする)か、特定X値での強度基準
    (指定したX値での補間値を1.0にする)かを選ばせ、後者の場合のみ
    基準X値の数値入力欄を有効にする。DatasetArithmeticDialogと同じ構成。
    """

    MODE_MAX = "最大値基準"
    MODE_X_VALUE = "特定X値での強度基準"
    MODES = [MODE_MAX, MODE_X_VALUE]

    def __init__(self, name, x_min=None, x_max=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("規格化(ノーマライズ)")
        self.resize(360, 220)

        layout = QVBoxLayout(self)
        label = QLabel(f"対象: {name}")
        layout.addWidget(label)

        form = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        form.addRow("基準", self.mode_combo)

        self.reference_x_spinbox = QDoubleSpinBox()
        self.reference_x_spinbox.setRange(-1e12, 1e12)
        self.reference_x_spinbox.setDecimals(6)
        self.reference_x_spinbox.setEnabled(False)
        if x_min is not None:
            self.reference_x_spinbox.setValue(x_min)
        form.addRow("基準X値", self.reference_x_spinbox)

        self.output_name_edit = QLineEdit(f"{name}_normalized")
        form.addRow("出力データセット名", self.output_name_edit)
        layout.addLayout(form)

        self.mode_combo.currentTextChanged.connect(
            lambda text: self.reference_x_spinbox.setEnabled(text == self.MODE_X_VALUE)
        )

        info_label = QLabel(
            "最大値基準: Yの最大値が1.0になるよう規格化します(マスク中の行は除外)。\n"
            "特定X値での強度基準: 指定したX値でのYを線形補間し、その値が1.0になるよう規格化します。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        Returns:
            tuple (str, float|None, str): (基準の種類 (MODESのいずれか),
            基準X値 (MODE_X_VALUEの場合のみ数値、それ以外はNone), 出力データセット名)
        """
        mode = self.mode_combo.currentText()
        reference_x = self.reference_x_spinbox.value() if mode == self.MODE_X_VALUE else None
        return mode, reference_x, self.output_name_edit.text().strip()


class SavGolDialog(QDialog):
    """
    Savitzky-Golayフィルタ(平滑化: 項目C-301、微分スペクトル: 項目C-302)の
    設定を入力させるダイアログ。NormalizeDatasetDialogと同じ構成。
    """

    MODE_SMOOTH = "平滑化"
    MODE_DERIV1 = "1次微分"
    MODE_DERIV2 = "2次微分"
    MODES = [MODE_SMOOTH, MODE_DERIV1, MODE_DERIV2]
    _DERIV_BY_MODE = {MODE_SMOOTH: 0, MODE_DERIV1: 1, MODE_DERIV2: 2}
    _SUFFIX_BY_MODE = {MODE_SMOOTH: "_smoothed", MODE_DERIV1: "_deriv1", MODE_DERIV2: "_deriv2"}

    def __init__(self, name, max_window=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Savitzky-Golayフィルタ")
        self.resize(380, 260)
        self._name = name

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"対象: {name}"))

        form = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        form.addRow("種類", self.mode_combo)

        self.window_spinbox = QSpinBox()
        self.window_spinbox.setRange(3, max_window if max_window else 999999)
        self.window_spinbox.setSingleStep(2)
        self.window_spinbox.setValue(min(5, max_window) if max_window else 5)
        form.addRow("窓幅(奇数)", self.window_spinbox)

        self.polyorder_spinbox = QSpinBox()
        self.polyorder_spinbox.setRange(1, 10)
        self.polyorder_spinbox.setValue(2)
        form.addRow("多項式の次数", self.polyorder_spinbox)

        self.output_name_edit = QLineEdit(f"{name}{self._SUFFIX_BY_MODE[self.MODE_SMOOTH]}")
        form.addRow("出力データセット名", self.output_name_edit)
        layout.addLayout(form)

        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        info_label = QLabel(
            "窓幅は奇数かつ多項式の次数より大きい値を指定してください。\n"
            "微分はX軸の間隔が概ね等間隔であることを前提とします。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def _on_mode_changed(self, mode):
        self.output_name_edit.setText(f"{self._name}{self._SUFFIX_BY_MODE[mode]}")

    def get_settings(self):
        """
        Returns:
            tuple (int, int, int, str): (窓幅, 多項式の次数, 微分階数(0/1/2), 出力データセット名)
        """
        mode = self.mode_combo.currentText()
        return (
            self.window_spinbox.value(),
            self.polyorder_spinbox.value(),
            self._DERIV_BY_MODE[mode],
            self.output_name_edit.text().strip(),
        )


class PluginParamDialog(QDialog):
    """
    register_processor()/register_analyzer() の param_schema から、パラメータ
    入力フォームを自動生成するダイアログ(項目C-1/C-2)。

    param_schema は dict のリストで、各要素は少なくとも "name" と "type" を持つ:
        {"name": str, "label": str(省略時はname), "type": "int"|"float"|"str"|"bool"|"choice",
         "default": 任意, "min"/"max": int|float(int/floatのみ), "choices": list(choiceのみ),
         "decimals": int(floatのみ、省略時4)}
    """

    _INT_RANGE = (-2_147_483_647, 2_147_483_647)  # Qt QSpinBoxのネイティブ範囲に合わせる

    def __init__(self, title, param_schema, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._widgets = {}  # name -> (type, widget)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        for spec in param_schema:
            name = spec["name"]
            label = spec.get("label", name)
            ptype = spec.get("type", "str")
            default = spec.get("default")
            widget = self._build_widget(ptype, spec, default)
            self._widgets[name] = (ptype, widget)
            form.addRow(label, widget)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def _build_widget(self, ptype, spec, default):
        if ptype == "int":
            widget = QSpinBox()
            widget.setRange(spec.get("min", self._INT_RANGE[0]), spec.get("max", self._INT_RANGE[1]))
            widget.setValue(int(default) if default is not None else 0)
            return widget
        if ptype == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(spec.get("decimals", 4))
            widget.setRange(spec.get("min", -1e12), spec.get("max", 1e12))
            widget.setValue(float(default) if default is not None else 0.0)
            return widget
        if ptype == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(default))
            return widget
        if ptype == "choice":
            widget = QComboBox()
            widget.addItems([str(c) for c in spec.get("choices", [])])
            if default is not None:
                widget.setCurrentText(str(default))
            return widget
        # "str" および未知のtypeはテキスト入力にフォールバックする
        widget = QLineEdit()
        if default is not None:
            widget.setText(str(default))
        return widget

    def get_values(self):
        """Returns: dict {パラメータ名: 入力値(型はparam_schemaのtypeに従う)}"""
        values = {}
        for name, (ptype, widget) in self._widgets.items():
            if ptype in ("int", "float"):
                values[name] = widget.value()
            elif ptype == "bool":
                values[name] = widget.isChecked()
            elif ptype == "choice":
                values[name] = widget.currentText()
            else:
                values[name] = widget.text()
        return values


#==============================================================================
# カスタムダイアログクラス: 環境設定 (Preferences)
#==============================================================================
class PreferencesDialog(QDialog):
    """
    これまでメニューに散らばっていた設定項目 (ダークモード、オートセーブ間隔) を
    1つの画面にまとめた環境設定ダイアログ。
    設定の永続化自体は呼び出し側 (main_window) が get_settings() の戻り値を
    使って行う。このダイアログ自体は値の入力/表示のみを担当する。
    """

    def __init__(self, dark_mode, autosave_minutes, autosave_bounds=(0, 180), parent=None,
                 current_language=None, autosave_dir="", point_label_max_points=1000,
                 snap_to_grid_enabled=False, snap_grid_interval_px=10,
                 plugin_records=None, plugin_registration_errors=None, disabled_plugin_names=None):
        """
        plugin_records/plugin_registration_errors/disabled_plugin_names は
        「プラグイン」タブ(項目F-2)用。呼び出し側(gui/mixins/project_io_mixin.py)
        が core.plugin_api.get_loaded_plugin_records() 等をそのまま渡す想定。
        plugin_records=None は「一度もロードされていない(セーフモード含む)」を表し、
        空リストの「1つも無い」とは区別して表示する。
        """
        super().__init__(parent)
        from core.i18n import tr, SUPPORTED_LANGUAGES, get_language
        self.setWindowTitle(tr("環境設定"))
        # ★ QGroupBoxの見出しをアクセントカラーの背景チップで目立たせるQSS
        #   (GUIモダン化第2弾、項目68)により、各グループボックスの上部余白
        #   (margin-top/padding-top)が以前より広くなったため、旧来のサイズ
        #   (360x260)のままだと3つのグループボックスがすべて収まりきらず
        #   文字が見切れてしまっていた。縦方向に余裕を持たせる。
        # 項目F-2でプラグイン管理タブを追加したため、さらに縦横に余裕を持たせる。
        self.resize(480, 520)

        outer_layout = QVBoxLayout(self)
        tabs = QTabWidget()
        outer_layout.addWidget(tabs)

        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)
        tabs.addTab(general_tab, tr("一般"))

        appearance_group = QGroupBox(tr("外観"))
        appearance_layout = QVBoxLayout(appearance_group)
        self.dark_mode_checkbox = QCheckBox(tr("ダークモードを有効にする"))
        self.dark_mode_checkbox.setChecked(bool(dark_mode))
        appearance_layout.addWidget(self.dark_mode_checkbox)
        layout.addWidget(appearance_group)

        # UIの多言語対応(項目41): 表示言語の選択。切り替えは次回起動時に反映される
        # (実行中のウィジェットをその場で再翻訳する仕組みは持たないため)。
        language_group = QGroupBox(tr("言語"))
        language_form = QFormLayout(language_group)
        self.language_combo = QComboBox()
        self._language_codes = list(SUPPORTED_LANGUAGES.keys())
        self.language_combo.addItems([SUPPORTED_LANGUAGES[code] for code in self._language_codes])
        active_language = current_language or get_language()
        if active_language in self._language_codes:
            self.language_combo.setCurrentIndex(self._language_codes.index(active_language))
        language_form.addRow(tr("表示言語"), self.language_combo)
        language_note = QLabel(tr("※ 言語の変更は次回起動時に反映されます。"))
        language_note.setStyleSheet("font-size: 9pt; color: gray;")
        language_note.setWordWrap(True)
        language_form.addRow(language_note)
        layout.addWidget(language_group)

        save_group = QGroupBox(tr("保存"))
        save_form = QFormLayout(save_group)
        self.autosave_spinbox = QSpinBox()
        min_minutes, max_minutes = autosave_bounds
        self.autosave_spinbox.setRange(min_minutes, max_minutes)
        self.autosave_spinbox.setSuffix(tr(" 分"))
        self.autosave_spinbox.setSpecialValueText(tr("無効"))
        self.autosave_spinbox.setValue(int(autosave_minutes))
        save_form.addRow(tr("オートセーブ間隔"), self.autosave_spinbox)

        # オートセーブの保存先フォルダ(未指定なら従来どおりアプリのフォルダに保存)
        self._autosave_dir = autosave_dir or ""
        autosave_dir_row = QHBoxLayout()
        self.autosave_dir_edit = QLineEdit(self._autosave_dir)
        self.autosave_dir_edit.setReadOnly(True)
        self.autosave_dir_edit.setPlaceholderText(tr("(既定: アプリのフォルダ)"))
        self.autosave_dir_browse_button = QPushButton(tr("参照..."))
        self.autosave_dir_browse_button.setIcon(icon_utils.icon("folder"))
        self.autosave_dir_browse_button.clicked.connect(self._on_browse_autosave_dir)
        self.autosave_dir_clear_button = QPushButton(tr("既定に戻す"))
        self.autosave_dir_clear_button.setIcon(icon_utils.icon("refresh"))
        self.autosave_dir_clear_button.clicked.connect(self._on_clear_autosave_dir)
        autosave_dir_row.addWidget(self.autosave_dir_edit, 1)
        autosave_dir_row.addWidget(self.autosave_dir_browse_button)
        autosave_dir_row.addWidget(self.autosave_dir_clear_button)
        save_form.addRow(tr("オートセーブ保存先"), autosave_dir_row)

        layout.addWidget(save_group)

        # パフォーマンス(項目105): データ点ラベル表示は点数が多いと ax.annotate() の
        # 呼び出し回数がそのまま増え、アプリがフリーズする原因になる。この件数を
        # 超えるデータセットには自動的にラベルを描画しないようにする上限を設定できる。
        performance_group = QGroupBox(tr("パフォーマンス"))
        performance_form = QFormLayout(performance_group)
        self.point_label_max_spinbox = QSpinBox()
        self.point_label_max_spinbox.setRange(10, 1_000_000)
        self.point_label_max_spinbox.setSingleStep(100)
        self.point_label_max_spinbox.setSuffix(tr(" 点"))
        self.point_label_max_spinbox.setValue(int(point_label_max_points))
        self.point_label_max_spinbox.setToolTip(tr(
            "データ点にラベルを表示する機能は、データ点数が多いと描画が重くなり、"
            "アプリがフリーズする場合があります。この件数を超えるデータセットには、"
            "ラベルを有効にしていても自動的に表示しません。"
        ))
        performance_form.addRow(tr("データ点ラベルの表示上限"), self.point_label_max_spinbox)
        layout.addWidget(performance_group)

        # スナップ・トゥ・グリッド(項目84): テキスト注釈・矢印注釈をドラッグ配置する際、
        # ピクセル単位のグリッドに位置を吸着させ、複数の注釈をきれいに整列できるようにする。
        annotation_group = QGroupBox(tr("注釈"))
        annotation_layout = QVBoxLayout(annotation_group)
        self.snap_to_grid_checkbox = QCheckBox(tr("スナップ・トゥ・グリッドを有効にする"))
        self.snap_to_grid_checkbox.setChecked(bool(snap_to_grid_enabled))
        annotation_layout.addWidget(self.snap_to_grid_checkbox)
        annotation_form = QFormLayout()
        self.snap_grid_interval_spinbox = QSpinBox()
        self.snap_grid_interval_spinbox.setRange(1, 200)
        self.snap_grid_interval_spinbox.setSuffix(tr(" px"))
        self.snap_grid_interval_spinbox.setValue(int(snap_grid_interval_px))
        annotation_form.addRow(tr("グリッド間隔"), self.snap_grid_interval_spinbox)
        annotation_layout.addLayout(annotation_form)
        layout.addWidget(annotation_group)

        layout.addStretch()

        # --- 「プラグイン」タブ(項目F-2) ---
        plugin_tab = QWidget()
        plugin_tab_layout = QVBoxLayout(plugin_tab)
        tabs.addTab(plugin_tab, tr("プラグイン"))

        # インストール・プラグインフォルダを開く(いずれもOK/Cancelフローとは
        # 独立した即時実行のボタン。オートセーブ保存先の参照ボタンと同じ位置づけ)
        plugin_actions_row = QHBoxLayout()
        self.install_plugin_button = QPushButton(tr("プラグインをインストール..."))
        self.install_plugin_button.setIcon(icon_utils.icon("download"))
        self.install_plugin_button.clicked.connect(self._on_install_plugin)
        plugin_actions_row.addWidget(self.install_plugin_button)
        self.open_plugins_folder_button = QPushButton(tr("プラグインフォルダを開く"))
        self.open_plugins_folder_button.setIcon(icon_utils.icon("folder"))
        self.open_plugins_folder_button.clicked.connect(self._on_open_plugins_folder)
        plugin_actions_row.addWidget(self.open_plugins_folder_button)
        plugin_actions_row.addStretch()
        plugin_tab_layout.addLayout(plugin_actions_row)

        # ロード済みプラグインの一覧(名前/バージョン/作者)+ 個別ON/OFF。
        # チェック状態はダイアログを閉じる際にget_disabled_plugin_names()経由で
        # 読み取られ、QSettingsへの反映(次回起動時に反映)は呼び出し側
        # (gui/mixins/project_io_mixin.py の _on_show_preferences)が行う。
        loaded_group = QGroupBox(tr("読み込み済みプラグイン"))
        loaded_layout = QVBoxLayout(loaded_group)
        self.plugin_list = QListWidget()
        self._disabled_plugin_names = set(disabled_plugin_names or [])
        self._populate_plugin_list(plugin_records, self._disabled_plugin_names)
        loaded_layout.addWidget(self.plugin_list)
        plugin_tab_layout.addWidget(loaded_group, 1)

        # フック単位の登録失敗(項目A-2): プラグイン全体としてはロードに成功して
        # いても、個々のregister_xxx呼び出しが(名前衝突等で)失敗している場合に
        # ここに表示する(get_loaded_plugin_recordsのerrorには現れないため)。
        hook_errors_group = QGroupBox(tr("フック単位の登録エラー"))
        hook_errors_layout = QVBoxLayout(hook_errors_group)
        self.plugin_hook_errors_list = QListWidget()
        self._populate_hook_errors_list(plugin_registration_errors)
        hook_errors_layout.addWidget(self.plugin_hook_errors_list)
        plugin_tab_layout.addWidget(hook_errors_group)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        outer_layout.addWidget(button_box)

        apply_form_spacing(self)

    def _populate_plugin_list(self, plugin_records, disabled_names):
        """
        「読み込み済みプラグイン」リストを構築する。plugin_records=Noneは
        「一度もロードされていない」(セーフモード中含む)ことを表す特別扱いの
        1行を出す。各行のチェック状態は現在の無効化設定を反映する(表示専用の
        行=状態未読込プラグイン向けエラー行にはチェックボックスを付けない)。
        """
        from core.i18n import tr
        self.plugin_list.clear()
        if plugin_records is None:
            item = QListWidgetItem(tr("(プラグインは読み込まれていません)"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.plugin_list.addItem(item)
            return
        if not plugin_records:
            item = QListWidgetItem(tr("(プラグインはありません)"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.plugin_list.addItem(item)
            return

        for record in plugin_records:
            name = record["name"]
            info = record.get("info")
            error = record.get("error")
            disabled = record.get("disabled", False)

            if disabled:
                label = tr("{name} (無効化中)").format(name=name)
            elif error:
                label = tr("{name} — エラー: {error}").format(name=name, error=error)
            elif info:
                label = f"{info.get('name', name)} v{info.get('version', '?')} — {info.get('author', '?')}"
            else:
                label = name

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Unchecked if name in disabled_names else Qt.CheckState.Checked
            )
            self.plugin_list.addItem(item)

    def _populate_hook_errors_list(self, plugin_registration_errors):
        from core.i18n import tr
        self.plugin_hook_errors_list.clear()
        if not plugin_registration_errors:
            item = QListWidgetItem(tr("(フック単位の登録エラーはありません)"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.plugin_hook_errors_list.addItem(item)
            return
        for error in plugin_registration_errors:
            text = f"[{error.plugin_name}] {error.hook_kind.value}: {error.message}"
            self.plugin_hook_errors_list.addItem(QListWidgetItem(text))

    def get_disabled_plugin_names(self):
        """
        「読み込み済みプラグイン」リストの現在のチェック状態から、無効化された
        (チェックが外された)プラグイン名の集合を返す。呼び出し側がこれを
        QSettingsのDISABLED_PLUGINS_SETTINGS_KEYへ保存する(次回起動時に反映)。
        """
        disabled = set()
        for i in range(self.plugin_list.count()):
            item = self.plugin_list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name is not None and item.checkState() == Qt.CheckState.Unchecked:
                disabled.add(name)
        return disabled

    def _on_open_plugins_folder(self):
        from core.app_paths import get_user_plugins_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(get_user_plugins_dir()))

    def _on_browse_autosave_dir(self):
        from core.i18n import tr
        directory = QFileDialog.getExistingDirectory(
            self, tr("オートセーブの保存先を選択"), self._autosave_dir or ""
        )
        if directory:
            self._autosave_dir = directory
            self.autosave_dir_edit.setText(directory)

    def _on_clear_autosave_dir(self):
        self._autosave_dir = ""
        self.autosave_dir_edit.setText("")

    def _on_install_plugin(self):
        from core.i18n import tr
        zip_path, _ = QFileDialog.getOpenFileName(
            self, tr("プラグインをインストール"), "", tr("Zip files (*.zip)")
        )
        if not zip_path:
            return

        from core.plugin_install import install_plugin_zip, PluginInstallError
        try:
            installed_name = install_plugin_zip(zip_path)
        except PluginInstallError as e:
            QMessageBox.critical(self, tr("インストール失敗"), str(e))
            return

        QMessageBox.information(
            self, tr("インストール完了"),
            tr("プラグイン '{name}' をインストールしました。次回起動時に有効になります。").format(
                name=installed_name
            ),
        )

    def get_settings(self):
        """
        Returns:
            tuple (bool, int, str, str, int, bool, int): (ダークモードを有効にするか,
                オートセーブ間隔(分, 0=無効), 表示言語コード,
                オートセーブ保存先ディレクトリ("" なら既定=アプリのフォルダ),
                データ点ラベルの表示上限(件数),
                スナップ・トゥ・グリッドを有効にするか, グリッド間隔(px))
        """
        language_code = self._language_codes[self.language_combo.currentIndex()]
        return (self.dark_mode_checkbox.isChecked(), self.autosave_spinbox.value(),
                language_code, self._autosave_dir, self.point_label_max_spinbox.value(),
                self.snap_to_grid_checkbox.isChecked(), self.snap_grid_interval_spinbox.value())


#==============================================================================
# カスタムダイアログクラス: コマンドパレット
#==============================================================================
class CommandPaletteDialog(QDialog):
    """
    Ctrl+Shift+P で開く、メニュー項目をキーボードで検索して実行できるダイアログ。
    検索欄にフォーカスがある状態のまま上下キーでリストの選択を移動し、
    Enterで実行できるようにしている(一般的なコマンドパレットのUXに合わせる)。

    ★ 注意 ★
    QMenu.addAction(text) の戻り値のように、Python側で明示的に self.xxx として
    保持されていない QAction は、後からPythonの参照だけを保持していても、
    ガベージコレクションのタイミングでラッパーが無効化される(実体は
    メニューに残っているのに "already deleted" になる)ことがある。
    そのため、収集した (path, action) の組は一度きりの表示にしか使わず、
    実際に実行する際は collect_fn() を呼び直して「今」有効なQActionを
    取り直してからその場で trigger() する(取得と使用の間に時間を空けない)。
    """

    def __init__(self, collect_fn, parent=None):
        """
        Args:
            collect_fn (callable): 呼ぶたびに現在のメニューアクションを
                [(パスのリスト, QAction), ...] として新しく収集して返す関数。
        """
        super().__init__(parent)
        self.setWindowTitle("コマンドパレット")
        self.resize(480, 420)

        self._collect_fn = collect_fn

        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("コマンドを検索...")
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.search_edit.textChanged.connect(self._update_list)
        self.list_widget.itemActivated.connect(self._on_item_activated)
        self.search_edit.installEventFilter(self)

        self._update_list("")

    def _update_list(self, text):
        query = text.strip().lower()
        self.list_widget.clear()
        for path, action in self._collect_fn():
            if not action.isEnabled():
                continue
            label = " > ".join(path)
            if query and query not in label.lower():
                continue
            item = QListWidgetItem(label)
            if action.isCheckable():
                item.setText(f"{'✓' if action.isChecked() else ' '}  {label}")
            # QAction そのものではなく、後で再検索するためのパスだけを保持する
            # (プレーンなPythonのリストなので、ラッパー無効化の影響を受けない)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_item_activated(self, item):
        target_path = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if target_path is None:
            return
        # 表示時に集めた QAction は使わず、実行直前に取り直したものを使う
        for path, action in self._collect_fn():
            if path == target_path:
                action.trigger()
                return

    def eventFilter(self, obj, event):
        """
        検索欄(QLineEdit)にフォーカスがある間も、上下キーでリストの選択を
        移動でき、Enterで実行できるようにする。
        """
        if obj is self.search_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                row = min(self.list_widget.currentRow() + 1, self.list_widget.count() - 1)
                self.list_widget.setCurrentRow(row)
                return True
            elif key == Qt.Key.Key_Up:
                row = max(self.list_widget.currentRow() - 1, 0)
                self.list_widget.setCurrentRow(row)
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                current = self.list_widget.currentItem()
                if current is not None:
                    self._on_item_activated(current)
                return True
        return super().eventFilter(obj, event)


#==============================================================================
# カスタムダイアログクラス: クイックアクセスの管理 (項目87)
#==============================================================================
class QuickAccessManagerDialog(QDialog):
    """
    クイックアクセスツールバーへのピン留めを、チェックボックス付きの検索可能な
    一覧から行うためのダイアログ。CommandPaletteDialogと同様、collect_fn()を
    呼ぶたびに現在有効なメニューアクションを集め直す(表示中に保持したQActionは
    実行には使わない)。

    ★ 注意 ★
    OK/キャンセルの概念を持たない、チェック状態の変更をその場で即座に反映する
    「表示/非表示」に近いトグルUI(閉じるボタンのみ)。
    """

    def __init__(self, collect_fn, is_pinned_fn, toggle_fn, parent=None):
        """
        Args:
            collect_fn (callable): CommandPaletteDialogと同じ契約。呼ぶたびに
                現在のメニューアクションを [(パスのリスト, QAction), ...] として返す。
            is_pinned_fn (callable): (識別子文字列) -> bool。現在ピン留め済みかどうか。
            toggle_fn (callable): (識別子文字列, パスのリスト, チェック後の状態bool) -> None。
                チェック状態が変わった項目に対して呼ばれる、ピン留め/解除の実処理。
        """
        super().__init__(parent)
        from core.i18n import tr

        self.setWindowTitle(tr("クイックアクセスの管理"))
        self.resize(480, 420)

        self._collect_fn = collect_fn
        self._is_pinned_fn = is_pinned_fn
        self._toggle_fn = toggle_fn
        self._updating = False  # _update_list() でのチェック状態初期化中はitemChangedを無視する

        layout = QVBoxLayout(self)

        info_label = QLabel(tr("チェックした項目がクイックアクセスツールバーに表示されます。"))
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("コマンドを検索..."))
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.search_edit.textChanged.connect(self._update_list)
        self.list_widget.itemChanged.connect(self._on_item_changed)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)  # Closeボタンは RejectRole → rejected() を発行する
        layout.addWidget(button_box)

        self._update_list("")

    def _update_list(self, text):
        query = text.strip().lower()
        self._updating = True
        try:
            self.list_widget.clear()
            for path, action in self._collect_fn():
                if action.isSeparator():
                    continue
                label = " > ".join(path)
                if query and query not in label.lower():
                    continue
                ident = " > ".join(path)
                item = QListWidgetItem(label)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(Qt.ItemDataRole.UserRole, (ident, path))
                item.setCheckState(
                    Qt.CheckState.Checked if self._is_pinned_fn(ident) else Qt.CheckState.Unchecked
                )
                self.list_widget.addItem(item)
        finally:
            self._updating = False

    def _on_item_changed(self, item):
        if self._updating:
            return
        ident, path = item.data(Qt.ItemDataRole.UserRole)
        checked = item.checkState() == Qt.CheckState.Checked
        self._toggle_fn(ident, path, checked)


#==============================================================================
# カスタムダイアログクラス: キーボードショートカット一覧
#==============================================================================
class ShortcutsDialog(QDialog):
    """
    ヘルプメニューから開く、現在使えるキーボードショートカットの一覧ダイアログ。
    メニューバーを直接走査するため、ショートカットを追加/変更してもここを
    個別に更新し忘れる心配がない(CommandPaletteDialogと同じ collect_fn 方式)。
    """

    def __init__(self, collect_fn, parent=None):
        """
        Args:
            collect_fn (callable): 呼ぶたびに現在のメニューアクションを
                [(パスのリスト, QAction), ...] として新しく収集して返す関数。
        """
        super().__init__(parent)
        self.setWindowTitle("キーボードショートカット一覧")
        self.resize(420, 380)

        layout = QVBoxLayout(self)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["操作", "ショートカット"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)

        rows = []
        for path, action in collect_fn():
            # ★ QUndoStack.createUndoAction() 等、self.xxx として保持されていない
            # QAction はPython側のラッパーがGCで無効化されうる(既知のPySide6の癖)。
            # 収集直後の使用でも起こりうるため、個別に握りつぶして続行する。
            try:
                shortcut = action.shortcut()
            except RuntimeError:
                continue
            if shortcut.isEmpty():
                continue
            rows.append((" > ".join(path), shortcut.toString(QKeySequence.SequenceFormat.NativeText)))

        table.setRowCount(len(rows))
        for row_idx, (label, shortcut_text) in enumerate(rows):
            table.setItem(row_idx, 0, QTableWidgetItem(label))
            table.setItem(row_idx, 1, QTableWidgetItem(shortcut_text))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.reject)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)


#==============================================================================
# カスタムダイアログクラス: タイトル/軸ラベルの編集(項目H-2-4追加分)
#==============================================================================
class LabelEditDialog(QDialog):
    """
    タイトル/X軸ラベル/Y軸ラベルを編集するためのポップアップダイアログ。

    以前はプロパティパネルのQLineEdit直下に小さな「Aa」ボタンを置き、押すと
    文字装飾(太字/イタリック/上付き/下付き)とギリシャ文字/記号パレットを
    ネストしたQMenuとして開いていたが、実機フィードバック(レイアウト画像の
    提示)を受けて、独立したポップアップウィンドウ形式に変更した。装飾ボタンを
    ネストしたメニューの中に隠さず、テキスト入力欄のすぐ下に横一列で常に
    見えるようにし、データセット操作ボタン列と同じ意匠
    (`QPushButton[iconOnly="true"]`)の正方形アイコンボタンにしている。

    書式適用のロジック(選択範囲をmathtextで包む/カーソル位置に記号を挿入する)
    自体は、以前 gui/mixins/settings_mixin.py 側にあった
    `_apply_label_mathtext_format`/`_on_label_symbol_clicked` と同じ考え方を、
    このダイアログの内部QLineEdit(`self.text_edit`)に対して直接行う形に
    移植している(ダイアログが受け持つのは自分自身が持つ1つの入力欄だけなので、
    以前のfield_keyディクショナリ経由の間接参照は不要になった)。
    """

    def __init__(self, initial_text, window_title, symbol_palette, parent=None):
        """
        Args:
            initial_text (str): 編集対象のQLineEditが現在持っているテキスト。
            window_title (str): ダイアログのタイトルバーに出す文字列
                (例: 「タイトルを編集」)。
            symbol_palette (list[tuple[str, str]]): (表示グリフ, mathtextマクロ名)
                のペアのリスト。呼び出し側(gui/main_window.py)の
                LABEL_SYMBOL_PALETTEをそのまま渡す想定(dialogs.py は
                main_window.py を逆import できないため、呼び出し側から渡す)。
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        self.text_edit = QLineEdit(initial_text)
        self.text_edit.setMinimumHeight(34)
        larger_font = QFont(self.text_edit.font())
        larger_font.setPointSize(larger_font.pointSize() + 1)
        self.text_edit.setFont(larger_font)
        layout.addWidget(self.text_edit)

        # ★ 実機フィードバック: 「ボタンを押してmathtext形式で書かれたラベルが
        #   出力されるんじゃなくて実際にボールドとかイタリックとかが適用
        #   されてるテキストが見れるようにしたい」。text_edit自体はQLineEdit
        #   なので部分的なリッチテキスト表示はできない(生のmathtext構文の
        #   ままにせざるを得ない)。代わりに、実際の描画結果をレンダリングする
        #   プレビュー欄をtext_editの下に常設し、太字/イタリック等を適用する
        #   たびに実際に適用された見た目を確認できるようにする(タイトル/
        #   軸ラベル欄本体のプレビュー、gui/mathtext_preview.pyを流用)。
        self.preview_label = FitWidthPixmapLabel()
        self.preview_label.setObjectName("mathtext_preview_label")
        self.preview_label.setMinimumHeight(36)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.preview_label)
        self.text_edit.textChanged.connect(self._refresh_preview)

        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        def _make_icon_button(icon_name, tooltip):
            button = QPushButton()
            button.setIcon(icon_utils.icon(icon_name, size=16))
            button.setToolTip(tooltip)
            button.setProperty("iconOnly", True)
            button.setFixedSize(28, 28)
            # ★ 実機フィードバック(バグ報告、下記参照): この装飾ボタンが
            #   フォーカスを奪わないようにするための本質的な修正。
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button_row.addWidget(button)
            return button

        bold_button = _make_icon_button("bold", "太字")
        italic_button = _make_icon_button("italic", "イタリック")
        superscript_button = _make_icon_button("superscript", "上付き文字")
        subscript_button = _make_icon_button("subscript", "下付き文字")

        # ★ 実機フィードバック(バグ報告): 「文字選択してハイライトされてから
        #   ボタン押しても文字を選択してって出る」。
        #   当初は「QPushButton.clickedはマウスの押下→解放が完了した後に発火
        #   するため、pressed(押下の瞬間)で選択範囲を保存しておけば間に合う」
        #   という仮説で対処したが、実際にQTest.mouseClick()で実クリックを
        #   再現したところ、pressedが発火する時点で既にtext_edit.
        #   hasSelectedText()がFalseになっており、直っていなかったことが判明。
        #   真因は「clickedが遅い」ことではなく、QAbstractButton系ウィジェットの
        #   既定フォーカスポリシー(StrongFocus)により、Qtがマウス押下イベントを
        #   ボタンへ配送する"前"にフォーカスをボタン側へ移してしまい、その
        #   フォーカスアウトでQLineEdit側の選択状態が失われてしまうこと
        #   (この経路はボタン自身のpressed/clickedシグナルより早く走るため、
        #   pressedで捕捉しても既に手遅れ)。
        #   本質的な修正は、これらの装飾ボタンにフォーカスを一切渡さないこと
        #   (上の_make_icon_button内でsetFocusPolicy(Qt.NoFocus)を設定)。
        #   これによりボタンをクリックしてもtext_edit側のフォーカス・選択状態が
        #   維持されたまま保たれる。pressedでの事前捕捉ロジック自体は無害かつ
        #   (フォーカスが移らない環境が万一あった場合の)保険として残す。
        self._pending_selection = None  # (start, selected_text) または選択なしならNone
        self._pending_cursor = 0

        for button in (bold_button, italic_button, superscript_button, subscript_button):
            button.pressed.connect(self._capture_pending_selection)

        # ★ 実機フィードバック(バグ報告): 「mathtextを複数適用しようとすると
        #   (例: イタリック+ボールド、上付き+ボールド)バグる」。
        #   kind引数の意味とバグの詳細は_apply_wrap()のdocstring参照。
        bold_button.clicked.connect(lambda: self._apply_wrap("bold", lambda s: f"\\mathbf{{{s}}}"))
        italic_button.clicked.connect(lambda: self._apply_wrap("italic", lambda s: f"\\mathit{{{s}}}"))
        superscript_button.clicked.connect(lambda: self._apply_wrap("super", lambda s: f"{{}}^{{{s}}}"))
        subscript_button.clicked.connect(lambda: self._apply_wrap("sub", lambda s: f"{{}}_{{{s}}}"))

        # ★ 項目81(mathtext拡充)のギリシャ文字/記号パレットは、以前と同じく
        #   小さなグリッドパネルをQMenuに埋め込む形のポップオーバーとして残す
        #   (32個の記号を常時ボタン表示すると場所を取りすぎるため、ここだけは
        #   ドロップダウン形式が妥当と判断した)。
        symbol_button = QToolButton()
        symbol_button.setText("Ω")
        symbol_button.setToolTip("ギリシャ文字・数学記号を挿入")
        symbol_button.setProperty("iconOnly", True)
        symbol_button.setFixedSize(28, 28)
        symbol_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # QToolButtonは既定でNoFocus(QPushButtonと異なりStrongFocusではない)
        # だが、上の装飾ボタンと同じ理由により明示的に指定しておく。
        symbol_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # ★ 上と同じ理由(ポップアップを開く動作自体でQLineEditの選択範囲が
        #   失われうる)で、メニューが開く前のpressedで選択範囲を確定させる。
        symbol_button.pressed.connect(self._capture_pending_selection)

        symbol_menu = QMenu(symbol_button)
        symbol_panel = QWidget()
        symbol_grid = QGridLayout(symbol_panel)
        symbol_grid.setContentsMargins(6, 6, 6, 6)
        symbol_grid.setSpacing(2)
        for index, (glyph, macro) in enumerate(symbol_palette):
            item_button = QToolButton()
            item_button.setText(glyph)
            item_button.setToolTip(f"\\{macro}")
            item_button.setFixedSize(26, 26)
            item_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            item_button.clicked.connect(
                lambda checked=False, m=macro, sm=symbol_menu: (self._insert_symbol(m), sm.close())
            )
            symbol_grid.addWidget(item_button, index // 4, index % 4)
        symbol_widget_action = QWidgetAction(symbol_button)
        symbol_widget_action.setDefaultWidget(symbol_panel)
        symbol_menu.addAction(symbol_widget_action)
        symbol_button.setMenu(symbol_menu)
        button_row.addWidget(symbol_button)

        button_row.addStretch(1)
        layout.addLayout(button_row)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._refresh_preview()

    def _refresh_preview(self):
        """
        text_editの現在の内容を実際にレンダリングし、preview_labelへ反映する。
        タイトル/軸ラベル欄本体のライブプレビュー(gui/mixins/settings_mixin.py
        の_refresh_label_preview)と同じ考え方・同じレンダラ(gui/
        mathtext_preview.py)を、このダイアログ内のtext_edit用に流用している。
        """
        from gui import theme
        from gui.mathtext_preview import render_mathtext_to_pixmap

        tokens = theme.current_tokens()
        text = self.text_edit.text()
        color = tokens["text_primary"] if text else tokens["text_muted"]
        pixmap = render_mathtext_to_pixmap(text if text else " ", color=color, fontsize=15)
        # ★ 実機フィードバック: 「ここの文字サイズを枠内に収まるようにして」。
        #   set_natural_pixmap()がpreview_label自身の実際の幅に合わせて
        #   自動的に縮小する(FitWidthPixmapLabel、gui/mathtext_preview.py参照)。
        self.preview_label.set_natural_pixmap(pixmap)

    def _capture_pending_selection(self):
        """
        装飾/記号ボタンが「押された瞬間」(pressed)に呼ばれ、その時点の
        text_editの選択範囲を_pending_selectionへ保存しておく。ボタンの
        clicked(マウス押下→解放が完了した後に発火)まで待つと、その間に
        フォーカスがボタン側へ移り、QLineEditの選択範囲が失われてしまう
        環境があるため(実機で報告されたバグ)、フォーカスがまだtext_editに
        残っているpressedの時点で確定させる。
        """
        if self.text_edit.hasSelectedText():
            self._pending_selection = (
                self.text_edit.selectionStart(), self.text_edit.selectedText()
            )
        else:
            self._pending_selection = None
        self._pending_cursor = self.text_edit.cursorPosition()

    # 既に$...$で囲まれた1個のmathtext断片全体(ちょうど直前の装飾操作の結果)が
    # 選択されているかどうかを判定するための正規表現群。_apply_wrap()参照。
    _MATH_SPAN_RE = re.compile(r'^\$(.*)\$$', re.DOTALL)
    _MATHBF_RE = re.compile(r'^\\mathbf\{(.*)\}$', re.DOTALL)
    _MATHIT_RE = re.compile(r'^\\mathit\{(.*)\}$', re.DOTALL)

    def _apply_wrap(self, kind, wrap_fn):
        """
        太字/イタリック/上付き/下付きボタン共通の処理。pressed時点で確定させた
        _pending_selection(選択範囲が失われる前に保存したもの、__init__の
        _capture_pending_selection参照)を使い、選択されていた文字列を
        wrap_fn()が返すmathtextの中身(前後の$は含まない)で置き換え、
        改めて$...$で囲む。

        Args:
            kind (str): "bold"/"italic"/"super"/"sub"のいずれか。
                "bold"/"italic"の組み合わせ検出にのみ使う。
            wrap_fn (callable): 中身の文字列を受け取り、装飾後の中身
                (前後の$は含まない断片、例: "\\mathbf{...}")を返す関数。

        ★ 実機フィードバック(バグ報告): 「mathtextを複数適用しようとすると
        (例: イタリック+ボールド、上付き+ボールド)バグる」。
        このダイアログは各装飾操作の後、置き換えた範囲を丸ごと選択状態にする
        (末尾のsetSelection参照)ため、続けて別の装飾ボタンを押すと、選択
        文字列は既に"$\\mathbf{wavelength}$"のような、前後を$で囲まれた
        1個のmathtext断片になっている。これに気づかず単純にwrap_fn()の結果を
        新しい$...$でさらに包んでいたため、"$\\mathit{$\\mathbf{wavelength}$}$"
        のように$が入れ子になった不正なmathtext構文になっていた。
        対策として、選択文字列が既に$...$で囲まれた単一の断片であれば、まず
        中身(内側の$無し部分)だけを取り出してから改めて$...$で囲み直す。

        さらに、太字(\\mathbf)とイタリック(\\mathit)は共にmatplotlib
        mathtextの「フォントクラス」指定であり、$\\mathit{\\mathbf{x}}$の
        ように入れ子にしても内側の指定で上書きされるだけで実際には合成
        されない(実機検証済み)。太字とイタリックを組み合わせようとしている
        場合(既存の中身が\\mathbf{...}でこれからイタリックを適用する、また
        はその逆)は、代わりに太字とイタリックを同時に表現できる
        \\boldsymbol{...}に置き換える。
        """
        if not self._pending_selection:
            QMessageBox.information(
                self, "文字装飾", "装飾したい文字を選択してから、このボタンを押してください。"
            )
            return
        start, selected = self._pending_selection
        span_match = self._MATH_SPAN_RE.match(selected)
        inner = span_match.group(1) if span_match else selected

        combined = None
        if kind == "bold":
            m = self._MATHIT_RE.match(inner)
            if m:
                combined = f"\\boldsymbol{{{m.group(1)}}}"
        elif kind == "italic":
            m = self._MATHBF_RE.match(inner)
            if m:
                combined = f"\\boldsymbol{{{m.group(1)}}}"

        new_inner = combined if combined is not None else wrap_fn(inner)
        replacement = f"${new_inner}$"
        text = self.text_edit.text()
        self.text_edit.setText(text[:start] + replacement + text[start + len(selected):])
        self.text_edit.setSelection(start, len(replacement))

    def _insert_symbol(self, macro):
        """
        ギリシャ文字/記号パレットの1項目が選ばれたときの処理。装飾ボタンと
        異なり、選択文字列を装飾するのではなく$\\macro$という新しい断片を
        挿入するものなので、pressed時点の選択範囲(_pending_selection)が
        あればそれを置き換え、無ければpressed時点のカーソル位置
        (_pending_cursor)に挿入する。
        """
        text = self.text_edit.text()
        if self._pending_selection:
            start, selected = self._pending_selection
            end = start + len(selected)
        else:
            start = end = self._pending_cursor
        replacement = f"$\\{macro}$"
        self.text_edit.setText(text[:start] + replacement + text[end:])
        self.text_edit.setCursorPosition(start + len(replacement))

    def get_text(self):
        return self.text_edit.text()


#==============================================================================
# カスタムダイアログクラス: 凡例の表示順序
#==============================================================================
class LegendOrderDialog(QDialog):
    """
    凡例の表示順序を、データセットの描画順とは独立にドラッグで並べ替えるためのダイアログ。
    QListWidget の InternalMove ドラッグ&ドロップをそのまま順序編集に使う。
    """

    def __init__(self, labels, parent=None):
        """
        Args:
            labels (list[str]): 現在の軸の凡例ラベル(既存の並び順、または
                以前保存した並び順)を並べたリスト。
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("凡例の順序")
        self.resize(320, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("ドラッグして凡例の表示順序を変更できます:"))

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_widget.addItems(labels)
        layout.addWidget(self.list_widget)

        reset_button = QPushButton("描画順にリセット")
        reset_button.clicked.connect(self._on_reset)
        layout.addWidget(reset_button)
        self._original_labels = list(labels)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_reset(self):
        """凡例をカスタム順ではなく、常にデータセットの描画順で表示するようにリセットする"""
        self.list_widget.clear()

    def get_order(self):
        """
        現在のリスト順を返す。「描画順にリセット」が押された場合は空リスト
        (=カスタム順を使わず、常に描画順に従う)を返す。
        """
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]


#==============================================================================
# カスタムダイアログクラス: バッチエクスポート
#==============================================================================
class BatchExportDialog(QDialog):
    """
    複数の画像をまとめて一括書き出しするための設定ダイアログ。
    2つのモードを切り替えられる:
      1. 現在のプロジェクトの各サブプロットを、個別の画像として書き出す
      2. 複数のプロジェクトファイル(.graphica/.pkl)を選び、それぞれの完成図を書き出す
    実際の書き出し処理自体はこのダイアログの責務ではなく、呼び出し側が
    get_*() で取得した設定を使って行う。
    """

    def __init__(self, subplot_count, parent=None, extra_formats=None):
        """
        Args:
            extra_formats (list[str] | None): プラグインが register_exporter()
                (項目B-2) で登録した形式名を、既存のPNG/PDF/SVGに追加する。
        """
        super().__init__(parent)
        self.setWindowTitle("バッチエクスポート")
        self.resize(480, 480)

        layout = QVBoxLayout(self)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "現在のプロジェクトの各サブプロットを個別に書き出す",
            "複数のプロジェクトファイルをまとめて書き出す",
        ])
        layout.addWidget(self.mode_combo)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # --- モード1: サブプロット選択 ---
        subplot_page = QWidget()
        subplot_page_layout = QVBoxLayout(subplot_page)
        subplot_page_layout.addWidget(QLabel("書き出すサブプロットを選択してください:"))
        self.subplot_list = QListWidget()
        self.subplot_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for i in range(max(subplot_count, 1)):
            item = QListWidgetItem(f"プロット {i + 1}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.subplot_list.addItem(item)
        subplot_page_layout.addWidget(self.subplot_list)
        self.stack.addWidget(subplot_page)

        # --- モード2: プロジェクトファイル選択 ---
        files_page = QWidget()
        files_page_layout = QVBoxLayout(files_page)
        files_page_layout.addWidget(QLabel("書き出すプロジェクトファイル(.graphica/.pkl)を追加してください:"))
        self.project_files_list = QListWidget()
        files_page_layout.addWidget(self.project_files_list)
        files_button_row = QHBoxLayout()
        add_files_button = QPushButton("追加...")
        add_files_button.clicked.connect(self._on_add_project_files)
        remove_files_button = QPushButton("削除")
        remove_files_button.clicked.connect(self._on_remove_selected_project_files)
        files_button_row.addWidget(add_files_button)
        files_button_row.addWidget(remove_files_button)
        files_button_row.addStretch()
        files_page_layout.addLayout(files_button_row)
        self.stack.addWidget(files_page)

        self.mode_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        # --- 共通設定 ---
        form = QFormLayout()

        output_dir_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setReadOnly(True)
        browse_button = QPushButton("参照...")
        browse_button.clicked.connect(self._on_browse_output_dir)
        output_dir_row.addWidget(self.output_dir_edit)
        output_dir_row.addWidget(browse_button)
        form.addRow("出力先フォルダ", output_dir_row)

        self.prefix_edit = QLineEdit("export")
        form.addRow("ファイル名の接頭辞", self.prefix_edit)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "PDF", "SVG"])
        if extra_formats:
            self.format_combo.addItems(extra_formats)
        form.addRow("形式", self.format_combo)

        self.dpi_spinbox = QSpinBox()
        self.dpi_spinbox.setRange(50, 1200)
        self.dpi_spinbox.setValue(150)
        self.dpi_spinbox.setSuffix(" dpi")
        form.addRow("解像度(ラスター形式時)", self.dpi_spinbox)

        self.transparent_checkbox = QCheckBox("背景を透過")
        self.transparent_checkbox.setChecked(True)
        form.addRow(self.transparent_checkbox)

        # SVG出力時の文字の扱い(項目88): ExportDialogと同じオプション
        self.svg_text_as_path_checkbox = QCheckBox("文字をアウトライン化する(SVG)")
        self.svg_text_as_path_checkbox.setToolTip(
            "SVG出力時、目盛りの数字やラベルの文字をパス(輪郭線)として出力します。"
            "PNG/PDF形式には影響しません。"
        )
        form.addRow(self.svg_text_as_path_checkbox)

        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("実行")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def _on_add_project_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "プロジェクトファイルを選択", "", "Project Files (*.graphica *.pkl)"
        )
        for path in paths:
            self.project_files_list.addItem(path)

    def _on_remove_selected_project_files(self):
        for item in self.project_files_list.selectedItems():
            self.project_files_list.takeItem(self.project_files_list.row(item))

    def _on_browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "出力先フォルダを選択")
        if directory:
            self.output_dir_edit.setText(directory)

    def get_mode(self):
        """'subplots' または 'project_files' を返す"""
        return "subplots" if self.mode_combo.currentIndex() == 0 else "project_files"

    def get_selected_subplot_indices(self):
        return [
            i for i in range(self.subplot_list.count())
            if self.subplot_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def get_project_file_paths(self):
        return [self.project_files_list.item(i).text() for i in range(self.project_files_list.count())]

    def get_common_options(self):
        return {
            'output_dir': self.output_dir_edit.text(),
            'prefix': self.prefix_edit.text().strip() or "export",
            'format': self.format_combo.currentText().lower(),
            'dpi': self.dpi_spinbox.value(),
            'transparent': self.transparent_checkbox.isChecked(),
            'svg_text_as_path': self.svg_text_as_path_checkbox.isChecked(),
        }


#==============================================================================
# カスタムダイアログクラス: 新規データセットを作成 (項目63)
#==============================================================================
class NewDatasetDialog(QDialog):
    """
    ファイル読み込みを介さず、名前・列名・初期行数だけを指定して空のデータセットを
    作成するためのダイアログ(項目63)。作成後はデータエディタが自動的に開き、
    そこでセルに直接データを打ち込んでいく運用を想定している。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.i18n import tr

        self.setWindowTitle(tr("新規データセットを作成"))
        self.resize(360, 180)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(tr("新規データセット"))
        layout.addRow(tr("データセット名"), self.name_edit)

        self.columns_edit = QLineEdit("X, Y")
        self.columns_edit.setToolTip(tr("カンマ区切りで列名を入力してください(例: X, Y, 誤差)"))
        layout.addRow(tr("列名 (カンマ区切り)"), self.columns_edit)

        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setRange(0, 10000)
        self.rows_spinbox.setValue(5)
        layout.addRow(tr("初期の空行数"), self.rows_spinbox)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        apply_form_spacing(self)

    def _on_accept(self):
        from core.i18n import tr
        if not self.get_dataset_name():
            QMessageBox.warning(self, tr("新規データセットを作成"), tr("データセット名を入力してください。"))
            return
        if not self.get_column_names():
            QMessageBox.warning(self, tr("新規データセットを作成"), tr("列名を1つ以上入力してください。"))
            return
        self.accept()

    def get_dataset_name(self):
        return self.name_edit.text().strip()

    def get_column_names(self):
        """カンマ区切りの入力を列名のリストに変換する(重複・空文字は除く)"""
        raw = self.columns_edit.text()
        names = [c.strip() for c in raw.split(',') if c.strip()]
        unique_names = []
        for name in names:
            if name not in unique_names:
                unique_names.append(name)
        return unique_names

    def get_row_count(self):
        return self.rows_spinbox.value()