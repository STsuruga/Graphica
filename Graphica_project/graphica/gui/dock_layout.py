"""ドックの配置: 組み立て、起動時の復元、名前を付けた配置の保存・読み込み・リセット。"""
import base64
import json
import logging
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QDockWidget, QGroupBox, QScrollArea, QVBoxLayout, QWidget
from graphica.core.i18n import tr
from graphica.gui import app_settings, notify
from graphica.gui.builders.common import DOCK_LAYOUT_VERSION, EXPORT_PREVIEW_DOCK_INITIAL_HEIGHT
from graphica.gui.export_preview_panel import ExportPreviewPanel
from graphica.gui.provenance_panel import ProvenancePanel
from graphica.gui.residual_panel import ResidualPanel

logger = logging.getLogger(__name__)


def arrange_property_docks(app):
    # 「プロットのプロパティ」と「データセットのプロパティ」を1つのドックに縦に並べ、1枚のパネルに見せる。
    # properties_dock_widget は control_dock_widget の別名(表示メニューなどがこの名前で使う)
    app.properties_dock_widget = app.ui.control_dock_widget
    app.ui.control_dock_widget.setWindowTitle(tr("プロパティ"))

    original_control_widget = app.ui.control_dock_widget.widget()
    plot_properties_group = QGroupBox(tr("プロットのプロパティ"))
    plot_properties_layout = QVBoxLayout(plot_properties_group)
    plot_properties_layout.setContentsMargins(0, 4, 0, 0)
    if original_control_widget:
        plot_properties_layout.addWidget(original_control_widget)
    else:
        logger.warning("control_dock_widget の中身が見つかりません。")

    app.ui.properties_groupbox.setTitle(tr("データセットのプロパティ"))

    # どちらも長いので開閉できるようにする。中身を1つずつ隠すと入れ子のレイアウトを取りこぼすので、
    # グループボックスごと出し入れする開閉ボタンを外に付ける(見出しはボタン側だけに出す)
    dataset_section = app._wrap_in_collapsible_section(
        app.ui.properties_groupbox, tr("データセットのプロパティ"))
    plot_section = app._wrap_in_collapsible_section(
        plot_properties_group, tr("プロットのプロパティ"))

    # 既定の余白だと縦スクロールバーの分だけ中身がはみ出し、横スクロールバーが出るので左右を詰める
    merged_properties_container = QWidget()
    merged_properties_layout = QVBoxLayout(merged_properties_container)
    merged_properties_layout.setContentsMargins(2, 4, 2, 4)
    merged_properties_layout.addWidget(dataset_section)
    merged_properties_layout.addWidget(plot_section)
    merged_properties_layout.addStretch()

    merged_scroll_area = QScrollArea()
    merged_scroll_area.setWidgetResizable(True)
    merged_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    merged_scroll_area.setWidget(merged_properties_container)
    app.ui.control_dock_widget.setWidget(merged_scroll_area)

    # エクスポートのプレビュー。描き続けると重いので既定では隠し、表示メニューから開く
    app.export_preview_panel = ExportPreviewPanel(app)
    app.export_preview_dock_widget = QDockWidget(tr("エクスポートプレビュー"), app)
    app.export_preview_dock_widget.setObjectName("ExportPreviewDockWidget")
    app.export_preview_dock_widget.setWidget(app.export_preview_panel)
    # 必要なときだけ見るものなので、キャンバスを狭めないよう独立した窓で開く(ドッキングもできる)
    app.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, app.export_preview_dock_widget)
    app.export_preview_dock_widget.setFloating(True)
    app.export_preview_dock_widget.hide()
    app._export_preview_first_show = True

    def _on_export_preview_visibility_changed(visible):
        if not visible:
            return
        # 浮いたドックは表示されるまで大きさを持たないことがあるので、最初に表示したときに整える
        if app._export_preview_first_show and app.export_preview_dock_widget.isFloating():
            app._export_preview_first_show = False
            preview_width, preview_height = 820, 680
            app.export_preview_dock_widget.resize(preview_width, preview_height)
            center = app.geometry().center()
            app.export_preview_dock_widget.move(
                center.x() - preview_width // 2, center.y() - preview_height // 2
            )
        app.export_preview_panel.refresh_preview()

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

    app.export_preview_dock_widget.visibilityChanged.connect(_on_export_preview_visibility_changed)


def restore_dock_layout(app):
    """前回のドック配置を戻す。タブが最終の大きさになってから呼ぶ(でないとスプリッターの位置がずれる)。"""
    saved_layout_version = (app_settings.DOCK_LAYOUT_VERSION.read(app.settings) if app._run_startup_checks
                            else DOCK_LAYOUT_VERSION)
    saved_state = app_settings.WINDOW_STATE.read(app.settings) if app._run_startup_checks else None
    state_restored = False
    if saved_state is not None and saved_layout_version == DOCK_LAYOUT_VERSION:
        state_restored = bool(app.restoreState(saved_state))

    if not state_restored:
        try:
            app.resizeDocks(
                [app.export_preview_dock_widget],
                [EXPORT_PREVIEW_DOCK_INITIAL_HEIGHT],
                Qt.Orientation.Vertical
            )
        except Exception:
            logger.exception("resizeDocks に失敗しました")


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
