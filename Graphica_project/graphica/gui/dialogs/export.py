"""書き出しと出力のダイアログ。呼び出し側は `from graphica.gui.dialogs import X` で参照する。"""

import os
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
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from graphica.gui.theme import apply_form_spacing
from graphica.core.cvd_simulation import CVD_TYPE_LABELS
from graphica.gui.cvd_preview import simulate_qimage


class ExportDialog(QDialog):
    """書き出しの大きさ・単位・解像度。プレビューを作るのは呼び出し側(PlotterApp._generate_preview)。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("プロットのエクスポート")


        # 学術誌の段組の幅(単段 85mm / 1.5段 114mm / 2段 170mm)。高さは図ごとに違うので決めない
        self.JOURNAL_PRESET_CUSTOM = "カスタム"
        self.JOURNAL_PRESETS = {
            "学術誌 単段 (85mm)": 85.0,
            "学術誌 1.5段 (114mm)": 114.0,
            "学術誌 2段 (170mm)": 170.0,
        }
        self.journal_preset_combo = QComboBox()
        self.journal_preset_combo.addItem(self.JOURNAL_PRESET_CUSTOM)
        self.journal_preset_combo.addItems(self.JOURNAL_PRESETS.keys())
        self.journal_preset_combo.currentTextChanged.connect(self._on_journal_preset_changed)

        self.width_spinbox = QDoubleSpinBox()
        self.width_spinbox.setRange(1, 10000)
        self.width_spinbox.setValue(800)
        self.width_spinbox.setDecimals(1)     # インチ指定のため小数を許す

        self.height_spinbox = QDoubleSpinBox()
        self.height_spinbox.setRange(1, 10000)
        self.height_spinbox.setValue(600)
        self.height_spinbox.setDecimals(1)

        # 学術誌のプリセットを選ぶとミリメートルに切り替わる
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["ピクセル (px)", "インチ (in)", "センチメートル (cm)", "ミリメートル (mm)"])

        self.dpi_spinbox = QSpinBox()
        self.dpi_spinbox.setRange(50, 1200)
        self.dpi_spinbox.setValue(300)
        self.dpi_spinbox.setSuffix(" dpi")

        self.transparent_checkbox = QCheckBox("背景を透過")
        self.transparent_checkbox.setChecked(True)

        # 既定は文字のまま(検索や編集ができる)。フォントの無い環境で化けるのを避けたいときだけパスにする。SVG だけに効く
        self.svg_text_as_path_checkbox = QCheckBox("文字をアウトライン化する(SVG)")
        self.svg_text_as_path_checkbox.setToolTip(
            "SVG出力時、目盛りの数字やラベルの文字をテキスト要素ではなく"
            "パス(輪郭線)として出力します。フォントが無い環境でも見た目が"
            "崩れませんが、テキストとしての検索・編集はできなくなります。"
        )

        # 表示用の間引き(線は 20,000 点超、2D マップは1軸 500 点超)をしない
        self.full_resolution_checkbox = QCheckBox("フル解像度でエクスポート(間引きなし)")
        self.full_resolution_checkbox.setToolTip(
            "通常、点数の多いLine(折れ線)データセットや2Dマップ(ヒートマップ/"
            "等高線)は画面表示同様に間引いて描画されます。このチェックを入れると"
            "間引きを無効化し、常に全データ点/全解像度でエクスポートします"
            "(処理が遅くなる場合があります)。Scatter/Line+Scatterのマーカーは"
            "この設定に関わらず常に全点描画されます。"
        )

        self.preview_button = QPushButton("プレビュー更新")
        self.preview_button.setToolTip("現在の設定でプレビュー画像を生成します。")
        
        self.preview_label = QLabel("プレビューがここに表示されます")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedSize(400, 300)
        self.preview_label.setFrameShape(QLabel.Shape.StyledPanel)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | 
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)


        form_layout = QFormLayout()
        form_layout.addRow("サイズプリセット", self.journal_preset_combo)
        form_layout.addRow("幅", self.width_spinbox)
        form_layout.addRow("高さ", self.height_spinbox)
        form_layout.addRow("単位", self.unit_combo)
        form_layout.addRow("解像度", self.dpi_spinbox)
        form_layout.addRow(self.transparent_checkbox)
        form_layout.addRow(self.svg_text_as_path_checkbox)
        form_layout.addRow(self.full_resolution_checkbox)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.preview_button)
        main_layout.addWidget(self.preview_label)
        main_layout.addWidget(button_box)
        
        self.setLayout(main_layout)

        apply_form_spacing(self)

    def _on_journal_preset_changed(self, preset_name):
        """「カスタム」なら入力した値をそのまま残す。"""
        if preset_name == self.JOURNAL_PRESET_CUSTOM:
            return
        self.unit_combo.setCurrentText("ミリメートル (mm)")
        self.width_spinbox.setValue(self.JOURNAL_PRESETS[preset_name])

    def get_options(self):
        return {
            "width": self.width_spinbox.value(),
            "height": self.height_spinbox.value(),
            "unit": self.unit_combo.currentText(),
            "dpi": self.dpi_spinbox.value(),
            "transparent": self.transparent_checkbox.isChecked(),
            "svg_text_as_path": self.svg_text_as_path_checkbox.isChecked(),
            "full_resolution": self.full_resolution_checkbox.isChecked(),
        }


class BatchExportDialog(QDialog):
    """サブプロットごと、または複数のプロジェクトファイルをまとめて書き出す設定。書き出しは呼び出し側。"""

    def __init__(self, subplot_count, parent=None, extra_formats=None):
        """extra_formats はプラグインの書き出し形式の名前(PNG / PDF / SVG に足す)。"""
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

        self.svg_text_as_path_checkbox = QCheckBox("文字をアウトライン化する(SVG)")
        self.svg_text_as_path_checkbox.setToolTip(
            "SVG出力時、目盛りの数字やラベルの文字をパス(輪郭線)として出力します。"
            "PNG/PDF形式には影響しません。"
        )
        form.addRow(self.svg_text_as_path_checkbox)

        self.full_resolution_checkbox = QCheckBox("フル解像度でエクスポート(間引きなし)")
        self.full_resolution_checkbox.setToolTip(
            "通常、点数の多いLine(折れ線)データセットや2Dマップ(ヒートマップ/"
            "等高線)は画面表示同様に間引いて描画されます。このチェックを入れると"
            "間引きを無効化し、常に全データ点/全解像度でエクスポートします"
            "(処理が遅くなる場合があります)。Scatter/Line+Scatterのマーカーは"
            "この設定に関わらず常に全点描画されます。"
        )
        form.addRow(self.full_resolution_checkbox)

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
        """'subplots' か 'project_files'。"""
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
            'full_resolution': self.full_resolution_checkbox.isChecked(),
        }


class CaptionGeneratorDialog(QDialog):
    """論文用の LaTeX の \\includegraphics 一式と Word 用のキャプションを作ってコピーする。画像ファイル名は自由入力。"""

    WIDTH_OPTIONS = [r'\linewidth', r'0.8\linewidth', r'0.5\linewidth', r'\textwidth']

    def __init__(self, default_caption="", default_label="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("LaTeX/Word用キャプションを生成")
        self.resize(480, 420)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.caption_edit = QLineEdit(default_caption)
        form.addRow("キャプション", self.caption_edit)

        image_layout = QHBoxLayout()
        self.image_name_edit = QLineEdit()
        self.image_name_edit.setPlaceholderText("例: figure1.pdf(空欄可、後から書き換えてください)")
        browse_button = QPushButton("参照...")
        browse_button.clicked.connect(self._on_browse_image)
        image_layout.addWidget(self.image_name_edit, 1)
        image_layout.addWidget(browse_button)
        form.addRow("画像ファイル名", image_layout)

        self.label_edit = QLineEdit(default_label)
        form.addRow("LaTeXラベル", self.label_edit)

        self.width_combo = QComboBox()
        self.width_combo.addItems(self.WIDTH_OPTIONS)
        form.addRow("幅(\\includegraphics)", self.width_combo)
        layout.addLayout(form)

        layout.addWidget(QLabel("LaTeXプレビュー"))
        self.latex_preview = QPlainTextEdit()
        self.latex_preview.setReadOnly(True)
        self.latex_preview.setFont(QFont("Consolas", 9))
        layout.addWidget(self.latex_preview, 1)

        button_layout = QHBoxLayout()
        copy_latex_button = QPushButton("LaTeXをコピー")
        copy_latex_button.clicked.connect(self._on_copy_latex)
        copy_caption_button = QPushButton("キャプション文をコピー(Word用)")
        copy_caption_button.clicked.connect(self._on_copy_caption)
        button_layout.addWidget(copy_latex_button)
        button_layout.addWidget(copy_caption_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        close_button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button_box.rejected.connect(self.reject)
        close_button_box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(close_button_box)

        for widget in (self.caption_edit, self.image_name_edit, self.label_edit):
            widget.textChanged.connect(self._update_preview)
        self.width_combo.currentTextChanged.connect(self._update_preview)
        self._update_preview()

        apply_form_spacing(self)

    def _on_browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "画像ファイルを選択", "", "画像ファイル (*.pdf *.svg *.png *.eps)"
        )
        if file_path:
            self.image_name_edit.setText(os.path.basename(file_path))

    def _update_preview(self):
        from graphica.core.caption_export import generate_latex_figure
        latex_code = generate_latex_figure(
            self.image_name_edit.text().strip(), self.caption_edit.text(),
            self.label_edit.text().strip(), self.width_combo.currentText(),
        )
        self.latex_preview.setPlainText(latex_code)

    def _on_copy_latex(self):
        QApplication.clipboard().setText(self.latex_preview.toPlainText())

    def _on_copy_caption(self):
        QApplication.clipboard().setText(self.caption_edit.text())


class CVDSimulationDialog(QDialog):
    """色覚シミュレーションのプレビュー。呼び出し側が1回撮った画像を、モードごとに変換して見せる(グラフは描き直さない)。"""

    MODE_NORMAL = "通常(変換なし)"

    def __init__(self, source_image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("色覚シミュレーションプレビュー")
        self.resize(700, 560)
        self._source_image = source_image

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.MODE_NORMAL, None)
        for key, label in CVD_TYPE_LABELS.items():
            self.mode_combo.addItem(label, key)
        self.mode_combo.currentIndexChanged.connect(self._update_preview)
        form.addRow("表示モード", self.mode_combo)
        layout.addLayout(form)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setFrameShape(QLabel.Shape.StyledPanel)
        layout.addWidget(self.preview_label, 1)

        info_label = QLabel(
            "sRGB値への直接変換による簡易的な近似シミュレーションです。"
            "実際の見え方を完全に再現するものではありません。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(button_box)

        self._update_preview()

    def _update_preview(self):
        cvd_type = self.mode_combo.currentData()
        image = self._source_image if cvd_type is None else simulate_qimage(self._source_image, cvd_type)
        pixmap = QPixmap.fromImage(image)
        target_width = max(self.preview_label.width(), 400)
        target_height = max(self.preview_label.height(), 300)
        scaled = pixmap.scaled(
            target_width, target_height,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
