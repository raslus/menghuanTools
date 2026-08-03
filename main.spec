# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('models/easyocr', 'models/easyocr'),
        ('assets/maps', 'assets/maps'),
    ],
    hiddenimports=[
        'rapidocr_onnxruntime',
        'easyocr',
        'core.data_manager',
        'core.growth_db',
        'core.accounting_db',
        'utils.platform_utils',
        'utils.logger_setup',
    ],
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
    name='main',
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
    version='C:\\Users\\l\\AppData\\Local\\Temp\\9f879339-21a1-40b5-a4dd-c59f80b2994a',
)
