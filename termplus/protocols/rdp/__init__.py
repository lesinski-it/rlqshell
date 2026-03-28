"""RDP protocol plugin — pure Python client via aardwolf."""

from termplus.protocols.rdp.connection import RDPConnection
from termplus.protocols.rdp.widget import RDPWidget

__all__ = ["RDPConnection", "RDPWidget"]
