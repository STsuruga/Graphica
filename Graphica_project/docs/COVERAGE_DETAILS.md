# テストカバレッジ詳細

計測日: 2026-09-28  
要約は [`COVERAGE.md`](COVERAGE.md)。このファイルも `bash scripts/run_coverage.sh` が自動生成する。
ソースと並べた色付き表示は https://stsuruga.github.io/Graphica/coverage/ (CI が master の push ごとに更新)。

全体: 行 **95.3%** / 分岐 90.3%

## モジュール別

行カバレッジの低い順。「部分分岐」は if の片側しか通っていない分岐の数。

| モジュール | 行数 | 未到達 | 行カバレッジ | 分岐 | 部分分岐 | 分岐カバレッジ |
|---|---:|---:|---:|---:|---:|---:|
| `graphica/__main__.py` | 63 | 46 | 22.7% | 12 | 0 | 0.0% |
| `graphica/plugins/example_plugin/__init__.py` | 15 | 5 | 64.7% | 2 | 1 | 50.0% |
| `graphica/core/color_palettes.py` | 20 | 4 | 73.3% | 10 | 4 | 60.0% |
| `graphica/gui/color_picker_widget.py` | 139 | 32 | 73.3% | 26 | 2 | 53.8% |
| `graphica/gui/single_instance.py` | 101 | 21 | 74.4% | 28 | 8 | 57.1% |
| `graphica/gui/file_association.py` | 67 | 12 | 82.3% | 12 | 2 | 83.3% |
| `graphica/gui/panels/axis_settings.py` | 381 | 44 | 84.4% | 92 | 12 | 67.4% |
| `graphica/gui/datasets/operations/fitting.py` | 240 | 29 | 86.6% | 52 | 4 | 80.8% |
| `graphica/gui/mathtext_preview.py` | 98 | 11 | 87.5% | 22 | 2 | 81.8% |
| `graphica/gui/mixins/ui_setup_mixin.py` | 142 | 8 | 88.3% | 64 | 16 | 75.0% |
| `graphica/core/json_utils.py` | 12 | 1 | 88.9% | 6 | 1 | 83.3% |
| `graphica/core/label_utils.py` | 12 | 1 | 88.9% | 6 | 1 | 83.3% |
| `graphica/gui/tools/__init__.py` | 28 | 2 | 88.9% | 8 | 2 | 75.0% |
| `graphica/gui/tools/region_highlight.py` | 140 | 12 | 88.9% | 50 | 9 | 82.0% |
| `graphica/gui/tools/layout_edit.py` | 177 | 11 | 89.6% | 54 | 13 | 75.9% |
| `graphica/gui/tools/slice_extraction.py` | 110 | 10 | 89.9% | 28 | 4 | 85.7% |
| `graphica/gui/datasets/colors.py` | 138 | 10 | 90.6% | 64 | 5 | 85.9% |
| `graphica/gui/mixins/export_mixin.py` | 364 | 26 | 91.0% | 92 | 13 | 83.7% |
| `graphica/gui/widget_translation.py` | 33 | 2 | 91.0% | 34 | 4 | 88.2% |
| `graphica/gui/dialogs/appearance.py` | 595 | 40 | 91.4% | 94 | 9 | 79.8% |
| `graphica/gui/splash.py` | 60 | 4 | 91.9% | 2 | 1 | 50.0% |
| `graphica/gui/tools/peak_placement.py` | 78 | 6 | 92.3% | 26 | 2 | 92.3% |
| `graphica/gui/main_app_window.py` | 146 | 5 | 92.4% | 38 | 9 | 76.3% |
| `graphica/gui/rendering/data_2d.py` | 37 | 3 | 92.5% | 16 | 1 | 93.8% |
| `graphica/core/excel_utils.py` | 36 | 2 | 92.6% | 18 | 2 | 88.9% |
| `graphica/gui/notify.py` | 28 | 2 | 92.9% | 0 | 0 | — |
| `graphica/core/methods_text.py` | 82 | 6 | 93.0% | 46 | 1 | 93.5% |
| `graphica/core/safe_eval.py` | 128 | 6 | 93.3% | 66 | 7 | 89.4% |
| `graphica/gui/panels/__init__.py` | 22 | 1 | 93.3% | 8 | 1 | 87.5% |
| `graphica/gui/tools/manager.py` | 29 | 1 | 93.3% | 16 | 2 | 87.5% |
| `graphica/gui/datasets/fitting.py` | 45 | 2 | 93.9% | 4 | 1 | 75.0% |
| `graphica/plugin/testing.py` | 18 | 1 | 94.4% | 0 | 0 | — |
| `graphica/gui/tools/cursor.py` | 161 | 6 | 94.6% | 62 | 6 | 90.3% |
| `graphica/gui/tools/range_select.py` | 115 | 5 | 94.6% | 34 | 3 | 91.2% |
| `graphica/core/diagnostics.py` | 58 | 3 | 94.7% | 18 | 1 | 94.4% |
| `graphica/gui/data_editor.py` | 526 | 23 | 94.8% | 144 | 12 | 91.7% |
| `graphica/gui/tools/annotation.py` | 180 | 6 | 94.8% | 70 | 3 | 90.0% |
| `graphica/core/script_export.py` | 162 | 6 | 95.2% | 90 | 6 | 93.3% |
| `graphica/gui/datasets/property_panel.py` | 340 | 9 | 95.4% | 94 | 11 | 88.3% |
| `graphica/gui/workers.py` | 197 | 8 | 95.4% | 64 | 4 | 93.8% |
| `graphica/core/dataset.py` | 265 | 8 | 95.5% | 90 | 8 | 91.1% |
| `graphica/gui/dialogs/data_import.py` | 467 | 18 | 95.5% | 88 | 7 | 92.0% |
| `graphica/gui/panels/dataset_tree.py` | 254 | 5 | 95.6% | 84 | 10 | 88.1% |
| `graphica/gui/minimap_widget.py` | 97 | 5 | 95.8% | 22 | 0 | 100.0% |
| `graphica/gui/dock_layout.py` | 123 | 4 | 95.9% | 22 | 2 | 90.9% |
| `graphica/gui/project_files.py` | 245 | 10 | 96.0% | 78 | 3 | 96.2% |
| `graphica/core/analysis.py` | 736 | 21 | 96.2% | 284 | 18 | 93.7% |
| `graphica/gui/mixins/project_io_mixin.py` | 173 | 6 | 96.3% | 68 | 3 | 95.6% |
| `graphica/gui/data_import_flow.py` | 228 | 5 | 96.4% | 80 | 6 | 92.5% |
| `graphica/gui/datasets/host.py` | 101 | 2 | 96.5% | 14 | 2 | 85.7% |
| `graphica/gui/builders/property_sections.py` | 139 | 3 | 96.5% | 34 | 3 | 91.2% |
| `graphica/gui/menu_bar.py` | 176 | 3 | 96.6% | 60 | 5 | 91.7% |
| `graphica/gui/plugin_context.py` | 80 | 2 | 96.7% | 10 | 1 | 90.0% |
| `graphica/core/plugin_testing.py` | 124 | 5 | 96.7% | 28 | 0 | 100.0% |
| `graphica/core/named_colors.py` | 89 | 2 | 96.7% | 34 | 2 | 94.1% |
| `graphica/core/plugin_install.py` | 46 | 1 | 96.9% | 18 | 1 | 94.4% |
| `graphica/gui/builders/canvas_area.py` | 94 | 3 | 96.9% | 4 | 0 | 100.0% |
| `graphica/gui/rendering/data_1d.py` | 206 | 5 | 96.9% | 88 | 4 | 95.5% |
| `graphica/gui/datasets/order.py` | 209 | 2 | 97.0% | 94 | 7 | 92.6% |
| `graphica/gui/datasets/operations/peaks.py` | 59 | 1 | 97.3% | 14 | 1 | 92.9% |
| `graphica/gui/plot_type_drawers.py` | 63 | 1 | 97.5% | 18 | 1 | 94.4% |
| `graphica/gui/dialogs/app.py` | 590 | 7 | 97.6% | 108 | 10 | 90.7% |
| `graphica/gui/theme.py` | 213 | 3 | 97.7% | 46 | 3 | 93.5% |
| `graphica/gui/mixins/help_mixin.py` | 88 | 1 | 98.1% | 18 | 1 | 94.4% |
| `graphica/core/plugin_api.py` | 221 | 3 | 98.1% | 46 | 2 | 95.7% |
| `graphica/gui/axis_bindings.py` | 48 | 0 | 98.1% | 6 | 1 | 83.3% |
| `graphica/gui/rendering/appearance.py` | 237 | 1 | 98.2% | 90 | 5 | 94.4% |
| `graphica/gui/mixins/quick_access_mixin.py` | 122 | 0 | 98.2% | 42 | 3 | 92.9% |
| `graphica/gui/dialogs/export.py` | 263 | 3 | 98.2% | 20 | 0 | 90.0% |
| `graphica/gui/dialogs/analysis.py` | 885 | 8 | 98.2% | 84 | 9 | 89.3% |
| `graphica/gui/builders/common.py` | 53 | 0 | 98.3% | 6 | 1 | 83.3% |
| `graphica/gui/export_preview_panel.py` | 214 | 0 | 98.5% | 46 | 4 | 91.3% |
| `graphica/models/project.py` | 107 | 1 | 98.5% | 26 | 1 | 96.2% |
| `graphica/gui/main_window.py` | 706 | 6 | 98.6% | 102 | 5 | 95.1% |
| `graphica/gui/binding.py` | 80 | 1 | 99.0% | 22 | 0 | 100.0% |
| `graphica/gui/rendering/common.py` | 178 | 1 | 99.2% | 60 | 1 | 98.3% |
| `graphica/gui/datasets/operations/processing.py` | 370 | 3 | 99.2% | 114 | 1 | 99.1% |
| `graphica/core/fit_models.py` | 222 | 1 | 99.3% | 52 | 1 | 98.1% |
| `graphica/gui/builders/axis_panel.py` | 296 | 0 | 99.4% | 20 | 2 | 90.0% |
| `graphica/gui/canvas.py` | 311 | 0 | 99.5% | 76 | 2 | 97.4% |
| `graphica/gui/datasets/operations/transfer.py` | 144 | 0 | 99.5% | 52 | 1 | 98.1% |
| `graphica/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/assets/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/assets/icons/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/app_paths.py` | 19 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/core/axis_settings.py` | 12 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/core/caption_export.py` | 18 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/core/commands.py` | 141 | 0 | 100.0% | 8 | 0 | 100.0% |
| `graphica/core/cvd_simulation.py` | 16 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/core/grid_data.py` | 70 | 0 | 100.0% | 20 | 0 | 100.0% |
| `graphica/core/i18n.py` | 21 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/core/plugin_context.py` | 21 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/plugin_manifest.py` | 33 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/core/plugin_types.py` | 79 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/provenance.py` | 4 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/report_export.py` | 17 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/core/translations_en.py` | 1 | 0 | 100.0% | 0 | 0 | — |
| `graphica/core/unit_conversion.py` | 24 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/core/update_check.py` | 23 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/core/version.py` | 3 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/app_settings.py` | 78 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/gui/builders/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/builders/dataset_panel.py` | 310 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/gui/color_history.py` | 23 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/gui/crash_handler.py` | 40 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/gui/cvd_preview.py` | 15 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dataset_bindings.py` | 28 | 0 | 100.0% | 2 | 0 | 100.0% |
| `graphica/gui/dataset_style_icon.py` | 43 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/gui/datasets/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/actions_menu.py` | 69 | 0 | 100.0% | 24 | 0 | 100.0% |
| `graphica/gui/datasets/operations/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/operations/runner.py` | 91 | 0 | 100.0% | 14 | 0 | 100.0% |
| `graphica/gui/datasets/overlays.py` | 39 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/gui/datasets/peaks.py` | 13 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/plugin_runs.py` | 65 | 0 | 100.0% | 26 | 0 | 100.0% |
| `graphica/gui/datasets/processing.py` | 44 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/transfer.py` | 23 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/detached_canvas_window.py` | 11 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dialogs/__init__.py` | 7 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dialogs/data_edit.py` | 359 | 0 | 100.0% | 30 | 0 | 100.0% |
| `graphica/gui/export_settings.py` | 7 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/icon_utils.py` | 28 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/mixins/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/provenance_panel.py` | 44 | 0 | 100.0% | 8 | 0 | 100.0% |
| `graphica/gui/rendering/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/rendering/annotations.py` | 113 | 0 | 100.0% | 44 | 0 | 100.0% |
| `graphica/gui/residual_panel.py` | 43 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/resources.py` | 8 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/task_runner.py` | 22 | 0 | 100.0% | 0 | 0 | — |
| `graphica/models/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/plugin/__init__.py` | 6 | 0 | 100.0% | 0 | 0 | — |
| `graphica/sample_data/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |

