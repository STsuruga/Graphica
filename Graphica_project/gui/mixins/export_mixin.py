# gui/mixins/export_mixin.py
"""
プロットを画像/PDF/SVGとしてエクスポートする処理、およびエクスポート
ダイアログのプレビュー生成をまとめた Mixin。
"""
import io
import os
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox
from matplotlib.figure import Figure

from gui.dialogs import ExportDialog

logger = logging.getLogger(__name__)

# クリップボードにコピーする画像の解像度 (現在の表示サイズのまま、荒くならない程度のDPI)
CLIPBOARD_COPY_DPI = 150


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
