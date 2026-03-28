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
    datas=[
        ('termplus/resources', 'termplus/resources'),
    ],
    hiddenimports=[
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
        # aardwolf RDP ecosystem (all subpackages)
        'aardwolf', 'aardwolf.connection', 'aardwolf.vncconnection',
        'aardwolf.channels', 'aardwolf.commons', 'aardwolf.extensions',
        'aardwolf.keyboard', 'aardwolf.network', 'aardwolf.protocol',
        'aardwolf.transport', 'aardwolf.utils', 'aardwolf.utils.rlers',
        'aardwolf.extensions.RDPECLIP', 'aardwolf.extensions.RDPEDYC',
        'asyauth', 'asyauth.common', 'asyauth.protocols', 'asyauth.utils',
        'asysocks', 'asysocks.unicomm', 'asysocks.unicomm.common',
        'asysocks.client', 'asysocks.common', 'asysocks.protocol',
        'asysocks.network', 'asysocks.security', 'asysocks.authentication',
        'unicrypto', 'unicrypto.backends', 'unicrypto.symmetric',
        'unicrypto.backends.cryptography', 'unicrypto.backends.cryptography.AES',
        'unicrypto.backends.cryptography.DES', 'unicrypto.backends.cryptography.RC4',
        'unicrypto.backends.cryptography.TDES',
        'unicrypto.backends.pure', 'unicrypto.backends.pure.AES',
        'unicrypto.backends.pure.DES', 'unicrypto.backends.pure.RC4',
        'unicrypto.backends.pure.TDES', 'unicrypto.backends.pure.MD4',
        'unicrypto.backends.pure.external',
        'unicrypto.backends.pycryptodomex', 'unicrypto.backends.pycryptodomex.AES',
        'unicrypto.backends.pycryptodomex.DES', 'unicrypto.backends.pycryptodomex.RC4',
        'unicrypto.backends.pycryptodomex.TDES',
        'unicrypto.hashlib', 'unicrypto.hmac', 'unicrypto.kdf',
        'unicrypto.cmac', 'unicrypto.pbkdf2',
        'minikerberos', 'minikerberos.common', 'minikerberos.protocol',
        'minikerberos.gssapi', 'minikerberos.network', 'minikerberos.security',
        'arc4', 'PIL', 'Pillow',
        'pycryptodomex', 'Cryptodome',
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
