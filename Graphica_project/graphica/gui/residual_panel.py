"""選んだデータセットのフィットの残差を出すドック。dataset.fit_result の残差をそのまま描く(計算し直さない)。

メインのグラフを上下2段に分けないのは、サブプロットの数・配置・自由配置・第2Y軸などの前提と絡み合うため。
"""
import logging

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from graphica.gui import theme

logger = logging.getLogger(__name__)


class ResidualPanel(QWidget):
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
        """fit_result が無いか残差が空なら案内の文を出す。"""
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
