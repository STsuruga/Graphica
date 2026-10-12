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
    ("coordinate_label", ADVANCED),
    ("dataset_stats_advanced_row", ADVANCED),
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


def _resolve(app, dotted_name):
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
        widget = _resolve(app, dotted_name)
        if widget is not None:
            widget.setVisible(mode == only_in)
    app.ui_mode = mode
