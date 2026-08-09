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
from PySide6.QtGui import QColor, QPainter, QWheelEvent
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
        proxy = theme._FlatThemeProxyStyle(base_style, theme.LIGHT_TOKENS)

        icon = proxy.standardIcon(QStyle.StandardPixmap.SP_TabCloseButton)
        assert not icon.isNull()

    def test_standard_pixmap_replaced_for_tab_close_button(self, qapp):
        # QtのプライベートなCloseButtonウィジェットは、standardIcon()ではなく
        # standardPixmap()経由でアイコンを取得しているため、こちらも
        # オーバーライドされている必要がある
        base_style = QStyleFactory.create('Fusion')
        proxy = theme._FlatThemeProxyStyle(base_style, theme.LIGHT_TOKENS)

        pixmap = proxy.standardPixmap(QStyle.StandardPixmap.SP_TabCloseButton)
        assert not pixmap.isNull()

    def test_other_standard_icons_are_not_affected(self, qapp):
        # QProxyStyle(base_style) はbase_styleの所有権を引き継ぐため、
        # 比較用の「素のFusion」は別インスタンスとして用意する
        # (同じインスタンスをproxy構築後に直接触るとPySide側で無効化される)
        reference_style = QStyleFactory.create('Fusion')
        proxy = theme._FlatThemeProxyStyle(QStyleFactory.create('Fusion'), theme.LIGHT_TOKENS)

        # 他の標準アイコンには手を加えず、素のFusionと同じ結果になる
        icon = proxy.standardIcon(QStyle.StandardPixmap.SP_DialogOkButton)
        expected = reference_style.standardIcon(QStyle.StandardPixmap.SP_DialogOkButton)
        assert icon.isNull() == expected.isNull()

    def test_generated_qss_does_not_style_close_button_subcontrol(self):
        # QTabBar::close-button { ... } のようにプロパティを指定すると
        # アイコンが描画されなくなるため、このサブコントロールに対する
        # プロパティ指定がQSSに含まれていないことを確認する。
        for dark in (False, True):
            qss = theme.build_qss(theme.DARK_TOKENS if dark else theme.LIGHT_TOKENS)
            assert not re.search(r"QTabBar::close-button\s*\{[^}]*\S[^}]*\}", qss)

    def test_generated_qss_does_not_style_checkbox_indicator(self):
        # QCheckBox::indicator { ... } を指定するとチェックマークが描画され
        # なくなるため、こちらもQSSにプロパティ指定が含まれていないことを
        # 確認する。
        for dark in (False, True):
            qss = theme.build_qss(theme.DARK_TOKENS if dark else theme.LIGHT_TOKENS)
            assert not re.search(r"QCheckBox::indicator[:\w]*\s*\{[^}]*\S[^}]*\}", qss)

    def test_draw_checkbox_indicator_does_not_raise_for_each_state(self, qapp):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QStyleOptionButton

        base_style = QStyleFactory.create('Fusion')
        proxy = theme._FlatThemeProxyStyle(base_style, theme.LIGHT_TOKENS)

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
            qss = theme.build_qss(theme.DARK_TOKENS if dark else theme.LIGHT_TOKENS)
            assert re.search(r"QSpinBox::up-arrow[^{]*\{[^}]*image:\s*url\(", qss)
            assert re.search(r"QSpinBox::down-arrow[^{]*\{[^}]*image:\s*url\(", qss)


# --- デザイントークン(項目H-1) ---

_REQUIRED_TOKEN_KEYS = {
    "bg", "surface", "surface_2", "border", "border_strong",
    "text_primary", "text_secondary", "text_muted",
    "accent", "accent_soft", "accent_text",
}


def test_light_and_dark_tokens_are_public_and_have_required_keys():
    assert _REQUIRED_TOKEN_KEYS <= set(theme.LIGHT_TOKENS.keys())
    assert _REQUIRED_TOKEN_KEYS <= set(theme.DARK_TOKENS.keys())


def test_light_and_dark_tokens_are_a_single_definition_used_by_apply_theme(monkeypatch):
    """apply_theme()がLIGHT_TOKENS/DARK_TOKENSという単一の定義箇所を
    経由してQSSを生成していること(H-1完了条件)を、build_qss()に渡される
    実際の引数を捕捉して確認する。"""
    captured = []
    real_build_qss = theme.build_qss
    monkeypatch.setattr(theme, "build_qss", lambda tokens: captured.append(tokens) or real_build_qss(tokens))

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    theme.apply_theme(app, dark=False)
    theme.apply_theme(app, dark=True)

    assert captured[-2] is theme.LIGHT_TOKENS
    assert captured[-1] is theme.DARK_TOKENS


