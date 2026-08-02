# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Graphica_ver1.py'],
    pathex=[],
    binaries=[],
    datas=[('Graphica.ico', '.')],
    hiddenimports=['matplotlib.backends.backend_pdf', 'matplotlib.backends.backend_svg', 'scipy.signal', 'scipy.optimize', 'scipy.interpolate'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Graphica_ver1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Graphica.ico'],
)
