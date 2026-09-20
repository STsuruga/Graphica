# テストカバレッジ詳細

計測日: 2026-09-20  
要約は [`COVERAGE.md`](COVERAGE.md)。このファイルも `bash scripts/run_coverage.sh` が自動生成する。
ソースと並べた色付き表示は https://stsuruga.github.io/Graphica/coverage/ (CI が master の push ごとに更新)。

全体: 行 **93.8%** / 分岐 89.2%

## モジュール別

行カバレッジの低い順。「部分分岐」は if の片側しか通っていない分岐の数。

| モジュール | 行数 | 未到達 | 行カバレッジ | 分岐 | 部分分岐 | 分岐カバレッジ |
|---|---:|---:|---:|---:|---:|---:|
| `graphica/plugins/example_plugin/__init__.py` | 15 | 8 | 41.2% | 2 | 0 | 0.0% |
| `graphica/__main__.py` | 39 | 21 | 41.9% | 4 | 0 | 0.0% |
| `graphica/core/color_palettes.py` | 16 | 4 | 69.2% | 10 | 4 | 60.0% |
| `graphica/gui/color_picker_widget.py` | 138 | 32 | 73.2% | 26 | 2 | 53.8% |
| `graphica/gui/dialogs/analysis.py` | 880 | 210 | 75.5% | 84 | 4 | 69.0% |
| `graphica/gui/menu_bar.py` | 176 | 25 | 82.2% | 60 | 5 | 71.7% |
| `graphica/gui/datasets/fitting.py` | 255 | 39 | 82.9% | 72 | 11 | 76.4% |
| `graphica/gui/mathtext_preview.py` | 72 | 10 | 84.1% | 10 | 1 | 70.0% |
| `graphica/gui/mixins/settings_mixin.py` | 503 | 45 | 87.1% | 96 | 14 | 66.7% |
| `graphica/gui/mixins/region_highlight_mixin.py` | 129 | 12 | 88.3% | 50 | 9 | 82.0% |
| `graphica/core/json_utils.py` | 12 | 1 | 88.9% | 6 | 1 | 83.3% |
| `graphica/core/label_utils.py` | 12 | 1 | 88.9% | 6 | 1 | 83.3% |
| `graphica/gui/mixins/slice_extraction_mixin.py` | 98 | 10 | 88.9% | 28 | 4 | 85.7% |
| `graphica/gui/mixins/layout_edit_mixin.py` | 167 | 11 | 89.1% | 54 | 13 | 75.9% |
| `graphica/gui/mixins/export_mixin.py` | 362 | 28 | 89.9% | 92 | 14 | 80.4% |
| `graphica/gui/datasets/colors.py` | 137 | 10 | 90.5% | 64 | 5 | 85.9% |
| `graphica/gui/datasets/transfer.py` | 152 | 14 | 91.0% | 60 | 5 | 91.7% |
| `graphica/core/safe_eval.py` | 98 | 6 | 91.3% | 52 | 7 | 86.5% |
| `graphica/gui/dialogs/appearance.py` | 549 | 36 | 91.7% | 92 | 9 | 81.5% |
| `graphica/gui/mixins/peak_placement_mixin.py` | 71 | 6 | 91.8% | 26 | 2 | 92.3% |
| `graphica/core/excel_utils.py` | 36 | 2 | 92.6% | 18 | 2 | 88.9% |
| `graphica/core/methods_text.py` | 81 | 6 | 92.9% | 46 | 1 | 93.5% |
| `graphica/gui/mixins/ui_setup_mixin.py` | 294 | 8 | 93.1% | 68 | 17 | 75.0% |
| `graphica/gui/mixins/mouse_mode_mixin.py` | 28 | 1 | 93.2% | 16 | 2 | 87.5% |
| `graphica/gui/main_app_window.py` | 121 | 3 | 93.2% | 26 | 7 | 73.1% |
| `graphica/gui/datasets/processing.py` | 576 | 36 | 93.8% | 192 | 12 | 93.8% |
| `graphica/gui/minimap_widget.py` | 97 | 6 | 94.1% | 22 | 1 | 95.5% |
| `graphica/gui/mixins/range_select_mixin.py` | 105 | 5 | 94.2% | 34 | 3 | 91.2% |
| `graphica/gui/mixins/cursor_mixin.py` | 151 | 6 | 94.4% | 62 | 6 | 90.3% |
| `graphica/gui/workers.py` | 97 | 4 | 94.4% | 28 | 3 | 89.3% |
| `graphica/gui/plugin_context.py` | 80 | 4 | 94.4% | 10 | 1 | 90.0% |
| `graphica/plugin/testing.py` | 18 | 1 | 94.4% | 0 | 0 | — |
| `graphica/core/diagnostics.py` | 58 | 3 | 94.7% | 18 | 1 | 94.4% |
| `graphica/gui/data_editor.py` | 525 | 23 | 94.8% | 144 | 12 | 91.7% |
| `graphica/core/script_export.py` | 151 | 6 | 94.8% | 80 | 6 | 92.5% |
| `graphica/core/dataset.py` | 265 | 9 | 94.9% | 90 | 9 | 90.0% |
| `graphica/gui/mixins/project_io_mixin.py` | 183 | 7 | 95.3% | 74 | 5 | 93.2% |
| `graphica/gui/dialogs/data_import.py` | 419 | 14 | 95.9% | 72 | 6 | 91.7% |
| `graphica/core/analysis.py` | 916 | 27 | 96.0% | 368 | 22 | 93.5% |
| `graphica/gui/datasets/property_panel.py` | 447 | 9 | 96.3% | 94 | 11 | 88.3% |
| `graphica/gui/datasets/host.py` | 98 | 2 | 96.4% | 14 | 2 | 85.7% |
| `graphica/gui/mixins/dataset_mixin.py` | 253 | 3 | 96.6% | 104 | 9 | 91.3% |
| `graphica/core/plugin_testing.py` | 124 | 5 | 96.7% | 28 | 0 | 100.0% |
| `graphica/core/named_colors.py` | 89 | 2 | 96.7% | 34 | 2 | 94.1% |
| `graphica/gui/main_window.py` | 2,078 | 44 | 96.8% | 420 | 37 | 91.2% |
| `graphica/core/plugin_install.py` | 46 | 1 | 96.9% | 18 | 1 | 94.4% |
| `graphica/gui/plot_type_drawers.py` | 63 | 1 | 97.5% | 18 | 1 | 94.4% |
| `graphica/gui/theme.py` | 213 | 3 | 97.7% | 46 | 3 | 93.5% |
| `graphica/gui/dialogs/app.py` | 542 | 3 | 97.8% | 104 | 11 | 89.4% |
| `graphica/gui/datasets/peaks.py` | 78 | 1 | 98.0% | 22 | 1 | 95.5% |
| `graphica/gui/mixins/help_mixin.py` | 87 | 1 | 98.1% | 18 | 1 | 94.4% |
| `graphica/core/plugin_api.py` | 221 | 3 | 98.1% | 46 | 2 | 95.7% |
| `graphica/gui/dialogs/export.py` | 260 | 3 | 98.2% | 18 | 0 | 88.9% |
| `graphica/gui/mixins/quick_access_mixin.py` | 125 | 0 | 98.2% | 44 | 3 | 93.2% |
| `graphica/gui/mixins/annotation_mixin.py` | 129 | 1 | 98.3% | 52 | 2 | 96.2% |
| `graphica/gui/canvas.py` | 960 | 10 | 98.4% | 352 | 11 | 96.9% |
| `graphica/gui/export_preview_panel.py` | 211 | 0 | 98.4% | 44 | 4 | 90.9% |
| `graphica/models/project.py` | 142 | 1 | 98.9% | 32 | 1 | 96.9% |
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
| `graphica/gui/color_history.py` | 23 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/gui/crash_handler.py` | 39 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/gui/cvd_preview.py` | 15 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dataset_style_icon.py` | 43 | 0 | 100.0% | 6 | 0 | 100.0% |
| `graphica/gui/datasets/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/datasets/actions_menu.py` | 68 | 0 | 100.0% | 24 | 0 | 100.0% |
| `graphica/gui/datasets/overlays.py` | 38 | 0 | 100.0% | 10 | 0 | 100.0% |
| `graphica/gui/datasets/plugin_runs.py` | 64 | 0 | 100.0% | 26 | 0 | 100.0% |
| `graphica/gui/detached_canvas_window.py` | 11 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dialogs/__init__.py` | 7 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/dialogs/data_edit.py` | 354 | 0 | 100.0% | 30 | 0 | 100.0% |
| `graphica/gui/export_settings.py` | 7 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/icon_utils.py` | 28 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/mixins/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/gui/provenance_panel.py` | 44 | 0 | 100.0% | 8 | 0 | 100.0% |
| `graphica/gui/residual_panel.py` | 43 | 0 | 100.0% | 4 | 0 | 100.0% |
| `graphica/gui/task_runner.py` | 22 | 0 | 100.0% | 0 | 0 | — |
| `graphica/models/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |
| `graphica/plugin/__init__.py` | 6 | 0 | 100.0% | 0 | 0 | — |
| `graphica/sample_data/__init__.py` | 0 | 0 | 100.0% | 0 | 0 | — |