def test_build_qss_accepts_arbitrary_token_dict():
    """build_qss(tokens)はLIGHT_TOKENS/DARK_TOKENS以外の任意の辞書も
    受け付ける(ロードマップH-1で示されたシグネチャ通り)。"""
    custom_tokens = dict(theme.LIGHT_TOKENS)
    custom_tokens["accent"] = "#FF00FF"

    qss = theme.build_qss(custom_tokens)

    assert "#FF00FF" in qss


def test_build_qss_output_identical_for_light_and_dark_token_dicts_by_value():
    """同じ内容のトークン辞書を渡せば、常に同じQSSが生成される(決定的)。"""
    tokens_copy = dict(theme.LIGHT_TOKENS)
    assert theme.build_qss(theme.LIGHT_TOKENS) == theme.build_qss(tokens_copy)


# --- データセットリストの選択ハイライト(項目H-2-2) ---


def test_selection_highlight_token_present_in_both_themes():
    assert "selection_highlight" in theme.LIGHT_TOKENS
    assert "selection_highlight" in theme.DARK_TOKENS


def test_current_selection_highlight_qcolor_reflects_active_theme(qapp):
    # rgba(...)形式のQSS文字列はQColor(str)コンストラクタでは解釈できず、
    # 不透明の黒に無効フォールバックしてしまう(実機で確認)ため、
    # current_selection_highlight_qcolor()が正しくパースして有効な色を
    # 返すことを検証する。
    theme.apply_theme(qapp, dark=False)
    light_color = theme.current_selection_highlight_qcolor()
    assert light_color.isValid()
    assert (light_color.red(), light_color.green(), light_color.blue()) == (37, 99, 235)
    assert 0.0 < light_color.alphaF() < 1.0

    theme.apply_theme(qapp, dark=True)
    dark_color = theme.current_selection_highlight_qcolor()
    assert dark_color.isValid()
    assert (dark_color.red(), dark_color.green(), dark_color.blue()) == (59, 130, 246)
    assert 0.0 < dark_color.alphaF() < 1.0


def test_dataset_list_item_radius_is_a_positive_int():
    assert isinstance(theme.DATASET_LIST_ITEM_RADIUS, int)
    assert theme.DATASET_LIST_ITEM_RADIUS > 0


def test_generated_qss_removes_border_from_dataset_list_and_search_box():
    # データセットリストと検索ボックスは、それぞれ独立した箱のまま(統合はしない)、
    # 各箱自身の枠線だけを消す指定になっていることを確認する(実機フィードバック)。
    for dark in (False, True):
        qss = theme.build_qss(theme.DARK_TOKENS if dark else theme.LIGHT_TOKENS)
        assert re.search(r"QTreeWidget#dataset_list_widget\s*\{[^}]*border:\s*none[^}]*\}", qss)
        assert re.search(r"QLineEdit#dataset_search_edit\s*\{[^}]*border:\s*none[^}]*\}", qss)


def test_generated_qss_neutralizes_generic_item_selected_background_for_dataset_list():
    # 汎用の QTreeWidget::item:selected { background: accent_soft; } が
    # このリストの分岐(展開矢印)用インデント列に滲み出るのを打ち消すための
    # 上書き規則が存在することを確認する(実機フィードバックで発見した経緯)。
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QTreeWidget#dataset_list_widget::item:selected\s*\{[^}]*background:\s*transparent[^}]*\}", qss
    )


# --- ドック全般: 境界線・タイトルバー・フォーカス時の強調(項目H-2-3) ---


def test_generated_qss_gives_dock_widgets_border_and_rounded_corners():
    for dark in (False, True):
        qss = theme.build_qss(theme.DARK_TOKENS if dark else theme.LIGHT_TOKENS)
        assert re.search(r"QDockWidget\s*\{[^}]*border:\s*1px solid[^}]*border-radius:\s*8px[^}]*\}", qss)


def test_generated_qss_highlights_active_dock_with_accent_border():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(r'QDockWidget\[dockActive="true"\]\s*\{[^}]*border:\s*1px solid[^}]*\}', qss)


