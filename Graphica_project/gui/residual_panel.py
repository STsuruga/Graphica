"""
gui/residual_panel.py

残差プロットの専用ドックパネル(項目C-406)。ミニマップ(gui/minimap_widget.py)
やエクスポートプレビュー(gui/export_preview_panel.py)と同じ「メインキャンバス
とは別の独立したFigure/Axesを持つ、選択状態に連動する小さなパネル」という
設計方針を踏襲する。選択中のデータセットが切り替わるたびに refresh(dataset)
が呼ばれ(gui/mixins/dataset_mixin.pyの_update_ui_state内)、そのデータセットが
曲線フィットの結果(dataset.fit_result、項目C-401で永続化)を持っていれば
dataset.fit_result['residual_x']/['residuals'] をそのまま散布図として描画する
(再計算はしない)。持っていなければプレースホルダの案内文を表示する。

★ 設計上の割り切り(実装時の判断、ユーザーとの相談の上で採用):
ロードマップ原文の「上下連動2段パネル」を、メインプロットのサブプロット
グリッド内に実際に2段のAxesとして埋め込む形(sharex等での軸連動)ではなく、
独立したドックパネルとして実装した。理由:
  - メインキャンバスの再描画ロジック(gui/canvas.pyのredraw_all/_draw_data)は
    サブプロット数=all_plot_settingsの要素数という前提でグリッド/自由配置
    レイアウトを組んでおり、「特定のデータセットが選択されている間だけその
    サブプロットを2段に割る」という状態を持ち込むと、グリッド計算・自由配置の
    ドラッグ座標・ミニマップ連動・第2Y軸等、既存の多くの機構と複雑に絡み合う
    ことになり、リグレッションリスクが高い。
  - 既にこのコードベースには「メインキャンバスとは別の、選択状態に連動する
    小さな独立パネル」という確立されたパターンがある(ミニマップ、エクスポート
    プレビュー)。これに倣うことで、既存機構を一切変更せずに実装できる。
  - 「連動」の意味を、軸範囲のリアルタイム同期(パン/ズームの相互反映)では
    なく、「選択中のフィットデータセットの残差が常に最新の状態で表示される」
    という選択状態の連動として解釈した。
"""
import logging

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from gui import theme

logger = logging.getLogger(__name__)


class ResidualPanel(QWidget):
    """
    フィット結果の残差(実測値 - フィット値)を表示する常設パネル。
    gui/dialogs.pyのResultDialog内の残差プロット(フィット直後に一度だけ表示
    される非モーダルダイアログの一部)と同じ配色方針(gui.themeの現在の
    トークンを使い、ダーク/ライト両対応)だが、こちらは選択中のデータセットに
    追従して更新され続ける常設パネルという点が異なる。
    """

    def __init__(self, parent=None, dpi=100):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.placeholder_label = QLabel(
            "曲線フィットの結果を持つデータセットを選択すると、\n"
            "ここに残差(実測値 - フィット値)が表示されます。"
        )
        self.placeholder_label.setWordWrap(True)
        self.placeholder_label.setStyleSheet("color: gray; padding: 12px;")
        layout.addWidget(self.placeholder_label)

        self.fig = Figure(figsize=(4, 2.2), dpi=dpi, tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setMinimumHeight(160)
        self.ax = self.fig.add_subplot(111)
        layout.addWidget(self.canvas)
        self.canvas.setVisible(False)

    def refresh(self, dataset):
        """
        選択中のデータセット(非選択時はNone)を受けて、残差プロットを描き直す。
        dataset.fit_result が無い、または残差データが空の場合はプレースホルダ
        表示に戻す(再計算は一切しない — dataset.fit_result に既に永続化されて
        いる残差をそのまま読むだけ)。
        """
        fit_result = dataset.fit_result if dataset is not None else None
        residual_x = fit_result.get('residual_x') if fit_result else None
        residuals = fit_result.get('residuals') if fit_result else None

        if not residual_x or not residuals:
            self.canvas.setVisible(False)
            self.placeholder_label.setVisible(True)
            return

        self.placeholder_label.setVisible(False)
        self.canvas.setVisible(True)

        tokens = theme.current_tokens()
        self.fig.set_facecolor(tokens['surface'])
        self.ax.cla()
        self.ax.set_facecolor(tokens['surface'])
        self.ax.axhline(0, color=tokens['border_strong'], linewidth=0.8, linestyle='--')
        self.ax.scatter(residual_x, residuals, s=14, color='#1F6F78')
        self.ax.set_xlabel("X", fontsize=8, color=tokens['text_primary'])
        self.ax.set_ylabel("残差", fontsize=8, color=tokens['text_primary'])
        self.ax.tick_params(labelsize=7, colors=tokens['text_primary'])
        for spine in self.ax.spines.values():
            spine.set_color(tokens['border_strong'])
        self.canvas.draw_idle()
