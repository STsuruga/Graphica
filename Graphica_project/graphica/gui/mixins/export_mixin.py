"""画像・PDF・SVG への書き出し、印刷、クリップボード、書き出しのプレビュー。"""
import datetime
import io
import os
import dataclasses
import logging
import matplotlib as mpl
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QImage
from PySide6.QtWidgets import QApplication, QDialog, QProgressDialog
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages

from graphica.gui import notify
from graphica.core.axis_settings import axis_setting
from graphica.gui.dialogs import ExportDialog, BatchExportDialog, CaptionGeneratorDialog, CVDSimulationDialog
from graphica.gui.canvas import _HeadlessRenderCanvas
from graphica.gui.export_settings import export_rc_params
from graphica.gui.task_runner import TaskRunner
from graphica.models.project import ProjectModel
from graphica.core.plugin_api import get_plugin_api, get_registered_exporters
from graphica.core.plugin_types import PluginExecutionError
from graphica.core.script_export import generate_python_script
from graphica.core.caption_export import sanitize_label
from graphica.core.report_export import collect_methods_sections, generate_html_report

logger = logging.getLogger(__name__)

def _project_has_raster_gradient_fill(project):
    """グラデーションの塗り(imshow で描くのでベクター形式でもラスタになる)を使う系列があるか。"""
    return any(
        ds.plot_type == 'Area' and ds.gradient_enabled and ds.gradient_target in ('fill', 'both')
        for ds in project.datasets
    )


CLIPBOARD_COPY_DPI = 150

PRINT_RENDER_DPI = 200

BATCH_EXPORT_FIGSIZE = (8, 6)


