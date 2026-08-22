"""Sign-in with Google, and approval before access.

The checks worth having here are the ones whose absence looks like working
software. A token accepted without verifying its audience signs people in
perfectly — with tokens minted by any other Google application. A pending
account that can still read the map makes the approval queue decorative. And
gating the collector endpoints would stop the Android fleet silently, the
moment sign-in was switched on.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import (
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    STATUS_APPROVED,
    STATUS_PENDING,
    User,
)
from app.services import auth as auth_service
from tests.conftest import make_record, sign_record

CLIENT_ID = "test-client-id.apps.googleusercontent.com"
FIREBASE_PROJECT = "test-project-a014e"

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeSigningKey:
    key = _key.public_key()


class _FakeJwks:
    """Stands in for Google's key set."""

    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
        return _FakeSigningKey()


def google_token(
    *,
    sub: str = "google-sub-1",
    email: str = "person@example.com",
    email_verified: bool = True,
    audience: str = CLIENT_ID,
    issuer: str = "https://accounts.google.com",
    expires_in: int = 600,
    name: str = "A Person",
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub,
            "email": email,
            "email_verified": email_verified,
            "name": name,
            "picture": "https://example.com/a.png",
            "aud": audience,
            "iss": issuer,
            "iat": now,
            "exp": now + expires_in,
        },
        _key,
        algorithm="RS256",
    )


def firebase_token(
    *,
    sub: str = "firebase-uid-1",
    email: str = "person@example.com",
    email_verified: bool = True,
    audience: str = FIREBASE_PROJECT,
    issuer: str | None = None,
    expires_in: int = 600,
    name: str = "A Person",
) -> str:
    """A token shaped like the one Firebase Authentication issues.

    Different from Google's in every field the verification depends on: the
    issuer names the project, the audience *is* the project, and `sub` is a
    Firebase uid rather than a Google account id.
    """
    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub,
            "email": email,
            "email_verified": email_verified,
            "name": name,
            "picture": "https://example.com/a.png",
            "aud": audience,
            "iss": issuer or f"https://securetoken.google.com/{audience}",
            "iat": now,
            "exp": now + expires_in,
        },
        _key,
        algorithm="RS256",
    )


@pytest.fixture(autouse=True)
def google_configured(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "firebase_project_id", FIREBASE_PROJECT)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "super_admin_emails", ["boss@example.com"])
    monkeypatch.setattr(auth_service, "_jwk_client", _FakeJwks())
    monkeypatch.setattr(auth_service, "_firebase_jwk_client", _FakeJwks())
    yield


async def sign_in(client: AsyncClient, token: str):
    return await client.post("/api/v1/auth/google", json={"credential": token})


# --------------------------------------------------------------------------
# Verifying Google's token
# --------------------------------------------------------------------------


def test_a_token_for_another_application_is_refused():
    """The classic mistake. Without the audience check, anyone who registers
    their own Google app could mint a token and sign in here as anybody."""
    with pytest.raises(auth_service.AuthError) as caught:
        auth_service.verify_google_id_token(google_token(audience="someone-elses-app"))
    assert caught.value.status_code == 401


def test_a_token_from_another_issuer_is_refused():
    with pytest.raises(auth_service.AuthError):
        auth_service.verify_google_id_token(google_token(issuer="https://evil.example"))


def test_an_expired_token_is_refused():
    with pytest.raises(auth_service.AuthError):
        auth_service.verify_google_id_token(google_token(expires_in=-60))


def test_an_unverified_address_is_refused():
    """The super-admin list is keyed on the address. Accepting an unverified
    one would let somebody claim an address they do not hold."""
    with pytest.raises(auth_service.AuthError):
        auth_service.verify_google_id_token(google_token(email_verified=False))


def test_a_token_signed_by_the_wrong_key_is_refused():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {
            "sub": "x", "email": "x@example.com", "email_verified": True,
            "aud": CLIENT_ID, "iss": "https://accounts.google.com",
            "iat": int(time.time()), "exp": int(time.time()) + 600,
        },
        other,
        algorithm="RS256",
    )
    with pytest.raises(auth_service.AuthError):
        auth_service.verify_google_id_token(forged)


# --------------------------------------------------------------------------
# Verifying Firebase's token
# --------------------------------------------------------------------------


def test_a_firebase_token_is_accepted():
    claims = auth_service.verify_google_id_token(firebase_token())
    assert claims["email"] == "person@example.com"
    assert claims["sub"] == "firebase-uid-1"


