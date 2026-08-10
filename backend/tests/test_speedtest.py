"""The endpoints a collector times itself against.

These exist to produce the throughput labels proposal 2.3 trains on, so the
things that would quietly corrupt those labels are what is pinned here.
"""

from __future__ import annotations

import zlib

from httpx import AsyncClient


async def test_ping_is_tiny_and_uncacheable(client: AsyncClient):
    response = await client.get("/api/v1/speedtest/ping")
    assert response.status_code == 200
    assert len(response.content) == 1
    assert "no-store" in response.headers["cache-control"]


async def test_payload_returns_exactly_what_was_asked_for(client: AsyncClient):
    response = await client.get("/api/v1/speedtest/payload", params={"bytes": 4096})
    assert response.status_code == 200
    assert len(response.content) == 4096


async def test_the_payload_does_not_compress(client: AsyncClient):
    """A compressible payload would measure how fast the phone inflates zeros.

    A village on a weak link would be recorded as having excellent throughput,
    and that reading would then teach the model that its radio conditions imply
    a speed nobody there can get.
    """
    response = await client.get("/api/v1/speedtest/payload", params={"bytes": 65536})
    squeezed = len(zlib.compress(response.content, 9))
    # Random data cannot be meaningfully compressed; a pattern would collapse.
    assert squeezed > 65536 * 0.95, squeezed


async def test_two_payloads_differ(client: AsyncClient):
    """Identical bodies would let a cache or a proxy answer the second run
    without the network being involved at all."""
    first = await client.get("/api/v1/speedtest/payload", params={"bytes": 8192})
    second = await client.get("/api/v1/speedtest/payload", params={"bytes": 8192})
    assert first.content != second.content


async def test_an_oversized_request_is_refused_not_clamped(client: AsyncClient):
    """Silently sending less than asked would make the client compute a
    throughput from a byte count that never crossed the wire."""
    response = await client.get("/api/v1/speedtest/payload", params={"bytes": 50_000_000})
    assert response.status_code == 422


async def test_the_collector_can_reach_these_without_signing_in(client: AsyncClient):
    """A handset has no browser session. If these ever moved behind the
    dashboard's sign-in, every collector would silently stop measuring speed."""
    for path in ("/api/v1/speedtest/ping", "/api/v1/speedtest/payload"):
        assert (await client.get(path)).status_code == 200
