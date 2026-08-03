# gui/mixins/export_mixin.py
"""
プロットを画像/PDF/SVGとしてエクスポートする処理、およびエクスポート
ダイアログのプレビュー生成をまとめた Mixin。
"""
import io
import os
import dataclasses
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from matplotlib.figure import Figure

from gui.dialogs import ExportDialog, BatchExportDialog
from gui.canvas import MplCanvas
from models.project import ProjectModel

logger = logging.getLogger(__name__)

# クリップボードにコピーする画像の解像度 (現在の表示サイズのまま、荒くならない程度のDPI)
CLIPBOARD_COPY_DPI = 150

# 印刷時の画像レンダリング解像度 (DPI)。プリンター出力なので画面表示より高めにする
PRINT_RENDER_DPI = 200

# バッチエクスポート時、個別画像として書き出す際のFigureサイズ (インチ)
BATCH_EXPORT_FIGSIZE = (8, 6)


class ExportMixin:
    def _on_copy_plot_to_clipboard(self):
        """
        「グラフをコピー」メニューがクリックされたときの処理。
        現在表示中のグラフ全体 (全サブプロット) を画像としてクリップボードに
        コピーする。他のアプリ (Word, PowerPointなど) に直接貼り付けられる。
        """
        buf = io.BytesIO()
        try:
            self.canvas.fig.savefig(buf, format='png', dpi=CLIPBOARD_COPY_DPI, bbox_inches='tight')
        except Exception as e:
            logger.exception("グラフのクリップボードコピーに失敗しました。")
            QMessageBox.warning(self, "コピーエラー", f"グラフのコピー中にエラーが発生しました:\n{e}")
            return
        buf.seek(0)

        pixmap = QPixmap()
        pixmap.loadFromData(buf.read())
        buf.close()

        QApplication.clipboard().setPixmap(pixmap)

    def _on_print_plot(self):
        """
        「印刷...」メニューがクリックされたときの処理。
        ファイル保存を経由せず、現在表示中のグラフ(全サブプロット)を
        QPrinter経由で直接プリンターに出力する。
        matplotlibのFigureを直接QPainterで描画する代わりに、PNG画像として
        レンダリングしてから貼り付ける方式にすることで、既存のsavefig周りの
        ロジック(エクスポート機能)と同じ確実な描画結果を得られるようにしている。
        """
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        buf = io.BytesIO()
        try:
            self.canvas.fig.savefig(buf, format='png', dpi=PRINT_RENDER_DPI, bbox_inches='tight')
        except Exception as e:
            logger.exception("印刷用画像の生成に失敗しました。")
            QMessageBox.warning(self, "印刷エラー", f"印刷用の画像生成中にエラーが発生しました:\n{e}")
            return
        buf.seek(0)

        pixmap = QPixmap()
        pixmap.loadFromData(buf.read())
        buf.close()

        if pixmap.isNull():
            QMessageBox.warning(self, "印刷エラー", "印刷用の画像生成に失敗しました。")
            return

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.warning(self, "印刷エラー", "プリンターへの描画を開始できませんでした。")
            return
        try:
            page_rect = printer.pageRect(QPrinter.Unit.DevicePixel).toRect()
            scaled = pixmap.scaled(
                page_rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            x = page_rect.x() + (page_rect.width() - scaled.width()) // 2
            y = page_rect.y() + (page_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        finally:
            painter.end()

        self.statusBar().showMessage("印刷を実行しました", 3000)

    def _on_batch_export(self):
        """
        「バッチエクスポート...」メニューの処理。
        現在のプロジェクトの各サブプロットを個別画像として、または複数の
        プロジェクトファイル(.pkl)をそれぞれの完成図として、まとめて書き出す。
        """
        dialog = BatchExportDialog(len(self.project.all_plot_settings), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        options = dialog.get_common_options()
        if not options['output_dir']:
            QMessageBox.warning(self, "バッチエクスポート", "出力先フォルダを指定してください。")
            return

        mode = dialog.get_mode()
        if mode == "subplots":
            indices = dialog.get_selected_subplot_indices()
            if not indices:
                QMessageBox.warning(self, "バッチエクスポート", "書き出すサブプロットを選択してください。")
                return
            results = self._batch_export_subplots(indices, options)
        else:
            paths = dialog.get_project_file_paths()
            if not paths:
                QMessageBox.warning(self, "バッチエクスポート", "プロジェクトファイルを追加してください。")
                return
            results = self._batch_export_project_files(paths, options)

        succeeded = [name for name, error in results if error is None]
        failed = [(name, error) for name, error in results if error is not None]

        message = f"{len(succeeded)}件を書き出しました。"
        if failed:
            message += "\n\n失敗:\n" + "\n".join(f"{name}: {error}" for name, error in failed)
        QMessageBox.information(self, "バッチエクスポート完了", message)

    def _save_figure_with_options(self, fig, out_path, options):
        """savefigのkwargsを、既存の単発エクスポートと同じ方針(透過背景・bbox_inches='tight')で組み立てて保存する"""
        save_kwargs = {'transparent': True, 'bbox_inches': 'tight'}
        if options['format'] not in ('pdf', 'svg'):
            save_kwargs['dpi'] = options['dpi']
        fig.savefig(out_path, **save_kwargs)

    def _batch_export_subplots(self, indices, options):
        """
        現在のプロジェクトの、指定されたサブプロットそれぞれを個別の画像として書き出す。
        一時的な MplCanvas を新しい1x1レイアウトとして使うため、対象データセットの
        subplot_target を一時的に0に付け替えたコピー(dataclasses.replace、dfは参照共有)を渡す。
        """
        results = []
        for idx in indices:
            out_name = f"{options['prefix']}_P{idx + 1}.{options['format']}"
            out_path = os.path.join(options['output_dir'], out_name)
            try:
                settings = self.project.all_plot_settings[idx]
                datasets_for_axis = [
                    dataclasses.replace(ds, subplot_target=0)
                    for ds in self.project.datasets if ds.subplot_target == idx
                ]
                temp_canvas = MplCanvas(width=BATCH_EXPORT_FIGSIZE[0], height=BATCH_EXPORT_FIGSIZE[1], dpi=options['dpi'])
                temp_canvas.dark_mode = self.canvas.dark_mode
                try:
                    temp_canvas.redraw_all(datasets_for_axis, 1, 1, [settings])
                    self._save_figure_with_options(temp_canvas.fig, out_path, options)
                finally:
                    temp_canvas.deleteLater()
                results.append((out_name, None))
            except Exception as e:
                logger.exception("バッチエクスポート(サブプロット)に失敗しました: %s", out_name)
                results.append((out_name, str(e)))
        return results

    def _batch_export_project_files(self, paths, options):
        """
        複数のプロジェクトファイル(.pkl)それぞれを読み込み、その完成図を書き出す。
        現在開いているプロジェクト/GUIの状態には一切触れない(使い捨てのProjectModelと
        MplCanvasだけを使う)。
        """
        results = []
        for path in paths:
            base_name = os.path.splitext(os.path.basename(path))[0]
            out_name = f"{options['prefix']}_{base_name}.{options['format']}"
            out_path = os.path.join(options['output_dir'], out_name)
            try:
                temp_project = ProjectModel()
                temp_project.load_project(path)
                layout_mode = getattr(temp_project, 'layout_mode', 'grid')
                if layout_mode == 'free':
                    # 自由配置レイアウトでは行数×列数という概念が無いため、
                    # サブプロット数(=all_plot_settingsの要素数)に応じた標準サイズを使う。
                    if not temp_project.all_plot_settings:
                        raise ValueError("有効なプロット設定が見つかりません")
                    rows, cols = 0, 0
                    fig_width, fig_height = BATCH_EXPORT_FIGSIZE[0] * 2, BATCH_EXPORT_FIGSIZE[1] * 2
                else:
                    rows, cols = temp_project.layout_rows, temp_project.layout_cols
                    if rows * cols == 0 or not temp_project.all_plot_settings:
                        raise ValueError("有効なプロット設定が見つかりません")
                    fig_width, fig_height = BATCH_EXPORT_FIGSIZE[0] * cols, BATCH_EXPORT_FIGSIZE[1] * rows

                temp_canvas = MplCanvas(width=fig_width, height=fig_height, dpi=options['dpi'])
                temp_canvas.dark_mode = self.canvas.dark_mode
                try:
                    temp_canvas.redraw_all(
                        temp_project.datasets, rows, cols, temp_project.all_plot_settings, layout_mode=layout_mode
                    )
                    self._save_figure_with_options(temp_canvas.fig, out_path, options)
                finally:
                    temp_canvas.deleteLater()
                results.append((out_name, None))
            except Exception as e:
                logger.exception("バッチエクスポート(プロジェクトファイル)に失敗しました: %s", path)
                results.append((os.path.basename(path), str(e)))
        return results

    def _on_export_plot(self):
            """
            「名前を付けてエクスポート」メニューがクリックされたときの処理。
            ExportDialog を表示し、設定を取得してプロットをファイルに保存します。
            """

            # 1. ExportDialog を作成
            dialog = ExportDialog(self)

            # 2. ダイアログの「プレビュー更新」ボタンの clicked シグナルを、
            #    _generate_preview メソッドに接続
            #    (lambda を使い、dialog 自身を引数として渡す)
            dialog.preview_button.clicked.connect(
                lambda: self._generate_preview(dialog)
            )

            # 3. ダイアログをモーダルで表示し、"Save" (Accepted) が押されたか確認
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # 4. ダイアログから設定辞書を取得
                options = dialog.get_options()

                # 5. 保存先ファイルパスを QFileDialog で取得
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "プロットを保存", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)"
                )
                if not file_path:
                    return # キャンセルされた

                # 6. ヘルパーメソッドで、設定 (px, cm) をインチ (in) に変換
                width_in, height_in = self._calculate_size_in_inches(options)

                # 7. ★ 一時的に Figure サイズを変更して保存
                original_size = self.canvas.fig.get_size_inches() # 現在のサイズを退避

                # 8. Figure のサイズをダイアログで指定されたサイズに変更
                self.canvas.fig.set_size_inches(width_in, height_in)

                # 9. savefig を実行 (DPIも指定)
                #    (transparent=True など、他のオプションもここに追加可能)
                try:
                    # ファイルパスの拡張子を取得 (小文字に変換)
                    file_ext = os.path.splitext(file_path)[1].lower()

                    # (オプション: 背景を透明にする)
                    save_kwargs = {'transparent': True}
                    save_kwargs['bbox_inches'] = 'tight'

                    # ベクター形式 (pdf, svg) の場合は dpi を指定しない
                    if file_ext in ['.pdf', '.svg']:
                        pass
                    else:
                        # ラスター形式 (png など) の場合は dpi を指定
                        save_kwargs['dpi'] = options["dpi"]

                    self.canvas.fig.savefig(file_path, **save_kwargs)
                except Exception as e:
                    QMessageBox.warning(self, "保存エラー", f"エクスポート中にエラーが発生しました:\n{e}")
                finally:
                    # 10. ★★★ 必須 ★★★
                    #    保存が成功しても失敗しても、Figure のサイズを
                    #    GUI上の元のサイズ (original_size) に戻す
                    self.canvas.fig.set_size_inches(original_size)
                    self.canvas.draw_idle() # GUIのキャンバスを再描画

    def _generate_preview(self, dialog):
            """
            ExportDialog 内の「プレビュー更新」ボタンが押されたときの処理。
            「現在アクティブなプロット」のプレビューを生成し、ダイアログに表示します。

            Args:
                dialog (ExportDialog): プレビューを表示するダイアログのインスタンス。
            """

            # 1. ダイアログから現在の設定を取得
            options = dialog.get_options()

            # 2. サイズをインチに変換
            width_in, height_in = self._calculate_size_in_inches(options)

            # 3. ★ プレビュー用の「一時的な」Figure を作成
            #    (GUIの self.canvas.fig とは別物)
            temp_fig = Figure(figsize=(width_in, height_in), dpi=100) # プレビューは 100 dpi 固定で十分
            temp_ax = temp_fig.add_subplot(111) # プレビューは 1x1

            # 4. 現在アクティブな軸」のインデックスと設定を取得
            active_index = self.project.active_axis_index
            if active_index >= len(self.project.all_plot_settings):
                logger.warning("プレビュー生成時、アクティブな軸設定が見つかりません。")
                return

            active_settings = self.project.all_plot_settings[active_index]

            # 5. 一時的な軸 (temp_ax) に対し、アクティブな軸の
            #    「データ」と「外観」を描画/適用する
            try:
                original_secondary = self.canvas.all_secondary_axes.copy()
                while len(self.canvas.all_secondary_axes) <= active_index:
                     self.canvas.all_secondary_axes.append(None)

                self.canvas._draw_data(temp_ax, active_index, self.project.datasets)
                self.canvas._apply_appearance(temp_ax, active_index, active_settings)

                self.canvas.all_secondary_axes = original_secondary
            except Exception as e:
                logger.error("プレビュー生成中にエラー: %s", e)

            # 6. tight_layout() でラベルの重なりを調整
            try:
                temp_fig.tight_layout()
            except ValueError:
                pass # 失敗しても無視

            # 7. メモリ上のバイトバッファ (BytesIO) に PNG として保存
            buf = io.BytesIO()
            temp_fig.savefig(buf, format='png', dpi=100)
            buf.seek(0) # バッファのポインタを先頭に戻す

            # 8. バッファから QPixmap (Qtの画像) をロード
            pixmap = QPixmap()
            pixmap.loadFromData(buf.read())

            # 9. ダイアログの QLabel に QPixmap をセット
            dialog.preview_label.setPixmap(
                pixmap.scaled(dialog.preview_label.size(), # ラベルのサイズ (400x300) に合わせる
                            Qt.AspectRatioMode.KeepAspectRatio, # アスペクト比を維持
                            Qt.TransformationMode.SmoothTransformation) # 滑らかに縮小
            )

            buf.close()
            del temp_fig # メモリを明示的に解放

    def _calculate_size_in_inches(self, options):
            """
            ExportDialog の設定 (options 辞書) から、
            幅と高さを「インチ」単位に変換して返すヘルパーメソッド。

            Args:
                options (dict): dialog.get_options() で取得した辞書。

            Returns:
                tuple (float, float): (width_in_inches, height_in_inches)
            """
            width, height, unit, dpi = options["width"], options["height"], options["unit"], options["dpi"]

            if "インチ" in unit:
                # 単位がインチなら、そのまま返す
                return width, height
            elif "センチメートル" in unit:
                # 1 インチ = 2.54 cm
                return width / 2.54, height / 2.54
            elif "ピクセル" in unit:
                # インチ = ピクセル数 / DPI (Dots Per Inch)
                return width / dpi, height / dpi

            # デフォルト (万が一単位が不明な場合)
            return 8, 6
