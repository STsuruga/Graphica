"""画面の短い動き(タブの切り替え・節の開閉・セグメントの板・下のパネル・ポップアップ)。

環境設定の「画面の動き」(app_settings.ANIMATIONS)で止められる。画面の無い環境(offscreen: テストと
特性テスト)では常に止め、どの部品もすぐ最後の状態になる(記録が時間で揺れないように)。
"""
import shiboken6
from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QRect, Qt, QTimer, QVariantAnimation
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QWidget

# ms。短いほど「待たされる」感じが出ない。開閉のように大きく動くものだけ少し長く
FADE_MS = 140
EXPAND_MS = 170
SLIDE_MS = 160
POPUP_MS = 110
EASING = QEasingCurve.Type.OutCubic
# Qt の QWIDGETSIZE_MAX。開き終わった節の高さの上限を外すのに使う
UNBOUNDED_HEIGHT = 16777215

_enabled = True


def set_enabled(enabled):
    """止めたり戻したりする。メニュー(★ や右クリック)とツールチップは Qt のふわっと出す効果をそろえて切り替える。"""
    global _enabled
    _enabled = bool(enabled)
    app = QApplication.instance()
    if app is None:
        return
    on = is_enabled()
    for effect in (Qt.UIEffect.UI_AnimateMenu, Qt.UIEffect.UI_FadeMenu, Qt.UIEffect.UI_AnimateTooltip,
                   Qt.UIEffect.UI_FadeTooltip):
        QApplication.setEffectEnabled(effect, on)


def is_enabled():
    app = QApplication.instance()
    return _enabled and app is not None and app.platformName() != "offscreen"


def _keep(owner, name, animation):
    """動きの途中で GC されないよう持ち主に持たせる。同じ名前の前の動きは止める。"""
    previous = getattr(owner, name, None)
    # 前のものは終わったときに Qt 側で消えていることがある(重ね絵は消し終わると deleteLater する)
    if previous is not None and shiboken6.isValid(previous):
        if hasattr(previous, "stop"):
            previous.stop()
        elif isinstance(previous, QWidget):
            previous.deleteLater()
    setattr(owner, name, animation)
    return animation


def crossfade(container, old_pixmap, duration=FADE_MS):
    """切り替える前の絵(old_pixmap)を container の上に重ね、それを消していく。

    新しいページは最初からふつうに描かれる。ページそのものを半透明にすると、後ろに前のページの絵が残って見える。
    """
    if not is_enabled() or container is None or old_pixmap is None or old_pixmap.isNull():
        return
    overlay = QLabel(container)
    overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    overlay.setPixmap(old_pixmap)
    overlay.setScaledContents(True)
    overlay.setGeometry(container.rect())
    effect = QGraphicsOpacityEffect(overlay)
    effect.setOpacity(1.0)
    overlay.setGraphicsEffect(effect)
    overlay.show()
    overlay.raise_()
    animation = QPropertyAnimation(effect, b"opacity", overlay)
    animation.setDuration(duration)
    animation.setStartValue(1.0)
    animation.setEndValue(0.0)
    animation.setEasingCurve(EASING)
    animation.finished.connect(overlay.deleteLater)
    _keep(container, "_motion_crossfade_overlay", overlay)
    animation.start()


def grab(widget):
    """クロスフェードに使う今の絵。動きが止まっていれば撮らない(撮るのにも少し時間がかかる)。"""
    if not is_enabled() or widget is None or not widget.isVisible():
        return None
    return widget.grab()


def fade_in(widget, duration=FADE_MS):
    """widget を透明からふわっと出す。終わったら効果を外す(効果を付けたままだと描画が遅くなる)。"""
    if not is_enabled() or widget is None:
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(EASING)

    def finish():
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)

    animation.finished.connect(finish)
    _keep(widget, "_motion_fade", animation).start()


def fade_in_window(window, duration=POPUP_MS):
    """ポップアップ(別の窓)を透明から出す。"""
    if not is_enabled() or window is None:
        return
    animation = QPropertyAnimation(window, b"windowOpacity", window)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(EASING)
    window.setWindowOpacity(0.0)
    _keep(window, "_motion_window_fade", animation).start()


def animate_value(owner, name, start, end, on_value, on_finished=None, duration=SLIDE_MS):
    """start から end へ値を動かし、途中の値を on_value に渡す。動きが止まっていればすぐ end を渡す。"""
    if not is_enabled() or start == end:
        on_value(end)
        if on_finished is not None:
            on_finished()
        return None
    animation = QVariantAnimation(owner)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(EASING)
    animation.valueChanged.connect(on_value)
    if on_finished is not None:
        animation.finished.connect(on_finished)
    _keep(owner, name, animation).start()
    return animation


def stop(owner, name):
    animation = getattr(owner, name, None)
    if animation is not None and shiboken6.isValid(animation):
        animation.stop()