## 未到達の行

テストで一度も実行されなかった行の番号(パス順)。すべて到達しているモジュールは省略。

### `graphica/__main__.py` (46 行)

26-27, 29-31, 37, 45, 47, 50-51, 53-56, 59, 61-63, 65, 67, 70-71, 73, 75-76, 78-81, 83-84, 86, 88-90, 92, 95-98, 100-103, 105, 107

### `graphica/core/analysis.py` (21 行)

150, 300, 306, 311, 315, 318, 420, 447, 460, 576, 656, 715, 1099, 1103, 1202, 1209-1210, 1272-1275

### `graphica/core/color_palettes.py` (4 行)

38, 42, 44, 46

### `graphica/core/dataset.py` (8 行)

301, 303, 403-404, 415-416, 442-443

### `graphica/core/diagnostics.py` (3 行)

39-40, 51

### `graphica/core/excel_utils.py` (2 行)

36, 48

### `graphica/core/fit_models.py` (1 行)

94

### `graphica/core/json_utils.py` (1 行)

24

### `graphica/core/label_utils.py` (1 行)

20

### `graphica/core/methods_text.py` (6 行)

68-72, 76

### `graphica/core/named_colors.py` (2 行)

99, 120

### `graphica/core/plugin_api.py` (3 行)

389, 415-416

