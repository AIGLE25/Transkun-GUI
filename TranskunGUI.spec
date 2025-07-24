# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['TranskunGUIstandalone.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'glob',
        'moduleconf',
        'soxr',
        'pretty_midi',
        'ncls',
        'torchaudio',
        'torch_optimizer',
        'mir_eval',
        'pydub',
        'numpy'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='transkun_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='transkun_gui',
)
