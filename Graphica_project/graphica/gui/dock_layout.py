"""ドックの配置: 組み立て、起動時の復元、名前を付けた配置の保存・読み込み・リセット。"""
import base64
import json
import logging
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QDockWidget, QFormLayout, QVBoxLayout, QWidget
from graphica.core.i18n import tr
from graphica.gui import app_settings, notify
from graphica.gui.builders.common import DOCK_LAYOUT_VERSION
from graphica.gui.export_preview_panel import ExportPreviewPanel
from graphica.gui.provenance_panel import ProvenancePanel
from graphica.gui.shell.inspector import (INSPECTOR_PAGES, Inspector, TargetHeader, scroll_page,
                                          section_state_texts, wrap_long_rows)
from graphica.gui.residual_panel import ResidualPanel

logger = logging.getLogger(__name__)


def arrange_property_docks(app):
    """右のインスペクタ(GUI 刷新): プロパティ・軸・凡例・エクスポートのタブを、プロパティのドックの中に並べる。

    ドックは動かさない(決定 5)。見出しの帯はタブが兼ねるので出さない。properties_dock_widget は
    control_dock_widget の別名(表示メニューなどがこの名前で使う)。
    """
    dock = app.ui.control_dock_widget
    app.properties_dock_widget = dock
    dock.setWindowTitle(tr("プロパティ"))
    dock.setTitleBarWidget(QWidget())
    dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)

    plot_properties = dock.widget()
    if plot_properties is None:
        logger.warning("control_dock_widget の中身が見つかりません。")
        plot_properties = QWidget()
    legend_page = _take_legend_rows(app)
    app.ui.properties_groupbox.setTitle("")
    # theme.py はグループボックスのタイトル用に上の余白を取る。タイトルが無いので、それを 0 にする目印
    app.ui.properties_groupbox.setProperty("collapsibleBody", True)

    app.inspector = Inspector()
    app.inspector_target = TargetHeader()
    properties_page = QWidget()
    properties_page.setObjectName("inspector_page")
    properties_layout = QVBoxLayout(properties_page)
    properties_layout.setContentsMargins(0, 0, 0, 0)
    properties_layout.setSpacing(0)
    properties_layout.addWidget(app.inspector_target)
    properties_layout.addWidget(app.ui.properties_groupbox)
    properties_layout.addStretch(1)

    plot_properties.setObjectName("inspector_axes_content")
    wrap_long_rows(plot_properties)
    # 見本どおり左右 16px の余白(欄が欄の端に付かないように)
    app.ui.gridLayout_4.setContentsMargins(16, 0, 16, 8)
    if plot_properties.layout() is not None:
        plot_properties.layout().setContentsMargins(16, 8, 16, 8)

    # エクスポートのプレビュー。見えている間だけ描く(ExportPreviewPanel.refresh_preview)ので、裏のタブにあれば重くならない
    app.export_preview_panel = ExportPreviewPanel(app)

    for key, title in INSPECTOR_PAGES:
        widget = {"properties": properties_page, "axes": plot_properties, "legend": legend_page,
                  "export": app.export_preview_panel}[key]
        app.inspector.add_page(key, title, scroll_page(widget, f"inspector_scroll_{key}"))
    app.inspector.tab_bar.currentChanged.connect(lambda _index: _on_inspector_page_changed(app))
    dock.setWidget(app.inspector)

    # 選んでいるデータセットの見出しと節の状態は、描き直すたびに合わせる(選択・名前・種類の変更をまとめて拾える)
    app.canvas.mpl_connect('draw_event', lambda _event: refresh_inspector(app))

    # 選んだデータセットのフィットの残差。既定では隠し、開くときはキャンバスの下に付ける
    app.residual_panel = ResidualPanel(app)
    app.residual_dock_widget = QDockWidget(tr("残差プロット"), app)
    app.residual_dock_widget.setObjectName("ResidualDockWidget")
    app.residual_dock_widget.setWidget(app.residual_panel)
    app.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, app.residual_dock_widget)
    app.residual_dock_widget.hide()

    # 選んだデータセットの処理の履歴。既定では隠す
    app.provenance_panel = ProvenancePanel(app)
    app.provenance_dock_widget = QDockWidget(tr("処理履歴"), app)
    app.provenance_dock_widget.setObjectName("ProvenanceDockWidget")
    app.provenance_dock_widget.setWidget(app.provenance_panel)
    app.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, app.provenance_dock_widget)
    app.provenance_dock_widget.hide()


# 凡例のタブに移す行(軸の設定の formLayout_3 から)。表示のチェックは格子の表示と同じ行の中なので、それも取り出す
_LEGEND_FIELDS = ("legend_loc_combo", "legend_font_button", "legend_color_button", "legend_order_button")


