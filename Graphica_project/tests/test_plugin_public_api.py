"""
プラグインの公開 API を固定するテスト。落ちたら、変更に合わせて版を上げる。

- 消した・名前や引数を変えた(壊す変更): PLUGIN_API_VERSION の主番号を上げ、
  docs/plugin_development.md に移行表を書き、下の SNAPSHOT を更新する。
- 足した(互換のある追加): 小番号を上げ、SNAPSHOT に足す。
- Dataset のフィールドとプロパティは、足すのは自由(消す・名前を変えるのが壊す変更)。
"""
import dataclasses
import inspect

import graphica.plugin as public
import graphica.plugin.testing as public_testing
from graphica.core.dataset import Dataset
from graphica.core.plugin_api import GraphicaPluginAPI
from graphica.core.plugin_context import PluginContext
from graphica.core.plugin_manifest import PLUGIN_API_VERSION
from graphica.core.plugin_types import AnalysisResult, PluginMenuAction

SNAPSHOT = {
    "version": "2.0",
    "graphica.plugin": ["AnalysisResult", "Dataset", "GraphicaPluginAPI", "PLUGIN_API_VERSION",
                        "PluginContext", "PluginExecutionError"],
    "graphica.plugin.testing": ["FakeGraphicaPluginAPI", "FakePluginContext", "PluginInstallError",
                                "install_zip_like_graphica", "load_plugin_like_graphica"],
    "register": {
        "register_analyzer": ["name", "fn", "output_kind", "param_schema"],
        "register_exporter": ["format_name", "extension", "writer", "name"],
        "register_fit_function": ["name", "func", "param_names", "p0"],
        "register_importer": ["extensions", "loader", "name", "priority"],
        "register_menu_action": ["text", "callback", "shortcut"],
        "register_panel": ["name", "widget_factory", "area"],
        "register_plot_type": ["type_name", "drawer", "requires_2d"],
        "register_processor": ["name", "fn", "category", "param_schema"],
        "register_render_backend": ["name", "backend"],
    },
    "context": {
        "active_color_cycle": [],
        "add_dataset": ["dataset", "description"],
        "color_palettes": [],
        "current_dataset": [],
        "data_dir": "property",
        "datasets": [],
        "named_colors": [],
        "on_datasets_changed": ["callback"],
        "on_selection_changed": ["callback"],
        "parent_widget": "property",
        "redraw": [],
        "selected_datasets": [],
        "set_color_palettes": ["palettes"],
        "set_dataset_properties": ["dataset", "values", "description"],
        "set_named_colors": ["entries"],
        "show_error": ["text", "title"],
        "show_message": ["text", "title"],
    },
    "AnalysisResult": ["table", "annotations", "new_datasets"],
    "PluginMenuAction": ["text", "callback", "shortcut", "plugin_name"],
    "Dataset.required": ["name", "df", "x_col_name", "y_col_name"],
    "Dataset.fields": [
        "name", "df", "x_col_name", "y_col_name", "plot_type", "color", "linestyle", "linewidth",
        "marker", "markersize", "smoothing", "smoothing_method", "alpha", "gradient_enabled",
        "gradient_color2", "gradient_target", "waterfall_enabled", "waterfall_offset_x",
        "waterfall_offset_y", "waterfall_occlusion_enabled", "waterfall_depth_shrink_enabled",
        "waterfall_depth_shrink_ratio", "show_point_labels", "point_label_col_name",
        "x_err_col_name", "y_err_col_name", "error_display", "masked_row_indices", "fit_info",
        "fit_result", "fit_band_display", "source_plugin", "source_file", "source_sheet",
        "nan_policy", "provenance", "use_secondary_y", "subplot_target", "data_kind", "z_col_name",
        "grid_interp_method", "grid_resolution", "colormap", "vmin", "vmax", "map_display_mode",
        "contour_levels", "visible", "artist", "dataset_id",
    ],
    "Dataset.properties": ["visible_df", "x_data", "x_err_data", "y_data", "y_err_data", "z_data", "z_grid"],
}

