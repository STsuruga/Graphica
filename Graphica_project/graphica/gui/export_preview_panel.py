"""書き出しのプレビューのドック。設定を変えるたびに全サブプロットの完成形を描き直し、ここから保存とコピーもできる。

一時的な MplCanvas に描くので、画面のキャンバスには触れない。
"""
import copy
import io
import os
import logging
import matplotlib as mpl

from PySide6.QtCore import Qt, QTimer, QByteArray, QMimeData
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
                               QLabel, QComboBox, QCheckBox, QDoubleSpinBox, QSpinBox,
                               QPushButton, QApplication)

from graphica.core.i18n import tr
from graphica.gui import notify
from graphica.gui import dialog_dirs
from graphica.gui.canvas import MplCanvas
from graphica.core.plugin_api import get_plugin_api, get_registered_exporters
from graphica.core.plugin_types import PluginExecutionError
from graphica.gui.export_settings import export_rc_params, project_has_raster_gradient_fill
from graphica.gui.export_size import ExportSizeFields, confirm_output_size, preview_dpi, preview_too_large_text
from graphica.gui.theme import apply_form_spacing
from graphica.gui.widgets import ComboMirror, SegmentedControl

logger = logging.getLogger(__name__)

# 矢印の連打などで毎回重い描き直しが走らないよう、まとめるまでの待ち(ms)
PREVIEW_DEBOUNCE_MS = 150

# 学術誌の段組の幅(mm)。高さは図ごとに違うので決めない
SIZE_PRESET_CUSTOM = "カスタム"
JOURNAL_COLUMN_WIDTHS_MM = (
    ("学術誌 単段 (85mm)", 85.0),
    ("学術誌 1.5段 (114mm)", 114.0),
    ("学術誌 2段 (170mm)", 170.0),
)
# 値は日本語の元の文字(書き出しの処理がそれで単位を見分ける)、見せるのは短い記号
EXPORT_UNITS = (
    ("ピクセル (px)", "px"), ("インチ (in)", "in"), ("センチメートル (cm)", "cm"), ("ミリメートル (mm)", "mm"),
)
MILLIMETRE_UNIT = "ミリメートル (mm)"


def _with_hidden_owner(view, owner):
    """見た目の部品と、隠した値の持ち主(コンボ)を1つの欄にまとめる。"""
    field = QWidget()
    layout = QHBoxLayout(field)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(view, 1)
    owner.setParent(field)
    owner.hide()
    return field


