"""Sign in with Google, and decide what the account may do.

The flow is the browser-side one: Google signs an id token in the page, the
page posts it here, and this module verifies it. There is no client secret,
because there is nothing here that a secret would protect — the server never
talks to Google on the user's behalf, it only checks a signature.

**What is actually checked.** The token's RS256 signature against Google's
published keys, that Google issued it, that it was issued for *this*
application, that it has not expired, and that the address on it is one Google
says it verified. Skipping the audience check is the classic mistake: without
it, a token minted for any other Google application would be accepted here, and
anyone with their own app could sign in as anyone.

**Identity is not authorisation.** A verified token proves an address belongs
to whoever presented it. It says nothing about whether they may see Lao
coverage data, so a new account is created ``pending`` and stays locked out
until a super admin approves it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.user import (
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    STATUS_APPROVED,
    STATUS_PENDING,
    User,
)

GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

SESSION_ALGORITHM = "HS256"

# Google's signing keys rotate; the client caches them and refetches on a key
# it has not seen, so rotation needs no action here. Created once — building it
# per request would refetch the key set on every sign-in.
_jwk_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)
    return _jwk_client


class AuthError(HTTPException):
    def __init__(self, detail: str, code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(status_code=code, detail=detail)


def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """Check a Google id token and return its claims.

    Raises :class:`AuthError` for anything that fails, with a reason vague
    enough not to help someone probing and specific enough to debug against the
    logs.
    """
    if not settings.google_client_id:
        raise AuthError(
            "Google sign-in is not configured on this server",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        key = _jwks().get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            # Without this, a token minted for any other Google application
            # would verify here.
            audience=settings.google_client_id,
            issuer=GOOGLE_ISSUERS,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
            leeway=30,
        )
    except jwt.ExpiredSignatureError as error:
        raise AuthError("sign-in has expired, please try again") from error
    except jwt.InvalidAudienceError as error:
        raise AuthError("this sign-in was not issued for this application") from error
    except jwt.InvalidTokenError as error:
        raise AuthError("could not verify this Google sign-in") from error

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise AuthError("this Google account has no email address")
    # Google sets this false for addresses it has not confirmed. Trusting an
    # unverified address would let someone claim an address they do not hold,
    # which is exactly what the super-admin list is keyed on.
    if not claims.get("email_verified"):
        raise AuthError("this Google account's email address is not verified")

    claims["email"] = email
    return claims


async def upsert_user_from_claims(session: AsyncSession, claims: dict[str, Any]) -> User:
    """Find or create the account behind a verified token.

    Matched on Google's subject rather than the address, because addresses get
    renamed and reassigned and the subject does not. An account that has been
    renamed keeps its approval instead of reappearing as a stranger.
    """
    google_sub = str(claims["sub"])
    email = claims["email"]

    user = await session.scalar(select(User).where(User.google_sub == google_sub))
    if user is None:
        # Same person, new Google subject, or a row seeded by address before
        # they ever signed in.
        user = await session.scalar(select(User).where(func.lower(User.email) == email))

    now = datetime.now(timezone.utc)
    is_bootstrap = email in settings.super_admin_emails

    if user is None:
        user = User(
            google_sub=google_sub,
            email=email,
            # Configured super admins are approved on sight; that is the only
            # way the first one can exist. Everyone else waits for a decision.
            role=ROLE_SUPER_ADMIN if is_bootstrap else ROLE_ADMIN,
            status=STATUS_APPROVED if is_bootstrap else STATUS_PENDING,
            requested_at=now,
            decided_at=now if is_bootstrap else None,
            decided_by="configuration" if is_bootstrap else None,
            login_count=0,
        )
        session.add(user)

    user.google_sub = google_sub
    user.email = email
    user.name = claims.get("name") or user.name
    user.picture_url = claims.get("picture") or user.picture_url

    # Being listed in configuration restores super admin on every sign-in. That
    # is what makes losing access to every super admin account recoverable
    # without database surgery.
    if is_bootstrap:
        user.role = ROLE_SUPER_ADMIN
        if user.status != STATUS_APPROVED:
            user.status = STATUS_APPROVED
            user.decided_at = now
            user.decided_by = "configuration"

    user.last_login_at = now
    user.login_count = (user.login_count or 0) + 1

    await session.flush()
    return user


def issue_session_token(user: User) -> str:
    """A signed session for this platform, separate from Google's token.

    Google's id token is evidence of a sign-in at one moment; it is not a
    session, and it carries claims this application has no business holding on
    to. The session says only who the holder is and until when — the role and
    the approval are read from the database on each request, so revoking
    someone takes effect immediately rather than whenever their token expires.
    """
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=SESSION_ALGORITHM,
    )


def read_session_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[SESSION_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError as error:
        raise AuthError("session is not valid, please sign in again") from error


async def current_user_or_none(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User | None:
    """The signed-in account, or None. Never raises."""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    try:
        claims = read_session_token(token)
    except AuthError:
        return None
    return await session.scalar(select(User).where(User.id == int(claims["sub"])))


async def require_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    """An approved account, or 401/403.

    The distinction matters to the client: 401 means "sign in", 403 with a
    pending status means "you have, and someone is looking at it" — two very
    different screens.
    """
    if not settings.auth_enabled:
        # Development only. Production defaults this on, so a deployment that
        # forgets to configure sign-in is closed rather than wide open.
        return User(id=0, google_sub="dev", email="dev@localhost", role=ROLE_SUPER_ADMIN,
                    status=STATUS_APPROVED)

    user = await current_user_or_none(request, session)
    if user is None:
        raise AuthError("sign in to view this")
    if not user.is_approved:
        raise AuthError(
            f"this account is {user.status}; a super admin must approve it",
            status.HTTP_403_FORBIDDEN,
        )
    return user


async def require_super_admin(user: User = Depends(require_user)) -> User:
    if not user.is_super_admin:
        raise AuthError("only a super admin may do this", status.HTTP_403_FORBIDDEN)
    return user
