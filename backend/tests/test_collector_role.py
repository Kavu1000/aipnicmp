"""A collector account sees its own readings and nothing else.

The thing being protected is not commercial, it is personal: a handset's
readings are where somebody went and when. So the tests that matter are the
negative ones — what this account is refused — and they are written against the
router rather than against a list of endpoints somebody has to remember to
update.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.user import (
    ROLE_ADMIN,
    ROLE_COLLECTOR,
    ROLE_OPERATOR,
    ROLE_SUPER_ADMIN,
    ROLES,
    STATUS_APPROVED,
    User,
)
from app.models.user_device import UserDevice
from app.services.auth import deny_collector_accounts, own_devices


def _account(role: str = ROLE_COLLECTOR, **kw) -> User:
    return User(
        google_sub=kw.pop("sub", "sub-collector"),
        email=kw.pop("email", "walker@example.la"),
        name=kw.pop("name", "Collector"),
        role=role,
        status=STATUS_APPROVED,
        **kw,
    )


def test_the_role_exists_and_is_its_own_thing():
    assert ROLE_COLLECTOR in ROLES
    assert _account().is_collector is True
    for other in (ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_OPERATOR):
        assert _account(other).is_collector is False


async def test_a_collector_owning_nothing_sees_nothing(session):
    """Fails closed. An account nobody has assigned a phone to must get an
    empty page, never the fleet — the opposite mistake shows one person every
    other person's movements."""
    account = _account()
    session.add(account)
    await session.commit()

    assert await own_devices(user=account, session=session) == frozenset()


async def test_a_collector_sees_only_the_handsets_assigned_to_it(
    session, client, public_key_b64
):
    from tests.test_ingest_api import enroll

    await enroll(client, public_key_b64)

    mine = _account(sub="sub-mine", email="mine@example.la")
    theirs = _account(sub="sub-theirs", email="theirs@example.la")
    session.add_all([mine, theirs])
    await session.commit()

    from sqlalchemy import select

    from app.models.device import Device

    device = (await session.scalars(select(Device))).first()
    session.add(UserDevice(user_id=mine.id, install_id=device.install_id))
    await session.commit()

    assert await own_devices(user=mine, session=session) == frozenset({device.install_id})
    # The other collector is not given it by default, nor by accident.
    assert await own_devices(user=theirs, session=session) == frozenset()


async def test_every_signed_in_router_is_closed_to_collectors():
    """Asserted against the router, not a list somebody maintains.

    An endpoint added later is shut to collectors until somebody decides
    otherwise. The operator role learned this the expensive way — scoping was
    opt-in, one endpoint did not opt in, and a network account could see its
    competitors' masts.
    """
    from app.api.v1.router import api_router
    from app.services.auth import require_super_admin

    def guards_of(dependant, found=None):
        """Every dependency on a route, including ones reached through others.

        Walked rather than read off the top level, because a guard declared as
        a handler parameter sits a layer down and a shallow check would call a
        protected route unprotected.
        """
        found = set() if found is None else found
        for sub in dependant.dependencies:
            if sub.call is not None:
                found.add(sub.call)
            guards_of(sub, found)
        return found

    # Either guard shuts the door on a collector: one by role, one by being a
    # super admin's page. Neither is a path somebody has to remember.
    closed = {deny_collector_accounts, require_super_admin}

    reachable = []
    for route in api_router.routes:
        path = getattr(route, "path", "")
        if not path or path.startswith("/mine"):
            continue
        if guards_of(route.dependant) & closed:
            continue
        reachable.append(path)

    # What remains must be a route no signed-in person reaches at all:
    # enrolment, upload, sign-in, the speed test, the public credits, the
    # health checks and the worker's own admin token.
    open_by_design = (
        "/devices", "/measurements", "/auth", "/speedtest",
        "/credits", "/admin", "/health", "/stats",
    )
    leaked = [p for p in reachable if not p.startswith(open_by_design)]
    assert leaked == [], f"reachable by a collector account: {leaked}"


async def test_a_collector_is_refused_by_the_guard():
    with pytest.raises(HTTPException) as refused:
        await deny_collector_accounts(user=_account())
    assert refused.value.status_code == 403

    # And everybody else passes it.
    for role in (ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_OPERATOR):
        assert await deny_collector_accounts(user=_account(role)) is None


async def test_my_tiles_are_built_from_my_readings_alone(
    client, session, device_key, public_key_b64
):
    """The leak this endpoint exists to avoid.

    The shared hexagons aggregate every device that passed through, so serving
    them to a collector would hand over other people's readings through the
    door marked "your own coverage".
    """
    from sqlalchemy import select

    from app.api.v1.mine import my_tiles
    from app.models.device import Device
    from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
    from tests.test_ingest_api import batch, enroll

    await enroll(client, public_key_b64)
    records = [
        sign_record(
            make_record(record_id=f"rec-mine{i:04d}", minutes_ago=60 - i, lat=BASE_LAT, lon=BASE_LON),
            device_key,
        )
        for i in range(4)
    ]
    assert (
        await client.post("/api/v1/measurements/batch", json=batch(records, batch_id="batch-mine"))
    ).json()["accepted"] == 4

    device = (await session.scalars(select(Device))).first()

    owned = await my_tiles(devices=frozenset({device.install_id}), session=session)
    assert owned["features"], "a collector should see the ground it covered"
    for feature in owned["features"]:
        assert feature["properties"]["colour"]
        assert feature["properties"]["measurements"] >= 1

    # An account owning nothing gets nothing, not everything.
    assert await my_tiles(devices=frozenset(), session=session) == {
        "type": "FeatureCollection",
        "features": [],
    }

    # And an account owning a different handset sees none of these readings.
    assert (await my_tiles(devices=frozenset({"someone-elses-phone"}), session=session))[
        "features"
    ] == []


