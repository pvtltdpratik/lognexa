"""HTTP client for the Lognexa API (enrolment, heartbeat, events, rotation).

Uses httpx when available and falls back to the standard library, so the agent
has no hard third-party dependency. HTTPS is required unless the server is
localhost and ``insecure_http_ok`` is set.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from lognexa_agent.config import AgentConfig

log = logging.getLogger("lognexa.agent.client")

try:  # optional, nicer TLS handling
    import httpx

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover - fallback path
    _HAS_HTTPX = False


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message

    @property
    def retryable(self) -> bool:
        # 5xx, 429 and transport errors (status 0) are worth retrying.
        return self.status == 0 or self.status == 429 or self.status >= 500


class ApiClient:
    def __init__(self, config: AgentConfig, credential: str | None = None):
        self.config = config
        self.base = config.server_url
        self.credential = credential
        if self.base.startswith("http://"):
            host = self.base.split("://", 1)[1].split("/")[0].split(":")[0]
            if host not in ("localhost", "127.0.0.1", "::1") or not config.insecure_http_ok:
                raise SystemExit(
                    "Refusing to use plain HTTP. Use an https:// server URL, or set insecure_http_ok "
                    "for a localhost development server."
                )

    # --- low level -----------------------------------------------------------
    def _request(self, method: str, path: str, body: dict | None, auth: str | None) -> dict:
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json", "User-Agent": "lognexa-agent"}
        if auth:
            headers["Authorization"] = f"Bearer {auth}"
        if _HAS_HTTPX:
            return self._httpx(method, url, data, headers)
        return self._urllib(method, url, data, headers)

    def _httpx(self, method, url, data, headers) -> dict:
        try:
            resp = httpx.request(method, url, content=data, headers=headers, verify=self.config.verify_tls, timeout=30)
        except httpx.HTTPError as exc:
            raise ApiError(0, "transport_error", str(exc)) from exc
        return self._parse(resp.status_code, resp.content)

    def _urllib(self, method, url, data, headers) -> dict:
        import ssl

        ctx = None
        if url.startswith("https"):
            if self.config.verify_tls is False:
                ctx = ssl._create_unverified_context()
            elif isinstance(self.config.verify_tls, str):
                ctx = ssl.create_default_context(cafile=self.config.verify_tls)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                return self._parse(resp.status, resp.read())
        except urllib.error.HTTPError as exc:
            return self._parse(exc.code, exc.read())
        except (urllib.error.URLError, OSError) as exc:
            raise ApiError(0, "transport_error", str(exc)) from exc

    @staticmethod
    def _parse(status: int, raw: bytes) -> dict:
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        if status >= 400:
            err = body.get("error", {}) if isinstance(body, dict) else {}
            raise ApiError(status, err.get("code", "http_error"), err.get("message", f"HTTP {status}"))
        return body

    # --- API methods ---------------------------------------------------------
    def enroll(self, payload: dict) -> dict:
        return self._request("POST", "/agent/enroll", payload, auth=None)

    def heartbeat(self, payload: dict) -> dict:
        return self._request("POST", "/agent/heartbeat", payload, auth=self.credential)

    def send_events(self, events: list[dict]) -> dict:
        return self._request("POST", "/agent/events", {"events": events}, auth=self.credential)

    def rotate(self) -> dict:
        return self._request("POST", "/agent/rotate-credentials", None, auth=self.credential)
