from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.services import keycloak as kc

router = APIRouter(prefix="/auth/enterprise", tags=["Enterprise SSO (Keycloak)"])


def _redirect_uri(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/api/v1/auth/enterprise/callback"


@router.get("/status")
def status():
    return {
        "keycloak_enabled": kc.enabled(),
        "realm": settings.keycloak_realm,
        "server_url": settings.keycloak_server_url,
        "client_id": settings.keycloak_client_id,
        "fallback": None if kc.enabled() else "local argon2 + JWT RBAC",
    }


@router.get("/login")
def login(request: Request):
    """Redirect the browser to Keycloak's authorization endpoint."""
    if not kc.enabled():
        raise HTTPException(503, "Keycloak SSO disabled (offline fallback active)")
    url, _state = kc.authorize_url(_redirect_uri(request))
    return RedirectResponse(url)


@router.get("/callback")
def callback(code: str, state: str, request: Request):
    if not kc.enabled():
        raise HTTPException(503, "Keycloak SSO disabled")
    if not kc.consume_state(state):
        raise HTTPException(400, "Invalid OAuth state")
    tokens = kc.exchange_code(code, _redirect_uri(request))
    if not tokens or "access_token" not in tokens:
        raise HTTPException(401, "Token exchange failed")
    info = kc.userinfo(tokens["access_token"]) or {}
    roles = kc.roles_for(tokens["access_token"], info)
    return {
        "preferred_username": info.get("preferred_username"),
        "name": info.get("name"),
        "email": info.get("email"),
        "minetrace_role": roles["minetrace_role"],
        "expires_in": tokens.get("expires_in"),
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
    }


@router.get("/me")
def me(request: Request):
    """Validate a Keycloak bearer token and map it to a MineTrace role."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token required")
    info = kc.userinfo(auth.split(" ", 1)[1])
    if not info:
        raise HTTPException(401, "Token rejected by Keycloak")
    roles = kc.roles_for(auth.split(" ", 1)[1], info)
    return {
        "preferred_username": info.get("preferred_username"),
        "minetrace_role": roles["minetrace_role"],
        "realm_roles": roles["realm_roles"],
    }