### `graphica/core/plugin_install.py` (1 行)

62

### `graphica/core/plugin_testing.py` (5 行)

161, 183, 189, 207, 213

### `graphica/core/safe_eval.py` (6 行)

82, 88, 97, 107, 136, 147

### `graphica/core/script_export.py` (6 行)

21-22, 164, 166, 173, 236

### `graphica/gui/binding.py` (1 行)

93

### `graphica/gui/builders/canvas_area.py` (3 行)

167-169

### `graphica/gui/builders/property_sections.py` (3 行)

174, 190, 194

### `graphica/gui/color_picker_widget.py` (32 行)

52, 91-92, 95-96, 98-99, 101-102, 104-106, 108-114, 117, 129-135, 140, 142, 162-164

### `graphica/gui/data_editor.py` (23 行)

560-563, 568, 581-582, 590-593, 601-602, 604-605, 607-608, 647-648, 654-655, 668, 702

### `graphica/gui/data_import_flow.py` (5 行)

260, 265, 285-287

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

348, 549-550

### `graphica/gui/datasets/order.py` (2 行)

35, 161

### `graphica/gui/datasets/property_panel.py` (9 行)

73, 388, 408, 411-412, 434, 452, 504-505

### `graphica/gui/dialogs/analysis.py` (8 行)

