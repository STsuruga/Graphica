# テストカバレッジ詳細

計測日: 2026-10-24  
要約は [`COVERAGE.md`](COVERAGE.md)。このファイルも `bash scripts/run_coverage.sh` が自動生成する。
ソースと並べた色付き表示は https://stsuruga.github.io/Graphica/coverage/ (CI が master の push ごとに更新)。

全体: 行 **94.8%** / 分岐 89.2%

## モジュール別

行カバレッジの低い順。「部分分岐」は if の片側しか通っていない分岐の数。

| モジュール | 行数 | 未到達 | 行カバレッジ | 分岐 | 部分分岐 | 分岐カバレッジ |
|---|---:|---:|---:|---:|---:|---:|
| `graphica/__main__.py` | 72 | 49 | 27.4% | 12 | 0 | 0.0% |
| `graphica/plugins/example_plugin/__init__.py` | 15 | 5 | 64.7% | 2 | 1 | 50.0% |
| `graphica/gui/single_instance.py` | 101 | 21 | 74.4% | 28 | 8 | 57.1% |
| `graphica/core/color_palettes.py` | 23 | 4 | 75.8% | 10 | 4 | 60.0% |
| `graphica/gui/plugin_update_flow.py` | 124 | 24 | 75.9% | 34 | 12 | 58.8% |
| `graphica/gui/color_picker_widget.py` | 160 | 32 | 77.1% | 32 | 2 | 62.5% |
| `graphica/gui/widgets/eye_toggle.py` | 45 | 8 | 81.6% | 4 | 1 | 75.0% |
| `graphica/gui/file_association.py` | 67 | 12 | 82.3% | 12 | 2 | 83.3% |
| `graphica/gui/widgets/cards.py` | 53 | 9 | 82.5% | 4 | 1 | 75.0% |
| `graphica/gui/tools/pointer.py` | 28 | 4 | 82.6% | 18 | 4 | 77.8% |
| `graphica/gui/tools/region_highlight.py` | 161 | 20 | 84.9% | 58 | 13 | 77.6% |
| `graphica/gui/panels/axis_settings.py` | 439 | 47 | 85.4% | 116 | 16 | 70.7% |
| `graphica/gui/datasets/operations/fitting.py` | 240 | 29 | 86.6% | 52 | 4 | 80.8% |
| `graphica/gui/shell/layout_popover.py` | 44 | 4 | 87.0% | 2 | 0 | 0.0% |
| `graphica/gui/motion.py` | 320 | 31 | 87.6% | 84 | 15 | 77.4% |
| `graphica/core/plugin_updates.py` | 96 | 12 | 88.1% | 30 | 3 | 90.0% |
| `graphica/gui/tools/slice_extraction.py` | 131 | 13 | 88.6% | 36 | 6 | 83.3% |
| `graphica/gui/mathtext_preview.py` | 109 | 11 | 88.7% | 24 | 2 | 83.3% |
| `graphica/core/json_utils.py` | 12 | 1 | 88.9% | 6 | 1 | 83.3% |
| `graphica/core/label_utils.py` | 12 | 1 | 88.9% | 6 | 1 | 83.3% |
| `graphica/gui/tools/__init__.py` | 28 | 2 | 88.9% | 8 | 2 | 75.0% |
| `graphica/gui/shell/settings_popover.py` | 198 | 20 | 89.4% | 18 | 1 | 83.3% |
| `graphica/gui/tools/layout_edit.py` | 181 | 11 | 89.9% | 56 | 13 | 76.8% |
| `graphica/gui/mixins/ui_setup_mixin.py` | 123 | 6 | 89.9% | 56 | 12 | 78.6% |
| `graphica/gui/mixins/export_mixin.py` | 309 | 22 | 90.2% | 68 | 13 | 77.9% |
| `graphica/gui/tools/view_navigation.py` | 348 | 22 | 90.3% | 148 | 26 | 82.4% |
| `graphica/gui/datasets/colors.py` | 142 | 10 | 90.9% | 66 | 5 | 86.4% |
| `graphica/gui/widget_translation.py` | 33 | 2 | 91.0% | 34 | 4 | 88.2% |
| `graphica/gui/tools/cursor.py` | 189 | 13 | 91.4% | 78 | 10 | 87.2% |
| `graphica/gui/ui_mode.py` | 41 | 1 | 91.5% | 18 | 4 | 77.8% |
| `graphica/gui/dialogs/appearance.py` | 625 | 40 | 91.8% | 98 | 9 | 80.6% |
| `graphica/gui/main_app_window.py` | 218 | 7 | 91.9% | 66 | 16 | 75.8% |
| `graphica/gui/splash.py` | 60 | 4 | 91.9% | 2 | 1 | 50.0% |
| `graphica/gui/mixins/help_mixin.py` | 142 | 9 | 92.0% | 32 | 3 | 84.4% |
| `graphica/core/diagnostics.py` | 58 | 4 | 92.1% | 18 | 2 | 88.9% |
| `graphica/gui/builders/axis_format_sections.py` | 140 | 5 | 92.4% | 44 | 9 | 79.5% |
| `graphica/gui/rendering/data_2d.py` | 37 | 3 | 92.5% | 16 | 1 | 93.8% |
| `graphica/core/excel_utils.py` | 36 | 2 | 92.6% | 18 | 2 | 88.9% |
| `graphica/gui/tools/peak_placement.py` | 81 | 6 | 92.7% | 28 | 2 | 92.9% |
| `graphica/gui/notify.py` | 28 | 2 | 92.9% | 0 | 0 | — |
| `graphica/core/methods_text.py` | 82 | 6 | 93.0% | 46 | 1 | 93.5% |
| `graphica/core/safe_eval.py` | 128 | 6 | 93.3% | 66 | 7 | 89.4% |
| `graphica/gui/panels/__init__.py` | 22 | 1 | 93.3% | 8 | 1 | 87.5% |
| `graphica/gui/tools/manager.py` | 29 | 1 | 93.3% | 16 | 2 | 87.5% |
| `graphica/gui/builders/axis_range_sections.py` | 92 | 3 | 93.4% | 30 | 5 | 83.3% |
| `graphica/gui/tools/range_select.py` | 119 | 6 | 93.6% | 38 | 4 | 89.5% |
| `graphica/gui/data_table_model.py` | 131 | 8 | 93.7% | 60 | 4 | 93.3% |
| `graphica/gui/datasets/fitting.py` | 45 | 2 | 93.9% | 4 | 1 | 75.0% |
| `graphica/gui/builders/property_sections.py` | 190 | 7 | 94.0% | 58 | 6 | 86.2% |
| `graphica/gui/mixins/project_io_mixin.py` | 227 | 11 | 94.0% | 88 | 8 | 90.9% |
| `graphica/gui/shell/fit_result_view.py` | 136 | 5 | 94.0% | 32 | 3 | 84.4% |
| `graphica/gui/tools/annotation.py` | 184 | 7 | 94.1% | 72 | 4 | 88.9% |
| `graphica/gui/shell/subplot_target_bar.py` | 130 | 5 | 94.2% | 24 | 2 | 83.3% |
| `graphica/gui/shell/project_tabs.py` | 64 | 1 | 94.3% | 6 | 3 | 50.0% |
| `graphica/plugin/testing.py` | 18 | 1 | 94.4% | 0 | 0 | — |
| `graphica/gui/data_editor.py` | 527 | 23 | 94.8% | 144 | 12 | 91.7% |
| `graphica/core/script_export.py` | 182 | 7 | 94.9% | 94 | 7 | 92.6% |
| `graphica/gui/shell/bottom_panel.py` | 310 | 9 | 95.3% | 50 | 8 | 84.0% |
| `graphica/gui/workers.py` | 197 | 8 | 95.4% | 64 | 4 | 93.8% |
| `graphica/gui/datasets/property_panel.py` | 396 | 10 | 95.4% | 108 | 13 | 88.0% |
| `graphica/gui/shell/rail.py` | 114 | 3 | 95.5% | 18 | 3 | 83.3% |
| `graphica/gui/dialogs/data_import.py` | 467 | 18 | 95.5% | 88 | 7 | 92.0% |
| `graphica/gui/widgets/segmented.py` | 210 | 7 | 95.7% | 44 | 4 | 90.9% |
| `graphica/gui/minimap_widget.py` | 95 | 5 | 95.7% | 22 | 0 | 100.0% |
| `graphica/gui/panels/dataset_tree.py` | 267 | 5 | 95.8% | 86 | 10 | 88.4% |
| `graphica/core/marker_style.py` | 50 | 1 | 96.1% | 26 | 2 | 92.3% |
| `graphica/gui/project_files.py` | 254 | 10 | 96.1% | 78 | 3 | 96.2% |
| `graphica/gui/export_size.py` | 98 | 2 | 96.2% | 32 | 3 | 90.6% |
| `graphica/plugin/ui.py` | 22 | 0 | 96.2% | 4 | 1 | 75.0% |
| `graphica/core/analysis.py` | 744 | 21 | 96.2% | 284 | 18 | 93.7% |
| `graphica/gui/dock_layout.py` | 106 | 0 | 96.3% | 28 | 5 | 82.1% |
| `graphica/gui/menu_bar.py` | 184 | 3 | 96.3% | 62 | 6 | 90.3% |
| `graphica/gui/shell/header.py` | 155 | 3 | 96.4% | 10 | 1 | 70.0% |
| `graphica/gui/dataset_style_icon.py` | 110 | 2 | 96.5% | 32 | 3 | 90.6% |
| `graphica/gui/data_import_flow.py` | 236 | 5 | 96.5% | 82 | 6 | 92.7% |
| `graphica/gui/log_axis_notes.py` | 42 | 1 | 96.6% | 16 | 1 | 93.8% |
| `graphica/gui/datasets/overlays.py` | 48 | 2 | 96.7% | 12 | 0 | 100.0% |
| `graphica/gui/datasets/host.py` | 107 | 2 | 96.7% | 14 | 2 | 85.7% |
| `graphica/core/dataset.py` | 298 | 6 | 96.7% | 96 | 7 | 92.7% |
| `graphica/core/named_colors.py` | 89 | 2 | 96.7% | 34 | 2 | 94.1% |
| `graphica/gui/shell/side_pages.py` | 172 | 2 | 96.8% | 14 | 4 | 71.4% |
| `graphica/core/plugin_install.py` | 46 | 1 | 96.9% | 18 | 1 | 94.4% |
| `graphica/gui/datasets/order.py` | 209 | 2 | 97.0% | 94 | 7 | 92.6% |
| `graphica/gui/rendering/data_1d.py` | 215 | 5 | 97.0% | 90 | 4 | 95.6% |
| `graphica/gui/builders/property_widgets.py` | 129 | 2 | 97.2% | 12 | 2 | 83.3% |
| `graphica/gui/datasets/operations/peaks.py` | 59 | 1 | 97.3% | 14 | 1 | 92.9% |
| `graphica/gui/dialogs/app.py` | 786 | 11 | 97.3% | 140 | 14 | 90.0% |
| `graphica/gui/main_window.py` | 785 | 17 | 97.3% | 118 | 7 | 94.1% |
| `graphica/gui/export_preview_panel.py` | 312 | 4 | 97.4% | 70 | 6 | 91.4% |
| `graphica/gui/builders/common.py` | 101 | 2 | 97.5% | 18 | 1 | 94.4% |
| `graphica/gui/plugin_context.py` | 102 | 2 | 97.5% | 18 | 1 | 94.4% |
| `graphica/gui/updater.py` | 73 | 2 | 97.7% | 14 | 0 | 100.0% |
| `graphica/gui/shell/inspector.py` | 119 | 2 | 97.7% | 12 | 1 | 91.7% |
| `graphica/gui/dialogs/export.py` | 204 | 3 | 97.7% | 16 | 0 | 87.5% |
| `graphica/gui/plot_type_drawers.py` | 71 | 1 | 97.8% | 20 | 1 | 95.0% |
| `graphica/gui/theme.py` | 296 | 3 | 97.8% | 74 | 5 | 93.2% |
| `graphica/core/plugin_testing.py` | 150 | 4 | 97.9% | 38 | 0 | 100.0% |
| `graphica/gui/widgets/slider_spin.py` | 43 | 0 | 97.9% | 4 | 1 | 75.0% |
| `graphica/core/plugin_api.py` | 221 | 3 | 98.1% | 46 | 2 | 95.7% |
| `graphica/gui/axis_bindings.py` | 48 | 0 | 98.1% | 6 | 1 | 83.3% |
| `graphica/gui/mixins/quick_access_mixin.py` | 122 | 0 | 98.2% | 42 | 3 | 92.9% |
| `graphica/gui/dialogs/analysis.py` | 886 | 7 | 98.4% | 84 | 9 | 89.3% |
| `graphica/gui/builders/canvas_area.py` | 237 | 2 | 98.5% | 30 | 2 | 93.3% |
| `graphica/gui/theme_color.py` | 61 | 0 | 98.5% | 6 | 1 | 83.3% |
| `graphica/gui/rendering/appearance.py` | 255 | 1 | 98.6% | 92 | 4 | 95.7% |
| `graphica/gui/canvas.py` | 338 | 3 | 98.6% | 80 | 3 | 96.2% |
| `graphica/models/project.py` | 119 | 1 | 98.7% | 32 | 1 | 96.9% |
| `graphica/gui/datasets/operations/processing.py` | 364 | 3 | 99.2% | 114 | 1 | 99.1% |
| `graphica/gui/rendering/common.py` | 186 | 1 | 99.2% | 60 | 1 | 98.3% |
| `graphica/gui/binding.py` | 97 | 1 | 99.2% | 30 | 0 | 100.0% |
| `graphica/gui/widgets/type_tiles.py` | 102 | 1 | 99.2% | 26 | 0 | 100.0% |
| `graphica/core/fit_models.py` | 222 | 1 | 99.3% | 52 | 1 | 98.1% |
| `graphica/gui/rendering/annotations.py` | 219 | 1 | 99.4% | 90 | 1 | 98.9% |
| `graphica/gui/datasets/operations/transfer.py` | 147 | 0 | 99.5% | 52 | 1 | 98.1% |
| `graphica/gui/builders/dataset_panel.py` | 389 | 1 | 99.5% | 20 | 1 | 95.0% |
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
| `graphica/gui/app_settings.py` | 84 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/gui/builders/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/builders/axis_panel.py` | 336 | 0 | 100.0% | 24 | 0 | 100.0% |
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
| `graphica/gui/export_settings.py` | 9 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/icon_utils.py` | 28 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/mixins/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/provenance_panel.py` | 45 | 0 | 100.0% | 8 | 0 | 100.0% |
| `graphica/gui/rendering/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/residual_panel.py` | 46 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/gui/resources.py` | 8 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/shell/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/shell/dataset_page.py` | 198 | 0 | 100.0% | 34 | 0 | 100.0% |
| `graphica/gui/shell/icons.py` | 13 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/gui/shell/tab_shell.py` | 40 | 0 | 100.0% | 4 | 0 | 100.0% |
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