class ExportPreviewPanel(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._current_pixmap = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)

        form = QFormLayout()
        self.size_preset_combo = QComboBox()
        self.size_preset_combo.addItem(tr(SIZE_PRESET_CUSTOM), None)
        for label, width_mm in JOURNAL_COLUMN_WIDTHS_MM:
            self.size_preset_combo.addItem(tr(label), width_mm)
        self.size_preset_combo.setToolTip(tr("学術誌の段の幅に合わせる(単位はミリメートルになる)"))
        form.addRow(tr("段幅"), self.size_preset_combo)

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
        for unit, _short in EXPORT_UNITS:
            self.unit_combo.addItem(tr(unit), unit)
        # 単位は選択肢が少ないのでセグメントで見せる(値の持ち主はコンボのまま)
        self.unit_segments = SegmentedControl()
        for unit, short in EXPORT_UNITS:
            self.unit_segments.addItem(short, unit, tr(unit))
        form.addRow("単位", _with_hidden_owner(self.unit_segments, self.unit_combo))

        self.dpi_spinbox = QSpinBox()
        self.dpi_spinbox.setRange(50, 1200)
        self.dpi_spinbox.setValue(150)
        self.dpi_spinbox.setSuffix(" dpi")
        form.addRow("解像度", self.dpi_spinbox)

        self.output_size_label = QLabel()
        form.addRow(self.output_size_label)
        # 単位のコンボの描き直しより先に換算が済むよう、ほかの通知をつなぐ前に作る
        self._size_fields = ExportSizeFields(
            self.width_spinbox, self.height_spinbox, self.unit_combo, self.dpi_spinbox, self.output_size_label)

        self.transparent_checkbox = QCheckBox("背景を透過")
        self.transparent_checkbox.setChecked(True)
        form.addRow(self.transparent_checkbox)

        # ダークのまま書き出すと、透過した白い紙に明るい文字と目盛が乗って読めない図になる
        self.light_colors_checkbox = QCheckBox(tr("ライト配色で書き出す"))
        self.light_colors_checkbox.setChecked(True)
        self.light_colors_checkbox.setToolTip(tr(
            "ダークモードのときも、書き出し・コピー・印刷はライトの配色(白地に濃い文字)で描きます。"))
        form.addRow(self.light_colors_checkbox)

        # 「名前を付けてエクスポート」は画面の図をそのまま書き出すので、既定はそれと同じ範囲にする
        self.visible_range_checkbox = QCheckBox("表示中の範囲で書き出す")
        self.visible_range_checkbox.setChecked(True)
        self.visible_range_checkbox.setToolTip("グラフの上でマウスで拡大・移動した範囲で書き出します。外すと、プロットのプロパティで決めた範囲(自動ならデータ全体)で書き出します。")
        form.addRow(self.visible_range_checkbox)

        self.svg_text_as_path_checkbox = QCheckBox("文字をアウトライン化する(SVG)")
        self.svg_text_as_path_checkbox.setToolTip(
            "SVG保存/コピー時、目盛の数字やラベルの文字をパス(輪郭線)として出力します。"
        )
        form.addRow(self.svg_text_as_path_checkbox)

        # プレビューは応答を優先して常に間引いて描く。このチェックは保存とコピーだけに効く
        # 解像度(dpi)の設定と取り違えられたので、「間引かない」ことを名前にする
        self.full_resolution_checkbox = QCheckBox("データを間引かずに保存/コピー")
        self.full_resolution_checkbox.setToolTip(
            "「名前を付けて保存」「コピー」で、点数の多い Line(折れ線)データセットや 2D マップ(ヒートマップ/等高線)を、"
            "画面表示用に間引かず全データ点で描きます(処理が遅くなる場合があります)。画像の解像度(dpi)とは別の設定です。常に描き直すプレビュー自体は、応答を優先して間引いたまま表示します。"
        )
        form.addRow(self.full_resolution_checkbox)

        layout.addLayout(form)
        apply_form_spacing(self)

        self.preview_label = QLabel("プレビューがここに表示されます")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 150)
        self.preview_label.setObjectName("export_preview_frame")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label, 1)

        button_row = QHBoxLayout()
        # インスペクタは縦のスクロールバーの幅をいつも取っておくので、この行が入るように少し詰める
        button_row.setSpacing(4)
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
        self.save_button.setProperty("primaryButton", True)
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.unit_mirror = ComboMirror(self.unit_segments, self.unit_combo)
        self.size_preset_combo.currentIndexChanged.connect(self._on_size_preset_changed)

        self.width_spinbox.valueChanged.connect(self.refresh_preview)
        self.height_spinbox.valueChanged.connect(self.refresh_preview)
        self.unit_combo.currentIndexChanged.connect(self.refresh_preview)
        self.dpi_spinbox.valueChanged.connect(self.refresh_preview)
        self.visible_range_checkbox.toggled.connect(self.refresh_preview)
        self.light_colors_checkbox.toggled.connect(self.refresh_preview)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self._render_if_shown)

    def _on_size_preset_changed(self, _index):
        """「カスタム」なら入力した値をそのまま残す。単位を先に替える(今の幅がミリメートルに換算されてから入れ直す)。"""
        width_mm = self.size_preset_combo.currentData()
        if width_mm is None:
            return
        self.unit_combo.setCurrentIndex(self.unit_combo.findData(MILLIMETRE_UNIT))
        self.width_spinbox.setValue(width_mm)

    def get_options(self):
        """書き出しの設定(_calculate_size_in_inches で使える)。"""
        return {
            "width": self.width_spinbox.value(),
            "height": self.height_spinbox.value(),
            "unit": self.unit_combo.currentData(),
            "dpi": self.dpi_spinbox.value(),
            "transparent": self.transparent_checkbox.isChecked(),
            "svg_text_as_path": self.svg_text_as_path_checkbox.isChecked(),
            "full_resolution": self.full_resolution_checkbox.isChecked(),
            "visible_range": self.visible_range_checkbox.isChecked(),
        }

    def refresh_preview(self):
        """少し待ってまとめて描く。隠れている間は描かない(表示したときに refresh_preview が呼ばれる)。"""
        if not self.isVisible():
            return
        self._refresh_timer.start()

    def _render_if_shown(self):
        """実際に見えているときだけ描く。プロパティとタブで並べたドックは、後ろのタブでも isVisible() が真のままなので、
        見えている領域で確かめる(前に出たときはドックの visibilityChanged から refresh_preview が呼ばれる)。"""
        if self.isVisible() and not self.visibleRegion().isEmpty():
            self._render_preview()

    def _render_preview(self):
        options = self.get_options()
        width_in, height_in = self.main_window._calculate_size_in_inches(options)
        if width_in <= 0 or height_in <= 0:
            return

        # 書き出しの解像度のまま描いてから縮めると、大きな図や高い解像度で固まる。欄に合う解像度で描く
        dpi = preview_dpi(width_in, height_in, options["dpi"],
                          self.preview_label.width(), self.preview_label.height())
        if dpi is None:
            self._current_pixmap = None
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(preview_too_large_text(width_in, height_in, options["dpi"]))
            return
        pixmap = self._render_full_figure_pixmap(width_in, height_in, dpi)
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
            # 欄に合わせた解像度で描いているので、欄が描いた画像より大きくなったら描き直す
            if (self._current_pixmap.width() < self.preview_label.width()
                    and self._current_pixmap.height() < self.preview_label.height()):
                self.refresh_preview()

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
        temp_canvas.dark_mode = mw.output_dark_mode()
        if self.visible_range_checkbox.isChecked():
            # 当て直すときに設定と合わない範囲を消すので、画面の記録を写して渡す
            temp_canvas.view_overrides = copy.deepcopy(mw.canvas.view_overrides)
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
        if not confirm_output_size(self, width_in, height_in, options["dpi"]):
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
        self.save_to_chosen_file()

    def save_to_chosen_file(self):
        """保存先を聞いて、このタブの設定で書き出す(メニューと上部バーの「エクスポート」もここを通る)。

        形式は拡張子で決める。プラグインの書き出しの拡張子なら、その writer に図を渡す。
        """
        mw = self.main_window
        options = self.get_options()
        width_in, height_in = mw._calculate_size_in_inches(options)

        layout_mode = getattr(mw.project, 'layout_mode', 'grid')
        if layout_mode == 'free':
            if not mw.project.all_plot_settings:
                notify.warning(self, "保存エラー", "有効なプロットがありません。")
                return
        else:
            rows = mw.subplot_rows_spinbox.value()
            cols = mw.subplot_cols_spinbox.value()
            if rows * cols == 0:
                notify.warning(self, "保存エラー", "有効なプロットがありません。")
                return
        # PDF・SVG でも、一時的な図をこの解像度で描いてから保存する
        if not confirm_output_size(self, width_in, height_in, options["dpi"]):
            return

        filter_parts = ["PNG (*.png)", "PDF (*.pdf)", "SVG (*.svg)"]
        filter_parts += [f"{exp.format_name} (*{exp.extension})" for exp in get_registered_exporters()]
        file_path, _ = dialog_dirs.get_save_file_name(
            mw, dialog_dirs.EXPORT, "プロットを保存", dialog_dirs.project_stem(mw), ";;".join(filter_parts),
            preferred_dir=dialog_dirs.output_dir(mw)
        )
        if not file_path:
            return

        file_ext = os.path.splitext(file_path)[1].lower()
        # グラデーションの塗りはベクター形式でもラスタで埋め込まれる。書き出しは続け、知らせるだけ
        if file_ext in ('.svg', '.pdf') and project_has_raster_gradient_fill(mw.project):
            notify.warning(
                mw, "ベクター出力時の注意",
                "グラデーション塗りが有効なデータセットが含まれています。\n"
                "この部分は画像(ラスタ)として埋め込まれるため、拡大すると"
                "他の要素のようにはくっきり表示されません。\n\n"
                "エクスポートは続行します。"
            )

        temp_canvas = self._make_temp_canvas_for_full_figure(
            width_in, height_in, options["dpi"], full_resolution=options["full_resolution"]
        )
        if temp_canvas is None:
            notify.warning(self, "保存エラー", "有効なプロットがありません。")
            return
        try:
            api = get_plugin_api()
            exporter = api.get_exporter_for_extension(file_ext) if api is not None else None
            if exporter is not None:
                try:
                    exporter.writer(temp_canvas.fig, file_path)
                except Exception as e:
                    raise PluginExecutionError(
                        exporter.name, f"「{file_path}」への書き出しに失敗しました: {e}") from e
            else:
                save_kwargs = {'transparent': options["transparent"], 'bbox_inches': 'tight'}
                if file_ext not in ('.pdf', '.svg'):
                    save_kwargs['dpi'] = options["dpi"]
                with mpl.rc_context(export_rc_params(file_ext, options.get("svg_text_as_path", False))):
                    temp_canvas.fig.savefig(file_path, **save_kwargs)
            mw.statusBar().showMessage(f"保存しました: {file_path}", 3000)
        except Exception as e:
            logger.exception("エクスポートに失敗しました。")
            notify.warning(mw, "保存エラー", f"エクスポート中にエラーが発生しました:\n{e}")
        finally:
            temp_canvas.deleteLater()
