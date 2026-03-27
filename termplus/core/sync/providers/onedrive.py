"""OneDrive cloud provider — Microsoft Graph API."""

from __future__ import annotations

import logging

import aiohttp

from termplus.core.sync.providers.base import AbstractCloudProvider, RemoteFileInfo

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.microsoft.com/v1.0"
_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0"
_SCOPES = "Files.ReadWrite offline_access"
_APP_FOLDER = "/Termplus"


class OneDriveProvider(AbstractCloudProvider):
    """OneDrive sync via Microsoft Graph API."""

    def __init__(self, client_id: str, redirect_uri: str = "http://localhost:8765/callback") -> None:
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._access_token: str | None = None
        self._refresh_token_str: str | None = None

    @property
    def provider_name(self) -> str:
        return "OneDrive"

    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def get_auth_url(self) -> str:
        return (
            f"{_AUTH_URL}/authorize?"
            f"client_id={self._client_id}&response_type=code"
            f"&redirect_uri={self._redirect_uri}"
            f"&scope={_SCOPES.replace(' ', '%20')}"
        )

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        """Restore tokens from encrypted storage."""
        self._access_token = access_token
        self._refresh_token_str = refresh_token

    async def authenticate(self, auth_code: str) -> bool:
        async with aiohttp.ClientSession() as session:
            data = {
                "client_id": self._client_id,
                "code": auth_code,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
                "scope": _SCOPES,
            }
            async with session.post(f"{_AUTH_URL}/token", data=data) as resp:
                if resp.status != 200:
                    logger.error("OneDrive auth failed: %s", await resp.text())
                    return False
                result = await resp.json()
                self._access_token = result["access_token"]
                self._refresh_token_str = result.get("refresh_token")
                logger.info("OneDrive authenticated")
                return True

    async def refresh_token(self) -> bool:
        if not self._refresh_token_str:
            return False
        async with aiohttp.ClientSession() as session:
            data = {
                "client_id": self._client_id,
                "refresh_token": self._refresh_token_str,
                "grant_type": "refresh_token",
                "scope": _SCOPES,
            }
            async with session.post(f"{_AUTH_URL}/token", data=data) as resp:
                if resp.status != 200:
                    logger.error("OneDrive token refresh failed")
                    return False
                result = await resp.json()
                self._access_token = result["access_token"]
                self._refresh_token_str = result.get("refresh_token", self._refresh_token_str)
                return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def create_folder(self, folder: str) -> None:
        async with aiohttp.ClientSession() as session:
            # Check if exists
            url = f"{_GRAPH_API}/me/drive/root:{folder}"
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status == 200:
                    return  # Already exists

            # Create
            parent = "/".join(folder.rstrip("/").split("/")[:-1]) or "/"
            name = folder.rstrip("/").split("/")[-1]
            url = f"{_GRAPH_API}/me/drive/root:{parent}:/children"
            body = {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
            async with session.post(url, headers=self._headers(), json=body) as resp:
                if resp.status in (200, 201, 409):
                    logger.info("OneDrive folder ensured: %s", folder)
                else:
                    logger.error("Failed to create folder: %s", await resp.text())

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        async with aiohttp.ClientSession() as session:
            with open(local_path, "rb") as f:
                content = f.read()
            url = f"{_GRAPH_API}/me/drive/root:{remote_path}:/content"
            async with session.put(url, headers=self._headers(), data=content) as resp:
                if resp.status in (200, 201):
                    logger.info("Uploaded to OneDrive: %s", remote_path)
                else:
                    raise RuntimeError(f"Upload failed ({resp.status}): {await resp.text()}")

    async def download_file(self, remote_path: str, local_path: str) -> None:
        async with aiohttp.ClientSession() as session:
            url = f"{_GRAPH_API}/me/drive/root:{remote_path}:/content"
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Download failed ({resp.status})")
                content = await resp.read()
                with open(local_path, "wb") as f:
                    f.write(content)
                logger.info("Downloaded from OneDrive: %s", remote_path)

    async def get_file_info(self, remote_path: str) -> RemoteFileInfo | None:
        async with aiohttp.ClientSession() as session:
            url = f"{_GRAPH_API}/me/drive/root:{remote_path}"
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                from datetime import datetime

                modified = None
                if "lastModifiedDateTime" in data:
                    modified = datetime.fromisoformat(
                        data["lastModifiedDateTime"].replace("Z", "+00:00")
                    )
                return RemoteFileInfo(
                    path=remote_path,
                    size=data.get("size", 0),
                    modified=modified,
                    hash=data.get("file", {}).get("hashes", {}).get("sha256Hash"),
                )

    async def list_files(self, folder: str) -> list[RemoteFileInfo]:
        async with aiohttp.ClientSession() as session:
            url = f"{_GRAPH_API}/me/drive/root:{folder}:/children"
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                files = []
                for item in data.get("value", []):
                    files.append(RemoteFileInfo(
                        path=f"{folder}/{item['name']}",
                        size=item.get("size", 0),
                    ))
                return files

    async def disconnect(self) -> None:
        self._access_token = None
        self._refresh_token_str = None
        logger.info("OneDrive disconnected")