def test_a_firebase_token_from_another_project_is_refused():
    """The audience is the project id, so this is the same mistake as
    accepting another application's Google token — and just as fatal: anyone
    with a free Firebase project could otherwise sign in here as anybody."""
    with pytest.raises(auth_service.AuthError) as caught:
        auth_service.verify_google_id_token(firebase_token(audience="somebody-elses-project"))
    assert caught.value.status_code == 401


def test_a_firebase_token_claiming_our_project_from_the_wrong_issuer_is_refused():
    with pytest.raises(auth_service.AuthError):
        auth_service.verify_google_id_token(
            firebase_token(issuer="https://securetoken.google.com/somebody-else")
        )


def test_a_firebase_token_is_refused_when_no_firebase_project_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "firebase_project_id", "")
    with pytest.raises(auth_service.AuthError) as caught:
        auth_service.verify_google_id_token(firebase_token())
    assert caught.value.status_code == 503


async def test_signing_in_through_firebase_reaches_the_same_account(
    anon_client: AsyncClient, session: AsyncSession
):
    """The two routes are one account, matched by address.

    Firebase's `sub` is its own uid, not the Google account id, so somebody who
    signed in with the button and then through Firebase must not arrive as a
    second person waiting in the approval queue.
    """
    assert (await sign_in(anon_client, google_token(email="dual@example.com"))).status_code == 200
    assert (
        await sign_in(anon_client, firebase_token(email="dual@example.com"))
    ).status_code == 200

    users = (await session.scalars(select(User).where(User.email == "dual@example.com"))).all()
    assert len(users) == 1
    assert users[0].google_sub == "firebase-uid-1"


# --------------------------------------------------------------------------
# Approval
# --------------------------------------------------------------------------


async def test_a_new_account_is_pending_and_cannot_read_anything(
    anon_client: AsyncClient, session: AsyncSession
):
    response = await sign_in(anon_client, google_token())
    assert response.status_code == 200

    body = response.json()
    assert body["authenticated"] is True
    assert body["approved"] is False
    assert body["user"]["status"] == STATUS_PENDING
    assert body["user"]["role"] == ROLE_ADMIN

    # Signed in, and still refused — with a reason the client can act on.
    blocked = await anon_client.get("/api/v1/dashboard/summary")
    assert blocked.status_code == 403
    assert "approve" in blocked.json()["detail"]


async def test_an_approved_account_can_read(anon_client: AsyncClient, session: AsyncSession):
    await sign_in(anon_client, google_token())

    user = await session.scalar(select(User).where(User.email == "person@example.com"))
    user.status = STATUS_APPROVED
    await session.commit()

    assert (await anon_client.get("/api/v1/dashboard/summary")).status_code == 200


async def test_signing_out_ends_the_session(anon_client: AsyncClient, session: AsyncSession):
    await sign_in(anon_client, google_token(email="boss@example.com", sub="boss"))
    assert (await anon_client.get("/api/v1/dashboard/summary")).status_code == 200

    await anon_client.post("/api/v1/auth/logout")
    assert (await anon_client.get("/api/v1/dashboard/summary")).status_code == 401


async def test_the_configured_address_becomes_an_approved_super_admin(
    anon_client: AsyncClient, session: AsyncSession
):
    """Somebody has to be able to approve the first person, and they cannot
    approve themselves into existence."""
    body = (await sign_in(anon_client, google_token(email="boss@example.com", sub="boss"))).json()

    assert body["approved"] is True
    assert body["user"]["role"] == ROLE_SUPER_ADMIN
    assert body["user"]["decided_by"] == "configuration"


async def test_a_renamed_account_keeps_its_approval(
    anon_client: AsyncClient, session: AsyncSession
):
    """Identity is Google's subject, not the address — people rename mailboxes,
    and reappearing as a stranger would mean asking for approval again."""
    await sign_in(anon_client, google_token(sub="stable-sub", email="before@example.com"))
    user = await session.scalar(select(User).where(User.google_sub == "stable-sub"))
    user.status = STATUS_APPROVED
    await session.commit()

    await sign_in(anon_client, google_token(sub="stable-sub", email="after@example.com"))

    await session.refresh(user)
    assert user.email == "after@example.com"
    assert user.status == STATUS_APPROVED
    assert (await session.scalar(select(User).where(User.google_sub == "stable-sub"))).id == user.id


# --------------------------------------------------------------------------
# What stays open
# --------------------------------------------------------------------------


