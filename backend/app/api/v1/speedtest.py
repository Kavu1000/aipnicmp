"""Endpoints a collector uses to measure the connection it is standing in.

Signal strength is not speed. A phone can show four bars against a tower whose
backhaul is saturated, and a coverage map built only on RSRP would call that
place well served. Proposal 2.2 asks for both, and section 2.3 depends on it:
the points carrying a real throughput reading are the training labels for the
model that estimates speed everywhere else from radio alone. Without any of
them that relationship can never be learned.

Served from this platform rather than a public speed-test host. It measures the
path the platform actually cares about — collector to this API — keeps the
bytes on infrastructure the ministry controls, and adds no third party to a
request made from a government project's handset.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Query, Response

router = APIRouter(prefix="/speedtest", tags=["speedtest"])

# The largest payload a collector may ask for.
#
# Sized for the connection this is aimed at, not for a fast one: 1 MB over a
# poor rural link is already several seconds of a collector's data allowance,
# and a bigger sample would not change the answer. Anything larger is refused
# rather than clamped, so a client asking for it learns that it was wrong.
MAX_PAYLOAD_BYTES = 1_048_576
DEFAULT_PAYLOAD_BYTES = 262_144


@router.get("/ping")
async def ping() -> Response:
    """The smallest possible reply, for timing a round trip.

    Deliberately not /health: that touches the database, so its timing would
    include work no collector is trying to measure.
    """
    return Response(
        content=b"1",
        media_type="text/plain",
        headers={"Cache-Control": "no-store", "Content-Length": "1"},
    )


@router.get("/payload")
async def payload(
    bytes_: int = Query(
        default=DEFAULT_PAYLOAD_BYTES,
        alias="bytes",
        ge=1024,
        le=MAX_PAYLOAD_BYTES,
        description="How many bytes to send back.",
    ),
) -> Response:
    """A block of incompressible bytes, for timing a download.

    Random rather than a repeated pattern, and served with compression refused:
    a payload that gzips to nothing would measure how fast the phone can
    inflate zeros, and report a rural village as having excellent throughput.

    Uncacheable for the same reason — a cached second run would time the
    phone's own storage.
    """
    return Response(
        content=os.urandom(bytes_),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Content-Encoding": "identity",
            "Content-Length": str(bytes_),
        },
    )