## 未到達の行

テストで一度も実行されなかった行の番号(パス順)。すべて到達しているモジュールは省略。

### `graphica/__main__.py` (21 行)

25-26, 28-30, 36, 44, 46, 49-50, 52-55, 57, 60, 62, 65, 67-68, 70

### `graphica/core/analysis.py` (27 行)

33, 219, 267, 324, 429-430, 432, 526, 532, 537, 541, 544, 646, 673, 686, 802, 882, 941, 1325, 1329, 1428, 1435-1436, 1498-1501

### `graphica/core/color_palettes.py` (4 行)

38, 42, 44, 46

### `graphica/core/dataset.py` (9 行)

117, 301, 303, 403-404, 415-416, 442-443

### `graphica/core/diagnostics.py` (3 行)

39-40, 51

### `graphica/core/excel_utils.py` (2 行)

36, 48

### `graphica/core/json_utils.py` (1 行)

24

### `graphica/core/label_utils.py` (1 行)

20

### `graphica/core/methods_text.py` (6 行)

65-69, 73

### `graphica/core/named_colors.py` (2 行)

99, 120

### `graphica/core/plugin_api.py` (3 行)

389, 415-416

### `graphica/core/plugin_install.py` (1 行)

62

### `graphica/core/plugin_testing.py` (5 行)

