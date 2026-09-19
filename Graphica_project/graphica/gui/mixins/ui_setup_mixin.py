# gui/mixins/ui_setup_mixin.py
"""
PlotterApp の「一度きりの初期化」処理 (シグナル接続、メニューバー構築、
初期UI状態の設定) を担当する Mixin。
__init__ の最後の方から一度だけ呼び出されるメソッド群をまとめている。
"""
from PySide6.QtWidgets import QApplication

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
        # グラフのレイアウト (行数/列数) が変更されたら _on_layout_changed を呼ぶ
        self.subplot_rows_spinbox.valueChanged.connect(self._on_layout_changed)
        self.subplot_cols_spinbox.valueChanged.connect(self._on_layout_changed)

        # 軸共有(sharex/sharey)チェックボックスが変更されたら _on_share_axis_changed を呼ぶ
        self.share_x_checkbox.toggled.connect(self._on_share_axis_changed)
        self.share_y_checkbox.toggled.connect(self._on_share_axis_changed)

        # 「編集対象のプロット」コンボボックスが変更されたら _on_active_axis_changed を呼ぶ
        self.active_axis_combo.currentIndexChanged.connect(self._on_active_axis_changed)

        # 自由配置レイアウト(項目37)関連のシグナル
        self.free_layout_checkbox.toggled.connect(self._on_toggle_free_layout)
        self.add_free_subplot_button.clicked.connect(self._on_add_free_subplot)
        self.remove_free_subplot_button.clicked.connect(self._on_remove_free_subplot)

        # 項目85: 自由配置レイアウトの位置・サイズ数値入力(X/Y/幅/高さ)。
        # どれか1つでも変更されたら、選択中のサブプロットへ即座に反映する。
        self.free_layout_x_spinbox.valueChanged.connect(self._on_free_layout_position_spinbox_changed)
        self.free_layout_y_spinbox.valueChanged.connect(self._on_free_layout_position_spinbox_changed)
        self.free_layout_width_spinbox.valueChanged.connect(self._on_free_layout_position_spinbox_changed)
        self.free_layout_height_spinbox.valueChanged.connect(self._on_free_layout_position_spinbox_changed)

    def _connect_axis_setting_signals(self):
        # ほとんどのUIは、値が変更されたら _on_axis_setting_changed を呼ぶ

        # (X軸タブ)
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
        # ★ 対数軸の補助目盛り制御(項目C-604)の表示/有効状態は対数表示の
        # ON/OFFにも依存するため、_on_x/y_minor_tick_visibility_changed
        # (元々は補助目盛表示チェックボックス用)を対数表示チェックボックス
        # にもつなぐ。
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
        # 目盛りの小数点以下桁数(実機フィードバック): X軸/Y軸それぞれ独立
        self.x_tick_decimals_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.y_tick_decimals_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.x_secondary_axis_source_unit_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.x_secondary_axis_target_unit_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        # ★ タイトル/軸ラベルの「Aa」ボタンは、ポップアップウィンドウ化
        #   (項目H-2-4)によりLabelEditDialogを開くだけの単純なclicked接続に
        #   なったため(gui/main_window.py側でline_editごとに直接connect
        #   済み)、ここでの個別ボタン配線は不要になった。
        self.ui.y_minor_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)

        # (ラベル/書式タブ)
        self.ui.title_text_edit.textChanged.connect(self._on_axis_setting_changed)
        self.ui.x_label_text_edit.textChanged.connect(self._on_axis_setting_changed)
        self.ui.y_label_text_edit.textChanged.connect(self._on_axis_setting_changed)
        self.x_label_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.y_label_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.y2_label_text_edit.textChanged.connect(self._on_axis_setting_changed) # 第2Y軸ラベル

        # (フォントと色はダイアログを開くため、専用のスロットを呼ぶ)
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
        # グリッド表示チェックは、_on_grid_visibility_changed にも接続 (補助グリッドの有効/無効化のため)
        self.ui.grid_visible_checkbox.stateChanged.connect(self._on_grid_visibility_changed)
        self.ui.minor_grid_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        # 補助グリッド表示チェックも、詳細カスタマイズ行の有効/無効切り替えのため
        # _on_grid_visibility_changed に接続する
        self.ui.minor_grid_visible_checkbox.stateChanged.connect(self._on_grid_visibility_changed)

        # グリッド線の詳細カスタマイズ(項目82): 線種/太さ/透過度 × X/Y軸 × 主/補助目盛
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

        # カラーバー(項目C-501)。2Dマップが描画されていないサブプロットでは
        # 何の効果も持たないが、他の軸設定と同じく常に収集・適用の対象にする。
        self.colorbar_enabled_checkbox.stateChanged.connect(self._on_axis_setting_changed)
        self.colorbar_position_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
        self.colorbar_width_spinbox.valueChanged.connect(self._on_axis_setting_changed)
        self.colorbar_label_edit.textChanged.connect(self._on_axis_setting_changed)

    def _connect_dataset_signals(self):
        # (データセットリストタブ)
        self.ui.add_dataset_button.clicked.connect(self._on_add_dataset)
        self.new_dataset_button.clicked.connect(self._on_create_new_dataset)
        self.ui.remove_dataset_button.clicked.connect(self._on_remove_dataset)
        self.new_folder_button.clicked.connect(self._on_new_folder)
        self.dataset_search_edit.textChanged.connect(self._on_dataset_search_changed)
        self.ui.dataset_list_widget.currentItemChanged.connect(self.property_panel.on_dataset_selected)
        self.ui.dataset_list_widget.customContextMenuRequested.connect(self._on_dataset_tree_context_menu)
        # 項目C-907: 目アイコン列のクリックでデータセットの表示/非表示をトグルする
        self.ui.dataset_list_widget.itemClicked.connect(self._on_dataset_tree_item_clicked)
        # ドラッグ&ドロップでの並べ替え/フォルダ移動(=描画の重なり順の変更)を project.datasets に反映する
        self.ui.dataset_list_widget.model().rowsMoved.connect(self._on_dataset_rows_moved)

        # (データセットプロパティタブ)

        # ★ 凡例名は editingFinished (Enterキー押下 or フォーカス喪失時) を使う
        #    (textChanged だと1文字打つたびにグラフが再描画され、重くなるため)
        self.ui.legend_name_edit.editingFinished.connect(self.property_panel.on_legend_name_changed)

        self.property_panel.watch(self.ui.plot_type_combo.currentTextChanged, self.ui.plot_type_combo)
        # ★ グラデーション対象コンボ(項目79)は、プロットタイプによって
        # 「線/塗り/両方」のうちどれが意味を持つかが変わるため、プロットタイプの
        # 変更のたびに表示/非表示を更新し直す(_on_property_changedとは別経路)。
        self.ui.plot_type_combo.currentTextChanged.connect(self.property_panel.update_gradient_controls_visibility)
        # ★ 平滑化チェックボックス(Line/Line+Scatterでのみ意味を持つ)も同様に、
        # プロットタイプの変更のたびに表示/非表示を更新し直す。
        self.ui.plot_type_combo.currentTextChanged.connect(self.property_panel.update_smoothing_control_visibility)
        # ★ 誤差表示コンボの「誤差バンド」項目(Bar/Areaでは無効化)も同様。
        self.ui.plot_type_combo.currentTextChanged.connect(self.property_panel.update_error_display_control_items)
        self.color_picker_widget.colorChanged.connect(self.colors.on_color_changed)
        self.property_panel.watch(self.ui.linestyle_combo.currentTextChanged, self.ui.linestyle_combo)
        self.property_panel.watch(self.ui.linewidth_spinbox.valueChanged, self.ui.linewidth_spinbox)
        self.property_panel.watch(self.ui.marker_combo.currentTextChanged, self.ui.marker_combo)
        self.property_panel.watch(self.ui.markersize_spinbox.valueChanged, self.ui.markersize_spinbox)
        self.property_panel.watch(self.ui.smoothing_checkbox.stateChanged, self.ui.smoothing_checkbox)
        # ★ 平滑化チェックボックスのON/OFFで、手法コンボ(項目C-304)の
        # 有効/無効も切り替える(_update_smoothing_control_visibility経由、
        # plot_type変更時と同じ更新ロジックを再利用する)。
        self.ui.smoothing_checkbox.stateChanged.connect(self.property_panel.update_smoothing_control_visibility)
        # 平滑化の手法(項目C-304)
        self.property_panel.watch(self.smoothing_method_combo.currentIndexChanged, self.smoothing_method_combo)
        self.property_panel.watch(self.alpha_spinbox.valueChanged, self.alpha_spinbox)
        # プロットへのグラデーション適用(項目79)
        self.property_panel.watch(self.gradient_checkbox.toggled, self.gradient_checkbox)
        # チェックのON/OFFで終端色/対象コンボの表示・非表示も切り替える
        self.gradient_checkbox.toggled.connect(self.property_panel.update_gradient_controls_visibility)
        self.gradient_color2_picker.colorChanged.connect(self.colors.on_gradient_color2_changed)
        self.property_panel.watch(self.gradient_target_combo.currentIndexChanged, self.gradient_target_combo)
        # ウォーターフォールプロット(項目80、項目109でplot_typeとは独立したフラグに変更)
        self.property_panel.watch(self.waterfall_checkbox.toggled, self.waterfall_checkbox)
        # チェックのON/OFFでオフセット量スピンボックスの表示・非表示も切り替える
        self.waterfall_checkbox.toggled.connect(self.property_panel.update_waterfall_controls_visibility)
        self.property_panel.watch(self.waterfall_offset_x_spinbox.valueChanged, self.waterfall_offset_x_spinbox)
        self.property_panel.watch(self.waterfall_offset_y_spinbox.valueChanged, self.waterfall_offset_y_spinbox)
        # オクルージョン(実機フィードバック): on/off切り替え可能にする
        self.property_panel.watch(self.waterfall_occlusion_checkbox.toggled, self.waterfall_occlusion_checkbox)
        # 斜向/立体風トグル(項目120、C-514): 奥のトレースをわずかに縮小
        self.property_panel.watch(self.waterfall_depth_checkbox.toggled, self.waterfall_depth_checkbox)
        # チェックのON/OFFで縮小率スピンボックスの表示・非表示も切り替える
        self.waterfall_depth_checkbox.toggled.connect(self.property_panel.update_waterfall_controls_visibility)
        self.property_panel.watch(self.waterfall_depth_ratio_spinbox.valueChanged, self.waterfall_depth_ratio_spinbox)
        # 項目105: ラベル有効化時、データ点が多いと確認ポップアップを挟むための
        # 専用ハンドラ経由にする(_on_property_changedへは内部で委譲される)
        self.point_labels_checkbox.toggled.connect(self.property_panel.on_point_labels_toggled)
        self.property_panel.watch(self.point_label_col_combo.currentTextChanged, self.point_label_col_combo)

        # 誤差の表示形式(項目C-502)
        self.property_panel.watch(self.error_display_combo.currentIndexChanged, self.error_display_combo)

        # 欠損値(NaN)の方針設定(項目C-201)
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

        # 2Dグリッドデータ(ヒートマップ、項目C-508)
        self.data_2d_checkbox.toggled.connect(self.property_panel.on_data_2d_toggled)
        self.z_col_combo.currentTextChanged.connect(self.property_panel.on_z_column_changed)
        self.property_panel.watch(self.colormap_combo.currentTextChanged, self.colormap_combo)
        self.property_panel.watch(self.grid_interp_method_combo.currentTextChanged, self.grid_interp_method_combo)
        self.color_range_auto_checkbox.toggled.connect(self.property_panel.on_2d_value_range_changed)
        self.vmin_spinbox.valueChanged.connect(self.property_panel.on_2d_value_range_changed)
        self.vmax_spinbox.valueChanged.connect(self.property_panel.on_2d_value_range_changed)
        # 2Dマップの表示方式・等高線レベル数(項目C-509)
        self.property_panel.watch(self.map_display_mode_combo.currentIndexChanged, self.map_display_mode_combo)
        self.property_panel.watch(self.contour_levels_spinbox.valueChanged, self.contour_levels_spinbox)

    def _create_menu_bar(self):
        build_menu_bar(self)

    def _populate_dataset_menu(self):
        populate_dataset_actions_menu(self, self._dataset_menu)

    def _collect_menu_actions(self):
        """
        メニューバー配下の全アクション(区切り線・空文字・サブメニュー自体を除く)を、
        表示用の階層パス付きで収集する。コマンドパレットの検索候補として使う。
        「最近使ったファイル」はコマンドではなくファイルパスの一覧なので対象外にする。

        ★ 重要 ★ 最上位メニューは self.menuBar().actions() 経由で毎回取り直すのではなく、
        _create_menu_bar() で self._file_menu 等として保持している永続参照を直接使う。
        self.menuBar().actions() で取得した QAction (各メニューの「メニューとしての自分」を
        表すaction) を経由して action.menu() でメニュー本体を辿るやり方だと、このメソッドを
        抜けて一時的な参照が失われた際に、なぜかメニュー本体ごとPySide6側に破棄されてしまう
        (子のQActionもろとも "already deleted" になる) という実測済みの癖があるため。

        ★ 同様の理由で「最近使ったファイル」サブメニューの除外判定は、
        action.menu() が返す QMenu の identity 比較(submenu is not
        self.recent_files_menu)だけに頼らない。繰り返し走査するうちにこの
        identity が失効し、除外しているはずの子アクション(「(履歴なし)」等)が
        リークすることが実測で確認されたため、永続参照として保持している
        開閉用アクション self._recent_files_menu_action の identity でも判定する。
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

        # ★ 「データセット」メニューは意図的に含めない。選択状態に応じて開くたびに
        # 作り直される(clear() → 詰め直し)ため、(1) コマンドパレットの候補が
        # 「そのとき何を選んでいたか」で変わってしまい、(2) クイックアクセスの
        # ピン留め識別子(メニューのパス全体)が安定しない。さらに、作り直される
        # サブメニューを action.menu() 経由で辿ると、このリポジトリで2度踏んでいる
        # shiboken のメニュー破棄(CLAUDE.md参照)を誘発しやすい。
        # 同じ操作は「データセットリストの右クリック」からも辿れるので、
        # 「最近使ったファイル」と同様に収集対象から外す。
        top_menus = [self._file_menu, self._edit_menu, self._view_menu, self._help_menu]
        # ★ 「プラグイン」メニューは、プラグインが1つもメニューアクションを
        # 登録していない場合は _create_menu_bar() で作られず self._plugin_menu が
        # 存在しないため、getattr で安全に確認してから含める。
        plugin_menu = getattr(self, '_plugin_menu', None)
        if plugin_menu is not None:
            top_menus.append(plugin_menu)
        for top_menu in top_menus:
            walk(top_menu, [top_menu.title().replace('&', '')])
        return results

    def _on_show_command_palette(self):
        """「コマンドパレット...」(Ctrl+Shift+P) の処理。メニュー項目を検索して実行できるようにする"""
        dialog = CommandPaletteDialog(self._collect_menu_actions, self)
        dialog.exec()

    def _on_toggle_dark_mode(self, checked):
        """
        「ダークモード」メニューのチェック状態が変更されたときの処理。
        アプリ全体のQtパレットと、グラフ(matplotlib)の配色の両方を切り替える。
        """
        apply_theme(QApplication.instance(), checked)
        self.canvas.dark_mode = checked
        self.settings.setValue("dark_mode", checked)
        self._update_plot(light=True) # 既存のグラフにも新しい配色を反映するため再描画(項目C-003フェーズ2)
        # ★ 項目H-2-4追加分: タイトル/軸ラベルのmathtextプレビュー
        #   (gui/mathtext_preview.py)は文字色をtext_primary/text_mutedトークン
        #   から都度レンダリングしているため、テーマが変わったら再描画しないと
        #   古い配色のまま残ってしまう。
        self._refresh_all_label_previews()
        # ★ 項目H-2-6: ColorPickerWidgetのスウォッチ枠線もテーマのborder_strong
        #   トークンを参照するようになったため、同様に再描画が必要。
        self.color_picker_widget.refresh_theme()
        self.gradient_color2_picker.refresh_theme()
        # ★ 項目H-4: matplotlib純正のナビゲーションツールバー(home/back/
        #   forward/pan/zoom/save)のアイコンは構築時のパレットで固定される
        #   ため、同様に再読み込みが必要(詳細は_refresh_mpl_toolbar_icons参照)。
        self._refresh_mpl_toolbar_icons()
        # ★ 項目H-4: 自前のTabler Icons SVGアイコン(カーソル/注釈/レイアウト
        #   編集ツール、データセット操作ボタン群、フォント/色選択ボタン群、
        #   統計/パレット系メニュー、折りたたみセクションのシェブロン)も
        #   同じ理由で再読み込みが必要(詳細は_refresh_custom_svg_icons参照)。
        self._refresh_custom_svg_icons()
        # ★ バグ修正: データエディタ(gui/data_editor.py)は非モーダル(show())
        #   で開いたまま操作を続けられるため、開いたままダークモードを切り替える
        #   と、マスク済み行の背景色(_masked_row_background())が古いテーマの
        #   ままになっていた。開いていれば再描画して追従させる。
        if getattr(self, 'data_editor_dialog', None) is not None:
            self.data_editor_dialog._populate_table()
        # ★ バグ修正: HelpDialog/CalcHelpDialog(gui/dialogs.py)も同様に
        #   非モーダルで開いたままダークモードを切り替えられるが、表見出しの
        #   色(tr.header-row)は__init__時点のトークンをQTextDocumentへ
        #   一度だけ焼き込む実装だったため、開いたまま切り替えると色が
        #   古いテーマのまま取り残されていた。
        for dialog_attr in ('help_dialog', 'calc_help_dialog'):
            dialog = getattr(self, dialog_attr, None)
            if dialog is not None and hasattr(dialog, 'refresh_theme'):
                dialog.refresh_theme()
        # ★ バグ修正: apply_theme() 自体はQApplication全体(=全タブ共有の
        #   QSS/パレット)に対して即座に効くプロセス全体の操作だが、
        #   このメソッドの残り(matplotlib配色・アイコン再読み込み・
        #   ダークモードのメニューチェック状態)はすべて self (=操作した
        #   タブ)にしか適用されない。各タブは完全に独立したPlotterApp
        #   インスタンス(CLAUDE.mdの設計方針通り)であるため、他のタブを
        #   開いたまま片方だけダークモードを切り替えると、Qtのチェコロム/
        #   ドック等は(共有QSSのため)即座にダークになるのに、他のタブの
        #   グラフやツールバーアイコン、メニューのチェック状態は古いまま
        #   残る「二重人格」状態になっていた。
        self._sync_dark_mode_to_sibling_tabs(checked)

    def _sync_dark_mode_to_sibling_tabs(self, checked):
        """
        自分以外の全タブ(独立したPlotterAppインスタンス)にも、同じダーク
        モード状態を反映する。MainAppWindow.tab_widgetの各ページが
        PlotterAppインスタンスそのもの(main_app_window.pyのadd_new_project_tab
        参照)であることを前提にしている。
        """
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
            tab.settings.setValue("dark_mode", checked)
            # ★ setChecked()がtoggledを発火すると、そのタブの
            #   _on_toggle_dark_modeがapply_theme()の再実行や、さらに
            #   自分自身への再同期を連鎖的に引き起こしてしまう(無害だが
            #   無駄な二重処理になる)ため、シグナルを止めて直接状態だけ揃える。
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
        matplotlib純正のNavigationToolbar2QTのアイコンを、現在のQPaletteに
        合わせて再読み込みする(_on_toggle_dark_modeから呼ばれる)。

        NavigationToolbar2QT._icon()は読み込み時にQPaletteのbackgroundRole()
        の明度を見て自動的にダークモード用の配色へ切り替える仕組みを内蔵して
        いるが、これはアイコン読み込み時(=ツールバー構築時)に一度だけ実行
        されるため、実行中にダークモードを切り替えても再読み込みされずアイコン
        が古いテーマの色のまま残ってしまう(実機で発覚)。matplotlib非公開の
        `toolitems`/`_actions`属性を使って手動で再読み込みする(将来の
        matplotlibバージョンでこれらの属性が無くなる可能性があるため、
        存在しない場合は何もしない安全側の実装にしている)。
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
        自前のTabler Icons SVGアイコン(gui/main_window.pyの_svg_icon()経由で
        setIcon()した永続的なウィジェット/アクション)を、現在のテーマに
        合わせて再読み込みする(_on_toggle_dark_modeから呼ばれる)。

        _svg_icon()自体は呼び出しの都度、現在のテーマから色を解決するように
        なっているが、それはあくまで「次にsetIcon()された時」に反映される
        だけで、既にsetIcon()済みのQIconオブジェクトが自動的に更新される
        わけではない。ダイアログ内のアイコン(H-2-6で対応済み)はダイアログが
        毎回新規に構築されるため問題にならないが、ここで挙げるものは
        PlotterApp.__init__で一度だけ構築される永続的なウィジェットのため、
        明示的な再設定が必要。
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
        # C-1: プロパティパネル内のサブセクション見出しも同じシェブロンを使う
        for entry in getattr(self, '_prop_sections', {}).values():
            button = entry['toggle']
            button.setIcon(
                _svg_icon("chevron-down" if button.isChecked() else "chevron-right", size=13)
            )

    def _set_initial_ui_state(self):
            """
            アプリケーション起動時にUIを初期状態に設定します。
            不要なウィジェットを非表示にし、デフォルト値を設定します。
            __init__ から一度だけ呼び出されます。
            """

            # --- デフォルトで ON にする項目 ---
            self.ui.x_autoscale_checkbox.setChecked(True)
            self.ui.y_autoscale_checkbox.setChecked(True)
            self.ui.legend_visible_checkbox.setChecked(True)

            # --- デフォルトで OFF (非表示) にする項目 ---

            # 第2Y軸関連のUI
            self.y2_label_text_label.setVisible(False)
            self.y2_label_text_edit.setVisible(False)
            self.tick_direction_y2_label.setVisible(False)
            self.major_tick_direction_y2_combo.setVisible(False)
            self.minor_tick_direction_y2_combo.setVisible(False)

            # フィット情報関連のUI
            self.fit_info_label.setVisible(False)
            self.fit_info_textedit.setVisible(False)

            # グリッド関連のUI (デフォルトは非表示)
            self.ui.grid_visible_checkbox.setChecked(False)
            self.ui.minor_grid_visible_checkbox.setChecked(False)

            # --- デフォルト値をUIにセット ---
            # (self._spine_width などは __init__ で初期化済み)
            self.ui.spine_width_spinbox.setValue(self._spine_width)
            self.ui.tick_width_spinbox.setValue(self._tick_width)

            # --- UIの一貫性を保つためのヘルパー呼び出し ---
            # (チェックボックスの状態に合わせて、関連スピンボックスを
            #  有効化/無効化（グレーアウト）するために呼び出す)
            self._on_x_minor_tick_visibility_changed()
            self._on_y_minor_tick_visibility_changed()
            self._on_grid_visibility_changed()
            self._on_legend_visibility_changed() # 凡例関連のUIを有効化

            # --- 最終的なUI状態の更新 ---
            # (データセットが選択されていない状態 = プロパティUIを無効化)
            self.property_panel.update_ui_state()
