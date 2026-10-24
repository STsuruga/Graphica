"""画面の短い動き(タブの切り替え・節の開閉・セグメントの板・下のパネル・ポップアップ)。

環境設定の「画面の動き」(app_settings.ANIMATIONS)で止められる。画面の無い環境(offscreen: テストと
特性テスト)では常に止め、どの部品もすぐ最後の状態になる(記録が時間で揺れないように)。
"""
import shiboken6
from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QPalette, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QScrollArea, QVBoxLayout, QWidget

# ms。短いほど「待たされる」感じが出ない。開閉のように大きく動くものだけ少し長く
FADE_MS = 140
EXPAND_MS = 220
SLIDE_MS = 160
POPUP_MS = 110
EASING = QEasingCurve.Type.OutCubic
# 高さのように大きく動くものは、ゆっくり動き出して途中で速く、ゆっくり止める。
# 始めが一番速い OutCubic だと、最初の1コマで大きく飛んでガクッと見える
EXPAND_EASING = QEasingCurve.Type.InOutCubic
# 1コマの中でレイアウトの知らせを片付ける回数(入れ子の深さぶん。知らせが無ければすぐ終わる)
LAYOUT_FLUSH_PASSES = 4
# Qt の QWIDGETSIZE_MAX。開き終わった節の高さの上限を外すのに使う
UNBOUNDED_HEIGHT = 16777215

_enabled = True
# 動いている(動き出す前も含む)ものの一覧。テストが「全部止まるまで待つ」のに使う
_active = set()


def busy():
    """動いている途中か、動き出しを待っているものがあるか。"""
    for animation in list(_active):
        if not shiboken6.isValid(animation):
            _active.discard(animation)
    return bool(_active)


def _track(animation):
    _active.add(animation)
    animation.finished.connect(lambda: _active.discard(animation))
    animation.destroyed.connect(lambda *_args: _active.discard(animation))
    return animation


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
            _active.discard(previous)
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
    # 引き伸ばさず撮ったときの大きさのまま重ねる(ページの高さが違うと、絵がゆがんでちらついて見える)
    ratio = old_pixmap.devicePixelRatio() or 1.0
    overlay.setGeometry(QRect(0, 0, round(old_pixmap.width() / ratio), round(old_pixmap.height() / ratio)))
    effect = QGraphicsOpacityEffect(overlay)
    effect.setOpacity(1.0)
    overlay.setGraphicsEffect(effect)
    overlay.show()
    overlay.raise_()
    animation = _track(QPropertyAnimation(effect, b"opacity", overlay))
    animation.setDuration(duration)
    animation.setStartValue(1.0)
    animation.setEndValue(0.0)
    animation.setEasingCurve(EASING)
    animation.finished.connect(overlay.deleteLater)
    _keep(container, "_motion_crossfade_overlay", overlay)
    # 新しいページを初めて描くのは重いので、描き終わってから消し始める
    QTimer.singleShot(0, lambda: animation.start() if shiboken6.isValid(animation) else None)


