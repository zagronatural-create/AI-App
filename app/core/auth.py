from __future__ import annotations

import json
from functools import lru_cache
from typing import Callable, Mapping

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthUser(BaseModel):
    user_id: str
    roles: list[str]
    token_source: str


@lru_cache(maxsize=1)
def _token_map() -> dict[str, dict]:
    raw = settings.api_token_map_json.strip()
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid API_TOKEN_MAP_JSON configuration") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("API_TOKEN_MAP_JSON must be a JSON object")
    return parsed


def _dev_user() -> AuthUser:
    return AuthUser(
        user_id="dev-local",
        roles=[
            "admin",
            "viewer",
            "qa_analyst",
            "qa_manager",
            "compliance_manager",
            "ops_scheduler",
        ],
        token_source="dev-bypass",
    )


def _parse_header_token(auth_header: str | None, api_key_header: str | None) -> tuple[str, str] | None:
    if auth_header:
        parts = auth_header.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip(), "authorization"
    if api_key_header and api_key_header.strip():
        return api_key_header.strip(), "x-api-key"
    return None


def resolve_user_from_headers(headers: Mapping[str, str]) -> AuthUser | None:
    if not settings.auth_enabled:
        return _dev_user()

    parsed = _parse_header_token(
        headers.get("Authorization") or headers.get("authorization"),
        headers.get("X-API-Key") or headers.get("x-api-key"),
    )
    if not parsed:
        return None

    token, source = parsed
    info = _token_map().get(token)
    if not info:
        return None

    user_id = str(info.get("user_id", "unknown"))
    roles = info.get("roles", [])
    if not isinstance(roles, list):
        roles = []
    return AuthUser(user_id=user_id, roles=[str(r) for r in roles], token_source=source)


def get_current_user(
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_scheme),
) -> AuthUser:
    headers = {}
    if bearer:
        headers["authorization"] = f"Bearer {bearer.credentials}"
    if api_key:
        headers["x-api-key"] = api_key

    user = resolve_user_from_headers(headers)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token",
        )
    return user


def require_roles(*required_roles: str) -> Callable:
    required = {r.strip() for r in required_roles if r.strip()}

    def dependency(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if "admin" in current_user.roles:
            return current_user
        if required and not required.intersection(set(current_user.roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {sorted(required)}",
            )
        return current_user

    return dependency
