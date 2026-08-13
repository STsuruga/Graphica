# -*- mode: python ; coding: utf-8 -*-
#
# Graphica の Windows exe / macOS .app を作成するための PyInstaller spec
# ファイル。sys.platform で分岐し、Windows/macOS 共用で使う。
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
# 生成物:
#   Windows: dist/Graphica/Graphica.exe (onedir 形式)
#   macOS:   dist/Graphica.app (BUNDLE) ※事前に Graphica.icns の生成が必要
#            (CIでは .github/workflows/build.yml の macOS ジョブが
#            Graphica.ico から都度生成している。ローカルでmacビルドする
#            場合は同じ変換を手動で行うか、Graphica.icns を用意すること)

import importlib.util
import os
import sys

# このファイル自身の場所を基準にする (cwd に依存しない: CLAUDE.md の
# resource_path() と同じ理由 — pyinstaller はこの spec ファイルを
# 別の cwd から実行されても壊れないようにする)
PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))
IS_MACOS = sys.platform == "darwin"

# core/version.py の __version__ をmacOSの Info.plist に転記する
# (バージョン文字列をこのファイルに二重管理しないため)
_version_spec = importlib.util.spec_from_file_location(
    "graphica_version", os.path.join(PROJECT_ROOT, "core", "version.py")
)
_version_module = importlib.util.module_from_spec(_version_spec)
_version_spec.loader.exec_module(_version_module)
APP_VERSION = _version_module.__version__

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

icon_path = os.path.join(
    PROJECT_ROOT, "Graphica.icns" if IS_MACOS else "Graphica.ico"
)

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
    icon=icon_path,
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

if IS_MACOS:
    # 署名なし(未署名)配布のため、初回起動時にGatekeeperの警告が出る点は
    # README側で案内する。BUNDLE()がないとダブルクリックで起動できる
    # 通常の.appにならず、Windows同様のonedirフォルダのままになる。
    app = BUNDLE(
        coll,
        name="Graphica.app",
        icon=icon_path,
        bundle_identifier="com.graphica.app",
        info_plist={
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHighResolutionCapable": True,
        },
    )
