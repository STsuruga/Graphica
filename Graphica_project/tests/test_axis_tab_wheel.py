"""軸の設定のタブ(X軸 / Y軸 / ラベル/書式)は、ホイールでは切り替わらない。"""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from graphica.gui.builders.common import disable_wheel_tab_switching
from graphica.gui.main_window import PlotterApp


def _scroll(tab_bar):
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(tab_bar, event)


def _tabs():
    tabs = QTabWidget()
    for name in ("a", "b", "c"):
        tabs.addTab(QWidget(), name)
    tabs.resize(300, 200)
    return tabs


def test_a_plain_tab_widget_switches_on_the_wheel(qapp):
    """前提の確認: 何もしなければ Qt はホイールでタブを移す。"""
    tabs = _tabs()
    _scroll(tabs.tabBar())
    assert tabs.currentIndex() == 1


def test_disabled_tab_widget_stays(qapp):
    tabs = _tabs()
    disable_wheel_tab_switching(tabs)
    _scroll(tabs.tabBar())
    assert tabs.currentIndex() == 0


def test_the_axis_tabs_do_not_switch_on_the_wheel(qapp):
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    tabs = window.ui.axis_tab_widget
    tabs.setCurrentIndex(0)

    _scroll(tabs.tabBar())

    assert tabs.currentIndex() == 0
    window.close()
