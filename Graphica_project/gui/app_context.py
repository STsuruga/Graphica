# gui/app_context.py
"""
アプリケーション全体で共有されるグローバル状態の集約点 (C-006)。

タブ (PlotterApp インスタンス) をまたいで共有される「プロセス全体で1つ」の
状態 (QSettings・最近使ったファイル・プラグインレジストリ) をここに集約する。

ProjectModel/undo_stack のようなタブ固有の状態はここでは保持せず、
active_project/active_undo_stack のように「呼び出し時点で MainAppWindow から
都度取得する」形で提供する。core/plugin_api.py の GraphicaPluginAPI が
self._main_window を登録時点(最初のタブ)で固定してしまい、以後のタブでは
常に古いタブを指してしまう既知の罠(CLAUDE.md参照)を、今後の新しい拡張
ポイント(例: register_panel)では踏まないようにするための設計。

MainAppWindow がプロセスにつき1つ生成・所有する。既存の PlotterApp / 各Mixin
の実装には一切手を加えない、という MainAppWindow の設計方針 (同モジュールの
docstring参照) を踏襲し、PlotterApp 側のコンストラクタ・内部実装はここでは
変更しない。PlotterApp は既存通り自分自身の QSettings / 最近使ったファイル
ロジックを引き続き使い続けてよい(同じ QSettings キーを読み書きするため、
AppContext経由の操作と食い違うことはない)。
"""
import os

from PySide6.QtCore import QSettings

from core.plugin_api import load_plugins_once
from gui.main_window import MAX_RECENT_FILES, resource_path


class AppContext:
    """MainAppWindowが生成・保持する、プロセス全体で1つのグローバル状態。"""

    def __init__(self, main_app_window):
        self._main_app_window = main_app_window
        self.settings = QSettings("Graphica", "Graphica")

    # --- 最近使ったファイル ---
    # gui/main_window.py の PlotterApp._get_recent_files() 等と同じ
    # QSettingsキー("recent_files")・同じ上限件数(MAX_RECENT_FILES)を使う。

    def get_recent_files(self):
        """QSettingsから履歴リスト(新しい順)を取得する"""
        files = self.settings.value("recent_files", [])
        if isinstance(files, str):
            # QSettingsは要素数1のリストを単一の文字列として返すことがあるため補正する
            files = [files]
        return list(files) if files else []

    def add_recent_file(self, file_path):
        """履歴の先頭にファイルパスを追加し、上限件数でトリムして保存する"""
        file_path = os.path.abspath(file_path)
        files = self.get_recent_files()
        if file_path in files:
            files.remove(file_path)
        files.insert(0, file_path)
        files = files[:MAX_RECENT_FILES]
        self.settings.setValue("recent_files", files)

    def clear_recent_files(self):
        self.settings.setValue("recent_files", [])

    # --- プラグインレジストリ ---

    @property
    def plugin_api(self):
        """プロセス全体で1つのGraphicaPluginAPI(未読み込みならこの時点で読み込む)"""
        return load_plugins_once(resource_path("plugins"))

    # --- 現在アクティブなタブへのアクセス ---
    # プラグインコールバック等が古いタブへの参照を保持し続けてしまわないよう、
    # プロパティアクセスのたびに MainAppWindow から現在のタブを取得し直す
    # (キャッシュしない)。

    @property
    def active_plotter_app(self):
        """現在アクティブなタブのPlotterAppインスタンス(タブが1つも無ければNone)"""
        return self._main_app_window.tab_widget.currentWidget()

    @property
    def active_project(self):
        """現在アクティブなタブのProjectModel(アクティブなタブが無ければNone)"""
        app = self.active_plotter_app
        return app.project if app is not None else None

    @property
    def active_undo_stack(self):
        """現在アクティブなタブのQUndoStack(アクティブなタブが無ければNone)"""
        app = self.active_plotter_app
        return app.undo_stack if app is not None else None
