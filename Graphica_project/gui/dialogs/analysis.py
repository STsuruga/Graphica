# gui/dialogs/analysis.py
"""
解析のダイアログ。

gui/dialogs.py(5,560行・47ダイアログ)を機能群ごとに分割したもの
(改善ボード B-2)。呼び出し側は従来どおり `from gui.dialogs import X` で
参照できる(gui/dialogs/__init__.py が再エクスポートしている)。
"""

import numpy as np
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from gui.theme import apply_form_spacing




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
            "ローレンツ関数 (y = a / (1 + ((x-b)/c)^2) + d)",
            "擬似フォークト関数 (y = a*(η/(1+((x-b)/c)^2) + (1-η)*exp(-4ln2*((x-b)/c)^2)) + d)",
            "フォークト関数 (y = a*Re[wofz((x-b+iγ)/(σ√2))] / (σ√(2π)) + d)",
            "2成分指数関数 (y = a1*exp(b1*x) + a2*exp(b2*x) + c)",
            "ボルツマンシグモイド (y = a2 + (a1-a2) / (1 + exp((x-x0)/dx)))",
            "シグモイド (y = a / (1 + exp(-b(x-c))))",
            "ヒルの式 (y = vmax*x^n / (k^n + x^n))",
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

        # --- ロバストフィット(項目C-407) ---
        loss_form = QFormLayout()
        self.loss_combo = QComboBox()
        self.loss_combo.addItem("通常の最小二乗(既定)", "linear")
        self.loss_combo.addItem("ロバスト(Soft L1)", "soft_l1")
        self.loss_combo.addItem("ロバスト(Huber)", "huber")
        self.loss_combo.setToolTip(
            "外れ値に引きずられにくい損失関数に切り替える(scipy.optimize.least_squares)。\n"
            "Soft L1/Huberはいずれも外れ値の寄与を線形二乗より抑える点で似ているが、\n"
            "Huberの方が正常値付近では通常の最小二乗に近い挙動になる。"
        )
        loss_form.addRow("損失関数", self.loss_combo)
        layout.addLayout(loss_form)

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

        # --- パラメータごとの初期値・固定・範囲拘束(項目C-403) ---
        # 「収束しないフィットの大半はこれで解決」— ユーザーがパラメータの
        # 自動推定初期値を上書きしたり、値を固定して自由パラメータから除外したり、
        # [最小,最大]の範囲に拘束したりできるようにする。
        layout.addWidget(QLabel("パラメータごとの初期値・固定・範囲拘束(収束しない場合に指定してください):"))
        self.param_table = QTableWidget(0, 6)
        self.param_table.setHorizontalHeaderLabels(
            ["パラメータ", "初期値/固定値", "固定", "範囲拘束", "最小", "最大"]
        )
        self.param_table.verticalHeader().setVisible(False)
        self.param_table.setMaximumHeight(180)
        layout.addWidget(self.param_table)

        self.fit_type_combo.currentTextChanged.connect(self._rebuild_param_table)
        # カスタム数式は入力途中でもパラメータ数が変わりうるため、1文字入力される
        # たびに再構築する(_rebuild_param_tableはパース失敗時に0行にするだけで
        # 例外を外に投げないため、入力途中でクラッシュすることはない)。
        self.custom_formula_edit.textChanged.connect(self._rebuild_param_table)

        # --- 信頼帯・予測帯(項目C-405) ---
        # 既定は「表示しない」(計算コストと帯の重ね描きが常に欲しいとは限らないため)。
        band_form = QFormLayout()
        self.band_combo = QComboBox()
        self.band_combo.addItems(["表示しない", "信頼帯 (95%)", "予測帯 (95%)"])
        self.band_combo.setToolTip(
            "信頼帯: 真の回帰曲線が収まると考えられる範囲(パラメータの不確かさのみ)。\n"
            "予測帯: 次に測定する新しい1点が収まると考えられる範囲\n"
            "(パラメータの不確かさに加え、観測ノイズの分散も加味するため信頼帯より広くなる)。"
        )
        band_form.addRow("信頼帯/予測帯", self.band_combo)
        layout.addLayout(band_form)

        # --- OK / Cancel ボタン ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._rebuild_param_table()

    def _on_fit_type_changed(self, text):
        """フィット関数の選択が変わったときに、カスタム数式入力欄の表示/非表示を切り替える"""
        is_custom = "カスタム数式" in text
        self.custom_formula_label.setVisible(is_custom)
        self.custom_formula_edit.setVisible(is_custom)

    def _rebuild_param_table(self, *_args):
        """
        項目C-403: フィットタイプ(コンボボックス)またはカスタム数式の入力内容が
        変わるたびに、パラメータテーブルの行を作り直す。get_fit_param_names()が
        ValueErrorを送出するケース(フィットタイプ未確定、カスタム数式が空/
        パース不能な入力途中の状態)は握りつぶして0行にする — ダイアログを
        クラッシュさせず、単に「まだ何も出さない」だけにする。

        各行の「初期値/固定値」欄はダブルユースで、「固定」チェックが外れている
        間はp0の初期値(ユーザーが実際に触った場合のみp0_overridesに採用される。
        触らなければフィットタイプごとの自動推定デフォルトのまま)、「固定」
        チェックが入っている間はその値でパラメータを固定する(fixed_params)。
        「範囲拘束」チェックは「固定」チェックと排他的に扱う(固定パラメータは
        最適化されないため範囲の概念自体が無意味なので、固定時は無効化する)。
        """
        fit_type = self.fit_type_combo.currentText()
        custom_formula = self.custom_formula_edit.text().strip() if "カスタム数式" in fit_type else None
        try:
            from core.analysis import get_fit_param_names
            param_names = get_fit_param_names(fit_type, custom_formula)
        except ValueError:
            param_names = []

        self.param_table.setRowCount(0)
        self.param_table.setRowCount(len(param_names))
        for row, name in enumerate(param_names):
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.param_table.setItem(row, 0, name_item)

            value_spin = QDoubleSpinBox()
            value_spin.setRange(-1e12, 1e12)
            value_spin.setDecimals(6)
            value_spin.blockSignals(True)
            value_spin.setValue(1.0)
            value_spin.blockSignals(False)
            # ★ ユーザーが実際に値を変更したかどうかを追跡する(初期化時の
            # setValue(1.0)はblockSignals()でこのフラグを立てない)。
            # get_param_settings()はこのフラグが立っている行だけをp0_overrides
            # に含める。立っていない行は「フィットタイプごとの自動推定デフォルト
            # のまま」を意味する(このダイアログはx_data/y_dataを持たないため、
            # 自動推定値そのものはここでは計算・表示できない)。
            value_spin.setProperty("_user_overridden", False)
            value_spin.valueChanged.connect(
                lambda _v, w=value_spin: w.setProperty("_user_overridden", True)
            )
            self.param_table.setCellWidget(row, 1, value_spin)

            fixed_check = QCheckBox()
            self.param_table.setCellWidget(row, 2, fixed_check)

            range_check = QCheckBox()
            self.param_table.setCellWidget(row, 3, range_check)

            min_spin = QDoubleSpinBox()
            min_spin.setRange(-1e12, 1e12)
            min_spin.setDecimals(6)
            min_spin.setValue(-1e12)
            min_spin.setEnabled(False)
            self.param_table.setCellWidget(row, 4, min_spin)

            max_spin = QDoubleSpinBox()
            max_spin.setRange(-1e12, 1e12)
            max_spin.setDecimals(6)
            max_spin.setValue(1e12)
            max_spin.setEnabled(False)
            self.param_table.setCellWidget(row, 5, max_spin)

            fixed_check.toggled.connect(
                lambda checked, rc=range_check, mn=min_spin, mx=max_spin:
                    self._on_param_fixed_toggled(checked, rc, mn, mx)
            )
            range_check.toggled.connect(
                lambda checked, mn=min_spin, mx=max_spin: (mn.setEnabled(checked), mx.setEnabled(checked))
            )

        self.param_table.resizeColumnsToContents()

    @staticmethod
    def _on_param_fixed_toggled(checked, range_check, min_spin, max_spin):
        """「固定」チェックが入っている間は「範囲拘束」チェックと最小/最大欄を
        無効化する(固定パラメータは最適化されないため範囲拘束は意味を持たない)。"""
        range_check.setEnabled(not checked)
        min_spin.setEnabled((not checked) and range_check.isChecked())
        max_spin.setEnabled((not checked) and range_check.isChecked())

    def get_param_settings(self):
        """
        項目C-403: パラメータテーブルの内容から、calculate_curve_fit()にそのまま
        渡せる (p0_overrides, fixed_params, bounds) の3つのdictを組み立てる。
        パラメータテーブルが0行(フィットタイプ未確定/カスタム数式が入力途中)
        の場合は3つとも空dictを返す。

        「固定」がチェックされている行は、値欄の値をfixed_paramsに入れ、
        p0_overrides・boundsのどちらにも含めない(「範囲拘束」がチェックされて
        いても無視する — 固定パラメータに範囲の概念はない)。

        Returns:
            tuple(dict[str, float], dict[str, float], dict[str, tuple[float, float]]):
            (p0_overrides, fixed_params, bounds)。何もカスタマイズしなかった
            場合はいずれも空dict(Noneではない)。
        """
        p0_overrides, fixed_params, bounds = {}, {}, {}
        for row in range(self.param_table.rowCount()):
            name = self.param_table.item(row, 0).text()
            value_spin = self.param_table.cellWidget(row, 1)
            fixed_check = self.param_table.cellWidget(row, 2)
            range_check = self.param_table.cellWidget(row, 3)
            min_spin = self.param_table.cellWidget(row, 4)
            max_spin = self.param_table.cellWidget(row, 5)

            if fixed_check.isChecked():
                fixed_params[name] = value_spin.value()
                continue

            if value_spin.property("_user_overridden"):
                p0_overrides[name] = value_spin.value()

            if range_check.isChecked():
                bounds[name] = (min_spin.value(), max_spin.value())

        return p0_overrides, fixed_params, bounds

    def get_band_type(self):
        """
        項目C-405。
        Returns:
            str | None: "confidence" / "prediction" / (「表示しない」選択時は)None。
        """
        text = self.band_combo.currentText()
        if "信頼帯" in text:
            return "confidence"
        if "予測帯" in text:
            return "prediction"
        return None

    def get_weighted(self):
        """Y誤差列を重みとして使うかどうか"""
        return self.weighted_checkbox.isChecked()

    def get_loss(self):
        """
        項目C-407(ロバストフィット)。
        Returns:
            str: 'linear'(既定、通常の最小二乗) / 'soft_l1' / 'huber'。
        """
        return self.loss_combo.currentData()

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
        またはNone, p0_overrides, fixed_params, bounds, band_type, loss) のタプルを、
        Cancelが押された場合は (None, None, False, None, {}, {}, {}, None, 'linear') を
        返します。p0_overrides/fixed_params/boundsは、何もカスタマイズしなかった
        場合も(Noneではなく)空dictになります — calculate_curve_fit()にそのまま
        キーワード引数として渡せる形です。band_type(項目C-405)は
        "confidence"/"prediction"/(表示しない場合)None。loss(項目C-407)は
        'linear'(既定)/'soft_l1'/'huber'。

        Args:
            parent (QWidget, optional): 親ウィジェット。
            x_min (float, optional): フィット範囲指定欄の初期値(最小X)。
            x_max (float, optional): フィット範囲指定欄の初期値(最大X)。

        Returns:
            tuple (str|None, str|None, bool, tuple(float,float)|None,
                   dict[str,float], dict[str,float], dict[str,tuple[float,float]],
                   str|None, str):
            (フィットタイプ名, カスタム数式, 重み付けを使うか, フィット範囲,
             p0_overrides, fixed_params, bounds, band_type, loss)
        """
        dialog = FitDialog(parent, x_min=x_min, x_max=x_max)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            fit_type = dialog.fit_type_combo.currentText()
            custom_formula = dialog.custom_formula_edit.text().strip() if "カスタム数式" in fit_type else None
            p0_overrides, fixed_params, bounds = dialog.get_param_settings()
            return (fit_type, custom_formula, dialog.get_weighted(), dialog.get_x_range(),
                    p0_overrides, fixed_params, bounds, dialog.get_band_type(), dialog.get_loss())
        return None, None, False, None, {}, {}, {}, None, 'linear'




#==============================================================================
# カスタムダイアログクラス (4b): 多峰分離フィット (項目C-409/C-410)
#==============================================================================
class MultiPeakFitDialog(QDialog):
    """
    多峰分離フィット(項目C-409)の設定ダイアログ。成分タイプ(全成分共通)・
    ベースラインタイプに加え、各ピークの初期値(中心/高さ/幅)を行として持つ
    テーブルを編集できる。行は手動追加/削除のほか、「ピーク検出から自動配置...」
    ボタン(項目C-411のcalculate_peak_quantificationを流用)、および
    キャンバス上のクリック配置モード(項目C-410、gui/mixins/peak_placement_mixin.py)
    で集めた初期値(initial_guesses引数)からも事前入力できる。
    """

    COMPONENT_TYPES = [
        ('gaussian', 'ガウシアン'),
        ('lorentzian', 'ローレンツ'),
        ('pseudo_voigt', '擬似フォークト'),
        ('voigt', 'フォークト'),
    ]
    BASELINE_TYPES = [
        ('none', 'なし'),
        ('constant', '定数'),
        ('linear', '1次'),
    ]

    def __init__(self, parent=None, x_data=None, y_data=None, initial_guesses=None):
        """
        Args:
            parent (QWidget, optional): 親ウィジェット。
            x_data, y_data (array-like, optional): 「ピーク検出から自動配置...」用の
                対象データセットの生データ。Noneの場合はそのボタンを無効化する。
            initial_guesses (list[dict], optional): 事前入力する初期値
                ([{'center':, 'height':, 'width':}, ...])。ピーク配置クリック
                モードで集めた点を引き継ぐ想定。
        """
        super().__init__(parent)
        self.setWindowTitle("多峰分離フィット")
        self._x_data = x_data
        self._y_data = y_data

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.component_combo = QComboBox()
        for key, label in self.COMPONENT_TYPES:
            self.component_combo.addItem(label, key)
        form.addRow("成分タイプ(全ピーク共通)", self.component_combo)

        self.baseline_combo = QComboBox()
        for key, label in self.BASELINE_TYPES:
            self.baseline_combo.addItem(label, key)
        self.baseline_combo.setCurrentIndex(1)  # 既定は「定数」
        form.addRow("ベースライン", self.baseline_combo)
        layout.addLayout(form)

        layout.addWidget(QLabel(
            "各ピークの初期値(中心X・高さ・おおよその幅[FWHM]):"
        ))
        self.guess_table = QTableWidget(0, 3)
        self.guess_table.setHorizontalHeaderLabels(["中心 (X)", "高さ", "幅 (FWHM)"])
        self.guess_table.verticalHeader().setVisible(False)
        self.guess_table.setMaximumHeight(200)
        layout.addWidget(self.guess_table)

        row_button_layout = QHBoxLayout()
        add_row_button = QPushButton("行を追加")
        add_row_button.clicked.connect(lambda: self._add_guess_row())
        remove_row_button = QPushButton("選択行を削除")
        remove_row_button.clicked.connect(self._remove_selected_rows)
        self.auto_detect_button = QPushButton("ピーク検出から自動配置...")
        self.auto_detect_button.clicked.connect(self._on_auto_detect)
        self.auto_detect_button.setEnabled(x_data is not None and y_data is not None)
        row_button_layout.addWidget(add_row_button)
        row_button_layout.addWidget(remove_row_button)
        row_button_layout.addWidget(self.auto_detect_button)
        row_button_layout.addStretch()
        layout.addLayout(row_button_layout)

        for guess in (initial_guesses or []):
            self._add_guess_row(
                center=guess.get('center', 0.0),
                height=guess.get('height', 0.0),
                width=guess.get('width', 1.0),
            )

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _add_guess_row(self, center=0.0, height=0.0, width=1.0):
        row = self.guess_table.rowCount()
        self.guess_table.insertRow(row)
        for col, value in enumerate((center, height, width)):
            spin = QDoubleSpinBox()
            spin.setRange(-1e12, 1e12)
            spin.setDecimals(6)
            spin.setValue(float(value))
            self.guess_table.setCellWidget(row, col, spin)

    def _remove_selected_rows(self):
        rows = sorted({idx.row() for idx in self.guess_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.guess_table.removeRow(row)

    def _on_auto_detect(self):
        """
        項目C-411のピーク検出設定ダイアログ(PeakSettingsDialog)を再利用して
        検出条件を尋ね、calculate_peak_quantification()の結果(中心/高さ/FWHM)を
        テーブルへ追加する(既存行は消さずに追加する — クリック配置と併用可能)。
        """
        settings = PeakSettingsDialog.get_peak_settings(self)
        if settings is None:
            return
        from core.analysis import calculate_peak_quantification
        try:
            result = calculate_peak_quantification(
                self._x_data, self._y_data, settings['peak_type'], settings
            )
        except Exception as e:
            QMessageBox.warning(self, "ピーク検出", f"ピーク検出に失敗しました:\n{e}")
            return
        if len(result['peak_x']) == 0:
            QMessageBox.information(self, "ピーク検出", "条件に一致するピークが見つかりませんでした。")
            return
        for x, y, fwhm in zip(result['peak_x'], result['peak_y'], result['fwhm']):
            self._add_guess_row(center=float(x), height=float(y), width=float(fwhm) or 1.0)

    def _on_accept(self):
        if self.guess_table.rowCount() == 0:
            QMessageBox.warning(self, "多峰分離フィット", "少なくとも1つのピークの初期値が必要です。")
            return
        self.accept()

    def get_component_type(self):
        return self.component_combo.currentData()

    def get_baseline_type(self):
        return self.baseline_combo.currentData()

    def get_initial_guesses(self):
        """
        Returns:
            list[dict]: [{'center': float, 'height': float, 'width': float}, ...]
            (calculate_multi_peak_fit()にそのまま渡せる形)。
        """
        guesses = []
        for row in range(self.guess_table.rowCount()):
            center = self.guess_table.cellWidget(row, 0).value()
            height = self.guess_table.cellWidget(row, 1).value()
            width = self.guess_table.cellWidget(row, 2).value()
            guesses.append({'center': center, 'height': height, 'width': width})
        return guesses

    @staticmethod
    def get_multi_peak_fit_settings(parent=None, x_data=None, y_data=None, initial_guesses=None):
        """
        【スタティックメソッド】
        ダイアログをモーダルで表示し、OKが押された場合は
        (component_type, baseline_type, initial_guesses) のタプルを、
        Cancelが押された場合は (None, None, None) を返す。

        Returns:
            tuple(str|None, str|None, list[dict]|None)
        """
        dialog = MultiPeakFitDialog(parent, x_data=x_data, y_data=y_data, initial_guesses=initial_guesses)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_component_type(), dialog.get_baseline_type(), dialog.get_initial_guesses()
        return None, None, None




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
            from gui import theme
            # ★ バグ修正: この残差プロットはgui/canvas.pyのMplCanvasとは別の、
            # 独立したFigureを都度その場で作っているため、canvas.py側の
            # dark_mode分岐(facecolor/文字色/グリッド色)を一切継承しない。
            # ダークモードで開くと、ダイアログ本体は暗いのに残差プロットだけ
            # matplotlib既定の白背景+黒文字のまま浮いて見えていた。
            _tokens = theme.current_tokens()
            fig = Figure(figsize=(4, 2.2), dpi=100, tight_layout=True,
                         facecolor=_tokens['surface'])
            canvas = FigureCanvasQTAgg(fig)
            canvas.setFixedHeight(200)
            ax = fig.add_subplot(111)
            ax.set_facecolor(_tokens['surface'])
            ax.axhline(0, color=_tokens['border_strong'], linewidth=0.8, linestyle='--')
            ax.scatter(residual_x, residual_y, s=14, color='#1F6F78')
            ax.set_xlabel("X", fontsize=8, color=_tokens['text_primary'])
            ax.set_ylabel("残差", fontsize=8, color=_tokens['text_primary'])
            ax.tick_params(labelsize=7, colors=_tokens['text_primary'])
            for spine in ax.spines.values():
                spine.set_color(_tokens['border_strong'])
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




class BaselineCorrectionDialog(QDialog):
    """
    ベースライン補正(項目C-308)の設定を入力させるダイアログ。
    ALS/多項式/ラバーバンド/手動点の4手法をコンボボックスで切り替え、
    QStackedWidgetで手法ごとのパラメータ欄を切り替える(BatchExportDialogの
    モード切り替えと同じ構成)。ラバーバンドはパラメータを持たない。
    """

    METHOD_ALS = "ALS(Asymmetric Least Squares)"
    METHOD_POLYNOMIAL = "多項式(反復フィット)"
    METHOD_RUBBERBAND = "ラバーバンド(下側凸包)"
    METHOD_MANUAL = "手動点"
    METHODS = [METHOD_ALS, METHOD_POLYNOMIAL, METHOD_RUBBERBAND, METHOD_MANUAL]

    _MANUAL_LINEAR = "直線"
    _MANUAL_SPLINE = "3次スプライン"

    def __init__(self, name, x_min=None, x_max=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ベースライン補正")
        self.resize(420, 440)
        self._name = name

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"対象: {name}"))

        method_form = QFormLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItems(self.METHODS)
        method_form.addRow("手法", self.method_combo)
        layout.addLayout(method_form)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # --- ALS ---
        als_page = QWidget()
        als_form = QFormLayout(als_page)
        self.als_lam_spinbox = QDoubleSpinBox()
        self.als_lam_spinbox.setRange(1.0, 1e12)
        self.als_lam_spinbox.setDecimals(0)
        self.als_lam_spinbox.setValue(1e5)
        als_form.addRow("lam(平滑さ)", self.als_lam_spinbox)
        self.als_p_spinbox = QDoubleSpinBox()
        self.als_p_spinbox.setRange(0.0001, 0.9999)
        self.als_p_spinbox.setDecimals(4)
        self.als_p_spinbox.setSingleStep(0.001)
        self.als_p_spinbox.setValue(0.01)
        als_form.addRow("p(非対称重み)", self.als_p_spinbox)
        self.als_niter_spinbox = QSpinBox()
        self.als_niter_spinbox.setRange(1, 1000)
        self.als_niter_spinbox.setValue(10)
        als_form.addRow("反復回数", self.als_niter_spinbox)
        self.stack.addWidget(als_page)

        # --- 多項式 ---
        poly_page = QWidget()
        poly_form = QFormLayout(poly_page)
        self.poly_degree_spinbox = QSpinBox()
        self.poly_degree_spinbox.setRange(0, 10)
        self.poly_degree_spinbox.setValue(3)
        poly_form.addRow("次数", self.poly_degree_spinbox)
        self.poly_iterations_spinbox = QSpinBox()
        self.poly_iterations_spinbox.setRange(1, 1000)
        self.poly_iterations_spinbox.setValue(10)
        poly_form.addRow("反復回数", self.poly_iterations_spinbox)
        self.stack.addWidget(poly_page)

        # --- ラバーバンド(パラメータなし) ---
        rubberband_page = QWidget()
        rubberband_layout = QVBoxLayout(rubberband_page)
        rubberband_info = QLabel(
            "データ点群の下側凸包(convex hull)を結んだ曲線をベースラインとします。"
            "設定できるパラメータはありません。"
        )
        rubberband_info.setWordWrap(True)
        rubberband_layout.addWidget(rubberband_info)
        rubberband_layout.addStretch()
        self.stack.addWidget(rubberband_page)

        # --- 手動点 ---
        manual_page = QWidget()
        manual_layout = QVBoxLayout(manual_page)
        manual_layout.addWidget(QLabel("アンカー点のX座標をカンマ区切りで入力してください(2点以上):"))
        self.manual_anchor_edit = QPlainTextEdit()
        self.manual_anchor_edit.setPlaceholderText("例: 0, 20, 50, 80, 100")
        if x_min is not None and x_max is not None:
            self.manual_anchor_edit.setPlainText(f"{x_min:g}, {x_max:g}")
        self.manual_anchor_edit.setMaximumHeight(60)
        manual_layout.addWidget(self.manual_anchor_edit)
        manual_method_form = QFormLayout()
        self.manual_method_combo = QComboBox()
        self.manual_method_combo.addItems([self._MANUAL_LINEAR, self._MANUAL_SPLINE])
        manual_method_form.addRow("補間方法", self.manual_method_combo)
        manual_layout.addLayout(manual_method_form)
        manual_info = QLabel(
            "各アンカー点のYは、指定したX位置での実データを線形補間して自動的に求めます"
            "(3次スプラインには3点以上必要です)。"
        )
        manual_info.setWordWrap(True)
        manual_layout.addWidget(manual_info)
        manual_layout.addStretch()
        self.stack.addWidget(manual_page)

        self.method_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        form = QFormLayout()
        self.output_name_edit = QLineEdit(f"{name}_baseline_corrected")
        form.addRow("出力データセット名", self.output_name_edit)
        layout.addLayout(form)

        self.add_baseline_checkbox = QCheckBox("推定したベースライン曲線も別データセットとして追加する")
        layout.addWidget(self.add_baseline_checkbox)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        Returns:
            tuple (str, dict, str, bool):
                (手法("als"|"polynomial"|"rubberband"|"manual"),
                 手法別パラメータのdict(calculate_baseline_xxxへそのままkwargsとして
                 渡せる形。"manual"のみ anchor_x ではなく anchor_x_text(未パース
                 の生テキスト)と method("linear"|"spline")を含む。数値パースは
                 呼び出し側(_on_baseline_correction_dataset)が行い、書式エラー
                 を利用者にわかりやすく伝える),
                 出力データセット名,
                 ベースライン曲線も別データセットとして追加するか)
        """
        method_text = self.method_combo.currentText()
        if method_text == self.METHOD_ALS:
            method = "als"
            params = {
                "lam": self.als_lam_spinbox.value(),
                "p": self.als_p_spinbox.value(),
                "niter": self.als_niter_spinbox.value(),
            }
        elif method_text == self.METHOD_POLYNOMIAL:
            method = "polynomial"
            params = {
                "degree": self.poly_degree_spinbox.value(),
                "iterations": self.poly_iterations_spinbox.value(),
            }
        elif method_text == self.METHOD_RUBBERBAND:
            method = "rubberband"
            params = {}
        else:
            method = "manual"
            params = {
                "anchor_x_text": self.manual_anchor_edit.toPlainText(),
                "method": "spline" if self.manual_method_combo.currentText() == self._MANUAL_SPLINE else "linear",
            }
        return method, params, self.output_name_edit.text().strip(), self.add_baseline_checkbox.isChecked()




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