class TestDockFocusHighlight:
    """
    theme.install_dock_focus_highlight()のテスト。

    QDockWidget自体には「アクティブ」を示すQt標準の状態が無いため、
    QApplication.focusChangedを監視して動的プロパティdockActiveを
    付け外しする自前の仕組みになっている(gui/theme.pyの該当docstring参照)。
    複数タブ(main_app_window.py、各タブが完全に独立したウィンドウという
    設計方針)を想定し、他のウィンドウのドックには一切影響しないことも確認する。
    """

    def _make_window_with_dock(self, qapp):
        """
        ドック内のQLineEditと、ドックの外(ウィンドウ直下)のQLineEditを両方
        持つウィンドウを作る。install_dock_focus_highlight()は
        window.show()より前(実際のPlotterApp.__init__と同じ順序)に
        呼び出すこと: show()時にフォーカス可能な唯一のウィジェットへ自動的に
        フォーカスが当たるが、これを先にinstallしておかないと最初の
        focusChangedイベントを取りこぼす。
        """
        from PySide6.QtWidgets import QDockWidget, QLineEdit, QMainWindow, QWidget, QVBoxLayout

        window = QMainWindow()
        theme.install_dock_focus_highlight(window)

        dock = QDockWidget("テストドック", window)
        line_edit = QLineEdit(dock)
        dock.setWidget(line_edit)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        central = QWidget(window)
        central_layout = QVBoxLayout(central)
        outside_edit = QLineEdit(central)
        central_layout.addWidget(outside_edit)
        window.setCentralWidget(central)

        window.show()
        for _ in range(5):
            qapp.processEvents()
        return window, dock, line_edit, outside_edit

    def test_focusing_widget_inside_dock_sets_dock_active_property(self, qapp):
        window, dock, line_edit, outside_edit = self._make_window_with_dock(qapp)

        line_edit.setFocus()
        for _ in range(5):
            qapp.processEvents()

        assert dock.property("dockActive") is True
        window.close()

    def test_focus_leaving_dock_clears_active_property(self, qapp):
        window, dock, line_edit, outside_edit = self._make_window_with_dock(qapp)

        line_edit.setFocus()
        for _ in range(5):
            qapp.processEvents()
        outside_edit.setFocus()
        for _ in range(5):
            qapp.processEvents()

        assert dock.property("dockActive") is False
        window.close()

    def test_focus_in_a_different_window_does_not_activate_this_windows_dock(self, qapp):
        window_a, dock_a, edit_a, _ = self._make_window_with_dock(qapp)
        window_b, dock_b, edit_b, _ = self._make_window_with_dock(qapp)

        edit_b.setFocus()
        for _ in range(5):
            qapp.processEvents()

        assert dock_b.property("dockActive") is True
        assert dock_a.property("dockActive") in (None, False)
        window_a.close()
        window_b.close()

    def test_window_destroyed_disconnects_focus_handler_without_raising(self, qapp):
        from PySide6.QtWidgets import QLineEdit

        window, dock, line_edit, outside_edit = self._make_window_with_dock(qapp)
        window.close()
        window.deleteLater()
        for _ in range(5):
            qapp.processEvents()

        # ハンドラがdisconnectされていれば、以降のフォーカス変化で例外は出ない
        other_edit = QLineEdit()
        other_edit.show()
        other_edit.setFocus()
        for _ in range(5):
            qapp.processEvents()
        other_edit.close()


# --- 選択色をデータセットリストに揃える(項目H-2-4、実機フィードバック:
#     「選択時とかポップアップとか色が緑だからデータセットリストの方に
#     色合わせて」) ---

def test_generated_qss_uses_selection_highlight_for_text_selection():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QWidget\s*\{[^}]*selection-background-color:\s*\{?selection_highlight\}?", qss
    ) or "selection-background-color: rgba(37, 99, 235, 0.12)" in qss


def test_generated_qss_uses_selection_highlight_for_menu_and_menubar():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QMenuBar::item:selected\s*\{[^}]*background:\s*rgba\(37, 99, 235, 0\.12\)", qss
    )
    assert re.search(
        r"QMenu::item:selected\s*\{[^}]*background:\s*rgba\(37, 99, 235, 0\.12\)", qss
    )


def test_generated_qss_uses_selection_highlight_for_combobox_popup():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QComboBox QAbstractItemView\s*\{[^}]*selection-background-color:\s*rgba\(37, 99, 235, 0\.12\)",
        qss,
    )


