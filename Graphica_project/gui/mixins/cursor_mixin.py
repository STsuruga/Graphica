# gui/mixins/cursor_mixin.py
"""
グラフ上のデータ点をクリックして座標を確認する「データカーソル」機能をまとめた Mixin。
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)


class CursorMixin:
    def _toggle_cursor_mode(self, checked: bool):
        """
        データカーソルモードのツールバーボタンが押されたときに呼び出されるスロット。
        モードの ON/OFF を切り替えます。

        Args:
            checked (bool): ボタンがチェックされた状態 (ON) かどうか。
        """
        self.cursor_mode_enabled = checked

        if checked:
            # 注釈モードと同時に有効だと同じクリックが両方に反応してしまうため排他にする
            if getattr(self, 'annotation_mode_enabled', False):
                self.annotation_action.setChecked(False)
                self._toggle_annotation_mode(False)

            # --- モード ON ---
            logger.debug("データカーソルモード ON")
            self.coordinate_label.setText("クリックしてデータを選択")

            # 1. Matplotlib の 'pick_event' を _on_pick メソッドに接続
            self.cursor_connection_id = self.canvas.mpl_connect(
                'pick_event', self._on_pick
            )

            # 2. すべてのプロット要素 (線, 点) をピック可能にする
            #    (all_secondary_axes には None が含まれる可能性があるのでチェック)
            all_valid_axes = [ax for ax in self.all_axes + self.all_secondary_axes if ax is not None]
            for ax in all_valid_axes:
                # ax.get_lines() -> plot() で描画された線 (Line2D)
                # ax.collections -> scatter() で描画された点 (PathCollection)
                for item in ax.get_lines() + ax.collections:
                    try:
                        # set_picker(5) : マウスクリック位置から 5 ピクセル以内を検出範囲とする
                        item.set_picker(5)
                    except AttributeError:
                        # (一部の Matplotlib アーティストは set_picker を持たない場合がある)
                        logger.warning("オブジェクト %s は set_picker をサポートしていません。", item)
        else:
            # --- モード OFF ---
            logger.debug("データカーソルモード OFF")
            self.coordinate_label.setText("X= ---, Y= ---")

            # 1. 'pick_event' の接続を切断
            if self.cursor_connection_id:
                self.canvas.mpl_disconnect(self.cursor_connection_id)
                self.cursor_connection_id = None

            # ★ バグ修正: 以前はここで全Artistに set_picker(False) していたが、
            # matplotlibのpickerは1アーティストにつき1つのフラグしか持てず、
            # gui/canvas.py の _enable_element_picking() が (データカーソル
            # モードのON/OFFと無関係に) 「クリックでデータセットを選択」機能
            # (項目35、常時有効)のために同じArtistへ set_picker(5) を設定
            # している。ここで無条件に False へ戻すと、データカーソルを
            # オフにした瞬間から次のフル再描画が起きるまでの間、項目35の
            # クリック選択が全く反応しなくなっていた(エラーも出ないため
            # 気づきにくいサイレントな機能破壊)。ピック可否の制御は
            # canvas.py側の責務に一本化し、ここでは pick_event の購読解除
            # (=データカーソル自身の反応)だけを行う。

            # 2. 表示中の注釈があれば削除
            if self.cursor_annotation:
                self.cursor_annotation.remove()
                self.cursor_annotation = None
                self.canvas.draw_idle() # 削除を画面に反映

    def _on_mouse_move(self, event):
        """マウスがキャンバス上を移動したときに呼び出される (motion_notify_event)"""

        # event.inaxes は、マウスカーソルが現在どの Axes の内側にあるかを示す
        # (Axes の外側なら None)
        if event.inaxes:
            ax = event.inaxes
            x, y = event.xdata, event.ydata # その Axes でのデータ座標

            # ★ オプション: どのサブプロット上の座標かを表示
            try:
                # ax が self.all_axes の何番目にあるかを探す
                ax_index = self.all_axes.index(ax)
                ax_label = f"P{ax_index+1}: " # 例: "P1: "
            except ValueError:
                # (ax が第2軸などで all_axes に見つからなかった場合)
                 try:
                      # ★ 第2軸の場合もインデックスを表示
                      sec_ax_index = self.all_secondary_axes.index(ax)
                      ax_label = f"P{sec_ax_index+1}(Y2): "
                 except ValueError:
                      ax_label = "?: " # 不明な軸

            # ステータスバーのテキストを更新 (: .4g は有効数字4桁で表示)
            self.coordinate_label.setText(f"{ax_label}X= {x:.4g}, Y= {y:.4g}")

        else: # Axes の外側にマウスがある場合
            # データカーソルモードが OFF ならデフォルト表示に戻す
            if not self.cursor_mode_enabled:
                self.coordinate_label.setText("X= ---, Y= ---")
            # (カーソルモード ON の場合は、最後の座標を表示し続ける方が良いかもしれない)

    def _on_element_pick(self, event):
        """
        グラフ要素の直接クリック選択(項目35)。データセットリストを介さず、
        グラフ上のデータ系列やタイトルを直接クリックして選択・編集できるようにする。
        データカーソル/注釈モードのON/OFFに関わらず常時有効な、独立したpick_event接続。
        """
        # 注釈モード中はクリックがテキスト/矢印の追加・削除操作として使われるため、
        # 選択処理と競合しないようここでは何もしない。
        if getattr(self, 'annotation_mode_enabled', False):
            return
        # 自由配置レイアウトの編集モード中は、クリックはサブプロットの移動/リサイズに
        # 使われるため、要素選択とは競合しないようここでは何もしない。
        if getattr(self, 'layout_edit_mode_enabled', False):
            return

        artist = event.artist

        # 1. タイトルがクリックされた場合: そのサブプロットを編集対象に切り替える
        for ax_index, ax in enumerate(self.all_axes):
            if artist is ax.title:
                if self.active_axis_combo.currentIndex() != ax_index:
                    self.active_axis_combo.setCurrentIndex(ax_index)
                return

        # 2. データ系列がクリックされた場合: 対応するデータセットをリストで選択する
        #    (Bar は BarContainer のためds.artist自体とは一致せず、
        #     patches (Rectangleの集合) の中にクリックされたArtistが含まれるかで判定する)
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
        """データ要素がクリックされたときに呼び出される (pick_event)"""

        # カーソルモードが OFF なら何もしない
        if not self.cursor_mode_enabled: return

        # クリックされた Artist (Line2D or PathCollection) とマウスイベントを取得
        artist = event.artist
        mouseevent = event.mouseevent

        x, y = None, None # 最終的に特定するデータ座標
        ind = None        # データ点のインデックス

        # --- クリックされたのが Scatter (点) か Line (線) かで処理を分岐 ---

        # 1. Scatter の場合 (PathCollection)
        #    get_offsets() メソッドを持っているかで判定 (より堅牢なのは isinstance)
        #    if isinstance(artist, matplotlib.collections.PathCollection):
        if hasattr(artist, 'get_offsets'):
            # event.ind にクリックされた点(複数可)のインデックスのリストが入っている
            # ここでは最初の点 (最も近い点) のインデックスを取得
            if len(event.ind) > 0:
                 ind = event.ind[0]
                 # get_offsets() は [(x1, y1), (x2, y2), ...] という形式のデータを返す
                 x, y = artist.get_offsets()[ind]

        # 2. Line の場合 (Line2D)
        #    get_xdata() メソッドを持っているかで判定
        #    elif isinstance(artist, matplotlib.lines.Line2D):
        elif hasattr(artist, 'get_xdata'):
            xdata = artist.get_xdata()
            ydata = artist.get_ydata()

            # マウスクリック位置 (mouseevent.xdata, ydata) に
            # 最も近いデータ点 (xdata[i], ydata[i]) のインデックスを見つける

            # (単純なユークリッド距離で計算)
            distances = np.sqrt((xdata - mouseevent.xdata)**2 + (ydata - mouseevent.ydata)**2)

            # distances 配列の中で最小値を持つ要素のインデックスを取得
            ind = np.argmin(distances)
            x, y = xdata[ind], ydata[ind]

        else: # クリックされたのが Line や Scatter でない場合
            return

        # --- 座標が特定できたら、注釈 (Annotation) を表示 ---
        if x is not None and y is not None:

            # 3. 以前の注釈があれば削除
            if self.cursor_annotation:
                self.cursor_annotation.remove()
                self.cursor_annotation = None # 参照をクリア (GCのため)

            # 4. 新しい注釈を作成
            ax = artist.axes # 注釈を表示する Axes を取得
            text = f"X: {x:.4g}\nY: {y:.4g}" # 2行で表示

            self.cursor_annotation = ax.annotate(text,
                xy=(x, y),                      # 矢印が指す座標 (データ点)
                xytext=(10, -10),                 # テキストを表示する位置 (データ点からのオフセット[ピクセル])
                textcoords="offset points",     # xytext がオフセットであることを示す
                bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.7), # 黄色い背景ボックス
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.3") # 矢印のスタイル
            )

            # 5. 注釈の描画を更新
            self.canvas.draw_idle()

            # 6. データ⇔グラフの双方向ハイライト (逆方向):
            #    クリックされた点の属するデータセットのデータエディタが開いていれば、
            #    対応する行をテーブル側でも選択状態にする。
            #    (ds.artist は _draw_data で描画のたびに設定される、そのデータセットの
            #     最新のArtistへの参照。identityで一致するものを探す)
            if ind is not None and self.data_editor_dialog is not None:
                owning_dataset = next(
                    (ds for ds in self.project.datasets if ds.artist is artist), None
                )
                if owning_dataset is not None and self.data_editor_dialog.dataset is owning_dataset:
                    try:
                        # ★ artistはvisible_df(マスクされた行を除いたもの)基準で描画されて
                        # いるため、indの位置からラベルへの変換もvisible_df.indexで行う。
                        # ただし項目C-1001(表示用ダウンサンプリング)が適用されている
                        # データセットでは、artistに実際に描かれているのはLTTBで間引いた
                        # 後の点であり、indはその間引き後の配列上の位置になる。そのため
                        # 先にdownsample_index_mapで「間引き後の位置→元のvisible_df上の
                        # 位置」へ変換してから、visible_df.indexを引く必要がある
                        # (このマップを経由しないと、間引き適用時に誤った行がハイライト
                        # される)。間引きが適用されていないデータセットはマップに
                        # 現れないため、indをそのまま使う。
                        index_map = self.canvas.downsample_index_map.get(owning_dataset.dataset_id)
                        if index_map is not None:
                            ind = index_map[ind]
                        master_index = owning_dataset.visible_df.index[ind]
                        # 選択変更のシグナルはブロックされているため(無限ループ防止)、
                        # グラフ側のハイライトはここで明示的に更新する
                        self.data_editor_dialog.select_row_by_master_index(master_index)
                        self.canvas.set_highlighted_points(
                            owning_dataset, self.data_editor_dialog.get_selected_master_indices()
                        )
                    except IndexError:
                        pass