class SectionClip(QWidget):
    """節の中身(body)を入れる外枠。開閉の間だけ高さを動かし、はみ出した中身は切って見せる。

    中身は動いている間、本来の高さに固定する(外枠と一緒に縮めると、中の行が毎回詰め直されて揺れる)。
    """

    def __init__(self, body, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(body, 0, Qt.AlignmentFlag.AlignTop)
        self.body = body


def _fit_scroll_content(widget):
    """widget の入ったスクロールの中身を、今の高さに合わせてすぐ広げる・縮める。

    外枠を高くしたとき、中身の入れ物は次のレイアウトの回まで前の高さのままなので、その間はほかの節が
    押し縮められ(上の節が数 px 動いて戻る)、1コマごとに揺れて見える。同じ回のうちに入れ物の高さを合わせる。
    """
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    if parent is None or not parent.widgetResizable() or parent.widget() is None:
        return
    content = parent.widget()
    # 外枠から中身の入れ物まで、途中の入れ物の覚えている大きさを全部捨てる。
    # 1段ずつ知らせが上がるのを待つと、その途中の回で、前の高さの入れ物の中の節が押し縮められる
    ancestor = widget
    while ancestor is not None:
        if ancestor.layout() is not None:
            ancestor.layout().invalidate()
        if ancestor is content:
            break
        ancestor = ancestor.parentWidget()
    width = content.width()
    hint = content.heightForWidth(width) if content.hasHeightForWidth() else -1
    if hint <= 0:
        hint = content.sizeHint().height()
    height = max(parent.viewport().height(), hint)
    if content.height() != height:
        content.resize(width, height)
    elif content.layout() is not None:
        content.layout().activate()
    # まだ順番待ちのレイアウトの知らせ(下の節を動かすものなど)も、次に描く前に済ませる
    for _ in range(LAYOUT_FLUSH_PASSES):
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)


def freeze_for_close(clip, keep_picture=True):
    """閉じ始める瞬間の中身を、閉じ終わるまでそのまま見せる(同じ知らせで中の行が消える節があるため)。

    スイッチでオフにした節(グラデーションなど)は、オフの知らせで中の行が先に消え、中身が空になる。
    そのまま縮めると、行が一気に消えて跳ねて見える。行が消える前に高さを止め、中身の絵をかぶせる。
    何度呼んでも同じ(閉じている途中なら何もしない)。keep_picture=False は高さを止めるだけ
    (見出しを押して閉じるときは中の行が変わらないので、絵を撮る時間を省く)。
    """
    body = clip.body
    if clip.isHidden() or getattr(clip, "_close_picture", None) is not None or running(clip, "_motion_expand"):
        return
    if not keep_picture:
        body.setFixedHeight(body.height())
        clip.setFixedHeight(clip.height())
        return
    picture = QLabel(clip)
    picture.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    picture.setPixmap(_picture(body))
    picture.setGeometry(body.geometry())
    picture.show()
    picture.raise_()
    clip._close_picture = picture
    body.setFixedHeight(body.height())
    clip.setFixedHeight(clip.height())


def _drop_close_picture(clip):
    picture = getattr(clip, "_close_picture", None)
    clip._close_picture = None
    if picture is not None and shiboken6.isValid(picture):
        picture.deleteLater()


def _natural_height(clip):
    """中の行が折り返す節は高さが幅で決まる(sizeHint を使うと、止まった後に 1px 揺れる)。"""
    body = clip.body
    width = clip.width() or body.width()
    natural = body.heightForWidth(width) if body.hasHeightForWidth() and width > 0 else -1
    return max(1, natural if natural > 0 else body.sizeHint().height())


def animate_section(clip, opening):
    """clip(SectionClip)を開く・閉じる。中身は本来の高さに止めたまま、外枠の高さだけを動かす。

    途中で逆に押されたら、今の高さから続ける。
    """
    body = clip.body
    moving = running(clip, "_motion_expand")
    if opening:
        _drop_close_picture(clip)
        body.setVisible(True)
        clip.setVisible(True)
        body.setMinimumHeight(0)
        body.setMaximumHeight(UNBOUNDED_HEIGHT)
        full = _natural_height(clip)
        start, end = (clip.height() if moving else 0), full
        body.setFixedHeight(full)
    else:
        freeze_for_close(clip, keep_picture=False)
        start, end = clip.height(), 0
    clip.setFixedHeight(start)
    _fit_scroll_content(clip)

    def step(value):
        clip.setFixedHeight(round(value))
        _fit_scroll_content(clip)

    def finish():
        _drop_close_picture(clip)
        body.setMinimumHeight(0)
        body.setMaximumHeight(UNBOUNDED_HEIGHT)
        clip.setMinimumHeight(0)
        clip.setMaximumHeight(UNBOUNDED_HEIGHT)
        body.setVisible(opening)
        clip.setVisible(opening)
        _fit_scroll_content(clip)

    animate_value(clip, "_motion_expand", start, end, step, finish, EXPAND_MS, EXPAND_EASING)