### `graphica/core/script_export.py` (7 行)

23-24, 190, 194, 196, 202, 265

### `graphica/gui/binding.py` (1 行)

119

### `graphica/gui/builders/axis_format_sections.py` (5 行)

94, 161, 163, 171, 200

### `graphica/gui/builders/axis_range_sections.py` (3 行)

82, 124, 131

### `graphica/gui/builders/canvas_area.py` (2 行)

121, 331

### `graphica/gui/builders/common.py` (2 行)

144-145

### `graphica/gui/builders/dataset_panel.py` (1 行)

454

### `graphica/gui/builders/property_sections.py` (7 行)

201-203, 226, 242, 259, 267

### `graphica/gui/builders/property_widgets.py` (2 行)

67, 185

### `graphica/gui/canvas.py` (3 行)

80-81, 553

### `graphica/gui/color_picker_widget.py` (32 行)

60, 117-118, 121-122, 124-125, 127-128, 130-132, 134-140, 143, 155-161, 166, 168, 188-190

### `graphica/gui/data_editor.py` (23 行)

561-564, 569, 582-583, 591-594, 602-603, 605-606, 608-609, 648-649, 655-656, 669, 703

### `graphica/gui/data_import_flow.py` (5 行)

261, 266, 286-288

### `graphica/gui/data_table_model.py` (8 行)

