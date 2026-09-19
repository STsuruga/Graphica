"""タブをまたいで共有する、プロセスに1つの状態(QSettings、最近使ったファイル、プラグイン)。

タブごとの状態(ProjectModel、Undo)は持たず、使うたびに MainAppWindow から今のタブのものを取る
(最初のタブを握り続けると、複数のタブで取り違える)。PlotterApp も同じ QSettings のキーを使うので食い違わない。
"""
import os

from PySide6.QtCore import QSettings

from graphica.core.plugin_api import load_plugins_once
from graphica.gui.main_window import MAX_RECENT_FILES, disabled_plugin_names, plugin_search_paths


class AppContext:
    def __init__(self, main_app_window):
        self._main_app_window = main_app_window
        self.settings = QSettings("Graphica", "Graphica")

    # PlotterApp._get_recent_files() と同じキー("recent_files")と上限を使う

    def get_recent_files(self):
        files = self.settings.value("recent_files", [])
        if isinstance(files, str):
            # 要素が1つのリストを文字列で返すことがある
            files = [files]
        return list(files) if files else []

    def add_recent_file(self, file_path):
        file_path = os.path.abspath(file_path)
        files = self.get_recent_files()
        if file_path in files:
            files.remove(file_path)
        files.insert(0, file_path)
        files = files[:MAX_RECENT_FILES]
        self.settings.setValue("recent_files", files)

    def clear_recent_files(self):
        self.settings.setValue("recent_files", [])


    @property
    def plugin_api(self):
        """プロセスに1つの GraphicaPluginAPI(まだなら、ここで読み込む)。"""
        return load_plugins_once(
            plugin_search_paths(), disabled_names=disabled_plugin_names(self.settings)
        )

    # 古いタブを握り続けないよう、毎回 MainAppWindow から今のタブを取る

    @property
    def active_plotter_app(self):
        """今のタブの PlotterApp。タブが無ければ None。"""
        return self._main_app_window.tab_widget.currentWidget()

    @property
    def active_project(self):
        app = self.active_plotter_app
        return app.project if app is not None else None

    @property
    def active_undo_stack(self):
        app = self.active_plotter_app
        return app.undo_stack if app is not None else None
