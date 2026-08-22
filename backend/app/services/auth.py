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
from fastapi import Depends, HTTPException, Query, Request, status
from jwt import PyJWKClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.device import Device
from app.models.user_device import UserDevice
from app.models.user import (
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    STATUS_APPROVED,
    STATUS_PENDING,
    User,
)

GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

# Firebase mints its own tokens rather than passing Google's through, so they
# carry a different issuer, a different audience and a different key set. The
# audience is the bare project id — not a client id — and the issuer names the
# same project, which is what stops a token from somebody else's Firebase
# project verifying here.
FIREBASE_ISSUER_PREFIX = "https://securetoken.google.com/"
FIREBASE_JWKS_URL = (
    "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
)

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


_firebase_jwk_client: PyJWKClient | None = None


def _firebase_jwks() -> PyJWKClient:
    """Firebase's own signing keys — a different set, rotated on its own clock."""
    global _firebase_jwk_client
    if _firebase_jwk_client is None:
        _firebase_jwk_client = PyJWKClient(FIREBASE_JWKS_URL, cache_keys=True)
    return _firebase_jwk_client


def _issuer_of(id_token: str) -> str:
    """The issuer a token *claims*, read without trusting any of it.

    Used only to choose which verification to run. Nothing is believed on the
    strength of this: both branches below check the signature, the issuer and
    the audience in full, so a token that lies here simply fails the other one.
    """
    try:
        return str(jwt.decode(id_token, options={"verify_signature": False}).get("iss") or "")
    except jwt.InvalidTokenError:
        return ""


def _verify_firebase_id_token(id_token: str) -> dict[str, Any]:
    project = settings.firebase_project_id
    if not project:
        raise AuthError(
            "Firebase sign-in is not configured on this server",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return jwt.decode(
        id_token,
        _firebase_jwks().get_signing_key_from_jwt(id_token).key,
        algorithms=["RS256"],
        # The bare project id, which is what Firebase puts in `aud`.
        audience=project,
        issuer=f"{FIREBASE_ISSUER_PREFIX}{project}",
        options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        leeway=30,
    )


def _verify_google_button_token(id_token: str) -> dict[str, Any]:
    if not settings.google_client_id:
        raise AuthError(
            "Google sign-in is not configured on this server",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return jwt.decode(
        id_token,
        _jwks().get_signing_key_from_jwt(id_token).key,
        algorithms=["RS256"],
        # Without this, a token minted for any other Google application
        # would verify here.
        audience=settings.google_client_id,
        issuer=GOOGLE_ISSUERS,
        options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        leeway=30,
    )


class AuthError(HTTPException):
    def __init__(self, detail: str, code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(status_code=code, detail=detail)


def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """Check a signed sign-in token and return its claims.

    Accepts both of the ways somebody can arrive: a token from the Google
    button in the page, and one from Firebase Authentication. Which one is in
    hand is decided by the issuer the token names, and then that branch checks
    everything — signature, issuer, audience, expiry — so naming an issuer buys
    a token nothing except the right to be refused by a different check.

    Raises :class:`AuthError` for anything that fails, with a reason vague
    enough not to help someone probing and specific enough to debug against the
    logs.
    """
    firebase = _issuer_of(id_token).startswith(FIREBASE_ISSUER_PREFIX)

    try:
        claims = (
            _verify_firebase_id_token(id_token) if firebase else _verify_google_button_token(id_token)
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


async def operator_scope(user: User = Depends(require_user)) -> str | None:
    """The network this request may see, or None for unrestricted.

    Read from the account, never from the request. An operator account cannot
    widen its own view by asking differently, because nothing it sends is
    consulted.
    """
    return user.operator_scope


async def enforce_scope(
    operator: str | None = Query(default=None),
    scope: str | None = Depends(operator_scope),
) -> str | None:
    """Resolve the network a request is answered for, refusing a mismatch.

    An operator account asking for somebody else's network is refused rather
    than quietly corrected. Silently substituting the right answer would hide
    the bug — or the attempt — and leave the client believing it had been given
    what it asked for. A 403 says what happened.
    """
    if scope is None:
        return operator
    if operator is not None and operator != scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this account may only see its own network",
        )
    return scope


async def deny_operator_accounts(user: User = Depends(require_user)) -> None:
    """Close an endpoint to operator accounts.

    Used where an endpoint cannot be scoped to one network — the collector
    fleet, which is internal operations rather than coverage, and anything
    describing the survey as a whole. Deny by default is the rule here: these
    four companies compete, and an endpoint that forgets to scope itself should
    fail shut rather than serve everything.
    """
    if user.is_operator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not available to network accounts",
        )


async def deny_collector_accounts(user: User = Depends(require_user)) -> None:
    """Close an endpoint to collector accounts.

    Applied to every signed-in router rather than to chosen endpoints, so an
    endpoint added later is closed to collectors until somebody decides
    otherwise. The operator role learned that lesson the expensive way: one
    endpoint went out unscoped and a network account could see its
    competitors' masts, because scoping was opt-in and the new endpoint simply
    did not opt in.

    A collector sees its own readings through /mine and nothing else. Not the
    national map, not the fleet, not another network's coverage — the account
    exists so somebody can check their own work, and everything else on this
    platform is somebody else's.
    """
    if user.is_collector:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="collector accounts see only their own readings",
        )


async def own_devices(
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> frozenset[str]:
    """The handsets whose readings this account may see.

    Empty for an account nobody has assigned a phone to, which means an empty
    page rather than the whole fleet — the same direction NO_NETWORK fails in,
    and for a stronger reason: these readings are a record of where a
    particular person has been.

    Administrators get every device, because they already see every reading
    through the national views; a separate rule here would be a second place to
    get wrong rather than a second layer of protection.
    """
    if user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return frozenset(
            (await session.scalars(select(Device.install_id))).all()
        )

    owned = (
        await session.scalars(
            select(UserDevice.install_id).where(UserDevice.user_id == user.id)
        )
    ).all()
    return frozenset(owned)
