# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import copy_metadata

datas = [('ck3loc/lang', 'ck3loc/lang'), ('ck3loc/community_db_config.json', 'ck3loc')]
hiddenimports = []
datas += copy_metadata('keyring')
hiddenimports += collect_submodules('keyring.backends')


a = Analysis(
    ['ck3loc/desktop/__main__.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='CK3LocalizationManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CK3LocalizationManager',
)


import sys
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='CK3LocalizationManager.app',
                 bundle_identifier='io.github.rqkeqq-ui.ck3translate',
                 info_plist={'NSHighResolutionCapable': True})
