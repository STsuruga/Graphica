# テストカバレッジ詳細

計測日: 2026-10-13  
要約は [`COVERAGE.md`](COVERAGE.md)。このファイルも `bash scripts/run_coverage.sh` が自動生成する。
ソースと並べた色付き表示は https://stsuruga.github.io/Graphica/coverage/ (CI が master の push ごとに更新)。

全体: 行 **95.1%** / 分岐 89.8%

## モジュール別

行カバレッジの低い順。「部分分岐」は if の片側しか通っていない分岐の数。

| モジュール | 行数 | 未到達 | 行カバレッジ | 分岐 | 部分分岐 | 分岐カバレッジ |
|---|---:|---:|---:|---:|---:|---:|
| `graphica/__main__.py` | 72 | 49 | 27.4% | 12 | 0 | 0.0% |
| `graphica/plugins/example_plugin/__init__.py` | 15 | 5 | 64.7% | 2 | 1 | 50.0% |
| `graphica/gui/single_instance.py` | 101 | 21 | 74.4% | 28 | 8 | 57.1% |
| `graphica/core/color_palettes.py` | 23 | 4 | 75.8% | 10 | 4 | 60.0% |
| `graphica/gui/plugin_update_flow.py` | 124 | 24 | 75.9% | 34 | 12 | 58.8% |
| `graphica/gui/color_picker_widget.py` | 156 | 32 | 76.6% | 32 | 2 | 62.5% |
| `graphica/gui/file_association.py` | 67 | 12 | 82.3% | 12 | 2 | 83.3% |
| `graphica/gui/widgets/cards.py` | 53 | 9 | 82.5% | 4 | 1 | 75.0% |
| `graphica/gui/tools/pointer.py` | 28 | 4 | 82.6% | 18 | 4 | 77.8% |
| `graphica/gui/panels/axis_settings.py` | 384 | 44 | 84.9% | 92 | 10 | 69.6% |
| `graphica/gui/tools/region_highlight.py` | 161 | 20 | 84.9% | 58 | 13 | 77.6% |
| `graphica/gui/datasets/operations/fitting.py` | 240 | 29 | 86.6% | 52 | 4 | 80.8% |
| `graphica/gui/mathtext_preview.py` | 98 | 11 | 87.5% | 22 | 2 | 81.8% |
| `graphica/core/plugin_updates.py` | 96 | 12 | 88.1% | 30 | 3 | 90.0% |
| `graphica/gui/tools/slice_extraction.py` | 131 | 13 | 88.6% | 36 | 6 | 83.3% |
| `graphica/core/json_utils.py` | 12 | 1 | 88.9% | 6 | 1 | 83.3% |
| `graphica/core/label_utils.py` | 12 | 1 | 88.9% | 6 | 1 | 83.3% |
| `graphica/gui/tools/__init__.py` | 28 | 2 | 88.9% | 8 | 2 | 75.0% |
| `graphica/gui/shell/settings_popover.py` | 196 | 20 | 89.3% | 18 | 1 | 83.3% |
| `graphica/gui/tools/layout_edit.py` | 181 | 11 | 89.9% | 56 | 13 | 76.8% |
| `graphica/gui/mixins/ui_setup_mixin.py` | 124 | 6 | 90.0% | 56 | 12 | 78.6% |
| `graphica/gui/tools/view_navigation.py` | 348 | 22 | 90.3% | 148 | 26 | 82.4% |
| `graphica/gui/mixins/export_mixin.py` | 369 | 27 | 90.6% | 90 | 14 | 82.2% |
| `graphica/gui/datasets/colors.py` | 142 | 10 | 90.9% | 66 | 5 | 86.4% |
| `graphica/gui/widget_translation.py` | 33 | 2 | 91.0% | 34 | 4 | 88.2% |
| `graphica/gui/tools/cursor.py` | 189 | 13 | 91.4% | 78 | 10 | 87.2% |
| `graphica/gui/main_app_window.py` | 217 | 6 | 91.5% | 66 | 18 | 72.7% |
| `graphica/gui/ui_mode.py` | 41 | 1 | 91.5% | 18 | 4 | 77.8% |
| `graphica/gui/dialogs/appearance.py` | 625 | 40 | 91.8% | 98 | 9 | 80.6% |
| `graphica/gui/splash.py` | 60 | 4 | 91.9% | 2 | 1 | 50.0% |
| `graphica/gui/mixins/help_mixin.py` | 142 | 9 | 92.0% | 32 | 3 | 84.4% |
| `graphica/core/diagnostics.py` | 58 | 4 | 92.1% | 18 | 2 | 88.9% |
| `graphica/gui/rendering/data_2d.py` | 37 | 3 | 92.5% | 16 | 1 | 93.8% |
| `graphica/core/excel_utils.py` | 36 | 2 | 92.6% | 18 | 2 | 88.9% |
| `graphica/gui/tools/peak_placement.py` | 81 | 6 | 92.7% | 28 | 2 | 92.9% |
| `graphica/gui/notify.py` | 28 | 2 | 92.9% | 0 | 0 | — |
| `graphica/core/methods_text.py` | 82 | 6 | 93.0% | 46 | 1 | 93.5% |
| `graphica/core/safe_eval.py` | 128 | 6 | 93.3% | 66 | 7 | 89.4% |
| `graphica/gui/panels/__init__.py` | 22 | 1 | 93.3% | 8 | 1 | 87.5% |
| `graphica/gui/tools/manager.py` | 29 | 1 | 93.3% | 16 | 2 | 87.5% |
| `graphica/gui/tools/range_select.py` | 119 | 6 | 93.6% | 38 | 4 | 89.5% |
| `graphica/gui/data_table_model.py` | 131 | 8 | 93.7% | 60 | 4 | 93.3% |
| `graphica/gui/datasets/fitting.py` | 45 | 2 | 93.9% | 4 | 1 | 75.0% |
| `graphica/gui/tools/annotation.py` | 184 | 7 | 94.1% | 72 | 4 | 88.9% |
| `graphica/gui/shell/project_tabs.py` | 64 | 1 | 94.3% | 6 | 3 | 50.0% |
| `graphica/gui/widgets/segmented.py` | 122 | 6 | 94.4% | 20 | 2 | 90.0% |
| `graphica/plugin/testing.py` | 18 | 1 | 94.4% | 0 | 0 | — |
| `graphica/gui/data_editor.py` | 527 | 23 | 94.8% | 144 | 12 | 91.7% |
| `graphica/gui/mixins/project_io_mixin.py` | 222 | 9 | 94.8% | 86 | 7 | 91.9% |
| `graphica/gui/shell/rail.py` | 66 | 2 | 94.9% | 12 | 2 | 83.3% |
| `graphica/gui/datasets/property_panel.py` | 392 | 10 | 95.4% | 106 | 13 | 87.7% |
| `graphica/gui/workers.py` | 197 | 8 | 95.4% | 64 | 4 | 93.8% |
| `graphica/gui/dialogs/data_import.py` | 467 | 18 | 95.5% | 88 | 7 | 92.0% |
| `graphica/gui/minimap_widget.py` | 92 | 5 | 95.6% | 22 | 0 | 100.0% |
| `graphica/gui/panels/dataset_tree.py` | 267 | 5 | 95.8% | 86 | 10 | 88.4% |
| `graphica/gui/builders/property_sections.py` | 141 | 4 | 95.8% | 48 | 4 | 91.7% |
| `graphica/core/marker_style.py` | 50 | 1 | 96.1% | 26 | 2 | 92.3% |
| `graphica/gui/project_files.py` | 253 | 10 | 96.1% | 78 | 3 | 96.2% |
| `graphica/gui/export_size.py` | 98 | 2 | 96.2% | 32 | 3 | 90.6% |
| `graphica/core/analysis.py` | 744 | 21 | 96.2% | 284 | 18 | 93.7% |
| `graphica/core/script_export.py` | 177 | 5 | 96.3% | 90 | 5 | 94.4% |
| `graphica/gui/menu_bar.py` | 184 | 3 | 96.3% | 62 | 6 | 90.3% |
| `graphica/gui/shell/bottom_panel.py` | 244 | 6 | 96.4% | 32 | 4 | 87.5% |
| `graphica/gui/dataset_style_icon.py` | 109 | 2 | 96.5% | 32 | 3 | 90.6% |
| `graphica/gui/data_import_flow.py` | 231 | 5 | 96.5% | 80 | 6 | 92.5% |
| `graphica/gui/builders/property_widgets.py` | 105 | 2 | 96.5% | 10 | 2 | 80.0% |
| `graphica/gui/log_axis_notes.py` | 42 | 1 | 96.6% | 16 | 1 | 93.8% |
| `graphica/gui/datasets/overlays.py` | 48 | 2 | 96.7% | 12 | 0 | 100.0% |
| `graphica/gui/datasets/host.py` | 107 | 2 | 96.7% | 14 | 2 | 85.7% |
| `graphica/core/dataset.py` | 298 | 6 | 96.7% | 96 | 7 | 92.7% |
| `graphica/core/named_colors.py` | 89 | 2 | 96.7% | 34 | 2 | 94.1% |
| `graphica/gui/shell/side_pages.py` | 173 | 2 | 96.8% | 14 | 4 | 71.4% |
| `graphica/core/plugin_install.py` | 46 | 1 | 96.9% | 18 | 1 | 94.4% |
| `graphica/gui/datasets/order.py` | 209 | 2 | 97.0% | 94 | 7 | 92.6% |
| `graphica/gui/rendering/data_1d.py` | 215 | 5 | 97.0% | 90 | 4 | 95.6% |
| `graphica/gui/builders/common.py` | 90 | 2 | 97.1% | 12 | 1 | 91.7% |
| `graphica/gui/datasets/operations/peaks.py` | 59 | 1 | 97.3% | 14 | 1 | 92.9% |
| `graphica/gui/dialogs/app.py` | 781 | 11 | 97.3% | 140 | 14 | 90.0% |
| `graphica/gui/shell/inspector.py` | 101 | 2 | 97.3% | 10 | 1 | 90.0% |
| `graphica/gui/main_window.py` | 775 | 16 | 97.4% | 118 | 7 | 94.1% |
| `graphica/gui/plugin_context.py` | 102 | 2 | 97.5% | 18 | 1 | 94.4% |
| `graphica/gui/widgets/slider_spin.py` | 38 | 0 | 97.5% | 2 | 1 | 50.0% |
| `graphica/gui/export_preview_panel.py` | 243 | 1 | 97.7% | 58 | 6 | 89.7% |
| `graphica/gui/updater.py` | 73 | 2 | 97.7% | 14 | 0 | 100.0% |
| `graphica/gui/plot_type_drawers.py` | 71 | 1 | 97.8% | 20 | 1 | 95.0% |
| `graphica/core/plugin_testing.py` | 150 | 4 | 97.9% | 38 | 0 | 100.0% |
| `graphica/core/plugin_api.py` | 221 | 3 | 98.1% | 46 | 2 | 95.7% |
| `graphica/gui/axis_bindings.py` | 48 | 0 | 98.1% | 6 | 1 | 83.3% |
| `graphica/gui/mixins/quick_access_mixin.py` | 122 | 0 | 98.2% | 42 | 3 | 92.9% |
| `graphica/gui/dialogs/export.py` | 271 | 3 | 98.3% | 20 | 0 | 90.0% |
| `graphica/gui/dialogs/analysis.py` | 886 | 7 | 98.4% | 84 | 9 | 89.3% |
| `graphica/gui/theme_color.py` | 61 | 0 | 98.5% | 6 | 1 | 83.3% |
| `graphica/gui/rendering/appearance.py` | 254 | 1 | 98.6% | 92 | 4 | 95.7% |
| `graphica/gui/canvas.py` | 338 | 3 | 98.6% | 80 | 3 | 96.2% |
| `graphica/models/project.py` | 119 | 1 | 98.7% | 32 | 1 | 96.9% |
| `graphica/gui/theme.py` | 254 | 2 | 98.7% | 62 | 2 | 96.8% |
| `graphica/gui/dock_layout.py` | 81 | 0 | 99.0% | 18 | 1 | 94.4% |
| `graphica/gui/builders/canvas_area.py` | 198 | 1 | 99.1% | 20 | 1 | 95.0% |
| `graphica/gui/datasets/operations/processing.py` | 364 | 3 | 99.2% | 114 | 1 | 99.1% |
| `graphica/gui/rendering/common.py` | 186 | 1 | 99.2% | 60 | 1 | 98.3% |
| `graphica/gui/shell/header.py` | 114 | 0 | 99.2% | 10 | 1 | 90.0% |
| `graphica/gui/binding.py` | 97 | 1 | 99.2% | 30 | 0 | 100.0% |
| `graphica/gui/widgets/type_tiles.py` | 102 | 1 | 99.2% | 26 | 0 | 100.0% |
| `graphica/core/fit_models.py` | 222 | 1 | 99.3% | 52 | 1 | 98.1% |
| `graphica/gui/rendering/annotations.py` | 219 | 1 | 99.4% | 90 | 1 | 98.9% |
| `graphica/gui/builders/axis_panel.py` | 308 | 0 | 99.4% | 20 | 2 | 90.0% |
| `graphica/gui/datasets/operations/transfer.py` | 147 | 0 | 99.5% | 52 | 1 | 98.1% |
| `graphica/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/assets/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/assets/icons/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/app_paths.py` | 19 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/core/axis_settings.py` | 24 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/core/caption_export.py` | 18 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/core/commands.py` | 156 | 0 | 100.0% | 12 | 0 | 100.0% |
| `graphica/core/cvd_simulation.py` | 16 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/core/grid_data.py` | 70 | 0 | 100.0% | 20 | 0 | 100.0% |
| `graphica/core/i18n.py` | 21 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/core/plugin_context.py` | 24 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/plugin_manifest.py` | 33 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/core/plugin_types.py` | 79 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/provenance.py` | 4 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/report_export.py` | 17 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/core/translations_en.py` | 1 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/unit_conversion.py` | 24 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/core/update_check.py` | 35 | 0 | 100.0% | 8 | 0 | 100.0% |
| `graphica/core/version.py` | 3 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/app_settings.py` | 83 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/gui/builders/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/builders/dataset_panel.py` | 353 | 0 | 100.0% | 12 | 0 | 100.0% |
| `graphica/gui/color_history.py` | 23 | 0 | 100.0% | 8 | 0 | 100.0% |
| `graphica/gui/crash_handler.py` | 40 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/gui/cvd_preview.py` | 15 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dataset_bindings.py` | 42 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/datasets/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/actions_menu.py` | 69 | 0 | 100.0% | 24 | 0 | 100.0% |
| `graphica/gui/datasets/operations/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/operations/runner.py` | 91 | 0 | 100.0% | 14 | 0 | 100.0% |
| `graphica/gui/datasets/peaks.py` | 13 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/plugin_runs.py` | 66 | 0 | 100.0% | 26 | 0 | 100.0% |
| `graphica/gui/datasets/processing.py` | 44 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/transfer.py` | 23 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/detached_canvas_window.py` | 11 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dialog_dirs.py` | 70 | 0 | 100.0% | 16 | 0 | 100.0% |
| `graphica/gui/dialogs/__init__.py` | 7 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dialogs/data_edit.py` | 359 | 0 | 100.0% | 30 | 0 | 100.0% |
| `graphica/gui/export_settings.py` | 7 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/icon_utils.py` | 28 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/mixins/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/provenance_panel.py` | 44 | 0 | 100.0% | 8 | 0 | 100.0% |
| `graphica/gui/rendering/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/residual_panel.py` | 46 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/gui/resources.py` | 8 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/shell/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/shell/dataset_page.py` | 198 | 0 | 100.0% | 34 | 0 | 100.0% |
| `graphica/gui/shell/icons.py` | 13 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/gui/shell/tab_shell.py` | 33 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/gui/task_runner.py` | 22 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/widgets/__init__.py` | 6 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/widgets/color_chips.py` | 75 | 0 | 100.0% | 12 | 0 | 100.0% |
| `graphica/models/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/plugin/__init__.py` | 6 | 0 | 100.0% | 0 | 0 | — |
| `graphica/sample_data/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |

## 未到達の行

テストで一度も実行されなかった行の番号(パス順)。すべて到達しているモジュールは省略。

### `graphica/__main__.py` (49 行)

31-33, 35-37, 43, 52-53, 62, 64, 67-68, 70-73, 76, 78-80, 82, 84, 87-88, 90, 92-93, 95-98, 100-101, 103, 105-107, 109, 112-115, 117-120, 122, 124

### `graphica/core/analysis.py` (21 行)

150, 320, 326, 331, 335, 338, 440, 467, 480, 596, 676, 735, 1119, 1123, 1222, 1229-1230, 1292-1295

### `graphica/core/color_palettes.py` (4 行)

41, 45, 47, 49

### `graphica/core/dataset.py` (6 行)

461-462, 474-475, 502-503

### `graphica/core/diagnostics.py` (4 行)

39-40, 51, 75

### `graphica/core/excel_utils.py` (2 行)

36, 48

### `graphica/core/fit_models.py` (1 行)

94

### `graphica/core/json_utils.py` (1 行)

24

### `graphica/core/label_utils.py` (1 行)

20

### `graphica/core/marker_style.py` (1 行)

58

### `graphica/core/methods_text.py` (6 行)

68-72, 76

### `graphica/core/named_colors.py` (2 行)

99, 120

### `graphica/core/plugin_api.py` (3 行)

389, 415-416

### `graphica/core/plugin_install.py` (1 行)

62

### `graphica/core/plugin_testing.py` (4 行)

186, 208, 214, 232

### `graphica/core/plugin_updates.py` (12 行)

23-25, 50, 55-56, 58, 70, 137-138, 151, 153

### `graphica/core/safe_eval.py` (6 行)

82, 88, 97, 107, 136, 147

### `graphica/core/script_export.py` (5 行)

23-24, 190, 197, 260

### `graphica/gui/binding.py` (1 行)

119

### `graphica/gui/builders/canvas_area.py` (1 行)

270

### `graphica/gui/builders/common.py` (2 行)

130-131

### `graphica/gui/builders/property_sections.py` (4 行)

151, 169, 186, 194

### `graphica/gui/builders/property_widgets.py` (2 行)

61, 158

### `graphica/gui/canvas.py` (3 行)

80-81, 553

### `graphica/gui/color_picker_widget.py` (32 行)

55, 113-114, 117-118, 120-121, 123-124, 126-128, 130-136, 139, 151-157, 162, 164, 184-186

### `graphica/gui/data_editor.py` (23 行)

561-564, 569, 582-583, 591-594, 602-603, 605-606, 608-609, 648-649, 655-656, 669, 703

### `graphica/gui/data_import_flow.py` (5 行)

262, 267, 287-289

### `graphica/gui/data_table_model.py` (8 行)

87-89, 101-102, 108, 144, 161

### `graphica/gui/dataset_style_icon.py` (2 行)

56, 103

### `graphica/gui/datasets/colors.py` (10 行)

54, 63, 94, 115-121

### `graphica/gui/datasets/fitting.py` (2 行)

51-52

### `graphica/gui/datasets/host.py` (2 行)

59, 69

### `graphica/gui/datasets/operations/fitting.py` (29 行)

76-77, 161-170, 175-178, 180-181, 186-193, 317-318, 331

### `graphica/gui/datasets/operations/peaks.py` (1 行)

94

### `graphica/gui/datasets/operations/processing.py` (3 行)

347, 544-545

### `graphica/gui/datasets/order.py` (2 行)

35, 161

### `graphica/gui/datasets/overlays.py` (2 行)

68-69

### `graphica/gui/datasets/property_panel.py` (10 行)

80, 111, 466, 486, 489-490, 512, 530, 582-583

### `graphica/gui/dialogs/analysis.py` (7 行)

248, 381-384, 560, 1227

### `graphica/gui/dialogs/app.py` (11 行)

341-342, 350-351, 827-828, 953-954, 980-981, 1049

### `graphica/gui/dialogs/appearance.py` (40 行)

201, 221, 226-229, 395, 534, 538, 545, 549-551, 555-560, 562-570, 575-576, 579-581, 587, 590-591, 710-712, 742

### `graphica/gui/dialogs/data_import.py` (18 行)

32, 89-90, 98-100, 103-105, 117, 273, 326-328, 389-390, 612-613

### `graphica/gui/dialogs/export.py` (3 行)

366, 369-370

### `graphica/gui/export_preview_panel.py` (1 行)

196

### `graphica/gui/export_size.py` (2 行)

73, 142

### `graphica/gui/file_association.py` (12 行)

16-17, 52-53, 58-63, 76, 88

### `graphica/gui/log_axis_notes.py` (1 行)

57

### `graphica/gui/main_app_window.py` (6 行)

71-72, 133, 223, 229, 248

### `graphica/gui/main_window.py` (16 行)

30, 583-584, 595-596, 604-612, 793, 1134

### `graphica/gui/mathtext_preview.py` (11 行)

42, 80-83, 98-102, 104

### `graphica/gui/menu_bar.py` (3 行)

236, 273, 305

### `graphica/gui/minimap_widget.py` (5 行)

124-126, 138, 140

### `graphica/gui/mixins/export_mixin.py` (27 行)

103-104, 108-109, 181-183, 194, 233, 246, 250-252, 263, 273-276, 280, 292-294, 441-442, 496, 510-511

### `graphica/gui/mixins/help_mixin.py` (9 行)

77, 142-143, 162-164, 193-195

### `graphica/gui/mixins/project_io_mixin.py` (9 行)

131, 180, 281-282, 320-322, 348-349

### `graphica/gui/mixins/ui_setup_mixin.py` (6 行)

65-66, 90, 95, 108, 110

### `graphica/gui/notify.py` (2 行)

29, 57

### `graphica/gui/panels/__init__.py` (1 行)

42

### `graphica/gui/panels/axis_settings.py` (44 行)

65-68, 72, 102, 151, 194, 337, 401-404, 415-418, 428-431, 434-437, 485, 488, 500-510, 512-517

### `graphica/gui/panels/dataset_tree.py` (5 行)

159, 165, 208, 212, 272

### `graphica/gui/plot_type_drawers.py` (1 行)

124

### `graphica/gui/plugin_context.py` (2 行)

36, 121

### `graphica/gui/plugin_update_flow.py` (24 行)

29, 54-55, 66, 71-73, 77, 85, 96, 98, 104, 116-117, 140-143, 145, 150-152, 163-164

### `graphica/gui/project_files.py` (10 行)

72-73, 85, 199-201, 276-277, 345, 347

### `graphica/gui/rendering/annotations.py` (1 行)

90

### `graphica/gui/rendering/appearance.py` (1 行)

389

### `graphica/gui/rendering/common.py` (1 行)

312

### `graphica/gui/rendering/data_1d.py` (5 行)

54, 181, 266, 330-331

### `graphica/gui/rendering/data_2d.py` (3 行)

27-29

### `graphica/gui/shell/bottom_panel.py` (6 行)

139, 206, 208, 285, 310, 319

### `graphica/gui/shell/inspector.py` (2 行)

137, 140

### `graphica/gui/shell/project_tabs.py` (1 行)

52

### `graphica/gui/shell/rail.py` (2 行)

68, 80

### `graphica/gui/shell/settings_popover.py` (20 行)

46-62, 64, 222-223

### `graphica/gui/shell/side_pages.py` (2 行)

218, 224

### `graphica/gui/single_instance.py` (21 行)

24-28, 52-53, 55-58, 77-81, 97, 104, 114-115, 119

### `graphica/gui/splash.py` (4 行)

80-83

### `graphica/gui/theme.py` (2 行)

1235, 1304

### `graphica/gui/tools/__init__.py` (2 行)

44, 55

### `graphica/gui/tools/annotation.py` (7 行)

118, 191-195, 245

### `graphica/gui/tools/cursor.py` (13 行)

136, 170, 202, 206, 222-223, 230, 235, 255, 294-295, 304, 308

### `graphica/gui/tools/layout_edit.py` (11 行)

53-54, 88, 93, 113, 169, 200, 205, 231, 237, 276

### `graphica/gui/tools/manager.py` (1 行)

73

### `graphica/gui/tools/peak_placement.py` (6 行)

65, 115, 122-123, 132-133

### `graphica/gui/tools/pointer.py` (4 行)

10, 28, 36, 42

### `graphica/gui/tools/range_select.py` (6 行)

76-77, 101, 132, 157, 188

### `graphica/gui/tools/region_highlight.py` (20 行)

85-90, 97, 114, 117, 131-132, 149-150, 158, 165, 171, 179, 205, 214, 218

### `graphica/gui/tools/slice_extraction.py` (13 行)

87-88, 112, 127-128, 136, 146, 163, 181-182, 189-191

### `graphica/gui/tools/view_navigation.py` (22 行)

86, 100, 153, 165, 188, 201, 209, 213, 266, 302, 314, 320, 342, 362, 366, 374, 402, 453-455, 459-460

### `graphica/gui/ui_mode.py` (1 行)

72

### `graphica/gui/updater.py` (2 行)

44-45

### `graphica/gui/widget_translation.py` (2 行)

32, 35

### `graphica/gui/widgets/cards.py` (9 行)

63-71

### `graphica/gui/widgets/segmented.py` (6 行)

90-93, 138-139

### `graphica/gui/widgets/type_tiles.py` (1 行)

101

### `graphica/gui/workers.py` (8 行)

39, 72, 98-99, 208-209, 253-254

### `graphica/models/project.py` (1 行)

47

### `graphica/plugin/testing.py` (1 行)

57

### `graphica/plugins/example_plugin/__init__.py` (5 行)

15, 19-20, 26-27
