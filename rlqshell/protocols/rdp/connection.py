"""RDP connection — wraps xfreerdp/wfreerdp subprocess embedded in a Qt window.

The previous in-process implementation (aardwolf) lacked MS-RDPDR/SCARD support,
so smart cards, drive mapping, and printer redirection were impossible. This
implementation delegates to FreeRDP, the same backend used by Remmina and
MobaXterm. The remote desktop is rendered by FreeRDP into a child window we
own via Qt's `winId()` and FreeRDP's `/parent-window:` argument.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Signal

from rlqshell.protocols.base import AbstractConnection

logger = logging.getLogger(__name__)


_ERROR_MAP: list[tuple[str, str]] = [
    ("logon failure", "Login failed — invalid username or password."),
    ("authentication failure", "Authentication failed — check your credentials."),
    ("access denied", "Access denied — insufficient permissions for RDP connection."),
    ("account locked", "Account has been locked — contact your administrator."),
    ("account disabled", "Account is disabled."),
    ("password must be changed", "Password expired — change it on the target server."),
    ("credssp", "CredSSP error — the server requires Network Level Authentication (NLA)."),
    ("ntlm", "NTLM authentication error — check username, password, and domain."),
    ("connection refused", "Connection refused — RDP service is not listening on this port."),
    ("connection reset", "Connection was reset by the server."),
    ("connection timed out", "Connection timed out — host unreachable or port blocked."),
    ("no route to host", "No route to host — check the address and network configuration."),
    ("network unreachable", "Network unreachable — check your network connection."),
    ("name or service not known", "Could not resolve hostname — check the address."),
    ("could not resolve", "Could not resolve hostname — check the address."),
    ("certificate", "Server certificate error — untrusted connection."),
    ("tls", "TLS/SSL connection error — server certificate problem."),
    ("negotiation", "RDP protocol negotiation error with the server."),
    ("disconnected", "Server closed the connection."),
]


def _friendly_error(text: str) -> str:
    """Translate xfreerdp stderr text into a user-readable message."""
    raw = text.lower()
    for pattern, message in _ERROR_MAP:
        if pattern in raw:
            return message
    return text.strip() or "RDP connection failed."


def _find_freerdp_binary() -> str | None:
    """Locate the FreeRDP executable.

    Search order:
      1. Bundled next to our executable (MSI install layout: ``freerdp/wfreerdp.exe``)
      2. PyInstaller onefile extraction dir (``sys._MEIPASS/freerdp/...``)
      3. Source-tree dev location (``installer/freerdp/...``)
      4. PATH lookup
      5. Common Windows install locations
    """
    names = (
        ["wfreerdp.exe", "xfreerdp.exe", "xfreerdp3.exe", "sdl-freerdp.exe"]
        if sys.platform == "win32"
        else ["xfreerdp3", "xfreerdp", "sdl-freerdp"]
    )

    bundled_roots: list[Path] = []
    # 1. Next to RLQShell.exe (frozen MSI install)
    bundled_roots.append(Path(sys.executable).resolve().parent / "freerdp")
    # 2. PyInstaller onefile extraction
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled_roots.append(Path(meipass) / "freerdp")
    # 3. Dev mode -- installer/freerdp/ at repo root
    bundled_roots.append(
        Path(__file__).resolve().parents[3] / "installer" / "freerdp",
    )

    for root in bundled_roots:
        for name in names:
            candidate = root / name
            if candidate.exists():
                return str(candidate)

    # 4. PATH
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    # 5. Common Windows locations
    if sys.platform == "win32":
        for path in (
            Path(r"C:\Program Files\FreeRDP\wfreerdp.exe"),
            Path(r"C:\Program Files\FreeRDP\xfreerdp.exe"),
            Path(r"C:\ProgramData\chocolatey\bin\wfreerdp.exe"),
        ):
            if path.exists():
                return str(path)
    return None


class RDPConnection(AbstractConnection):
    """RDP connection driven by FreeRDP, embedded into a host Qt window."""

    # Signals kept for compatibility with ClipboardBridge — xfreerdp handles
    # clipboard sync natively at the OS level so these are never emitted.
    clipboard_text_received = Signal(str)
    clipboard_image_received = Signal(object)
    clipboard_ready = Signal()

    def __init__(
        self,
        hostname: str,
        port: int = 3389,
        username: str | None = None,
        password: str | None = None,
        domain: str | None = None,
        resolution: str = "1920x1080",
        color_depth: int = 32,
        audio: bool = False,
        clipboard: bool = True,
        smartcard: bool = False,
        drives_enabled: bool = False,
        drive_mapping: str | None = None,
        printers: bool = False,
        parent_winid: int | None = None,
    ) -> None:
        super().__init__()
        self._hostname = hostname
        self._port = port
        self._username = username
        self._password = password
        self._domain = domain
        self._resolution = resolution
        self._color_depth = color_depth
        self._audio = audio
        self._clipboard = clipboard
        self._smartcard = smartcard
        self._drives_enabled = drives_enabled
        self._drive_mapping = drive_mapping
        self._printers = printers
        self._parent_winid = parent_winid

        self._process: QProcess | None = None
        self._connected = False
        self._stderr_buffer = ""
        self._closing = False

    # ------------------------------------------------------------------
    # AbstractConnection API
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def protocol(self) -> str:
        return "rdp"

    def set_parent_window(self, winid: int | None) -> None:
        """Attach the parent native window before connect()."""
        self._parent_winid = winid

    async def connect(self) -> None:
        try:
            self._validate()
            self._spawn()
            self._connected = True
            self.connected.emit()
        except Exception as exc:
            logger.exception("RDP connection failed: %s", exc)
            self.error.emit(_friendly_error(str(exc)))
            raise

    def _validate(self) -> None:
        if not self._username:
            raise ConnectionError("Username is missing — provide RDP login credentials.")
        if not self._password:
            raise ConnectionError("Password is missing — provide RDP login password.")
        # Allow "host:port" embedded in the address field
        if ":" in self._hostname:
            head, tail = self._hostname.rsplit(":", 1)
            if tail.isdigit():
                self._hostname = head
                self._port = int(tail)

    def _spawn(self) -> None:
        binary = _find_freerdp_binary()
        if binary is None:
            raise ConnectionError(
                "FreeRDP not found. Install it (Windows: choco install freerdp; "
                "Linux: apt install freerdp2-x11) and ensure it is on PATH.",
            )

        args = self._build_args()

        proc = QProcess(self)
        proc.setProgram(binary)
        proc.setArguments(args)
        # Merge stderr into stdout for unified logging — FreeRDP writes errors
        # and progress to stderr, neither of which we display in real-time.
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.errorOccurred.connect(self._on_proc_error)
        proc.finished.connect(self._on_proc_finished)

        logger.info(
            "Spawning FreeRDP: %s (smartcard=%s drives=%s printers=%s parent_winid=%s)",
            binary, self._smartcard, self._drives_enabled, self._printers,
            self._parent_winid,
        )
        if not self._parent_winid:
            logger.warning(
                "No parent_winid set -- FreeRDP will open in a separate window "
                "instead of embedding into the Qt widget. RDPWidget should call "
                "set_parent_window() before connect().",
            )
        proc.start()
        if not proc.waitForStarted(5000):
            raise ConnectionError(f"Could not start FreeRDP: {proc.errorString()}")
        self._process = proc
        self.title_changed.emit(f"RDP: {self._hostname}")

    # ------------------------------------------------------------------
    # Argument building
    # ------------------------------------------------------------------

    def _build_args(self) -> list[str]:
        args: list[str] = [
            f"/v:{self._hostname}:{self._port}",
            f"/u:{self._username}",
            f"/p:{self._password or ''}",
            f"/bpp:{min(max(int(self._color_depth), 15), 32)}",
            "/cert:ignore",
            "/sec:nla,tls,rdp",
            "/dynamic-resolution",
            # Without smart-sizing the rendered framebuffer is fixed at /size:
            # and the embedded child window simply clips it, so a 1920x1080
            # remote desktop ends up showing only its top-left corner inside
            # our Qt widget. /smart-sizing scales the bitmap to the embedded
            # window dimensions instead.
            "/smart-sizing",
        ]
        if self._domain:
            args.append(f"/d:{self._domain}")

        if self._resolution and "x" in self._resolution:
            args.append(f"/size:{self._resolution}")

        if self._parent_winid:
            args.append(f"/parent-window:{int(self._parent_winid)}")

        # Local resource redirection
        if self._clipboard:
            args.append("+clipboard")
        if self._audio:
            args.append("/sound:sys:default")
        if self._smartcard:
            args.append("/smartcard")
        if self._printers:
            args.append("/printer")
        if self._drives_enabled:
            for spec in self._drive_specs():
                args.append(spec)

        return args

    def _drive_specs(self) -> list[str]:
        """Translate drive_mapping ('C:\\;D:\\Projects') into /drive args."""
        raw = (self._drive_mapping or "").strip()
        if not raw:
            # No explicit list → expose the user's home directory by default.
            home = str(Path.home())
            return [f"/drive:Home,{home}"]
        out: list[str] = []
        for idx, item in enumerate(raw.split(";")):
            path = item.strip()
            if not path:
                continue
            label = self._drive_label(path) or f"Drive{idx}"
            out.append(f"/drive:{label},{path}")
        return out

    @staticmethod
    def _drive_label(path: str) -> str | None:
        p = Path(path)
        # On Windows a drive root like "C:\" has parts ('C:\\',) — derive a
        # single-letter label. Otherwise use the directory name.
        if len(p.parts) == 1 and p.drive:
            return p.drive.rstrip(":\\/").upper() or None
        return p.name or None

    # ------------------------------------------------------------------
    # QProcess callbacks
    # ------------------------------------------------------------------

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        chunk = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace",
        )
        if not chunk:
            return
        self._stderr_buffer = (self._stderr_buffer + chunk)[-4096:]
        for line in chunk.splitlines():
            logger.debug("freerdp: %s", line.rstrip())

    def _on_proc_error(self, err: QProcess.ProcessError) -> None:
        if self._closing:
            return
        msg = self._process.errorString() if self._process else str(err)
        logger.error("FreeRDP process error: %s", msg)
        self.error.emit(_friendly_error(msg))

    def _on_proc_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        was_connected = self._connected
        self._connected = False
        if self._closing or exit_code == 0:
            logger.info("FreeRDP exited cleanly (code=%s)", exit_code)
        else:
            logger.warning(
                "FreeRDP exited with code %s (%s)", exit_code, exit_status,
            )
            if was_connected and self._stderr_buffer:
                self.error.emit(_friendly_error(self._stderr_buffer))
        self.disconnected.emit()

    # ------------------------------------------------------------------
    # Clipboard hooks (no-ops — xfreerdp syncs the OS clipboard itself)
    # ------------------------------------------------------------------

    async def send_clipboard_text(self, text: str) -> None:  # noqa: ARG002
        return

    async def send_clipboard_image(self, image) -> None:  # noqa: ARG002
        return

    # ------------------------------------------------------------------
    # AbstractConnection bytestream (unused for RDP)
    # ------------------------------------------------------------------

    def send(self, data: bytes) -> None:  # noqa: ARG002
        pass

    def resize(self, cols: int, rows: int) -> None:  # noqa: ARG002
        pass

    def close(self) -> None:
        self._closing = True
        self._connected = False
        if self._process is not None:
            try:
                self._process.terminate()
                if not self._process.waitForFinished(2000):
                    self._process.kill()
                    self._process.waitForFinished(1000)
            except Exception:
                logger.exception("Error terminating FreeRDP process")
            self._process = None
        logger.info("RDP connection closed (%s)", self._hostname)
