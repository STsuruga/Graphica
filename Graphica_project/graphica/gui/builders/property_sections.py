"""データセットのプロパティ欄の 7 つの節(折りたたみ・開閉の保存・見出しの出し入れ・ラベル列の幅)。"""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget
from graphica.core.i18n import tr
from graphica.gui import app_settings
from graphica.gui.builders.common import DATASET_PROPERTY_SECTIONS, PLOT_TYPE_COMBO_MIN_CHARS, _svg_icon


def wrap_in_collapsible_section(app, group_box, title):
    """group_box の外に開閉ボタンを付け、グループボックスごと出し入れする。見出しはボタンにだけ出す。"""
    group_box.setTitle("")
    # theme.py はグループボックスのタイトル用に上の余白を取る。タイトルを空にしたので、それを 0 にする目印
    group_box.setProperty("collapsibleBody", True)

    wrapper = QWidget()
    wrapper_layout = QVBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(0, 0, 0, 0)
    wrapper_layout.setSpacing(2)

    toggle_button = QToolButton()
    toggle_button.setText(title)
    toggle_button.setCheckable(True)
    toggle_button.setChecked(True)
    toggle_button.setIcon(_svg_icon("chevron-down", size=14))
    toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    toggle_button.setObjectName("collapsible_section_toggle")
    toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
    toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _on_toggled(checked, box=group_box, btn=toggle_button):
        box.setVisible(checked)
        btn.setIcon(_svg_icon("chevron-down" if checked else "chevron-right", size=14))

    toggle_button.toggled.connect(_on_toggled)
    # ダークモードの切り替えでアイコンを作り直すので、ボタンを集めておく
    if not hasattr(app, '_collapsible_toggle_buttons'):
        app._collapsible_toggle_buttons = []
    app._collapsible_toggle_buttons.append(toggle_button)

    wrapper_layout.addWidget(toggle_button)
    wrapper_layout.addWidget(group_box)
    return wrapper


def build_dataset_property_sections(app):
    """データセットのプロパティ欄を DATASET_PROPERTY_SECTIONS の節に分け、節ごとに QFormLayout を持たせる。

    列幅の広がりが節の中に閉じる。Designer の行は takeRow() で移す(removeRow() はウィジェットごと破棄する)。
    平滑化のチェックだけは「平滑化の手法」の直前に置くので、ここでは移さない。
    """
    app._prop_sections = {}

    container = QWidget()
    container_layout = QVBoxLayout(container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(0)

    collapsed = app._load_collapsed_property_sections()

    for key, title in DATASET_PROPERTY_SECTIONS:
        body = QWidget()
        form = QFormLayout(body)
        # 親の見出し(4px)→ 子の見出し(12px)→ 中身、の階段になるよう字下げする
        form.setContentsMargins(24, 2, 0, 6)
        form.setSpacing(6)

        toggle_button = QToolButton()
        toggle_button.setText(tr(title))
        toggle_button.setCheckable(True)
        toggle_button.setIcon(_svg_icon("chevron-down", size=13))
        toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # 上の2つの開閉ボタンとは別の名前(theme.py で控えめに描き、2つだけであることをテストが確かめる)
        toggle_button.setObjectName("property_subsection_toggle")
        toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # QToolButton は文字幅なので、区切りの罫線が見出しの下にしか引かれない
        toggle_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toggle_button.setChecked(key not in collapsed)
        # 1本目は親の見出しのすぐ下なので、罫線が二重に見える
        if key == DATASET_PROPERTY_SECTIONS[0][0]:
            toggle_button.setProperty("firstSection", True)

        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)
        section_layout.addWidget(toggle_button)
        section_layout.addWidget(body)
        body.setVisible(toggle_button.isChecked())

        toggle_button.toggled.connect(
            lambda checked, k=key: app._on_property_section_toggled(k, checked))

        container_layout.addWidget(section)
        app._prop_sections[key] = {
            'form': form, 'body': body, 'toggle': toggle_button, 'section': section,
        }

    # 空の formLayout_4 は生成物の構造なので残し、余白だけ潰す
    for row in range(app.ui.formLayout_4.rowCount() - 1, -1, -1):
        app.ui.formLayout_4.takeRow(row)
    app.ui.formLayout_4.setContentsMargins(0, 0, 0, 0)
    app.ui.formLayout_4.setSpacing(0)
    app.ui.gridLayout_4.setContentsMargins(0, 0, 0, 0)
    app.ui.gridLayout_4.addWidget(container, 1, 0, 1, 1)
    app._dataset_property_sections_container = container

    # 無効な親の下の子は有効にできないので、グループボックスは常に有効にして中身だけ無効にする
    # (でないと、データセットが無い間は節を開閉できない)
    app.ui.properties_groupbox.setEnabled(True)
    app._set_dataset_property_fields_enabled(False)

    style_form = app._prop_form('style')
    style_form.addRow(app.ui.legend_name_label, app.ui.legend_name_edit)
    style_form.addRow(app.ui.plot_type_label, app.ui.plot_type_combo)
    style_form.addRow(app.ui.color_label, app.color_picker_widget)
    style_form.addRow(app.ui.linestyle_label, app.ui.linestyle_combo)
    style_form.addRow(app.ui.linewidth_label, app.ui.linewidth_spinbox)
    style_form.addRow(app.ui.marker_label, app.ui.marker_combo)
    style_form.addRow(app.ui.makersize_label, app.ui.markersize_spinbox)

    app.ui.plot_type_combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    app.ui.plot_type_combo.setMinimumContentsLength(PLOT_TYPE_COMBO_MIN_CHARS)