87-89, 101-102, 108, 144, 161

### `graphica/gui/dataset_style_icon.py` (2 行)

58, 105

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

80, 111, 472, 492, 495-496, 518, 536, 588-589

### `graphica/gui/dialogs/analysis.py` (7 行)

248, 381-384, 560, 1227

### `graphica/gui/dialogs/app.py` (11 行)

344-345, 353-354, 833-834, 959-960, 986-987, 1055

### `graphica/gui/dialogs/appearance.py` (40 行)

201, 221, 226-229, 395, 534, 538, 545, 549-551, 555-560, 562-570, 575-576, 579-581, 587, 590-591, 710-712, 742

### `graphica/gui/dialogs/data_import.py` (18 行)

32, 89-90, 98-100, 103-105, 117, 273, 326-328, 389-390, 612-613

### `graphica/gui/dialogs/export.py` (3 行)

247, 250-251

### `graphica/gui/export_preview_panel.py` (4 行)

205, 272, 457-458

### `graphica/gui/export_size.py` (2 行)

73, 142

### `graphica/gui/file_association.py` (12 行)

16-17, 52-53, 58-63, 76, 88

### `graphica/gui/log_axis_notes.py` (1 行)

57

### `graphica/gui/main_app_window.py` (7 行)

73-74, 119, 152, 233, 239, 258

