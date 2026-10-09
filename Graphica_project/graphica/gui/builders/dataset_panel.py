"""データセットの一覧とプロパティ欄の欄の組み立て。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QHeaderView,
    QLabel, QLineEdit,
    QMenu, QPushButton, QSpinBox, QTextEdit, QToolButton, QTreeWidget, QVBoxLayout, QWidget, QWidgetAction)
from graphica.core.dataset import WATERFALL_OFFSET_ABSOLUTE, WATERFALL_OFFSET_STEP
from graphica.core.i18n import tr
from graphica.gui.builders.common import (
    COLORMAP_CHOICES, DATASET_TREE_VISIBILITY_COLUMN_WIDTH, _DatasetTreeSelectionDelegate, _insert_form_row_after,
    _svg_icon)
from graphica.gui.color_picker_widget import ColorPickerWidget
from graphica.gui.dataset_style_icon import DATASET_TREE_NAME_COLUMN, DATASET_TREE_VISIBILITY_COLUMN


def build_dataset_color_picker(app):
    old_color_button = app.ui.color_button
    app.color_picker_widget = ColorPickerWidget(app.settings, app)
    app.ui.formLayout_4.replaceWidget(old_color_button, app.color_picker_widget)
    old_color_button.hide()
    old_color_button.deleteLater()

    # 「データ追加」のすぐ隣
    app.new_dataset_button = QPushButton(tr("新規データセット作成..."))
    app.ui.horizontalLayout_3.insertWidget(1, app.new_dataset_button)


def build_dataset_list_buttons(app):
    app.duplicate_dataset_button = QPushButton(tr("プロット複製"))
    app.view_edit_data_button = QPushButton(tr("データ表示/編集"))
    app.fit_curve_button = QPushButton(tr("曲線フィット"))
    app.find_peaks_button = QPushButton(tr("ピーク検出"))
    app.multi_peak_fit_button = QPushButton(tr("多峰フィット"))
    app.auto_color_button = QPushButton(tr("自動配色"))
    app.new_folder_button = QPushButton(tr("新しいフォルダ"))

    # ボタンをアイコンだけにして「データ処理」「解析」「整理」の3組に分ける(文字はツールチップに残す)。
    # ダークモードの切り替えでアイコンを作り直すので(_refresh_custom_svg_icons)、対応を持っておく
    app._dataset_action_button_icons = {
        app.ui.add_dataset_button: ("file-plus", tr("データ追加")),
        app.new_dataset_button: ("table", tr("新規作成")),
        app.duplicate_dataset_button: ("copy", tr("複製")),
        app.view_edit_data_button: ("edit", tr("表示/編集")),
        app.ui.remove_dataset_button: ("trash", tr("削除")),
        app.fit_curve_button: ("chart-line", tr("曲線フィット")),
        app.find_peaks_button: ("mountain", tr("ピーク検出")),
        app.multi_peak_fit_button: ("chart-histogram", tr("多峰フィット")),
        app.auto_color_button: ("palette", tr("自動配色")),
        app.new_folder_button: ("folder-plus", tr("新しいフォルダ")),
    }
    for button, (icon_name, short_label) in app._dataset_action_button_icons.items():
        button.setToolTip(button.text() or short_label)
        button.setText("")
        button.setIcon(_svg_icon(icon_name, size=18))
        button.setProperty("iconOnly", True)
        button.setFixedSize(34, 34)
        # フォーカスを持つと、押した後も :focus の枠が残って押されたままに見える
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _make_group_separator():
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("button_row_separator")
        sep.setFixedWidth(2)
        return sep

    # データ処理: 追加・新規作成・複製・表示編集・削除(削除は Designer の配置のまま)
    app.ui.horizontalLayout_3.insertWidget(2, app.duplicate_dataset_button)
    app.ui.horizontalLayout_3.insertWidget(3, app.view_edit_data_button)

    app.ui.horizontalLayout_3.insertWidget(5, _make_group_separator())
    # 解析
    app.ui.horizontalLayout_3.addWidget(app.fit_curve_button)
    app.ui.horizontalLayout_3.addWidget(app.find_peaks_button)
    app.ui.horizontalLayout_3.addWidget(app.multi_peak_fit_button)

    app.ui.horizontalLayout_3.addWidget(_make_group_separator())
    # 整理
    app.ui.horizontalLayout_3.addWidget(app.auto_color_button)
    app.ui.horizontalLayout_3.addWidget(app.new_folder_button)

    app.ui.horizontalLayout_3.addStretch()

    # 「⋯」: たまにしか使わない操作
    app.dataset_overflow_button = QToolButton()
    app.dataset_overflow_button.setText("⋯")
    app.dataset_overflow_button.setToolTip(tr("その他の操作"))
    app.dataset_overflow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    app.dataset_overflow_button.setFixedSize(34, 34)
    overflow_menu = QMenu(app.dataset_overflow_button)
    app.manage_palette_action = overflow_menu.addAction(
        _svg_icon("palette", size=16), tr("パレット管理...")
    )
    app.colormap_assign_action = overflow_menu.addAction(
        _svg_icon("palette", size=16), tr("カラーマップから自動配色...")
    )
    # 登録はいつでも変わるので開くたびに作り直す。QMenu と menuAction() の両方を持つ(持たないと回収される)
    app._named_color_apply_menu = overflow_menu.addMenu(
        _svg_icon("color-swatch", size=16), tr("登録した色を適用"))
    app._named_color_apply_menu_action = app._named_color_apply_menu.menuAction()
    app._named_color_apply_menu.aboutToShow.connect(
        app.colors.populate_named_color_menu)
    app.colors.populate_named_color_menu()
    app.dataset_overflow_button.setMenu(overflow_menu)
    app.ui.horizontalLayout_3.addWidget(app.dataset_overflow_button)

    # データセットのプロパティ欄を7つの節に分ける。Designer の行もここで移すので、formLayout_4 を触る
    # 色欄の差し替え(_build_dataset_color_picker)より後であること。以降の行は app._prop_form(キー) に足す
    app._build_dataset_property_sections()


def build_dataset_style_controls(app):
    app.x_col_combo = QComboBox()
    app.y_col_combo = QComboBox()
    app._prop_form('data').addRow("X軸の列", app.x_col_combo)
    app._prop_form('data').addRow("Y軸の列", app.y_col_combo)

    app.x_err_col_combo = QComboBox()
    app.y_err_col_combo = QComboBox()
    app._prop_form('data').addRow("X誤差列", app.x_err_col_combo)
    app._prop_form('data').addRow("Y誤差列", app.y_err_col_combo)

    app.alpha_label = QLabel("透明度")
    app.alpha_spinbox = QDoubleSpinBox()
    app.alpha_spinbox.setRange(0.0, 1.0)
    app.alpha_spinbox.setSingleStep(0.05)
    app.alpha_spinbox.setDecimals(2)
    app.alpha_spinbox.setValue(1.0)
    app._prop_form('style').addRow(app.alpha_label, app.alpha_spinbox)

    # グラデーション(線・面の塗り)。出し入れは property_panel.update_gradient_controls_visibility
    app.gradient_checkbox = QCheckBox(tr("グラデーションを適用"))
    app._prop_form('gradient').addRow(app.gradient_checkbox)

    app.gradient_color2_label = QLabel(tr("終端色"))
    app.gradient_color2_picker = ColorPickerWidget(app.settings, app, initial_color='#ffffff')
    app._prop_form('gradient').addRow(app.gradient_color2_label, app.gradient_color2_picker)

    app.gradient_target_label = QLabel(tr("対象"))
    app.gradient_target_combo = QComboBox()
    app.gradient_target_combo.addItem(tr("線"), "line")
    app.gradient_target_combo.addItem(tr("塗り"), "fill")
    app.gradient_target_combo.addItem(tr("両方"), "both")
    app._prop_form('gradient').addRow(app.gradient_target_label, app.gradient_target_combo)

    # ウォーターフォールは種類ではなく、どの種類とも組み合わせられるオプション。
    # 出し入れは property_panel.update_waterfall_controls_visibility
    app.waterfall_checkbox = QCheckBox(tr("ウォーターフォール表示(積み重ね)"))
    app._prop_form('waterfall').addRow(app.waterfall_checkbox)

    # オフセットの欄は大きな値や指数表記(1.5E6)も入れられる(main_window の _enable_scientific_notation_input)
    app.waterfall_offset_mode_label = QLabel(tr("オフセットの指定"))
    app.waterfall_offset_mode_combo = QComboBox()
    app.waterfall_offset_mode_combo.addItem(tr("段ごとの間隔(段の番号 × オフセット)"), WATERFALL_OFFSET_STEP)
    app.waterfall_offset_mode_combo.addItem(tr("ずらし量をそのまま"), WATERFALL_OFFSET_ABSOLUTE)
    app._prop_form('waterfall').addRow(app.waterfall_offset_mode_label, app.waterfall_offset_mode_combo)

    app.waterfall_offset_x_label = QLabel(tr("Xオフセット"))
    app.waterfall_offset_x_spinbox = QDoubleSpinBox()
    app.waterfall_offset_x_spinbox.setRange(-1e6, 1e6)
    app.waterfall_offset_x_spinbox.setSingleStep(0.1)
    app.waterfall_offset_x_spinbox.setDecimals(4)
    app.waterfall_offset_x_spinbox.setValue(0.0)
    app._prop_form('waterfall').addRow(app.waterfall_offset_x_label, app.waterfall_offset_x_spinbox)

    app.waterfall_offset_y_label = QLabel(tr("Yオフセット"))
    app.waterfall_offset_y_spinbox = QDoubleSpinBox()
    app.waterfall_offset_y_spinbox.setRange(-1e6, 1e6)
    app.waterfall_offset_y_spinbox.setSingleStep(0.1)
    app.waterfall_offset_y_spinbox.setDecimals(4)
    app.waterfall_offset_y_spinbox.setValue(1.0)
    app._prop_form('waterfall').addRow(app.waterfall_offset_y_label, app.waterfall_offset_y_spinbox)

    app.waterfall_occlusion_checkbox = QCheckBox(tr("背面のトレースを隠す(オクルージョン)"))
    app.waterfall_occlusion_checkbox.setChecked(True)
    app._prop_form('waterfall').addRow(app.waterfall_occlusion_checkbox)

    # 奥の段ほど Y をわずかに縮めて立体風にする
    app.waterfall_depth_checkbox = QCheckBox(tr("奥行き効果(奥のトレースをわずかに縮小)"))
    app.waterfall_depth_checkbox.setChecked(False)
    app._prop_form('waterfall').addRow(app.waterfall_depth_checkbox)

    app.waterfall_depth_ratio_label = QLabel(tr("1段あたりの縮小率"))
    app.waterfall_depth_ratio_spinbox = QDoubleSpinBox()
    app.waterfall_depth_ratio_spinbox.setRange(0.0, 0.9)
    app.waterfall_depth_ratio_spinbox.setSingleStep(0.01)
    app.waterfall_depth_ratio_spinbox.setDecimals(3)
    app.waterfall_depth_ratio_spinbox.setValue(0.03)
    app._prop_form('waterfall').addRow(app.waterfall_depth_ratio_label, app.waterfall_depth_ratio_spinbox)

    app.point_labels_checkbox = QCheckBox("データ点にラベルを表示")
    app._prop_form('extra').addRow(app.point_labels_checkbox)
    # 点が上限を超えてラベルを描かないときに、その理由を出す
    app.point_labels_limit_note = QLabel()
    app.point_labels_limit_note.setObjectName("point_labels_limit_note")
    app.point_labels_limit_note.setWordWrap(True)
    app.point_labels_limit_note.setVisible(False)
    app._prop_form('extra').addRow(app.point_labels_limit_note)
    app.point_label_col_label = QLabel("ラベルの内容")
    app.point_label_col_combo = QComboBox()
    app._prop_form('extra').addRow(app.point_label_col_label, app.point_label_col_combo)

    # 誤差の表し方。誤差列が無ければどれを選んでも描かれない
    app.error_display_label = QLabel(tr("誤差の表示形式"))
    app.error_display_combo = QComboBox()
    app.error_display_combo.addItem(tr("エラーバー"), "bar")
    app.error_display_combo.addItem(tr("誤差バンド"), "band")
    app.error_display_combo.addItem(tr("両方"), "both")
    app._prop_form('extra').addRow(app.error_display_label, app.error_display_combo)

    # 凡例名(= データセット名)を変えずに凡例の文字だけ変える。空ならデータセット名
    app.legend_label_label = QLabel(tr("凡例の表示名"))
    app.legend_label_edit = QLineEdit()
    app.legend_label_edit.setPlaceholderText(tr("空ならデータセット名"))
    app._prop_form('extra').addRow(app.legend_label_label, app.legend_label_edit)
    app.hide_from_legend_checkbox = QCheckBox(tr("凡例に表示しない"))
    app._prop_form('extra').addRow(app.hide_from_legend_checkbox)

    # X/Y/Z 列の長形式を2Dマップとして描く。関係する欄の出し入れは property_panel.update_2d_controls_visibility
    app.data_2d_checkbox = QCheckBox(tr("2Dグリッドデータとして扱う(ヒートマップ)"))
    app._prop_form('map').addRow(app.data_2d_checkbox)

    app.z_col_label = QLabel(tr("Z軸の列"))
    app.z_col_combo = QComboBox()
    app._prop_form('map').addRow(app.z_col_label, app.z_col_combo)

    app.colormap_label = QLabel(tr("カラーマップ"))
    app.colormap_combo = QComboBox()
    app.colormap_combo.addItems(COLORMAP_CHOICES)
    app._prop_form('map').addRow(app.colormap_label, app.colormap_combo)

    app.map_display_mode_label = QLabel(tr("表示方式"))
    app.map_display_mode_combo = QComboBox()
    app.map_display_mode_combo.addItem(tr("ヒートマップ"), "heatmap")
    app.map_display_mode_combo.addItem(tr("等高線(線)"), "contour")
    app.map_display_mode_combo.addItem(tr("等高線(塗りつぶし)"), "contour_filled")
    app.map_display_mode_combo.addItem(tr("ヒートマップ+等高線"), "heatmap_contour")
    app._prop_form('map').addRow(app.map_display_mode_label, app.map_display_mode_combo)

    app.contour_levels_label = QLabel(tr("等高線レベル数"))
    app.contour_levels_spinbox = QSpinBox()
    app.contour_levels_spinbox.setRange(2, 100)
    app.contour_levels_spinbox.setValue(10)
    app._prop_form('map').addRow(app.contour_levels_label, app.contour_levels_spinbox)

    app.grid_interp_method_label = QLabel(tr("補間方法"))
    app.grid_interp_method_combo = QComboBox()
    app.grid_interp_method_combo.addItems(['linear', 'cubic', 'nearest'])
    app._prop_form('map').addRow(app.grid_interp_method_label, app.grid_interp_method_combo)

    app.color_range_auto_checkbox = QCheckBox(tr("値域を自動"))
    app.color_range_auto_checkbox.setChecked(True)
    app._prop_form('map').addRow(app.color_range_auto_checkbox)

    app.vmin_label = QLabel(tr("値域の最小"))
    app.vmin_spinbox = QDoubleSpinBox()
    app.vmin_spinbox.setRange(-1e12, 1e12)
    app.vmin_spinbox.setDecimals(4)
    app.vmin_spinbox.setEnabled(False)
    app._prop_form('map').addRow(app.vmin_label, app.vmin_spinbox)

    app.vmax_label = QLabel(tr("値域の最大"))
    app.vmax_spinbox = QDoubleSpinBox()
    app.vmax_spinbox.setRange(-1e12, 1e12)
    app.vmax_spinbox.setDecimals(4)
    app.vmax_spinbox.setValue(1.0)
    app.vmax_spinbox.setEnabled(False)
    app._prop_form('map').addRow(app.vmax_label, app.vmax_spinbox)

    # 欠損値の扱いは描くときだけに効く(データ自体は変えない)。
    # ラベルの列幅は全部の節で揃えるので、ここが一番長いと全体の入力欄が狭まる。「(NaN)」はツールチップに回す
    app.nan_policy_label = QLabel(tr("欠損値の扱い"))
    app.nan_policy_label.setToolTip(tr("欠損値(NaN)を含む点の描画方法"))
    app.nan_policy_combo = QComboBox()
    app.nan_policy_combo.addItem(tr("線を切る(既定)"), "gap")
    app.nan_policy_combo.addItem(tr("前の値で埋める"), "ffill")
    app.nan_policy_combo.addItem(tr("無視してつなぐ"), "drop")
    app._prop_form('data').addRow(app.nan_policy_label, app.nan_policy_combo)

    # 平滑化の手法。オン/オフは Designer の smoothing_checkbox
    app.smoothing_method_label = QLabel(tr("平滑化の手法"))
    app.smoothing_method_combo = QComboBox()
    app.smoothing_method_combo.addItem(tr("CubicSpline(既定)"), "cubic_spline")
    app.smoothing_method_combo.addItem(tr("移動平均"), "moving_average")
    app.smoothing_method_combo.addItem(tr("中央値フィルタ"), "median")
    app.smoothing_method_combo.addItem(tr("ガウシアンフィルタ"), "gaussian")
    # 「平滑化」のチェックは手法と対なので、_build_dataset_property_sections では移さずここで手法の直前に置く
    # (そうしないと間に「透明度」が挟まる)
    app._prop_form('style').addRow(app.ui.smoothing_checkbox)
    app._prop_form('style').addRow(app.smoothing_method_label, app.smoothing_method_combo)


def build_fit_info_and_stats(app):
    app.fit_info_label = QLabel("フィット情報")
    app.fit_info_textedit = QTextEdit()
    app.fit_info_textedit.setReadOnly(True)
    app.fit_info_textedit.setFixedHeight(100)
    # 節の最後(描画先の後ろ)に置く(_add_subplot_target_row)。フィットが無いと隠れる欄なので、
    # 先頭に置くとフィットのたびに下の項目が押し下げられる

    # 統計値はいつも見るものではないので、ツールバーのボタンから開く小窓に出す。
    # 中身は選択が変わるたびに property_panel.update_stats_summary_label が更新する(閉じている間も)
    app.stats_summary_label = QLabel("-")
    app.stats_summary_label.setWordWrap(True)
    app.stats_summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    app.stats_toolbar_button = QToolButton()
    app.stats_toolbar_button.setIcon(_svg_icon("chart-histogram"))
    app.stats_toolbar_button.setToolTip(tr("統計情報 (選択中データセットのY列の要約統計量)"))
    app.stats_toolbar_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    stats_popup = QWidget()
    stats_popup_layout = QVBoxLayout(stats_popup)
    stats_popup_layout.setContentsMargins(10, 8, 10, 8)
    stats_popup_title = QLabel(tr("統計 (Y列)"))
    stats_popup_title_font = QFont(stats_popup_title.font())
    stats_popup_title_font.setBold(True)
    stats_popup_title.setFont(stats_popup_title_font)
    stats_popup_layout.addWidget(stats_popup_title)
    app.stats_summary_label.setMinimumWidth(260)
    stats_popup_layout.addWidget(app.stats_summary_label)

    stats_menu = QMenu(app.stats_toolbar_button)
    stats_widget_action = QWidgetAction(app.stats_toolbar_button)
    stats_widget_action.setDefaultWidget(stats_popup)
    stats_menu.addAction(stats_widget_action)
    app.stats_toolbar_button.setMenu(stats_menu)
    app.plot_toolbar.addSeparator()
    app.plot_toolbar.addWidget(app.stats_toolbar_button)


def _y2_value_spinbox(decimals=2):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(-2147483648.0, 2147483648.0)
    spinbox.setDecimals(decimals)
    return spinbox


def _build_secondary_y_axis_group(app):
    """「Y軸」タブの末尾に、第 2 Y 軸の範囲と目盛りの欄を足す(主の Y 軸の欄と同じ並び)。"""
    app.y2_axis_group = QGroupBox(tr("第2Y軸"))
    form = QFormLayout(app.y2_axis_group)
    app.y2_autoscale_checkbox = QCheckBox(tr("自動スケール"))
    app.y2_autoscale_checkbox.setChecked(True)
    form.addRow(app.y2_autoscale_checkbox)
    app.y2_min_spinbox = _y2_value_spinbox()
    form.addRow(tr("最小値"), app.y2_min_spinbox)
    app.y2_max_spinbox = _y2_value_spinbox()
    app.y2_max_spinbox.setValue(1.0)
    form.addRow(tr("最大値"), app.y2_max_spinbox)
    app.y2_log_checkbox = QCheckBox(tr("対数表示"))
    form.addRow(app.y2_log_checkbox)
    # 対数軸で表示されない 0 以下の値を知らせる(中身は log_axis_notes.update_log_axis_notes)
    app.y2_log_note = QLabel()
    app.y2_log_note.setObjectName("y2_log_note")
    app.y2_log_note.setWordWrap(True)
    app.y2_log_note.setVisible(False)
    form.addRow(app.y2_log_note)
    app.y2_invert_checkbox = QCheckBox(tr("軸を反転"))
    form.addRow(app.y2_invert_checkbox)
    app.y2_major_tick_mode_combo = QComboBox()
    # 選んだ番号で値を持つ(index の束ね)ので、表示を訳してよい
    app.y2_major_tick_mode_combo.addItems([tr("自動"), tr("固定間隔")])
    form.addRow(tr("主目盛"), app.y2_major_tick_mode_combo)
    app.y2_major_tick_interval_spinbox = _y2_value_spinbox()
    app.y2_major_tick_interval_spinbox.setValue(1.0)
    form.addRow(tr("間隔"), app.y2_major_tick_interval_spinbox)
    app.y2_minor_ticks_visible_checkbox = QCheckBox(tr("補助目盛を表示"))
    form.addRow(app.y2_minor_ticks_visible_checkbox)
    app.y2_minor_tick_interval_spinbox = _y2_value_spinbox()
    app.y2_minor_tick_interval_spinbox.setValue(0.5)
    form.addRow(tr("補助目盛の間隔"), app.y2_minor_tick_interval_spinbox)
    layout = app.ui.gridLayout_3
    layout.addWidget(app.y2_axis_group, layout.rowCount(), 0, 1, layout.columnCount() or 1)


def build_secondary_y_controls(app):
    app.use_secondary_y_checkbox = QCheckBox("第2Y軸 (右側) を使用")
    app._prop_form('place').addRow(app.use_secondary_y_checkbox)

    app.y2_label_text_label = QLabel("第2Y軸ラベル")
    app.y2_label_text_edit = QLineEdit()
    _insert_form_row_after(app.ui.formLayout_3, app.ui.y_label_text_edit,
                           app.y2_label_text_label, app.y2_label_text_edit)

    _build_secondary_y_axis_group(app)

def add_subplot_target_row(app):
    app.subplot_target_label = QLabel("描画先プロット")
    app.subplot_target_combo = QComboBox()
    app._prop_form('place').addRow(app.subplot_target_label, app.subplot_target_combo)
    # フィット情報欄 (上で構築済み) は、このセクションの最後に置く
    app._prop_form('place').addRow(app.fit_info_label, app.fit_info_textedit)


def replace_dataset_list_with_tree(app):
    """Designer の QListWidget を、同じセルに「検索欄 + QTreeWidget」を縦に並べたものへ差し替える。"""
    old_widget = app.ui.dataset_list_widget
    parent_widget = old_widget.parentWidget()
    parent_layout = parent_widget.layout()

    idx = parent_layout.indexOf(old_widget)
    row = col = rowspan = colspan = None
    if isinstance(parent_layout, QGridLayout):
        row, col, rowspan, colspan = parent_layout.getItemPosition(idx)

    parent_layout.removeWidget(old_widget)
    old_widget.setParent(None)
    old_widget.deleteLater()

    container = QWidget(parent_widget)
    container_layout = QVBoxLayout(container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(6)

    search_edit = QLineEdit(container)
    search_edit.setObjectName("dataset_search_edit")
    search_edit.setPlaceholderText("データセットを検索...")
    search_edit.setClearButtonEnabled(True)
    container_layout.addWidget(search_edit)

    tree = QTreeWidget(container)
    tree.setObjectName("dataset_list_widget")
    tree.setHeaderHidden(True)
    # 列1は表示/非表示の目のアイコン。stretchLastSection のままだと目の列が余白を吸って広がる
    tree.setColumnCount(2)
    header = tree.header()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(DATASET_TREE_NAME_COLUMN, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(DATASET_TREE_VISIBILITY_COLUMN, QHeaderView.ResizeMode.Fixed)
    tree.setColumnWidth(DATASET_TREE_VISIBILITY_COLUMN, DATASET_TREE_VISIBILITY_COLUMN_WIDTH)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
    tree.setDefaultDropAction(Qt.DropAction.MoveAction)
    tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    # 行の伸びをキャンバスに譲ったので、放っておくと数件でも窮屈な高さまで縮む
    tree.setMinimumHeight(90)
    tree.setItemDelegate(_DatasetTreeSelectionDelegate(tree))
    container_layout.addWidget(tree)

    # 一覧のすぐ下に、選んでいるデータセットの短い統計値
    mini_stats_label = QLabel("-")
    mini_stats_label.setObjectName("dataset_mini_stats_label")
    mini_stats_label.setWordWrap(True)
    container_layout.addWidget(mini_stats_label)
    app.dataset_mini_stats_label = mini_stats_label

    if isinstance(parent_layout, QGridLayout) and row is not None:
        parent_layout.addWidget(container, row, col, rowspan, colspan)
    else:
        parent_layout.addWidget(container)

    app.ui.dataset_list_widget = tree
    app.dataset_search_edit = search_edit
