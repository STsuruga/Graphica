import logging

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from graphica.core.axis_settings import axis_setting
from graphica.gui.app_settings import DEFAULT_POINT_LABEL_MAX_POINTS
from graphica.gui.rendering import annotations, appearance, data_1d, data_2d
# 描画の定数と補助は rendering/common.py にある。テストとほかのモジュールがここから読むので同じ名前で出す
from graphica.gui.rendering.common import (  # noqa: F401
    _NO_KEY, MAX_TICKS_PER_AXIS, WATERFALL_ZORDER_BASE, WATERFALL_ZORDER_TOP, waterfall_offset_steps,
    WATERFALL_DEPTH_SHRINK_MIN_SCALE, _LAYOUT_SETTLED_TOLERANCE, _LAYOUT_MAX_PASSES, fit_tight_layout,
    _waterfall_depth_scale, _WaterfallLayout, _waterfall_layout, _AxisStyle, _LOG_MINOR_SUBS_PRESETS,
    _ARROW_STYLE_MAP, _INSET_CORNER_ORIGINS, LTTB_DOWNSAMPLE_THRESHOLD, LTTB_DOWNSAMPLE_TARGET_POINTS,
    GRID_2D_MAX_DISPLAY_POINTS_PER_AXIS, REGION_HIGHLIGHT_DEFAULT_COLOR, REGION_HIGHLIGHT_DEFAULT_ALPHA,
    _apply_legend_order, _apply_nan_policy, STAT_LABEL_TITLES, _legend_position_from_settings,
    _compute_stat_label_text, _safe_multiple_locator, _sci_each_formatter, _apply_tick_format_mode,
    _apply_tick_decimal_places, DEFAULT_MAJOR_TICK_LENGTH, MINOR_TICK_LENGTH_RATIO, MINOR_TICK_LENGTH_AUTO,
    _resolve_tick_lengths, DARK_FIGURE_FACECOLOR, DARK_AXES_FACECOLOR, DARK_TEXT_COLOR, LIGHT_FIGURE_FACECOLOR,
    LIGHT_AXES_FACECOLOR, LIGHT_TEXT_COLOR, DARK_LEGEND_FACECOLOR, DARK_LEGEND_EDGECOLOR, LIGHT_LEGEND_FACECOLOR,
    LIGHT_LEGEND_EDGECOLOR, DARK_GRID_COLOR, LIGHT_GRID_COLOR)

logger = logging.getLogger(__name__)


