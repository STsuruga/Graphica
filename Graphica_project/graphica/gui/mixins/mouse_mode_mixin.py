# gui/mixins/mouse_mode_mixin.py
"""
7つの排他マウスモード(データカーソル / 注釈 / 自由配置編集 / 範囲選択 /
ピーク配置 / スライス抽出 / 領域ハイライト)の「どれか1つだけが有効」という
制約を、1箇所の登録簿(MOUSE_MODES)にまとめて管理するためのミックスイン。

背景(改善ボード B-1 / A-2):
    以前は各モードの ``_toggle_*_mode`` が「自分以外の6モード」を手書きの
    if連鎖で解除しており、7ファイル×6分岐=42分岐が重複展開されていた。
    この構造のため実際に解除漏れが2件発生していた:

    - 注釈モードが自由配置編集モードを解除していない (A-2)
    - データカーソルモードも同様に自由配置編集モードを解除していない
      (A-2の調査中に発見した同種の抜け)

    8つ目のモードを追加するときは、下の ``MOUSE_MODES`` に1行足すだけでよい。
    個々の ``_toggle_*_mode`` を書き換える必要はない。

各モードの ``_toggle_*_mode`` は、ONになったときの先頭で
``self._deactivate_other_mouse_modes('<自分の名前>')`` を呼ぶだけでよい。
ツールバーのQActionは ``toggled`` ではなく ``triggered`` に接続されているため、
``setChecked(False)`` だけではスロットが再入しない。そのため解除処理は
「チェックを外す」と「``_toggle_*_mode(False)`` を呼ぶ」の両方を行う
(この2段構えは従来の手書きif連鎖と同じ挙動)。
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
    """排他マウスモードの登録簿を持ち、切り替えの共通処理を提供するミックスイン。"""

    MOUSE_MODES = MOUSE_MODES

    def _deactivate_other_mouse_modes(self, active_name):
        """
        ``active_name`` 以外の全マウスモードを解除する。

        各モードの ``_toggle_*_mode`` が「ONになったとき」の先頭で呼ぶことを
        想定している。有効になっていないモードには何もしないため、
        ``_toggle_*_mode(False)`` が再帰的に呼び戻されることはない
        (解除処理は ``checked=True`` の枝にしか無いため)。

        Args:
            active_name (str): これから有効にするモードの名前(MOUSE_MODES の name)。
        """
        if active_name not in MOUSE_MODES_BY_NAME:
            # 登録簿への追加漏れ。実行は継続するが、開発中に気づけるようログに残す。
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
                # 万一メソッドが無い場合でも、フラグだけは落として
                # 「2つ有効」の状態を残さない。
                setattr(self, mode.flag_attr, False)

    def _active_mouse_mode(self):
        """現在有効なマウスモードの名前を返す(どれも有効でなければ None)。"""
        for mode in self.MOUSE_MODES:
            if getattr(self, mode.flag_attr, False):
                return mode.name
        return None
