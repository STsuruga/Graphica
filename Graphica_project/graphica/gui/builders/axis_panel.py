"""軸の設定の欄(凡例の位置・目盛り・グリッド・カラーバー・目盛りの書式・タイトルと軸ラベル・ラベルのタブ)の組み立て。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget)
from graphica.core.i18n import tr
from graphica.core.unit_conversion import X_AXIS_UNIT_CHOICES, X_AXIS_UNIT_LABELS
from graphica.gui.builders.common import _ClickableMathPreviewLabel, _insert_form_row_after, _svg_icon
from graphica.gui.canvas import DEFAULT_MAJOR_TICK_LENGTH, MINOR_TICK_LENGTH_AUTO
from graphica.gui.mixins.layout_edit_mixin import MIN_FREE_RECT_SIZE


def build_legend_location_control(app):
    app.legend_loc_label = QLabel("凡例の位置")
    app.legend_loc_combo = QComboBox()
    app.legend_loc_combo.addItems([
        "best", "upper right", "upper left", "lower left", "lower right", "center"
    ])
    _insert_form_row_after(app.ui.formLayout_3, app.ui.legend_visible_checkbox,
                           app.legend_loc_label, app.legend_loc_combo)

    app.legend_font_label = QLabel("凡例フォント")
    app.legend_font_button = QPushButton("フォント選択...")
    _insert_form_row_after(app.ui.formLayout_3, app.legend_loc_combo,
                           app.legend_font_label, app.legend_font_button)

    app.legend_color_label = QLabel("凡例 文字色")
    app.legend_color_button = QPushButton("色選択...")
    _insert_form_row_after(app.ui.formLayout_3, app.legend_font_button,
                           app.legend_color_label, app.legend_color_button)

    # 凡例の並びは描画順とは別に決められる
    app.legend_order_button = QPushButton("凡例の順序...")
    _insert_form_row_after(app.ui.formLayout_3, app.legend_color_button, app.legend_order_button)

    # ダークモードの切り替えで作り直すので(_refresh_custom_svg_icons)、対応を持っておく
    app._field_icon_buttons = {
        app.ui.tick_font_button: "typography",
        app.ui.tick_color_button: "color-swatch",
        app.ui.axis_label_font_button: "typography",
        app.ui.axis_label_color_button: "color-swatch",
        app.ui.spine_color_button: "color-swatch",
        app.legend_font_button: "typography",
        app.legend_color_button: "color-swatch",
    }
    for button, icon_name in app._field_icon_buttons.items():
        button.setIcon(_svg_icon(icon_name, size=16))


def build_tick_grid_and_colorbar_controls(app):
    app.tick_direction_label = QLabel("主軸目盛(主/補助)")
    app.major_tick_direction_combo = QComboBox()
    app.major_tick_direction_combo.addItems(["out", "in", "inout"])
    app.minor_tick_direction_combo = QComboBox()
    app.minor_tick_direction_combo.addItems(["out", "in", "inout"])
    dir_layout = QHBoxLayout()
    dir_layout.addWidget(app.major_tick_direction_combo)
    dir_layout.addWidget(app.minor_tick_direction_combo)

    app.tick_direction_y2_label = QLabel("第2軸目盛(主/補助)")
    app.major_tick_direction_y2_combo = QComboBox()
    app.major_tick_direction_y2_combo.addItems(["out", "in", "inout"])
    app.minor_tick_direction_y2_combo = QComboBox()
    app.minor_tick_direction_y2_combo.addItems(["out", "in", "inout"])
    dir_y2_layout = QHBoxLayout()
    dir_y2_layout.addWidget(app.major_tick_direction_y2_combo)
    dir_y2_layout.addWidget(app.minor_tick_direction_y2_combo)

    _insert_form_row_after(app.ui.formLayout_3, app.ui.tick_format_label, app.tick_direction_label, dir_layout)
    _insert_form_row_after(app.ui.formLayout_3, app.tick_direction_label, app.tick_direction_y2_label, dir_y2_layout)

    # グリッド線の線種・太さ・透明度(X/Y × 主/補助)。「補助グリッドの表示」のすぐ下に置く
    app.grid_linestyle_choices = [
        (tr("実線"), '-'), (tr("破線"), '--'), (tr("点線"), ':'), (tr("一点鎖線"), '-.'),
    ]

    def _make_grid_style_row(default_linestyle, default_width):
        linestyle_combo = QComboBox()
        for choice_label, _code in app.grid_linestyle_choices:
            linestyle_combo.addItem(choice_label)
        default_index = next(
            (i for i, (_label, code) in enumerate(app.grid_linestyle_choices) if code == default_linestyle),
            0
        )
        linestyle_combo.setCurrentIndex(default_index)
        linestyle_combo.setToolTip(tr("線種"))
        linestyle_combo.setMaximumWidth(90)

        width_spinbox = QDoubleSpinBox()
        width_spinbox.setRange(0.1, 10.0)
        width_spinbox.setSingleStep(0.1)
        width_spinbox.setDecimals(1)
        width_spinbox.setValue(default_width)
        width_spinbox.setToolTip(tr("太さ"))
        # これより狭いと矢印ボタンと重なって "10.0" のような値が見切れる
        width_spinbox.setMinimumWidth(60)
        width_spinbox.setMaximumWidth(78)

        alpha_spinbox = QDoubleSpinBox()
        alpha_spinbox.setRange(0.0, 1.0)
        alpha_spinbox.setSingleStep(0.05)
        alpha_spinbox.setDecimals(2)
        alpha_spinbox.setValue(1.0)
        alpha_spinbox.setToolTip(tr("透過度(アルファ)"))
        alpha_spinbox.setMinimumWidth(60)
        alpha_spinbox.setMaximumWidth(78)

        row_layout = QHBoxLayout()
        row_layout.addWidget(linestyle_combo)
        row_layout.addWidget(width_spinbox)
        row_layout.addWidget(alpha_spinbox)
        return linestyle_combo, width_spinbox, alpha_spinbox, row_layout

    (app.x_major_grid_linestyle_combo, app.x_major_grid_width_spinbox,
     app.x_major_grid_alpha_spinbox, x_major_grid_layout) = _make_grid_style_row('-', 0.8)
    (app.x_minor_grid_linestyle_combo, app.x_minor_grid_width_spinbox,
     app.x_minor_grid_alpha_spinbox, x_minor_grid_layout) = _make_grid_style_row('--', 0.5)
    (app.y_major_grid_linestyle_combo, app.y_major_grid_width_spinbox,
     app.y_major_grid_alpha_spinbox, y_major_grid_layout) = _make_grid_style_row('-', 0.8)
    (app.y_minor_grid_linestyle_combo, app.y_minor_grid_width_spinbox,
     app.y_minor_grid_alpha_spinbox, y_minor_grid_layout) = _make_grid_style_row('--', 0.5)

    app.x_major_grid_style_label = QLabel(tr("X軸主目盛"))
    app.x_minor_grid_style_label = QLabel(tr("X軸補助目盛"))
    app.y_major_grid_style_label = QLabel(tr("Y軸主目盛"))
    app.y_minor_grid_style_label = QLabel(tr("Y軸補助目盛"))

    _grid_style_anchor = app.ui.minor_grid_visible_checkbox
    for _grid_style_label, _grid_style_layout in (
        (app.x_major_grid_style_label, x_major_grid_layout),
        (app.x_minor_grid_style_label, x_minor_grid_layout),
        (app.y_major_grid_style_label, y_major_grid_layout),
        (app.y_minor_grid_style_label, y_minor_grid_layout),
    ):
        _insert_form_row_after(app.ui.formLayout_3, _grid_style_anchor, _grid_style_label, _grid_style_layout)
        _grid_style_anchor = _grid_style_label

    # 目盛線の長さ(pt)。「目盛の太さ」の直後。補助目盛の最小値(-0.5)は「自動」(主目盛 × MINOR_TICK_LENGTH_RATIO)
    app.tick_length_label = QLabel(tr("目盛の長さ(主/補助)"))
    app.major_tick_length_spinbox = QDoubleSpinBox()
    app.major_tick_length_spinbox.setRange(0.0, 20.0)
    app.major_tick_length_spinbox.setSingleStep(0.5)
    app.major_tick_length_spinbox.setDecimals(1)
    app.major_tick_length_spinbox.setSuffix(" pt")
    app.major_tick_length_spinbox.setValue(DEFAULT_MAJOR_TICK_LENGTH)
    app.major_tick_length_spinbox.setToolTip(tr("主目盛の線の長さ(pt)"))
    app.minor_tick_length_spinbox = QDoubleSpinBox()
    app.minor_tick_length_spinbox.setRange(MINOR_TICK_LENGTH_AUTO, 20.0)
    app.minor_tick_length_spinbox.setSingleStep(0.5)
    app.minor_tick_length_spinbox.setDecimals(1)
    app.minor_tick_length_spinbox.setSuffix(" pt")
    app.minor_tick_length_spinbox.setSpecialValueText(tr("自動"))
    app.minor_tick_length_spinbox.setValue(MINOR_TICK_LENGTH_AUTO)
    app.minor_tick_length_spinbox.setToolTip(
        tr("補助目盛の線の長さ(pt)。「自動」は主目盛の長さの約0.57倍"))
    # QDoubleSpinBox を2つ並べると最小幅が約306pxになり、フォームの列幅を広げてドックに横スクロールが出る
    # (tests/test_main_window.py が検出)。すぐ上の目盛方向の欄と同じ幅に揃える
    for _tick_length_spin in (app.major_tick_length_spinbox, app.minor_tick_length_spinbox):
        _tick_length_spin.setMinimumWidth(app.major_tick_direction_combo.minimumSizeHint().width())
    tick_length_layout = QHBoxLayout()
    tick_length_layout.addWidget(app.major_tick_length_spinbox)
    tick_length_layout.addWidget(app.minor_tick_length_spinbox)
    _insert_form_row_after(app.ui.formLayout_3, app.ui.tick_width_spinbox,
                           app.tick_length_label, tick_length_layout)

    # カラーバーは2Dマップ(か値で色分けした散布図)がある軸でだけ効く
    app.colorbar_enabled_checkbox = QCheckBox(tr("カラーバーを表示"))
    app.colorbar_enabled_checkbox.setChecked(True)
    app.ui.formLayout_3.addRow(app.colorbar_enabled_checkbox)

    app.colorbar_position_label = QLabel(tr("カラーバーの位置"))
    app.colorbar_position_combo = QComboBox()
    app.colorbar_position_combo.addItem(tr("右"), "right")
    app.colorbar_position_combo.addItem(tr("左"), "left")
    app.colorbar_position_combo.addItem(tr("上"), "top")
    app.colorbar_position_combo.addItem(tr("下"), "bottom")
    app.ui.formLayout_3.addRow(app.colorbar_position_label, app.colorbar_position_combo)

    app.colorbar_width_label = QLabel(tr("カラーバーの幅(割合)"))
    app.colorbar_width_spinbox = QDoubleSpinBox()
    app.colorbar_width_spinbox.setRange(0.01, 0.5)
    app.colorbar_width_spinbox.setSingleStep(0.01)
    app.colorbar_width_spinbox.setDecimals(2)
    app.colorbar_width_spinbox.setValue(0.05)
    app.ui.formLayout_3.addRow(app.colorbar_width_label, app.colorbar_width_spinbox)

    app.colorbar_label_label = QLabel(tr("カラーバーのラベル"))
    app.colorbar_label_edit = QLineEdit()
    app.ui.formLayout_3.addRow(app.colorbar_label_label, app.colorbar_label_edit)


def build_tick_format_controls(app):
    tick_format_choices = [
        tr("自動"),
        tr("軸端にまとめて指数表記 (×10ⁿ)"),
        tr("目盛りごとに指数表記 (例: 1.0×10¹⁰)"),
        tr("常に小数表記"),
    ]
    app.x_tick_format_label = QLabel(tr("目盛り表記"))
    app.x_tick_format_combo = QComboBox()
    app.x_tick_format_combo.addItems(tick_format_choices)
    app.ui.formLayout.addRow(app.x_tick_format_label, app.x_tick_format_combo)

    # 目盛線と目盛数値の表示は X/Y で別々なので、それぞれの軸のタブに置く
    app.x_ticks_visible_checkbox = QCheckBox(tr("目盛を表示"))
    app.x_ticks_visible_checkbox.setChecked(True)
    app.ui.formLayout.addRow(app.x_ticks_visible_checkbox)
    app.x_tick_labels_visible_checkbox = QCheckBox(tr("目盛の数値を表示"))
    app.x_tick_labels_visible_checkbox.setChecked(True)
    app.ui.formLayout.addRow(app.x_tick_labels_visible_checkbox)

    # 目盛数値の小数点以下の桁数。-1(最小値)は「自動」で、指数表記の設定に任せる
    app.x_tick_decimals_spinbox = QSpinBox()
    app.x_tick_decimals_spinbox.setRange(-1, 10)
    app.x_tick_decimals_spinbox.setSpecialValueText(tr("自動"))
    app.x_tick_decimals_spinbox.setValue(-1)
    app.x_tick_decimals_spinbox.setToolTip(
        tr("目盛りの数値を表示する小数点以下の桁数(「自動」以外を選ぶと指数表記モードより優先されます)"))
    app.ui.formLayout.addRow(QLabel(tr("小数桁数")), app.x_tick_decimals_spinbox)

    # 対数軸で補助目盛を出すときだけ使う(出し入れは _on_x_minor_tick_visibility_changed)。
    # ラベルの列幅は X/Y のタブで揃えるので、長いと両方の入力欄が狭まる。説明はツールチップに回す
    app.x_log_minor_subs_label = QLabel(tr("対数補助目盛"))
    app.x_log_minor_subs_label.setToolTip(tr("対数軸の補助目盛りをどこに打つか"))
    app.x_log_minor_subs_combo = QComboBox()
    app.x_log_minor_subs_combo.addItem(tr("自動(既定)"), "auto")
    app.x_log_minor_subs_combo.addItem(tr("全て(2〜9)"), "all")
    app.x_log_minor_subs_combo.addItem(tr("少なめ(2, 5)"), "few")
    app.x_log_minor_subs_combo.addItem(tr("最小限(5)"), "one")
    app.ui.formLayout.addRow(app.x_log_minor_subs_label, app.x_log_minor_subs_combo)
    app.x_log_minor_labels_checkbox = QCheckBox(tr("補助目盛りに数値ラベルを表示"))
    app.ui.formLayout.addRow(app.x_log_minor_labels_checkbox)
    app.x_log_minor_subs_label.setVisible(False)
    app.x_log_minor_subs_combo.setVisible(False)
    app.x_log_minor_labels_checkbox.setVisible(False)

    # X の単位と上に出したい単位が別々に選ばれていれば、単位を変換した第2X軸を上に付ける。
    # ラベルは短く保つ(フォームの全行でラベルの列幅を共有するので、長いとドックに横スクロールが出る。
    # test_properties_dock_has_no_horizontal_scrollbar)。説明はツールチップに置く
    unit_combo_choices = [X_AXIS_UNIT_LABELS[u] for u in X_AXIS_UNIT_CHOICES]
    app.x_secondary_axis_source_unit_label = QLabel(tr("X軸単位"))
    app.x_secondary_axis_source_unit_combo = QComboBox()
    app.x_secondary_axis_source_unit_combo.addItems(unit_combo_choices)
    app.x_secondary_axis_source_unit_combo.setToolTip(tr("X軸データが表している物理量の単位"))
    app.ui.formLayout.addRow(
        app.x_secondary_axis_source_unit_label, app.x_secondary_axis_source_unit_combo)

    app.x_secondary_axis_target_unit_label = QLabel(tr("第2X軸単位"))
    app.x_secondary_axis_target_unit_combo = QComboBox()
    app.x_secondary_axis_target_unit_combo.addItems(unit_combo_choices)
    app.x_secondary_axis_target_unit_combo.setToolTip(tr("上部に追加する第2X軸に変換して表示する単位"))
    app.ui.formLayout.addRow(
        app.x_secondary_axis_target_unit_label, app.x_secondary_axis_target_unit_combo)

    app.y_tick_format_label = QLabel(tr("目盛り表記"))
    app.y_tick_format_combo = QComboBox()
    app.y_tick_format_combo.addItems(tick_format_choices)
    app.ui.formLayout_2.addRow(app.y_tick_format_label, app.y_tick_format_combo)

    app.y_ticks_visible_checkbox = QCheckBox(tr("目盛を表示"))
    app.y_ticks_visible_checkbox.setChecked(True)
    app.ui.formLayout_2.addRow(app.y_ticks_visible_checkbox)
    app.y_tick_labels_visible_checkbox = QCheckBox(tr("目盛の数値を表示"))
    app.y_tick_labels_visible_checkbox.setChecked(True)
    app.ui.formLayout_2.addRow(app.y_tick_labels_visible_checkbox)

    app.y_tick_decimals_spinbox = QSpinBox()
    app.y_tick_decimals_spinbox.setRange(-1, 10)
    app.y_tick_decimals_spinbox.setSpecialValueText(tr("自動"))
    app.y_tick_decimals_spinbox.setValue(-1)
    app.y_tick_decimals_spinbox.setToolTip(
        tr("目盛りの数値を表示する小数点以下の桁数(「自動」以外を選ぶと指数表記モードより優先されます)"))
    app.ui.formLayout_2.addRow(QLabel(tr("小数桁数")), app.y_tick_decimals_spinbox)

    # X 軸と同じく、ラベルは短くして説明はツールチップへ
    app.y_log_minor_subs_label = QLabel(tr("対数補助目盛"))
    app.y_log_minor_subs_label.setToolTip(tr("対数軸の補助目盛りをどこに打つか"))
    app.y_log_minor_subs_combo = QComboBox()
    app.y_log_minor_subs_combo.addItem(tr("自動(既定)"), "auto")
    app.y_log_minor_subs_combo.addItem(tr("全て(2〜9)"), "all")
    app.y_log_minor_subs_combo.addItem(tr("少なめ(2, 5)"), "few")
    app.y_log_minor_subs_combo.addItem(tr("最小限(5)"), "one")
    app.ui.formLayout_2.addRow(app.y_log_minor_subs_label, app.y_log_minor_subs_combo)
    app.y_log_minor_labels_checkbox = QCheckBox(tr("補助目盛りに数値ラベルを表示"))
    app.ui.formLayout_2.addRow(app.y_log_minor_labels_checkbox)
    app.y_log_minor_subs_label.setVisible(False)
    app.y_log_minor_subs_combo.setVisible(False)
    app.y_log_minor_labels_checkbox.setVisible(False)


def build_label_editors(app):
    # タイトルと軸ラベルは、mathtext を描いたプレビューに差し替え、クリックで編集ダイアログを開く。
    # 元の QLineEdit は値の置き場と textChanged の発信元として、見えないまま残す
    app._label_preview_widgets = []  # [(preview_label, line_edit, placeholder), ...]
    for field_key, line_edit, dialog_title, placeholder in (
        ('title', app.ui.title_text_edit, tr("タイトルを編集"), tr("タイトルを入力")),
        ('x_label', app.ui.x_label_text_edit, tr("X軸ラベルを編集"), tr("X軸ラベルを入力")),
        ('y_label', app.ui.y_label_text_edit, tr("Y軸ラベルを編集"), tr("Y軸ラベルを入力")),
    ):
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(4)

        # 同じ位置に差し替える(行の位置がずれない)
        app.ui.formLayout_3.replaceWidget(line_edit, wrapper)
        # レイアウトには入れない(隠れていても余白の計算に関わることがある)。親を wrapper にするだけ
        line_edit.setParent(wrapper)
        line_edit.hide()

        preview_label = _ClickableMathPreviewLabel(wrapper)
        wrapper_layout.addWidget(preview_label, 1)
        preview_label.clicked.connect(
            lambda le=line_edit, dt=dialog_title: app._open_label_edit_dialog(le, dt)
        )
        app._label_preview_widgets.append((preview_label, line_edit, placeholder))
        line_edit.textChanged.connect(
            lambda text, lbl=preview_label, ph=placeholder:
                app._refresh_label_preview(lbl, text, ph)
        )
        app._refresh_label_preview(preview_label, line_edit.text(), placeholder)

        # 軸ラベルだけ、文字を残したまま隠せる(タイトルには付けない)
        if field_key in ('x_label', 'y_label'):
            visible_checkbox = QCheckBox()
            visible_checkbox.setChecked(True)
            visible_checkbox.setToolTip(tr("ラベルの表示/非表示(テキスト自体は保持されます)"))
            wrapper_layout.addWidget(visible_checkbox)
            setattr(app, f'{field_key}_visible_checkbox', visible_checkbox)

        format_button = QToolButton()
        format_button.setText("Aa")
        format_button.setToolTip(tr("タイトル/ラベルを編集(書式・記号入力)"))
        format_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # パネルの幅が狭いので、ボタンは小さくして欄の幅を取らない
        format_button.setFixedSize(26, 22)
        small_font = QFont(format_button.font())
        small_font.setPointSize(max(7, small_font.pointSize() - 2))
        format_button.setFont(small_font)
        wrapper_layout.addWidget(format_button)
        format_button.clicked.connect(
            lambda checked=False, le=line_edit, dt=dialog_title:
                app._open_label_edit_dialog(le, dt)
        )


def rebuild_label_tab(app):
    # 「ラベル/書式」タブの先頭に、グラフ全体のレイアウトと編集対象の軸の欄を入れる
    layout_group = QGroupBox(tr("グラフ全体レイアウト"))
    layout_form = QFormLayout()
    sizePolicy = layout_group.sizePolicy()
    sizePolicy.setVerticalPolicy(QSizePolicy.Policy.Fixed)
    layout_group.setSizePolicy(sizePolicy)
    app.subplot_rows_spinbox = QSpinBox()
    app.subplot_rows_spinbox.setRange(1, 10)
    app.subplot_rows_spinbox.setValue(1)
    app.subplot_cols_spinbox = QSpinBox()
    app.subplot_cols_spinbox.setRange(1, 10)
    app.subplot_cols_spinbox.setValue(1)
    layout_form.addRow(tr("行数"), app.subplot_rows_spinbox)
    layout_form.addRow(tr("列数"), app.subplot_cols_spinbox)

    # 軸の共有は自由配置では意味が無いので、_on_toggle_free_layout で有効/無効を合わせる
    app.share_x_checkbox = QCheckBox(tr("X軸を共有(グリッドレイアウト時)"))
    app.share_y_checkbox = QCheckBox(tr("Y軸を共有(グリッドレイアウト時)"))
    layout_form.addRow(app.share_x_checkbox)
    layout_form.addRow(app.share_y_checkbox)

    app.free_layout_checkbox = QCheckBox(tr("自由配置レイアウト(ドラッグで配置)"))
    layout_form.addRow(app.free_layout_checkbox)

    free_layout_button_row = QHBoxLayout()
    app.add_free_subplot_button = QPushButton(tr("+ プロット追加"))
    app.remove_free_subplot_button = QPushButton(tr("- プロット削除"))
    app.add_free_subplot_button.setEnabled(False)
    app.remove_free_subplot_button.setEnabled(False)
    free_layout_button_row.addWidget(app.add_free_subplot_button)
    free_layout_button_row.addWidget(app.remove_free_subplot_button)
    layout_form.addRow(free_layout_button_row)

    # 自由配置で選んだ軸の位置と大きさを数値でも入れられる。値は Figure に対する割合(ax.set_position と同じ)で、
    # ドラッグと同じく少しなら範囲外も許す
    app.free_layout_position_group = QGroupBox(tr("選択中のサブプロットの位置・サイズ"))
    free_layout_position_form = QFormLayout()
    app.free_layout_x_spinbox = QDoubleSpinBox()
    app.free_layout_y_spinbox = QDoubleSpinBox()
    app.free_layout_width_spinbox = QDoubleSpinBox()
    app.free_layout_height_spinbox = QDoubleSpinBox()
    for spinbox in (app.free_layout_x_spinbox, app.free_layout_y_spinbox):
        spinbox.setRange(-1.0, 2.0)
        spinbox.setDecimals(3)
        spinbox.setSingleStep(0.01)
    for spinbox in (app.free_layout_width_spinbox, app.free_layout_height_spinbox):
        spinbox.setRange(MIN_FREE_RECT_SIZE, 2.0)
        spinbox.setDecimals(3)
        spinbox.setSingleStep(0.01)
    free_layout_position_form.addRow(tr("X"), app.free_layout_x_spinbox)
    free_layout_position_form.addRow(tr("Y"), app.free_layout_y_spinbox)
    free_layout_position_form.addRow(tr("幅"), app.free_layout_width_spinbox)
    free_layout_position_form.addRow(tr("高さ"), app.free_layout_height_spinbox)
    app.free_layout_position_group.setLayout(free_layout_position_form)
    # 自由配置モードで、かつサブプロットが選択されている間だけ表示する
    app.free_layout_position_group.setVisible(False)
    layout_form.addRow(app.free_layout_position_group)

    layout_group.setLayout(layout_form)

    active_axis_group = QGroupBox(tr("編集対象のプロット"))
    active_axis_layout = QVBoxLayout()
    sizePolicy = active_axis_group.sizePolicy()
    sizePolicy.setVerticalPolicy(QSizePolicy.Policy.Fixed)
    active_axis_group.setSizePolicy(sizePolicy)
    app.active_axis_combo = QComboBox()
    active_axis_layout.addWidget(app.active_axis_combo)
    active_axis_group.setLayout(active_axis_layout)

    grid_layout = app.ui.tab_3.layout()  # QGridLayout

    # 既存の formLayout_3 を (0, 0) から外し、新しい2つの下(2行目)に入れ直す
    existing_layout_item = grid_layout.itemAtPosition(0, 0)

    if existing_layout_item:
        grid_layout.removeItem(existing_layout_item)

    grid_layout.addWidget(layout_group, 0, 0)
    grid_layout.addWidget(active_axis_group, 1, 0)

    if existing_layout_item:
        grid_layout.addItem(existing_layout_item, 2, 0)
