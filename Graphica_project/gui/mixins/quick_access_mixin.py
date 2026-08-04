# gui/mixins/quick_access_mixin.py
"""
項目87: クイックアクセスのカスタムツールバー。

ユーザーがよく使うメニュー項目(プラグイン(項目76)が追加したメニュー項目も
含む)を、専用のツールバーにピン留めできるようにするMixin。

設計方針:
- ピン留め対象は「メニューバー配下の実行可能なQAction」に統一する。
  既存の _collect_menu_actions() (UISetupMixinで定義、コマンドパレット/
  ショートカット一覧が既に依存している) が返す [(パスのリスト, QAction), ...]
  をそのまま再利用する。プラグインが register_menu_action() で追加した
  アクションも、_create_menu_bar() の時点で通常のQActionとして
  「プラグイン」メニューに追加済みのため、特別扱い不要で一緒に集まる
  (_collect_menu_actions() 側で「プラグイン」メニューも走査するよう修正済み)。
- ★ 重要 ★ ピン留めしたQActionは、コピーを作らず「同じオブジェクト」を
  ツールバーにも addAction() する。QActionは複数のウィジェット
  (メニュー・ツールバー)に同時に所属でき、Qt側が状態(有効/無効・チェック
  状態など)を自動的に同期するため、複製すると起き得る「本体側だけ更新されて
  ツールバー側が古いままになる」ようなズレを避けられる。
- 永続化はQSettings("Graphica", "Graphica")の "quick_access_pinned_actions"
  キーに、識別子文字列のリストとして保存する。識別子は
  _collect_menu_actions() が返すパスのリストを " > " で連結した文字列
  (例: "ファイル(F) > プロジェクトを開く(O)...")。アプリ再起動のたびに
  メニューは一から再構築され、QAction自体は毎回新しいオブジェクトになる
  ため、objectName等ではなく「表示テキストの階層パス」を安定識別子として
  使う。メニュー構造やテキストを変えない限り再起動をまたいで一致し続け、
  該当するアクションが見つからない場合(プラグインが削除された等)は
  単に無視して復元をスキップする(エラーにしない)。
- 複数タブ(項目40)対応: 各PlotterAppタブは自分自身の menuBar()・
  _collect_menu_actions()・quick_access_toolbar を個別に持つため、
  ツールバーの構築/復元は毎回タブごとに独立して行う。共有するのは
  QSettingsの永続化データ(識別子のリスト)のみで、新しく開いたタブは
  そのタブ自身のメニューから同じ識別子に一致するアクションを探して
  復元する。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar, QMenu

from core.i18n import tr
from gui.dialogs import QuickAccessManagerDialog

QUICK_ACCESS_SETTINGS_KEY = "quick_access_pinned_actions"


def quick_access_action_identifier(path):
    """_collect_menu_actions() が返すパスのリストから、永続化用の識別子文字列を作る"""
    return " > ".join(path)


class QuickAccessMixin:
    def _create_quick_access_toolbar(self):
        """
        空のクイックアクセスツールバーと、表示/非表示を切り替えるための
        表示メニュー項目を作成する。__init__ 内の _create_menu_bar() から、
        表示メニュー構築の一環として呼ばれる。

        ピン留め済みアクションの実際の復元は _restore_quick_access_actions() で
        別途行う(「プラグイン」メニューを含む全メニューが構築し終わった後で
        ないと、プラグインが登録したアクションを _collect_menu_actions() 経由で
        見つけられないため)。
        """
        self._quick_access_actions = {}  # 識別子 -> QAction (GC対策の永続参照)

        toolbar = QToolBar(tr("クイックアクセス"), self)
        # QMainWindow::saveState()/restoreState() がツールバーの表示状態・配置を
        # 一意に識別できるよう、objectNameを設定しておく(未設定だと警告が出る)。
        toolbar.setObjectName("quick_access_toolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.quick_access_toolbar = toolbar

        # ツールバー先頭には常に「管理...」ボタンを置く(ピン留め0件でも
        # 管理ダイアログへ辿り着けるようにするため)。
        self.quick_access_manage_action = QAction(tr("クイックアクセスの管理..."), self)
        self.quick_access_manage_action.triggered.connect(self._on_manage_quick_access)
        toolbar.addAction(self.quick_access_manage_action)
        toolbar.addSeparator()

        # QToolBarもQDockWidgetと同様、標準の表示/非表示トグルアクションを持つ
        # (既存のプロパティパネル/エクスポートプレビューの表示メニュー項目と同じ方式)。
        toggle_action = toolbar.toggleViewAction()
        toggle_action.setText(tr("クイックアクセスツールバー"))
        self._view_menu.addAction(toggle_action)

    # --------------------------------------------------------------------
    # 右クリックでのピン留め/解除 (メニュー項目 → コンテキストメニュー)
    # --------------------------------------------------------------------

    def _quick_access_pinnable_menus(self):
        """右クリックでのピン留め対象とする、キャッシュ済みの最上位メニュー一覧"""
        menus = [self._file_menu, self._edit_menu, self._view_menu, self._help_menu]
        plugin_menu = getattr(self, '_plugin_menu', None)
        if plugin_menu is not None:
            menus.append(plugin_menu)
        return menus

    def _install_quick_access_context_menus(self):
        """
        各最上位メニューに、項目を右クリックして
        「クイックアクセスに追加/から削除」できるコンテキストメニューを取り付ける。
        _create_menu_bar() が完全に終わった後(プラグインメニューも含めて
        全メニューが揃った後)に __init__ 側から一度だけ呼ばれる想定。
        """
        for menu in self._quick_access_pinnable_menus():
            menu.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            menu.customContextMenuRequested.connect(
                lambda pos, m=menu: self._on_quick_access_menu_context_menu(m, pos)
            )

    def _resolve_quick_access_menu_target(self, menu, pos):
        """
        menu内の座標posにあるアクションから、(識別子, パスのリスト, QAction) を返す。
        区切り線・サブメニューを開くアクション・どこも指していない位置の場合はNoneを返す。

        ★ このメソッドはUIを一切開かない(ポップアップ表示を伴う
        _on_quick_access_menu_context_menu から意図的に切り出してある)ため、
        イベントループを介さずにテストできる。
        """
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
        """メニュー項目を右クリックしたときの処理。ピン留め/解除の小さなメニューを出す"""
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

    # --------------------------------------------------------------------
    # 永続化 (QSettings)
    # --------------------------------------------------------------------

    def _get_pinned_quick_access_ids(self):
        """QSettingsから、ピン留め済み識別子のリスト(ピン留めした順)を取得する"""
        ids = self.settings.value(QUICK_ACCESS_SETTINGS_KEY, [])
        if isinstance(ids, str):
            # QSettings は要素数1のリストを単一の文字列として返すことがあるため補正する
            # (_get_recent_files と同じ既知の癖)
            ids = [ids]
        return list(ids) if ids else []

    def _set_pinned_quick_access_ids(self, ids):
        self.settings.setValue(QUICK_ACCESS_SETTINGS_KEY, ids)

    def _restore_quick_access_actions(self):
        """
        起動時に一度呼ばれる。QSettingsに保存された識別子のリストから、
        現在のメニューに存在するアクションだけをツールバーへ復元する。
        該当するアクションが見つからない識別子(プラグインが削除された等)は
        黙ってスキップする(エラーにしない、ベストエフォート)。
        """
        ids = self._get_pinned_quick_access_ids()
        if not ids:
            return
        available = {
            quick_access_action_identifier(path): action
            for path, action in self._collect_menu_actions()
        }
        for ident in ids:
            action = available.get(ident)
            if action is not None:
                self._add_action_to_quick_access_toolbar(ident, action)

    # --------------------------------------------------------------------
    # ピン留め/解除の実処理 (コンテキストメニュー・管理ダイアログ共通)
    # --------------------------------------------------------------------

    def _add_action_to_quick_access_toolbar(self, ident, action):
        if ident in self._quick_access_actions:
            return
        self.quick_access_toolbar.addAction(action)
        self._quick_access_actions[ident] = action

    def pin_quick_access_action(self, ident, action):
        """
        アクションをクイックアクセスツールバーにピン留めする
        (コンテキストメニュー・管理ダイアログの両方から呼ばれる共通エントリポイント)。
        """
        self._add_action_to_quick_access_toolbar(ident, action)
        ids = self._get_pinned_quick_access_ids()
        if ident not in ids:
            ids.append(ident)
            self._set_pinned_quick_access_ids(ids)

    def unpin_quick_access_action(self, ident):
        """クイックアクセスツールバーからピン留めを解除する"""
        action = self._quick_access_actions.pop(ident, None)
        if action is not None:
            self.quick_access_toolbar.removeAction(action)
        ids = self._get_pinned_quick_access_ids()
        if ident in ids:
            ids.remove(ident)
            self._set_pinned_quick_access_ids(ids)

    def is_quick_access_pinned(self, ident):
        return ident in self._quick_access_actions

    # --------------------------------------------------------------------
    # 管理ダイアログ
    # --------------------------------------------------------------------

    def _on_manage_quick_access(self):
        """クイックアクセスツールバーの「クイックアクセスの管理...」ボタンの処理"""

        def toggle(ident, path, checked):
            if checked:
                # CommandPaletteDialogと同じ理由で、表示時に集めたQActionは
                # 使わず、実行直前に取り直したものを使う(パスで再照合する)。
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