247, 380-383, 558-559, 1226

### `graphica/gui/dialogs/app.py` (7 行)

285-286, 294-295, 735-736, 804

### `graphica/gui/dialogs/appearance.py` (40 行)

201, 221, 226-229, 394, 523, 527, 534, 538-540, 544-549, 551-559, 564-565, 568-570, 576, 579-580, 699-701, 731

### `graphica/gui/dialogs/data_import.py` (18 行)

32, 89-90, 98-100, 103-105, 117, 273, 326-328, 389-390, 612-613

### `graphica/gui/dialogs/export.py` (3 行)

360, 363-364

### `graphica/gui/dock_layout.py` (4 行)

126-128, 171

### `graphica/gui/file_association.py` (12 行)

16-17, 52-53, 58-63, 76, 88

### `graphica/gui/main_app_window.py` (5 行)

85-86, 145, 151, 170

### `graphica/gui/main_window.py` (6 行)

29, 583-584, 595-596, 1039

### `graphica/gui/mathtext_preview.py` (11 行)

42, 80-83, 98-102, 104

### `graphica/gui/menu_bar.py` (3 行)

232, 269, 301

### `graphica/gui/minimap_widget.py` (5 行)

128-130, 142, 144

### `graphica/gui/mixins/export_mixin.py` (26 行)

