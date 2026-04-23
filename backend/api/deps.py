from dataclasses import dataclass

from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

from core.security import decode_access_token, verify_api_key

# JWT bearer for admin frontend
bearer_scheme = HTTPBearer(auto_error=False)

# API key header for platform clients
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    """JWT auth — used by the React admin frontend."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return payload


def get_platform_from_api_key(
    api_key: str = Security(api_key_header),
) -> str:
    """API key auth — used by platforms (PyRates, AlgoPython, ...).
    Returns the platform_id associated with the key."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    return verify_api_key(api_key)


@dataclass
class CallerContext:
    """Resolved auth context — works for both JWT admins and API-key platform clients."""
    is_admin: bool
    platform_id: str | None  # set when authenticated via API key; None for JWT admins


def get_caller(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    api_key: str = Security(api_key_header),
) -> CallerContext:
    """
    Accept either a valid admin JWT (Bearer token) or a platform API key (X-API-Key header).

    - JWT admin  → CallerContext(is_admin=True, platform_id=None)
                   platform_id MUST be supplied as a query param by the caller.
    - API key    → CallerContext(is_admin=False, platform_id=<from key>)
                   platform_id is already resolved from the key; query param is ignored.
    """
    if credentials and credentials.credentials:
        try:
            payload = decode_access_token(credentials.credentials)
            if payload.get("role") == "admin":
                return CallerContext(is_admin=True, platform_id=None)
        except Exception:
            pass  # fall through to API key check

    if api_key:
        try:
            pid = verify_api_key(api_key)
            return CallerContext(is_admin=False, platform_id=pid)
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Provide a valid Bearer token (admin) or X-API-Key (platform client).",
        headers={"WWW-Authenticate": "Bearer"},
    )