class ExportMixin:
    def _on_copy_plot_to_clipboard(self):
        buf = io.BytesIO()
        try:
            self.canvas.fig.savefig(buf, format='png', dpi=CLIPBOARD_COPY_DPI, bbox_inches='tight')
        except Exception as e:
            logger.exception("グラフのクリップボードコピーに失敗しました。")
            notify.warning(self, "コピーエラー", f"グラフのコピー中にエラーが発生しました:\n{e}")
            return
        buf.seek(0)

        pixmap = QPixmap()
        pixmap.loadFromData(buf.read())
        buf.close()

        QApplication.clipboard().setPixmap(pixmap)

    def _on_show_cvd_simulation(self):
        """今のグラフを1回だけ PNG にし、ダイアログはその画像を変換して見せる(グラフは描き直さない)。"""
        buf = io.BytesIO()
        try:
            self.canvas.fig.savefig(buf, format='png', dpi=CLIPBOARD_COPY_DPI, bbox_inches='tight')
        except Exception as e:
            logger.exception("色覚シミュレーションプレビュー用の画像生成に失敗しました。")
            notify.warning(self, "プレビューエラー", f"プレビュー画像の生成中にエラーが発生しました:\n{e}")
            return
        buf.seek(0)
        image = QImage()
        image.loadFromData(buf.read())
        buf.close()

        dialog = CVDSimulationDialog(image, self)
        dialog.exec()

    def _on_print_plot(self):
        """PNG に描いてから QPrinter に貼る(書き出しと同じ描画結果になる)。"""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        buf = io.BytesIO()
        try:
            self.canvas.fig.savefig(buf, format='png', dpi=PRINT_RENDER_DPI, bbox_inches='tight')
        except Exception as e:
            logger.exception("印刷用画像の生成に失敗しました。")
            notify.warning(self, "印刷エラー", f"印刷用の画像生成中にエラーが発生しました:\n{e}")
            return
        buf.seek(0)

        pixmap = QPixmap()
        pixmap.loadFromData(buf.read())
        buf.close()

        if pixmap.isNull():
            notify.warning(self, "印刷エラー", "印刷用の画像生成に失敗しました。")
            return

        painter = QPainter()
        if not painter.begin(printer):
            notify.warning(self, "印刷エラー", "プリンターへの描画を開始できませんでした。")
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
        """サブプロットごと、または複数のプロジェクトファイルをまとめて書き出す。別スレッドで1本の TaskRunner で行う。

        rc_context はプロセス全体の rcParams を書き換えるので、並列にはしない。
        """
        if self._batch_export_task_runner is not None:
            notify.information(self, "実行中", "別のバッチエクスポート処理が実行中です。完了までお待ちください。")
            return

        extra_formats = [exp.format_name for exp in get_registered_exporters()]
        dialog = BatchExportDialog(len(self.project.all_plot_settings), self, extra_formats=extra_formats)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        options = dialog.get_common_options()
        if not options['output_dir']:
            notify.warning(self, "バッチエクスポート", "出力先フォルダを指定してください。")
            return

        mode = dialog.get_mode()
        if mode == "subplots":
            indices = dialog.get_selected_subplot_indices()
            if not indices:
                notify.warning(self, "バッチエクスポート", "書き出すサブプロットを選択してください。")
                return
            items = indices
            worker_fn = self._batch_export_subplots
        else:
            paths = dialog.get_project_file_paths()
            if not paths:
                notify.warning(self, "バッチエクスポート", "プロジェクトファイルを追加してください。")
                return
            items = paths
            worker_fn = self._batch_export_project_files

        progress_dialog = QProgressDialog("バッチエクスポートを実行中...", "キャンセル", 0, len(items), self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)

        runner = TaskRunner(worker_fn, items, options)
        runner.progress.connect(lambda done, total, message: progress_dialog.setValue(done))
        progress_dialog.canceled.connect(runner.requestInterruption)
        runner.succeeded.connect(lambda results: self._on_batch_export_succeeded(results, progress_dialog))
        runner.failed.connect(lambda msg: self._on_batch_export_failed(msg, progress_dialog))
        self._batch_export_task_runner = runner
        runner.start()

    def _cleanup_batch_export_task_runner(self):
        if self._batch_export_task_runner is not None:
            self._batch_export_task_runner.wait()
            self._batch_export_task_runner.deleteLater()
            self._batch_export_task_runner = None

    def _on_batch_export_failed(self, error_message, progress_dialog):
        self._cleanup_batch_export_task_runner()
        progress_dialog.close()
        notify.warning(self, "バッチエクスポート", f"バッチエクスポート処理に失敗しました:\n{error_message}")

    def _on_batch_export_succeeded(self, results, progress_dialog):
        """結果は [(出力ファイル名, エラーか None), ...]。キャンセルなら終わった分だけ。"""
        self._cleanup_batch_export_task_runner()
        progress_dialog.close()

        succeeded = [name for name, error in results if error is None]
        failed = [(name, error) for name, error in results if error is not None]

        if not succeeded and not failed:
            return  # 1件も終わらないうちにキャンセルされた

        message = f"{len(succeeded)}件を書き出しました。"
        if failed:
            message += "\n\n失敗:\n" + "\n".join(f"{name}: {error}" for name, error in failed)
        notify.information(self, "バッチエクスポート完了", message)

    def _save_figure_with_options(self, fig, out_path, options):
        """bbox_inches='tight' で保存する。rc の設定は export_rc_params(SVG の文字の扱い、PDF の TrueType 埋め込み)。

        形式がプラグインの書き出しの名前なら、プラグインの writer を呼ぶ。
        """
        api = get_plugin_api()
        exporter = api.get_exporter(options['format']) if api is not None else None
        if exporter is not None:
            try:
                exporter.writer(fig, out_path)
            except Exception as e:
                raise PluginExecutionError(exporter.name, f"「{out_path}」への書き出しに失敗しました: {e}") from e
            return

        save_kwargs = {'transparent': options.get('transparent', True), 'bbox_inches': 'tight'}
        if options['format'] not in ('pdf', 'svg'):
            save_kwargs['dpi'] = options['dpi']
        with mpl.rc_context(export_rc_params(options['format'], options.get('svg_text_as_path', False))):
            fig.savefig(out_path, **save_kwargs)

    def _batch_export_subplots(self, indices, options, report_progress=None, is_cancelled=None):
        """サブプロットを1枚ずつ書き出す。1x1 の一時キャンバスなので、subplot_target を 0 にした写しを渡す。

        別スレッドで呼ばれるので Qt には触れない(_HeadlessRenderCanvas は QWidget ではない)。
        キャンセルは1件ごとにしか見ない(1件の描画と保存は中断できない)。
        """
        results = []
        total = len(indices)
        for i, idx in enumerate(indices):
            if is_cancelled is not None and is_cancelled():
                break
            if report_progress is not None:
                report_progress(i, total, f"P{idx + 1}")
            out_name = f"{options['prefix']}_P{idx + 1}.{options['format']}"
            out_path = os.path.join(options['output_dir'], out_name)
            try:
                settings = self.project.all_plot_settings[idx]
                datasets_for_axis = [
                    dataclasses.replace(ds, subplot_target=0)
                    for ds in self.project.datasets if ds.subplot_target == idx
                ]
                temp_canvas = _HeadlessRenderCanvas(width=BATCH_EXPORT_FIGSIZE[0], height=BATCH_EXPORT_FIGSIZE[1], dpi=options['dpi'])
                temp_canvas.dark_mode = self.canvas.dark_mode
                temp_canvas.redraw_all(datasets_for_axis, 1, 1, [settings], full_resolution=options.get('full_resolution', False))
                self._save_figure_with_options(temp_canvas.fig, out_path, options)
                results.append((out_name, None))
            except Exception as e:
                logger.exception("バッチエクスポート(サブプロット)に失敗しました: %s", out_name)
                results.append((out_name, str(e)))
        return results

    def _batch_export_project_files(self, paths, options, report_progress=None, is_cancelled=None):
        """プロジェクトファイルを1つずつ読み、その図を書き出す。開いているプロジェクトには触れない。別スレッドで呼ばれる。"""
        results = []
        total = len(paths)
        for i, path in enumerate(paths):
            if is_cancelled is not None and is_cancelled():
                break
            if report_progress is not None:
                report_progress(i, total, os.path.basename(path))
            base_name = os.path.splitext(os.path.basename(path))[0]
            out_name = f"{options['prefix']}_{base_name}.{options['format']}"
            out_path = os.path.join(options['output_dir'], out_name)
            try:
                temp_project = ProjectModel()
                temp_project.load_project(path)
                layout_mode = getattr(temp_project, 'layout_mode', 'grid')
                if layout_mode == 'free':
                    # 自由配置には行×列が無いので、サブプロットの数に応じた大きさにする
                    if not temp_project.all_plot_settings:
                        raise ValueError("有効なプロット設定が見つかりません")
                    rows, cols = 0, 0
                    fig_width, fig_height = BATCH_EXPORT_FIGSIZE[0] * 2, BATCH_EXPORT_FIGSIZE[1] * 2
                else:
                    rows, cols = temp_project.layout_rows, temp_project.layout_cols
                    if rows * cols == 0 or not temp_project.all_plot_settings:
                        raise ValueError("有効なプロット設定が見つかりません")
                    fig_width, fig_height = BATCH_EXPORT_FIGSIZE[0] * cols, BATCH_EXPORT_FIGSIZE[1] * rows

                temp_canvas = _HeadlessRenderCanvas(width=fig_width, height=fig_height, dpi=options['dpi'])
                temp_canvas.dark_mode = self.canvas.dark_mode
                temp_canvas.redraw_all(
                    temp_project.datasets, rows, cols, temp_project.all_plot_settings, layout_mode=layout_mode,
                    panel_labels_enabled=temp_project.panel_labels_enabled,
                    full_resolution=options.get('full_resolution', False),
                )
                self._save_figure_with_options(temp_canvas.fig, out_path, options)
                results.append((out_name, None))
            except Exception as e:
                logger.exception("バッチエクスポート(プロジェクトファイル)に失敗しました: %s", path)
                results.append((os.path.basename(path), str(e)))
        return results

    def _on_export_python_script(self):
        """matplotlib だけで図を再現するスクリプトを書き出す(生成は core/script_export.py)。"""
        file_path, _ = notify.get_save_file_name(
            self, "Pythonスクリプトとしてエクスポート", "", "Python Files (*.py)"
        )
        if not file_path:
            return
        if not file_path.endswith('.py'):
            file_path += '.py'

        try:
            script_text = generate_python_script(self.project)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(script_text)
        except Exception as e:
            notify.warning(self, "保存エラー", f"スクリプトの書き出し中にエラーが発生しました:\n{e}")
            logger.exception("Pythonスクリプトの書き出し中にエラー")
            return

        self.statusBar().showMessage(f"Pythonスクリプトを書き出しました: {file_path}", 3000)

    def _on_generate_caption(self):
        """今の軸のタイトルを初期値にキャプションのダイアログを出す(生成は core/caption_export.py)。"""
        settings = {}
        if 0 <= self.project.active_axis_index < len(self.project.all_plot_settings):
            settings = self.project.all_plot_settings[self.project.active_axis_index]
        default_caption = axis_setting(settings, 'title') or ''
        default_label = sanitize_label(default_caption)

        dialog = CaptionGeneratorDialog(default_caption, default_label, self)
        dialog.exec()

    def _on_generate_report(self):
        """グラフの画像と、履歴のある全データセットの方法の文を1つのレポートにする。形式は拡張子(.html / .pdf)で決まる。"""
        settings = {}
        if 0 <= self.project.active_axis_index < len(self.project.all_plot_settings):
            settings = self.project.all_plot_settings[self.project.active_axis_index]
        title = axis_setting(settings, 'title') or "実験レポート"

        file_path, _ = notify.get_save_file_name(
            self, "実験レポートを生成", "", "HTML Files (*.html);;PDF Files (*.pdf)"
        )
        if not file_path:
            return
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in ('.html', '.pdf'):
            file_ext = '.html'
            file_path += file_ext

        methods_sections = collect_methods_sections(self.project)

        try:
            if file_ext == '.pdf':
                self._write_pdf_report(file_path, title, methods_sections)
            else:
                buf = io.BytesIO()
                self.canvas.fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
                html_text = generate_html_report(buf.getvalue(), methods_sections, title=title)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(html_text)
        except Exception as e:
            logger.exception("実験レポートの生成中にエラーが発生しました。")
            notify.warning(self, "保存エラー", f"実験レポートの生成中にエラーが発生しました:\n{e}")
            return

        self.statusBar().showMessage(f"実験レポートを書き出しました: {file_path}", 3000)

    def _write_pdf_report(self, file_path, title, methods_sections):
        """1ページ目にグラフ、2ページ目にタイトルと方法の文。"""
        from graphica.gui.mathtext_preview import JP_CAPABLE_FONT_FAMILIES

        with mpl.rc_context(export_rc_params('pdf')), PdfPages(file_path) as pdf:
            pdf.savefig(self.canvas.fig, bbox_inches='tight')

            text_fig = Figure(figsize=(8.27, 11.69))  # A4 縦
            text_fig.text(0.08, 0.95, title, fontsize=16, fontweight='bold', va='top',
                          family=JP_CAPABLE_FONT_FAMILIES)
            body_lines = [f"生成日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "方法:"]
            if methods_sections:
                for name, text in methods_sections:
                    body_lines.append(f"・{name}: {text}")
            else:
                body_lines.append("(処理履歴を持つデータセットはありません)")
            text_fig.text(0.08, 0.88, "\n".join(body_lines), fontsize=10, va='top', wrap=True,
                          family=JP_CAPABLE_FONT_FAMILIES)
            pdf.savefig(text_fig)

    def _on_export_plot(self):
            dialog = ExportDialog(self)

            dialog.preview_button.clicked.connect(
                lambda: self._generate_preview(dialog)
            )

            if dialog.exec() == QDialog.DialogCode.Accepted:
                options = dialog.get_options()

                filter_parts = ["PNG (*.png)", "PDF (*.pdf)", "SVG (*.svg)"]
                for exp in get_registered_exporters():
                    filter_parts.append(f"{exp.format_name} (*{exp.extension})")
                file_path, _ = notify.get_save_file_name(
                    self, "プロットを保存", "", ";;".join(filter_parts)
                )
                if not file_path:
                    return

                # グラデーションの塗りはベクター形式でもラスタで埋め込まれる。書き出しは続け、知らせるだけ
                export_ext = os.path.splitext(file_path)[1].lower()
                if export_ext in ('.svg', '.pdf') and _project_has_raster_gradient_fill(self.project):
                    notify.warning(
                        self, "ベクター出力時の注意",
                        "グラデーション塗りが有効なデータセットが含まれています。\n"
                        "この部分は画像(ラスタ)として埋め込まれるため、拡大すると"
                        "他の要素のようにはくっきり表示されません。\n\n"
                        "エクスポートは続行します。"
                    )

                width_in, height_in = self._calculate_size_in_inches(options)

                # フル解像度なら間引かずに描き直してから保存する(finally で画面用に戻す)
                full_resolution = options.get('full_resolution', False)
                if full_resolution:
                    self._update_plot(full_resolution=True)

                original_size = self.canvas.fig.get_size_inches()

                self.canvas.fig.set_size_inches(width_in, height_in)

                try:
                    file_ext = os.path.splitext(file_path)[1].lower()

                    api = get_plugin_api()
                    exporter = api.get_exporter_for_extension(file_ext) if api is not None else None
                    if exporter is not None:
                        try:
                            exporter.writer(self.canvas.fig, file_path)
                        except Exception as e:
                            raise PluginExecutionError(
                                exporter.name, f"「{file_path}」への書き出しに失敗しました: {e}"
                            ) from e
                        return

                    save_kwargs = {'transparent': options.get('transparent', True)}
                    save_kwargs['bbox_inches'] = 'tight'

                    if file_ext in ['.pdf', '.svg']:
                        pass
                    else:
                        save_kwargs['dpi'] = options["dpi"]

                    with mpl.rc_context(export_rc_params(file_ext, options.get('svg_text_as_path', False))):
                        self.canvas.fig.savefig(file_path, **save_kwargs)
                except Exception as e:
                    logger.exception("エクスポートに失敗しました")
                    notify.warning(self, "保存エラー", f"エクスポート中にエラーが発生しました:\n{e}")
                finally:
                    # 失敗しても画面の大きさに戻す
                    self.canvas.fig.set_size_inches(original_size)
                    if full_resolution:
                        self._update_plot(full_resolution=False)
                    self.canvas.draw_idle()

    def _generate_preview(self, dialog):
            """今の軸だけを、書き出しの大きさの一時的な Figure に描いて見せる。"""

            options = dialog.get_options()

            width_in, height_in = self._calculate_size_in_inches(options)

            temp_fig = Figure(figsize=(width_in, height_in), dpi=100)
            temp_ax = temp_fig.add_subplot(111)

            active_index = self.project.active_axis_index
            if active_index >= len(self.project.all_plot_settings):
                logger.warning("プレビュー生成時、アクティブな軸設定が見つかりません。")
                return

            active_settings = self.project.all_plot_settings[active_index]

            # _draw_data は第2Y軸をこの一時的な Figure に作って all_secondary_axes に入れる。
            # 失敗しても必ず戻さないと、画面の第2Y軸がプレビューの軸を指したままになる。
            original_secondary = self.canvas.all_secondary_axes.copy()
            try:
                while len(self.canvas.all_secondary_axes) <= active_index:
                    self.canvas.all_secondary_axes.append(None)

                self.canvas._draw_data(
                    temp_ax, active_index, self.project.datasets,
                    full_resolution=options.get('full_resolution', False),
                )
                self.canvas._apply_appearance(temp_ax, active_index, active_settings)
            except Exception:
                logger.exception("エクスポートのプレビューを描画できませんでした")
            finally:
                self.canvas.all_secondary_axes = original_secondary

            try:
                temp_fig.tight_layout()
            except ValueError:
                pass

            buf = io.BytesIO()
            temp_fig.savefig(buf, format='png', dpi=100)
            buf.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(buf.read())

            dialog.preview_label.setPixmap(
                pixmap.scaled(dialog.preview_label.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            )

            buf.close()
            del temp_fig

    def _calculate_size_in_inches(self, options):
            """ダイアログの幅と高さをインチにする。"""
            width, height, unit, dpi = options["width"], options["height"], options["unit"], options["dpi"]

            if "インチ" in unit:
                return width, height
            elif "ミリメートル" in unit:
                return width / 25.4, height / 25.4
            elif "センチメートル" in unit:
                return width / 2.54, height / 2.54
            elif "ピクセル" in unit:
                return width / dpi, height / dpi

            return 8, 6
