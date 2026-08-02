# gui/mixins/ui_setup_mixin.py
"""
PlotterApp の「一度きりの初期化」処理 (シグナル接続、メニューバー構築、
初期UI状態の設定) を担当する Mixin。
__init__ の最後の方から一度だけ呼び出されるメソッド群をまとめている。
"""
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from gui.theme import apply_theme
from core.version import APP_NAME


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

            self.ui.legend_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
            self.ui.legend_visible_checkbox.stateChanged.connect(self._on_legend_visibility_changed)
            self.legend_loc_combo.currentTextChanged.connect(self._on_axis_setting_changed)

            self.ui.grid_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)
            # グリッド表示チェックは、_on_grid_visibility_changed にも接続 (補助グリッドの有効/無効化のため)
            self.ui.grid_visible_checkbox.stateChanged.connect(self._on_grid_visibility_changed)
            self.ui.minor_grid_visible_checkbox.stateChanged.connect(self._on_axis_setting_changed)

            self.ui.spine_width_spinbox.valueChanged.connect(self._on_axis_setting_changed)
            self.ui.spine_color_button.clicked.connect(self._on_change_spine_color)

            self.major_tick_direction_combo.currentTextChanged.connect(self._on_axis_setting_changed)
            self.minor_tick_direction_combo.currentTextChanged.connect(self._on_axis_setting_changed)
            self.major_tick_direction_y2_combo.currentTextChanged.connect(self._on_axis_setting_changed)
            self.minor_tick_direction_y2_combo.currentTextChanged.connect(self._on_axis_setting_changed)


            # --- 3. データセット関連のシグナル ---

            # (データセットリストタブ)
            self.ui.add_dataset_button.clicked.connect(self._on_add_dataset)
            self.ui.remove_dataset_button.clicked.connect(self._on_remove_dataset)
            self.new_folder_button.clicked.connect(self._on_new_folder)
            self.ui.dataset_list_widget.currentItemChanged.connect(self._on_dataset_selected)
            self.ui.dataset_list_widget.customContextMenuRequested.connect(self._on_dataset_tree_context_menu)
            # ドラッグ&ドロップでの並べ替え/フォルダ移動(=描画の重なり順の変更)を project.datasets に反映する
            self.ui.dataset_list_widget.model().rowsMoved.connect(self._on_dataset_rows_moved)

            # (データセットプロパティタブ)

            # ★ 凡例名は editingFinished (Enterキー押下 or フォーカス喪失時) を使う
            #    (textChanged だと1文字打つたびにグラフが再描画され、重くなるため)
            self.ui.legend_name_edit.editingFinished.connect(self._on_legend_name_changed)

            self.ui.plot_type_combo.currentTextChanged.connect(self._on_property_changed)
            self.ui.color_button.clicked.connect(self._on_change_dataset_color)
            self.ui.linestyle_combo.currentTextChanged.connect(self._on_property_changed)
            self.ui.linewidth_spinbox.valueChanged.connect(self._on_property_changed)
            self.ui.marker_combo.currentTextChanged.connect(self._on_property_changed)
            self.ui.markersize_spinbox.valueChanged.connect(self._on_property_changed)
            self.ui.smoothing_checkbox.stateChanged.connect(self._on_property_changed)
            self.alpha_spinbox.valueChanged.connect(self._on_property_changed)

            self.fit_curve_button.clicked.connect(self._on_fit_curve)
            self.find_peaks_button.clicked.connect(self._on_find_peaks)

            self.use_secondary_y_checkbox.stateChanged.connect(self._on_secondary_y_changed)
            self.subplot_target_combo.currentIndexChanged.connect(self._on_subplot_target_changed)

            self.duplicate_dataset_button.clicked.connect(self._on_duplicate_dataset)
            self.auto_color_button.clicked.connect(self._on_auto_assign_colors)
            self.view_edit_data_button.clicked.connect(self._on_show_data_editor)

            self.x_col_combo.currentTextChanged.connect(self._on_plot_column_changed)
            self.y_col_combo.currentTextChanged.connect(self._on_plot_column_changed)
            self.x_err_col_combo.currentTextChanged.connect(self._on_error_column_changed)
            self.y_err_col_combo.currentTextChanged.connect(self._on_error_column_changed)

    def _create_menu_bar(self):
            """
            メインウィンドウのメニューバー (「ファイル」「表示」「ヘルプ」) を作成します。
            __init__ から一度だけ呼び出されます。
            """

            # QMainWindow が持つ menuBar() を取得
            menu_bar = self.menuBar()

            # --- 1. 「ファイル」メニュー ---
            # "ファイル(&F)" の &F は、Alt+F で開くためのニーモニック
            file_menu = menu_bar.addMenu("ファイル(&F)")

            # (プロジェクト機能)
            open_project_action = file_menu.addAction("プロジェクトを開く(&O)...")
            open_project_action.setShortcut(QKeySequence.StandardKey.Open)
            open_project_action.triggered.connect(self._on_load_project)

            save_project_action = file_menu.addAction("プロジェクトを保存(&P)...")
            save_project_action.setShortcut(QKeySequence.StandardKey.Save)
            save_project_action.triggered.connect(self._on_save_project)

            # 最近使ったファイル (プロジェクト/データファイル共通の履歴)
            self.recent_files_menu = file_menu.addMenu("最近使ったファイル")
            self._update_recent_files_menu()

            file_menu.addSeparator() # 区切り線

            # (テンプレート機能)
            save_template_action = file_menu.addAction("書式テンプレートを保存(&T)...")
            save_template_action.triggered.connect(self._on_save_plot_template)

            load_template_action = file_menu.addAction("書式テンプレートを適用(&A)...")
            load_template_action.triggered.connect(self._on_load_plot_template)

            file_menu.addSeparator() # --- 区切り線 ---

            # (エクスポート機能)
            save_action = file_menu.addAction("名前を付けてエクスポート(&S)...")
            save_action.setShortcut(QKeySequence.StandardKey.SaveAs)
            save_action.triggered.connect(self._on_export_plot)

            # (クリップボードコピー: Ctrl+C は既存のテキスト編集のコピー操作と
            #  衝突しうるため、あえてショートカットは割り当てずメニューのみにする)
            copy_plot_action = file_menu.addAction("グラフをコピー(&C)")
            copy_plot_action.triggered.connect(self._on_copy_plot_to_clipboard)

            file_menu.addSeparator() # --- 区切り線 ---

            # (オートセーブ設定: テキストには現在の状態(有効/無効・間隔)を表示する)
            self.autosave_interval_action = file_menu.addAction("オートセーブ間隔を設定(&I)...")
            self.autosave_interval_action.triggered.connect(self._on_configure_autosave_interval)
            self._update_autosave_menu_text()

            # --- 2. 「編集」メニュー ---
            # データセットのプロパティ変更 (色・線種・凡例名など) の Undo/Redo
            # (DataEditorDialog 内のセル編集用スタックとは別の、メインウィンドウ用スタック)
            edit_menu = menu_bar.addMenu("編集(&E)")

            undo_action = self.undo_stack.createUndoAction(self, "元に戻す")
            undo_action.setShortcut(QKeySequence.StandardKey.Undo)
            edit_menu.addAction(undo_action)

            redo_action = self.undo_stack.createRedoAction(self, "やり直し")
            redo_action.setShortcut(QKeySequence.StandardKey.Redo)
            edit_menu.addAction(redo_action)

            # --- 3. 「表示」メニュー ---
            view_menu = menu_bar.addMenu("表示(&V)")

            # QDockWidget が持つ標準の「表示/非表示」アクションを取得
            dock_widget_action = self.ui.control_dock_widget.toggleViewAction()
            dock_widget_action.setText("プロット制御パネル") # メニューに表示される名前を設定
            view_menu.addAction(dock_widget_action)

            # ★ (__init__ で作成した properties_dock_widget も同様に追加可能)
            properties_dock_action = self.properties_dock_widget.toggleViewAction()
            properties_dock_action.setText("データセットプロパティ")
            view_menu.addAction(properties_dock_action)

            view_menu.addSeparator()

            # ダークモード切り替え (アプリ全体のQtパレット + グラフの配色の両方に適用)
            # チェック状態は設定から復元する。setChecked() は toggled.connect() より前に
            # 行うことで、復元時に _on_toggle_dark_mode が二重に呼ばれないようにしている。
            dark_mode_action = view_menu.addAction("ダークモード")
            dark_mode_action.setCheckable(True)
            dark_mode_action.setChecked(self.canvas.dark_mode)
            dark_mode_action.toggled.connect(self._on_toggle_dark_mode)
            # 起動時のモードに関わらず必ず呼び、Fusionスタイルを一貫して適用する
            # (呼ばないとネイティブスタイルのままになり、後でダーク→ライトと
            # 切り替えた際にツールバーサイズ等が変わってしまう)
            apply_theme(QApplication.instance(), self.canvas.dark_mode)


            # --- 4. 「ヘルプ」メニュー ---
            help_menu = menu_bar.addMenu("ヘルプ(&H)")

            mathtext_help_action = help_menu.addAction("mathtext リファレンス...")
            mathtext_help_action.triggered.connect(self._on_show_help) # HelpDialog を表示

            calc_help_action = help_menu.addAction("列計算機能 リファレンス...")
            calc_help_action.triggered.connect(self._on_show_calc_help) # CalcHelpDialog を表示

            help_menu.addSeparator()

            about_action = help_menu.addAction(f"{APP_NAME} について...")
            about_action.triggered.connect(self._on_show_about) # AboutDialog を表示

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
