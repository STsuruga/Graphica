# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This repo root contains only `README.md` (user-facing manual, Japanese) and the actual application, which lives entirely under `Graphica_project/`. Always treat `Graphica_project/` as the working root for commands below. Two stale PyInstaller `.spec` files exist at the repo root (`Graphica_ver1.spec`, `main_ver6.spec`) referencing entry points that no longer exist (`Graphica_ver1.py`, `main_ver6.py`) — they predate the current `Graphica_project/` layout and should not be relied on for packaging guidance.

## Commands

All commands assume `cwd = Graphica_project/`.

```bash
pip install -r requirements.txt   # installs PySide6, matplotlib, numpy, pandas, scipy, openpyxl, pytest
python main.py                    # run the app
python main.py --safe-mode        # start with plugins disabled and the saved dock layout ignored
pytest tests/test_dataset.py      # run a single test file
pytest tests/test_dataset.py::test_name -v   # run a single test
pytest tests/test_dataset.py -k waterfall    # run a filtered subset
bash scripts/run_tests_chunked.sh            # the ONLY supported way to run the whole suite
```

**Do not run bare `pytest` over the whole suite** — a single process degrades until it never finishes (see "Full-suite execution" below). Always use `scripts/run_tests_chunked.sh`.

`tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` and provides a session-scoped, autouse `QApplication` fixture, so the suite runs headless with no display and no manual env var needed — this matters because several `core/`/`models/` classes (`core/commands.py`'s `QUndoCommand` subclasses, `models/project.py`'s `ProjectModel`) are `QObject`s and cannot be instantiated without a live `QApplication`.

There is no configured linter/formatter in this repo (no `.flake8`, `pyproject.toml`, or `.pylintrc`) — match the surrounding code's style rather than introducing a new tool.

## Architecture

### Entry point and window hierarchy

`main.py` installs a crash handler (`gui/crash_handler.py`, writes to `graphica.log` and shows a recovery dialog on unhandled exceptions) and creates a single `MainAppWindow` (`gui/main_app_window.py`). `MainAppWindow` owns a `QTabWidget` where **each tab is a complete, independent `PlotterApp` instance** — not a shared-state view. This is a deliberate architecture choice: rather than making the mixins "tab-aware," every tab gets its own full `QMainWindow` (menu bar, docks, undo stack, canvas, project). Only the first tab (`run_startup_checks=True, tab_id=None`) performs autosave-recovery checks, first-launch welcome, and `clean_exit` QSettings tracking; additional tabs (`tab_id=2, 3, ...`) skip these and get uniquely-named autosave files (`autosave_tab{N}.graphica`) to avoid collisions.

### `PlotterApp` mixin composition

`gui/main_window.py`'s `PlotterApp(QMainWindow, ...)` composes its behavior from **15 mixins** under `gui/mixins/`, each owning one concern:

- `UISetupMixin` — one-time signal wiring (`_connect_signals`), menu bar construction, and `_collect_menu_actions()` (backs the command palette / quick access / shortcuts list)
- `SettingsMixin` — collecting/applying the UI ↔ per-axis settings dict, font/color pickers, axis behavior
- `DatasetMixin` — dataset add/remove/duplicate/property editing, curve fitting, peak detection, and the ~30-item dataset context menu (data processing, analysis, batch operations)
- `ExportMixin` — image/PDF/SVG export, batch export, the live export-preview panel, CVD preview, LaTeX captions, HTML/PDF reports
- `ProjectIOMixin` — project save/load menu actions and format templates
- `HelpMixin` — help dialogs and the update check
- `QuickAccessMixin` — the pinnable quick-access toolbar
- `MouseModeMixin` — the registry (`MOUSE_MODES`) and `_deactivate_other_mouse_modes()` that keep the seven mouse modes below mutually exclusive
- Seven **mutually exclusive mouse-interaction modes**, one mixin each: `CursorMixin` (data cursor), `AnnotationMixin` (text/arrow annotations), `LayoutEditMixin` (free-form subplot drag), `RangeSelectMixin` (drag to mask an X range), `PeakPlacementMixin` (click to seed multi-peak fit guesses), `SliceExtractionMixin` (drag a 1D slice out of a 2D map), `RegionHighlightMixin` (drag to add a vspan/hspan)

