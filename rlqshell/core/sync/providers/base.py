"""Abstract cloud storage provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RemoteFileInfo:
    """Metadata for a file in cloud storage."""

    path: str
    size: int = 0
    modified: datetime | None = None
    hash: str | None = None


class AbstractCloudProvider(ABC):
    """Interface for cloud storage providers (OneDrive, Google Drive, Dropbox)."""

    @abstractmethod
    async def authenticate(self, auth_code: str) -> bool:
        """Exchange an auth code for tokens. Returns True on success."""

    @abstractmethod
    async def refresh_token(self) -> bool:
        """Refresh the access token. Returns True on success."""

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Whether valid tokens exist."""

    @abstractmethod
    def get_auth_url(self) -> str:
        """Get the OAuth2 authorization URL."""

    @abstractmethod
    async def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a local file to cloud storage."""

    @abstractmethod
    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from cloud storage to local path."""

    @abstractmethod
    async def get_file_info(self, remote_path: str) -> RemoteFileInfo | None:
        """Get metadata for a remote file. Returns None if not found."""

    @abstractmethod
    async def list_files(self, folder: str) -> list[RemoteFileInfo]:
        """List files in a remote folder."""

    @abstractmethod
    async def create_folder(self, folder: str) -> None:
        """Create a remote folder (no-op if exists)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Clear stored tokens and disconnect."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""
