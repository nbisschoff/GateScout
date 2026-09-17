# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icon.ico', 'assets'),
        ('assets/01.mp3',   'assets'),
        ('assets/02.mp3',   'assets'),
        ('assets/03.mp3',   'assets'),
        ('assets/04.mp3',   'assets'),
        ('assets/05.mp3',   'assets'),
        ('assets/06.mp3',   'assets'),
    ],
    hiddenimports=[
        'PyQt6.sip',
        'pygame',
        'pygame.mixer',
        'requests',
        'requests.adapters',
        'requests.auth',
        'urllib3',
        'charset_normalizer',
        'idna',
        'certifi',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GateScout',
    debug=False,
    strip=False,
    upx=True,
    console=False,                  # no black console window
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GateScout',
)
