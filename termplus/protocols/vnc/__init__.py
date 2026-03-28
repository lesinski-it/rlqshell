"""VNC protocol plugin — RFB client and display widget."""

from termplus.protocols.vnc.connection import VNCConnection
from termplus.protocols.vnc.widget import VNCWidget

__all__ = ["VNCConnection", "VNCWidget"]
