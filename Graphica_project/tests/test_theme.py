# tests/test_theme.py
"""
gui/theme.py の disable_scroll_value_change() のテスト。

QSpinBox/QDoubleSpinBox/QComboBoxは既定でマウスホイールにより値が変わって
しまうため、ホイール操作による値変更を常に無効化する挙動を検証する。
(フォーカスの有無で条件分岐する実装は一度試したが、QAbstractSpinBoxの既定の
フォーカスポリシーがWheelFocusであるため実際には効果がなく、無条件に
無効化する方式に変更した経緯がある)
"""
import re

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QMainWindow,
                               QStyle, QStyleFactory, QWidget, QVBoxLayout)

from gui import theme


def _make_wheel_event():
    return QWheelEvent(
        QPointF(1, 1), QPointF(1, 1), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_wheel_does_not_change_spinbox_value(qapp):
    theme.disable_scroll_value_change()

    spin = QDoubleSpinBox()
    spin.setValue(5.0)
    QApplication.sendEvent(spin, _make_wheel_event())

    assert spin.value() == 5.0


def test_wheel_does_not_change_value_even_when_focused(qapp):
    # フォーカスの有無に関わらず無効化されることを確認する。
    # (実際のフォームでは、直前に触っていた別のフィールドがフォーカスを
    #  保持したまま、ユーザーはマウスを動かしてスクロールするだけのことが
    #  多いため、フォーカスの有無では判定しない設計にしている)
    theme.disable_scroll_value_change()

    win = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    spin = QDoubleSpinBox()
    spin.setValue(5.0)
    layout.addWidget(spin)
    win.setCentralWidget(central)
    win.show()
    qapp.processEvents()

    assert spin.hasFocus()  # 唯一のフォーカス可能ウィジェットなので自動的にフォーカスされる
    QApplication.sendEvent(spin, _make_wheel_event())

    assert spin.value() == 5.0
    win.close()


def test_wheel_does_not_change_combobox_selection(qapp):
    theme.disable_scroll_value_change()

    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    combo.setCurrentIndex(0)
    QApplication.sendEvent(combo, _make_wheel_event())

    assert combo.currentIndex() == 0


def test_disable_scroll_value_change_is_idempotent(qapp):
    # 複数回呼び出してもwheelEventが二重にラップされない
    theme.disable_scroll_value_change()
    theme.disable_scroll_value_change()

    spin = QDoubleSpinBox()
    spin.setValue(1.0)
    QApplication.sendEvent(spin, _make_wheel_event())
    assert spin.value() == 1.0


class TestTabCloseIconStyle:
    """
    タブの「閉じる」ボタンのアイコンをTabler Icons "x" に差し替える
    _TabCloseIconStyle (QProxyStyle) のテスト。

    経緯: QTabBar::close-button にQSSで何かひとつでもプロパティ
    (paddingやborder-radiusだけでも) を指定すると、Qtがこのサブコントロールを
    「スタイルシートでカスタム描画される」ものとみなし、アイコン自体が
    一切描画されなくなる(実機で「タブを閉じるバツが見にくい」と報告され、
    調査したところ実際にはほぼ見えなくなっていた)。この回帰を防ぐため、
    (1) _TabCloseIconStyle 自体が正しくカスタムアイコンを返すこと、
    (2) 生成されるQSSにQTabBar::close-buttonへのプロパティ指定が
    含まれないこと、の両方を確認する。
    """

    def test_standard_icon_replaced_for_tab_close_button(self, qapp):
        base_style = QStyleFactory.create('Fusion')
        proxy = theme._TabCloseIconStyle(base_style, "#5B6462")

        icon = proxy.standardIcon(QStyle.StandardPixmap.SP_TabCloseButton)
        assert not icon.isNull()

    def test_standard_pixmap_replaced_for_tab_close_button(self, qapp):
        # QtのプライベートなCloseButtonウィジェットは、standardIcon()ではなく
        # standardPixmap()経由でアイコンを取得しているため、こちらも
        # オーバーライドされている必要がある
        base_style = QStyleFactory.create('Fusion')
        proxy = theme._TabCloseIconStyle(base_style, "#5B6462")

        pixmap = proxy.standardPixmap(QStyle.StandardPixmap.SP_TabCloseButton)
        assert not pixmap.isNull()

    def test_other_standard_icons_are_not_affected(self, qapp):
        # QProxyStyle(base_style) はbase_styleの所有権を引き継ぐため、
        # 比較用の「素のFusion」は別インスタンスとして用意する
        # (同じインスタンスをproxy構築後に直接触るとPySide側で無効化される)
        reference_style = QStyleFactory.create('Fusion')
        proxy = theme._TabCloseIconStyle(QStyleFactory.create('Fusion'), "#5B6462")

        # 他の標準アイコンには手を加えず、素のFusionと同じ結果になる
        icon = proxy.standardIcon(QStyle.StandardPixmap.SP_DialogOkButton)
        expected = reference_style.standardIcon(QStyle.StandardPixmap.SP_DialogOkButton)
        assert icon.isNull() == expected.isNull()

    def test_generated_qss_does_not_style_close_button_subcontrol(self):
        # QTabBar::close-button { ... } のようにプロパティを指定すると
        # アイコンが描画されなくなるため、このサブコントロールに対する
        # プロパティ指定がQSSに含まれていないことを確認する。
        for dark in (False, True):
            qss = theme._build_flat_qss(dark)
            assert not re.search(r"QTabBar::close-button\s*\{[^}]*\S[^}]*\}", qss)
