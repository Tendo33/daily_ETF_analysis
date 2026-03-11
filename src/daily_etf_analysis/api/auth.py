from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from daily_etf_analysis.config.settings import get_settings


def require_admin_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    settings = get_settings()
    if not settings.api_auth_enabled:
        return

    expected = (settings.api_admin_token or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="API admin token is not configured")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Authorization must use Bearer token"
        )

    token = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Invalid admin token")