### `graphica/gui/main_window.py` (17 行)

30, 597-598, 609-610, 618-626, 807, 1071, 1147

### `graphica/gui/mathtext_preview.py` (11 行)

42, 80-83, 98-102, 104

### `graphica/gui/menu_bar.py` (3 行)

236, 273, 305

### `graphica/gui/minimap_widget.py` (5 行)

128-130, 142, 144

### `graphica/gui/mixins/export_mixin.py` (22 行)

119-120, 124-125, 199-201, 212, 251, 264, 268-270, 281, 291-294, 298, 310-312

### `graphica/gui/mixins/help_mixin.py` (9 行)

77, 142-143, 162-164, 193-195

### `graphica/gui/mixins/project_io_mixin.py` (11 行)

133, 138-139, 188, 289-290, 328-330, 356-357

### `graphica/gui/mixins/ui_setup_mixin.py` (6 行)

65-66, 90, 95, 108, 110

### `graphica/gui/motion.py` (31 行)

34, 127, 130, 150-152, 240-249, 251-253, 255-256, 263-269, 445, 455, 462

### `graphica/gui/notify.py` (2 行)

29, 57

### `graphica/gui/panels/__init__.py` (1 行)

42

### `graphica/gui/panels/axis_settings.py` (47 行)

68-71, 75, 119, 168, 212, 272, 279, 304, 412, 477-480, 491-494, 504-507, 510-513, 560, 563, 575-585, 587-592

