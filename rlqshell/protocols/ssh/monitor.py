"""SSH server monitor — collects live metrics via a separate exec channel."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import paramiko
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# Bash script sent to `bash -s` on the remote server.
# Outputs one KEY=VALUE line every 5 seconds.
# Uses only /proc files and standard POSIX tools — no Python required.
_MONITORING_SCRIPT = b"""\
p_idle=0; p_total=0; p_rx=0; p_tx=0; n=0
while true; do
  read -r _ u ni s id io ir st _ < /proc/stat
  total=$((u+ni+s+id+io+ir+st))
  dt=$((total-p_total)); di=$((id-p_idle))
  if [ "$dt" -gt 0 ] && [ "$n" -gt 0 ]; then cpu=$((100*(dt-di)/dt)); else cpu=0; fi
  p_total=$total; p_idle=$id

  mt=$(awk '/^MemTotal/{print $2;exit}' /proc/meminfo)
  ma=$(awk '/^MemAvailable/{print $2;exit}' /proc/meminfo)
  mu=$((mt-ma))

  net=$(awk '/^[[:space:]]*[^I]/ && /:/ {gsub(/:/," ");if($1!="lo"){rx+=$2;tx+=$10}} END{print rx+0,tx+0}' /proc/net/dev)
  crx=$(echo $net|awk '{print $1}'); ctx=$(echo $net|awk '{print $2}')
  if [ "$n" -gt 0 ]; then drx=$((crx-p_rx)); dtx=$((ctx-p_tx)); else drx=0; dtx=0; fi
  p_rx=$crx; p_tx=$ctx

  up=$(awk '{printf "%d",$1}' /proc/uptime)
  usr=$(id -un 2>/dev/null)
  disk=$(df -P 2>/dev/null | awk 'NR>1&&($6=="/"||$6=="/boot"||$6=="/home"||$6=="/var"||$6=="/data"){gsub(/%/,"",$5);printf "%s%%%s%%%s%%%s;",$6,$5,$3,$2}' | sed 's/;$//')

  echo "cpu=${cpu} mu=${mu} mt=${mt} rx=${drx} tx=${dtx} up=${up} usr=${usr} disk=${disk}"
  n=$((n+1)); sleep 5
done
"""


@dataclass
class ServerStats:
    """Parsed snapshot of remote server metrics."""

    hostname: str
    cpu_pct: int
    mem_used_kb: int
    mem_total_kb: int
    net_rx_bytes: int   # bytes received since last sample (~5 s window)
    net_tx_bytes: int
    uptime_secs: int
    user: str
    # [(mount, pct, used_kb, total_kb), ...]
    disk: list[tuple[str, int, int, int]] = field(default_factory=list)


class ServerMonitor(QObject):
    """Opens a separate SSH exec channel and periodically emits server stats.

    Uses ``bash -s`` with a monitoring script sent via stdin so that no
    script file needs to be uploaded to the remote host.  Falls back
    silently if bash or /proc are unavailable.
    """

    stats_updated = Signal(object)  # ServerStats

    def __init__(self, transport: paramiko.Transport, hostname: str) -> None:
        super().__init__()
        self._transport = transport
        self._hostname = hostname
        self._stop_event = threading.Event()
        self._channel: paramiko.Channel | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background monitoring thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"monitor-{self._hostname}"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the monitoring thread to stop and close the channel."""
        self._stop_event.set()
        ch = self._channel
        if ch is not None:
            try:
                ch.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            channel = self._transport.open_session()
            channel.settimeout(15.0)
            self._channel = channel

            channel.exec_command("bash -s")
            channel.sendall(_MONITORING_SCRIPT)
            channel.shutdown_write()

            # Read stdout line by line
            buf = b""
            channel.settimeout(12.0)  # slightly longer than sleep 5 + awk overhead
            while not self._stop_event.is_set():
                try:
                    chunk = channel.recv(4096)
                except Exception:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if line:
                        stats = self._parse(line)
                        if stats is not None:
                            self.stats_updated.emit(stats)
        except Exception as exc:
            logger.debug("ServerMonitor[%s] exited: %s", self._hostname, exc)
        finally:
            self._channel = None

    def _parse(self, line: str) -> ServerStats | None:
        """Parse a ``KEY=VALUE ...`` output line into a ``ServerStats``."""
        try:
            parts: dict[str, str] = {}
            for token in line.split():
                if "=" in token:
                    k, v = token.split("=", 1)
                    parts[k] = v

            disk: list[tuple[str, int, int, int]] = []
            raw_disk = parts.get("disk", "")
            if raw_disk:
                for entry in raw_disk.split(";"):
                    # Format: mount%pct%used_kb%total_kb
                    segs = entry.split("%")
                    if len(segs) >= 4:
                        try:
                            disk.append((segs[0], int(segs[1]), int(segs[2]), int(segs[3])))
                        except ValueError:
                            pass
                    elif len(segs) == 2:
                        # Fallback: mount%pct only (legacy)
                        try:
                            disk.append((segs[0], int(segs[1]), 0, 0))
                        except ValueError:
                            pass

            return ServerStats(
                hostname=self._hostname,
                cpu_pct=int(parts.get("cpu", 0)),
                mem_used_kb=int(parts.get("mu", 0)),
                mem_total_kb=int(parts.get("mt", 0)),
                net_rx_bytes=max(0, int(parts.get("rx", 0))),
                net_tx_bytes=max(0, int(parts.get("tx", 0))),
                uptime_secs=int(parts.get("up", 0)),
                user=parts.get("usr", ""),
                disk=disk,
            )
        except Exception as exc:
            logger.debug("ServerMonitor parse error: %s — line: %r", exc, line)
            return None