161, 183, 189, 207, 213

### `graphica/core/safe_eval.py` (6 行)

79, 85, 94, 104, 133, 144

### `graphica/core/script_export.py` (6 行)

21-22, 152, 154, 161, 224

### `graphica/gui/canvas.py` (10 行)

287, 814-815, 896-898, 968, 1080, 1161, 1569

### `graphica/gui/color_picker_widget.py` (32 行)

51, 90-91, 94-95, 97-98, 100-101, 103-105, 107-113, 116, 128-134, 139, 141, 161-163

### `graphica/gui/data_editor.py` (23 行)

559-562, 567, 580-581, 589-592, 600-601, 603-604, 606-607, 646-647, 653-654, 667, 701

### `graphica/gui/datasets/colors.py` (10 行)

53, 62, 93, 114-120

### `graphica/gui/datasets/fitting.py` (39 行)

72-73, 138-147, 152-155, 157-158, 163-170, 187-188, 208-209, 268-269, 300-301, 314, 434-435, 438-439

### `graphica/gui/datasets/host.py` (2 行)

55, 65

### `graphica/gui/datasets/peaks.py` (1 行)

114

### `graphica/gui/datasets/processing.py` (36 行)

89-90, 100, 102, 104, 109-110, 182, 186, 203-205, 480, 484-485, 497-499, 549, 598, 602, 641-642, 666-668, 707-709, 761-763, 804-806, 828

### `graphica/gui/datasets/property_panel.py` (9 行)

71, 536, 556, 559-560, 582, 600, 652-653

### `graphica/gui/datasets/transfer.py` (14 行)

50, 71, 73, 85-88, 106-107, 110, 200-203

### `graphica/gui/dialogs/analysis.py` (210 行)

