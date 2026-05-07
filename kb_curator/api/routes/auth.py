"""Authentication API routes (token issuance)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from kb_curator.api.deps import get_app_settings
from kb_curator.core.config import AppSettings

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/token", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    settings: AppSettings = Depends(get_app_settings),
) -> TokenResponse:
    """Issue a JWT token.

    This is a simple username/password check. In production, replace with
    a proper identity provider or user database.
    """
    if not settings.auth.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is not enabled",
        )

    # Simple credential check — replace with real user store in production
    # Default admin:admin for development
    valid_users = {
        "admin": "admin",
    }
    if body.username not in valid_users or valid_users[body.username] != body.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    try:
        import jwt
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PyJWT not installed — cannot issue tokens",
        )

    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=settings.auth.token_expire_minutes)
    payload = {
        "sub": body.username,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.auth.secret_key, algorithm=settings.auth.algorithm)

    return TokenResponse(
        access_token=token,
        expires_in=settings.auth.token_expire_minutes * 60,
    )
