# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

# Find python DLL
python_dll = os.path.join(os.path.dirname(sys.executable), f'python{sys.version_info.major}{sys.version_info.minor}.dll')
python3_dll = os.path.join(os.path.dirname(sys.executable), 'python3.dll')

extra_binaries = []
if os.path.exists(python_dll):
    extra_binaries.append((python_dll, '.'))
if os.path.exists(python3_dll):
    extra_binaries.append((python3_dll, '.'))

# Collect PySide6/shiboken6 dynamic libs
pyside6_binaries = collect_dynamic_libs('PySide6')
shiboken6_binaries = collect_dynamic_libs('shiboken6')

a = Analysis(
    ['termplus/main.py'],
    pathex=['.'],
    binaries=extra_binaries + pyside6_binaries + shiboken6_binaries,
    datas=[],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'paramiko',
        'pyte',
        'qasync',
        'cryptography',
        'keyring',
        'keyring.backends',
        'keyring.backends.Windows',
        'appdirs',
        'aiofiles',
        'aiohttp',
        'bcrypt',
        'nacl',
        'cffi',
        'aardwolf',
        'aardwolf.connection',
        'aardwolf.commons.iosettings',
        'aardwolf.commons.target',
        'aardwolf.commons.queuedata.constants',
        'aardwolf.extensions.RDPECLIP.channel',
        'aardwolf.extensions.RDPEDYC.channel',
        'aardwolf.utils.rlers',
        'asyauth',
        'asyauth.common.credentials',
        'asyauth.common.constants',
        'asysocks',
        'unicrypto',
        'arc4',
        'Pillow',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'test',
        'msal',
        'google',
        'dropbox',
        'PyQt6',
        'PyQt5',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Termplus',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=None,
)
