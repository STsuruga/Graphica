"""書き出しのプレビューのドック。設定を変えるたびに全サブプロットの完成形を描き直し、ここから保存とコピーもできる。

一時的な MplCanvas に描くので、画面のキャンバスには触れない。
"""
import io
import os
import logging
import matplotlib as mpl

from PySide6.QtCore import Qt, QTimer, QByteArray, QMimeData
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
                               QLabel, QComboBox, QCheckBox, QDoubleSpinBox, QSpinBox,
                               QPushButton, QApplication)

from graphica.gui import notify
from graphica.gui.canvas import MplCanvas
from graphica.gui.export_settings import export_rc_params
from graphica.gui.theme import apply_form_spacing

logger = logging.getLogger(__name__)

# 矢印の連打などで毎回重い描き直しが走らないよう、まとめるまでの待ち(ms)
PREVIEW_DEBOUNCE_MS = 150


class ExportPreviewPanel(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._current_pixmap = None

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.width_spinbox = QDoubleSpinBox()
        self.width_spinbox.setRange(1, 10000)
        self.width_spinbox.setDecimals(1)
        self.width_spinbox.setValue(800)
        form.addRow("幅", self.width_spinbox)

        self.height_spinbox = QDoubleSpinBox()
        self.height_spinbox.setRange(1, 10000)
        self.height_spinbox.setDecimals(1)
        self.height_spinbox.setValue(600)
        form.addRow("高さ", self.height_spinbox)

        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["ピクセル (px)", "インチ (in)", "センチメートル (cm)"])
        form.addRow("単位", self.unit_combo)

        self.dpi_spinbox = QSpinBox()
        self.dpi_spinbox.setRange(50, 1200)
        self.dpi_spinbox.setValue(150)
        self.dpi_spinbox.setSuffix(" dpi")
        form.addRow("解像度", self.dpi_spinbox)

        self.transparent_checkbox = QCheckBox("背景を透過")
        self.transparent_checkbox.setChecked(True)
        form.addRow(self.transparent_checkbox)

        self.svg_text_as_path_checkbox = QCheckBox("文字をアウトライン化する(SVG)")
        self.svg_text_as_path_checkbox.setToolTip(
            "SVG保存/コピー時、目盛りの数字やラベルの文字をパス(輪郭線)として出力します。"
        )
        form.addRow(self.svg_text_as_path_checkbox)

        # プレビューは応答を優先して常に間引いて描く。このチェックは保存とコピーだけに効く
        self.full_resolution_checkbox = QCheckBox("フル解像度で保存/コピー(間引きなし)")
        self.full_resolution_checkbox.setToolTip(
            "「名前を付けて保存」「コピー」の出力にのみ適用されます(常時更新される"
            "プレビュー自体は応答性のため常に間引いたまま表示します)。点数の多い"
            "Line(折れ線)データセットや2Dマップ(ヒートマップ/等高線)の間引きを"
            "無効化し、常に全データ点/全解像度で保存/コピーします。"
        )
        form.addRow(self.full_resolution_checkbox)

        layout.addLayout(form)
        apply_form_spacing(self)

        self.preview_label = QLabel("プレビューがここに表示されます")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 150)
        self.preview_label.setFrameShape(QLabel.Shape.StyledPanel)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label, 1)

        button_row = QHBoxLayout()
        # SVG はベクター画像を受け付けるアプリ(Illustrator、Inkscape など)に貼れる
        self.copy_format_combo = QComboBox()
        self.copy_format_combo.addItems(["PNG", "SVG"])
        self.copy_format_combo.setToolTip("クリップボードにコピーする形式を選択します")
        button_row.addWidget(self.copy_format_combo)

        self.copy_button = QPushButton("コピー")
        self.copy_button.setToolTip("現在の設定でレンダリングした画像をクリップボードにコピーします")
        self.copy_button.clicked.connect(self._on_copy_clicked)
        button_row.addWidget(self.copy_button)

        self.save_button = QPushButton("名前を付けて保存...")
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.width_spinbox.valueChanged.connect(self.refresh_preview)
        self.height_spinbox.valueChanged.connect(self.refresh_preview)
        self.unit_combo.currentIndexChanged.connect(self.refresh_preview)
        self.dpi_spinbox.valueChanged.connect(self.refresh_preview)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self._render_preview)

    def get_options(self):
        """ExportDialog と同じ形の設定(_calculate_size_in_inches で使える)。"""
        return {
            "width": self.width_spinbox.value(),
            "height": self.height_spinbox.value(),
            "unit": self.unit_combo.currentText(),
            "dpi": self.dpi_spinbox.value(),
            "transparent": self.transparent_checkbox.isChecked(),
            "svg_text_as_path": self.svg_text_as_path_checkbox.isChecked(),
            "full_resolution": self.full_resolution_checkbox.isChecked(),
        }

    def refresh_preview(self):
        """少し待ってまとめて描く。隠れている間は描かない(表示したときに refresh_preview が呼ばれる)。"""
        if not self.isVisible():
            return
        self._refresh_timer.start()

    def _render_preview(self):
        options = self.get_options()
        width_in, height_in = self.main_window._calculate_size_in_inches(options)
        if width_in <= 0 or height_in <= 0:
            return

        pixmap = self._render_full_figure_pixmap(width_in, height_in, options["dpi"])
        self._current_pixmap = pixmap
        if pixmap is None or pixmap.isNull():
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("プレビューを生成できませんでした\n(データセットがないか、設定を確認してください)")
            return
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            pixmap.scaled(self.preview_label.size(),
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            self.preview_label.setPixmap(
                self._current_pixmap.scaled(self.preview_label.size(),
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            )

    def _make_temp_canvas_for_full_figure(self, width_in, height_in, dpi, full_resolution=False):
        """全サブプロットを描いた一時的な MplCanvas。描けるものが無ければ None。

        full_resolution=True は間引かない。常に描き直すプレビューでは False、保存とコピーでだけ設定の値を渡す。
        """
        mw = self.main_window
        layout_mode = getattr(mw.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            rows, cols = 0, 0
            if not mw.project.all_plot_settings:
                return None
        else:
            rows = mw.subplot_rows_spinbox.value()
            cols = mw.subplot_cols_spinbox.value()
            if rows * cols == 0:
                return None

        temp_canvas = MplCanvas(width=width_in, height=height_in, dpi=dpi)
        temp_canvas.dark_mode = mw.canvas.dark_mode
        temp_canvas.redraw_all(
            mw.project.datasets, rows, cols, mw.project.all_plot_settings, layout_mode=layout_mode,
            panel_labels_enabled=mw.project.panel_labels_enabled,
            full_resolution=full_resolution,
        )
        return temp_canvas

    def _render_full_figure_pixmap(self, width_in, height_in, dpi):
        """画面のプレビュー用。常に不透明で描く(透過は保存とコピーのときだけ選べる)。"""
        try:
            temp_canvas = self._make_temp_canvas_for_full_figure(width_in, height_in, dpi)
            if temp_canvas is None:
                return None
            try:
                buf = io.BytesIO()
                temp_canvas.fig.savefig(
                    buf, format='png', dpi=dpi, bbox_inches='tight',
                    facecolor=temp_canvas.fig.get_facecolor()
                )
                buf.seek(0)
                pixmap = QPixmap()
                pixmap.loadFromData(buf.read())
                buf.close()
                return pixmap
            finally:
                temp_canvas.deleteLater()
        except Exception:
            logger.exception("エクスポートプレビューの生成に失敗しました。")
            return None

    def _render_full_figure_bytes(self, width_in, height_in, dpi, fmt, transparent, svg_text_as_path=False,
                                   full_resolution=False):
        """'png' か 'svg' で書いたバイト列(保存とコピーで共有)。"""
        try:
            temp_canvas = self._make_temp_canvas_for_full_figure(width_in, height_in, dpi, full_resolution=full_resolution)
            if temp_canvas is None:
                return None
            try:
                buf = io.BytesIO()
                save_kwargs = {'format': fmt, 'bbox_inches': 'tight', 'transparent': transparent}
                if fmt != 'svg':
                    save_kwargs['dpi'] = dpi
                with mpl.rc_context(export_rc_params(fmt, svg_text_as_path)):
                    temp_canvas.fig.savefig(buf, **save_kwargs)
                buf.seek(0)
                data = buf.read()
                buf.close()
                return data
            finally:
                temp_canvas.deleteLater()
        except Exception:
            logger.exception("エクスポートプレビューのレンダリングに失敗しました(形式: %s)。", fmt)
            return None

    def _on_copy_clicked(self):
        options = self.get_options()
        width_in, height_in = self.main_window._calculate_size_in_inches(options)
        if width_in <= 0 or height_in <= 0:
            notify.warning(self, "コピーエラー", "コピーする画像がありません。")
            return

        if self.copy_format_combo.currentText() == "SVG":
            svg_bytes = self._render_full_figure_bytes(
                width_in, height_in, options["dpi"], fmt='svg', transparent=options["transparent"],
                svg_text_as_path=options["svg_text_as_path"], full_resolution=options["full_resolution"]
            )
            if svg_bytes is None:
                notify.warning(self, "コピーエラー", "コピーする画像がありません。")
                return
            mime_data = QMimeData()
            mime_data.setData("image/svg+xml", QByteArray(svg_bytes))
            # SVG だけでは Word や PowerPoint が貼り付けられないので、PNG も同じ QMimeData に載せる。
            # その PNG は透過にしない(macOS のクリップボードはアルファを引き継がず、貼ると真っ黒になる)
            png_fallback_bytes = self._render_full_figure_bytes(
                width_in, height_in, options["dpi"], fmt='png', transparent=False,
                full_resolution=options["full_resolution"]
            )
            if png_fallback_bytes is not None:
                fallback_pixmap = QPixmap()
                fallback_pixmap.loadFromData(png_fallback_bytes)
                if not fallback_pixmap.isNull():
                    mime_data.setImageData(fallback_pixmap.toImage())
            QApplication.clipboard().setMimeData(mime_data)
            self.main_window.statusBar().showMessage("プレビュー画像をSVG形式でクリップボードにコピーしました", 3000)
        else:
            # 上と同じ理由で透過にしない
            png_bytes = self._render_full_figure_bytes(
                width_in, height_in, options["dpi"], fmt='png', transparent=False,
                full_resolution=options["full_resolution"]
            )
            if png_bytes is None:
                notify.warning(self, "コピーエラー", "コピーする画像がありません。")
                return
            pixmap = QPixmap()
            pixmap.loadFromData(png_bytes)
            QApplication.clipboard().setPixmap(pixmap)
            self.main_window.statusBar().showMessage("プレビュー画像をクリップボードにコピーしました", 3000)

    def _on_save_clicked(self):
        options = self.get_options()
        width_in, height_in = self.main_window._calculate_size_in_inches(options)

        layout_mode = getattr(self.main_window.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            if not self.main_window.project.all_plot_settings:
                notify.warning(self, "保存エラー", "有効なプロットがありません。")
                return
        else:
            rows = self.main_window.subplot_rows_spinbox.value()
            cols = self.main_window.subplot_cols_spinbox.value()
            if rows * cols == 0:
                notify.warning(self, "保存エラー", "有効なプロットがありません。")
                return

        file_path, _ = notify.get_save_file_name(
            self, "プロットを保存", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)"
        )
        if not file_path:
            return

        file_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        temp_canvas = self._make_temp_canvas_for_full_figure(
            width_in, height_in, options["dpi"], full_resolution=options["full_resolution"]
        )
        if temp_canvas is None:
            notify.warning(self, "保存エラー", "有効なプロットがありません。")
            return
        try:
            save_kwargs = {'transparent': options["transparent"], 'bbox_inches': 'tight'}
            if file_ext not in ('pdf', 'svg'):
                save_kwargs['dpi'] = options["dpi"]
            with mpl.rc_context(export_rc_params(file_ext, options.get("svg_text_as_path", False))):
                temp_canvas.fig.savefig(file_path, **save_kwargs)
            self.main_window.statusBar().showMessage(f"保存しました: {file_path}", 3000)
        except Exception as e:
            logger.exception("エクスポートプレビューパネルからの保存に失敗しました。")
            notify.warning(self, "保存エラー", f"エクスポート中にエラーが発生しました:\n{e}")
        finally:
            temp_canvas.deleteLater()