### `graphica/gui/panels/dataset_tree.py` (5 行)

159, 165, 208, 212, 272

### `graphica/gui/plot_type_drawers.py` (1 行)

124

### `graphica/gui/plugin_context.py` (2 行)

36, 121

### `graphica/gui/plugin_update_flow.py` (24 行)

29, 54-55, 66, 71-73, 77, 85, 96, 98, 104, 116-117, 140-143, 145, 150-152, 163-164

### `graphica/gui/project_files.py` (10 行)

72-73, 85, 199-201, 277-278, 346, 348

### `graphica/gui/rendering/annotations.py` (1 行)

90

### `graphica/gui/rendering/appearance.py` (1 行)

392

### `graphica/gui/rendering/common.py` (1 行)

312

### `graphica/gui/rendering/data_1d.py` (5 行)

54, 181, 266, 330-331

### `graphica/gui/rendering/data_2d.py` (3 行)

27-29

### `graphica/gui/shell/bottom_panel.py` (9 行)

142, 245, 247, 270, 274, 281, 366, 392, 409

### `graphica/gui/shell/fit_result_view.py` (5 行)

31, 66, 153-155

### `graphica/gui/shell/header.py` (3 行)

61-63

### `graphica/gui/shell/inspector.py` (2 行)

165, 168

### `graphica/gui/shell/layout_popover.py` (4 行)

55-57, 59

### `graphica/gui/shell/project_tabs.py` (1 行)

52

### `graphica/gui/shell/rail.py` (3 行)

85, 131, 143

### `graphica/gui/shell/settings_popover.py` (20 行)

47-63, 65, 223-224

### `graphica/gui/shell/side_pages.py` (2 行)

217, 223

### `graphica/gui/shell/subplot_target_bar.py` (5 行)

66, 69-72

### `graphica/gui/single_instance.py` (21 行)

24-28, 52-53, 55-58, 77-81, 97, 104, 114-115, 119

### `graphica/gui/splash.py` (4 行)

80-83

### `graphica/gui/theme.py` (3 行)

1378, 1457, 1709

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

77

### `graphica/gui/updater.py` (2 行)

44-45

### `graphica/gui/widget_translation.py` (2 行)

32, 35

### `graphica/gui/widgets/cards.py` (9 行)

63-71

### `graphica/gui/widgets/eye_toggle.py` (8 行)

41, 48-50, 59-60, 63-64

### `graphica/gui/widgets/segmented.py` (7 行)

79, 158-161, 256-257

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
