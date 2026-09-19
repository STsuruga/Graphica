"""データカーソル(点をクリックして値を見る)、ホイールでのズーム、中ボタンでのパン、グラフの要素のクリックでの選択。"""
import logging
import numpy as np

logger = logging.getLogger(__name__)


class CursorMixin:
    # ホイールのズームと中ボタンのパンは、どのモードの左クリックともぶつからないので常に有効。
    # 対象はカーソルの下の軸だけ(ミニマップは全部の軸)。

    def _on_scroll_zoom(self, event):
        """カーソルの位置を中心に、上で拡大、下で縮小する。"""
        ax = event.inaxes
        if ax is None or event.xdata is None or event.ydata is None:
            return

        base_scale = 1.2
        scale_factor = (1 / base_scale) if event.button == 'up' else base_scale

        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        xdata, ydata = event.xdata, event.ydata

        new_width = (xlim[1] - xlim[0]) * scale_factor
        new_height = (ylim[1] - ylim[0]) * scale_factor

        # カーソルが新しい範囲でも同じ相対位置に来るよう、余白を左右と上下に配分する
        old_width = xlim[1] - xlim[0]
        old_height = ylim[1] - ylim[0]
        relx = (xlim[1] - xdata) / old_width if old_width else 0.5
        rely = (ylim[1] - ydata) / old_height if old_height else 0.5

        ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
        ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        self.canvas.draw_idle()

    def _on_middle_button_press_pan(self, event):
        """押したときの範囲とカーソルのデータ座標を覚える。"""
        if event.button != 2 or event.inaxes is None:
            return
        if event.xdata is None or event.ydata is None:
            return
        self._middle_pan_axes = event.inaxes
        self._middle_pan_start_data = (event.xdata, event.ydata)
        self._middle_pan_start_xlim = event.inaxes.get_xlim()
        self._middle_pan_start_ylim = event.inaxes.get_ylim()

    def _on_middle_button_motion_pan(self, event):
        """押したときの範囲を基準に、押した位置と今の位置の差だけずらす(差分を積み上げないので誤差がたまらない)。"""
        axes = getattr(self, '_middle_pan_axes', None)
        if axes is None or event.inaxes is not axes:
            return
        if event.xdata is None or event.ydata is None:
            return

        start_x, start_y = self._middle_pan_start_data
        dx = start_x - event.xdata
        dy = start_y - event.ydata

        xlim = self._middle_pan_start_xlim
        ylim = self._middle_pan_start_ylim
        axes.set_xlim(xlim[0] + dx, xlim[1] + dx)
        axes.set_ylim(ylim[0] + dy, ylim[1] + dy)
        self.canvas.draw_idle()

    def _on_middle_button_release_pan(self, event):
        if event.button != 2:
            return
        self._middle_pan_axes = None
        self._middle_pan_start_data = None
        self._middle_pan_start_xlim = None
        self._middle_pan_start_ylim = None

    def _toggle_cursor_mode(self, checked: bool):
        self.cursor_mode_enabled = checked

        if checked:
            self._deactivate_other_mouse_modes('cursor')

            logger.debug("データカーソルモード ON")
            self.coordinate_label.setText("クリックしてデータを選択")

            self.cursor_connection_id = self.canvas.mpl_connect(
                'pick_event', self._on_pick
            )

            # 平滑化の曲線は元のデータの点と対応しないので、ピックできるようにしない
            non_pickable_artists = {
                ds.artist for ds in self.project.datasets
                if ds.dataset_id in self.canvas._non_pickable_dataset_ids and ds.artist is not None
            }
            all_valid_axes = [ax for ax in self.all_axes + self.all_secondary_axes if ax is not None]
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
            self.coordinate_label.setText("X= ---, Y= ---")

            if self.cursor_connection_id:
                self.canvas.mpl_disconnect(self.cursor_connection_id)
                self.cursor_connection_id = None

            # set_picker(False) には戻さない。同じ Artist のピックはクリックでの選択(常に有効)も使っている
            if self.cursor_annotation:
                self.cursor_annotation.remove()
                self.cursor_annotation = None
                self.canvas.draw_idle()

    def _on_mouse_move(self, event):
        if event.inaxes:
            ax = event.inaxes
            x, y = event.xdata, event.ydata

            try:
                ax_index = self.all_axes.index(ax)
                ax_label = f"P{ax_index+1}: "
            except ValueError:
                # 第2軸は all_axes に無い
                 try:
                      sec_ax_index = self.all_secondary_axes.index(ax)
                      ax_label = f"P{sec_ax_index+1}(Y2): "
                 except ValueError:
                      ax_label = "?: "

            self.coordinate_label.setText(f"{ax_label}X= {x:.4g}, Y= {y:.4g}")

        else:
            if not self.cursor_mode_enabled:
                self.coordinate_label.setText("X= ---, Y= ---")

    def _on_element_pick(self, event):
        """グラフの系列やタイトルをクリックして選ぶ(常に有効)。"""
        # 注釈モードと自由配置の編集モードでは、クリックはそちらの操作に使う
        if getattr(self, 'annotation_mode_enabled', False):
            return
        if getattr(self, 'layout_edit_mode_enabled', False):
            return

        artist = event.artist

        # タイトルなら、そのサブプロットを編集対象にする
        for ax_index, ax in enumerate(self.all_axes):
            if artist is ax.title:
                if self.active_axis_combo.currentIndex() != ax_index:
                    self.active_axis_combo.setCurrentIndex(ax_index)
                return

        # 系列なら、そのデータセットを一覧で選ぶ。Bar は BarContainer なので、patches に含まれるかで見る
        owning_dataset = next(
            (ds for ds in self.project.datasets
             if ds.artist is artist or (hasattr(ds.artist, 'patches') and artist in ds.artist.patches)),
            None
        )
        if owning_dataset is None:
            return

        item = self._get_dataset_tree_item(owning_dataset)
        if item is not None and self.ui.dataset_list_widget.currentItem() is not item:
            self.ui.dataset_list_widget.setCurrentItem(item)

    def _on_pick(self, event):
        if not self.cursor_mode_enabled: return

        artist = event.artist
        mouseevent = event.mouseevent

        x, y = None, None
        ind = None


        if hasattr(artist, 'get_offsets'):
            if len(event.ind) > 0:
                 ind = event.ind[0]
                 x, y = artist.get_offsets()[ind]

        elif hasattr(artist, 'get_xdata'):
            xdata = artist.get_xdata()
            ydata = artist.get_ydata()

            # クリックの位置にいちばん近い点
            distances = np.sqrt((xdata - mouseevent.xdata)**2 + (ydata - mouseevent.ydata)**2)

            ind = np.argmin(distances)
            x, y = xdata[ind], ydata[ind]

        else:
            return

        if x is not None and y is not None:
            # x, y はウォーターフォールのずらしが掛かった表示座標。矢印はそのままの位置に出し、
            # 表示する値だけデータ座標に戻す
            owning_dataset = next(
                (ds for ds in self.project.datasets if ds.artist is artist), None
            )
            if owning_dataset is not None:
                data_x, data_y = self.canvas.display_to_data(owning_dataset, x, y)
            else:
                data_x, data_y = x, y

            if self.cursor_annotation:
                self.cursor_annotation.remove()
                self.cursor_annotation = None

            ax = artist.axes
            text = f"X: {data_x:.4g}\nY: {data_y:.4g}"

            self.cursor_annotation = ax.annotate(text,
                xy=(x, y),
                xytext=(10, -10),
                textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.7),
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.3")
            )

            self.canvas.draw_idle()

            # データエディタが開いていれば、クリックした点の行を表でも選ぶ
            if ind is not None and self.data_editor_dialog is not None:
                if owning_dataset is not None and self.data_editor_dialog.dataset is owning_dataset:
                    try:
                        # ind は描いた点(visible_df、間引いていれば間引いた後)の位置。
                        # 間引いた系列は downsample_index_map で元の位置に戻してから visible_df.index を引く
                        index_map = self.canvas.downsample_index_map.get(owning_dataset.dataset_id)
                        if index_map is not None:
                            ind = index_map[ind]
                        master_index = owning_dataset.visible_df.index[ind]
                        # 選択の通知は止めてあるので、グラフ側の強調はここで更新する
                        self.data_editor_dialog.select_row_by_master_index(master_index)
                        self.canvas.set_highlighted_points(
                            owning_dataset, self.data_editor_dialog.get_selected_master_indices()
                        )
                    except IndexError:
                        pass
