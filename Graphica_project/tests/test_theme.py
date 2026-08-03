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
from PySide6.QtGui import QPainter, QWheelEvent
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


class TestFlatThemeProxyStyle:
    """
    _FlatThemeProxyStyle (QProxyStyle) のテスト。

    共通の経緯: Qtは、あるサブコントロールにQSSで何かひとつでもプロパティ
    (padding/border-radius/widthだけでも) を指定すると、Qtがそのサブ
    コントロールを「スタイルシートでカスタム描画される」ものとみなし、
    アイコンやチェックマークなどの「中身」が一切描画されなくなることがある。
    これはタブの閉じるボタン(実機で「見にくい」と報告)と、チェックボックスの
    チェックマーク(実機で「塗りつぶしだけ」と報告)の両方で実際に発生した。
    そのため両方とも、該当のサブコントロールにはQSSを一切当てず、
    このQProxyStyleが見た目をすべて肩代わりする設計にしている。
    """

    def test_standard_icon_replaced_for_tab_close_button(self, qapp):
        base_style = QStyleFactory.create('Fusion')
        proxy = theme._FlatThemeProxyStyle(base_style, theme._LIGHT_TOKENS)

        icon = proxy.standardIcon(QStyle.StandardPixmap.SP_TabCloseButton)
        assert not icon.isNull()

    def test_standard_pixmap_replaced_for_tab_close_button(self, qapp):
        # QtのプライベートなCloseButtonウィジェットは、standardIcon()ではなく
        # standardPixmap()経由でアイコンを取得しているため、こちらも
        # オーバーライドされている必要がある
        base_style = QStyleFactory.create('Fusion')
        proxy = theme._FlatThemeProxyStyle(base_style, theme._LIGHT_TOKENS)

        pixmap = proxy.standardPixmap(QStyle.StandardPixmap.SP_TabCloseButton)
        assert not pixmap.isNull()

    def test_other_standard_icons_are_not_affected(self, qapp):
        # QProxyStyle(base_style) はbase_styleの所有権を引き継ぐため、
        # 比較用の「素のFusion」は別インスタンスとして用意する
        # (同じインスタンスをproxy構築後に直接触るとPySide側で無効化される)
        reference_style = QStyleFactory.create('Fusion')
        proxy = theme._FlatThemeProxyStyle(QStyleFactory.create('Fusion'), theme._LIGHT_TOKENS)

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

    def test_generated_qss_does_not_style_checkbox_indicator(self):
        # QCheckBox::indicator { ... } を指定するとチェックマークが描画され
        # なくなるため、こちらもQSSにプロパティ指定が含まれていないことを
        # 確認する。
        for dark in (False, True):
            qss = theme._build_flat_qss(dark)
            assert not re.search(r"QCheckBox::indicator[:\w]*\s*\{[^}]*\S[^}]*\}", qss)

    def test_draw_checkbox_indicator_does_not_raise_for_each_state(self, qapp):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QStyleOptionButton

        base_style = QStyleFactory.create('Fusion')
        proxy = theme._FlatThemeProxyStyle(base_style, theme._LIGHT_TOKENS)

        pixmap = QPixmap(20, 20)
        painter = QPainter(pixmap)
        try:
            for state in (
                QStyle.StateFlag.State_On | QStyle.StateFlag.State_Enabled,
                QStyle.StateFlag.State_Off | QStyle.StateFlag.State_Enabled,
                QStyle.StateFlag.State_NoChange | QStyle.StateFlag.State_Enabled,
                QStyle.StateFlag.State_On,  # disabled (State_Enabledなし)
            ):
                option = QStyleOptionButton()
                option.rect = QRect(2, 2, 14, 14)
                option.state = state
                proxy.drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox, option, painter)
        finally:
            painter.end()


class TestSpinboxArrowIcons:
    """
    gui/theme.py の _spinbox_arrow_icon_url() のテスト。

    経緯: QSpinBox::up-arrow/down-arrow はQSSでwidth/heightを指定するだけでも
    矢印が描画されなくなる(QSpinBox自体がQLineEdit等と共有の角丸入力欄QSSの
    対象になっているため)。QProxyStyle側でdrawPrimitive/drawComplexControlを
    オーバーライドしても、Qt内部のQStyleSheetStyleへの委譲が安定せず矢印が
    表示されたりされなかったりした。最終的に、矢印だけは実ファイルとして
    PNGを生成し、QSSの `image: url(...)` で確実に読み込む方式にした。
    """

    def test_arrow_icon_file_is_created_and_nonempty(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setattr(theme, "_ARROW_ICON_CACHE_DIR", str(tmp_path))

        url = theme._spinbox_arrow_icon_url("up", "#1B1F1E")

        assert url.startswith(str(tmp_path).replace("\\", "/"))
        # url()に渡す文字列にバックスラッシュが残っていないこと
        assert "\\" not in url

        from pathlib import Path
        generated_files = list(tmp_path.glob("*.png"))
        assert len(generated_files) == 1
        assert generated_files[0].stat().st_size > 0

    def test_arrow_icon_is_cached_not_regenerated(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setattr(theme, "_ARROW_ICON_CACHE_DIR", str(tmp_path))

        url1 = theme._spinbox_arrow_icon_url("down", "#1B1F1E")
        mtime1 = None
        for p in tmp_path.glob("*.png"):
            mtime1 = p.stat().st_mtime_ns

        url2 = theme._spinbox_arrow_icon_url("down", "#1B1F1E")
        mtime2 = None
        for p in tmp_path.glob("*.png"):
            mtime2 = p.stat().st_mtime_ns

        assert url1 == url2
        assert mtime1 == mtime2  # 再生成されていない

    def test_up_and_down_arrows_produce_different_files(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setattr(theme, "_ARROW_ICON_CACHE_DIR", str(tmp_path))

        up_url = theme._spinbox_arrow_icon_url("up", "#1B1F1E")
        down_url = theme._spinbox_arrow_icon_url("down", "#1B1F1E")

        assert up_url != down_url

    def test_generated_qss_references_arrow_image_urls(self):
        for dark in (False, True):
            qss = theme._build_flat_qss(dark)
            assert re.search(r"QSpinBox::up-arrow[^{]*\{[^}]*image:\s*url\(", qss)
            assert re.search(r"QSpinBox::down-arrow[^{]*\{[^}]*image:\s*url\(", qss)
