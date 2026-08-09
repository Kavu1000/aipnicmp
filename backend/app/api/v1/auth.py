"""Sign in, sign out, and who am I."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.services.auth import (
    current_user_or_none,
    issue_session_token,
    upsert_user_from_claims,
    verify_google_id_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleSignIn(BaseModel):
    # Google Identity Services calls this field `credential`; it is the id
    # token the button produces.
    credential: str = Field(min_length=16, max_length=8192)


def _set_session_cookie(response: Response, token: str) -> None:
    """Store the session where page scripts cannot read it.

    httpOnly is the point: a cross-site scripting bug anywhere in the app would
    otherwise hand over the session. SameSite=Lax stops another site's form
    posting with it. Secure is set outside development, because a cookie sent
    over plain HTTP can simply be read off the wire.
    """
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        secure=not settings.is_dev,
        samesite="lax",
        path="/",
    )


@router.get("/session")
async def session_state(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """What the sign-in screen needs to render itself.

    Deliberately 200 whether or not anyone is signed in — "nobody is signed in"
    is the normal first state of the application, not an error, and returning
    401 for it would make every page load look like a failure.
    """
    user = await current_user_or_none(request, session)
    return {
        "auth_enabled": settings.auth_enabled,
        # Public by design; it identifies the application to Google.
        "google_client_id": settings.google_client_id,
        "authenticated": user is not None,
        "approved": bool(user and user.is_approved),
        "user": user.public_dict() if user else None,
    }


@router.post("/google")
async def sign_in_with_google(
    body: GoogleSignIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Exchange a verified Google id token for a session on this platform.

    A first-time account is created pending and gets a session anyway — it can
    see the "waiting for approval" screen and nothing else. Without a session
    it could not even be told why it is being refused.
    """
    claims = verify_google_id_token(body.credential)
    user = await upsert_user_from_claims(session, claims)
    await session.commit()

    _set_session_cookie(response, issue_session_token(user))
    return {
        "authenticated": True,
        "approved": user.is_approved,
        "user": user.public_dict(),
    }


@router.post("/logout")
async def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"authenticated": False}
