# -*- mode: python ; coding: utf-8 -*-
#
# Graphica の Windows exe を作成するための PyInstaller spec ファイル。
#
# リポジトリルートに残っている Graphica_ver1.spec / main_ver6.spec は、
# 現行の Graphica_project/ レイアウトより前のもの(参照しているエントリ
# ポイント Graphica_ver1.py / main_ver6.py も既に存在しない)なので、
# パッケージングの参考にしない。このファイルが現行レイアウトに対応した
# 唯一の spec ファイル。
#
# 実行方法 (cwd = Graphica_project/):
#   pyinstaller graphica.spec
#
# 生成物: dist/Graphica/Graphica.exe (onedir 形式)

import os

# このファイル自身の場所を基準にする (cwd に依存しない: CLAUDE.md の
# resource_path() と同じ理由 — pyinstaller はこの spec ファイルを
# 別の cwd から実行されても壊れないようにする)
PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))

block_cipher = None

datas = [
    # 実行時に import される Qt Designer 生成ファイル。
    (os.path.join(PROJECT_ROOT, "ui_main_window.py"), "."),
    # gui/icon_utils.py がバンドルする Tabler Icons SVG 一式 (MIT license)。
    (os.path.join(PROJECT_ROOT, "assets", "icons"), os.path.join("assets", "icons")),
    # ウィンドウ/タスクバーアイコン (resource_path("Graphica.ico") で参照)。
    (os.path.join(PROJECT_ROOT, "Graphica.ico"), "."),
    # 初回起動時の「サンプルデータを読み込む」機能が参照するCSV。
    (os.path.join(PROJECT_ROOT, "sample_data"), "sample_data"),
]

hiddenimports = [
    # matplotlib の Qt (PySide6) 用バックエンド。gui/canvas.py が
    # matplotlib.backends.backend_qtagg を直接importしているので通常は
    # 静的解析で検出されるが、明示しておく。
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_agg",
    # gui/icon_utils.py の SVG レンダリングに必要。
    "PySide6.QtSvg",
    # gui/mixins/export_mixin.py の PDF エクスポートに使用。
    "PySide6.QtPrintSupport",
    # コード全体で使用されている PySide6 サブモジュール。
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    # openpyxl は Excel 読み込み (core/excel_utils.py) で使用。動的import
    # がある場合に備えて明示。
    "openpyxl",
    "scipy.interpolate",
    "scipy.optimize",
    "scipy.signal",
]

a = Analysis(
    [os.path.join(PROJECT_ROOT, "main.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Graphica",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed ビルド (コンソール非表示)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, "Graphica.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Graphica",
)