async def test_the_android_collector_still_works_without_signing_in(
    anon_client: AsyncClient, device_key, public_key_b64: str
):
    """A phone has no Google account. Gating these would stop the fleet the
    moment sign-in was switched on, and the map would quietly stop growing."""
    enrolled = await anon_client.post(
        "/api/v1/devices/enroll",
        json={
            "device": {"install_id": "install-anon0000000001"},
            "public_key": public_key_b64,
        },
    )
    assert enrolled.status_code == 200

    record = sign_record(make_record(record_id="rec-anon00000001"), device_key)
    upload = await anon_client.post(
        "/api/v1/measurements/batch",
        json={
            "batch_id": "batch-anon00001",
            "device": {"install_id": "install-anon0000000001"},
            "records": [record],
        },
    )
    assert upload.status_code == 200
    assert upload.json()["accepted"] == 1


async def test_health_stays_open_but_the_figures_do_not(anon_client: AsyncClient):
    """A load balancer cannot sign in. It also does not need national coverage
    statistics."""
    assert (await anon_client.get("/api/v1/health")).status_code == 200
    assert (await anon_client.get("/api/v1/stats")).status_code == 401


async def test_the_map_is_closed_to_anonymous_visitors(anon_client: AsyncClient):
    for path in ("/api/v1/tiles?area=LA", "/api/v1/areas", "/api/v1/dashboard/summary"):
        assert (await anon_client.get(path)).status_code == 401, path


# --------------------------------------------------------------------------
# The super admin's queue
# --------------------------------------------------------------------------


async def _boss_and_pending(anon_client: AsyncClient, session: AsyncSession) -> User:
    await sign_in(anon_client, google_token(email="boss@example.com", sub="boss"))
    pending = User(
        google_sub="pending-sub",
        email="waiting@example.com",
        name="Waiting",
        role=ROLE_ADMIN,
        status=STATUS_PENDING,
        requested_at=datetime.now(timezone.utc),
    )
    session.add(pending)
    await session.commit()
    return pending


async def test_a_super_admin_sees_the_queue_pending_first(
    anon_client: AsyncClient, session: AsyncSession
):
    await _boss_and_pending(anon_client, session)

    body = (await anon_client.get("/api/v1/users")).json()
    assert body["pending"] == 1
    assert body["users"][0]["status"] == STATUS_PENDING


async def test_a_super_admin_can_approve(anon_client: AsyncClient, session: AsyncSession):
    pending = await _boss_and_pending(anon_client, session)

    response = await anon_client.post(
        f"/api/v1/users/{pending.id}/decision", json={"status": "approved"}
    )
    assert response.status_code == 200
    assert response.json()["user"]["status"] == STATUS_APPROVED
    assert response.json()["user"]["decided_by"] == "boss@example.com"


async def test_an_ordinary_admin_cannot_reach_the_queue(
    anon_client: AsyncClient, session: AsyncSession
):
    await sign_in(anon_client, google_token())
    user = await session.scalar(select(User).where(User.email == "person@example.com"))
    user.status = STATUS_APPROVED
    await session.commit()

    assert (await anon_client.get("/api/v1/users")).status_code == 403


async def test_a_super_admin_cannot_decide_about_themselves(
    anon_client: AsyncClient, session: AsyncSession
):
    """Self-approval would make the pending state decorative, and self-demotion
    is how somebody removes their own last way back in."""
    await _boss_and_pending(anon_client, session)
    boss = await session.scalar(select(User).where(User.email == "boss@example.com"))

    refused = await anon_client.post(
        f"/api/v1/users/{boss.id}/role", json={"role": "admin"}
    )
    assert refused.status_code == 400
    assert "your own" in refused.json()["detail"]


async def test_the_last_super_admin_cannot_be_removed(
    anon_client: AsyncClient, session: AsyncSession
):
    """Otherwise the platform reaches a state where nobody can approve anybody,
    recoverable only by editing configuration and redeploying."""
    await _boss_and_pending(anon_client, session)
    boss = await session.scalar(select(User).where(User.email == "boss@example.com"))

    second = User(
        google_sub="second-boss", email="second@example.com",
        role=ROLE_SUPER_ADMIN, status=STATUS_APPROVED,
    )
    session.add(second)
    await session.commit()

    # With two, demoting the other one is allowed.
    assert (
        await anon_client.post(f"/api/v1/users/{second.id}/role", json={"role": "admin"})
    ).status_code == 200

    # Now boss is the last, and cannot be removed by anyone — including a
    # second super admin promoted later.
    await session.refresh(boss)
    assert boss.role == ROLE_SUPER_ADMIN
