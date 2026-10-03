"""データカーソル(点をクリックして値を見る)と、グラフの要素のクリックでの選択。表示範囲の操作は view_navigation.py。"""
import logging
import numpy as np
from matplotlib.patches import Rectangle

logger = logging.getLogger(__name__)


class CursorTool:
    """状態はこのツールが持ち、PlotterApp の同じ名前は窓口(gui/tools/__init__.py)。"""

    # PlotterApp から同じ名前で読み書きできるもの(テスト・メニュー・ほかの mixin が使う)
    EXPOSED_NAMES = (
        '_on_element_pick', '_on_mouse_move', '_on_pick', '_toggle_cursor_mode',
        'cursor_annotation', 'cursor_connection_id', 'cursor_mode_enabled',
    )

    def __init__(self, app):
        self._app = app
        # マウス操作の各モードの状態(接続 ID は切るときに使う)
        self.cursor_mode_enabled = False
        self.cursor_connection_id = None
        self.cursor_annotation = None

    def _toggle_cursor_mode(self, checked: bool):
        self.cursor_mode_enabled = checked

        if checked:
            self._app._deactivate_other_mouse_modes('cursor')

            logger.debug("データカーソルモード ON")
            self._app.coordinate_label.setText("クリックしてデータを選択")

            self.cursor_connection_id = self._app.canvas.mpl_connect(
                'pick_event', self._on_pick
            )

            # 平滑化の曲線は元のデータの点と対応しないので、ピックできるようにしない
            non_pickable_artists = {
                ds.artist for ds in self._app.project.datasets
                if ds.dataset_id in self._app.canvas._non_pickable_dataset_ids and ds.artist is not None
            }
            all_valid_axes = [ax for ax in self._app.all_axes + self._app.all_secondary_axes if ax is not None]
            for ax in all_valid_axes:
                for item in ax.get_lines() + ax.collections:
                    if item in non_pickable_artists:
                        continue
                    try:
                        item.set_picker(5)
                    except AttributeError:
                        logger.warning("オブジェクト %s は set_picker をサポートしていません。", item)
        else:
            logger.debug("データカーソルモード OFF")
            self._app.coordinate_label.setText("X= ---, Y= ---")

            if self.cursor_connection_id:
                self._app.canvas.mpl_disconnect(self.cursor_connection_id)
                self.cursor_connection_id = None

            # set_picker(False) には戻さない。同じ Artist のピックはクリックでの選択(常に有効)も使っている
            if self.cursor_annotation:
                self._remove_cursor_annotation()
                self._app.canvas.draw_idle()

    def _remove_cursor_annotation(self):
        annotation, self.cursor_annotation = self.cursor_annotation, None
        if annotation is None:
            return
        # 描き直しで Axes ごと消えた注釈は remove() できない
        try:
            annotation.remove()
        except (NotImplementedError, ValueError):
            pass

    def _on_mouse_move(self, event):
        if event.inaxes:
            ax = event.inaxes
            x, y = event.xdata, event.ydata

            try:
                ax_index = self._app.all_axes.index(ax)
                ax_label = f"P{ax_index+1}: "
            except ValueError:
                # 第2軸は all_axes に無い
                 try:
                      sec_ax_index = self._app.all_secondary_axes.index(ax)
                      ax_label = f"P{sec_ax_index+1}(Y2): "
                 except ValueError:
                      ax_label = "?: "

            self._app.coordinate_label.setText(f"{ax_label}X= {x:.4g}, Y= {y:.4g}")

        else:
            if not self.cursor_mode_enabled:
                self._app.coordinate_label.setText("X= ---, Y= ---")

    def _on_element_pick(self, event):
        """グラフの系列やタイトルをクリックして選ぶ(常に有効)。"""
        # 注釈モードと自由配置の編集モードでは、クリックはそちらの操作に使う
        if getattr(self._app, 'annotation_mode_enabled', False):
            return
        if getattr(self._app, 'layout_edit_mode_enabled', False):
            return

        artist = event.artist

        # タイトルなら、そのサブプロットを編集対象にする
        for ax_index, ax in enumerate(self._app.all_axes):
            if artist is ax.title:
                if self._app.active_axis_combo.currentIndex() != ax_index:
                    self._app.active_axis_combo.setCurrentIndex(ax_index)
                return

        # 系列なら、そのデータセットを一覧で選ぶ。Bar は BarContainer なので、patches に含まれるかで見る
        owning_dataset = next(
            (ds for ds in self._app.project.datasets
             if ds.artist is artist or (hasattr(ds.artist, 'patches') and artist in ds.artist.patches)),
            None
        )
        if owning_dataset is None:
            return

        item = self._app._get_dataset_tree_item(owning_dataset)
        if item is not None and self._app.ui.dataset_list_widget.currentItem() is not item:
            self._app.ui.dataset_list_widget.setCurrentItem(item)

    def _owning_dataset(self, artist):
        """artist を描いたデータセット。棒グラフは1本ずつの Rectangle が拾われるので、BarContainer の中も見る。"""
        return next(
            (ds for ds in self._app.project.datasets
             if ds.artist is artist or (hasattr(ds.artist, 'patches') and artist in ds.artist.patches)),
            None
        )

    def _picked_point(self, artist, event):
        """(データセット, 描いた点の番号か None, 表示座標の x, y, 2D マップの値か None)。読めなければ None。"""
        mouse = event.mouseevent
        ax = getattr(artist, 'axes', None)
        if ax is None or mouse.x is None or mouse.y is None:
            return None
        dataset = self._owning_dataset(artist)

        if dataset is not None and dataset.data_kind == '2d_grid':
            return self._picked_grid_value(dataset, ax, mouse)
        if isinstance(artist, Rectangle):
            # 棒は頂上の値を読む(負の値の棒は高さが負なので、y + 高さが値になる)
            ind = dataset.artist.patches.index(artist) if dataset is not None else None
            return dataset, ind, artist.get_x() + artist.get_width() / 2, artist.get_y() + artist.get_height(), None
        if hasattr(artist, 'get_xydata'):
            # 単位変換後の数値なので、カテゴリ軸・日付軸の線でも引き算できる
            points = np.asarray(artist.get_xydata(), dtype=float)
            candidates = np.arange(len(points))
        elif hasattr(artist, 'get_offsets') and len(event.ind) > 0:
            points = np.asarray(artist.get_offsets(), dtype=float)
            candidates = np.asarray(event.ind)
        else:
            return None

        ind = _nearest_in_pixels(ax, points, candidates, (mouse.x, mouse.y))
        if ind is None:
            return None
        return dataset, ind, points[ind][0], points[ind][1], None

    @staticmethod
    def _picked_grid_value(dataset, ax, mouse):
        """2D マップは、クリックした位置にいちばん近い格子点の値を読む。"""
        grid = dataset.z_grid
        if grid is None:
            return None
        x, y = ax.transData.inverted().transform((mouse.x, mouse.y))
        x_grid = np.asarray(grid['x_grid'], dtype=float)
        y_grid = np.asarray(grid['y_grid'], dtype=float)
        if x_grid.size == 0 or y_grid.size == 0:
            return None
        col = int(np.argmin(np.abs(x_grid - x)))
        row = int(np.argmin(np.abs(y_grid - y)))
        return dataset, None, x_grid[col], y_grid[row], grid['z_grid'][row, col]

    def _on_pick(self, event):
        if not self.cursor_mode_enabled: return

        artist = event.artist
        picked = self._picked_point(artist, event)
        if picked is None:
            return
        owning_dataset, ind, x, y, z = picked

        if x is not None and y is not None:
            # x, y はウォーターフォールのずらしが掛かった表示座標。矢印はそのままの位置に出し、
            # 表示する値だけデータ座標に戻す
            if owning_dataset is not None:
                data_x, data_y = self._app.canvas.display_to_data(owning_dataset, x, y)
            else:
                data_x, data_y = x, y

            self._remove_cursor_annotation()

            ax = artist.axes
            text = f"X: {data_x:.4g}\nY: {data_y:.4g}"
            if z is not None:
                text += f"\nZ: {z:.4g}"

            self.cursor_annotation = ax.annotate(text,
                xy=(x, y),
                xytext=(10, -10),
                textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.7),
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.3")
            )

            self._app.canvas.draw_idle()

            # データエディタが開いていれば、クリックした点の行を表でも選ぶ
            if ind is not None and self._app.data_editor_dialog is not None:
                if owning_dataset is not None and self._app.data_editor_dialog.dataset is owning_dataset:
                    try:
                        # ind は描いた点(visible_df、間引いていれば間引いた後)の位置。
                        # 間引いた系列は downsample_index_map で元の位置に戻してから visible_df.index を引く
                        index_map = self._app.canvas.downsample_index_map.get(owning_dataset.dataset_id)
                        if index_map is not None:
                            ind = index_map[ind]
                        master_index = owning_dataset.visible_df.index[ind]
                        # 選択の通知は止めてあるので、グラフ側の強調はここで更新する
                        self._app.data_editor_dialog.select_row_by_master_index(master_index)
                        self._app.canvas.set_highlighted_points(
                            owning_dataset, self._app.data_editor_dialog.get_selected_master_indices()
                        )
                    except IndexError:
                        pass


def _nearest_in_pixels(ax, points, candidates, mouse_px):
    """candidates(points の番号)のうち、画面上でマウスにいちばん近いもの。

    データ座標の距離だと、X と Y の桁が違う(例えば 0〜1000 と 0〜1)とほぼ X だけで決まってしまう。
    """
    if len(candidates) == 0:
        return None
    pixels = ax.transData.transform(points[candidates])
    distances = np.hypot(pixels[:, 0] - mouse_px[0], pixels[:, 1] - mouse_px[1])
    if np.all(np.isnan(distances)):
        return None
    return int(candidates[np.nanargmin(distances)])