# カスタムダイアログクラス: 区間積分(項目C-311)
class IntervalIntegralDialog(QDialog):
    """
    区間積分(項目C-311)の設定を入力させるダイアログ。

    真のグラフ上ドラッグ選択(項目C-909、未実装)ではなく、FitDialog(項目C-404、
    フィット範囲の指定)と同じ「数値でXの範囲を指定する」UXを踏襲する。
    最小/最大XはQDoubleSpinBoxで、ダイアログを開いた時点で対象データセットの
    実際のX範囲を初期値として埋めておく(そのままOKすればデータセット全体を
    積分できる)。
    """

    METHOD_TRAPEZOID = "台形則(Trapezoidal)"
    METHOD_SIMPSON = "Simpson則"
    METHODS = [METHOD_TRAPEZOID, METHOD_SIMPSON]
    _METHOD_KEY_BY_LABEL = {METHOD_TRAPEZOID: "trapezoid", METHOD_SIMPSON: "simpson"}

    def __init__(self, name, x_min=None, x_max=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("区間積分")
        self.resize(380, 260)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"対象: {name}"))

        form = QFormLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItems(self.METHODS)
        form.addRow("積分方法", self.method_combo)

        self.range_min_spinbox = QDoubleSpinBox()
        self.range_min_spinbox.setRange(-1e12, 1e12)
        self.range_min_spinbox.setDecimals(6)
        if x_min is not None:
            self.range_min_spinbox.setValue(x_min)
        form.addRow("最小X", self.range_min_spinbox)

        self.range_max_spinbox = QDoubleSpinBox()
        self.range_max_spinbox.setRange(-1e12, 1e12)
        self.range_max_spinbox.setDecimals(6)
        if x_max is not None:
            self.range_max_spinbox.setValue(x_max)
        form.addRow("最大X", self.range_max_spinbox)
        layout.addLayout(form)

        self.subtract_baseline_checkbox = QCheckBox(
            "ベースラインを差し引く(範囲の両端を結ぶ直線を差し引いてから積分)"
        )
        self.subtract_baseline_checkbox.setToolTip(
            "積分範囲の両端のY値(実データを線形補間して求めた値)を結ぶ直線を\n"
            "ベースラインとしてYから差し引いてから積分します。\n"
            "スペクトルのピーク面積など「傾いた背景の上のピーク」を求める用途向けの\n"
            "簡易オプションです。ALS等の本格的なベースライン補正を使いたい場合は、\n"
            "先に「ベースライン補正...」で補正したデータセットに対してこの機能を\n"
            "使ってください。"
        )
        layout.addWidget(self.subtract_baseline_checkbox)

        info_label = QLabel(
            "台形則・Simpson則いずれもデータ点数の偶奇による制約はありません。"
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
            tuple (str, tuple(float, float), bool):
                (積分方法("trapezoid"|"simpson"), (最小X, 最大X), ベースラインを差し引くか)
        """
        method_text = self.method_combo.currentText()
        method = self._METHOD_KEY_BY_LABEL[method_text]
        x_range = (self.range_min_spinbox.value(), self.range_max_spinbox.value())
        return method, x_range, self.subtract_baseline_checkbox.isChecked()




class CumulativeIntegralDialog(QDialog):
    """
    累積積分(項目C-303)の設定を入力させるダイアログ。IntervalIntegralDialogと
    積分方法の選択肢は共有するが、こちらは範囲指定・ベースライン差し引きは
    持たず(常にデータ全体を対象に、Xの各点までの積分値を求める)、代わりに
    SavGolDialog等と同じ「出力データセット名」欄を持つ(結果はスカラーではなく
    新しいデータセットとして追加されるため)。
    """

    METHOD_TRAPEZOID = "台形則(Trapezoidal)"
    METHOD_SIMPSON = "Simpson則"
    METHODS = [METHOD_TRAPEZOID, METHOD_SIMPSON]
    _METHOD_KEY_BY_LABEL = {METHOD_TRAPEZOID: "trapezoid", METHOD_SIMPSON: "simpson"}

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("累積積分")
        self.resize(380, 200)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"対象: {name}"))

        form = QFormLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItems(self.METHODS)
        form.addRow("積分方法", self.method_combo)

        self.output_name_edit = QLineEdit(f"{name}_cumsum")
        form.addRow("出力データセット名", self.output_name_edit)
        layout.addLayout(form)

        info_label = QLabel(
            "Xの各点までの積分値 ∫[x_min, x_i] y dx を新しいデータセットとして追加します。\n"
            "範囲を絞りたい場合は「区間積分」を使ってください。"
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
            tuple (str, str): (積分方法("trapezoid"|"simpson"), 出力データセット名)
        """
        method_text = self.method_combo.currentText()
        method = self._METHOD_KEY_BY_LABEL[method_text]
        return method, self.output_name_edit.text().strip()




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




class ResampleDatasetDialog(QDialog):
    """
    共通X格子へのリサンプリング/補間(項目C-305)の設定を入力させるダイアログ。

    対象のグリッド(リサンプリング先のX格子)を「他のデータセットのX格子」または
    「等間隔グリッド」のいずれかから選ばせる。BaselineCorrectionDialogと同じく
    QStackedWidgetで選択肢ごとの入力欄を切り替える。
    「他のデータセットのX格子」はDatasetArithmeticDialogのA/B選択と異なり、
    ここでは対象データセット1件(カレント)に対して"もう1件"を後から選ぶ形に
    なるため、コンボボックスで他データセット名を選ばせる(ロード中のデータセットが
    対象1件のみの場合は選択肢がなく、その場合はこのソースを選べない)。
    """

    SOURCE_DATASET = "他のデータセットのX格子"
    SOURCE_LINSPACE = "等間隔グリッド"
    SOURCES = [SOURCE_DATASET, SOURCE_LINSPACE]

    METHOD_LINEAR = "線形補間"
    METHOD_CUBIC = "3次スプライン補間"
    METHODS = [METHOD_LINEAR, METHOD_CUBIC]
    _METHOD_KEY_BY_LABEL = {METHOD_LINEAR: "linear", METHOD_CUBIC: "cubic"}

    def __init__(self, name, other_dataset_names, x_min=None, x_max=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("共通X格子へのリサンプリング/補間")
        self.resize(420, 380)
        self._name = name

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"対象: {name}"))

        source_form = QFormLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItems(self.SOURCES)
        source_form.addRow("リサンプリング先の格子", self.source_combo)
        layout.addLayout(source_form)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # --- 他のデータセットのX格子 ---
        dataset_page = QWidget()
        dataset_form = QFormLayout(dataset_page)
        self.other_dataset_combo = QComboBox()
        self.other_dataset_combo.addItems(other_dataset_names)
        dataset_form.addRow("データセット", self.other_dataset_combo)
        if not other_dataset_names:
            # 対象になり得る他のデータセットが存在しない(ロード中がこの1件のみ)。
            # コンボが空のままOKされないよう選択肢自体を無効化しておく。
            self.other_dataset_combo.setEnabled(False)
            no_dataset_label = QLabel("(他に読み込まれているデータセットがありません)")
            no_dataset_label.setWordWrap(True)
            dataset_form.addRow(no_dataset_label)
        self.stack.addWidget(dataset_page)

        # --- 等間隔グリッド(numpy.linspace方式: 開始・終了・点数) ---
        linspace_page = QWidget()
        linspace_form = QFormLayout(linspace_page)
        self.linspace_start_spinbox = QDoubleSpinBox()
        self.linspace_start_spinbox.setRange(-1e12, 1e12)
        self.linspace_start_spinbox.setDecimals(6)
        if x_min is not None:
            self.linspace_start_spinbox.setValue(x_min)
        linspace_form.addRow("開始X", self.linspace_start_spinbox)

        self.linspace_stop_spinbox = QDoubleSpinBox()
        self.linspace_stop_spinbox.setRange(-1e12, 1e12)
        self.linspace_stop_spinbox.setDecimals(6)
        if x_max is not None:
            self.linspace_stop_spinbox.setValue(x_max)
        linspace_form.addRow("終了X", self.linspace_stop_spinbox)

        self.linspace_num_points_spinbox = QSpinBox()
        self.linspace_num_points_spinbox.setRange(2, 1_000_000)
        self.linspace_num_points_spinbox.setValue(100)
        linspace_form.addRow("点数", self.linspace_num_points_spinbox)
        self.stack.addWidget(linspace_page)

        self.source_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        if not other_dataset_names:
            # 選べる他データセットがない場合は最初から「等間隔グリッド」を既定にする。
            self.source_combo.setCurrentText(self.SOURCE_LINSPACE)

        method_form = QFormLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItems(self.METHODS)
        method_form.addRow("補間方法", self.method_combo)
        layout.addLayout(method_form)

        self.extrapolate_checkbox = QCheckBox("範囲外を外挿する(既定はNaNにする)")
        self.extrapolate_checkbox.setToolTip(
            "元データのX範囲外にある格子点の扱いです。\n"
            "オフ(既定): 範囲外はNaNになります(安全側)。\n"
            "オン: 線形補間は両端の傾きで、3次スプラインはscipy標準の\n"
            "区間多項式の延長で外挿します(いずれも範囲から離れるほど\n"
            "不正確になりうる点に注意してください)。"
        )
        layout.addWidget(self.extrapolate_checkbox)

        output_form = QFormLayout()
        self.output_name_edit = QLineEdit(f"{name}_resampled")
        output_form.addRow("出力データセット名", self.output_name_edit)
        layout.addLayout(output_form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        Returns:
            tuple (str, dict, str, bool, str):
                (グリッドソース("dataset"|"linspace"),
                 ソース別パラメータのdict。"dataset"なら{"dataset_name": str}、
                 "linspace"なら{"start": float, "stop": float, "num_points": int}、
                 補間方法("linear"|"cubic"),
                 範囲外を外挿するか,
                 出力データセット名)
        """
        source_text = self.source_combo.currentText()
        if source_text == self.SOURCE_DATASET:
            source = "dataset"
            params = {"dataset_name": self.other_dataset_combo.currentText()}
        else:
            source = "linspace"
            params = {
                "start": self.linspace_start_spinbox.value(),
                "stop": self.linspace_stop_spinbox.value(),
                "num_points": self.linspace_num_points_spinbox.value(),
            }
        method_text = self.method_combo.currentText()
        method = self._METHOD_KEY_BY_LABEL[method_text]
        return (
            source, params, method,
            self.extrapolate_checkbox.isChecked(),
            self.output_name_edit.text().strip(),
        )




#==============================================================================
# カスタムダイアログクラス: 統計的外れ値検出(項目C-306)
#==============================================================================
class OutlierDetectionDialog(QDialog):
    """
    Z-score/IQRによる外れ値検出(Y値基準)の設定ダイアログ。

    検出そのものと「検出結果をマスクに適用するか」を分離しており、後者は
    既定でOFFのチェックボックスとしてユーザーに明示的に選ばせる(検出だけ
    行って結果を確認し、必要ならマスクする、という2段階の運用を想定)。
    OK後は必ず検出結果をResultDialogで表示し(_on_detect_outliers参照)、
    チェックボックスがONの場合のみSetMaskedRowsCommandで実際にマスクする。
    """

    METHOD_ZSCORE = "Z-score"
    METHOD_IQR = "IQR(四分位範囲)"
    METHODS = [METHOD_ZSCORE, METHOD_IQR]
    _METHOD_KEY_BY_LABEL = {METHOD_ZSCORE: "zscore", METHOD_IQR: "iqr"}

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("外れ値検出")
        self.resize(420, 280)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"対象: {name}(Y値をもとに検出します)"))

        form = QFormLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItems(self.METHODS)
        form.addRow("検出方法", self.method_combo)
        layout.addLayout(form)

        self.stack = QStackedWidget()

        zscore_page = QWidget()
        zscore_form = QFormLayout(zscore_page)
        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setRange(0.1, 100.0)
        self.threshold_spinbox.setDecimals(2)
        self.threshold_spinbox.setValue(3.0)
        zscore_form.addRow("しきい値(|Z| >)", self.threshold_spinbox)
        self.stack.addWidget(zscore_page)

        iqr_page = QWidget()
        iqr_form = QFormLayout(iqr_page)
        self.multiplier_spinbox = QDoubleSpinBox()
        self.multiplier_spinbox.setRange(0.1, 100.0)
        self.multiplier_spinbox.setDecimals(2)
        self.multiplier_spinbox.setValue(1.5)
        iqr_form.addRow("係数(IQR ×)", self.multiplier_spinbox)
        self.stack.addWidget(iqr_page)

        layout.addWidget(self.stack)
        self.method_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        self.apply_mask_checkbox = QCheckBox("検出した外れ値をマスク(除外)に適用する")
        self.apply_mask_checkbox.setToolTip(
            "チェックを外すと検出結果を表示するだけでマスクは変更しません。\n"
            "マスクは非破壊(項目36と同じ仕組み)で、いつでも解除できます。"
        )
        layout.addWidget(self.apply_mask_checkbox)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def get_settings(self):
        """
        Returns:
            tuple (str, float, bool): (検出方法("zscore"|"iqr"),
                しきい値/係数(検出方法に応じてどちらか一方の意味),
                検出結果をマスクに適用するか)
        """
        method = self._METHOD_KEY_BY_LABEL[self.method_combo.currentText()]
        value = self.threshold_spinbox.value() if method == "zscore" else self.multiplier_spinbox.value()
        return method, value, self.apply_mask_checkbox.isChecked()




#==============================================================================
# カスタムダイアログクラス: ヒストグラム / カーネル密度推定(項目115、C-505)
#==============================================================================
class HistogramKDEDialog(QDialog):
    """
    ヒストグラム(区間集計)またはカーネル密度推定(KDE)を、対象列・モードごとの
    設定で1つの新しいデータセットとして生成するためのダイアログ。
    ResampleDatasetDialog/DuplicateXDialogと同じく、モードごとの入力欄を
    QStackedWidgetで切り替える。対象列はY列に限らず、データセットの任意の
    数値列から選べる(分布を見たいのはY値とは限らないため)。
    """

    MODE_HISTOGRAM = "ヒストグラム"
    MODE_KDE = "カーネル密度推定(KDE)"
    MODES = [MODE_HISTOGRAM, MODE_KDE]

    def __init__(self, name, column_names, default_column=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ヒストグラム / KDE")
        self.resize(420, 320)
        self._name = name

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"対象: {name}"))

        form = QFormLayout()
        self.column_combo = QComboBox()
        self.column_combo.addItems(column_names)
        if default_column and default_column in column_names:
            self.column_combo.setCurrentText(default_column)
        form.addRow("対象列", self.column_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        form.addRow("モード", self.mode_combo)
        layout.addLayout(form)

        self.stack = QStackedWidget()

        hist_page = QWidget()
        hist_form = QFormLayout(hist_page)
        self.auto_bins_checkbox = QCheckBox("ビン数を自動決定")
        self.auto_bins_checkbox.setChecked(True)
        hist_form.addRow(self.auto_bins_checkbox)
        self.bins_spinbox = QSpinBox()
        self.bins_spinbox.setRange(2, 500)
        self.bins_spinbox.setValue(10)
        self.bins_spinbox.setEnabled(False)
        hist_form.addRow("ビン数", self.bins_spinbox)
        self.auto_bins_checkbox.toggled.connect(lambda checked: self.bins_spinbox.setEnabled(not checked))
        self.density_checkbox = QCheckBox("確率密度で正規化する(合計面積 = 1)")
        hist_form.addRow(self.density_checkbox)
        self.stack.addWidget(hist_page)

        kde_page = QWidget()
        kde_form = QFormLayout(kde_page)
        self.kde_points_spinbox = QSpinBox()
        self.kde_points_spinbox.setRange(10, 2000)
        self.kde_points_spinbox.setValue(200)
        kde_form.addRow("評価点数", self.kde_points_spinbox)
        self.stack.addWidget(kde_page)

        layout.addWidget(self.stack)
        self.mode_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        output_form = QFormLayout()
        self.output_name_edit = QLineEdit(f"{name}_hist")
        output_form.addRow("出力データセット名", self.output_name_edit)
        layout.addLayout(output_form)
        self.mode_combo.currentTextChanged.connect(self._update_default_output_name)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def _update_default_output_name(self, mode_text):
        # ユーザーが手で書き換えていそうな場合(既定のどちらの接尾辞パターンとも
        # 一致しない)は上書きしない。
        current = self.output_name_edit.text()
        if current not in (f"{self._name}_hist", f"{self._name}_kde"):
            return
        suffix = "_hist" if mode_text == self.MODE_HISTOGRAM else "_kde"
        self.output_name_edit.setText(f"{self._name}{suffix}")

    def get_settings(self):
        """
        Returns:
            dict: {'mode': "histogram"|"kde", 'column': str, 'output_name': str,
                'bins': int|'auto' (histogramのみ), 'density': bool (histogramのみ),
                'n_points': int (kdeのみ)}
        """
        mode = "histogram" if self.mode_combo.currentText() == self.MODE_HISTOGRAM else "kde"
        settings = {
            'mode': mode,
            'column': self.column_combo.currentText(),
            'output_name': self.output_name_edit.text().strip(),
        }
        if mode == "histogram":
            settings['bins'] = 'auto' if self.auto_bins_checkbox.isChecked() else self.bins_spinbox.value()
            settings['density'] = self.density_checkbox.isChecked()
        else:
            settings['n_points'] = self.kde_points_spinbox.value()
        return settings




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
# カスタムダイアログクラス: X軸アライメント(相互相関、項目105、C-307)
#==============================================================================
class XAxisAlignmentDialog(QDialog):
    """
    相互相関によるX軸アライメント(項目105、C-307)の設定を入力させるダイアログ。
    2つのデータセット(A=基準/移動しない、B=位置合わせ対象/移動する)を対象とし、
    シフト量自体は自動推定(ユーザー入力不要)のため、出力データセット名の
    入力のみを求める最小限の構成(DatasetArithmeticDialogと同じ「A/B表示 +
    出力名」の構成)。
    """

    def __init__(self, name_a, name_b, parent=None):
        super().__init__(parent)
        self.setWindowTitle("X軸アライメント(相互相関)")
        self.resize(380, 200)

        layout = QVBoxLayout(self)
        label = QLabel(f"基準(移動しない): {name_a}\n位置合わせ対象(移動する): {name_b}")
        layout.addWidget(label)

        form = QFormLayout()
        self.output_name_edit = QLineEdit(f"{name_b}_aligned")
        form.addRow("出力データセット名", self.output_name_edit)
        layout.addLayout(form)

        info_label = QLabel(
            "2つのデータセットの相互相関が最大になるよう、位置合わせ対象のX値を"
            "シフトした新しいデータセットを作成します(元のデータセットは変更しません)。"
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
        """Returns: str (出力データセット名)"""
        return self.output_name_edit.text().strip()
