"""Authentication and authorisation for dashboard users and endpoint agents.

* Humans: static bearer tokens per role (``analyst`` < ``admin``) configured in
  the environment. Comparison is constant-time.
* Agents: per-device credential ``<device_uid>.<secret>``. Only the SHA-256 of
  the 256-bit random secret is stored, so a database leak does not reveal usable
  credentials. Revoked devices are rejected.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import APIError
from app.models import Device

ROLE_RANK = {"analyst": 1, "admin": 2}


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def new_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


# --- dashboard users -----------------------------------------------------------------
@dataclass(frozen=True)
class Principal:
    role: str

    def has(self, role: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[role]


def resolve_principal(token: str | None) -> Principal | None:
    if not token:
        return None
    s = get_settings()
    # Check every configured token so timing does not reveal which role matched.
    matched = None
    for role, expected in (("admin", s.admin_token), ("analyst", s.analyst_token)):
        if expected and hmac.compare_digest(token.encode(), expected.encode()) and matched is None:
            matched = Principal(role)
    return matched


def optional_principal(request: Request) -> Principal | None:
    token = _bearer(request)
    principal = resolve_principal(token)
    if token and principal is None:
        raise APIError(401, "invalid_token", "The access token is not valid")
    return principal


def require_role(role: str):
    def dependency(request: Request) -> Principal:
        s = get_settings()
        if not (s.admin_token or s.analyst_token):
            raise APIError(
                503, "auth_not_configured",
                "Endpoint monitoring is disabled until LOGNEXA_ADMIN_TOKEN / LOGNEXA_ANALYST_TOKEN are configured.",
            )
        principal = optional_principal(request)
        if principal is None:
            raise APIError(401, "authentication_required", "Sign in with an analyst or admin token")
        if not principal.has(role):
            raise APIError(403, "forbidden", f"This action requires the '{role}' role")
        return principal

    return dependency


require_analyst = require_role("analyst")
require_admin = require_role("admin")


# --- transport security for agents ----------------------------------------------------
def client_ip(request: Request) -> str | None:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def is_secure(request: Request) -> bool:
    if get_settings().trust_proxy_headers and request.headers.get("x-forwarded-proto", "").lower() == "https":
        return True
    return request.url.scheme == "https"


def _is_loopback(host: str | None) -> bool:
    if host in ("localhost", "testclient"):
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def enforce_agent_transport(request: Request) -> None:
    if get_settings().agent_require_https and not is_secure(request) and not _is_loopback(client_ip(request)):
        raise APIError(403, "https_required", "Agents must connect over HTTPS")


# --- agents ----------------------------------------------------------------------------
def issue_device_credential(device_uid: str) -> tuple[str, str]:
    """Return (credential to give the agent, hash to store)."""
    secret = new_secret()
    return f"{device_uid}.{secret}", hash_secret(secret)


def authenticate_device(request: Request, db: Session = Depends(get_db)) -> Device:
    enforce_agent_transport(request)
    token = _bearer(request)
    if not token or "." not in token:
        raise APIError(401, "device_auth_required", "Missing or malformed device credential")
    device_uid, _, secret = token.partition(".")
    device = db.scalar(select(Device).where(Device.device_uid == device_uid))
    # Hash even when the device is unknown to keep timing uniform.
    presented = hash_secret(secret)
    if device is None or not hmac.compare_digest(presented, device.credential_hash):
        raise APIError(401, "invalid_device_credential", "Device credential is not valid")
    if device.status == "revoked":
        raise APIError(403, "device_revoked", "This device has been revoked; re-enrol it with a new token")
    device.last_seen_at = datetime.utcnow()
    ip = client_ip(request)
    if ip:
        device.ip_address = ip[:45]
    return device
