"""Dropbox cloud provider — Dropbox API v2 with PKCE."""

from __future__ import annotations

import hashlib
import logging
import secrets

import aiohttp

from rlqshell.core.sync.providers.base import AbstractCloudProvider, RemoteFileInfo

logger = logging.getLogger(__name__)

_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
_API_URL = "https://api.dropboxapi.com/2"
_CONTENT_URL = "https://content.dropboxapi.com/2"
_APP_FOLDER = "/Apps/RLQShell"


class DropboxProvider(AbstractCloudProvider):
    """Dropbox sync via Dropbox API v2."""

    def __init__(
        self,
        app_key: str,
        redirect_uri: str = "http://localhost:8765/callback",
    ) -> None:
        self._app_key = app_key
        self._redirect_uri = redirect_uri
        self._access_token: str | None = None
        self._refresh_token_str: str | None = None

        # PKCE
        self._code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(self._code_verifier.encode()).digest()
        import base64

        self._code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    @property
    def provider_name(self) -> str:
        return "Dropbox"

    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def get_auth_url(self) -> str:
        return (
            f"{_AUTH_URL}?"
            f"client_id={self._app_key}"
            f"&redirect_uri={self._redirect_uri}"
            f"&response_type=code"
            f"&code_challenge={self._code_challenge}"
            f"&code_challenge_method=S256"
            f"&token_access_type=offline"
        )

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        self._access_token = access_token
        self._refresh_token_str = refresh_token

    async def authenticate(self, auth_code: str) -> bool:
        async with aiohttp.ClientSession() as session:
            data = {
                "code": auth_code,
                "grant_type": "authorization_code",
                "client_id": self._app_key,
                "redirect_uri": self._redirect_uri,
                "code_verifier": self._code_verifier,
            }
            async with session.post(_TOKEN_URL, data=data) as resp:
                if resp.status != 200:
                    logger.error("Dropbox auth failed: %s", await resp.text())
                    return False
                result = await resp.json()
                self._access_token = result["access_token"]
                self._refresh_token_str = result.get("refresh_token")
                logger.info("Dropbox authenticated")
                return True

    async def refresh_token(self) -> bool:
        if not self._refresh_token_str:
            return False
        async with aiohttp.ClientSession() as session:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token_str,
                "client_id": self._app_key,
            }
            async with session.post(_TOKEN_URL, data=data) as resp:
                if resp.status != 200:
                    return False
                result = await resp.json()
                self._access_token = result["access_token"]
                return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def create_folder(self, folder: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_API_URL}/files/create_folder_v2",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"path": folder, "autorename": False},
            ) as resp:
                if resp.status in (200, 409):  # 409 = already exists
                    return
                # May also get "path/conflict/folder" error
                text = await resp.text()
                if "conflict" in text.lower():
                    return
                logger.warning("Dropbox create_folder: %s", text)

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        import json

        with open(local_path, "rb") as f:
            content = f.read()

        headers = self._headers()
        headers["Content-Type"] = "application/octet-stream"
        headers["Dropbox-API-Arg"] = json.dumps({
            "path": remote_path,
            "mode": "overwrite",
            "autorename": False,
            "mute": True,
        })

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_CONTENT_URL}/files/upload", headers=headers, data=content
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Upload failed: {await resp.text()}")
                logger.info("Uploaded to Dropbox: %s", remote_path)

    async def download_file(self, remote_path: str, local_path: str) -> None:
        import json

        headers = self._headers()
        headers["Dropbox-API-Arg"] = json.dumps({"path": remote_path})

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_CONTENT_URL}/files/download", headers=headers
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Download failed ({resp.status})")
                content = await resp.read()
                with open(local_path, "wb") as f:
                    f.write(content)
                logger.info("Downloaded from Dropbox: %s", remote_path)

    async def get_file_info(self, remote_path: str) -> RemoteFileInfo | None:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_API_URL}/files/get_metadata",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"path": remote_path},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                from datetime import datetime

                modified = None
                if "server_modified" in data:
                    modified = datetime.fromisoformat(
                        data["server_modified"].replace("Z", "+00:00")
                    )
                return RemoteFileInfo(
                    path=remote_path,
                    size=data.get("size", 0),
                    modified=modified,
                    hash=data.get("content_hash"),
                )

    async def list_files(self, folder: str) -> list[RemoteFileInfo]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_API_URL}/files/list_folder",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"path": folder},
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    RemoteFileInfo(
                        path=entry["path_display"],
                        size=entry.get("size", 0),
                    )
                    for entry in data.get("entries", [])
                    if entry.get(".tag") == "file"
                ]

    async def disconnect(self) -> None:
        if self._access_token:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{_API_URL}/auth/token/revoke",
                    headers=self._headers(),
                )
        self._access_token = None
        self._refresh_token_str = None
        logger.info("Dropbox disconnected")
