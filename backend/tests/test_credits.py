"""Who appears on the sign-in page, and what a stranger learns from it.

This is the one page served to people who have not signed in, so everything it
carries is public. Two separate risks are guarded here: publishing a colleague
without anybody deciding to, and handing a visitor a directory of the accounts
worth attacking.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.user import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SUPER_ADMIN,
    STATUS_APPROVED,
    STATUS_PENDING,
    User,
)
from app.services.credits import credited_people, heading_for


def _person(**kw) -> User:
    base = dict(
        google_sub=kw.pop("sub", "sub-1"),
        email=kw.pop("email", "someone@example.la"),
        name=kw.pop("name", "Somebody"),
        role=ROLE_ADMIN,
        status=STATUS_APPROVED,
        show_in_credits=True,
    )
    base.update(kw)
    return User(**base)


async def test_nobody_is_credited_until_somebody_says_so(session):
    """The whole reason credit is not derived from the role column.

    Granting admin must not publish a name and photograph to every visitor.
    """
    session.add(
        _person(sub="sub-quiet", email="quiet@example.la", name="Not Published",
                show_in_credits=False)
    )
    await session.commit()

    people = await credited_people(session)
    assert people == {"team": [], "advisors": []}


async def test_the_role_chooses_the_heading(session):
    """Admins built it, super admins advised it — as asked for."""
    session.add_all([
        _person(sub="s1", email="dev@example.la", name="Dev One",
                role=ROLE_ADMIN, credit_title="Android collector"),
        _person(sub="s2", email="prof@example.la", name="Advisor One",
                role=ROLE_SUPER_ADMIN, credit_title="Faculty advisor"),
    ])
    await session.commit()

    people = await credited_people(session)
    assert [p["name"] for p in people["team"]] == ["Dev One"]
    assert [p["name"] for p in people["advisors"]] == ["Advisor One"]
    assert people["team"][0]["title"] == "Android collector"


async def test_the_public_list_never_carries_an_email_address(session):
    """A public page of administrators with addresses is a phishing list."""
    session.add(_person(sub="s3", email="target@example.la", name="Named Person"))
    await session.commit()

    people = await credited_people(session)
    body = repr(people)
    assert "Named Person" in body
    assert "target@example.la" not in body
    assert "@" not in body
    # Nor which access anybody holds.
    for person in people["team"]:
        assert set(person) == {"id", "name", "title", "has_avatar"}


async def test_an_unapproved_or_operator_account_is_never_credited(session):
    """Pending accounts have not been vetted, and a network account belongs to
    a network rather than to this project — crediting one would say the
    operator built the platform that measures it."""
    session.add_all([
        _person(sub="s4", email="pending@example.la", name="Waiting", status=STATUS_PENDING),
        _person(sub="s5", email="ops@example.la", name="Network Person",
                role=ROLE_OPERATOR, scoped_operator="ETL"),
    ])
    await session.commit()

    people = await credited_people(session)
    assert people["team"] == [] and people["advisors"] == []
    assert heading_for(ROLE_OPERATOR) is None


async def test_a_portrait_is_only_served_for_a_credited_person(client, session):
    """Otherwise the path could be walked to collect the photograph of every
    account that has ever signed in."""
    hidden = _person(sub="s6", email="hidden@example.la", name="Hidden",
                     show_in_credits=False)
    hidden.avatar_image = b"\\x89PNG not really"
    hidden.avatar_content_type = "image/png"
    session.add(hidden)
    await session.commit()

    assert (await client.get(f"/api/v1/credits/{hidden.id}/avatar")).status_code == 404


async def test_a_credited_portrait_is_served_from_this_platform(client, session):
    """Served as bytes from our own origin, so no visitor's browser is sent to
    Google before they have signed in to anything."""
    shown = _person(sub="s7", email="shown@example.la", name="Shown")
    shown.avatar_image = b"pretend-png-bytes"
    shown.avatar_content_type = "image/png"
    session.add(shown)
    await session.commit()

    response = await client.get(f"/api/v1/credits/{shown.id}/avatar")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"pretend-png-bytes"
    assert "max-age" in response.headers["cache-control"]


async def test_the_credits_endpoint_needs_no_account(anon_client, session):
    """It is on the sign-in page. Requiring sign-in to read it would be a
    door that opens only for people already inside."""
    session.add(_person(sub="s8", email="open@example.la", name="Public Name"))
    await session.commit()

    response = await anon_client.get("/api/v1/credits")
    assert response.status_code == 200
    assert [p["name"] for p in response.json()["team"]] == ["Public Name"]


async def test_only_an_administrator_can_be_credited(client, session):
    """The heading has to exist before somebody can be put under it."""
    from app.api.v1.users import CreditChange, set_credit

    operator = _person(sub="s9", email="net@example.la", name="Network Person",
                       role=ROLE_OPERATOR, scoped_operator="ETL", show_in_credits=False)
    session.add(operator)
    await session.commit()

    actor = (await session.scalars(select(User).where(User.role == ROLE_SUPER_ADMIN))).first()
    with pytest.raises(HTTPException) as refused:
        await set_credit(
            operator.id, CreditChange(show=True), actor=actor or operator, session=session
        )
    assert refused.value.status_code == 400


async def test_removing_the_credit_removes_the_portrait(session):
    """A photograph kept for a page that no longer shows it is a photograph
    nobody agreed to store."""
    from app.api.v1.users import CreditChange, set_credit

    person = _person(sub="s10", email="bye@example.la", name="Departing")
    person.avatar_image = b"portrait"
    person.avatar_content_type = "image/png"
    session.add(person)
    await session.commit()

    await set_credit(person.id, CreditChange(show=False), actor=person, session=session)
    await session.refresh(person)

    assert person.show_in_credits is False
    assert person.avatar_image is None
    assert person.avatar_content_type is None


def test_a_role_name_is_not_a_credit():
    """"admin" is not something somebody did, it is what they may do.

    The field once asked for a "role", so the first people credited went out
    labelled with theirs on the public sign-in page — which also told every
    visitor who held which access, on a page built never to say that.
    """
    from app.services.credits import is_role_name

    for role in ("admin", "super_admin", "Admin", "SUPER ADMIN", " operator ", "collector"):
        assert is_role_name(role) is True, role

    for real in ("Project lead", "Backend and data", "Android collector", "Faculty advisor"):
        assert is_role_name(real) is False, real

    assert is_role_name(None) is False
    assert is_role_name("") is False


async def test_a_saved_role_name_is_suppressed_rather_than_shown(session):
    """Fixes what is already stored without anybody editing data by hand."""
    person = _person(sub="s-role", email="role@example.la", name="Titled Person")
    person.credit_title = "admin"
    session.add(person)
    await session.commit()

    people = await credited_people(session)
    assert people["team"][0]["name"] == "Titled Person"
    assert people["team"][0]["title"] is None


async def test_a_role_name_cannot_be_saved_as_a_credit(session):
    """And it is refused on the way in, with a sentence saying what to write."""
    import pytest
    from fastapi import HTTPException

    from app.api.v1.users import CreditChange, set_credit

    person = _person(sub="s-refuse", email="refuse@example.la", name="Somebody")
    session.add(person)
    await session.commit()

    with pytest.raises(HTTPException) as refused:
        await set_credit(
            person.id, CreditChange(show=True, title="admin"), actor=person, session=session
        )
    assert refused.value.status_code == 400
    assert "not what they may do" in refused.value.detail