class _CanvasDrawingMixin:
    """
    描画の本体。Qt に依存しないので、画面用の MplCanvas(FigureCanvasQTAgg)と
    一括エクスポート用の _HeadlessRenderCanvas(FigureCanvasAgg)の両方が使う。
    """

    def _init_drawing_state(self, width, height, dpi):
        self.fig = Figure(figsize=(width, height), dpi=dpi)

        self.all_axes = []
        self.all_secondary_axes = []
        # 軸ごとに、X が日時か(目盛りの付け方)・文字列カテゴリか(数値向けの設定を使わない)
        self.axis_is_date_x = []
        self.axis_is_category_x = []
        self.dark_mode = False
        self.point_label_max_points = DEFAULT_POINT_LABEL_MAX_POINTS
        # 軸ごとの描画済みの注釈。update_appearance_only は fig.clf() しないので、消してから描き直す
        self._annotation_artists = {}
        # 軸ごとに直近に描いた注釈の内容。同じなら描き直しを省く(_annotation_render_key)
        self._annotation_render_keys = {}
        # データエディタと連動する行のハイライト(dataset_id ごと)
        self._highlight_artists = {}
        # 間引いたデータセットの「描いた点の添字 -> visible_df の位置」(dataset_id ごと)。
        # データカーソルがクリックした点を正しい行に戻すのに使う。間引いていなければ入らない
        self.downsample_index_map = {}
        # 平滑化した曲線のデータセット。点が元の行と対応しないのでクリックで選ばせない。
        # データカーソルモードの一括 set_picker(cursor_mixin.py)もこれを見て除く
        self._non_pickable_dataset_ids = set()
        # 軸ごとのカラーバーの対象(2Dマップか値で色分けした散布図)。_apply_appearance に渡すため
        self._axis_2d_mappables = {}
        # マウスで変えた表示範囲。{サブプロットの番号: {'x'/'y'/'y2': (範囲, 範囲の設定の署名)}}。
        # 描き直しても保ち、その軸の範囲の設定が変わったら忘れる(rendering/appearance.apply_view_override)
        self.view_overrides = {}
        # ウォーターフォールの変換(dataset_id ごと)。トレースは
        #     表示X = データX + index * offset_x
        #     表示Y = データY * depth_scale + index * offset_y
        # に描かれるので、マウス位置をデータの行に対応づける側は逆変換(display_to_data)を通す。
        # 値は {'index', 'offset_x', 'offset_y', 'depth_scale', 'mode'}。ウォーターフォールでなければ入らない
        self._waterfall_transforms = {}
        # 軸の番号 -> ウォーターフォールでトレースを X にずらした幅 (左へ, 右へ)。手動の範囲をその分広げる
        self.waterfall_x_shift = {}

    # --- ウォーターフォールの表示座標 ⇔ データ座標 ---

    def get_waterfall_transform(self, dataset_or_id):
        """
        データセットの今のウォーターフォール変換。無効または未描画なら None。

        Args:
            dataset_or_id: Dataset オブジェクト、または dataset_id。
        """
        dataset_id = getattr(dataset_or_id, 'dataset_id', dataset_or_id)
        return self._waterfall_transforms.get(dataset_id)

    def data_to_display(self, dataset_or_id, x, y):
        """データ座標(dataset.x_data/y_data と同じ)を、描かれている位置へ変換する。スカラーでも配列でもよい。ウォーターフォールでなければそのまま返す。"""
        transform = self.get_waterfall_transform(dataset_or_id)
        if transform is None:
            return x, y
        steps = waterfall_offset_steps(transform['index'], transform.get('mode'))
        display_x = x if transform['offset_x'] == 0 else x + steps * transform['offset_x']
        display_y = y * transform['depth_scale'] + steps * transform['offset_y']
        return display_x, display_y

    def display_to_data(self, dataset_or_id, x, y):
        """
        data_to_display() の逆。マウス位置をデータの行に対応づける処理(範囲選択・データカーソル・
        エディタ連動のハイライト・ピーク配置)は必ずこれを通す。通さないと積み重ねの2本目以降で位置がずれる。
        """
        transform = self.get_waterfall_transform(dataset_or_id)
        if transform is None:
            return x, y
        steps = waterfall_offset_steps(transform['index'], transform.get('mode'))
        data_x = x if transform['offset_x'] == 0 else x - steps * transform['offset_x']
        # depth_scale は 0.2 以上に抑えてあるので 0 で割ることはない
        data_y = (y - steps * transform['offset_y']) / transform['depth_scale']
        return data_x, data_y

    def _effective_text_color(self, configured_color):
        """ダークモードで既定の黒のままだと見えないので明るい色にする。利用者が選んだ別の色はそのまま。"""
        if self.dark_mode and configured_color == '#000000':
            return DARK_TEXT_COLOR
        return configured_color

    def _default_free_rect(self, index):
        """自由配置で新しい軸に割り当てる初期の (left, bottom, width, height)。少しずつずらして重ならないようにする。"""
        offset = 0.04 * (index % 6)
        left = min(0.1 + offset, 0.55)
        bottom = min(0.55 - offset, 0.55) if index % 2 == 0 else min(0.1 + offset, 0.5)
        return (left, max(bottom, 0.08), 0.45, 0.38)

    def _safe_draw(self):
        """
        self.draw() の失敗をログに残す。直接の draw() は例外を投げても、呼び出し元のシグナルの経路によっては
        どこにも記録されず「何も反映されない」だけになる(draw_idle 側は matplotlib が標準エラーに出すだけで、
        画面版の exe ではそれも見えない)。
        """
        try:
            self.draw()
        except Exception:
            logger.exception(
                "Figureの描画(self.draw())に失敗しました。"
                "グラフの表示が更新されていない可能性があります。"
            )

    def redraw_all(self, datasets, rows, cols, all_plot_settings, layout_mode='grid', panel_labels_enabled=False,
                    share_x_axis=False, share_y_axis=False, full_resolution=False):
        """
        Figure を作り直して全部の軸を描く。full_resolution=True なら間引かない(エクスポートの「フル解像度」)。
        非表示のデータセットも含めて _draw_data に渡すこと(ウォーターフォールの段の振り方のため。_draw_data 参照)。
        """
        self.fig.clf()
        self.all_axes.clear()
        self.all_secondary_axes.clear()
        self.axis_is_date_x.clear()
        self.axis_is_category_x.clear()
        # fig.clf() で古い artist はすべて消えるので、参照を捨てるだけでよい
        self._annotation_artists.clear()
        self._annotation_render_keys.clear()
        self._highlight_artists.clear()
        self.downsample_index_map.clear()
        self._non_pickable_dataset_ids.clear()
        self._axis_2d_mappables.clear()
        self._waterfall_transforms.clear()
        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)

        is_free_layout = layout_mode == 'free'
        subplot_count = len(all_plot_settings) if is_free_layout else rows * cols
        if subplot_count == 0:
            return False

        is_secondary_visible_global = False

        if is_free_layout:
            for i in range(subplot_count):
                rect = axis_setting(all_plot_settings[i], 'free_rect') or self._default_free_rect(i)
                ax = self.fig.add_axes(rect)
                self.all_axes.append(ax)
                self.all_secondary_axes.append(None)
        else:
            # 軸の共有は、行・列ごとではなく全部の軸を最初の軸に束ねる
            for i in range(subplot_count):
                share_x_target = self.all_axes[0] if (share_x_axis and self.all_axes) else None
                share_y_target = self.all_axes[0] if (share_y_axis and self.all_axes) else None
                ax = self.fig.add_subplot(rows, cols, i + 1, sharex=share_x_target, sharey=share_y_target)
                self.all_axes.append(ax)
                self.all_secondary_axes.append(None)

        for index, ax in enumerate(self.all_axes):
            if index < len(all_plot_settings):
                settings = all_plot_settings[index]
            else:
                continue

            self._draw_data(ax, index, datasets, full_resolution=full_resolution)
            self._apply_appearance(ax, index, settings)
            # _apply_appearance が目盛数値の表示を毎回設定し直すので、共有で隠すのはその後
            if not is_free_layout:
                self._apply_shared_axis_tick_visibility(index, rows, cols, share_x_axis, share_y_axis)
            self._draw_annotations(ax, index, settings, datasets=datasets, full_resolution=full_resolution)
            if panel_labels_enabled:
                self._draw_panel_label(ax, index)

            if self.all_secondary_axes[index] is not None:
                is_secondary_visible_global = True

        if not is_free_layout:
            # 自由配置は利用者が決めた位置を tight_layout が上書きするので、グリッドだけ。
            # matplotlib の予備フォント(LastResortHE)が欠けた環境では FileNotFoundError になるので、配置を諦めて続ける
            try:
                fit_tight_layout(self.fig)
            except (ValueError, FileNotFoundError):
                pass

        self._safe_draw()
        return is_secondary_visible_global

    def update_appearance_only(self, all_plot_settings, datasets=(), rows=1, cols=1,
                                layout_mode='grid', share_x_axis=False, share_y_axis=False):
        """
        データはそのままで見た目の設定だけを当て直す。datasets は統計値ラベルの計算にだけ使う
        (省略すると統計値ラベルが「データセットなし」になるだけ)。
        """
        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)
        is_free_layout = layout_mode == 'free'
        for index, ax in enumerate(self.all_axes):
            if index < len(all_plot_settings):
                settings = all_plot_settings[index]
                self._apply_appearance(ax, index, settings)
                # redraw_all と同じく、共有で隠すのは _apply_appearance の後
                if not is_free_layout:
                    self._apply_shared_axis_tick_visibility(index, rows, cols, share_x_axis, share_y_axis)
                # この経路だけ軸を cla() しないので、内容が同じなら注釈を使い回せる
                self._draw_annotations(ax, index, settings, datasets=datasets,
                                       allow_reuse=True)
        try:
            fit_tight_layout(self.fig)
        except (ValueError, FileNotFoundError):
            # フォントが欠けた環境の対策(redraw_all 参照)
            pass
        self._safe_draw()

    def _apply_shared_axis_tick_visibility(self, axis_index, rows, cols, share_x_axis, share_y_axis):
        """軸の共有が有効なら、内側の目盛数値(最下行以外の X・最左列以外の Y)を隠す。自由配置(cols=0)では何もしない。"""
        if cols <= 0:
            return
        row_idx, col_idx = divmod(axis_index, cols)
        ax = self.all_axes[axis_index]
        if share_x_axis and row_idx != rows - 1:
            ax.tick_params(labelbottom=False)
        if share_y_axis and col_idx != 0:
            ax.tick_params(labelleft=False)

    def _redraw_single_axis_no_draw(self, axis_index, datasets, settings, rows=1, cols=1,
                                     share_x_axis=False, share_y_axis=False, panel_labels_enabled=False,
                                     full_resolution=False):
        """update_single_axis() の、draw を呼ぶ手前まで(全軸をまとめて描き直すときに draw を1回で済ませるため)。"""
        if axis_index >= len(self.all_axes):
            return

        # twinx() の第2軸は cla() では消えないので、取り除かないと呼ぶたびに積み重なる
        old_secondary = self.all_secondary_axes[axis_index]
        if old_secondary is not None:
            old_secondary.remove()
            self.all_secondary_axes[axis_index] = None

        ax = self.all_axes[axis_index]
        ax.cla()

        # cla() で古い artist は消えているので、参照を捨てるだけ
        self._annotation_artists.pop(axis_index, None)
        self._annotation_render_keys.pop(axis_index, None)
        for dataset_id in [ds.dataset_id for ds in datasets if ds.subplot_target == axis_index]:
            self._highlight_artists.pop(dataset_id, None)
            self.downsample_index_map.pop(dataset_id, None)
            self._non_pickable_dataset_ids.discard(dataset_id)

        self._draw_data(ax, axis_index, datasets, full_resolution=full_resolution)
        self._apply_appearance(ax, axis_index, settings)
        self._draw_annotations(ax, axis_index, settings, datasets=datasets, full_resolution=full_resolution)
        if panel_labels_enabled:
            self._draw_panel_label(ax, axis_index)

        self._apply_shared_axis_tick_visibility(axis_index, rows, cols, share_x_axis, share_y_axis)

    def update_single_axis(self, axis_index, datasets, settings, rows=1, cols=1,
                            share_x_axis=False, share_y_axis=False, panel_labels_enabled=False,
                            full_resolution=False):
        """
        1つの軸だけを描き直す。Figure とほかの軸には触らない。データセットの見た目や描画先・第2Y軸の変更用
        (描画先の変更は旧・新の軸それぞれで呼ぶ)。軸の数や配置が変わるときは redraw_all() か
        add_free_axis()/remove_last_free_axis() を使う。
        """
        self._redraw_single_axis_no_draw(
            axis_index, datasets, settings, rows=rows, cols=cols,
            share_x_axis=share_x_axis, share_y_axis=share_y_axis,
            panel_labels_enabled=panel_labels_enabled, full_resolution=full_resolution,
        )
        self.draw_idle()

    def add_free_axis(self, datasets, settings, panel_labels_enabled=False):
        """自由配置の末尾に軸を1つ足す(ほかの軸には触らない)。足す軸はどのデータセットからも参照されていない。"""
        rect = axis_setting(settings, 'free_rect') or self._default_free_rect(len(self.all_axes))
        ax = self.fig.add_axes(rect)
        self.all_axes.append(ax)
        self.all_secondary_axes.append(None)
        self.axis_is_date_x.append(False)
        self.axis_is_category_x.append(False)

        axis_index = len(self.all_axes) - 1
        self._draw_data(ax, axis_index, datasets)
        self._apply_appearance(ax, axis_index, settings)
        self._draw_annotations(ax, axis_index, settings, datasets=datasets)
        if panel_labels_enabled:
            self._draw_panel_label(ax, axis_index)

        self.draw_idle()

    def remove_last_free_axis(self, datasets):
        """
        自由配置の末尾の軸を消す(ほかの軸には触らない)。消す軸のデータセットは、呼び出し側が先に
        新しい末尾の軸へ付け替え、描き直しも update_single_axis() で行うこと。
        """
        if not self.all_axes:
            return
        removed_index = len(self.all_axes) - 1

        secondary = self.all_secondary_axes[removed_index]
        if secondary is not None:
            secondary.remove()
        self.all_axes[removed_index].remove()

        self.all_axes.pop()
        self.all_secondary_axes.pop()
        if removed_index < len(self.axis_is_date_x):
            self.axis_is_date_x.pop()
        if removed_index < len(self.axis_is_category_x):
            self.axis_is_category_x.pop()

        self._annotation_artists.pop(removed_index, None)
        self._annotation_render_keys.pop(removed_index, None)
        for dataset_id in [ds.dataset_id for ds in datasets if ds.subplot_target == removed_index]:
            self._highlight_artists.pop(dataset_id, None)
            self.downsample_index_map.pop(dataset_id, None)
            self._non_pickable_dataset_ids.discard(dataset_id)

        self.draw_idle()

    def update_all_axes_appearance_and_data(self, datasets, rows, cols, all_plot_settings, layout_mode='grid',
                                             panel_labels_enabled=False, share_x_axis=False, share_y_axis=False,
                                             full_resolution=False):
        """
        軸の数と配置を変えずに、全部の軸のデータと見た目を描き直す(パネルラベルやダークモードの切り替え用)。
        fig.clf() しないので、軸の数や配置が変わるときには使えない。draw などの Figure 全体の処理は最後に1回だけ。
        """
        is_free_layout = layout_mode == 'free'
        is_secondary_visible_global = False

        for index in range(len(self.all_axes)):
            if index >= len(all_plot_settings):
                continue
            settings = all_plot_settings[index]
            self._redraw_single_axis_no_draw(
                index, datasets, settings, rows=rows, cols=cols,
                share_x_axis=share_x_axis, share_y_axis=share_y_axis,
                panel_labels_enabled=panel_labels_enabled, full_resolution=full_resolution,
            )
            if self.all_secondary_axes[index] is not None:
                is_secondary_visible_global = True

        self.fig.set_facecolor(DARK_FIGURE_FACECOLOR if self.dark_mode else LIGHT_FIGURE_FACECOLOR)
        if not is_free_layout:
            # 自由配置には tight_layout を掛けない・フォントが欠けた環境の対策(redraw_all 参照)
            try:
                fit_tight_layout(self.fig)
            except (ValueError, FileNotFoundError):
                pass

        self._safe_draw()
        return is_secondary_visible_global

    def _draw_panel_label(self, ax, index):
        return annotations.draw_panel_label(self, ax, index)

    @staticmethod
    def _panel_label_for_index(index):
        return annotations.panel_label_for_index(index)

    def _downsample_for_inset(self, x_data, y_data, full_resolution=False):
        return annotations.downsample_for_inset(self, x_data, y_data, full_resolution)

    def _annotation_render_key(self, axis_index, settings, datasets, full_resolution, parent_ax=None):
        return annotations.annotation_render_key(self, axis_index, settings, datasets, full_resolution, parent_ax)

    def _draw_annotations(self, ax, axis_index, settings, datasets=None, full_resolution=False,
                          allow_reuse=False):
        return annotations.draw_annotations(self, ax, axis_index, settings, datasets, full_resolution, allow_reuse)

    def _enable_element_picking(self, artist):
        return data_1d.enable_element_picking(self, artist)

    def _add_gradient_line(self, ax, x, y, color1, color2, linewidth, alpha, linestyle, label=None):
        return data_1d.add_gradient_line(self, ax, x, y, color1, color2, linewidth, alpha, linestyle, label)

    def _add_gradient_fill(self, ax, x, y, color1, color2, alpha, baseline=0.0):
        return data_1d.add_gradient_fill(self, ax, x, y, color1, color2, alpha, baseline)

    _VALID_MAP_DISPLAY_MODES = ('heatmap', 'contour', 'contour_filled', 'heatmap_contour')

    def _draw_2d_data(self, ax, axis_index, datasets_2d, full_resolution=False):
        return data_2d.draw_2d_data(self, ax, axis_index, datasets_2d, full_resolution)

    def _draw_data(self, ax, axis_index, datasets, full_resolution=False):
        return data_1d.draw_data(self, ax, axis_index, datasets, full_resolution)

    def _record_x_axis_kind(self, axis_index, datasets):
        return data_1d.record_x_axis_kind(self, axis_index, datasets)

    def _draw_1d_dataset(self, target_ax, axis_index, ds, waterfall, is_category_x, full_resolution):
        return data_1d.draw_1d_dataset(self, target_ax, axis_index, ds, waterfall, is_category_x, full_resolution)

    def _waterfall_shifted_points(self, ds, waterfall, is_category_x):
        return data_1d.waterfall_shifted_points(self, ds, waterfall, is_category_x)

    def _downsample_for_display(self, ds, plot_x_data, plot_y_data, is_category_x, full_resolution):
        return data_1d.downsample_for_display(self, ds, plot_x_data, plot_y_data, is_category_x, full_resolution)

    def _draw_smoothed(self, target_ax, ds, plot_x_data, plot_y_data, plot_kwargs):
        return data_1d.draw_smoothed(self, target_ax, ds, plot_x_data, plot_y_data, plot_kwargs)

    def _draw_plot_type(self, target_ax, axis_index, ds, plot_x_data, plot_y_data, plot_kwargs):
        return data_1d.draw_plot_type(self, target_ax, axis_index, ds, plot_x_data, plot_y_data, plot_kwargs)

    def _draw_error_display(self, target_ax, ds, plot_x_data, plot_y_data, downsample_indices):
        return data_1d.draw_error_display(self, target_ax, ds, plot_x_data, plot_y_data, downsample_indices)

    def set_highlighted_points(self, dataset, master_indices):
        """
        データエディタで選んだ行の点をグラフ上で丸く囲む。

        Args:
            dataset (Dataset): 対象のデータセット。
            master_indices (list): dataset.df.index のラベル。空ならこのデータセットのハイライトを消す。
        """
        old_artist = self._highlight_artists.pop(dataset.dataset_id, None)
        if old_artist is not None:
            try:
                old_artist.remove()
            except (ValueError, NotImplementedError):
                pass

        if not master_indices:
            self.draw_idle()
            return

        axis_index = dataset.subplot_target
        if axis_index >= len(self.all_axes):
            self.draw_idle()
            return

        if dataset.use_secondary_y and axis_index < len(self.all_secondary_axes) \
                and self.all_secondary_axes[axis_index] is not None:
            ax = self.all_secondary_axes[axis_index]
        else:
            ax = self.all_axes[axis_index]

        try:
            # x_data/y_data は visible_df の並びなので、位置も visible_df.index で引く(除外した行は描かれていない)
            visible_index = dataset.visible_df.index
            positions = [visible_index.get_loc(idx) for idx in master_indices if idx in visible_index]
        except Exception:
            logger.exception("ハイライト対象の行インデックス変換に失敗しました。")
            positions = []

        if not positions:
            self.draw_idle()
            return

        x_vals = dataset.x_data[positions]
        y_vals = dataset.y_data[positions]
        # ウォーターフォールでずらした位置に合わせる
        x_vals, y_vals = self.data_to_display(dataset, x_vals, y_vals)
        artist = ax.scatter(
            x_vals, y_vals, s=160, facecolors='none', edgecolors='#e6194b',
            linewidths=2.0, zorder=15
        )
        self._highlight_artists[dataset.dataset_id] = artist
        self.draw_idle()

    def _draw_point_labels(self, ax, ds, x_data=None, y_data=None, downsample_indices=None):
        return data_1d.draw_point_labels(self, ax, ds, x_data, y_data, downsample_indices)

    def _apply_appearance(self, ax, axis_index, settings):
        return appearance.apply_appearance(self, ax, axis_index, settings)

    def _apply_limits_and_scale(self, ax, settings, is_category_x, axis_index=None):
        return appearance.apply_limits_and_scale(self, ax, settings, is_category_x, axis_index)

    def _apply_tick_locators(self, ax, settings, is_date_x, is_category_x):
        return appearance.apply_tick_locators(self, ax, settings, is_date_x, is_category_x)

    def _axis_text_and_line_style(self, settings):
        return appearance.axis_text_and_line_style(self, settings)

    def _apply_titles_and_labels(self, ax, settings, style):
        return appearance.apply_titles_and_labels(self, ax, settings, style)

    def _apply_spines_and_tick_marks(self, ax, settings, style):
        return appearance.apply_spines_and_tick_marks(self, ax, settings, style)

    def _apply_legend(self, ax, secondary_ax, settings):
        return appearance.apply_legend(self, ax, secondary_ax, settings)

    def _apply_grid(self, ax, settings):
        return appearance.apply_grid(self, ax, settings)

    def _apply_secondary_y_axis(self, ax, secondary_ax, settings, style):
        return appearance.apply_secondary_y_axis(self, ax, secondary_ax, settings, style)

    def _apply_unit_conversion_x_axis(self, ax, settings, style, is_date_x, is_category_x):
        return appearance.apply_unit_conversion_x_axis(self, ax, settings, style, is_date_x, is_category_x)

    def _apply_colorbar(self, ax, axis_index, settings, style):
        return appearance.apply_colorbar(self, ax, axis_index, settings, style)


class MplCanvas(FigureCanvas, _CanvasDrawingMixin):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self._init_drawing_state(width, height, dpi)
        super().__init__(self.fig)
        self.setParent(parent)


class _HeadlessRenderCanvas(FigureCanvasAgg, _CanvasDrawingMixin):
    """一括エクスポート用の Qt に依存しないキャンバス。QWidget ではないので GUI スレッドの外で描いてよい。"""
    def __init__(self, width=5, height=4, dpi=100):
        self._init_drawing_state(width, height, dpi)
        super().__init__(self.fig)