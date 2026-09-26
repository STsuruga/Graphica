"""PlotterApp の一度きりの組み立て(シグナル、メニューバー、初めの画面の状態)と、ダークモードの切り替え。"""
from PySide6.QtWidgets import QApplication

from graphica.gui import app_settings
from graphica.gui.theme import apply_theme
from graphica.gui.dialogs import CommandPaletteDialog
from graphica.gui.datasets.actions_menu import populate_dataset_actions_menu
from graphica.gui.menu_bar import build_menu_bar


class UISetupMixin:
    def _connect_signals(self):
        """画面の部品のシグナルをつなぐ。__init__ から1回だけ。同じシグナルに複数つなぐものは、つないだ順に呼ばれる。"""
        self._connect_layout_signals()
        self._connect_axis_setting_signals()
        self._connect_dataset_signals()

    def _connect_layout_signals(self):
        self.subplot_rows_spinbox.valueChanged.connect(self._on_layout_changed)
        self.subplot_cols_spinbox.valueChanged.connect(self._on_layout_changed)

        self.share_x_checkbox.toggled.connect(self._on_share_axis_changed)
        self.share_y_checkbox.toggled.connect(self._on_share_axis_changed)

        self.active_axis_combo.currentIndexChanged.connect(self._on_active_axis_changed)

        self.free_layout_checkbox.toggled.connect(self._on_toggle_free_layout)
        self.add_free_subplot_button.clicked.connect(self._on_add_free_subplot)
        self.remove_free_subplot_button.clicked.connect(self._on_remove_free_subplot)

        self.free_layout_x_spinbox.valueChanged.connect(self._on_free_layout_position_spinbox_changed)
        self.free_layout_y_spinbox.valueChanged.connect(self._on_free_layout_position_spinbox_changed)
        self.free_layout_width_spinbox.valueChanged.connect(self._on_free_layout_position_spinbox_changed)
        self.free_layout_height_spinbox.valueChanged.connect(self._on_free_layout_position_spinbox_changed)

    def _connect_axis_setting_signals(self):
        # ほとんどの欄は、変わったら _on_axis_setting_changed で今の軸の設定に書き戻す

        self.ui.x_autoscale_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.x_autoscale_checkbox.stateChanged.connect(self._on_x_autoscale_changed)

        self.ui.y_autoscale_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.y_autoscale_checkbox.stateChanged.connect(self._on_y_autoscale_changed)

        self.ui.x_major_tick_mode_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.ui.x_major_tick_mode_combo.currentIndexChanged.connect(self._on_x_tick_mode_changed)

        self.ui.y_major_tick_mode_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.ui.y_major_tick_mode_combo.currentIndexChanged.connect(self._on_y_tick_mode_changed)

        self.ui.x_minor_ticks_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.x_minor_ticks_visible_checkbox.stateChanged.connect(self._on_x_minor_tick_visibility_changed)

        self.ui.y_minor_ticks_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.y_minor_ticks_visible_checkbox.stateChanged.connect(self._on_y_minor_tick_visibility_changed)

        self.ui.x_log_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        # 対数軸の補助目盛りの欄は対数表示にも左右されるので、対数表示のチェックにもつなぐ
        self.ui.x_log_checkbox.stateChanged.connect(self._on_x_minor_tick_visibility_changed)
        self.ui.x_invert_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.x_min_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.ui.x_max_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.ui.y_log_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.y_log_checkbox.stateChanged.connect(self._on_y_minor_tick_visibility_changed)
        self.ui.y_invert_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.y_min_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.ui.y_max_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.ui.x_major_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.ui.y_major_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.ui.x_minor_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.x_log_minor_subs_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.x_log_minor_labels_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.y_log_minor_subs_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.y_log_minor_labels_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.x_tick_format_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.y_tick_format_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.x_tick_decimals_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.y_tick_decimals_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.x_secondary_axis_source_unit_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.x_secondary_axis_target_unit_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        # タイトルと軸ラベルの編集ボタンは _build_label_editors でつないでいる
        self.ui.y_minor_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)

        self.ui.title_text_edit.textChanged.connect(self._on_axis_setting_changed)
        self.ui.x_label_text_edit.textChanged.connect(self._on_axis_setting_changed)
        self.ui.y_label_text_edit.textChanged.connect(self._on_axis_setting_changed)
        self.x_label_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.y_label_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.y2_label_text_edit.textChanged.connect(self._on_axis_setting_changed) # 第2Y軸ラベル

        self.ui.tick_font_button.clicked.connect(self._on_change_tick_font)
        self.ui.tick_color_button.clicked.connect(self._on_change_tick_color)
        self.ui.tick_width_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.major_tick_length_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.minor_tick_length_spinbox.valueChanged.connect(self._on_axis_setting_changed)

        self.ui.axis_label_font_button.clicked.connect(self._on_change_axis_label_font)
        self.ui.axis_label_color_button.clicked.connect(self._on_change_axis_label_color)

        self.legend_font_button.clicked.connect(self._on_change_legend_font)
        self.legend_color_button.clicked.connect(self._on_change_legend_color)
        self.legend_order_button.clicked.connect(self._on_edit_legend_order)

        self.ui.legend_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.legend_visible_checkbox.stateChanged.connect(self._on_legend_visibility_changed)
        self.legend_loc_combo.currentTextChanged.connect(self._on_legend_loc_changed)

        self.ui.grid_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        # グリッドのチェックは補助グリッドと詳細の欄の有効/無効も切り替える
        self.ui.grid_visible_checkbox.stateChanged.connect(self._on_grid_visibility_changed)
        self.ui.minor_grid_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.ui.minor_grid_visible_checkbox.stateChanged.connect(self._on_grid_visibility_changed)

        for grid_style_widget in (
            self.x_major_grid_linestyle_combo, self.x_minor_grid_linestyle_combo,
            self.y_major_grid_linestyle_combo, self.y_minor_grid_linestyle_combo,
        ):
            grid_style_widget.currentIndexChanged.connect(self._on_axis_setting_changed)
        for grid_style_widget in (
            self.x_major_grid_width_spinbox, self.x_major_grid_alpha_spinbox,
            self.x_minor_grid_width_spinbox, self.x_minor_grid_alpha_spinbox,
            self.y_major_grid_width_spinbox, self.y_major_grid_alpha_spinbox,
            self.y_minor_grid_width_spinbox, self.y_minor_grid_alpha_spinbox,
        ):
            grid_style_widget.valueChanged.connect(self._on_axis_setting_changed)

        self.ui.spine_width_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.ui.spine_color_button.clicked.connect(self._on_change_spine_color)

        self.major_tick_direction_combo.currentTextChanged.connect(self._on_axis_setting_changed)
        self.minor_tick_direction_combo.currentTextChanged.connect(self._on_axis_setting_changed)
        self.major_tick_direction_y2_combo.currentTextChanged.connect(self._on_axis_setting_changed)
        self.minor_tick_direction_y2_combo.currentTextChanged.connect(self._on_axis_setting_changed)
        self.x_ticks_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.x_tick_labels_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.y_ticks_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.y_tick_labels_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)

        self.colorbar_enabled_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.colorbar_position_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.colorbar_width_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.colorbar_label_edit.textChanged.connect(self._on_axis_setting_changed)

    def _connect_dataset_signals(self):
        self.ui.add_dataset_button.clicked.connect(self._on_add_dataset)
        self.new_dataset_button.clicked.connect(self._on_create_new_dataset)
        self.ui.remove_dataset_button.clicked.connect(self._on_remove_dataset)
        self.new_folder_button.clicked.connect(self._on_new_folder)
        self.dataset_search_edit.textChanged.connect(self._on_dataset_search_changed)
        self.ui.dataset_list_widget.currentItemChanged.connect(self.property_panel.on_dataset_selected)
        self.ui.dataset_list_widget.customContextMenuRequested.connect(self._on_dataset_tree_context_menu)
        self.ui.dataset_list_widget.itemClicked.connect(self._on_dataset_tree_item_clicked)
        # ドラッグでの並べ替え(描画の重なり順)を project.datasets に合わせる
        self.ui.dataset_list_widget.model().rowsMoved.connect(self._on_dataset_rows_moved)


        # textChanged だと1文字ごとに描き直して重いので editingFinished
        self.ui.legend_name_edit.editingFinished.connect(self.property_panel.on_legend_name_changed)

        self.property_panel.watch(self.ui.plot_type_combo.currentTextChanged, self.ui.plot_type_combo)
        # 種類によって意味のある欄が変わるので、種類が変わるたびに出し入れし直す
        self.ui.plot_type_combo.currentTextChanged.connect(self.property_panel.update_gradient_controls_visibility)
        self.ui.plot_type_combo.currentTextChanged.connect(self.property_panel.update_smoothing_control_visibility)
        self.ui.plot_type_combo.currentTextChanged.connect(self.property_panel.update_error_display_control_items)
        self.color_picker_widget.colorChanged.connect(self.colors.on_color_changed)
        self.property_panel.watch(self.ui.linestyle_combo.currentTextChanged, self.ui.linestyle_combo)
        self.property_panel.watch(self.ui.linewidth_spinbox.valueChanged, self.ui.linewidth_spinbox)
        self.property_panel.watch(self.ui.marker_combo.currentTextChanged, self.ui.marker_combo)
        self.property_panel.watch(self.ui.markersize_spinbox.valueChanged, self.ui.markersize_spinbox)
        self.property_panel.watch(self.ui.smoothing_checkbox.stateChanged, self.ui.smoothing_checkbox)
        # 平滑化のチェックで手法の欄の有効/無効も切り替える
        self.ui.smoothing_checkbox.stateChanged.connect(self.property_panel.update_smoothing_control_visibility)
        self.property_panel.watch(self.smoothing_method_combo.currentIndexChanged, self.smoothing_method_combo)
        self.property_panel.watch(self.alpha_spinbox.valueChanged, self.alpha_spinbox)
        self.property_panel.watch(self.gradient_checkbox.toggled, self.gradient_checkbox)
        self.gradient_checkbox.toggled.connect(self.property_panel.update_gradient_controls_visibility)
        self.gradient_color2_picker.colorChanged.connect(self.colors.on_gradient_color2_changed)
        self.property_panel.watch(self.gradient_target_combo.currentIndexChanged, self.gradient_target_combo)
        self.property_panel.watch(self.waterfall_checkbox.toggled, self.waterfall_checkbox)
        self.waterfall_checkbox.toggled.connect(self.property_panel.update_waterfall_controls_visibility)
        self.property_panel.watch(self.waterfall_offset_x_spinbox.valueChanged, self.waterfall_offset_x_spinbox)
        self.property_panel.watch(self.waterfall_offset_y_spinbox.valueChanged, self.waterfall_offset_y_spinbox)
        self.property_panel.watch(self.waterfall_occlusion_checkbox.toggled, self.waterfall_occlusion_checkbox)
        self.property_panel.watch(self.waterfall_depth_checkbox.toggled, self.waterfall_depth_checkbox)
        self.waterfall_depth_checkbox.toggled.connect(self.property_panel.update_waterfall_controls_visibility)
        self.property_panel.watch(self.waterfall_depth_ratio_spinbox.valueChanged, self.waterfall_depth_ratio_spinbox)
        # 点ラベルは上限の説明の更新もするので専用のハンドラ(中で on_property_changed を呼ぶ)
        self.point_labels_checkbox.toggled.connect(self.property_panel.on_point_labels_toggled)
        self.property_panel.watch(self.point_label_col_combo.currentTextChanged, self.point_label_col_combo)

        self.property_panel.watch(self.error_display_combo.currentIndexChanged, self.error_display_combo)

        self.property_panel.watch(self.nan_policy_combo.currentIndexChanged, self.nan_policy_combo)

        self.fit_curve_button.clicked.connect(self.fitting.fit_current_dataset)
        self.find_peaks_button.clicked.connect(self.peaks.find_peaks)
        self.multi_peak_fit_button.clicked.connect(self.fitting.multi_peak_fit_current_dataset)

        self.use_secondary_y_checkbox.stateChanged.connect(self.property_panel.on_secondary_y_changed)
        self.subplot_target_combo.currentIndexChanged.connect(self.property_panel.on_subplot_target_changed)

        self.duplicate_dataset_button.clicked.connect(self._on_duplicate_dataset)
        self.auto_color_button.clicked.connect(self.colors.auto_assign_colors)
        self.manage_palette_action.triggered.connect(self.colors.manage_palettes)
        self.colormap_assign_action.triggered.connect(self.colors.auto_assign_colors_from_colormap)
        self.view_edit_data_button.clicked.connect(self._on_show_data_editor)

        self.x_col_combo.currentTextChanged.connect(self.property_panel.on_plot_column_changed)
        self.y_col_combo.currentTextChanged.connect(self.property_panel.on_plot_column_changed)
        self.x_err_col_combo.currentTextChanged.connect(self.property_panel.on_error_column_changed)
        self.y_err_col_combo.currentTextChanged.connect(self.property_panel.on_error_column_changed)

        self.data_2d_checkbox.toggled.connect(self.property_panel.on_data_2d_toggled)
        self.z_col_combo.currentTextChanged.connect(self.property_panel.on_z_column_changed)
        self.property_panel.watch(self.colormap_combo.currentTextChanged, self.colormap_combo)
        self.property_panel.watch(self.grid_interp_method_combo.currentTextChanged, self.grid_interp_method_combo)
        self.color_range_auto_checkbox.toggled.connect(self.property_panel.on_2d_value_range_changed)
        self.vmin_spinbox.valueChanged.connect(self.property_panel.on_2d_value_range_changed)
        self.vmax_spinbox.valueChanged.connect(self.property_panel.on_2d_value_range_changed)
        self.property_panel.watch(self.map_display_mode_combo.currentIndexChanged, self.map_display_mode_combo)
        self.property_panel.watch(self.contour_levels_spinbox.valueChanged, self.contour_levels_spinbox)

    def _create_menu_bar(self):
        build_menu_bar(self)

    def _populate_dataset_menu(self):
        populate_dataset_actions_menu(self, self._dataset_menu)

    def _collect_menu_actions(self):
        """
        メニューの全項目を、階層のパス付きで集める(コマンドパレット・クイックアクセス・ショートカット一覧が使う)。
        区切り線・空の項目・サブメニュー自体は除く。「最近使ったファイル」はコマンドではないので除く。

        最上位のメニューは menuBar().actions() から .menu() で辿らず、組み立て時に持たせた self._file_menu などを使う
        (辿ると、参照が切れたときにメニューごと回収されることがある)。「最近使ったファイル」の判定も、QMenu の
        同一性ではなく持たせてある self._recent_files_menu_action で行う(繰り返すうちに QMenu の同一性が崩れ、
        除いたはずの子の項目が混ざることがあった)。
        """
        results = []
        recent_files_action = getattr(self, '_recent_files_menu_action', None)

        def walk(menu, path):
            for action in menu.actions():
                if action.isSeparator() or menu is self.recent_files_menu:
                    continue
                if action is recent_files_action:
                    continue
                submenu = action.menu()
                if submenu is not None:
                    if submenu is not self.recent_files_menu:
                        walk(submenu, path + [action.text().replace('&', '')])
                else:
                    text = action.text().replace('&', '').strip()
                    if text:
                        results.append((path + [text], action))

        # 「データセット」メニューは含めない。開くたびに作り直すので、候補がそのときの選択で変わり、
        # ピン留めの識別子も安定しない(作り直すサブメニューを辿るとメニューの回収も起きやすい)
        top_menus = [self._file_menu, self._edit_menu, self._view_menu, self._help_menu]
        # 「プラグイン」メニューは、プラグインが何も登録していなければ作られない
        plugin_menu = getattr(self, '_plugin_menu', None)
        if plugin_menu is not None:
            top_menus.append(plugin_menu)
        for top_menu in top_menus:
            walk(top_menu, [top_menu.title().replace('&', '')])
        return results

    def _on_show_command_palette(self):
        dialog = CommandPaletteDialog(self._collect_menu_actions, self)
        dialog.exec()

    def _on_toggle_dark_mode(self, checked):
        """アプリ全体の配色(Qt のパレットと QSS)と、このタブのグラフ・アイコンを切り替える。"""
        apply_theme(QApplication.instance(), checked)
        self.canvas.dark_mode = checked
        app_settings.DARK_MODE.write(self.settings, checked)
        self._update_plot(light=True)  # 軸の数は変わらないので軽い描き直しでよい
        # 以下は作ったときにテーマの色を焼き込んでいるので、描き直す:
        # タイトルと軸ラベルのプレビュー
        self._refresh_all_label_previews()
        # 色欄の見本の枠
        self.color_picker_widget.refresh_theme()
        self.gradient_color2_picker.refresh_theme()
        # matplotlib のツールバーのアイコン
        self._refresh_mpl_toolbar_icons()
        # 自前の SVG アイコン
        self._refresh_custom_svg_icons()
        # 開いたままのデータエディタ(除外した行の背景色)
        if getattr(self, 'data_editor_dialog', None) is not None:
            self.data_editor_dialog._populate_table()
        # 開いたままのヘルプ(表の見出しの色)
        for dialog_attr in ('help_dialog', 'calc_help_dialog'):
            dialog = getattr(self, dialog_attr, None)
            if dialog is not None and hasattr(dialog, 'refresh_theme'):
                dialog.refresh_theme()
        # QSS はアプリ全体に効くが、グラフ・アイコン・メニューのチェックはタブごとなので、ほかのタブにも当てる
        self._sync_dark_mode_to_sibling_tabs(checked)

    def _sync_dark_mode_to_sibling_tabs(self, checked):
        """ほかのタブにも同じダークモードを当てる(QSS はアプリ全体だが、グラフやアイコンはタブごと)。"""
        main_app_window = self.window()
        tab_widget = getattr(main_app_window, 'tab_widget', None)
        if tab_widget is None:
            return
        for i in range(tab_widget.count()):
            tab = tab_widget.widget(i)
            if tab is None or tab is self:
                continue
            if not hasattr(tab, 'dark_mode_action') or not hasattr(tab, 'canvas'):
                continue
            if tab.canvas.dark_mode == checked:
                continue
            tab.canvas.dark_mode = checked
            app_settings.DARK_MODE.write(tab.settings, checked)
            # toggled を出すと、そのタブがまたほかのタブへ当て直しを連鎖させるので、シグナルを止めてチェックだけ揃える
            tab.dark_mode_action.blockSignals(True)
            tab.dark_mode_action.setChecked(checked)
            tab.dark_mode_action.blockSignals(False)
            tab._update_plot(light=True)
            tab._refresh_all_label_previews()
            tab.color_picker_widget.refresh_theme()
            tab.gradient_color2_picker.refresh_theme()
            tab._refresh_mpl_toolbar_icons()
            tab._refresh_custom_svg_icons()

    def _refresh_mpl_toolbar_icons(self):
        """
        matplotlib のツールバーのアイコンを今のパレットで読み直す。matplotlib は作ったときに一度だけ明暗を決めるので、
        ダークモードを切り替えても古い色のまま残る。非公開の toolitems/_actions を使うので、無ければ何もしない。
        """
        toolbar = getattr(self, 'mpl_toolbar', None)
        if toolbar is None:
            return
        toolitems = getattr(toolbar, 'toolitems', None)
        actions = getattr(toolbar, '_actions', None)
        if toolitems is None or actions is None:
            return
        for text, _tooltip_text, image_file, callback in toolitems:
            if text is None:
                continue
            action = actions.get(callback)
            if action is not None:
                action.setIcon(toolbar._icon(image_file + '.png'))

    def _refresh_custom_svg_icons(self):
        """
        自前の SVG アイコンを今のテーマで作り直す。_svg_icon() は作るときに色を決めるだけで、
        setIcon() 済みのアイコンは変わらない(ダイアログは開くたびに作るので対象外)。
        """
        from graphica.gui.main_window import _svg_icon

        if hasattr(self, 'cursor_action'):
            self.cursor_action.setIcon(_svg_icon("pointer"))
        if hasattr(self, 'annotation_action'):
            self.annotation_action.setIcon(_svg_icon("message-2"))
        if hasattr(self, 'layout_edit_action'):
            self.layout_edit_action.setIcon(_svg_icon("layout-grid"))
        if hasattr(self, 'reset_zoom_action'):
            self.reset_zoom_action.setIcon(_svg_icon("refresh"))
        if hasattr(self, 'stats_toolbar_button'):
            self.stats_toolbar_button.setIcon(_svg_icon("chart-histogram"))
        if hasattr(self, 'manage_palette_action'):
            self.manage_palette_action.setIcon(_svg_icon("palette", size=16))
        if hasattr(self, 'colormap_assign_action'):
            self.colormap_assign_action.setIcon(_svg_icon("palette", size=16))

        for button, (icon_name, _label) in getattr(self, '_dataset_action_button_icons', {}).items():
            button.setIcon(_svg_icon(icon_name, size=18))
        for button, icon_name in getattr(self, '_field_icon_buttons', {}).items():
            button.setIcon(_svg_icon(icon_name, size=16))
        for toggle_button in getattr(self, '_collapsible_toggle_buttons', []):
            toggle_button.setIcon(
                _svg_icon("chevron-down" if toggle_button.isChecked() else "chevron-right", size=14)
            )
        # プロパティ欄の節の見出しも同じ矢印
        for entry in getattr(self, '_prop_sections', {}).values():
            button = entry['toggle']
            button.setIcon(
                _svg_icon("chevron-down" if button.isChecked() else "chevron-right", size=13)
            )

    def _set_initial_ui_state(self):

            self.ui.x_autoscale_checkbox.setChecked(True)
            self.ui.y_autoscale_checkbox.setChecked(True)
            self.ui.legend_visible_checkbox.setChecked(True)


            self.y2_label_text_label.setVisible(False)
            self.y2_label_text_edit.setVisible(False)
            self.tick_direction_y2_label.setVisible(False)
            self.major_tick_direction_y2_combo.setVisible(False)
            self.minor_tick_direction_y2_combo.setVisible(False)

            self.fit_info_label.setVisible(False)
            self.fit_info_textedit.setVisible(False)

            self.ui.grid_visible_checkbox.setChecked(False)
            self.ui.minor_grid_visible_checkbox.setChecked(False)

            self.ui.spine_width_spinbox.setValue(self._spine_width)
            self.ui.tick_width_spinbox.setValue(self._tick_width)

            # チェックの状態に合わせて関係する欄の有効/無効を揃える
            self._on_x_minor_tick_visibility_changed()
            self._on_y_minor_tick_visibility_changed()
            self._on_grid_visibility_changed()
            self._on_legend_visibility_changed() # 凡例関連のUIを有効化

            self.property_panel.update_ui_state()
