"""OneDrive cloud provider — Microsoft Graph API via MSAL Device Code Flow."""

from __future__ import annotations

import logging

import aiohttp
import msal

from rlqshell.core.sync.providers.base import AbstractCloudProvider, RemoteFileInfo

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.microsoft.com/v1.0"
_AUTHORITY = "https://login.microsoftonline.com/consumers"
_SCOPES = ["Files.ReadWrite"]


class OneDriveProvider(AbstractCloudProvider):
    """OneDrive Personal sync via MSAL Device Code Flow + aiohttp Graph API."""

    def __init__(
        self,
        client_id: str,
        proxy_url: str | None = None,
    ) -> None:
        super().__init__(proxy_url=proxy_url)
        self._client_id = client_id
        self._cache = msal.SerializableTokenCache()
        self._app: msal.PublicClientApplication | None = None

    def _get_app(self) -> msal.PublicClientApplication:
        if self._app is None:
            self._app = msal.PublicClientApplication(
                self._client_id,
                authority=_AUTHORITY,
                token_cache=self._cache,
            )
        return self._app

    # ------------------------------------------------------------------
    # Device Code Flow (called from DeviceCodeDialog)
    # ------------------------------------------------------------------

    def initiate_device_flow(self) -> dict:
        """Start Device Code Flow. Returns dict with user_code, verification_uri."""
        app = self._get_app()
        flow = app.initiate_device_flow(scopes=_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(
                f"Device flow init failed: "
                f"{flow.get('error_description', 'unknown error')}"
            )
        return flow

    def complete_device_flow(self, flow: dict) -> bool:
        """Block until user confirms login. Must run in a worker thread."""
        app = self._get_app()
        result = app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            logger.info("OneDrive Device Code Flow completed")
            return True
        raise RuntimeError(
            f"Authentication failed: "
            f"{result.get('error_description', result.get('error', 'unknown'))}"
        )

    def try_silent_auth(self) -> bool:
        """Acquire token silently from cache. Returns True if a valid token exists."""
        app = self._get_app()
        accounts = app.get_accounts()
        if not accounts:
            return False
        result = app.acquire_token_silent(_SCOPES, account=accounts[0])
        return bool(result and "access_token" in result)

    def _ensure_token(self, force_refresh: bool = False) -> str:
        """Get a valid access token (from cache or via silent refresh)."""
        app = self._get_app()
        accounts = app.get_accounts()
        if not accounts:
            raise RuntimeError("No OneDrive account — authenticate first")
        result = app.acquire_token_silent(
            _SCOPES, account=accounts[0], force_refresh=force_refresh,
        )
        if result and "access_token" in result:
            return result["access_token"]
        raise RuntimeError("Token acquisition failed — re-authenticate required")

    # ------------------------------------------------------------------
    # AbstractCloudProvider interface
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "OneDrive"

    @property
    def connectivity_check_url(self) -> str:
        return f"{_GRAPH_API}/$metadata"

    def is_authenticated(self) -> bool:
        try:
            return self.try_silent_auth()
        except Exception:
            return False

    def get_tokens(self) -> tuple[str, str] | None:
        """Return serialized MSAL cache as (cache_data, '') for persistence."""
        if self._cache.has_state_changed or self._get_app().get_accounts():
            data = self._cache.serialize()
            if data:
                return (data, "")
        return None

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        """Restore MSAL cache from persisted data."""
        # access_token holds the serialized MSAL cache; refresh_token is unused
        if access_token:
            self._cache.deserialize(access_token)
            # Recreate the app to pick up the restored cache
            self._app = None

    # ------------------------------------------------------------------
    # HTTP helpers (aiohttp for async Graph API calls)
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        token = self._ensure_token()
        return {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Execute an HTTP request with automatic 401 retry (silent token refresh)."""
        session = await self._get_session()
        kwargs.setdefault("proxy", self._proxy_url)
        kwargs["headers"] = self._headers()

        resp = await session.request(method, url, **kwargs)
        if resp.status == 401:
            resp.release()
            try:
                token = self._ensure_token(force_refresh=True)
                kwargs["headers"] = {"Authorization": f"Bearer {token}"}
                resp = await session.request(method, url, **kwargs)
            except RuntimeError:
                pass  # return the 401 response
        return resp

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    async def create_folder(self, folder: str) -> None:
        url = f"{_GRAPH_API}/me/drive/root:{folder}"
        resp = await self._request("GET", url)
        async with resp:
            if resp.status == 200:
                return

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
        # Clear MSAL cache and accounts
        app = self._get_app()
        for account in app.get_accounts():
            app.remove_account(account)
        self._cache = msal.SerializableTokenCache()
        self._app = None
        await self.close()
        logger.info("OneDrive disconnected")
