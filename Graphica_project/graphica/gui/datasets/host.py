"""機能ごとのクラスが本体(PlotterApp の1タブ)に頼むことの窓口。"""
from contextlib import contextmanager

from graphica.core.commands import SetAnnotationsCommand


class DatasetHost:
    """機能ごとのクラスが PlotterApp の内部に直接触らないよう、使う操作だけをここに集める。"""

    def __init__(self, app):
        self._app = app

    @property
    def parent_widget(self):
        return self._app

    @property
    def undo_stack(self):
        return self._app.undo_stack

    @contextmanager
    def undo_macro(self, text, enabled=True):
        """中の操作を Undo 1回分にまとめる(enabled=False なら何もしない)。"""
        if enabled:
            self._app.undo_stack.beginMacro(text)
        try:
            yield
        finally:
            if enabled:
                self._app.undo_stack.endMacro()

    def current_dataset(self):
        return self._app._get_current_dataset()

    def add_derived_dataset(self, dataset, source):
        """source と同じフォルダにデータセットを足して描き直す(Undo の対象にはしない)。"""
        self._app.project.datasets.append(dataset)
        source_item = self._app._get_dataset_tree_item(source)
        self._app._add_dataset_list_item(dataset, source_item.parent() if source_item else None)
        self._app._update_plot()

    def add_annotation(self, axis_index, annotation, description):
        self._app._add_annotation(axis_index, annotation, description=description)

    def annotations(self, axis_index):
        """その軸の注釈(リストはコピー)。"""
        return list(self._app.project.all_plot_settings[axis_index].get('annotations', []))

    def add_annotations_to_active_axis(self, annotations, description):
        """今の軸に注釈をまとめて足す(Undo 1回分)。"""
        project = self._app.project
        index = project.active_axis_index
        if index >= len(project.all_plot_settings):
            return
        old_annotations = self.annotations(index)
        self._app.undo_stack.push(SetAnnotationsCommand(
            project, index, old_annotations, old_annotations + list(annotations),
            self._app._update_plot_appearance, description=description))

    def axis_y_span(self, axis_index):
        """その軸の今の Y の表示幅。軸が無ければ None。"""
        axes = self._app.canvas.all_axes
        if not 0 <= axis_index < len(axes):
            return None
        y_lo, y_hi = axes[axis_index].get_ylim()
        return y_hi - y_lo

    def selected_datasets(self):
        return self._app._get_selected_datasets()

    def target_folder_for_new_dataset(self):
        """ツリーで選ばれているのがフォルダならそのフォルダ(新しいデータセットの置き場所)、それ以外は None。"""
        return self._app._get_target_folder_for_new_dataset()

    def add_datasets_to_folder(self, datasets, folder):
        """まとめて足してから1回だけ描き直す(1件ずつ描き直すと件数分のフル再描画になる)。"""
        for dataset in datasets:
            self._app.project.datasets.append(dataset)
            self._app._add_dataset_list_item(dataset, folder)
        self._app._update_plot()

    def axis_count(self):
        return len(self._app.project.all_plot_settings)

    def show_status(self, text, msecs=3000):
        self._app.statusBar().showMessage(text, msecs)

    def set_fit_button_enabled(self, enabled):
        self._app.fit_curve_button.setEnabled(enabled)

    def set_multi_peak_fit_button_enabled(self, enabled):
        self._app.multi_peak_fit_button.setEnabled(enabled)

    def pending_peak_guesses(self):
        """グラフ上のクリックで置いた多峰フィットの初期値(のコピー)。"""
        return list(self._app._pending_peak_guesses)

    def finish_peak_placement(self):
        """置いた初期値を消し、ピーク配置モードを抜ける。"""
        self._app._clear_pending_peak_guesses()
        if getattr(self._app, 'peak_placement_mode_enabled', False):
            self._app.peak_placement_action.setChecked(False)
            self._app._toggle_peak_placement_mode(False)

    def datasets(self):
        """タブの全データセット(リストはコピー)。"""
        return list(self._app.project.datasets)

    def add_dataset(self, dataset, parent_folder=None, select=True):
        """ツリーと描画に足す(Undo の対象にはしない)。"""
        return self._app._add_dataset(dataset, parent_folder, select=select)

    def add_dataset_with_undo(self, dataset, parent_folder=None, description="データセットの追加"):
        self._app._add_dataset_with_undo(dataset, parent_folder=parent_folder, description=description)

    def redraw(self):
        self._app._update_plot()

    def refresh_ui_state(self):
        """選択中のデータセットに合わせてパネルとメニューの状態を更新する。"""
        self._app._update_ui_state()

    def active_color_cycle(self):
        return self._app.colors.active_color_cycle()

    @property
    def project(self):
        """文書全体。読むためだけに使う(書き換えは host の操作を通す)。"""
        return self._app.project

    @property
    def settings(self):
        """アプリ全体の設定(QSettings)。"""
        return self._app.settings

    def push_property_change(self, dataset, old_values, new_values, description, skip_if_unchanged=True):
        """データセットの属性の変更を Undo できる形で積む(skip_if_unchanged なら変化が無いときは何もしない)。"""
        self._app._push_dataset_property_command(dataset, old_values, new_values, description,
                                                 skip_if_unchanged=skip_if_unchanged)

    def remove_datasets(self, datasets, description=None):
        """確認なしで Undo できる形で消す。"""
        items = [item for dataset in datasets
                 if (item := self._app._get_dataset_tree_item(dataset)) is not None]
        self._app._remove_dataset_items_with_undo(items, description=description)

    def sibling_tabs(self):
        """ほかのタブの (タブの見出し, そのタブの DatasetHost)。タブの窓に入っていなければ空。"""
        from graphica.gui.main_app_window import MainAppWindow  # main_app_window がこのパッケージを読み込むので遅らせる
        top = self._app.window()
        if not isinstance(top, MainAppWindow):
            return []
        tabs = top.tab_widget
        return [(tabs.tabText(i), tabs.widget(i)._dataset_host)
                for i in range(tabs.count()) if tabs.widget(i) is not self._app]