BREAKING = "壊す変更です。PLUGIN_API_VERSION の主番号を上げ、移行表を書き、SNAPSHOT を更新してください"
ADDITION = "公開 API に追加しています。PLUGIN_API_VERSION の小番号を上げ、SNAPSHOT に足してください"


def _params(func):
    return [p for p in inspect.signature(func).parameters if p != "self"]


def _current_context():
    members = {}
    for name in dir(PluginContext):
        if name.startswith("_"):
            continue
        member = getattr(PluginContext, name)
        members[name] = _params(member) if inspect.isfunction(member) else "property"
    return members


def _compare(expected, actual):
    removed_or_changed = {k for k in expected if k not in actual or actual[k] != expected[k]}
    added = set(actual) - set(expected)
    return removed_or_changed, added


def test_snapshot_matches_the_declared_api_version():
    assert SNAPSHOT["version"] == PLUGIN_API_VERSION, "版を上げたら SNAPSHOT の version も合わせる"


def test_public_modules_export_exactly_the_snapshot():
    for module, name in ((public, "graphica.plugin"), (public_testing, "graphica.plugin.testing")):
        missing = set(SNAPSHOT[name]) - set(module.__all__)
        added = set(module.__all__) - set(SNAPSHOT[name])
        assert not missing, f"{name} から消えた {sorted(missing)}: {BREAKING}"
        assert not added, f"{name} に増えた {sorted(added)}: {ADDITION}"
        for export in module.__all__:
            assert hasattr(module, export)


def test_register_hooks_match_the_snapshot():
    actual = {n: _params(getattr(GraphicaPluginAPI, n)) for n in dir(GraphicaPluginAPI) if n.startswith("register_")}
    removed_or_changed, added = _compare(SNAPSHOT["register"], actual)
    assert not removed_or_changed, f"{sorted(removed_or_changed)}: {BREAKING}"
    assert not added, f"{sorted(added)}: {ADDITION}"


def test_plugin_context_matches_the_snapshot():
    removed_or_changed, added = _compare(SNAPSHOT["context"], _current_context())
    assert not removed_or_changed, f"{sorted(removed_or_changed)}: {BREAKING}"
    assert not added, f"{sorted(added)}: {ADDITION}"


def test_public_types_match_the_snapshot():
    for cls in (AnalysisResult, PluginMenuAction):
        fields = [f.name for f in dataclasses.fields(cls)]
        assert fields == SNAPSHOT[cls.__name__], f"{cls.__name__}: {BREAKING}"


def test_dataset_keeps_every_public_field_and_property():
    fields = dataclasses.fields(Dataset)
    required = [f.name for f in fields
                if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING]
    assert required == SNAPSHOT["Dataset.required"], f"Dataset の必須引数が変わった: {BREAKING}"

    missing_fields = set(SNAPSHOT["Dataset.fields"]) - {f.name for f in fields}
    assert not missing_fields, f"Dataset から消えたフィールド {sorted(missing_fields)}: {BREAKING}"

    properties = {n for n, v in inspect.getmembers(Dataset) if isinstance(v, property)}
    missing_props = set(SNAPSHOT["Dataset.properties"]) - properties
    assert not missing_props, f"Dataset から消えたプロパティ {sorted(missing_props)}: {BREAKING}"


def test_load_plugin_like_graphica_runs_the_real_loading_path(tmp_path):
    folder = tmp_path / "src" / "hello"
    folder.mkdir(parents=True)
    (folder / "plugin.json").write_text(
        '{"name": "Hello", "version": "1", "api_version": "%s"}' % PLUGIN_API_VERSION, encoding="utf-8")
    (folder / "helper.py").write_text("TEXT = 'hi'\n", encoding="utf-8")
    (folder / "__init__.py").write_text(
        "from .helper import TEXT\n\ndef register(api):\n    api.register_menu_action(TEXT, lambda ctx: None)\n",
        encoding="utf-8")

    api, record = public_testing.load_plugin_like_graphica(str(folder), work_dir=str(tmp_path))

    assert record["error"] is None
    assert [a.text for a in api.menu_actions] == ["hi"]
