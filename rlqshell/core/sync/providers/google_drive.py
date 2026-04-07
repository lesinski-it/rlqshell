"""Google Drive cloud provider — Google Drive API v3."""

from __future__ import annotations

import logging

import aiohttp

from rlqshell.core.sync.providers.base import AbstractCloudProvider, RemoteFileInfo

logger = logging.getLogger(__name__)

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API_URL = "https://www.googleapis.com/drive/v3"
_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3"
_SCOPES = "https://www.googleapis.com/auth/drive.file"
_APP_FOLDER = "RLQShell"


class GoogleDriveProvider(AbstractCloudProvider):
    """Google Drive sync via Drive API v3."""

    def __init__(
        self,
        client_id: str,
        client_secret: str = "",
        redirect_uri: str = "http://localhost:8765/callback",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._access_token: str | None = None
        self._refresh_token_str: str | None = None
        self._folder_id: str | None = None

    @property
    def provider_name(self) -> str:
        return "Google Drive"

    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def get_auth_url(self) -> str:
        return (
            f"{_AUTH_URL}?"
            f"client_id={self._client_id}"
            f"&redirect_uri={self._redirect_uri}"
            f"&response_type=code"
            f"&scope={_SCOPES}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        self._access_token = access_token
        self._refresh_token_str = refresh_token

    async def authenticate(self, auth_code: str) -> bool:
        async with aiohttp.ClientSession() as session:
            data = {
                "code": auth_code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            }
            async with session.post(_TOKEN_URL, data=data) as resp:
                if resp.status != 200:
                    logger.error("Google auth failed: %s", await resp.text())
                    return False
                result = await resp.json()
                self._access_token = result["access_token"]
                self._refresh_token_str = result.get("refresh_token")
                logger.info("Google Drive authenticated")
                return True

    async def refresh_token(self) -> bool:
        if not self._refresh_token_str:
            return False
        async with aiohttp.ClientSession() as session:
            data = {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token_str,
                "grant_type": "refresh_token",
            }
            async with session.post(_TOKEN_URL, data=data) as resp:
                if resp.status != 200:
                    return False
                result = await resp.json()
                self._access_token = result["access_token"]
                return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _ensure_folder(self) -> str:
        """Get or create the app folder, returning its ID."""
        if self._folder_id:
            return self._folder_id

        async with aiohttp.ClientSession() as session:
            # Search for existing folder
            query = f"name='{_APP_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            url = f"{_API_URL}/files?q={query}&fields=files(id,name)"
            async with session.get(url, headers=self._headers()) as resp:
                data = await resp.json()
                files = data.get("files", [])
                if files:
                    self._folder_id = files[0]["id"]
                    return self._folder_id

            # Create folder
            meta = {
                "name": _APP_FOLDER,
                "mimeType": "application/vnd.google-apps.folder",
            }
            async with session.post(
                f"{_API_URL}/files", headers=self._headers(), json=meta
            ) as resp:
                data = await resp.json()
                self._folder_id = data["id"]
                return self._folder_id

    async def create_folder(self, folder: str) -> None:
        await self._ensure_folder()

    async def _find_file(self, name: str) -> str | None:
        """Find a file by name in the app folder, return its ID."""
        folder_id = await self._ensure_folder()
        async with aiohttp.ClientSession() as session:
            query = f"name='{name}' and '{folder_id}' in parents and trashed=false"
            url = f"{_API_URL}/files?q={query}&fields=files(id)"
            async with session.get(url, headers=self._headers()) as resp:
                data = await resp.json()
                files = data.get("files", [])
                return files[0]["id"] if files else None

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        folder_id = await self._ensure_folder()
        filename = remote_path.split("/")[-1]

        with open(local_path, "rb") as f:
            content = f.read()

        existing_id = await self._find_file(filename)

        async with aiohttp.ClientSession() as session:
            headers = self._headers()
            if existing_id:
                # Update existing file
                url = f"{_UPLOAD_URL}/files/{existing_id}?uploadType=media"
                async with session.patch(url, headers=headers, data=content) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"Upload failed: {await resp.text()}")
            else:
                # Create new file (multipart)
                import json

                meta = json.dumps({"name": filename, "parents": [folder_id]})
                boundary = "rlqshell_boundary"
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{meta}\r\n"
                    f"--{boundary}\r\n"
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode() + content + f"\r\n--{boundary}--".encode()

                headers["Content-Type"] = f"multipart/related; boundary={boundary}"
                url = f"{_UPLOAD_URL}/files?uploadType=multipart"
                async with session.post(url, headers=headers, data=body) as resp:
                    if resp.status not in (200, 201):
                        raise RuntimeError(f"Upload failed: {await resp.text()}")

        logger.info("Uploaded to Google Drive: %s", filename)

    async def download_file(self, remote_path: str, local_path: str) -> None:
        filename = remote_path.split("/")[-1]
        file_id = await self._find_file(filename)
        if not file_id:
            raise FileNotFoundError(f"File not found in Drive: {filename}")

        async with aiohttp.ClientSession() as session:
            url = f"{_API_URL}/files/{file_id}?alt=media"
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Download failed ({resp.status})")
                content = await resp.read()
                with open(local_path, "wb") as f:
                    f.write(content)

        logger.info("Downloaded from Google Drive: %s", filename)

    async def get_file_info(self, remote_path: str) -> RemoteFileInfo | None:
        filename = remote_path.split("/")[-1]
        file_id = await self._find_file(filename)
        if not file_id:
            return None

        async with aiohttp.ClientSession() as session:
            url = f"{_API_URL}/files/{file_id}?fields=id,name,size,modifiedTime,md5Checksum"
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                from datetime import datetime

                modified = None
                if "modifiedTime" in data:
                    modified = datetime.fromisoformat(
                        data["modifiedTime"].replace("Z", "+00:00")
                    )
                return RemoteFileInfo(
                    path=remote_path,
                    size=int(data.get("size", 0)),
                    modified=modified,
                    hash=data.get("md5Checksum"),
                )

    async def list_files(self, folder: str) -> list[RemoteFileInfo]:
        folder_id = await self._ensure_folder()
        async with aiohttp.ClientSession() as session:
            query = f"'{folder_id}' in parents and trashed=false"
            url = f"{_API_URL}/files?q={query}&fields=files(id,name,size)"
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    RemoteFileInfo(path=f"{folder}/{f['name']}", size=int(f.get("size", 0)))
                    for f in data.get("files", [])
                ]

    async def disconnect(self) -> None:
        self._access_token = None
        self._refresh_token_str = None
        self._folder_id = None
        logger.info("Google Drive disconnected")