def test_generated_qss_uses_selection_highlight_for_generic_lists():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QTreeWidget::item:selected,\s*QListWidget::item:selected,\s*"
        r"QTableWidget::item:selected\s*\{[^}]*background:\s*rgba\(37, 99, 235, 0\.12\)",
        qss,
    )


def test_generated_qss_does_not_use_teal_accent_for_any_selection_state():
    # 「緑っぽい」の原因だったティール系accent/accent_softが、選択系の
    # プロパティ(selection-background-color、::item:selected、
    # ::item(menu/menubar):selectedのbackground)にもう使われていないことを
    # 回帰的に確認する。
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert "selection-background-color: #1F6F78" not in qss
    assert "selection-background-color: #E4F0EF" not in qss


# --- selection_accent(opaqueな青、H-2-4の追加フィードバック): 「フォーカス時
#     の色が緑のまま」「チェックボックスの塗りつぶしの色も」「タブの選択色も」 ---


def test_selection_accent_token_present_and_opaque_in_both_themes():
    for tokens in (theme.LIGHT_TOKENS, theme.DARK_TOKENS):
        assert "selection_accent" in tokens
        color = QColor(tokens["selection_accent"])
        assert color.isValid()
        assert color.alpha() == 255  # opaque(枠線・塗りつぶし用途のため透過なし)


def test_generated_qss_uses_selection_accent_for_focus_borders():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QPushButton:focus,\s*QToolButton:focus\s*\{[^}]*border:\s*1px solid #2563EB", qss
    )
    assert re.search(
        r"QComboBox:focus,\s*QTextEdit:focus,\s*QPlainTextEdit:focus\s*\{[^}]*"
        r"border-color:\s*#2563EB",
        qss,
    )


def test_generated_qss_uses_selection_accent_for_dock_focus_highlight():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(r'QDockWidget\[dockActive="true"\]\s*\{[^}]*border:\s*1px solid #2563EB', qss)


def test_generated_qss_uses_selection_accent_for_selected_tab():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QTabBar::tab:selected\s*\{[^}]*border-bottom:\s*2px solid #2563EB[^}]*color:\s*#2563EB",
        qss,
    )


def test_generated_qss_uses_selection_accent_for_checked_radio_button():
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QRadioButton::indicator:checked\s*\{[^}]*background:\s*#2563EB[^}]*border-color:\s*#2563EB",
        qss,
    )


def test_checkbox_indicator_checked_fill_uses_selection_accent(qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QStyleOptionButton

    base_style = QStyleFactory.create('Fusion')
    proxy = theme._FlatThemeProxyStyle(base_style, theme.LIGHT_TOKENS)

    pixmap = QPixmap(20, 20)
    pixmap.fill(QColor("white"))
    painter = QPainter(pixmap)
    try:
        option = QStyleOptionButton()
        option.rect = QRect(2, 2, 14, 14)
        option.state = QStyle.StateFlag.State_On | QStyle.StateFlag.State_Enabled
        proxy.drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox, option, painter)
    finally:
        painter.end()

    # (4, 4) はチェックマーク(レ点)のパスから離れた塗りつぶし部分のみの座標
    # (中心付近はチェックマークのストロークと重なりアンチエイリアスで色が
    # 混ざるため避ける)。
    fill_color = pixmap.toImage().pixelColor(4, 4)
    expected = QColor(theme.LIGHT_TOKENS["selection_accent"])
    assert (fill_color.red(), fill_color.green(), fill_color.blue()) == (
        expected.red(), expected.green(), expected.blue(),
    )


def test_generated_qss_gives_dock_widget_a_background(qapp):
    """
    実機フィードバック「プロパティウィンドウの背景色がそのまま」の回帰テスト。
    QDockWidgetに{bg}の明示的なbackgroundが無いと、OSネイティブのパレット
    既定色が透けて見えてしまう(bg/surface_2トークンを変更しても無反映になる)。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"^QDockWidget\s*\{[^}]*background:\s*#F6F7F9", qss, re.MULTILINE
    )


def test_generated_qss_uses_selection_accent_for_button_hover_border():
    """
    実機フィードバック「フォーカス時は青になっているのに、マウスを合わせた
    ときの色が緑のまま」の回帰テスト。:hoverのborder-colorが:focusと同じ
    selection_accentを使っていることを確認する。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QPushButton:hover\s*\{[^}]*border-color:\s*#2563EB", qss
    )


