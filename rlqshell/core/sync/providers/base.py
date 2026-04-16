"""Abstract cloud storage provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import aiohttp


@dataclass
class RemoteFileInfo:
    """Metadata for a file in cloud storage."""

    path: str
    size: int = 0
    modified: datetime | None = None
    hash: str | None = None


class AbstractCloudProvider(ABC):
    """Interface for cloud storage providers (OneDrive, Google Drive, Dropbox)."""

    def __init__(self, proxy_url: str | None = None) -> None:
        self._proxy_url = proxy_url
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return a cached aiohttp session (lazy-created)."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Whether valid tokens exist."""

    @abstractmethod
    def get_tokens(self) -> tuple[str, str] | None:
        """Return (access_token, refresh_token) or None if not authenticated."""

    @abstractmethod
    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        """Restore tokens from encrypted storage."""

    # --- Redirect-based OAuth (optional — override in redirect-flow providers) ---

    def get_auth_url(self) -> str:
        """Get the OAuth2 authorization URL (redirect flow only)."""
        raise NotImplementedError

    async def authenticate(self, auth_code: str) -> bool:
        """Exchange an auth code for tokens (redirect flow only)."""
        raise NotImplementedError

    async def refresh_token(self) -> bool:
        """Refresh the access token explicitly. Returns True on success."""
        raise NotImplementedError

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

    @property
    @abstractmethod
    def connectivity_check_url(self) -> str:
        """URL used to verify internet connectivity for this provider."""