async def test_a_handset_cannot_belong_to_two_accounts(client, session, public_key_b64):
    """Two people each told the readings are theirs is two people shown a
    third person's journey."""
    from sqlalchemy import select

    from app.api.v1.users import DeviceAssignment, set_devices
    from app.models.device import Device
    from tests.test_ingest_api import enroll

    await enroll(client, public_key_b64)
    device = (await session.scalars(select(Device))).first()

    boss = _account(ROLE_SUPER_ADMIN, sub="sub-boss", email="boss@example.la")
    first = _account(sub="sub-first", email="first@example.la")
    second = _account(sub="sub-second", email="second@example.la")
    session.add_all([boss, first, second])
    await session.commit()

    await set_devices(
        first.id, DeviceAssignment(install_ids=[device.install_id]), actor=boss, session=session
    )
    with pytest.raises(HTTPException) as refused:
        await set_devices(
            second.id,
            DeviceAssignment(install_ids=[device.install_id]),
            actor=boss,
            session=session,
        )
    assert refused.value.status_code == 409


async def test_only_a_collector_account_owns_devices(client, session, public_key_b64):
    """An admin already sees every reading; giving one a device list would be a
    second place to get the rule wrong rather than a second layer of it."""
    from sqlalchemy import select

    from app.api.v1.users import DeviceAssignment, set_devices
    from app.models.device import Device
    from tests.test_ingest_api import enroll

    await enroll(client, public_key_b64)
    device = (await session.scalars(select(Device))).first()

    boss = _account(ROLE_SUPER_ADMIN, sub="sub-boss2", email="boss2@example.la")
    admin = _account(ROLE_ADMIN, sub="sub-admin2", email="admin2@example.la")
    session.add_all([boss, admin])
    await session.commit()

    with pytest.raises(HTTPException) as refused:
        await set_devices(
            admin.id,
            DeviceAssignment(install_ids=[device.install_id]),
            actor=boss,
            session=session,
        )
    assert refused.value.status_code == 400


async def test_the_collectors_map_carries_the_same_shape_as_the_public_one(
    client, session, device_key, public_key_b64
):
    """The map component draws whatever it is given, so the shape has to match.

    A collector's hexagons come from a different endpoint and a different
    aggregation; if the property names drifted the map would render nothing and
    look like an empty collection rather than a bug.
    """
    from sqlalchemy import select

    from app.api.v1.mine import my_tiles
    from app.models.device import Device
    from app.services.aggregate import rebuild_tiles
    from tests.conftest import BASE_LAT, BASE_LON, make_record, sign_record
    from tests.test_ingest_api import batch, enroll

    await enroll(client, public_key_b64)
    records = [
        sign_record(
            make_record(record_id=f"rec-shape{i:04d}", minutes_ago=60 - i, lat=BASE_LAT, lon=BASE_LON),
            device_key,
        )
        for i in range(4)
    ]
    assert (
        await client.post("/api/v1/measurements/batch", json=batch(records, batch_id="batch-shape"))
    ).json()["accepted"] == 4
    await rebuild_tiles(session)

    device = (await session.scalars(select(Device))).first()
    mine = await my_tiles(devices=frozenset({device.install_id}), session=session)

    viewport = {
        "min_lat": BASE_LAT - 0.5, "min_lon": BASE_LON - 0.5,
        "max_lat": BASE_LAT + 0.5, "max_lon": BASE_LON + 0.5,
    }
    public = (await client.get("/api/v1/tiles", params=viewport)).json()

    assert mine["features"] and public["features"]
    shared = {"h3", "state", "colour", "predicted", "measurements"}
    assert shared <= set(mine["features"][0]["properties"])
    assert shared <= set(public["features"][0]["properties"])
    assert mine["features"][0]["geometry"]["type"] == "Polygon"


async def test_the_picker_shows_full_ids_and_who_holds_them(
    client, session, public_key_b64
):
    """The fleet page shortens install ids to sixteen characters, which is
    enough to tell two devices apart and not enough to assign one. And a taken
    handset is listed with its owner rather than hidden, so the person choosing
    sees why it cannot be picked instead of wondering where it went."""
    from sqlalchemy import select

    from app.api.v1.users import assignable_devices
    from app.models.device import Device
    from tests.test_ingest_api import enroll

    await enroll(client, public_key_b64)
    device = (await session.scalars(select(Device))).first()

    boss = _account(ROLE_SUPER_ADMIN, sub="sub-pick", email="pick@example.la")
    owner = _account(sub="sub-owner", email="owner@example.la")
    session.add_all([boss, owner])
    await session.commit()
    session.add(UserDevice(user_id=owner.id, install_id=device.install_id))
    await session.commit()

    body = await assignable_devices(actor=boss, session=session)
    row = next(d for d in body["devices"] if d["install_id"] == device.install_id)

    assert row["install_id"] == device.install_id, "the whole id, not a prefix"
    assert len(row["install_id"]) > 16
    assert row["owner_user_id"] == owner.id
