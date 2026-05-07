"""API dependencies (dependency injection)."""

from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.core.config import AppSettings, get_settings
from kb_curator.services.db import get_session_factory


def get_app_settings() -> AppSettings:
    """FastAPI dependency for application settings."""
    return get_settings()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


SettingsDep = Annotated[AppSettings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

# ============================================================
# Token Authentication
# ============================================================

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: AppSettings = Depends(get_app_settings),
) -> str | None:
    """Verify JWT token and return the user identifier.

    Returns None when authentication is disabled (auth.enabled = False).
    Raises 401 when authentication is enabled but the token is missing or invalid.
    """
    if not settings.auth.enabled:
        return None

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        import jwt

        payload = jwt.decode(
            token,
            settings.auth.secret_key,
            algorithms=[settings.auth.algorithm],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        return user_id
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PyJWT not installed — cannot verify tokens",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


UserDep = Annotated[str | None, Depends(get_current_user)]
