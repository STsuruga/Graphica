"""シンプル(Lite)とアドバンスド(Advanced)の表示の出し分け。

部品は1組だけで、モードで見せる・隠すだけ。値には触らない(隠した設定もそのまま描かれ、保存される)。
どの部品をどちらのモードで出すかは MODE_ONLY_ELEMENTS の表で決める。見本は docs/dev/mockups/gui_redesign/。
"""
from graphica.core.i18n import tr
from graphica.gui import app_settings

LITE = "lite"
ADVANCED = "advanced"
MODES = (LITE, ADVANCED)

# 表示名(日本語は「シンプル / アドバンスド」。「ライト」はテーマのライトと紛らわしいので使わない)
MODE_LABELS = {LITE: "シンプル", ADVANCED: "アドバンスド"}

# (タブの属性の名前(ドットで辿る), 出すモード)。ここに無い部品は両方のモードで出す
MODE_ONLY_ELEMENTS = (
    # ステータスバー: 座標と、データセット・選択の数
    ("coordinate_label", ADVANCED),
    ("status_selection_label", ADVANCED),
    ("dataset_stats_advanced_row", ADVANCED),
    # グラフの道具: シンプルは左に縦のアイコン、アドバンスドはプロットの上に文字付き(同じ QAction)
    ("plot_tool_rail", LITE),
    ("plot_toolbar", ADVANCED),
    ("card_subplot_label", ADVANCED),
    ("card_minimap_button", ADVANCED),
    # プロパティ: シンプルは種類のタイルと「アドバンスドですべて表示」の案内、色の 16 進はアドバンスドだけ
    ("_plot_type_tiles_row", LITE),
    ("lite_more_box", LITE),
    ("color_picker_widget.hex_edit", ADVANCED),
    # グラフの下のパネル(データ表・フィット結果・残差・来歴・ログ)
    ("bottom_panel", ADVANCED),
)

# シンプルで隠すプロパティの行(欄の属性の名前。名前の欄も一緒に隠す)。種類などによる今の出し入れより強い
LITE_HIDDEN_PROPERTY_FIELDS = (
    "use_secondary_y_checkbox", "x_err_col_combo", "y_err_col_combo", "nan_policy_combo",
    "ui.plot_type_combo", "alpha_slider", "ui.smoothing_checkbox", "smoothing_method_combo",
    "marker_fill_combo", "marker_face_color_picker", "marker_edge_combo", "marker_edge_color_picker",
    "marker_edge_width_spinbox", "legend_label_edit", "hide_from_legend_checkbox",
)
# シンプルで出すプロパティの節(ほかの節は見出しごと隠す)。マーカーは形と大きさだけ(点の種類のときに出る)
LITE_PROPERTY_SECTIONS = ("data", "style", "marker")


# インスペクタのタブ(キー, 出すモード)
MODE_ONLY_INSPECTOR_PAGES = (
    ("legend", ADVANCED),
)


def mode_label(mode):
    return tr(MODE_LABELS[mode])


def initial_mode(settings):
    """保存したモード。無ければ、今までの利用者(スタートアップ画面を見たことがある)はアドバンスド、初めての人はシンプル。

    更新した人の手元で項目が消えて見えないよう、決めた値はすぐ保存する。
    """
    saved = app_settings.UI_MODE.read(settings)
    if saved in MODES:
        return saved
    mode = ADVANCED if app_settings.HAS_SHOWN_WELCOME.read(settings) else LITE
    app_settings.UI_MODE.write(settings, mode)
    return mode


def resolve(app, dotted_name):
    target = app
    for part in dotted_name.split("."):
        target = getattr(target, part, None)
        if target is None:
            return None
    return target


def apply_ui_mode(app, mode):
    """タブの部品をモードに合わせて見せる・隠す。値は変えない。"""
    if mode not in MODES:
        raise ValueError(f"知らないモード: {mode!r}")
    for dotted_name, only_in in MODE_ONLY_ELEMENTS:
        widget = resolve(app, dotted_name)
        if widget is not None:
            widget.setVisible(mode == only_in)
    inspector = getattr(app, 'inspector', None)
    if inspector is not None:
        for key, only_in in MODE_ONLY_INSPECTOR_PAGES:
            inspector.set_page_visible(key, mode == only_in)
    app.ui_mode = mode
    # プロパティの行は種類などの条件でも出し入れするので、条件を当て直してからモードで隠す
    property_panel = getattr(app, 'property_panel', None)
    if property_panel is not None:
        property_panel.update_mode_visibility()