259, 391-394, 569-570, 599-602, 604-605, 607-611, 613-614, 616-633, 635-645, 647-649, 653-656, 658-672, 676-679, 681, 683-686, 688-689, 691, 693-695, 697, 704-707, 712-714, 718-720, 722-723, 727, 807-809, 811-812, 814-817, 819-824, 826-832, 834, 837, 845, 847, 850-851, 853, 855-857, 859, 863-866, 986-989, 991-992, 994-998, 1000-1001, 1003-1008, 1010-1014, 1016-1023, 1025-1030, 1032-1036, 1038-1040, 1042-1046, 1048-1049, 1056, 1058-1061, 1063, 1065-1067, 1069, 1076-1079, 1081-1082, 1087-1089, 1237

### `graphica/gui/dialogs/app.py` (3 行)

682-683, 751

### `graphica/gui/dialogs/appearance.py` (36 行)

201, 221, 226-229, 394, 523, 527, 534, 538-540, 544-549, 551-559, 564-565, 568-570, 576, 579-580

### `graphica/gui/dialogs/data_import.py` (14 行)

73-74, 82-84, 87-89, 101, 244, 332-333, 542-543

### `graphica/gui/dialogs/export.py` (3 行)

357, 360-361

### `graphica/gui/main_app_window.py` (3 行)

82-83, 136

### `graphica/gui/main_window.py` (44 行)

35, 1652, 1655-1657, 1696, 1724, 1732-1740, 1824-1825, 1837, 1879, 1885, 1888, 1972-1974, 2041-2042, 2412, 2428, 2432, 2579, 2582, 2758, 2760, 2966, 2971, 2990-2992, 3069-3071, 3122, 3124

### `graphica/gui/mathtext_preview.py` (10 行)

37-40, 55-59, 61

### `graphica/gui/menu_bar.py` (25 行)

232, 269, 274-287, 290-297, 301

### `graphica/gui/minimap_widget.py` (6 行)

128-130, 132, 142, 144

### `graphica/gui/mixins/annotation_mixin.py` (1 行)

171

### `graphica/gui/mixins/cursor_mixin.py` (6 行)

43, 55, 166, 205, 239-240

### `graphica/gui/mixins/dataset_mixin.py` (3 行)

154, 160, 271

### `graphica/gui/mixins/export_mixin.py` (28 行)

99-100, 104-105, 174-176, 187, 226, 240-242, 253, 263-266, 270, 282-284, 366-367, 423-424, 471, 485-486

### `graphica/gui/mixins/help_mixin.py` (1 行)

73

### `graphica/gui/mixins/layout_edit_mixin.py` (11 行)

30-31, 65, 69, 89, 145, 174, 179, 205, 211, 250

### `graphica/gui/mixins/mouse_mode_mixin.py` (1 行)

68

### `graphica/gui/mixins/peak_placement_mixin.py` (6 行)

45, 95, 102-103, 112-113

### `graphica/gui/mixins/project_io_mixin.py` (7 行)

160, 257, 267-269, 295-296

### `graphica/gui/mixins/range_select_mixin.py` (5 行)

56-57, 107, 130, 161

### `graphica/gui/mixins/region_highlight_mixin.py` (12 行)

63-64, 72, 84, 102-103, 115, 122, 135, 161, 170, 174

### `graphica/gui/mixins/settings_mixin.py` (45 行)

75-78, 82, 88, 137, 179, 284, 291, 338-341, 352-355, 365-368, 371-374, 422, 425, 437-447, 449-454

### `graphica/gui/mixins/slice_extraction_mixin.py` (10 行)

63-64, 93, 101, 119, 137-138, 145-147

### `graphica/gui/mixins/ui_setup_mixin.py` (8 行)

268-269, 289, 294, 309, 311, 332, 336

### `graphica/gui/plot_type_drawers.py` (1 行)

113

### `graphica/gui/plugin_context.py` (4 行)

33, 91, 94, 97

### `graphica/gui/theme.py` (3 行)

627, 688, 795

### `graphica/gui/workers.py` (4 行)

35, 68, 94-95

### `graphica/models/project.py` (1 行)

77

### `graphica/plugin/testing.py` (1 行)

57

### `graphica/plugins/example_plugin/__init__.py` (8 行)

15, 19-20, 24-28