**The seven mouse modes are kept exclusive through a single registry** (`gui/mixins/mouse_mode_mixin.py`). Each mode's `_toggle_*_mode(checked)` calls `self._deactivate_other_mouse_modes('<name>')` on the `checked=True` branch and nothing else; the registry's `MOUSE_MODES` tuple maps each mode name to its flag attribute, its `QAction` attribute, and its toggle method. **Adding an eighth mode means adding one `MouseMode(...)` row to that tuple** — do not reintroduce per-mixin if-chains. Note that the `QAction`s are connected to `triggered`, not `toggled`, so `setChecked(False)` alone does not fire the slot; deactivation must both uncheck the action and call `_toggle_*_mode(False)` (the registry does both). This replaced 42 hand-written branches spread across seven files, in which two modes (`AnnotationMixin` and `CursorMixin`) had silently omitted `LayoutEditMixin` and could therefore be active simultaneously with it; `tests/test_mouse_modes.py` now asserts all 42 ordered pairs.

`PlotterApp.__init__` itself is long and split into numbered sections (UI file load → dynamic widget construction → dynamic layout surgery → signal connection → menu bar → initial state) — when adding a new always-visible control, follow the existing section it belongs to rather than appending at the end, since later sections depend on earlier ones (e.g. `_connect_signals()` must run after all dynamically-created widgets exist).

### Designer-generated UI vs. runtime-constructed UI

