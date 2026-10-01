"""Keycloak OIDC integration (enterprise auth layer).

The abstract specifies Keycloak for authentication. MineTrace keeps its local
argon2 + JWT RBAC as the offline fallback (a mine office cannot always reach an
IdP), and when MINETRACE_KEYCLOAK_ENABLED=true this module provides:

- Authorization-Code login (browser redirect) for the React portal
- Token exchange against the realm's token endpoint
- Role mapping: Keycloak realm roles FOREMAN/SUPERVISOR/ENGINEER/MANAGER/GM
  map onto the same MineTrace role codes used by the local RBAC, so the rest
  of the app is IdP-agnostic.
"""
from __future__ import annotations

import logging
import secrets

import httpx

from app.config import settings

logger = logging.getLogger("minetrace.keycloak")

# MineTrace role codes the portal recognises (subset of the approval chain;
# higher roles in the chain are granted via the roles master in-app).
KNOWN_ROLES = {"FOREMAN", "SUPERVISOR", "ENGINEER", "MANAGER", "GM"}

_PENDING_STATES: set[str] = set()


def enabled() -> bool:
    return settings.keycloak_enabled


def realm_base() -> str:
    return (
        f"{settings.keycloak_server_url}/realms/{settings.keycloak_realm}"
    )


def admin_base() -> str:
    return (
        f"{settings.keycloak_server_url}/admin/realms/{settings.keycloak_realm}"
    )


def authorize_url(redirect_uri: str) -> tuple[str, str]:
    """Build the OIDC authorization redirect; returns (url, state)."""
    state = secrets.token_urlsafe(24)
    _PENDING_STATES.add(state)
    url = (
        f"{realm_base()}/protocol/openid-connect/auth"
        f"?client_id={settings.keycloak_client_id}"
        f"&response_type=code&scope=openid"
        f"&redirect_uri={redirect_uri}&state={state}"
    )
    return url, state


def consume_state(state: str) -> bool:
    """One-time state validation (CSRF protection for the code flow)."""
    if state in _PENDING_STATES:
        _PENDING_STATES.discard(state)
        return True
    return False


def exchange_code(code: str, redirect_uri: str) -> dict | None:
    """Exchange an authorization code for tokens."""
    try:
        resp = httpx.post(
            f"{realm_base()}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.keycloak_client_id,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=15.0,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Keycloak token exchange failed: %s", resp.status_code)
    except Exception:
        logger.exception("Keycloak token exchange error")
    return None


def userinfo(access_token: str) -> dict | None:
    """Validate a bearer token against the realm's userinfo endpoint."""
    try:
        resp = httpx.get(
            f"{realm_base()}/protocol/openid-connect/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Keycloak userinfo rejected token: %s", resp.status_code)
    except Exception:
        logger.exception("Keycloak userinfo error")
    return None


def decode_jwt_payload(access_token: str) -> dict:
    """Decode the JWT payload (unverified) to read realm_access.

    Safe here because callers only use it AFTER kc.userinfo() validated the
    token against the realm's userinfo endpoint; Keycloak's default userinfo
    response omits realm_access, which lives in the token claims.
    """
    import base64
    import json as _json

    try:
        payload_b64 = access_token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        return _json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        logger.warning("could not decode Keycloak token payload")
        return {}


def roles_for(access_token: str, info: dict) -> dict:
    """Best-effort realm roles: JWT claims first, userinfo fallback."""
    claims = decode_jwt_payload(access_token) if access_token else {}
    realm_roles = claims.get("realm_access", {}).get("roles") or info.get(
        "realm_access", {}
    ).get("roles", [])
    return {
        "realm_roles": realm_roles,
        "minetrace_role": map_role({"realm_access": {"roles": realm_roles}}),
    }


def map_role(token_payload: dict) -> str | None:
    """Map realm roles onto a MineTrace role code (highest rank wins)."""
    realm_roles = (
        token_payload.get("realm_access", {}).get("roles", [])
        if isinstance(token_payload, dict)
        else []
    )
    hits = [r.upper() for r in realm_roles if r.upper() in KNOWN_ROLES]
    if not hits:
        return None
    rank_order = ["FOREMAN", "SUPERVISOR", "ENGINEER", "MANAGER", "GM"]
    return max(hits, key=rank_order.index)