def test_generated_qss_gives_scroll_area_and_its_content_widget_a_background():
    """
    実機フィードバック「プロパティウィンドウの背景色が他と違う」の回帰テスト
    (QDockWidgetにbackgroundを追加した後も再発した、その2回目の修正)。

    実測(widgetAt()での特定+QWidget.grab()での分離検証)の結果、QScrollArea
    自体やそのビューポート(QScrollArea直下の子QWidget)にbackgroundを
    指定しただけでは不十分で、setWidget()で入れている中身のwidget
    (QScrollArea直下の"孫"QWidget)がアプリ全体QSSの副作用でOSネイティブの
    パレットWindowロール色を不透明に描画してしまい、これが実際に見えている
    色だったと判明した。QScrollArea・その子・その孫の3階層すべてに{bg}が
    指定されていることを確認する。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(r"^QScrollArea\s*\{[^}]*background:\s*#F6F7F9", qss, re.MULTILINE)
    assert re.search(r"QScrollArea > QWidget\s*\{[^}]*background:\s*#F6F7F9", qss)
    assert re.search(r"QScrollArea > QWidget > QWidget\s*\{[^}]*background:\s*#F6F7F9", qss)


def test_generated_qss_uses_selection_highlight_for_button_pressed_background():
    """
    実機フィードバック「フォント選択/色選択ボタンのクリックした瞬間の色が
    緑のまま」の回帰テスト。:hover/:focusの枠線は既に青系に揃えていたが、
    :pressedの背景だけティール系accent_softのまま取り残されていた。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QPushButton:pressed\s*\{[^}]*background:\s*rgba\(37, 99, 235", qss
    )


def test_generated_qss_uses_selection_colors_for_toolbutton_pressed_and_checked():
    """
    項目H-2-5(クイックアクセスツールバーの実機確認で発覚)の回帰テスト。
    QPushButton側は:pressed/:hoverとも青系へ統一済みだったが、QToolButton側
    (ツールバーの全ボタンはQToolButton)は同じ更新が漏れており、クイック
    アクセスに登録したボタンを押すと依然ティール系accent_softの緑っぽい色に
    なっていた。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QToolButton:pressed\s*\{[^}]*background:\s*rgba\(37, 99, 235", qss
    )
    assert re.search(
        r"QToolButton:checked\s*\{[^}]*background:\s*rgba\(37, 99, 235[^}]*"
        r"border:\s*1px solid #2563EB",
        qss,
    )


def test_generated_qss_uses_selection_accent_for_default_button():
    """
    実機フィードバック(画像提示、複数のポップアップダイアログ: バッチ
    エクスポートの「実行」、環境設定/フォント選択/色選択/メッセージボックス
    の「OK」、ヘルプの「Close」)の回帰テスト。ダイアログの既定ボタン
    (Enterキーで実行される、QDialogButtonBoxが自動的にdefaultにする
    ボタン)は他の全ての強調表現と揃っていなかった唯一の箇所で、ティール系
    accentのまま残っていた。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    assert re.search(
        r"QPushButton:default\s*\{[^}]*background:\s*#2563EB[^}]*"
        r"border-color:\s*#2563EB",
        qss,
    )
    assert "background: #1F6F78;" not in re.search(
        r"QPushButton:default\s*\{[^}]*\}", qss
    ).group(0)


