"""OneDrive cloud provider — Microsoft Graph API (Personal + Business)."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets

import aiohttp

from rlqshell.core.sync.providers.base import AbstractCloudProvider, RemoteFileInfo

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.microsoft.com/v1.0"
_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0"
_SCOPES = "Files.ReadWrite offline_access"


class OneDriveProvider(AbstractCloudProvider):
    """OneDrive sync via Microsoft Graph API (Personal + Business)."""

    def __init__(
        self,
        client_id: str,
        redirect_uri: str = "http://localhost:8765/callback",
        proxy_url: str | None = None,
    ) -> None:
        super().__init__(proxy_url=proxy_url)
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._access_token: str | None = None
        self._refresh_token_str: str | None = None

        # PKCE
        self._code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(self._code_verifier.encode()).digest()
        self._code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    @property
    def provider_name(self) -> str:
        return "OneDrive"

    @property
    def connectivity_check_url(self) -> str:
        return f"{_GRAPH_API}/$metadata"

    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def get_auth_url(self) -> str:
        return (
            f"{_AUTH_URL}/authorize?"
            f"client_id={self._client_id}&response_type=code"
            f"&redirect_uri={self._redirect_uri}"
            f"&scope={_SCOPES.replace(' ', '%20')}"
            f"&code_challenge={self._code_challenge}"
            f"&code_challenge_method=S256"
        )

    def get_tokens(self) -> tuple[str, str] | None:
        if self._access_token and self._refresh_token_str:
            return (self._access_token, self._refresh_token_str)
        return None

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        """Restore tokens from encrypted storage."""
        self._access_token = access_token
        self._refresh_token_str = refresh_token

    async def authenticate(self, auth_code: str) -> bool:
        session = await self._get_session()
        data = {
            "client_id": self._client_id,
            "code": auth_code,
            "redirect_uri": self._redirect_uri,
            "grant_type": "authorization_code",
            "scope": _SCOPES,
            "code_verifier": self._code_verifier,
        }
        async with session.post(
            f"{_AUTH_URL}/token", data=data, proxy=self._proxy_url
        ) as resp:
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
        session = await self._get_session()
        data = {
            "client_id": self._client_id,
            "refresh_token": self._refresh_token_str,
            "grant_type": "refresh_token",
            "scope": _SCOPES,
        }
        async with session.post(
            f"{_AUTH_URL}/token", data=data, proxy=self._proxy_url
        ) as resp:
            if resp.status != 200:
                logger.error("OneDrive token refresh failed")
                return False
            result = await resp.json()
            self._access_token = result["access_token"]
            self._refresh_token_str = result.get("refresh_token", self._refresh_token_str)
            return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Execute an HTTP request with automatic 401 retry (token refresh)."""
        session = await self._get_session()
        kwargs.setdefault("proxy", self._proxy_url)
        kwargs.setdefault("headers", self._headers())

        resp = await session.request(method, url, **kwargs)
        if resp.status == 401:
            resp.release()
            if await self.refresh_token():
                kwargs["headers"] = self._headers()
                resp = await session.request(method, url, **kwargs)
        return resp

    async def create_folder(self, folder: str) -> None:
        # Check if exists
        url = f"{_GRAPH_API}/me/drive/root:{folder}"
        resp = await self._request("GET", url)
        async with resp:
            if resp.status == 200:
                return

        # Create
        parent = "/".join(folder.rstrip("/").split("/")[:-1]) or "/"
        name = folder.rstrip("/").split("/")[-1]
        url = f"{_GRAPH_API}/me/drive/root:{parent}:/children"
        body = {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
        resp = await self._request("POST", url, json=body)
        async with resp:
            if resp.status in (200, 201, 409):
                logger.info("OneDrive folder ensured: %s", folder)
            else:
                logger.error("Failed to create folder: %s", await resp.text())

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        with open(local_path, "rb") as f:
            content = f.read()
        url = f"{_GRAPH_API}/me/drive/root:{remote_path}:/content"
        resp = await self._request("PUT", url, data=content)
        async with resp:
            if resp.status in (200, 201):
                logger.info("Uploaded to OneDrive: %s", remote_path)
            else:
                raise RuntimeError(f"Upload failed ({resp.status}): {await resp.text()}")

    async def download_file(self, remote_path: str, local_path: str) -> None:
        url = f"{_GRAPH_API}/me/drive/root:{remote_path}:/content"
        resp = await self._request("GET", url)
        async with resp:
            if resp.status != 200:
                raise RuntimeError(f"Download failed ({resp.status})")
            content = await resp.read()
            with open(local_path, "wb") as f:
                f.write(content)
            logger.info("Downloaded from OneDrive: %s", remote_path)

    async def get_file_info(self, remote_path: str) -> RemoteFileInfo | None:
        url = f"{_GRAPH_API}/me/drive/root:{remote_path}"
        resp = await self._request("GET", url)
        async with resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            from datetime import datetime

            modified = None
            if "lastModifiedDateTime" in data:
                modified = datetime.fromisoformat(
                    data["lastModifiedDateTime"].replace("Z", "+00:00")
                )
            hashes = data.get("file", {}).get("hashes", {})
            file_hash = hashes.get("sha256Hash") or hashes.get("quickXorHash")
            return RemoteFileInfo(
                path=remote_path,
                size=data.get("size", 0),
                modified=modified,
                hash=file_hash,
            )

    async def list_files(self, folder: str) -> list[RemoteFileInfo]:
        url = f"{_GRAPH_API}/me/drive/root:{folder}:/children"
        resp = await self._request("GET", url)
        async with resp:
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
        await self.close()
        logger.info("OneDrive disconnected")
