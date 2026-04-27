"""Diagnostic script: inspect what windows wfreerdp creates inside /parent-window.

Spawns wfreerdp.exe with /parent-window:HWND pointing at a Qt widget,
then for ~5 seconds enumerates every descendant window of our HWND and
prints class name, dimensions and visibility. This tells us which child
window is the actual rendering surface vs message-only / helper windows.

The target is a non-routable address so wfreerdp will exit quickly with
a connection error -- but it still creates its window tree first.

Run: python scripts/diag_rdp_embed.py
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

REPO_ROOT = Path(__file__).resolve().parents[1]
WFREERDP = REPO_ROOT / "installer" / "freerdp" / "wfreerdp.exe"

user32 = ctypes.windll.user32
EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumChildWindows.argtypes = [ctypes.c_void_p, EnumChildProc, ctypes.c_void_p]
user32.EnumChildWindows.restype = ctypes.c_bool
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = ctypes.c_bool
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = ctypes.c_bool
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetParent.argtypes = [ctypes.c_void_p]
user32.GetParent.restype = ctypes.c_void_p


def cls(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value or ""


def title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value or ""


def client_size(hwnd: int) -> tuple[int, int]:
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right, r.bottom


def enumerate_descendants(parent_hwnd: int) -> list[dict]:
    out: list[dict] = []

    def cb(hwnd, _lparam):
        try:
            w, h = client_size(hwnd)
            out.append({
                "hwnd": int(hwnd),
                "parent": int(user32.GetParent(hwnd) or 0),
                "class": cls(hwnd),
                "title": title(hwnd),
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "w": w,
                "h": h,
            })
        except Exception as exc:  # noqa: BLE001
            print(f"  cb error: {exc}")
        return True

    user32.EnumChildWindows(parent_hwnd, EnumChildProc(cb), None)
    return out


def main() -> int:
    if sys.platform != "win32":
        print("Windows only")
        return 1
    if not WFREERDP.exists():
        print(f"FreeRDP not found at {WFREERDP}")
        print("Run: pwsh installer/fetch-freerdp.ps1")
        return 1

    app = QApplication(sys.argv)
    win = QWidget()
    win.resize(1280, 720)
    win.setWindowTitle("FreeRDP embedding diagnostic")
    layout = QVBoxLayout(win)
    label = QLabel("Spawning wfreerdp.exe in parent window…", parent=win)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label)

    # Force native window so winId is a real HWND
    win.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
    win.show()
    app.processEvents()

    parent_hwnd = int(win.winId())
    print(f"Parent HWND: {parent_hwnd}")

    # Spawn wfreerdp targeting a black-hole address; we don't care about
    # the connection, only about the windows it creates.
    import subprocess
    target = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:3389"
    user = sys.argv[2] if len(sys.argv) > 2 else "diag"
    password = sys.argv[3] if len(sys.argv) > 3 else "diag"
    args = [
        str(WFREERDP),
        f"/v:{target}",
        f"/u:{user}",
        f"/p:{password}",
        "/cert:ignore",
        "/sec:nla,tls,rdp",
        "/size:1024x768",
        f"/parent-window:{parent_hwnd}",
    ]
    print("Args:", " ".join(args))
    proc = subprocess.Popen(args)
    print(f"wfreerdp PID: {proc.pid}")

    polls = [(0.5, "after 0.5s"), (1.5, "after 1.5s"), (3.0, "after 3.0s"),
             (6.0, "after 6.0s"), (10.0, "after 10.0s")]
    start = time.monotonic()

    last_count = 0
    for delay, label_text in polls:
        # Pump the Qt event loop until target time
        target = start + delay
        while time.monotonic() < target:
            app.processEvents()
            time.sleep(0.05)
        descendants = enumerate_descendants(parent_hwnd)
        if len(descendants) != last_count:
            last_count = len(descendants)
            print(f"\n=== Descendants of parent HWND {parent_hwnd} {label_text} "
                  f"({len(descendants)} found) ===")
            for d in descendants:
                vis = "VIS" if d["visible"] else "hid"
                print(f"  [{vis}] hwnd={d['hwnd']:<10} "
                      f"parent={d['parent']:<10} "
                      f"{d['w']}x{d['h']:<6} "
                      f"class={d['class']!r:<30} "
                      f"title={d['title']!r}")

    # Final dump regardless
    descendants = enumerate_descendants(parent_hwnd)
    print(f"\n=== FINAL: {len(descendants)} descendants ===")
    for d in descendants:
        vis = "VIS" if d["visible"] else "hid"
        print(f"  [{vis}] hwnd={d['hwnd']:<10} "
              f"parent={d['parent']:<10} "
              f"{d['w']}x{d['h']:<6} "
              f"class={d['class']!r:<30} "
              f"title={d['title']!r}")

    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()

    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
