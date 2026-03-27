"""Local HTTP server to receive OAuth2 callback."""

from __future__ import annotations

import asyncio
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth2 authorization code."""

    auth_code: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        if code:
            _CallbackHandler.auth_code = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization successful!</h2>"
                b"<p>You can close this window and return to Termplus.</p>"
                b"</body></html>"
            )
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h2>Authorization failed: {error}</h2></body></html>".encode()
            )

    def log_message(self, format, *args) -> None:
        logger.debug("OAuth callback: %s", format % args)


class OAuthCallbackServer:
    """Starts a local HTTP server to capture OAuth2 redirect."""

    def __init__(self, port: int = 8765) -> None:
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self._port}/callback"

    def start(self) -> None:
        """Start the callback server in a background thread."""
        _CallbackHandler.auth_code = None
        self._server = HTTPServer(("127.0.0.1", self._port), _CallbackHandler)
        self._thread = Thread(target=self._server.handle_request, daemon=True)
        self._thread.start()
        logger.info("OAuth callback server started on port %d", self._port)

    async def wait_for_code(self, timeout: float = 120) -> str | None:
        """Wait for the authorization code. Returns None on timeout."""
        elapsed = 0.0
        while elapsed < timeout:
            if _CallbackHandler.auth_code is not None:
                code = _CallbackHandler.auth_code
                _CallbackHandler.auth_code = None
                self.stop()
                return code
            await asyncio.sleep(0.5)
            elapsed += 0.5

        self.stop()
        return None

    def stop(self) -> None:
        """Shut down the callback server."""
        if self._server:
            self._server.server_close()
            self._server = None
        logger.info("OAuth callback server stopped")
