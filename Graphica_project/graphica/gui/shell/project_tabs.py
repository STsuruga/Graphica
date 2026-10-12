"""プロジェクトのタブ。タブの帯は上部バーに置き、中身(各タブの PlotterApp)はその下に重ねる。

QTabWidget は帯と中身を1つの部品に持つので、帯だけを上部バーへ移せない。今まで QTabWidget で使っていた呼び方
(addTab・removeTab・widget・indexOf・count・currentIndex・tabText など)はそのまま使える。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QStackedWidget, QTabBar, QVBoxLayout, QWidget


class ProjectTabs(QWidget):
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bar = QTabBar()
        self._bar.setObjectName("project_tab_bar")
        self._bar.setDrawBase(False)
        self._bar.setExpanding(False)
        self._bar.setElideMode(Qt.TextElideMode.ElideRight)
        self._bar.setUsesScrollButtons(True)
        self._bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self._bar.currentChanged.connect(self._on_bar_current_changed)
        self._bar.tabCloseRequested.connect(self.tabCloseRequested)
        self._bar.tabMoved.connect(self._on_tab_moved)

    def tabBar(self):
        return self._bar

    def _on_bar_current_changed(self, index):
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)
        self.currentChanged.emit(index)

    def _on_tab_moved(self, from_index, to_index):
        widget = self._stack.widget(from_index)
        self._stack.removeWidget(widget)
        self._stack.insertWidget(to_index, widget)
        self._stack.setCurrentIndex(self._bar.currentIndex())

    def addTab(self, widget, text):
        # 先に中身を足す(帯に足した時点で currentChanged が出て、その先が中身を引く)
        self._stack.addWidget(widget)
        return self._bar.addTab(text)

    def removeTab(self, index):
        if not 0 <= index < self._stack.count():
            return
        self._stack.removeWidget(self._stack.widget(index))
        self._bar.removeTab(index)

    def widget(self, index):
        return self._stack.widget(index)

    def indexOf(self, widget):
        return self._stack.indexOf(widget)

    def count(self):
        return self._bar.count()

    def currentIndex(self):
        return self._bar.currentIndex()

    def setCurrentIndex(self, index):
        self._bar.setCurrentIndex(index)

    def currentWidget(self):
        return self._stack.currentWidget()

    def setCurrentWidget(self, widget):
        index = self.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def tabText(self, index):
        return self._bar.tabText(index)

    def setTabText(self, index, text):
        self._bar.setTabText(index, text)

    def setTabsClosable(self, closable):
        self._bar.setTabsClosable(closable)

    def setMovable(self, movable):
        self._bar.setMovable(movable)
