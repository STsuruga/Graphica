# gui/mixins/ui_setup_mixin.py
"""
PlotterApp の「一度きりの初期化」処理 (シグナル接続、メニューバー構築、
初期UI状態の設定) を担当する Mixin。
__init__ の最後の方から一度だけ呼び出されるメソッド群をまとめている。
"""
from PySide6.QtGui import QKeySequence, QAction
from PySide6.QtWidgets import QApplication

from gui.theme import apply_theme
from gui.dialogs import CommandPaletteDialog
from core.version import APP_NAME
from core.i18n import tr


class UISetupMixin:
    def _connect_signals(self):
            """
            すべてのUI要素のシグナルをスロット（コールバックメソッド）に接続します。
            __init__ の最後の方で一度だけ呼び出されます。
            """

            # --- 1. サブプロット関連のシグナル ---
            # グラフのレイアウト (行数/列数) が変更されたら _on_layout_changed を呼ぶ
            self.subplot_rows_spinbox.valueChanged.connect(self._on_layout_changed)
            self.subplot_cols_spinbox.valueChanged.connect(self._on_layout_changed)

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

            # --- 2. 編集対象の「軸設定」が変更されたときのシグナル ---
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
            self.ui.x_invert_checkbox.stateChanged.connect(self._on_axis_setting_changed)
            self.ui.x_min_spinbox.valueChanged.connect(self._on_axis_setting_changed)
            self.ui.x_max_spinbox.valueChanged.connect(self._on_axis_setting_changed)
            self.ui.y_log_checkbox.stateChanged.connect(self._on_axis_setting_changed)
            self.ui.y_invert_checkbox.stateChanged.connect(self._on_axis_setting_changed)
            self.ui.y_min_spinbox.valueChanged.connect(self._on_axis_setting_changed)
            self.ui.y_max_spinbox.valueChanged.connect(self._on_axis_setting_changed)
            self.ui.x_major_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)
            self.ui.y_major_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)
            self.ui.x_minor_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)
            self.x_tick_format_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
            self.y_tick_format_combo.currentIndexChanged.connect(self._on_axis_setting_changed)
            # 文字装飾ポップアップパネル(項目101)のアイコンボタン。クリックされたら
            # 装飾を適用したうえで、QWidgetAction経由のためクリックしても自動では
            # 閉じないポップアップメニューを明示的に閉じる。
            for field_key, buttons in self.label_format_menu_buttons.items():
                menu = self._label_format_menus[field_key]
                buttons['bold'].clicked.connect(
                    lambda checked=False, k=field_key, m=menu: (self._on_label_bold_clicked(k), m.close()))
                buttons['italic'].clicked.connect(
                    lambda checked=False, k=field_key, m=menu: (self._on_label_italic_clicked(k), m.close()))
                buttons['superscript'].clicked.connect(
                    lambda checked=False, k=field_key, m=menu: (self._on_label_superscript_clicked(k), m.close()))
                buttons['subscript'].clicked.connect(
                    lambda checked=False, k=field_key, m=menu: (self._on_label_subscript_clicked(k), m.close()))
            self.ui.y_minor_tick_interval_spinbox.valueChanged.connect(self._on_axis_setting_changed)

            # (ラベル/書式タブ)
            self.ui.title_text_edit.textChanged.connect(self._on_axis_setting_changed)
            self.ui.x_label_text_edit.textChanged.connect(self._on_axis_setting_changed)
            self.ui.y_label_text_edit.textChanged.connect(self._on_axis_setting_changed)
            self.y2_label_text_edit.textChanged.connect(self._on_axis_setting_changed) # 第2Y軸ラベル

            # (フォントと色はダイアログを開くため、専用のスロットを呼ぶ)
            self.ui.tick_font_button.clicked.connect(self._on_change_tick_font)
            self.ui.tick_color_button.clicked.connect(self._on_change_tick_color)
            self.ui.tick_width_spinbox.valueChanged.connect(self._on_axis_setting_changed)

            self.ui.axis_label_font_button.clicked.connect(self._on_change_axis_label_font)
            self.ui.axis_label_color_button.clicked.connect(self._on_change_axis_label_color)

            self.legend_font_button.clicked.connect(self._on_change_legend_font)
            self.legend_color_button.clicked.connect(self._on_change_legend_color)
            self.legend_order_button.clicked.connect(self._on_edit_legend_order)

            self.ui.legend_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
            self.ui.legend_visible_checkbox.stateChanged.connect(self._on_legend_visibility_changed)
            self.legend_loc_combo.currentTextChanged.connect(self._on_axis_setting_changed)

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


            # --- 3. データセット関連のシグナル ---

            # (データセットリストタブ)
            self.ui.add_dataset_button.clicked.connect(self._on_add_dataset)
            self.new_dataset_button.clicked.connect(self._on_create_new_dataset)
            self.ui.remove_dataset_button.clicked.connect(self._on_remove_dataset)
            self.new_folder_button.clicked.connect(self._on_new_folder)
            self.dataset_search_edit.textChanged.connect(self._on_dataset_search_changed)
            self.ui.dataset_list_widget.currentItemChanged.connect(self._on_dataset_selected)
            self.ui.dataset_list_widget.customContextMenuRequested.connect(self._on_dataset_tree_context_menu)
            # ドラッグ&ドロップでの並べ替え/フォルダ移動(=描画の重なり順の変更)を project.datasets に反映する
            self.ui.dataset_list_widget.model().rowsMoved.connect(self._on_dataset_rows_moved)

            # (データセットプロパティタブ)

            # ★ 凡例名は editingFinished (Enterキー押下 or フォーカス喪失時) を使う
            #    (textChanged だと1文字打つたびにグラフが再描画され、重くなるため)
            self.ui.legend_name_edit.editingFinished.connect(self._on_legend_name_changed)

            self.ui.plot_type_combo.currentTextChanged.connect(self._on_property_changed)
            # ★ グラデーション対象コンボ(項目79)は、プロットタイプによって
            # 「線/塗り/両方」のうちどれが意味を持つかが変わるため、プロットタイプの
            # 変更のたびに表示/非表示を更新し直す(_on_property_changedとは別経路)。
            self.ui.plot_type_combo.currentTextChanged.connect(self._update_gradient_controls_visibility)
            self.color_picker_widget.colorChanged.connect(self._on_dataset_color_changed)
            self.ui.linestyle_combo.currentTextChanged.connect(self._on_property_changed)
            self.ui.linewidth_spinbox.valueChanged.connect(self._on_property_changed)
            self.ui.marker_combo.currentTextChanged.connect(self._on_property_changed)
            self.ui.markersize_spinbox.valueChanged.connect(self._on_property_changed)
            self.ui.smoothing_checkbox.stateChanged.connect(self._on_property_changed)
            self.alpha_spinbox.valueChanged.connect(self._on_property_changed)
            # プロットへのグラデーション適用(項目79)
            self.gradient_checkbox.toggled.connect(self._on_property_changed)
            # チェックのON/OFFで終端色/対象コンボの表示・非表示も切り替える
            self.gradient_checkbox.toggled.connect(self._update_gradient_controls_visibility)
            self.gradient_color2_picker.colorChanged.connect(self._on_gradient_color2_changed)
            self.gradient_target_combo.currentIndexChanged.connect(self._on_property_changed)
            # ウォーターフォールプロット(項目80、項目109でplot_typeとは独立したフラグに変更)
            self.waterfall_checkbox.toggled.connect(self._on_property_changed)
            # チェックのON/OFFでオフセット量スピンボックスの表示・非表示も切り替える
            self.waterfall_checkbox.toggled.connect(self._update_waterfall_controls_visibility)
            self.waterfall_offset_x_spinbox.valueChanged.connect(self._on_property_changed)
            self.waterfall_offset_y_spinbox.valueChanged.connect(self._on_property_changed)
            # 項目105: ラベル有効化時、データ点が多いと確認ポップアップを挟むための
            # 専用ハンドラ経由にする(_on_property_changedへは内部で委譲される)
            self.point_labels_checkbox.toggled.connect(self._on_point_labels_toggled)
            self.point_label_col_combo.currentTextChanged.connect(self._on_property_changed)

            # 誤差の表示形式(項目C-502)
            self.error_display_combo.currentIndexChanged.connect(self._on_property_changed)

            self.fit_curve_button.clicked.connect(self._on_fit_curve)
            self.find_peaks_button.clicked.connect(self._on_find_peaks)

            self.use_secondary_y_checkbox.stateChanged.connect(self._on_secondary_y_changed)
            self.subplot_target_combo.currentIndexChanged.connect(self._on_subplot_target_changed)

            self.duplicate_dataset_button.clicked.connect(self._on_duplicate_dataset)
            self.auto_color_button.clicked.connect(self._on_auto_assign_colors)
            self.manage_palette_action.triggered.connect(self._on_manage_color_palettes)
            self.colormap_assign_action.triggered.connect(self._on_auto_assign_colors_from_colormap)
            self.view_edit_data_button.clicked.connect(self._on_show_data_editor)

            self.x_col_combo.currentTextChanged.connect(self._on_plot_column_changed)
            self.y_col_combo.currentTextChanged.connect(self._on_plot_column_changed)
            self.x_err_col_combo.currentTextChanged.connect(self._on_error_column_changed)
            self.y_err_col_combo.currentTextChanged.connect(self._on_error_column_changed)

    def _create_menu_bar(self):
            """
            メインウィンドウのメニューバー (「ファイル」「表示」「プラグイン」「ヘルプ」) を
            作成します。「プラグイン」はプラグインが1つもメニューアクションを
            登録していない場合は作られない。
            __init__ から一度だけ呼び出されます。
            """

            # QMainWindow が持つ menuBar() を取得
            menu_bar = self.menuBar()

            # --- 1. 「ファイル」メニュー ---
            # "ファイル(&F)" の &F は、Alt+F で開くためのニーモニック
            file_menu = menu_bar.addMenu(tr("ファイル(&F)"))
            # ★ 重要 ★ menu_bar.addMenu() の戻り値をローカル変数のままにすると、
            # (このメソッドを抜けて file_menu への唯一のPython参照が消えた時点で)
            # PySide6側がこのQMenuをPython所有と誤認しているらしく、ガベージ
            # コレクトのタイミングでC++オブジェクトごと実際に破棄されてしまう
            # (子のQActionも道連れで "already deleted" になる)。self.xxx として
            # 永続的な参照を保持することで、この破棄を防ぐ。
            self._file_menu = file_menu

            # (プロジェクト機能)
            # ★ ショートカットを持つQActionは self.xxx として保持する。
            # menu.addAction(text) の戻り値をローカル変数のままにすると、
            # (Qt側では file_menu が親でC++オブジェクトは生きているにも関わらず)
            # PySide6側のPythonラッパーが後からGCで無効化されることがある
            # (コマンドパレット/ショートカット一覧のような「後から再収集して使う」
            # 機能で "already deleted" になる既知の癖)。self.xxx で参照を保持することで防ぐ。
            self.open_project_action = file_menu.addAction(tr("プロジェクトを開く(&O)..."))
            self.open_project_action.setShortcut(QKeySequence.StandardKey.Open)
            self.open_project_action.triggered.connect(self._on_load_project)

            self.save_project_action = file_menu.addAction(tr("プロジェクトを保存(&P)..."))
            self.save_project_action.setShortcut(QKeySequence.StandardKey.Save)
            self.save_project_action.triggered.connect(self._on_save_project)

            # (クリップボードから表データを貼り付け: Excel/スプレッドシートでコピーした
            #  セル範囲をタブ区切りテキストとして解釈し、新しいデータセットにする)
            paste_data_action = file_menu.addAction(tr("クリップボードから貼り付け(&V)..."))
            paste_data_action.triggered.connect(self._on_paste_data_from_clipboard)

            # 最近使ったファイル (プロジェクト/データファイル共通の履歴)
            self.recent_files_menu = file_menu.addMenu(tr("最近使ったファイル"))
            self._update_recent_files_menu()

            file_menu.addSeparator() # 区切り線

            # (テンプレート機能)
            save_template_action = file_menu.addAction(tr("書式テンプレートを保存(&T)..."))
            save_template_action.triggered.connect(self._on_save_plot_template)

            load_template_action = file_menu.addAction(tr("書式テンプレートを適用(&A)..."))
            load_template_action.triggered.connect(self._on_load_plot_template)

            file_menu.addSeparator() # --- 区切り線 ---

            # (エクスポート機能)
            self.save_action = file_menu.addAction(tr("名前を付けてエクスポート(&S)..."))
            self.save_action.setShortcut(QKeySequence.StandardKey.SaveAs)
            self.save_action.triggered.connect(self._on_export_plot)

            # (クリップボードコピー: Ctrl+C は既存のテキスト編集のコピー操作と
            #  衝突しうるため、あえてショートカットは割り当てずメニューのみにする)
            copy_plot_action = file_menu.addAction(tr("グラフをコピー(&C)"))
            copy_plot_action.triggered.connect(self._on_copy_plot_to_clipboard)

            # (印刷: ファイル保存を経由せず直接プリンターに出力)
            self.print_action = file_menu.addAction(tr("印刷(&R)..."))
            self.print_action.setShortcut(QKeySequence.StandardKey.Print)
            self.print_action.triggered.connect(self._on_print_plot)

            # (バッチエクスポート: 複数サブプロット/複数プロジェクトファイルを一括書き出し)
            batch_export_action = file_menu.addAction(tr("バッチエクスポート(&B)..."))
            batch_export_action.triggered.connect(self._on_batch_export)

            file_menu.addSeparator() # --- 区切り線 ---

            # (オートセーブ設定: テキストには現在の状態(有効/無効・間隔)を表示する)
            self.autosave_interval_action = file_menu.addAction(tr("オートセーブ間隔を設定(&I)..."))
            self.autosave_interval_action.triggered.connect(self._on_configure_autosave_interval)
            self._update_autosave_menu_text()

            # --- 2. 「編集」メニュー ---
            # データセットのプロパティ変更 (色・線種・凡例名など) の Undo/Redo
            # (DataEditorDialog 内のセル編集用スタックとは別の、メインウィンドウ用スタック)
            edit_menu = menu_bar.addMenu(tr("編集(&E)"))
            self._edit_menu = edit_menu  # 破棄されないよう保持 (上記file_menuと同じ理由)

            undo_action = self.undo_stack.createUndoAction(self, tr("元に戻す"))
            undo_action.setShortcut(QKeySequence.StandardKey.Undo)
            edit_menu.addAction(undo_action)

            redo_action = self.undo_stack.createRedoAction(self, tr("やり直し"))
            redo_action.setShortcut(QKeySequence.StandardKey.Redo)
            edit_menu.addAction(redo_action)

            edit_menu.addSeparator()

            # 散らばっていた設定項目 (ダークモード/オートセーブ間隔など) を
            # 1画面にまとめた環境設定ダイアログ
            preferences_action = edit_menu.addAction(tr("環境設定(&P)..."))
            preferences_action.triggered.connect(self._on_show_preferences)

            # コマンドパレット (Ctrl+Shift+P): メニュー項目をキーボードで検索して実行する。
            # メニューにフォーカスがなくても使えるよう self (QMainWindow) にも
            # アクションを追加し、ショートカットがウィンドウ全体で有効になるようにする。
            self.command_palette_action = QAction(tr("コマンドパレット(&K)..."), self)
            self.command_palette_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
            self.command_palette_action.triggered.connect(self._on_show_command_palette)
            self.addAction(self.command_palette_action)
            edit_menu.addAction(self.command_palette_action)

            # --- 3. 「表示」メニュー ---
            view_menu = menu_bar.addMenu(tr("表示(&V)"))
            self._view_menu = view_menu  # 破棄されないよう保持 (上記file_menuと同じ理由)

            # QDockWidget が持つ標準の「表示/非表示」アクションを取得
            # ★ GUI洗練: 「プロットのプロパティ」「データセットのプロパティ」は
            #   1つのドック(self.ui.control_dock_widget、内部で2セクションに分割)に
            #   統合したため、表示メニューの項目も1つにまとめる
            #   (properties_dock_widget は control_dock_widget のエイリアス)
            dock_widget_action = self.ui.control_dock_widget.toggleViewAction()
            dock_widget_action.setText(tr("プロパティパネル")) # メニューに表示される名前を設定
            view_menu.addAction(dock_widget_action)

            # 常時表示のエクスポートプレビューパネル (デフォルトは非表示)
            export_preview_dock_action = self.export_preview_dock_widget.toggleViewAction()
            export_preview_dock_action.setText(tr("エクスポートプレビュー"))
            view_menu.addAction(export_preview_dock_action)

            # ミニマップ(レンジスライダー、項目83)の表示/非表示切り替え。
            # チェック状態はQSettingsから復元済みの self.minimap_visible に合わせる。
            # setChecked() は toggled.connect() より前に行うことで、復元時に
            # _on_toggle_minimap が二重に呼ばれないようにしている(ダークモードと同じ理由)。
            self.minimap_action = view_menu.addAction(tr("ミニマップ(レンジスライダー)"))
            self.minimap_action.setCheckable(True)
            self.minimap_action.setChecked(self.minimap_visible)
            self.minimap_action.toggled.connect(self._on_toggle_minimap)

            # 項目86: マルチモニター対応。キャンバスを独立したウィンドウへ
            # 切り離し、サブモニターへドラッグ・最大化できるようにする。
            # チェック状態は self.canvas_detached (この時点ではまだ復元前なので
            # 常にFalse。起動時の復元は__init__側でQTimer経由の遅延処理として
            # 行われ、その際に _sync_canvas_detach_action() 経由でここに反映される)。
            self.canvas_detach_action = view_menu.addAction(tr("キャンバスを別ウィンドウに切り離す"))
            self.canvas_detach_action.setCheckable(True)
            self.canvas_detach_action.setChecked(self.canvas_detached)
            self.canvas_detach_action.toggled.connect(self._on_toggle_canvas_detached)

            # パネルラベルの自動採番(項目C-712): 複数サブプロットに(a)(b)(c)...を
            # 自動表示する。プロジェクトごとの設定(self.project.panel_labels_enabled)
            # なので、チェック状態はプロジェクト読み込み時にも同期される
            # (_load_project_from_path参照)。
            self.panel_labels_action = view_menu.addAction(tr("パネルラベルを自動表示 ((a)(b)(c)...)"))
            self.panel_labels_action.setCheckable(True)
            self.panel_labels_action.setChecked(self.project.panel_labels_enabled)
            self.panel_labels_action.toggled.connect(self._on_toggle_panel_labels)

            # 項目87: クイックアクセスのカスタムツールバー。ツールバー本体の作成と
            # 表示/非表示を切り替える表示メニュー項目の追加はここで行う。
            # ★ ピン留め済みアクションの実際の復元 (_restore_quick_access_actions) と
            #   右クリックでのピン留め用コンテキストメニューの設置
            #   (_install_quick_access_context_menus) は、「プラグイン」メニュー
            #   (このメソッドの後段、セクション4) も含めた全メニューが構築し
            #   終わった後でないと _collect_menu_actions() がプラグインの
            #   アクションを拾えないため、このメソッドの外(__init__側)で
            #   _create_menu_bar() 呼び出し直後に行う。
            self._create_quick_access_toolbar()

            view_menu.addSeparator()

            # ダークモード切り替え (アプリ全体のQtパレット + グラフの配色の両方に適用)
            # チェック状態は設定から復元する。setChecked() は toggled.connect() より前に
            # 行うことで、復元時に _on_toggle_dark_mode が二重に呼ばれないようにしている。
            self.dark_mode_action = view_menu.addAction(tr("ダークモード"))
            self.dark_mode_action.setCheckable(True)
            self.dark_mode_action.setChecked(self.canvas.dark_mode)
            self.dark_mode_action.toggled.connect(self._on_toggle_dark_mode)
            # 起動時のモードに関わらず必ず呼び、Fusionスタイルを一貫して適用する
            # (呼ばないとネイティブスタイルのままになり、後でダーク→ライトと
            # 切り替えた際にツールバーサイズ等が変わってしまう)
            apply_theme(QApplication.instance(), self.canvas.dark_mode)


            # --- 4. 「プラグイン」メニュー (プラグインが1つも登録していない場合は作らない) ---
            # ★ self.plugin_api は __init__ 側で _create_menu_bar() より前に
            #   load_plugins_once() 済み。フィット関数の登録はプロセス全体で
            #   1度だけだが、メニューアクションはタブごとの menuBar() に
            #   個別に追加する必要があるため、ここで毎回追加する。
            if self.plugin_api.menu_actions:
                plugin_menu = menu_bar.addMenu(tr("プラグイン(&P)"))
                self._plugin_menu = plugin_menu  # 破棄されないよう保持 (上記file_menuと同じ理由)
                for text, callback, shortcut in self.plugin_api.menu_actions:
                    action = plugin_menu.addAction(text)
                    if shortcut:
                        action.setShortcut(QKeySequence(shortcut))
                    # callback(self) の形式で、現在のPlotterAppインスタンスを渡す。
                    # デフォルト引数でクロージャに現在のcallback/selfを束縛する
                    # (ループ変数をラムダで直接使うと最後の値だけが使われてしまうため)。
                    action.triggered.connect(
                        lambda checked=False, cb=callback: cb(self)
                    )

            # --- 5. 「ヘルプ」メニュー ---
            help_menu = menu_bar.addMenu(tr("ヘルプ(&H)"))
            self._help_menu = help_menu  # 破棄されないよう保持 (上記file_menuと同じ理由)

            mathtext_help_action = help_menu.addAction(tr("mathtext リファレンス..."))
            mathtext_help_action.triggered.connect(self._on_show_help) # HelpDialog を表示

            calc_help_action = help_menu.addAction(tr("列計算機能 リファレンス..."))
            calc_help_action.triggered.connect(self._on_show_calc_help) # CalcHelpDialog を表示

            shortcuts_action = help_menu.addAction(tr("キーボードショートカット一覧..."))
            shortcuts_action.triggered.connect(self._on_show_shortcuts)

            help_menu.addSeparator()

            # 診断情報バンドル出力(項目C-1201): バグ報告時に添付できるよう、
            # ログ・環境情報・設定値・プラグイン読み込み状況を1つのzipにまとめる。
            diagnostic_bundle_action = help_menu.addAction(tr("診断情報をエクスポート..."))
            diagnostic_bundle_action.triggered.connect(self._on_export_diagnostic_bundle)

            help_menu.addSeparator()

            about_action = help_menu.addAction(tr("{app} について...").format(app=APP_NAME))
            about_action.triggered.connect(self._on_show_about) # AboutDialog を表示

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
        """
        results = []

        def walk(menu, path):
            for action in menu.actions():
                if action.isSeparator() or menu is self.recent_files_menu:
                    continue
                submenu = action.menu()
                if submenu is not None:
                    if submenu is not self.recent_files_menu:
                        walk(submenu, path + [action.text().replace('&', '')])
                else:
                    text = action.text().replace('&', '').strip()
                    if text:
                        results.append((path + [text], action))

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
        self._update_plot() # 既存のグラフにも新しい配色を反映するため再描画

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
            self._update_ui_state()
