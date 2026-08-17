# gui/mixins/cursor_mixin.py
"""
グラフ上のデータ点をクリックして座標を確認する「データカーソル」機能をまとめた Mixin。
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)


class CursorMixin:
    # --- マウス操作拡充(項目C-908): ホイールズーム + 中ボタンドラッグパン ---
    # matplotlib標準のNavigationToolbar2QTには、ドラッグ矩形選択によるZoom
    # ツール・クリック&ドラッグのPanツール・Home/Back/Forwardのズーム履歴は
    # 既にあるが、ホイールでのズームと、Panツールを明示的に選ばなくても常時
    # 使える中ボタンドラッグパンは無い。この2つは他の操作モード(データ
    # カーソル/注釈/自由配置編集、いずれも左クリックを使う)と衝突しない
    # 入力(スクロールホイール/中ボタン)のみを使うため、専用のON/OFF切り替え
    # なしに常時有効にする(項目35のクリック選択と同じ「常時有効」方針)。
    # ズーム/パンの対象は、matplotlib標準のPan/Zoomツールと同じくカーソルが
    # 乗っている軸(event.inaxes)のみ(ミニマップの「全サブプロット一括
    # ズーム」とは意図的に異なるスコープ)。

    def _on_scroll_zoom(self, event):
        """
        マウスホイールでのズーム(項目C-908)。カーソル位置を中心に、
        上スクロールで拡大・下スクロールで縮小する。
        """
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

        # カーソル位置が新しい範囲内でも同じ相対位置(relx/rely)に来るように、
        # 左右/上下で縮尺後の余白を配分する(カーソル位置を中心に拡大縮小
        # しているように見せるための計算)。
        old_width = xlim[1] - xlim[0]
        old_height = ylim[1] - ylim[0]
        relx = (xlim[1] - xdata) / old_width if old_width else 0.5
        rely = (ylim[1] - ydata) / old_height if old_height else 0.5

        ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
        ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        self.canvas.draw_idle()

    def _on_middle_button_press_pan(self, event):
        """中ボタンドラッグパンの開始(項目C-908)。押下時点の軸範囲とカーソルの
        データ座標を記憶しておき、以降のドラッグ量をそこからの差分で計算する。"""
        if event.button != 2 or event.inaxes is None:
            return
        if event.xdata is None or event.ydata is None:
            return
        self._middle_pan_axes = event.inaxes
        self._middle_pan_start_data = (event.xdata, event.ydata)
        self._middle_pan_start_xlim = event.inaxes.get_xlim()
        self._middle_pan_start_ylim = event.inaxes.get_ylim()

    def _on_middle_button_motion_pan(self, event):
        """
        中ボタンドラッグ中の軸範囲更新。押下時に記憶した軸範囲(固定)から、
        「押下位置のデータ座標」と「現在のカーソル位置のデータ座標(現在の
        軸範囲基準)」の差分だけずらした範囲を毎回計算して設定する
        (差分を毎回積み上げるのではなく、常に押下時の範囲を基準に計算し
        直すことで、誤差が蓄積しないようにしている)。
        """
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
        """中ボタンを離したらパン状態を解除する。"""
        if event.button != 2:
            return
        self._middle_pan_axes = None
        self._middle_pan_start_data = None
        self._middle_pan_start_xlim = None
        self._middle_pan_start_ylim = None

    def _toggle_cursor_mode(self, checked: bool):
        """
        データカーソルモードのツールバーボタンが押されたときに呼び出されるスロット。
        モードの ON/OFF を切り替えます。

        Args:
            checked (bool): ボタンがチェックされた状態 (ON) かどうか。
        """
        self.cursor_mode_enabled = checked

        if checked:
            # 注釈モード/範囲選択モードと同時に有効だと同じクリックが競合するため排他にする
            if getattr(self, 'annotation_mode_enabled', False):
                self.annotation_action.setChecked(False)
                self._toggle_annotation_mode(False)
            if getattr(self, 'range_select_mode_enabled', False):
                self.range_select_action.setChecked(False)
                self._toggle_range_select_mode(False)
            if getattr(self, 'peak_placement_mode_enabled', False):
                self.peak_placement_action.setChecked(False)
                self._toggle_peak_placement_mode(False)
            if getattr(self, 'slice_extraction_mode_enabled', False):
                self.slice_extraction_action.setChecked(False)
                self._toggle_slice_extraction_mode(False)

            # --- モード ON ---
            logger.debug("データカーソルモード ON")
            self.coordinate_label.setText("クリックしてデータを選択")

            # 1. Matplotlib の 'pick_event' を _on_pick メソッドに接続
            self.cursor_connection_id = self.canvas.mpl_connect(
                'pick_event', self._on_pick
            )

            # 2. すべてのプロット要素 (線, 点) をピック可能にする
            #    (all_secondary_axes には None が含まれる可能性があるのでチェック)
            # ★ 平滑化(CubicSpline)曲線のArtist(元データと1:1に対応しない200点の
            #   補間点、gui/canvas.py の_non_pickable_dataset_ids参照)は、この
            #   一括有効化からも除外する。ds.dataset_id→ds.artistの対応はこの
            #   呼び出しの直前(現在の描画結果)から都度組み立てるため、過去に
            #   破棄されたArtistオブジェクトのメモリアドレス再利用による誤った
            #   一致が起きる余地はない。
            non_pickable_artists = {
                ds.artist for ds in self.project.datasets
                if ds.dataset_id in self.canvas._non_pickable_dataset_ids and ds.artist is not None
            }
            all_valid_axes = [ax for ax in self.all_axes + self.all_secondary_axes if ax is not None]
            for ax in all_valid_axes:
                # ax.get_lines() -> plot() で描画された線 (Line2D)
                # ax.collections -> scatter() で描画された点 (PathCollection)
                for item in ax.get_lines() + ax.collections:
                    if item in non_pickable_artists:
                        continue
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
