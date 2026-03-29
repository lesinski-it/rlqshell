"""Abstract protocol base classes."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod

from PySide6.QtCore import QObject, Signal


class _QABCMeta(type(QObject), ABCMeta):
    """Merged metaclass for QObject + ABC."""


class AbstractConnection(QObject, metaclass=_QABCMeta):
    """Base class for all protocol connections.

    Subclasses must emit signals and implement the abstract methods.
    """

    # Signals
    connected = Signal()
    disconnected = Signal()
    error = Signal(str)  # error message
    data_received = Signal(bytes)
    title_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @abstractmethod
    async def connect(self) -> None:
        """Establish the connection."""

    @abstractmethod
    def send(self, data: bytes) -> None:
        """Send data to the remote side."""

    @abstractmethod
    def resize(self, cols: int, rows: int) -> None:
        """Notify the remote side of a terminal resize."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection and release resources."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the connection is currently active."""

    @property
    @abstractmethod
    def protocol(self) -> str:
        """Return the protocol name (e.g., 'ssh', 'rdp')."""
