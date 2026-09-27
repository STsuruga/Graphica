"""クイックアクセス: よく使うメニュー項目をツールバーにピン留めする。

ツールバーにはメニューの QAction そのものを addAction する(写しを作ると状態がずれる)。
ピン留めは QSettings の "quick_access_pinned_actions" に、メニューのパスを " > " でつないだ文字列で保存する
(QAction は起動のたびに作り直されるので、表示文字のパスを識別子にする)。見つからないものは黙って飛ばす。
ツールバーはタブごとに作り、共有するのは保存した識別子だけ。
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar, QMenu

from graphica.core.i18n import tr
from graphica.gui import app_settings
from graphica.gui.dialogs import QuickAccessManagerDialog

logger = logging.getLogger(__name__)



# _migrate_pinned_quick_access_ids() が末尾の項目名を取り出すのにも使う
SEPARATOR = " > "


def quick_access_action_identifier(path):
    return SEPARATOR.join(path)


class QuickAccessMixin:
    def _create_quick_access_toolbar(self):
        """空のツールバーと、表示メニューの切り替えを作る。

        ピン留めを戻すのは _restore_quick_access_actions()(プラグインのメニューを含めて全部できた後でないと見つからない)。
        """
        self._quick_access_actions = {}  # 識別子 -> QAction(回収されないよう持つ)

        toolbar = QToolBar(tr("クイックアクセス"), self)
        # saveState() が見分けられるように
        toolbar.setObjectName("quick_access_toolbar")
        # 上に固定するので、移動用のつまみは出さない(QSS では隠せない)
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.quick_access_toolbar = toolbar

        # ピン留めが0件でも管理ダイアログに行けるよう、先頭に置く
        self.quick_access_manage_action = QAction(tr("クイックアクセスの管理..."), self)
        self.quick_access_manage_action.triggered.connect(self._on_manage_quick_access)
        toolbar.addAction(self.quick_access_manage_action)
        toolbar.addSeparator()

        toggle_action = toolbar.toggleViewAction()
        toggle_action.setText(tr("クイックアクセスツールバー"))
        self._view_menu.addAction(toggle_action)


    def _quick_access_pinnable_menus(self):
        menus = [self._file_menu, self._edit_menu, self._view_menu, self._help_menu]
        plugin_menu = getattr(self, '_plugin_menu', None)
        if plugin_menu is not None:
            menus.append(plugin_menu)
        return menus

    def _install_quick_access_context_menus(self):
        """各メニューの項目の右クリックでピン留めと解除をできるようにする(全部のメニューができた後に1回)。"""
        for menu in self._quick_access_pinnable_menus():
            menu.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            menu.customContextMenuRequested.connect(
                lambda pos, m=menu: self._on_quick_access_menu_context_menu(m, pos)
            )

    def _resolve_quick_access_menu_target(self, menu, pos):
        """pos の項目の (識別子, パス, QAction)。区切り線やサブメニューなら None。UI を開かないのでテストできる。"""
        action = menu.actionAt(pos)
        if action is None or action.isSeparator() or action.menu() is not None:
            return None
        text = action.text().replace('&', '').strip()
        if not text:
            return None
        path = [menu.title().replace('&', ''), text]
        ident = quick_access_action_identifier(path)
        return ident, path, action

    def _on_quick_access_menu_context_menu(self, menu, pos):
        target = self._resolve_quick_access_menu_target(menu, pos)
        if target is None:
            return
        ident, path, action = target

        popup = QMenu(self)
        if self.is_quick_access_pinned(ident):
            remove_action = popup.addAction(tr("クイックアクセスから削除"))
            remove_action.triggered.connect(lambda: self.unpin_quick_access_action(ident))
        else:
            add_action = popup.addAction(tr("クイックアクセスに追加"))
            add_action.triggered.connect(lambda: self.pin_quick_access_action(ident, action))
        popup.exec(menu.mapToGlobal(pos))


    def _get_pinned_quick_access_ids(self):
        """ピン留めした順の識別子。"""
        return app_settings.as_list_keeping_empty_string(app_settings.QUICK_ACCESS_PINNED_ACTIONS.read(self.settings))

    def _set_pinned_quick_access_ids(self, ids):
        app_settings.QUICK_ACCESS_PINNED_ACTIONS.write(self.settings, ids)

    def _migrate_pinned_quick_access_ids(self, ids, available):
        """メニューの組み替えでパスが変わったピン留めを、新しい識別子に読み替える。((識別子のリスト, 変えたか))

        一致しない識別子は黙って飛ばされ、ピンが知らないうちに消えるので読み替える。末尾の項目名が一致する候補が
        今のメニューにちょうど1つあるときだけ読み替え、複数あれば触らない。項目名自体が変わったものは読み替えない。
        """
        by_leaf = {}
        for ident in available:
            leaf = ident.rsplit(SEPARATOR, 1)[-1]
            by_leaf.setdefault(leaf, []).append(ident)

        migrated, changed = [], False
        for ident in ids:
            if ident in available:
                migrated.append(ident)
                continue
            candidates = by_leaf.get(ident.rsplit(SEPARATOR, 1)[-1], [])
            if len(candidates) == 1:
                logger.info(
                    "クイックアクセスのピン留めを移動先へ読み替えました: %r -> %r",
                    ident, candidates[0],
                )
                migrated.append(candidates[0])
                changed = True
            else:
                migrated.append(ident)
        return migrated, changed

    def _restore_quick_access_actions(self):
        """保存した識別子のうち、今のメニューにあるものをツールバーに戻す(起動時に1回)。"""
        ids = self._get_pinned_quick_access_ids()
        if not ids:
            return
        available = {
            quick_access_action_identifier(path): action
            for path, action in self._collect_menu_actions()
        }
        ids, changed = self._migrate_pinned_quick_access_ids(ids, available)
        if changed:
            # 書き戻して、次からは読み替えずに済むように
            self._set_pinned_quick_access_ids(ids)
        for ident in ids:
            action = available.get(ident)
            if action is not None:
                self._add_action_to_quick_access_toolbar(ident, action)


    def _add_action_to_quick_access_toolbar(self, ident, action):
        if ident in self._quick_access_actions:
            return
        self.quick_access_toolbar.addAction(action)
        self._quick_access_actions[ident] = action

    def pin_quick_access_action(self, ident, action):
        self._add_action_to_quick_access_toolbar(ident, action)
        ids = self._get_pinned_quick_access_ids()
        if ident not in ids:
            ids.append(ident)
            self._set_pinned_quick_access_ids(ids)

    def unpin_quick_access_action(self, ident):
        action = self._quick_access_actions.pop(ident, None)
        if action is not None:
            self.quick_access_toolbar.removeAction(action)
        ids = self._get_pinned_quick_access_ids()
        if ident in ids:
            ids.remove(ident)
            self._set_pinned_quick_access_ids(ids)

    def is_quick_access_pinned(self, ident):
        return ident in self._quick_access_actions


    def _on_manage_quick_access(self):
        def toggle(ident, path, checked):
            if checked:
                # 一覧を作ったときの QAction は使わず、実行する直前にパスで取り直す
                for p, action in self._collect_menu_actions():
                    if p == path:
                        self.pin_quick_access_action(ident, action)
                        break
            else:
                self.unpin_quick_access_action(ident)

        dialog = QuickAccessManagerDialog(
            self._collect_menu_actions, self.is_quick_access_pinned, toggle, self
        )
        dialog.exec()
