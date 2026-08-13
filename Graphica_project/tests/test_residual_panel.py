# tests/test_residual_panel.py
"""項目C-406「残差プロット」の専用ドックパネル(ResidualPanel)に対するテスト。"""
import matplotlib
matplotlib.use("Agg")
import pytest

from gui.residual_panel import ResidualPanel
from core.dataset import Dataset
import pandas as pd


def _make_dataset_with_fit_result(fit_result):
    df = pd.DataFrame({"x_fit": [0.0, 1.0, 2.0], "y_fit": [1.0, 2.0, 3.0]})
    return Dataset(name="Fit (d)", df=df, x_col_name="x_fit", y_col_name="y_fit",
                    fit_result=fit_result)


@pytest.fixture
def panel(qapp):
    # isVisible()はウィジェット自身がshow()されたトップレベルウィンドウに
    # 属していないと常にFalseを返す(setVisible(True)を呼んだだけでは不十分)。
    p = ResidualPanel()
    p.show()
    qapp.processEvents()
    yield p
    p.close()


def test_residual_panel_starts_with_placeholder_visible(panel):
    assert panel.placeholder_label.isVisible() is True
    assert panel.canvas.isVisible() is False


def test_residual_panel_refresh_none_shows_placeholder(panel):
    panel.refresh(None)
    assert panel.placeholder_label.isVisible() is True
    assert panel.canvas.isVisible() is False


def test_residual_panel_refresh_dataset_without_fit_result_shows_placeholder(panel):
    ds = Dataset(name="d", df=pd.DataFrame({"x": [1.0], "y": [1.0]}), x_col_name="x", y_col_name="y")
    panel.refresh(ds)
    assert panel.placeholder_label.isVisible() is True
    assert panel.canvas.isVisible() is False


def test_residual_panel_refresh_with_fit_result_shows_canvas(panel):
    ds = _make_dataset_with_fit_result({
        'residual_x': [0.0, 1.0, 2.0],
        'residuals': [0.1, -0.2, 0.05],
    })
    panel.refresh(ds)
    assert panel.placeholder_label.isVisible() is False
    assert panel.canvas.isVisible() is True
    # 散布図が実際に描画されていること(0,0を通る基準線 + 残差の散布図の2アーティスト)
    assert len(panel.ax.collections) == 1
    assert len(panel.ax.lines) == 1  # axhline(0)


def test_residual_panel_refresh_with_empty_residuals_shows_placeholder(panel):
    """fit_resultはあるが、residual_x/residualsが空リストの退化ケース
    (例: データ点数がパラメータ数と同じで自由度0のフィット)でもクラッシュせず
    プレースホルダに戻ること。"""
    ds = _make_dataset_with_fit_result({'residual_x': [], 'residuals': []})
    panel.refresh(ds)
    assert panel.placeholder_label.isVisible() is True
    assert panel.canvas.isVisible() is False


def test_residual_panel_refresh_replaces_previous_plot_not_accumulates(panel):
    """refresh()を複数回呼んでも、古い散布図/基準線が残らず1回分だけ描画される
    こと(ax.cla()を呼ばずにaxhline/scatterを積み上げていくとリークするため)。"""
    ds1 = _make_dataset_with_fit_result({'residual_x': [0.0, 1.0], 'residuals': [0.1, 0.2]})
    ds2 = _make_dataset_with_fit_result({'residual_x': [0.0, 1.0, 2.0], 'residuals': [0.3, -0.1, 0.2]})

    panel.refresh(ds1)
    panel.refresh(ds2)

    assert len(panel.ax.collections) == 1
    assert len(panel.ax.lines) == 1


def test_residual_panel_refresh_back_to_none_after_showing_data_returns_to_placeholder(panel):
    ds = _make_dataset_with_fit_result({'residual_x': [0.0, 1.0], 'residuals': [0.1, 0.2]})
    panel.refresh(ds)
    assert panel.canvas.isVisible() is True

    panel.refresh(None)
    assert panel.placeholder_label.isVisible() is True
    assert panel.canvas.isVisible() is False