def prop_form(app, section_key):
    return app._prop_sections[section_key]['form']


def align_form_label_columns(app, forms):
    """ラベルの列幅を複数の QFormLayout で揃え、入力欄の左端を合わせる。決めた幅(px)を返す。

    隠れているラベルも数える(QFormLayout は隠れたものを外すので、出た瞬間に列幅が変わって欄がずれる)。
    """
    labels = []
    widest = 0
    for form in forms:
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item is None or not isinstance(item.widget(), QLabel):
                continue
            label = item.widget()
            labels.append(label)
            widest = max(widest, label.sizeHint().width())

    for label in labels:
        label.setMinimumWidth(widest)
    return widest


def set_dataset_property_fields_enabled(app, enabled):
    """選択が無いときは無効にする。無効にするのは節の中身だけ(見出しまで無効にすると開閉できない)。"""
    for entry in getattr(app, '_prop_sections', {}).values():
        entry['body'].setEnabled(enabled)


def load_collapsed_property_sections(app):
    raw = app_settings.DATASET_PROPERTY_COLLAPSED_SECTIONS.read(app.settings)
    try:
        keys = json.loads(raw) if isinstance(raw, str) else list(raw)
    except (ValueError, TypeError):
        return set()
    valid = {key for key, _ in DATASET_PROPERTY_SECTIONS}
    return {k for k in keys if k in valid}


def on_property_section_toggled(app, section_key, checked):
    """開閉し、閉じている節を QSettings に書き戻す(一度閉じたものは次の起動でも閉じたまま)。"""
    entry = app._prop_sections.get(section_key)
    if entry is None:
        return
    entry['body'].setVisible(checked)
    entry['toggle'].setIcon(
        _svg_icon("chevron-down" if checked else "chevron-right", size=13))

    collapsed = sorted(
        key for key, _ in DATASET_PROPERTY_SECTIONS
        if not app._prop_sections[key]['toggle'].isChecked()
    )
    app_settings.DATASET_PROPERTY_COLLAPSED_SECTIONS.write(app.settings, json.dumps(collapsed))


def update_property_section_visibility(app):
    """中の行が全部隠れた節は見出しごと隠す。"""
    sections = getattr(app, '_prop_sections', None)
    if not sections:
        return
    for key, _ in DATASET_PROPERTY_SECTIONS:
        entry = sections.get(key)
        if entry is None:
            continue
        form = entry['form']
        has_visible = False
        for row in range(form.rowCount()):
            for role in (QFormLayout.ItemRole.LabelRole,
                         QFormLayout.ItemRole.FieldRole,
                         QFormLayout.ItemRole.SpanningRole):
                item = form.itemAt(row, role)
                if item is not None and item.widget() is not None \
                        and not item.widget().isHidden():
                    has_visible = True
                    break
            if has_visible:
                break
        entry['section'].setVisible(has_visible)