def test_generated_qss_uses_selection_colors_for_groupbox_title_chip():
    """
    実機フィードバック(画像提示、環境設定/フォント選択ダイアログ)の回帰
    テスト:「外観/言語/保存...やEffect/Sampleのチップの色が緑」。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    match = re.search(r"^QGroupBox::title\s*\{([^}]*)\}", qss, re.MULTILINE)
    assert match, "QGroupBox::title のルールが見つかりません"
    body = match.group(1)
    assert "#2563EB" in body  # color: selection_accent
    assert "rgba(37, 99, 235" in body  # background: selection_highlight
    assert "#1F6F78" not in body
    assert "#E4F0EF" not in body


def test_generated_qss_groupbox_title_chip_does_not_overflow_above_border():
    """
    バグ回帰テスト:「外観/言語/保存...やEffect/Sampleのチップが見切れてる」。
    以前は`top: -6px`でグループボックスの外枠より上に突き出す配置にしており、
    自前で構築するダイアログでは問題なかったが、QFontDialog/QColorDialogの
    ようなQt標準ダイアログ(内部レイアウトを直接制御できない)では、この
    突き出し分の外側の余白が確保されずチップの上端が見切れていた(実機の
    スクリーンショットで確認済み)。外枠の外へ一切はみ出さない0px以上に
    することを確認する(周囲のレイアウト側の余白に依存しない安全な配置)。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    match = re.search(r"^QGroupBox::title\s*\{([^}]*)\}", qss, re.MULTILINE)
    assert match
    # ブロック内のコメント(実装経緯の説明文に"top: -6px"という過去の値への
    # 言及が含まれる)を取り除いてから実際のCSSプロパティ値を検証する
    # (コメントの地の文を誤ってマッチしないようにするため)。
    body_without_comments = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.DOTALL)
    top_matches = re.findall(r"top:\s*(-?\d+)px", body_without_comments)
    assert top_matches, "QGroupBox::title に top プロパティが見つかりません"
    assert all(int(value) >= 0 for value in top_matches)


def test_current_tokens_returns_light_tokens_by_default(qapp, monkeypatch):
    monkeypatch.setattr(theme, "_current_tokens", None)
    assert theme.current_tokens() == theme.LIGHT_TOKENS


def test_current_tokens_reflects_active_theme(qapp):
    app = QApplication.instance()
    theme.apply_theme(app, dark=True)
    try:
        assert theme.current_tokens() == theme.DARK_TOKENS
    finally:
        theme.apply_theme(app, dark=False)
    assert theme.current_tokens() == theme.LIGHT_TOKENS


class TestArrowIconSizesMatch:
    """
    スピンボックスとコンボボックスの矢印マークのサイズが揃っていることを
    確認する回帰テスト(実機フィードバック: 「コンボボックスとスピンボックスで
    マークの大きさそろってる?」で発覚した、コンボボックス側だけ旧サイズの
    ままだった不具合の再発防止)。
    """

    @staticmethod
    def _extract_arrow_size(qss, selector):
        match = re.search(
            re.escape(selector) + r"\s*\{[^}]*width:\s*(\d+)px;\s*height:\s*(\d+)px;", qss
        )
        assert match, f"{selector} の矢印サイズが見つかりません"
        return int(match.group(1)), int(match.group(2))

    def test_combobox_and_spinbox_arrow_sizes_are_identical(self):
        qss = theme.build_qss(theme.LIGHT_TOKENS)
        spin_up = self._extract_arrow_size(qss, "QSpinBox::up-arrow, QDoubleSpinBox::up-arrow")
        spin_down = self._extract_arrow_size(qss, "QSpinBox::down-arrow, QDoubleSpinBox::down-arrow")
        combo_down = self._extract_arrow_size(qss, "QComboBox::down-arrow")

        assert spin_up == spin_down == combo_down


def test_generated_qss_removes_border_from_plot_container():
    """
    実機フィードバック「プロットパネルの枠線も消して」の回帰テスト。
    背景・角丸は維持しつつborderプロパティが無いことを確認する。
    """
    qss = theme.build_qss(theme.LIGHT_TOKENS)
    match = re.search(r"QWidget#plot_container\s*\{([^}]*)\}", qss)
    assert match, "QWidget#plot_container のルールが見つかりません"
    body = match.group(1)
    assert "border:" not in body
    assert "background:" in body
    assert "border-radius:" in body


def test_flat_theme_proxy_style_suppresses_tab_bar_base_frame(qapp):
    """
    実機フィードバック(画像提示)「プロパティ/エクスポートプレビュー」タブ
    (タブ化したQDockWidget)の上に出ていた灰色の横線の回帰テスト。
    QTabBar::tab等のQSSでは制御できないPE_FrameTabBarBaseプリミティブを
    _FlatThemeProxyStyle.drawPrimitive()で抑制していることを確認する。
    """
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QStyleOptionTabBarBase

    base_style = QStyleFactory.create('Fusion')
    base_style.drawPrimitive = MagicMock()
    proxy = theme._FlatThemeProxyStyle(base_style, theme.LIGHT_TOKENS)

    option = QStyleOptionTabBarBase()
    painter = QPainter()
    proxy.drawPrimitive(QStyle.PrimitiveElement.PE_FrameTabBarBase, option, painter, None)

    base_style.drawPrimitive.assert_not_called()