100-101, 105-106, 175-177, 188, 227, 241-243, 254, 264-267, 271, 283-285, 426-427, 474, 488-489

### `graphica/gui/mixins/help_mixin.py` (1 行)

74

### `graphica/gui/mixins/project_io_mixin.py` (6 行)

144, 242-244, 270-271

### `graphica/gui/mixins/ui_setup_mixin.py` (8 行)

64-65, 85, 90, 105, 107, 128, 132

### `graphica/gui/notify.py` (2 行)

29, 57

### `graphica/gui/panels/__init__.py` (1 行)

42

### `graphica/gui/panels/axis_settings.py` (44 行)

65-68, 72, 102, 151, 193, 336, 392-395, 406-409, 419-422, 425-428, 476, 479, 491-501, 503-508

### `graphica/gui/panels/dataset_tree.py` (5 行)

155, 161, 192, 196, 256

### `graphica/gui/plot_type_drawers.py` (1 行)

113

### `graphica/gui/plugin_context.py` (2 行)

33, 97

### `graphica/gui/project_files.py` (10 行)

69-70, 82, 193-195, 269-270, 335, 337

### `graphica/gui/rendering/appearance.py` (1 行)

359

### `graphica/gui/rendering/common.py` (1 行)

293

### `graphica/gui/rendering/data_1d.py` (5 行)

50, 166, 250, 314-315

### `graphica/gui/rendering/data_2d.py` (3 行)

27-29

### `graphica/gui/single_instance.py` (21 行)

24-28, 52-53, 55-58, 77-81, 97, 104, 114-115, 119

### `graphica/gui/splash.py` (4 行)

80-83

### `graphica/gui/theme.py` (3 行)

627, 688, 795

### `graphica/gui/tools/__init__.py` (2 行)

44, 55

### `graphica/gui/tools/annotation.py` (6 行)

186-190, 240

### `graphica/gui/tools/cursor.py` (6 行)

62, 74, 185, 224, 258-259

### `graphica/gui/tools/layout_edit.py` (11 行)

52-53, 87, 91, 111, 167, 196, 201, 227, 233, 272

### `graphica/gui/tools/manager.py` (1 行)

71

### `graphica/gui/tools/peak_placement.py` (6 行)

61, 111, 118-119, 128-129

### `graphica/gui/tools/range_select.py` (5 行)

76-77, 127, 150, 181

### `graphica/gui/tools/region_highlight.py` (12 行)

85-86, 94, 106, 124-125, 137, 144, 157, 183, 192, 196

### `graphica/gui/tools/slice_extraction.py` (10 行)

84-85, 114, 122, 140, 158-159, 166-168

### `graphica/gui/widget_translation.py` (2 行)

32, 35

### `graphica/gui/workers.py` (8 行)

39, 72, 98-99, 208-209, 253-254

### `graphica/models/project.py` (1 行)

46

### `graphica/plugin/testing.py` (1 行)

57

### `graphica/plugins/example_plugin/__init__.py` (5 行)

15, 19-20, 26-27
