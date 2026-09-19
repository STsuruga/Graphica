"""機能ごとのクラスが本体(PlotterApp の1タブ)に頼むことの窓口。"""
from contextlib import contextmanager


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
        return self._app._get_active_color_cycle()