def grab(widget):
    """クロスフェードに使う今の絵。動きが止まっていれば撮らない(撮るのにも少し時間がかかる)。

    widget.grab() は後ろを窓の地の色(灰色)で塗ってから撮るので、白い面の上に重ねると一瞬灰色に見える。
    面の色(パレットの Base = surface)で塗ってから中身だけを描く。
    """
    if not is_enabled() or widget is None or not widget.isVisible():
        return None
    return _picture(widget)


def _picture(widget):
    ratio = widget.devicePixelRatioF()
    picture = QPixmap(round(widget.width() * ratio), round(widget.height() * ratio))
    picture.setDevicePixelRatio(ratio)
    picture.fill(widget.palette().color(QPalette.ColorRole.Base))
    widget.render(picture, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return picture


def fade_in(widget, duration=FADE_MS):
    """widget を透明からふわっと出す。終わったら効果を外す(効果を付けたままだと描画が遅くなる)。"""
    if not is_enabled() or widget is None:
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    animation = _track(QPropertyAnimation(effect, b"opacity", widget))
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
    animation = _track(QPropertyAnimation(window, b"windowOpacity", window))
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(EASING)
    window.setWindowOpacity(0.0)
    _keep(window, "_motion_window_fade", animation).start()


def animate_value(owner, name, start, end, on_value, on_finished=None, duration=SLIDE_MS, easing=EASING,
                  after_paint=False):
    """start から end へ値を動かし、途中の値を on_value に渡す。動きが止まっていればすぐ end を渡す。

    after_paint=True は、今の重い処理(ページの切り替えなど)と次の描画が済んでから時計を動かす。
    すぐ動かすと、画面が固まっている間に動きの大半が過ぎ、最初に描けたときにはもう着いている。
    """
    if not is_enabled() or start == end:
        on_value(end)
        if on_finished is not None:
            on_finished()
        return None
    animation = _track(QVariantAnimation(owner))
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(easing)
    animation.valueChanged.connect(on_value)
    if on_finished is not None:
        animation.finished.connect(on_finished)
    _keep(owner, name, animation)
    if after_paint:
        on_value(start)

        def start_if_current():
            if getattr(owner, name, None) is animation and shiboken6.isValid(animation):
                animation.start()

        QTimer.singleShot(0, start_if_current)
    else:
        animation.start()
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

    def __init__(self, tab_bar, trailing_margin=0):
        """trailing_margin: QSS でタブの右に空けた余白(tabRect に含まれる)。線はその手前までにする。"""
        super().__init__(tab_bar)
        self.setObjectName("tab_indicator")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._tab_bar = tab_bar
        self._trailing_margin = trailing_margin
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
        return QRect(rect.left(), rect.bottom() - self.HEIGHT + 1, rect.width() - self._trailing_margin, self.HEIGHT)

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
                          lambda: self.follow(animate=False), duration=SLIDE_MS, after_paint=True)
        else:
            stop(self, "_motion_slide")
            self.setGeometry(target)

    def eventFilter(self, watched, event):
        if watched is self._tab_bar and not running(self, "_motion_slide"):
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest,
                                QEvent.Type.StyleChange):
                # タブの幅は表示されてから決まる。動いている途中でなければ行き先へ合わせる
                QTimer.singleShot(0, lambda: self.follow(animate=False))
            elif event.type() == QEvent.Type.Paint:
                # タブを出し入れしても(凡例のタブなど)上の知らせが来ないことがあるので、描くたびに確かめる
                target = self._target()
                if target is not None and target != self.geometry():
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
        animate_value(self, "_motion_switch", start, target, step, finish, SLIDE_MS, after_paint=True)


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