def _take_legend_rows(app):
    page = QWidget()
    page.setObjectName("inspector_legend_content")
    form = QFormLayout(page)
    form.setContentsMargins(16, 10, 16, 10)
    form.setSpacing(6)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    visible_checkbox = app.ui.legend_visible_checkbox
    visible_checkbox.parentWidget().layout().removeWidget(visible_checkbox)
    form.addRow(visible_checkbox)
    source = app.ui.formLayout_3
    for attr in _LEGEND_FIELDS:
        row, _role = source.getWidgetPosition(getattr(app, attr))
        taken = source.takeRow(row)
        label = taken.labelItem.widget() if taken.labelItem is not None else None
        field = taken.fieldItem.widget() if taken.fieldItem is not None else None
        if label is not None and field is not None:
            form.addRow(label, field)
        else:
            form.addRow(field or label)
    return page


def _on_inspector_page_changed(app):
    if app.inspector.current_page() == "export":
        app.export_preview_panel.refresh_preview()


def refresh_inspector(app):
    """右の見出しと、節の見出しの右の状態の文字を、表示しているデータセットに合わせる。"""
    dataset = app.property_panel.shown_dataset()
    app.inspector_target.set_dataset(dataset)
    states = section_state_texts(dataset)
    for key, entry in getattr(app, '_prop_sections', {}).items():
        toggle = entry['toggle']
        if hasattr(toggle, 'set_state_text'):
            toggle.set_state_text(states.get(key, ""))


def restore_dock_layout(app):
    """前回のドック配置を戻す。タブが最終の大きさになってから呼ぶ(でないとスプリッターの位置がずれる)。"""
    saved_layout_version = (app_settings.DOCK_LAYOUT_VERSION.read(app.settings) if app._run_startup_checks
                            else DOCK_LAYOUT_VERSION)
    saved_state = app_settings.WINDOW_STATE.read(app.settings) if app._run_startup_checks else None
    if saved_state is not None and saved_layout_version == DOCK_LAYOUT_VERSION and app.restoreState(saved_state):
        return
    # 戻せなければ(初回・追加したタブ)組み立てたときの配置のまま。タブで並べたドックは後から足した方が前に出るので
    # プロパティを前にする(表示される前の raise_() は効かないので、表示された後のここで行う)
    app.ui.control_dock_widget.raise_()


def load_dock_layout_presets(app):
    """{名前: base64 の saveState}"""
    raw = app_settings.DOCK_LAYOUT_PRESETS.read(app.settings)
    if not isinstance(raw, str):
        raw = "{}"
    try:
        presets = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("ドックレイアウトプリセットの読み込みに失敗しました。空として扱います。")
        return {}
    return presets if isinstance(presets, dict) else {}


def save_dock_layout_presets(app, presets: dict):
    app_settings.DOCK_LAYOUT_PRESETS.write(app.settings, json.dumps(presets))


def on_save_dock_layout_preset(app):
    name, ok = notify.get_text(app, "レイアウトを保存", "プリセット名:")
    name = name.strip()
    if not ok or not name:
        return
    presets = app._load_dock_layout_presets()
    presets[name] = base64.b64encode(bytes(app.saveState())).decode('ascii')
    app._save_dock_layout_presets(presets)
    app.statusBar().showMessage(f"レイアウト「{name}」を保存しました", 3000)


def populate_load_layout_menu(app):
    """保存や削除のたびに更新しなくて済むよう、開く直前に作り直す。"""
    app.load_layout_menu.clear()
    presets = app._load_dock_layout_presets()
    if not presets:
        empty_action = app.load_layout_menu.addAction("(保存済みレイアウトはありません)")
        empty_action.setEnabled(False)
        return
    for name in sorted(presets.keys()):
        action = app.load_layout_menu.addAction(name)
        action.triggered.connect(lambda checked=False, n=name: app._on_load_dock_layout_preset(n))


def on_load_dock_layout_preset(app, name):
    presets = app._load_dock_layout_presets()
    state_b64 = presets.get(name)
    if state_b64 is None:
        return
    try:
        state_bytes = base64.b64decode(state_b64)
    except (ValueError, TypeError):
        notify.warning(app, "レイアウトの復元", "保存されたレイアウトデータが壊れています。")
        return
    if not app.restoreState(QByteArray(state_bytes)):
        notify.warning(app, "レイアウトの復元", "レイアウトの復元に失敗しました。")


def on_reset_dock_layout(app):
    """組み立てた直後、配置を戻す前に控えた状態(_pristine_dock_state)に戻す。"""
    app.restoreState(app._pristine_dock_state)
