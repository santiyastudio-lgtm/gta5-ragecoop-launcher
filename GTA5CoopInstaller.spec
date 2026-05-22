# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ('dist\\GTA5CoopLauncher.exe', '.'),
    ('dist\\launcher_config.json', '.'),
    ('dist\\README.md', '.'),
    ('dist\\RageCoop.Client.zip', '.'),
    ('dist\\RageCoop.Server-win-x64.zip', '.'),
    ('dist\\RageCoopPlus.zip', '.'),
    ('dist\\ScriptHookV.zip', '.'),
    ('dist\\ScriptHookVDotNetEnhanced-v1.1.0.5.zip', '.'),
    ('dist\\PLAYER_INSTRUCTIONS_RU.txt', '.'),
    ('dist\\ЧТО_ВВОДИТЬ_ИГРОКУ.txt', '.'),
    ('dist\\wireguard-amd64-1.1.msi', '.'),
]
datas += collect_data_files('customtkinter')


a = Analysis(
    ['ragecoop_installer.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
    name='GTA5CoopInstaller',
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
    icon='assets\\app_icon.ico',
)