`ui_main_window.py` (repo root of `Graphica_project/`, not under `gui/`) is generated by Qt Designer/`pyside6-uic` and is **never hand-edited** — its header says as much. Any UI element not present in the `.ui` file (which is most of the app's functionality, added incrementally) is constructed at runtime in `gui/main_window.py`, using one of two patterns depending on whether the target widget already exists in `ui_main_window.py`:

- **New widget, no Designer counterpart**: just instantiate and `addWidget`/`insertRow` into an existing Designer-created layout (e.g. `self.ui.formLayout_3.insertRow(...)`).
- **Replacing a Designer-created widget in place**: use `layout.replaceWidget(old_widget, new_wrapper)` so the widget's position/row index is preserved and later hard-coded `insertRow(N, ...)` calls elsewhere in `__init__` don't need renumbering. Used for swapping the dataset list `QListWidget` → `QTreeWidget` (`_replace_dataset_list_with_tree`), the color swatch button → `ColorPickerWidget`, and the title/axis-label `QLineEdit`s → line-edit-plus-format-menu-button wrappers. Because `QFormLayout` gives every row in a layout the *same* label-column and field-column width, adding a wider widget to any one row can force horizontal overflow across the whole form — check `CONTROL_DOCK_WIDTH` headroom (in `gui/main_window.py`) after adding anything to `formLayout_3`.

When inserting into a `QFormLayout`/`QGridLayout` with **numbered** `insertRow`/`addWidget(row, col)` calls elsewhere in the same method, trace through the existing insert order carefully before adding a new numbered insert — they're position-dependent on each other executing in sequence, and getting the order wrong silently misplaces unrelated fields rather than raising an error.

### Core data/undo layer (`core/`)

- `core/dataset.py` — `Dataset` dataclass holding one plot's data + style. All data-consuming properties (`x_data`, `y_data`, `x_err_data`, `y_err_data`) route through the `visible_df` property, which filters out `masked_row_indices` (non-destructive outlier exclusion) — any new code that maps a plotted-point index back to a dataframe row must index into `visible_df`, not `df`, or it will misalign once any row is masked.
- `core/commands.py` — all `QUndoCommand` subclasses (cell edits, row/column add/delete, dataset property changes, mask toggling, annotation changes, dataset reordering, column rename). Commands mutate `Dataset`/`ProjectModel` directly and know nothing about GUI widgets; GUI mixins push commands onto `self.undo_stack` and re-render afterward.
- `core/analysis.py` — the analysis workhorse (~2,100 lines, scipy-based): curve fitting (many models, fixed/bounded parameters, confidence/prediction bands), peak detection and quantification, baseline correction, smoothing, interval/cumulative integration, normalization, resampling/interpolation, outlier detection, duplicate-X averaging, peak-label collision avoidance.
- `core/excel_utils.py` — Excel-specific helpers (unevaluated-formula detection, multi-sheet handling).
- `core/i18n.py` / `core/translations_en.py` — a deliberately minimal translation layer (not Qt Linguist): `tr(japanese_text)` looks up `japanese_text` as a dict key in the active language's dict, falling back to the original string if untranslated. `set_language()` takes effect only on next launch — there is no live re-translation of already-built widgets. Scope is main UI (menus, buttons, key dialogs), not exhaustive.
- `core/app_paths.py` — writable per-user directories (`%LOCALAPPDATA%\Graphica`): the log file and the user plugins folder. Distinct from `resource_path()`, which resolves read-only bundled resources. Anything the app must *write* goes here, never next to the executable (an install under `Program Files` is read-only).
- Other `core/` modules worth knowing before adding a new one (27 total): `safe_eval.py` (sandboxed expression evaluation for column calculations), `script_export.py` (generates a standalone numpy+matplotlib script — deliberately scipy-free, so plot types that need scipy fall back to `Line`), `methods_text.py` / `report_export.py` / `caption_export.py` (provenance → prose → HTML/PDF/LaTeX output), `grid_data.py` (2D map gridding), `unit_conversion.py`, `color_palettes.py`, `cvd_simulation.py`, `update_check.py`, `plugin_*.py` (see below).
- `models/project.py` — `ProjectModel` (the full document: datasets, per-axis settings, layout). Two save formats: legacy `.pkl` (pickle) and the current `.graphica` (JSON, with `format_version` + a `_MIGRATIONS` chain; a file from a *newer* version is rejected outright rather than silently half-read). Pickle loading uses a `_RestrictedUnpickler` allowlisting only `numpy`, `pandas`, and `core.dataset` — intentional protection against arbitrary code execution from a crafted `.pkl`; do not widen the allowlist without equivalent scrutiny. `ProjectModel` is a `QObject` and exposes a `changed` signal plus `notify_changed()` (item C-005): the ~38 existing call sites still call `PlotterApp._update_plot()` directly and were deliberately left alone, so the signal is currently emitted by nobody — it exists so *new* mutation paths can trigger a redraw without knowing that method name.
- **Adding a field to `Dataset` or `ProjectModel`**: both pickle (`__getstate__`/`__setstate__`) and JSON (`to_dict`/`from_dict`) iterate `dataclasses.fields()` generically and backfill anything missing from the dataclass default. A new field therefore needs **no serialization code** — but it MUST have a default that reproduces the old behavior, or every existing saved project changes meaning on load.

### Plugin API (`core/plugin_api.py`) — gotchas not obvious from the code itself

`GraphicaPluginAPI` is the sole surface plugins touch. It now has **nine** extension points: `register_fit_function` (backed by `core/analysis.py`'s `_PLUGIN_FIT_FUNCTIONS`), `register_menu_action`, `register_importer`, `register_exporter`, `register_processor`, `register_analyzer`, `register_panel`, `register_plot_type`, `register_render_backend`. Before adding a tenth, know these:

- **How plugins are found and installed.** `gui/main_window.py`'s `plugin_search_paths()` returns two directories: `resource_path("plugins")` (**only when running from source** — the bundled `plugins/example_plugin/` sample) and `core/app_paths.py`'s `get_user_plugins_dir()` = `%LOCALAPPDATA%\Graphica\plugins`, which always exists and is always writable. Users install plugins as **zip files** through the preferences dialog's 「プラグインをインストール...」 button, which calls `core/plugin_install.py`'s `install_plugin_zip()` (validates the manifest, rejects path traversal, extracts into the user plugins dir). Do not reintroduce a path based on `sys._MEIPASS` or `sys.executable` — an installed exe under `Program Files` is read-only.
- **Every plugin needs a `plugin.json` manifest.** `core/plugin_manifest.py` requires `name`, `version`, and `api_version`, and validates `api_version` against `PLUGIN_API_VERSION` (currently `"1.0"`); a mismatch or a malformed manifest means the plugin's code is never imported at all. The `entry_point` key that appears in sample manifests is reserved for future use and is currently ignored — the loader always calls `register(api)` in the package's `__init__.py`. **Bump `PLUGIN_API_VERSION` when you make a breaking change to `GraphicaPluginAPI`.**
- **The registry is process-wide, not per-tab.** `load_plugins_once()` loads and calls every plugin's `register()` exactly once per process and caches the resulting `GraphicaPluginAPI`; `core/analysis.py`'s fit-function dict is a plain module-level dict with the same lifetime. Any new `register_xxx` you add inherits this: calling it twice with the same name is expected to collide/error, and there is no per-tab-scoped variant. Don't design a new extension point that assumes "each tab gets its own registration."
- **Don't capture `self._main_window` from `GraphicaPluginAPI.__init__` for anything user-facing.** It's set once, from whichever `PlotterApp` happened to trigger the first (and only) `load_plugins_once()` call. The *correct* pattern — already used by `register_menu_action` — is that the callback receives the currently-active `PlotterApp` as an argument **at invocation time** (see `plugins/example_plugin/__init__.py`'s `_show_dataset_point_count(main_window)`), not at registration time. A new extension point that reads `self._main_window` instead would silently always operate on the first tab ever opened, in a multi-tab session.
- **A broken plugin fails silently in the app.** `PluginManager.load_all()` wraps each plugin's `register(api)` call in a blanket `except Exception`, logs via `logger.exception`, and moves on — no dialog, no crash. While developing an extension point, watch `graphica.log` rather than assuming a quiet plugin means a working one.
- **Everything is synchronous on the GUI thread.** Every extension point assumes the plugin's code runs quickly and blocks the UI thread while it does. A plugin-provided renderer or anything else with real latency (e.g. a first-call LaTeX engine spin-up) will freeze the app; there is no async/progress scaffolding to build on.
- **Mirror new extension points into `core/plugin_testing.py`.** `FakeGraphicaPluginAPI` is what plugin authors unit-test against, and it deliberately reproduces the real duplicate-registration `ValueError` — a Fake that silently accepts what the real API rejects lets plugin authors ship a bug their own tests pass.

### Rendering (`gui/canvas.py`)

`MplCanvas` owns the matplotlib `Figure`/`Axes` and does all drawing (`_draw_data`, `_apply_appearance`). Notable non-obvious behavior: `ax.set_xscale(...)` resets that axis's Locator/Formatter to scale defaults even when set to its current value, so category-axis and date-axis code paths must skip calling it entirely rather than calling it with the "same" value.

**Three redraw paths, in decreasing cost** (item C-003 split them; pick the cheapest one whose preconditions hold):

- `redraw_all()` — `fig.clf()` and rebuild every Axes. Required when the Axes *count*, GridSpec layout, or `layout_mode` changes. **All previously-held `Axes` references become stale**, so never cache an `Axes` across it.
- `update_all_axes_appearance_and_data()` (`_update_plot(light=True)`) — redraw data and appearance on the *existing* Axes. Valid only when Axes count/placement is unchanged (dark-mode toggle, panel-label toggle).
- `update_single_axis()` — one Axes only. This is what a dataset property change goes through (`_refresh_after_dataset_property_change`), including `subplot_target`/`use_secondary_y` changes, which touch just the old and new Axes.

Two filters are applied *before* `_draw_data` sees the list, and both matter when reasoning about indices: `data_kind == '2d_grid'` datasets are split off into `_draw_2d_data()` (so heatmaps never reach the 1D code path), and `visible == False` datasets are dropped entirely. The second one is why hiding one waterfall trace renumbers the stack behind it.

**Display coordinates ≠ data coordinates.** With waterfall stacking enabled, a trace is drawn at `x + index*offset_x`, `y*depth_scale + index*offset_y`. Anything that maps a mouse position back onto a data row (range-select masking, the data cursor, editor↔plot highlight, peak placement) must invert that transform — several existing call sites do not, which is a known open bug.

### Icons

`gui/icon_utils.py` renders bundled Tabler Icons SVGs (`assets/icons/*.svg`, MIT-licensed, `stroke="currentColor"`) into themed `QIcon`s by string-replacing `currentColor` before feeding the SVG to `QSvgRenderer`. Path resolution is anchored to `icon_utils.py`'s own file location (not `cwd`) for the same reason described below — icons must resolve correctly regardless of the process's working directory.

### `resource_path()` is cwd-independent by design

`gui/main_window.py`'s `resource_path()` resolves bundled resources (icons, sample data, the app icon) relative to `gui/main_window.py`'s own location when running from source, and `sys._MEIPASS` when frozen by PyInstaller. It deliberately does **not** use the process's current working directory — an earlier `os.path.abspath(".")`-based version silently broke icon loading whenever the app was launched with a cwd other than `Graphica_project/`. Any new resource-loading code should go through `resource_path()` (or `icon_utils.icon()`), not construct cwd-relative paths directly.

### A known PySide6/shiboken GC gotcha

Traversing `self.menuBar().actions()` and then calling `.menu()` on each top-level action to reach a `QMenu` — even when the result is used immediately, in the same call — can cause that `QMenu` and its child `QAction`s to become invalid ("Internal C++ object already deleted") sometime after the traversal, for reasons not fully understood at the shiboken level. The fix used throughout this codebase is to cache top-level menus as persistent `self._file_menu` / `self._edit_menu` / etc. attributes at menu-creation time, and always traverse from those cached references rather than re-deriving them via `menuBar().actions()`. The command palette, quick-access manager, and shortcuts-list dialog all depend on this pattern (`_collect_menu_actions()` in `gui/mixins/ui_setup_mixin.py`).

**Caching the `QMenu` is not enough for a submenu — cache its `menuAction()` too.** When `_collect_menu_actions()` recursed into the "ドックレイアウト" submenu (the first real submenu it ever walked; "最近使ったファイル" is explicitly excluded, and the plugin submenus only exist when a plugin registers one), a single call was enough to destroy that submenu permanently: every later access raised "Internal C++ object already deleted", so opening the command palette once broke the menu for the rest of the session. Holding `self._dock_layout_menu` did **not** prevent it — the object that gets collected is the `QAction` that `addMenu()` returns/attaches (`QMenu.menuAction()`), and destroying it takes its `QMenu` and all children with it. **When adding any submenu, store both**:

```python
sub = parent_menu.addMenu(tr("..."))
self._sub_menu = sub                    # the QMenu
self._sub_menu_action = sub.menuAction()  # and its opener action
```

This matters most for the dataset context menu and the File menu, both of which are candidates for submenu grouping. Note also the pre-existing limitation that menu items nested two or more levels deep cannot be pinned via the quick-access right-click.

### Settings and autosave

`QSettings("Graphica", "Graphica")` persists dark mode, autosave interval/directory, recent files, window/dock layout, named dock-layout presets, custom color palettes and the active palette, quick-access pins, disabled plugins, language, minimap visibility, detached-canvas state, snap-to-grid, `point_label_max_points`, and the `clean_exit` / `has_shown_welcome` / `dock_layout_version` bookkeeping flags. Values that aren't plain scalars are stored as **JSON strings** (and binary Qt data such as `saveState()` output is base64-encoded first, see `DOCK_LAYOUT_PRESETS_SETTINGS_KEY`) — follow that pattern rather than storing Python objects.

Autosave writes to `AUTOSAVE_FILENAME` (`autosave.graphica`, JSON format) under a configurable directory (`autosave_dir`, empty = alongside the app) with generation rotation (`_rotate_autosave_generations`, keeps `AUTOSAVE_GENERATIONS` copies).

Dock layout has two independent mechanisms, and they are easy to confuse: **startup restore** (`saveState()`/`restoreState()` via the `window_state` key) happens only on the first tab and only when `dock_layout_version` matches — so changing the default dock-size constants in code has no visible effect until the user resets or manually resizes. Separately, item C-911 added **manual, always-available** named presets (View ▸ ドックレイアウト ▸ 保存/読み込み/リセット) that work on every tab regardless of `run_startup_checks`; "リセット" restores `self._pristine_dock_state`, snapshotted in `__init__` before any restore happens.

## Planning documents and active roadmap

**Session handoff (read this first, every session)**: `Graphica_project/docs/CURRENT_STATE.md` holds the current branch, the most recently completed roadmap item(s), what's next, and the operating rules the user and Claude have agreed on for this project (autonomous agent use, when to run the full test suite, the commit/push/update cadence). It's kept short and is overwritten at each work boundary — read it before touching anything else, especially when picking up after a gap (a new chat, a crashed desktop-app session, etc.) where prior conversation context may be gone. Update it as the last step of every completed unit of work.

The user tracks the full feature list as a single numbered checklist in `Graphica_project/docs/roadmap.html` (a self-contained HTML file, also published as a Claude Artifact for convenient browsing — the URL is recorded in `CURRENT_STATE.md`). The user instructs work by number against this list (e.g. "23-25実施"). The file's own `DATA` array is the source of truth for what's done (`true`/`false` per item) even if the Artifact URL is lost — always edit this file and re-publish from it, never edit only the published Artifact.

**Where the roadmap actually stands** (verify against `roadmap.html` rather than trusting this line after a long gap): 229 numbered items, of which ~128 are done and ~29 are explicitly excluded by user decision (kept in the list, with the reason appended to the title, so the numbering never shifts). **The core-app (`C-xxx`) track is effectively complete** — almost all remaining items are plugin-track (`P-xxx`) work. There is also a standing audit board of non-roadmap improvements (bugs, GUI restructuring, performance) recorded in `CURRENT_STATE.md`.

Six further planning documents live under `Graphica_project/docs/` and describe the multi-session development plan (plugin API extension points, GUI modernization, and the core/plugin backlogs) in more narrative detail than the roadmap checklist. These are living project-management documents, not architecture reference — for architecture, keep using the sections above and `docs/Graphica_SPEC.md`.

- `docs/Graphica_MASTER_SCHEDULE.md` — Defines 5 execution tracks (Track 0: prerequisites, Track 0': quick wins, Track 1: plugin API phases A–G, Track 2: GUI modernization phase H, Track 3: remaining core features, Track 4: plugin development) and states which track/phase is currently active.
- `docs/PLUGIN_API_PROGRESS.md` — detailed completion log (ID, status, completion date, implementation notes) for Track 1 (plugin API extension), updated every time a roadmap item finishes. This is where to look for *how* something was implemented; `CURRENT_STATE.md` is where to look for *where things stand right now*.
- `docs/GUI_MODERNIZATION_PROGRESS.md` — the same kind of completion log, but for Track 2 (GUI modernization, phase H). Track 1 and Track 2 progress live in separate files since they're developed on separate branches (`feature/format-version-and-foundations` and `feature/gui-modernization` respectively).
- `docs/gui_style_audit.md` — Track 2's H-0 deliverable: an inventory of the existing Qt theming (`gui/theme.py`), matplotlib dark-mode color duplication (`gui/canvas.py`, `gui/minimap_widget.py`), and custom widgets. Read this before touching anything styling-related in Track 2's later phases (H-2 onward) — it documents non-obvious findings (e.g. two independent, mutually-inconsistent sets of hardcoded dark/light matplotlib color constants) that later phases must account for.
- `docs/Graphica_SPEC.md` — full architecture/feature handoff doc (superset of this file, written for an AI picking up the project cold).
- `docs/Graphica_ROADMAP_PLUGIN_AND_GUI.md` — detailed phase-by-phase steps for Track 1 (plugin API) and Track 2 (GUI).
- `docs/Graphica_CORE_BACKLOG.md` / `docs/Graphica_PLUGIN_BACKLOG.md` — the core-app and plugin backlog items referenced by ID (e.g. "C-001", "P-304") from the schedule and roadmap. Items the user has decided against are **not deleted**: they stay in place with a 🔽 marker and are indexed with their reason in the 「低優先(ユーザー判断により不要、番号は保持)」 section. Follow that convention rather than removing rows.
- `docs/Graphica_INTEGRATION_REPORT.md` — background/rationale for how the backlogs were split; not required reading to execute a task.

**Before starting any task from this roadmap**: read `docs/CURRENT_STATE.md` first, then `docs/Graphica_MASTER_SCHEDULE.md`, and identify the current track and phase — do not assume which one is active from memory or from a prior session.

**Track status**: Tracks 0 / 0' / 1 (plugin API) / 2 (GUI modernization) / 3 (core features) are all complete and merged to `master`; the original "Track 0 gate" that guarded them no longer applies. **Track 4 (plugin development) is the only track with work left.** It was paused early on because plugin distribution was undecided — that blocker has since been resolved (zip install + `%LOCALAPPDATA%` plugins dir, see the Plugin API section), but one finished plugin (P-805) is still sitting unmerged on the `feature/plugin-track4` branch, and `master` has moved ~80 commits past its branch point. Resolve that branch before starting new plugin work.

**Scope discipline**: work only the track/phase/item the user specifies. Do not autonomously expand into adjacent tracks or "while I'm here" fixes elsewhere in the roadmap — the master schedule explicitly calls this out as a failure mode to avoid.

**Regression bar**: the full `pytest` suite must stay green, but running it after *every* small change is wasteful — it takes 25-30 minutes and most changes don't warrant that cost. Calibrate by blast radius:

- **Small, isolated changes** (a single-component QSS/style tweak, a docstring, a change confined to one function with no shared/global state involved): run the changed test file(s) plus a relevant broader `pytest -k <keyword>` subset (e.g. `-k "quick_access or main_window"` for a GUI mixin change). That's sufficient before committing.
- **Changes touching shared or global state, or core mechanisms** (anything in `core/`, `gui/theme.py`, the plugin registry singleton, `models/project.py` serialization, or anything else many other modules depend on): run the full suite before considering the change done. This isn't theoretical — two real bugs in this project only surfaced when running the full suite (global plugin-registry singleton state leaking between test files depending on execution order; a test-mock lambda whose fixed signature broke after an unrelated signature change elsewhere) and were invisible in any subset run.
- **Regardless of the above**: run the full suite at some regular cadence before pushing — not necessarily after every single item, but every few items or at a natural phase/task boundary — so breakage never accumulates silently across several unverified commits.

**Full-suite execution and progress reporting**: The suite is currently **78 test files / ~37,000 lines**, which `scripts/run_tests_chunked.sh` splits into roughly **133 chunks**. Never run it as a single `pytest -q` process — one process accumulates Qt/matplotlib resources and silently degrades to the point of never completing, even though it's still burning CPU (confirmed here: 1 hour elapsed with no completion, 5.8GB resident, before chunking fixed it). Always run it chunked, one fresh process per test file (or per 30 tests for the big files). While a full-suite run is in progress, report progress **every 30 minutes**, and each report must state completion as **both an absolute count and a percentage of the total** (e.g. "84/133 chunks done (63%)"), not just "still running." This progress check doubles as the stuck-detection check (verify forward progress via CPU-time delta or growth in chunks-completed — see the global `~/.claude/CLAUDE.md` method — before reporting; a report with no growth since the last one is the stuck signal, not a thing to paper over).

**Known benign failure**: `tests/test_export_preview_panel.py` reliably segfaults *after* printing its passing summary (interpreter teardown, exit 139) on both Windows and macOS. The chunk runner already distinguishes this by looking for an `N passed` summary line with no `failed`/`error`, and reports it as `!!! WARN` rather than a failure. A run whose only non-green line is that WARN is a green run.

**Constraint inherited from `docs/Graphica_SPEC.md` §2.8**: do not add new Win32 DPI-awareness API calls, and do not add any code that depends on the process's current working directory — route resource loading through `resource_path()` / `icon_utils.icon()` as already established above.
