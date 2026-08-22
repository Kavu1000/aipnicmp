"""What a stranger with no cookie may reach.

Three things are pinned down here. First, that /public/* actually answers
with no cookie at all, and that the fields on a public hexagon stop where
privacy requires — no device count, no moment in time, on the combined map
or on any one network's own (see decision 26 for why per-network coverage
is public at all now). Second, that an unknown network name is refused
rather than silently answered with nothing. Third — the one that matters
most for the long run — that every *other* route in the app is closed to
that same stranger, checked by walking the live route table rather than by
re-listing paths a maintainer could just as easily forget to update. A route
added next month with no dependency on require_user fails this test until
someone decides, on purpose, which side of the line it belongs on.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app
from app.services.auth import require_user
from tests.test_areas import PROVINCE, seed_areas, seed_journey

LAO_VIEWPORT = {"min_lat": 18.5, "min_lon": 101.8, "max_lat": 20.2, "max_lon": 102.6}


async def _seed(session: AsyncSession, client: AsyncClient, device_key, public_key_b64) -> None:
    from app.services.aggregate import rebuild_tiles

    await seed_areas(session)
    await seed_journey(client, device_key, public_key_b64)
    await rebuild_tiles(session)


async def test_summary_and_tiles_need_no_cookie(
    anon_client: AsyncClient, session: AsyncSession, device_key, public_key_b64
):
    await _seed(session, anon_client, device_key, public_key_b64)

    summary = await anon_client.get("/api/v1/public/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["measurements"] > 0

    tiles = await anon_client.get("/api/v1/public/tiles", params=LAO_VIEWPORT)
    assert tiles.status_code == 200, tiles.text
    assert tiles.json()["features"], "the seeded journey should have produced tiles"


async def test_a_public_hexagon_carries_nothing_that_places_a_person(
    anon_client: AsyncClient, session: AsyncSession, device_key, public_key_b64
):
    await _seed(session, anon_client, device_key, public_key_b64)

    body = (await anon_client.get("/api/v1/public/tiles", params=LAO_VIEWPORT)).json()
    assert body["features"]
    for feature in body["features"]:
        properties = feature["properties"]
        # Exactly these fields — not "at least", because a field that shows up
        # here by accident (device_count, last_measured_at, an RSRP figure) is
        # the failure this test exists to catch.
        assert set(properties) == {
            "h3_index",
            "dominant_state",
            "colour",
            "is_predicted",
            "measured",
            "updated_at",
        }, properties


async def test_public_networks_lists_every_lao_operator(
    anon_client: AsyncClient, session: AsyncSession, device_key, public_key_b64
):
    """Every Lao network is named, measured or not — see decision 26 and
    dashboard/operator-names, which this mirrors for a stranger."""
    await _seed(session, anon_client, device_key, public_key_b64)

    response = await anon_client.get("/api/v1/public/networks")
    assert response.status_code == 200, response.text
    networks = {row["operator"]: row for row in response.json()["networks"]}
    assert set(networks) == {"Lao Telecom", "ETL", "Unitel", "Tplus"}
    # The seeded journey rides Lao Telecom's SIM; the others exist but no
    # collector carries them, which is a recruitment gap, not a coverage
    # finding — see network_catalogue's own docstring.
    assert networks["Lao Telecom"]["measured"] is True
    assert networks["Unitel"]["measured"] is False


async def test_operator_tiles_answer_one_networks_own_coverage(
    anon_client: AsyncClient, session: AsyncSession, device_key, public_key_b64
):
    """The policy this project settled on (decision 26): a network's own
    coverage is public, on request, by name."""
    await _seed(session, anon_client, device_key, public_key_b64)

    combined = await anon_client.get("/api/v1/public/tiles", params=LAO_VIEWPORT)
    scoped = await anon_client.get(
        "/api/v1/public/tiles", params={**LAO_VIEWPORT, "operator": "Lao Telecom"}
    )
    assert scoped.status_code == 200, scoped.text
    body = scoped.json()
    assert body["operator"] == "Lao Telecom"
    assert body["features"], "the seeded journey rode this network's SIM"

    # Same shape as the combined view — no field that appears for one and not
    # the other — and never a prediction: Layer 4 has no per-operator model.
    for feature in body["features"]:
        properties = feature["properties"]
        assert set(properties) == {
            "h3_index",
            "dominant_state",
            "colour",
            "is_predicted",
            "measured",
            "updated_at",
        }, properties
        assert properties["is_predicted"] is False

    # A network nobody carries a SIM for answers with an empty map, not an
    # error — "no collector has been here on this network" is a true finding.
    unmeasured = await anon_client.get(
        "/api/v1/public/tiles", params={**LAO_VIEWPORT, "operator": "Unitel"}
    )
    assert unmeasured.status_code == 200, unmeasured.text
    assert unmeasured.json()["features"] == []

    # A name that is not a Lao network at all is refused, not silently
    # empty — the difference between "checked, nothing there" and "typo".
    bogus = await anon_client.get(
        "/api/v1/public/tiles", params={**LAO_VIEWPORT, "operator": "Not A Real Network"}
    )
    assert bogus.status_code == 400
    assert "Not A Real Network" in bogus.json()["detail"]


async def test_a_country_sized_box_is_refused(anon_client: AsyncClient):
    response = await anon_client.get(
        "/api/v1/public/tiles",
        params={"min_lat": 14.0, "min_lon": 100.0, "max_lat": 22.0, "max_lon": 107.5},
    )
    assert response.status_code == 400
    assert "zoom in" in response.json()["detail"]


async def test_public_responses_are_cacheable(anon_client: AsyncClient):
    response = await anon_client.get("/api/v1/public/summary")
    assert response.headers["cache-control"] == "public, max-age=60"


async def test_area_endpoints_answer_and_carry_no_operator_scope(
    anon_client: AsyncClient, session: AsyncSession, device_key, public_key_b64
):
    await _seed(session, anon_client, device_key, public_key_b64)

    listed = await anon_client.get("/api/v1/public/areas", params={"level": 1})
    assert listed.status_code == 200, listed.text
    assert any(area["code"] == PROVINCE for area in listed.json()["areas"])

    detail = await anon_client.get(f"/api/v1/public/areas/{PROVINCE}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["area"]["code"] == PROVINCE
    # No operator key at all on the response — the signed-in endpoint echoes
    # the query parameter back for the client's own bookkeeping; this one has
    # no such parameter to echo.
    assert "operator" not in detail.json()

    children = await anon_client.get(f"/api/v1/public/areas/{PROVINCE}/children")
    assert children.status_code == 200, children.text
    assert children.json()["features"]

    missing = await anon_client.get("/api/v1/public/areas/NOT-A-REAL-CODE")
    assert missing.status_code == 404


async def test_the_flag_takes_the_whole_router_down_as_404(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "public_preview_enabled", False)
    response = await anon_client.get("/api/v1/public/summary")
    # 404, not 403 — this is a "does not exist" answer, not a locked door.
    assert response.status_code == 404


# --------------------------------------------------------------------------
# The allowlist: every OTHER route in the app must require a signed-in
# account somewhere in its dependency graph, or be named here on purpose.
# --------------------------------------------------------------------------

# Paths open to a stranger for reasons that have nothing to do with the
# public preview: machines with their own authentication (a device
# signature, an admin token), and the handful of pages a person needs before
# they have an account at all.
OPEN_ELSEWHERE = {
    "/api/v1/health",
    "/api/v1/health/db",
    "/api/v1/devices/enroll",
    "/api/v1/measurements/batch",
    "/api/v1/admin/rebuild-tiles",
    "/api/v1/speedtest/ping",
    "/api/v1/speedtest/payload",
    "/api/v1/auth/session",
    "/api/v1/auth/google",
    "/api/v1/auth/logout",
    "/api/v1/credits",
    "/api/v1/credits/{user_id}/avatar",
    "/",
}

# The public preview itself.
PUBLIC_PREVIEW = {
    "/api/v1/public/summary",
    "/api/v1/public/tiles",
    "/api/v1/public/networks",
    "/api/v1/public/areas",
    "/api/v1/public/areas/{code}",
    "/api/v1/public/areas/{code}/children",
}

ALLOWED_OPEN = OPEN_ELSEWHERE | PUBLIC_PREVIEW


def _dependency_calls(dependant, seen: set[int] | None = None) -> set:
    """Every callable anywhere in a route's resolved dependency tree."""
    if seen is None:
        seen = set()
    calls: set = set()
    for dep in dependant.dependencies:
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        if dep.call is not None:
            calls.add(dep.call)
        calls |= _dependency_calls(dep, seen)
    return calls


def test_every_route_either_requires_sign_in_or_is_named_on_this_allowlist():
    unguarded_and_unlisted = []
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        guarded = require_user in _dependency_calls(dependant)
        if not guarded and route.path not in ALLOWED_OPEN:
            unguarded_and_unlisted.append(route.path)

    assert not unguarded_and_unlisted, (
        "these routes answer with no signed-in account and are not on the "
        f"public allowlist: {unguarded_and_unlisted}. If this is deliberate, "
        "add the path to OPEN_ELSEWHERE or PUBLIC_PREVIEW above; if not, add "
        "require_user."
    )
