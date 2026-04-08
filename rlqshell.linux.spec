# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs


def safe_collect_submodules(package_name):
    try:
        return collect_submodules(package_name)
    except Exception:
        return []


def safe_collect_data_files(package_name):
    try:
        return collect_data_files(package_name)
    except Exception:
        return []


block_cipher = None

binaries = collect_dynamic_libs("PySide6") + collect_dynamic_libs("shiboken6")

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
    "paramiko",
    "pyte",
    "qasync",
    "cryptography",
    "keyring",
    "keyring.backends",
    "appdirs",
    "aiofiles",
    "aiohttp",
    "bcrypt",
    "nacl",
    "cffi",
    "arc4",
    "pycryptodomex",
]

for package in [
    "aardwolf",
    "asyauth",
    "asysocks",
    "minikerberos",
    "PIL",
    "Cryptodome",
    "unicrypto",
]:
    hiddenimports += safe_collect_submodules(package)

# Keep explicit unicrypto backends; dynamic imports can be missed.
hiddenimports += [
    "unicrypto.backends.pycryptodomex",
    "unicrypto.backends.pycryptodomex.AES",
    "unicrypto.backends.pycryptodomex.DES",
    "unicrypto.backends.pycryptodomex.RC4",
    "unicrypto.backends.pycryptodomex.TDES",
]

extra_datas = []
for package in ["aardwolf", "unicrypto"]:
    extra_datas += safe_collect_data_files(package)

a = Analysis(
    ["rlqshell/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=[
        ("rlqshell/resources", "rlqshell/resources"),
        ("rlqshell/ui/themes/dark.qss", "rlqshell/ui/themes"),
        ("rlqshell/ui/themes/terminal_schemes.json", "rlqshell/ui/themes"),
    ] + extra_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "test",
        "msal",
        "google",
        "dropbox",
        "PyQt6",
        "PyQt5",
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
    name="RLQShell",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
)
