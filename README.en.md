# Graphica

[日本語](README.md) | **English**

**A desktop app for turning CSV/Excel measurement data into publication-quality plots.**
Curve fitting, peak detection, baseline correction and other analyses are built in, so the whole workflow from raw
data to a finished figure stays in one place. Free and open source (MIT), for Windows and macOS.

[![Release](https://img.shields.io/github/v/release/STsuruga/Graphica)](https://github.com/STsuruga/Graphica/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Coverage report](https://img.shields.io/badge/coverage-report-brightgreen.svg)](https://stsuruga.github.io/Graphica/coverage/)

![Graphica main window](https://github.com/STsuruga/Graphica/raw/master/Graphica_project/docs/images/main_window.png)

> **Language note**: Graphica's interface is Japanese by default. The main menus and key dialogs are available in
> English — see [Switching the interface to English](#switching-the-interface-to-english). The detailed user manual
> ([Wiki](https://github.com/STsuruga/Graphica/wiki)) is currently written in Japanese.

---

## Features

**Importing data**
- CSV and text files (`.csv` / `.txt`) with automatic detection of encoding (UTF-8, Shift_JIS, …) and delimiter
  (comma, tab, semicolon, whitespace)
- Excel workbooks (`.xlsx` / `.xls`), including choosing sheets or importing several at once
- Drag and drop, paste from the clipboard, and batch import from a folder

**Building plots**
- Line, scatter, area, bar, step, density scatter and color-by-value scatter plots
- Error bars or error bands, a secondary Y axis, logarithmic and reversed axes, and a unit-converted top X axis
  (nm / eV / cm⁻¹ / Hz)
- Multiple subplots in a grid or free layout, with automatic panel labels ((a), (b), (c), …)
- Waterfall (stacked) display, gradients, and 2D maps as heatmaps or contour plots
- Fine control over ticks, grids, fonts, legends and mathtext labels; dark mode
- Named colors, so the same sample keeps the same color across figures

**Processing and analysis**
- Normalization, Savitzky–Golay smoothing and differentiation, baseline correction, interval and cumulative
  integration, resampling onto a common X grid, outlier detection and masking
- Curve fitting with many built-in models or your own formula, parameter bounds and fixed values, confidence and
  prediction bands, and a residual plot
- Multi-peak fitting with peaks placed by clicking on the plot, peak detection and automatic peak labels
- Summary statistics, histograms / KDE, arithmetic between datasets, and mean ± SD from replicate measurements
- A column calculator for deriving new columns from expressions

**Finishing and exporting**
- Text and arrow annotations, highlighted regions, insets, and a color-vision-deficiency preview
- Export to PNG, PDF (with embedded TrueType fonts) and SVG, with a live export preview; batch export; printing
- Export the figure as a standalone Python (matplotlib) script, generate LaTeX/Word captions, or an HTML/PDF report
  that records the processing steps

**Working safely**
- Project files (`.graphica`, JSON) that keep data, folders and plot settings
- Undo/redo, autosave with multiple generations, crash recovery, and a prompt before closing with unsaved changes
- Plugins that add importers, exporters, processing steps, fit functions, panels and plot types

## Download and install

Download the zip for your OS from [the latest release](https://github.com/STsuruga/Graphica/releases/latest).
No installation is needed.

- **Windows**: Extract the zip and run `Graphica.exe`.
  Because the executable is not code-signed, Windows SmartScreen may show "Windows protected your PC". Click
  **More info** and then **Run anyway**.
- **macOS** (Apple Silicon): Extract the zip and move `Graphica.app` to the Applications folder.
  Because the app is not signed, **the first time you open it, right-click (or Control-click) it and choose Open**.
  Double-clicking alone is blocked by Gatekeeper. Intel Macs are not supported by the prebuilt app; run from source
  instead.

### Switching the interface to English

1. Open **編集 (Edit) ▸ 環境設定... (Preferences...)**.
2. On the **一般** (General) tab, set **言語** (Language) to **English**.
3. Click OK and restart Graphica.

Translation currently covers the main menus, buttons and key dialogs; some less common dialogs remain in Japanese.

## Install with pip

With Python 3.10 or later you can install straight from GitHub; the dependencies come along (a virtual environment is
recommended so they do not clash with other software).

```
pip install "git+https://github.com/STsuruga/Graphica.git#subdirectory=Graphica_project"
graphica
```

`graphica` starts without a console window. Use `python -m graphica` to see the log in a console. Add `--upgrade` to
update; `pip uninstall graphica` removes it.

## Run from source

Python 3.11 or later is required (`requirements.txt` pins the versions Graphica is tested with).

```
git clone https://github.com/STsuruga/Graphica.git
cd Graphica/Graphica_project
pip install -r requirements.txt
python main.py
```

`python main.py --safe-mode` (or `Graphica.exe --safe-mode`) starts without loading any plugins, which is useful when
a plugin prevents Graphica from starting.

## Tests

The suite has about 3,000 pytest tests covering data processing, fitting, undo/redo, project save/load, and the GUI
wiring and rendering (run headless).

```
cd Graphica_project
pytest tests/test_dataset.py              # a single file
bash scripts/run_tests_chunked.sh         # the whole suite (about 20 minutes)
```

Do not run the whole suite as a single `pytest` process: GUI tests accumulate Qt/matplotlib resources and slow down
progressively, so the script runs each file in its own process. The latest coverage report for `master` is published
at https://stsuruga.github.io/Graphica/coverage/.

## Plugins

Plugins can add data importers and exporters, processing and analysis steps, fit functions, panels and plot types.
Install a plugin zip from **Preferences**, on the **プラグイン** (Plugins) tab, with the **プラグインをインストール...** (Install plugin) button — these labels are not translated yet. The plugin is extracted into
`%LOCALAPPDATA%\Graphica\plugins` on Windows. To write your own, see
[`Graphica_project/docs/plugin_development.md`](Graphica_project/docs/plugin_development.md) (Japanese) and the example
repository [graphica-plugin-element-constants](https://github.com/STsuruga/graphica-plugin-element-constants).

## Contributing and support

- **Bug reports and feature requests**: [open an issue](https://github.com/STsuruga/Graphica/issues/new/choose).
  English is welcome. For bugs, attaching the zip from **Help ▸ 診断情報をエクスポート...** (Export diagnostics)
  helps a lot; check it first, as it contains local folder names.
- **Contributing**: see [CONTRIBUTING.md](CONTRIBUTING.md) (Japanese) for setup, testing and the codebase's pitfalls.
- **Security issues**: please report them privately as described in [SECURITY.md](SECURITY.md).
- **Code of conduct**: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- **Changes**: [CHANGELOG.md](CHANGELOG.md) (Japanese).

## License

Graphica is released under the [MIT License](LICENSE).

The distributed executables bundle third-party libraries, including **Qt / PySide6 under the LGPL v3**. See
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for the full list and the conditions for redistribution.
