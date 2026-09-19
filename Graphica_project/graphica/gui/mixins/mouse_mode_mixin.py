"""マウスの7つのモード(データカーソル / 注釈 / 自由配置 / 範囲選択 / ピーク配置 / スライス抽出 / 領域強調)を、
どれか1つだけが有効になるよう MOUSE_MODES の表でまとめて管理する。

モードを足すときは MOUSE_MODES に1行足す。各モードの _toggle_*_mode は、有効になるときの先頭で
self._deactivate_other_mouse_modes('<名前>') を呼ぶだけでよい。QAction は toggled ではなく triggered に
つないであるので、setChecked(False) だけではスロットが呼ばれない。解除ではチェックを外すのと
_toggle_*_mode(False) の呼び出しの両方をする。
"""
import logging
from collections import namedtuple

logger = logging.getLogger(__name__)


# name:          モードの識別子(_deactivate_other_mouse_modes に渡す名前)
# flag_attr:     PlotterApp 上の「有効かどうか」を持つ属性名
# action_attr:   ツールバーの QAction を持つ属性名
# toggle_method: ON/OFF を切り替えるメソッド名
MouseMode = namedtuple("MouseMode", "name flag_attr action_attr toggle_method")

MOUSE_MODES = (
    MouseMode("cursor", "cursor_mode_enabled",
              "cursor_action", "_toggle_cursor_mode"),
    MouseMode("annotation", "annotation_mode_enabled",
              "annotation_action", "_toggle_annotation_mode"),
    MouseMode("layout_edit", "layout_edit_mode_enabled",
              "layout_edit_action", "_toggle_layout_edit_mode"),
    MouseMode("range_select", "range_select_mode_enabled",
              "range_select_action", "_toggle_range_select_mode"),
    MouseMode("peak_placement", "peak_placement_mode_enabled",
              "peak_placement_action", "_toggle_peak_placement_mode"),
    MouseMode("slice_extraction", "slice_extraction_mode_enabled",
              "slice_extraction_action", "_toggle_slice_extraction_mode"),
    MouseMode("region_highlight", "region_highlight_mode_enabled",
              "region_highlight_action", "_toggle_region_highlight_mode"),
)

MOUSE_MODES_BY_NAME = {mode.name: mode for mode in MOUSE_MODES}


class MouseModeMixin:
    MOUSE_MODES = MOUSE_MODES

    def _deactivate_other_mouse_modes(self, active_name):
        """active_name 以外のモードを解除する。有効でないモードには何もしないので、解除から呼び戻されて循環しない。"""
        if active_name not in MOUSE_MODES_BY_NAME:
            # 表への登録漏れ。動作は続けるが、開発中に気づけるようログに残す
            logger.warning(
                "未登録のマウスモード名です: %s (gui/mixins/mouse_mode_mixin.py の "
                "MOUSE_MODES に追加してください)", active_name
            )

        for mode in self.MOUSE_MODES:
            if mode.name == active_name:
                continue
            if not getattr(self, mode.flag_attr, False):
                continue

            action = getattr(self, mode.action_attr, None)
            if action is not None:
                action.setChecked(False)

            toggle = getattr(self, mode.toggle_method, None)
            if callable(toggle):
                toggle(False)
            else:
                # メソッドが無くても、フラグは落として「2つ有効」を残さない
                setattr(self, mode.flag_attr, False)

    def _active_mouse_mode(self):
        """有効なモードの名前。無ければ None。"""
        for mode in self.MOUSE_MODES:
            if getattr(self, mode.flag_attr, False):
                return mode.name
        return None
