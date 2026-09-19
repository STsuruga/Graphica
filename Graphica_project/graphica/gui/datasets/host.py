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
