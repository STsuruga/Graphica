# gui/export_preview_panel.py
"""
「常時表示のエクスポートプレビュー」ドックパネル。

これまでの「名前を付けてエクスポート」ダイアログ (ExportDialog) は、開くたびに
手動で「プレビュー更新」ボタンを押す必要があり、かつプレビューは「現在アクティブな
1つのサブプロット」のみが対象だった。

このパネルはドックとして常設し、幅・高さ・単位・DPIを変更するたびに自動で
プレビューを再生成する。プレビューは全サブプロットをまとめた完成形を表示する。
実際の保存/クリップボードコピーも、この設定のままここから直接行える。

一時的な MplCanvas を新しく作って描画することで、画面表示用の本体キャンバス
(main_window.canvas) には一切手を加えずに済んでいる。
"""
import io
import os
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
                               QLabel, QComboBox, QDoubleSpinBox, QSpinBox,
                               QPushButton, QFileDialog, QMessageBox, QApplication)

from gui.canvas import MplCanvas

logger = logging.getLogger(__name__)

# プレビュー更新をまとめるための遅延(ms)。スピンボックスの矢印連打などで
# 毎回すぐに重い再描画が走らないようにする。
PREVIEW_DEBOUNCE_MS = 150


class ExportPreviewPanel(QWidget):
    """エクスポート設定 + 常時プレビュー + 保存/コピーをまとめたドック用ウィジェット"""

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
        form.addRow("幅:", self.width_spinbox)

        self.height_spinbox = QDoubleSpinBox()
        self.height_spinbox.setRange(1, 10000)
        self.height_spinbox.setDecimals(1)
        self.height_spinbox.setValue(600)
        form.addRow("高さ:", self.height_spinbox)

        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["ピクセル (px)", "インチ (in)", "センチメートル (cm)"])
        form.addRow("単位:", self.unit_combo)

        self.dpi_spinbox = QSpinBox()
        self.dpi_spinbox.setRange(50, 1200)
        self.dpi_spinbox.setValue(150)
        self.dpi_spinbox.setSuffix(" dpi")
        form.addRow("解像度:", self.dpi_spinbox)
        layout.addLayout(form)

        self.preview_label = QLabel("プレビューがここに表示されます")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 150)
        self.preview_label.setFrameShape(QLabel.Shape.StyledPanel)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label, 1)

        button_row = QHBoxLayout()
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
        """ExportDialogと同じ形式の設定辞書を返す(main_window._calculate_size_in_inchesと互換)"""
        return {
            "width": self.width_spinbox.value(),
            "height": self.height_spinbox.value(),
            "unit": self.unit_combo.currentText(),
            "dpi": self.dpi_spinbox.value(),
        }

    def refresh_preview(self):
        """
        プレビューの再生成をリクエストする(実際の描画は少し遅延させてまとめて行う)。
        パネルが非表示のときは無駄な描画を避けるため何もしない
        (再表示された際に別途 refresh_preview が呼ばれる)。
        """
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
        # ドックの大きさが変わったら、既存のプレビュー画像をラベルサイズに合わせて再スケールする
        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            self.preview_label.setPixmap(
                self._current_pixmap.scaled(self.preview_label.size(),
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            )

    def _render_full_figure_pixmap(self, width_in, height_in, dpi):
        """
        現在の全プロット(全サブプロット)を、指定したサイズ・DPIで新規にレンダリングし、
        QPixmapとして返す。一時的な MplCanvas を使うため、画面表示用の本体キャンバス
        (main_window.canvas) には一切影響を与えない。
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
        try:
            temp_canvas.redraw_all(mw.project.datasets, rows, cols, mw.project.all_plot_settings, layout_mode=layout_mode)
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
        except Exception:
            logger.exception("エクスポートプレビューの生成に失敗しました。")
            return None
        finally:
            temp_canvas.deleteLater()

    def _on_copy_clicked(self):
        if self._current_pixmap is None or self._current_pixmap.isNull():
            self._render_preview()
        if self._current_pixmap is None or self._current_pixmap.isNull():
            QMessageBox.warning(self, "コピーエラー", "コピーする画像がありません。")
            return
        QApplication.clipboard().setPixmap(self._current_pixmap)
        self.main_window.statusBar().showMessage("プレビュー画像をクリップボードにコピーしました", 3000)

    def _on_save_clicked(self):
        options = self.get_options()
        width_in, height_in = self.main_window._calculate_size_in_inches(options)

        layout_mode = getattr(self.main_window.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            rows, cols = 0, 0
            if not self.main_window.project.all_plot_settings:
                QMessageBox.warning(self, "保存エラー", "有効なプロットがありません。")
                return
        else:
            rows = self.main_window.subplot_rows_spinbox.value()
            cols = self.main_window.subplot_cols_spinbox.value()
            if rows * cols == 0:
                QMessageBox.warning(self, "保存エラー", "有効なプロットがありません。")
                return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "プロットを保存", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)"
        )
        if not file_path:
            return

        temp_canvas = MplCanvas(width=width_in, height=height_in, dpi=options["dpi"])
        temp_canvas.dark_mode = self.main_window.canvas.dark_mode
        try:
            temp_canvas.redraw_all(
                self.main_window.project.datasets, rows, cols, self.main_window.project.all_plot_settings,
                layout_mode=layout_mode
            )
            file_ext = os.path.splitext(file_path)[1].lower()
            save_kwargs = {'transparent': True, 'bbox_inches': 'tight'}
            if file_ext not in ('.pdf', '.svg'):
                save_kwargs['dpi'] = options["dpi"]
            temp_canvas.fig.savefig(file_path, **save_kwargs)
            self.main_window.statusBar().showMessage(f"保存しました: {file_path}", 3000)
        except Exception as e:
            logger.exception("エクスポートプレビューパネルからの保存に失敗しました。")
            QMessageBox.warning(self, "保存エラー", f"エクスポート中にエラーが発生しました:\n{e}")
        finally:
            temp_canvas.deleteLater()
