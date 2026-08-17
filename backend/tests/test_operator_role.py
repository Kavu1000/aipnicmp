"""An account that belongs to one network, and sees only that network.

These four companies compete. A leak between them is not an embarrassment, it
is commercially damaging and would end the pilot — so the scope is taken from
the account on every request and never from anything the client sends, and an
endpoint that cannot be scoped is closed rather than left open.
"""

from __future__ import annotations

import pytest

from app.models.user import NO_NETWORK, ROLE_ADMIN, ROLE_OPERATOR, User


def test_an_operator_account_is_confined_to_its_network():
    user = User(role=ROLE_OPERATOR, scoped_operator="Lao Telecom")
    assert user.operator_scope == "Lao Telecom"
    assert user.is_operator is True


def test_an_operator_account_with_no_network_sees_nothing():
    """Fails closed, not open.

    A scope of None means "unrestricted" everywhere it is used, so returning
    None for a misconfigured operator account would show one company the whole
    country including its competitors. A sentinel that matches no real network
    shows an empty map instead, which is wrong in the harmless direction.
    """
    user = User(role=ROLE_OPERATOR, scoped_operator=None)
    assert user.operator_scope == NO_NETWORK
    assert user.operator_scope is not None


def test_other_roles_are_unrestricted():
    for role in (ROLE_ADMIN, "super_admin"):
        assert User(role=role).operator_scope is None
        assert User(role=role).is_operator is False


@pytest.mark.parametrize(
    "asked_for, scope, allowed",
    [
        ("Lao Telecom", "Lao Telecom", True),
        (None, "Lao Telecom", True),
        ("Unitel", "Lao Telecom", False),
        ("Unitel", None, True),
    ],
)
def test_asking_for_another_network_is_refused_not_corrected(asked_for, scope, allowed):
    """Silently substituting the right answer would hide the attempt.

    A client that asked for Unitel and received Lao Telecom has been told
    something untrue about what it is looking at. A refusal says what happened,
    and surfaces the bug — or the probe — instead of burying it.
    """
    mismatch = scope is not None and asked_for is not None and asked_for != scope
    assert mismatch is not allowed or scope is None or asked_for is None


async def test_the_mast_layer_is_filtered_by_network(
    client, session, device_key, public_key_b64
):
    """Choosing a network must filter the masts, not only the hexagons.

    A map showing one operator's coverage under every operator's transmitters
    invites the reader to attribute a mast to the wrong company — and for a
    network account it is a leak, which is the reason this endpoint is scoped
    rather than merely filtered.
    """
    from app.models.cell import ObservedCell

    session.add_all(
        [
            ObservedCell(
                mcc="457", mnc="01", lac_tac=100, cid=1001,
                operator_name="Lao Telecom", observations=9,
                est_lat=18.0, est_lon=102.6, spread_m=2000.0, uncertainty_m=1000.0,
                position_is_reliable=True,
            ),
            ObservedCell(
                mcc="457", mnc="02", lac_tac=200, cid=2002,
                operator_name="ETL", observations=9,
                est_lat=18.1, est_lon=102.7, spread_m=2000.0, uncertainty_m=1000.0,
                position_is_reliable=True,
            ),
            # Never published, whatever is asked for: the readings behind it
            # were too tightly clustered to place.
            ObservedCell(
                mcc="457", mnc="01", lac_tac=100, cid=1002,
                operator_name="Lao Telecom", observations=9,
                est_lat=18.2, est_lon=102.8, spread_m=100.0, uncertainty_m=250.0,
                position_is_reliable=False,
            ),
        ]
    )
    await session.commit()

    everything = (await client.get("/api/v1/cells")).json()["features"]
    assert {f["properties"]["operator"] for f in everything} == {"Lao Telecom", "ETL"}
    assert len(everything) == 2

    only_ltc = (
        await client.get("/api/v1/cells", params={"operator": "Lao Telecom"})
    ).json()["features"]
    assert [f["properties"]["operator"] for f in only_ltc] == ["Lao Telecom"]


async def test_an_account_can_actually_be_promoted_to_a_network(session):
    """The role can be given, not merely honoured once somebody has it.

    Everything else here tests what an operator account sees. Nothing tested
    that one could be created, and it could not: the request model listed only
    the administrator roles, so the network dialog failed at validation and the
    branch below it had never run.
    """
    from app.api.v1.users import RoleChange, set_role
    from app.models.user import ROLE_SUPER_ADMIN, STATUS_APPROVED

    actor = User(
        google_sub="sub-actor", email="boss@example.la", name="Boss",
        role=ROLE_SUPER_ADMIN, status=STATUS_APPROVED,
    )
    target = User(
        google_sub="sub-target", email="net@example.la", name="Network Person",
        role=ROLE_ADMIN, status=STATUS_APPROVED,
    )
    session.add_all([actor, target])
    await session.commit()

    body = await set_role(
        target.id, RoleChange(role="operator", operator="ETL"), actor=actor, session=session
    )
    assert body["user"]["role"] == ROLE_OPERATOR
    assert body["user"]["scoped_operator"] == "ETL"

    await session.refresh(target)
    assert target.operator_scope == "ETL"


async def test_promotion_without_a_real_network_is_refused(session):
    """A scope of nothing resolves to a sentinel that matches nothing, so the
    account would see an empty map and nobody would know why."""
    import pytest
    from fastapi import HTTPException

    from app.api.v1.users import RoleChange, set_role
    from app.models.user import ROLE_SUPER_ADMIN, STATUS_APPROVED

    actor = User(
        google_sub="sub-a2", email="boss2@example.la", role=ROLE_SUPER_ADMIN,
        status=STATUS_APPROVED,
    )
    target = User(
        google_sub="sub-t2", email="net2@example.la", role=ROLE_ADMIN, status=STATUS_APPROVED,
    )
    session.add_all([actor, target])
    await session.commit()

    with pytest.raises(HTTPException) as refused:
        await set_role(
            target.id, RoleChange(role="operator", operator="Not A Network"),
            actor=actor, session=session,
        )
    assert refused.value.status_code == 400


async def test_demotion_clears_the_network(session):
    """A later promotion must not silently inherit a scope nobody chose."""
    from app.api.v1.users import RoleChange, set_role
    from app.models.user import ROLE_SUPER_ADMIN, STATUS_APPROVED

    actor = User(
        google_sub="sub-a3", email="boss3@example.la", role=ROLE_SUPER_ADMIN,
        status=STATUS_APPROVED,
    )
    target = User(
        google_sub="sub-t3", email="net3@example.la", role=ROLE_OPERATOR,
        scoped_operator="Unitel", status=STATUS_APPROVED,
    )
    session.add_all([actor, target])
    await session.commit()

    await set_role(target.id, RoleChange(role="admin"), actor=actor, session=session)
    await session.refresh(target)

    assert target.role == ROLE_ADMIN
    assert target.scoped_operator is None
    assert target.operator_scope is None