def running(owner, name):
    animation = getattr(owner, name, None)
    return (animation is not None and shiboken6.isValid(animation)
            and animation.state() == QVariantAnimation.State.Running)


class TabIndicator(QWidget):
    """下線のタブの、選んだタブの下の線。タブを替えると横に滑る(QSS の選んだタブの下線は消しておく)。"""

    HEIGHT = 2

    def __init__(self, tab_bar):
        super().__init__(tab_bar)
        self.setObjectName("tab_indicator")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._tab_bar = tab_bar
        tab_bar.setProperty("slidingIndicator", True)
        tab_bar.style().unpolish(tab_bar)
        tab_bar.style().polish(tab_bar)
        tab_bar.currentChanged.connect(lambda _index: self.follow(animate=True))
        tab_bar.installEventFilter(self)
        self.follow(animate=False)

    def _target(self):
        index = self._tab_bar.currentIndex()
        if index < 0:
            return None
        rect = self._tab_bar.tabRect(index)
        return QRect(rect.left(), rect.bottom() - self.HEIGHT + 1, rect.width(), self.HEIGHT)

    def follow(self, animate):
        target = self._target()
        if target is None or target.width() <= 0:
            self.hide()
            return
        self.show()
        self.raise_()
        start = self.geometry()
        if animate and self.isVisible() and start.width() > 0 and start != target:
            # 滑っている間にタブの幅が決まり直すこともあるので、止まったら今の行き先に合わせ直す
            animate_value(self, "_motion_slide", start, target, self.setGeometry,
                          lambda: self.follow(animate=False), duration=SLIDE_MS)
        else:
            stop(self, "_motion_slide")
            self.setGeometry(target)

    def eventFilter(self, watched, event):
        if watched is self._tab_bar and event.type() in (QEvent.Type.Resize, QEvent.Type.Show,
                                                          QEvent.Type.LayoutRequest, QEvent.Type.StyleChange):
            # タブの幅は表示されてから決まる。動いている途中でなければ行き先へ合わせる
            if not running(self, "_motion_slide"):
                QTimer.singleShot(0, lambda: self.follow(animate=False))
        return super().eventFilter(watched, event)


class _SwitchMotion(QObject):
    """スイッチのつまみを滑らせる。描くのはスタイル(theme._draw_toggle_switch)で、途中の位置を property で渡す。

    束ねの復元はシグナルを止めて setChecked するので、そのときは動かさない(property は動いている間だけ置く)。
    """

    def __init__(self, checkbox):
        super().__init__(checkbox)
        self._checkbox = checkbox
        self._shown = 1.0 if checkbox.isChecked() else 0.0
        checkbox.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        target = 1.0 if checked else 0.0
        checkbox = self._checkbox
        if not (is_enabled() and checkbox.isVisible()):
            self._shown = target
            return
        start = checkbox.property(SWITCH_PROGRESS_PROPERTY)
        start = self._shown if start is None else float(start)

        def step(value):
            self._shown = float(value)
            checkbox.setProperty(SWITCH_PROGRESS_PROPERTY, float(value))
            checkbox.update()

        def finish():
            checkbox.setProperty(SWITCH_PROGRESS_PROPERTY, None)
            checkbox.update()

        checkbox.setProperty(SWITCH_PROGRESS_PROPERTY, start)
        animate_value(self, "_motion_switch", start, target, step, finish, SLIDE_MS)


# スイッチのつまみの途中の位置(0 = オフ、1 = オン)。動いている間だけ置く
SWITCH_PROGRESS_PROPERTY = "switchProgress"


def attach_switch_motion(checkbox):
    if getattr(checkbox, "_switch_motion", None) is None:
        checkbox._switch_motion = _SwitchMotion(checkbox)


class Toast(QLabel):
    """ウィンドウの右下に短い知らせ(「保存しました」など)をふわっと出して、少したったら消す。"""

    SHOW_MS = 1800
    MARGIN = 18

    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text):
        self.setText(text)
        self.adjustSize()
        window = self.parentWidget()
        bottom_margin = self.MARGIN + 24  # ステータスバーの上
        self.move(window.width() - self.width() - self.MARGIN, window.height() - self.height() - bottom_margin)
        self.show()
        self.raise_()
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        if is_enabled():
            animate_value(self, "_motion_toast", 0.0, 1.0, effect.setOpacity, duration=FADE_MS)
        else:
            effect.setOpacity(1.0)
        self._timer.start(self.SHOW_MS)

    def _fade_out(self):
        effect = self.graphicsEffect()
        if effect is None or not is_enabled():
            self.hide()
            return
        animate_value(self, "_motion_toast", 1.0, 0.0, effect.setOpacity, self.hide, FADE_MS * 2)


def toast(widget, text):
    """widget のウィンドウの右下に知らせを出す(ステータスバーの表示はそのまま)。"""
    window = widget.window() if widget is not None else None
    if window is None:
        return
    box = getattr(window, "_toast", None)
    if box is None:
        box = Toast(window)
        window._toast = box
    box.show_message(text)
