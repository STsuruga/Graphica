"""アプリの設定(QSettings)のキー・型・既定値の表と、設定を開く唯一の場所。

読み方は今の挙動をそのまま写している。型を指定しないキー(value_type が None)は INI 形式では真偽や数が文字列で返り、
要素が 1 つのリストは文字列で返ることがある。どちらも読む側の扱いまで含めて挙動なので、型の有無を変えないこと。
"""
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QSettings

from graphica.core.i18n import DEFAULT_LANGUAGE

ORGANIZATION_NAME = "Graphica"
APPLICATION_NAME = "Graphica"

DEFAULT_AUTOSAVE_INTERVAL_MIN = 5  # 0 で無効
# これより点が多いデータセットには点ラベルを描かない(annotate が点の数だけ呼ばれて固まる)。環境設定で変えられる
DEFAULT_POINT_LABEL_MAX_POINTS = 1000
DEFAULT_SNAP_TO_GRID_ENABLED = False
DEFAULT_SNAP_GRID_INTERVAL_PX = 10

CANVAS_DETACHED_GEOMETRY_KEY = "canvas_detached_geometry"
CANVAS_WAS_DETACHED_KEY = "canvas_was_detached"
# 名前を付けて保存するドック配置(起動時に戻す直近の window_state とは別)
DOCK_LAYOUT_PRESETS_SETTINGS_KEY = "dock_layout_presets"
# 閉じている節のキーの JSON 配列。無い・空なら全部開く(節を足しても既定は開いたまま)
DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY = "dataset_property_collapsed_sections"
DISABLED_PLUGINS_SETTINGS_KEY = "disabled_plugins"
QUICK_ACCESS_SETTINGS_KEY = "quick_access_pinned_actions"
COLOR_PALETTES_SETTINGS_KEY = "custom_color_palettes_json"
ACTIVE_PALETTE_SETTINGS_KEY = "active_color_palette"
RECENT_COLORS_SETTINGS_KEY = "recent_colors"

_TABLE_DEFAULT = object()


def open_settings() -> QSettings:
    """アプリの設定を開く。QSettings を作るのはここだけ(テストはこのモジュールの QSettings を差し替えて隔離する)。"""
    return QSettings(ORGANIZATION_NAME, APPLICATION_NAME)


@dataclass(frozen=True)
class Setting:
    key: str
    default: Any = None
    value_type: type | None = None       # None なら型を指定せずに読む
    export_as: type | None = None        # 設定の書き出しに入れるときの型(list は要素 1 つを直して読む)
    export_default: Any = _TABLE_DEFAULT  # 書き出しのときだけ既定値が違うもの

    def read(self, settings: QSettings, default: Any = _TABLE_DEFAULT) -> Any:
        """default を渡すのは、読む場所によって既定値が違うところ(今の挙動)だけ。"""
        fallback = self.default if default is _TABLE_DEFAULT else default
        if self.value_type is None:
            return settings.value(self.key, fallback)
        return settings.value(self.key, fallback, type=self.value_type)

    def write(self, settings: QSettings, value: Any) -> None:
        settings.setValue(self.key, value)

    def read_for_export(self, settings: QSettings) -> Any:
        default = self.default if self.export_default is _TABLE_DEFAULT else self.export_default
        if self.export_as is list:
            value = settings.value(self.key, default)
            if isinstance(value, str):
                value = [value] if value else []
            return value
        return settings.value(self.key, default, type=self.export_as)


def as_list_keeping_empty_string(value: Any) -> list[Any]:
    """要素 1 つのリストが文字列で返ったのを直す(最近使ったファイル・クイックアクセスの読み方)。"""
    if isinstance(value, str):
        value = [value]
    return list(value) if value else []


LANGUAGE = Setting("language", DEFAULT_LANGUAGE, export_as=str, export_default="")
DARK_MODE = Setting("dark_mode", False, bool, export_as=bool)
AUTOSAVE_INTERVAL_MIN = Setting("autosave_interval_min", DEFAULT_AUTOSAVE_INTERVAL_MIN, int, export_as=int)
AUTOSAVE_DIR = Setting("autosave_dir", "", str)
POINT_LABEL_MAX_POINTS = Setting("point_label_max_points", DEFAULT_POINT_LABEL_MAX_POINTS, int, export_as=int)
SNAP_TO_GRID_ENABLED = Setting("snap_to_grid_enabled", DEFAULT_SNAP_TO_GRID_ENABLED, bool, export_as=bool)
SNAP_GRID_INTERVAL_PX = Setting("snap_grid_interval_px", DEFAULT_SNAP_GRID_INTERVAL_PX, int, export_as=int)
CUSTOM_COLOR_PALETTES = Setting(COLOR_PALETTES_SETTINGS_KEY, "", export_as=str)
# 画面の既定は配色パレットのダイアログの既定の名前(読む側が渡す)。書き出しでは空
ACTIVE_COLOR_PALETTE = Setting(ACTIVE_PALETTE_SETTINGS_KEY, None, export_as=str, export_default="")
QUICK_ACCESS_PINNED_ACTIONS = Setting(QUICK_ACCESS_SETTINGS_KEY, [], export_as=list)
DISABLED_PLUGINS = Setting(DISABLED_PLUGINS_SETTINGS_KEY, [], export_as=list)

CLEAN_EXIT = Setting("clean_exit", True, bool)
HAS_SHOWN_WELCOME = Setting("has_shown_welcome", False, bool)
MINIMAP_VISIBLE = Setting("minimap_visible", True, bool)
RECENT_FILES = Setting("recent_files", [])
RECENT_COLORS = Setting(RECENT_COLORS_SETTINGS_KEY, [])
WINDOW_GEOMETRY = Setting("window_geometry")
WINDOW_STATE = Setting("window_state")
DOCK_LAYOUT_VERSION = Setting("dock_layout_version", 0, int)
DOCK_LAYOUT_PRESETS = Setting(DOCK_LAYOUT_PRESETS_SETTINGS_KEY, "{}")
DATASET_PROPERTY_COLLAPSED_SECTIONS = Setting(DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY, "[]")
CANVAS_WAS_DETACHED = Setting(CANVAS_WAS_DETACHED_KEY, False, bool)
CANVAS_DETACHED_GEOMETRY = Setting(CANVAS_DETACHED_GEOMETRY_KEY)

# 設定の書き出し(別の PC や研究室での共有用)に入れるもの。JSON の並びはこの順
EXPORTED_SETTINGS: tuple[Setting, ...] = (
    LANGUAGE, DARK_MODE, AUTOSAVE_INTERVAL_MIN, POINT_LABEL_MAX_POINTS, SNAP_TO_GRID_ENABLED, SNAP_GRID_INTERVAL_PX,
    CUSTOM_COLOR_PALETTES, ACTIVE_COLOR_PALETTE, QUICK_ACCESS_PINNED_ACTIONS, DISABLED_PLUGINS,
)


def disabled_plugin_names(settings: QSettings) -> set[str]:
    """QSettings は要素が1つのリストを文字列で返すことがあるので直す。"""
    names = DISABLED_PLUGINS.read(settings)
    if isinstance(names, str):
        names = [names]
    return set(names) if names else set()
