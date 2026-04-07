# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

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

# Collect ALL submodules for aardwolf and its dependencies
hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtSvg',
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
    'arc4',
    'pycryptodomex',
]

# Use collect_submodules for packages with heavy dynamic imports
for pkg in [
    'aardwolf',
    'asyauth',
    'asysocks',
    'minikerberos',
    'PIL',
    'Cryptodome',
]:
    hiddenimports += collect_submodules(pkg)

# unicrypto has a circular import in pycryptodomex backend that breaks
# collect_submodules — collect other backends normally, add pycryptodomex manually
hiddenimports += collect_submodules('unicrypto')
hiddenimports += [
    'unicrypto.backends.pycryptodomex',
    'unicrypto.backends.pycryptodomex.AES',
    'unicrypto.backends.pycryptodomex.DES',
    'unicrypto.backends.pycryptodomex.RC4',
    'unicrypto.backends.pycryptodomex.TDES',
]

# Data files (e.g. aardwolf may have data files)
extra_datas = []
for pkg in ['aardwolf', 'unicrypto']:
    try:
        extra_datas += collect_data_files(pkg)
    except Exception:
        pass

a = Analysis(
    ['rlqshell/main.py'],
    pathex=['.'],
    binaries=extra_binaries + pyside6_binaries + shiboken6_binaries,
    datas=[
        ('rlqshell/resources', 'rlqshell/resources'),
        ('rlqshell/ui/themes/dark.qss', 'rlqshell/ui/themes'),
        ('rlqshell/ui/themes/terminal_schemes.json', 'rlqshell/ui/themes'),
    ] + extra_datas,
    hiddenimports=hiddenimports,
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
    name='RLQShell',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='rlqshell/resources/images/app_icon.ico',
)
