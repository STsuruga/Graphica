# gui/dialogs/export.py
"""
エクスポート・出力のダイアログ。

gui/dialogs.py(5,560行・47ダイアログ)を機能群ごとに分割したもの
(改善ボード B-2)。呼び出し側は従来どおり `from gui.dialogs import X` で
参照できる(gui/dialogs/__init__.py が再エクスポートしている)。
"""

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

        # 図面サイズプリセット(項目139、C-802): 学術誌でよく使われる段組幅
        # (単段85mm/1.5段114mm/2段170mm)を選ぶと、幅を自動的にミリメートル
        # 単位で埋める(高さはアスペクト比が図ごとに異なるため自動設定しない、
        # ユーザーが別途指定する)。
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

        # 単位 (Unit)。ミリメートル(項目139、C-802)は上記の学術誌プリセット選択時に
        # 自動的に切り替わる(mm指定は学術誌の投稿規定でよく使われる単位のため)。
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["ピクセル (px)", "インチ (in)", "センチメートル (cm)", "ミリメートル (mm)"])

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

        # フル解像度エクスポート: 表示用ダウンサンプリング(LTTB、項目C-1001)は
        # Line(連続曲線)が20,000点を超えた場合のみ画面表示を軽量化するが、
        # 出版・印刷用など間引き無しのデータが必要な場合はこれを有効にする。
        # 2Dマップ(ヒートマップ/等高線)のグリッド間引き(1軸500点超で発動)も
        # 同じチェックボックスで無効化される。
        self.full_resolution_checkbox = QCheckBox("フル解像度でエクスポート(間引きなし)")
        self.full_resolution_checkbox.setToolTip(
            "通常、点数の多いLine(折れ線)データセットや2Dマップ(ヒートマップ/"
            "等高線)は画面表示同様に間引いて描画されます。このチェックを入れると"
            "間引きを無効化し、常に全データ点/全解像度でエクスポートします"
            "(処理が遅くなる場合があります)。Scatter/Line+Scatterのマーカーは"
            "この設定に関わらず常に全点描画されます。"
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
        form_layout.addRow("サイズプリセット", self.journal_preset_combo)
        form_layout.addRow("幅", self.width_spinbox)
        form_layout.addRow("高さ", self.height_spinbox)
        form_layout.addRow("単位", self.unit_combo)
        form_layout.addRow("解像度", self.dpi_spinbox)
        form_layout.addRow(self.transparent_checkbox)
        form_layout.addRow(self.svg_text_as_path_checkbox)
        form_layout.addRow(self.full_resolution_checkbox)

        # 2. 全体をまとめる垂直レイアウト
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)      # フォームレイアウトを追加
        main_layout.addWidget(self.preview_button) # プレビューボタンを追加
        main_layout.addWidget(self.preview_label)  # プレビュー表示エリアを追加
        main_layout.addWidget(button_box)       # 保存/Cancelボタンを追加
        
        self.setLayout(main_layout)

        apply_form_spacing(self)

    def _on_journal_preset_changed(self, preset_name):
        """
        図面サイズプリセット(項目139、C-802)が選ばれたときの処理。
        「カスタム」ではユーザーが自由に入力した値をそのまま残す(何もしない)。
        """
        if preset_name == self.JOURNAL_PRESET_CUSTOM:
            return
        self.unit_combo.setCurrentText("ミリメートル (mm)")
        self.width_spinbox.setValue(self.JOURNAL_PRESETS[preset_name])

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
            "full_resolution": self.full_resolution_checkbox.isChecked(),
        }




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

        # フル解像度エクスポート: ExportDialogと同じオプション
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
            'full_resolution': self.full_resolution_checkbox.isChecked(),
        }




#==============================================================================
# カスタムダイアログクラス: LaTeX/Word用キャプション自動生成(項目142、C-807)
#==============================================================================
class CaptionGeneratorDialog(QDialog):
    """
    グラフを論文に貼り込む際の定型作業(LaTeXの\\includegraphics一式、
    Word用のキャプション文)を自動生成し、クリップボードにコピーできるように
    するダイアログ。入力欄を変更するたびにLaTeXプレビューをライブ更新する。
    実際のファイル書き出しは行わない(画像ファイル名は自由入力のプレースホルダ
    として扱う、既にエクスポート済みの画像に後から差し替える運用を想定)。
    """

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




#==============================================================================
# カスタムダイアログクラス: 色覚シミュレーションプレビュー(項目140、C-803)
#==============================================================================
class CVDSimulationDialog(QDialog):
    """
    現在のグラフのスナップショット画像に、色覚多様性(色覚異常)のシミュレーション
    変換(core/cvd_simulation.py)を適用して表示するプレビューダイアログ。
    元画像は呼び出し側(gui/mixins/export_mixin.pyの_on_show_cvd_simulation)が
    1回だけキャプチャして渡し、ここではモード切替のたびにそのコピーへ変換を
    適用するだけで、実際のグラフの再描画は一切行わない。
    """

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
