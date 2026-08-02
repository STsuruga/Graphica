import numpy as np
import pandas as pd
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTextBrowser,
                               QDialogButtonBox, QFormLayout, QComboBox,
                               QDoubleSpinBox, QLabel, QLineEdit, QSpinBox,
                               QPushButton, QHBoxLayout, QPlainTextEdit,
                               QApplication, QFileDialog, QMessageBox, QGroupBox,
                               QTableWidget, QTableWidgetItem)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QFont


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

        self.setWindowTitle(f"{APP_NAME} について")
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

        version_label = QLabel(f"バージョン {__version__}")
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
            <tr style="background-color: #f0f0f0;">
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
            <tr style="background-color: #f0f0f0;">
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
            <tr style="background-color: #f0f0f0;">
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
        """
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
    pandas.eval() で使用できる構文について説明します。
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
            <b>pandas.eval()</b> 機能を利用して、列データを使った計算を行います。
            「出力先の列」に指定した列に、計算式の結果が一度に適用されます（Excelのオートフィルのように、全行に適用されます）。
        </p>
        
        <hr>
        
        <h2>1. 基本的な算術演算子 🧮</h2>
        <p>列名（例: <code>A</code>, <code>B</code>）や数値をそのまま使えます。</p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background-color: #f0f0f0;"><th>計算式 (入力例)</th><th>実行内容</th></tr>
            <tr><td><code>A + B</code></td><td>A列とB列の各行を足し算します。</td></tr>
            <tr><td><code>A * 100</code></td><td>A列の全データを100倍します。</td></tr>
            <tr><td><code>(A + B) / 2</code></td><td>A列とB列の平均値を計算します。</td></tr>
            <tr><td><code>A ** 2</code></td><td>A列の値を2乗します。</td></tr>
            <tr><td><code>A % 5</code></td><td>A列の値を5で割った余りを計算します。</td></tr>
        </table>
        
        <hr>
        
        <h2>2. 一般的な数学関数 📈</h2>
        <p>
            pandas.eval() は内部で <a href="https://numexpr.readthedocs.io/en/latest/user_guide.html#supported-functions">NumExpr ライブラリ</a> 
            がサポートする関数を利用可能です。
        </p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background-color: #f0f0f0;"><th>関数 (入力例)</th><th>意味</th></tr>
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
            <tr style="background-color: #f0f0f0;"><th>計算式 (入力例)</th><th>実行内容</th></tr>
            <tr><td><code>A > 10</code></td><td>A列の値が10より大きい行はTrueになります。</td></tr>
            <tr><td><code>A == B</code></td><td>A列とB列の値が等しい行はTrueになります。</td></tr>
            <tr><td><code>A > 5 and B < 3</code></td><td>Aが5より大きく、<b>かつ</b> Bが3未満の行だけTrueになります。</td></tr>
            <tr><td><code>A < 0 or A > 10</code></td><td>Aが0未満、<b>または</b> Aが10より大きい行がTrueになります。</td></tr>
            <tr><td><code>not (A > 5)</code></td><td>Aが5より大きい、という条件を否定します (A <= 5 と同じ)。</td></tr>
        </table>
        """
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

    def __init__(self, title, text, parent=None, csv_data=None):
        """
        Args:
            title (str): ウィンドウタイトル。
            text (str): 表示する結果テキスト (複数行可)。
            parent (QWidget, optional): 親ウィジェット。
            csv_data (pandas.DataFrame, optional): CSV保存用の構造化データ。
                None の場合は「CSVとして保存」ボタンを表示しない
                (表示テキストをそのままパースするのではなく、呼び出し側が
                 意味のある表形式データを渡す設計にしている)。
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
        layout.insertRow(0, "検出タイプ:", self.type_combo) 

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
        layout.addRow("Y値の閾値 (Height):", self.height_spinbox)
        layout.addRow("最小X距離 (Distance):", self.distance_spinbox)
        layout.addRow("最小突出度 (Prominence):", self.prominence_spinbox)
        
        # --- OK / Cancel ボタン ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept) # OK が押されたら accept
        button_box.rejected.connect(self.reject) # Cancel が押されたら reject
        layout.addRow(button_box)

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
    
    def __init__(self, parent=None):
        """
        ダイアログのUIコンポーネントを初期化します。
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
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
            "指数関数 (y = a * exp(bx))"
            # (将来的にここに関数の種類を追加可能)
        ])
        layout.addWidget(self.fit_type_combo)
        
        # --- OK / Cancel ボタン ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    @staticmethod
    def get_fit_type(parent=None):
        """
        【スタティックメソッド】
        ダイアログをモーダルで表示し、OKが押された場合は選択されたフィットタイプ名 (文字列) を、
        Cancelが押された場合は None を返します。
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
        
        Returns:
            str or None: 選択された関数の名前 (例: "線形 (y = ax + b)")、または None。
        """
        dialog = FitDialog(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # コンボボックスで現在選択されているテキストを返す
            return dialog.fit_type_combo.currentText()
        return None


#==============================================================================
# カスタムダイアログクラス (5)
#==============================================================================
class ColumnCalculatorDialog(QDialog):
    """
    データエディタの「列の計算」機能で使用するダイアログクラスです。
    出力先（新規または既存）の列名と、pandas.eval() で実行する計算式を
    ユーザーに入力させます。
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
        
        self.output_col_label = QLabel("出力先の列 (既存または新規):")
        
        # --- 出力先コンボボックス ---
        self.output_col_combo = QComboBox()
        self.output_col_combo.addItems(self.column_names) # 既存の列を選択肢に追加
        # ★ setEditable(True) が重要
        # これにより、ユーザーは既存の列を選択するだけでなく、
        # テキストボックスのように新しい列名を自由に入力できます。
        self.output_col_combo.setEditable(True) 
        
        self.formula_label = QLabel("計算式 (例: A + B * 2):")

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
        preset_source_row.addWidget(QLabel("対象列:"))
        self.preset_source_combo = QComboBox()
        self.preset_source_combo.addItems(self.column_names)
        preset_source_row.addWidget(self.preset_source_combo)
        preset_source_row.addWidget(QLabel("移動平均の窓幅:"))
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
        form_layout.addRow("幅:", self.width_spinbox)
        form_layout.addRow("高さ:", self.height_spinbox)
        form_layout.addRow("単位:", self.unit_combo)
        form_layout.addRow("解像度:", self.dpi_spinbox)

        # 2. 全体をまとめる垂直レイアウト
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)      # フォームレイアウトを追加
        main_layout.addWidget(self.preview_button) # プレビューボタンを追加
        main_layout.addWidget(self.preview_label)  # プレビュー表示エリアを追加
        main_layout.addWidget(button_box)       # 保存/Cancelボタンを追加
        
        self.setLayout(main_layout)

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
            "dpi": self.dpi_spinbox.value()
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
    """

    def __init__(self, df, file_name, parent=None):
        """
        Args:
            df (pandas.DataFrame): 読み込んだファイルのデータ (プレビュー表示用)。
            file_name (str): 表示用のファイル名。
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle(f"列の選択: {file_name}")
        self.resize(600, 450)

        columns = [str(c) for c in df.columns]

        layout = QVBoxLayout(self)

        info_label = QLabel(
            f"{len(df)}行 × {len(columns)}列 が見つかりました。"
            "プレビューを確認し、X軸・Y軸に使う列を選択してください。"
        )
        layout.addWidget(info_label)

        # --- プレビューテーブル (先頭最大20行、読み取り専用) ---
        preview_row_count = min(len(df), 20)
        table = QTableWidget(preview_row_count, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r in range(preview_row_count):
            for c in range(len(columns)):
                value = df.iloc[r, c]
                text = "" if pd.isna(value) else str(value)
                table.setItem(r, c, QTableWidgetItem(text))
        table.resizeColumnsToContents()
        layout.addWidget(table)

        # --- X/Y列選択 ---
        form = QFormLayout()
        self.x_col_combo = QComboBox()
        self.x_col_combo.addItems(columns)
        self.y_col_combo = QComboBox()
        self.y_col_combo.addItems(columns)
        if len(columns) >= 2:
            self.x_col_combo.setCurrentIndex(0)
            self.y_col_combo.setCurrentIndex(1)
        form.addRow("X軸の列:", self.x_col_combo)
        form.addRow("Y軸の列:", self.y_col_combo)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_selected_columns(self):
        """
        選択された (X軸の列名, Y軸の列名) をタプルで返す。

        Returns:
            tuple (str, str): (x_col_name, y_col_name)
        """
        return self.x_col_combo.currentText(), self.y_col_combo.currentText()