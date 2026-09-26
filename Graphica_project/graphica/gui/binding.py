"""画面の欄と設定の辞書のキーの対応(バインディング)を表で持ち、集める・戻す・信号を止める・つなぐを表から行う。

表の順が戻す順になる。戻す順は値に効く(スピンボックスの範囲による丸め、途中の例外でどこまで入ったか)ので、
行を並べ替えるときは戻したあとの欄の値が変わらないことを確かめる。
"""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Binding:
    key: str
    # 持ち主からの属性の道筋("ui.x_min_spinbox")。None は欄を持たず持ち主の属性に持つもの(フォントと色)
    widget: str | None
    read: Callable[[Any, Any], Any]
    write: Callable[[Any, Any, Any], None]
    # 変更の信号の名前。None ならここではつながない
    signal: str | None = None
    # 信号につなぐ持ち主のメソッドの名前。つないだ順に呼ばれる
    slots: tuple[str, ...] = ()


def text(key, widget, slots):
    return Binding(key, widget, lambda _o, w: w.text(), lambda _o, w, v: w.setText(v), 'textChanged', slots)


def check(key, widget, slots):
    return Binding(key, widget, lambda _o, w: w.isChecked(), lambda _o, w, v: w.setChecked(v), 'stateChanged', slots)


def number(key, widget, slots):
    return Binding(key, widget, lambda _o, w: w.value(), lambda _o, w, v: w.setValue(v), 'valueChanged', slots)


def index(key, widget, slots):
    return Binding(key, widget, lambda _o, w: w.currentIndex(), lambda _o, w, v: w.setCurrentIndex(v),
                   'currentIndexChanged', slots)


def shown_text(key, widget, slots):
    return Binding(key, widget, lambda _o, w: w.currentText(), lambda _o, w, v: w.setCurrentText(v),
                   'currentTextChanged', slots)


def item_data(key, widget, slots):
    """選択肢に持たせたデータ。見つからない値は先頭の選択肢にする。"""
    def write(_owner, combo, value):
        found = combo.findData(value)
        combo.setCurrentIndex(found if found != -1 else 0)
    return Binding(key, widget, lambda _o, w: w.currentData(), write, 'currentIndexChanged', slots)


def choice(key, widget, choices, slots):
    """選択肢の番号と choices の値の対応。見つからない値は先頭の選択肢にする。"""
    def write(_owner, combo, value):
        combo.setCurrentIndex(choices.index(value) if value in choices else 0)
    return Binding(key, widget, lambda _o, w: choices[w.currentIndex()], write, 'currentIndexChanged', slots)


def resolve(owner, path):
    obj = owner
    for part in path.split('.'):
        obj = getattr(obj, part)
    return obj


class Binder:
    """持ち主(PlotterApp)と表から、集める・戻す・止める・つなぐを行う。欄は組み立ての途中で差し替わるので毎回引く。"""

    def __init__(self, owner, bindings, also_blocked=()):
        self._owner = owner
        self._bindings = tuple(bindings)
        # 表に無いが、戻す間は信号を止める欄(フォントと色のボタン)
        self._also_blocked = tuple(also_blocked)

    @property
    def bindings(self):
        return self._bindings

    def _widget(self, binding):
        return None if binding.widget is None else resolve(self._owner, binding.widget)

    def gather(self):
        return {b.key: b.read(self._owner, self._widget(b)) for b in self._bindings}

    def restore(self, value_of):
        """value_of(key) の値を表の順に戻す。例外はそのまま上げる(そこまでに入れた欄はそのまま残る)。"""
        for binding in self._bindings:
            binding.write(self._owner, self._widget(binding), value_of(binding.key))

    def block_signals(self, block):
        for binding in self._bindings:
            if binding.widget is not None:
                self._widget(binding).blockSignals(block)
        for path in self._also_blocked:
            resolve(self._owner, path).blockSignals(block)

    def connect(self):
        for binding in self._bindings:
            if binding.signal is None:
                continue
            signal = getattr(self._widget(binding), binding.signal)
            for slot in binding.slots:
                signal.connect(getattr(self._owner, slot))
