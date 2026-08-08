"""Simulate a collector device travelling a route and uploading measurements.

Exists so the backend, the map and the AI pipeline can be developed and
demonstrated before the Android app is finished, and so the store-and-forward
path can be exercised without driving into a dead zone.

It speaks the real wire protocol and signs with a real Ed25519 key, so anything
it uploads has passed exactly the checks a phone's data will face.

    python scripts/simulate_journey.py --api http://127.0.0.1:8000 --points 200

The synthetic data is obvious in the database: every simulated device's
install_id starts with ``sim-``, so it can be deleted wholesale before real
collection begins.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import random
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

# Route 13 North, roughly Luang Prabang -> Nong Khiaw: a real corridor with
# genuine coverage gaps, which is what makes it a useful demo.
ROUTE = [
    (19.8845, 102.1350),
    (19.9600, 102.2100),
    (20.0500, 102.2800),
    (20.1400, 102.3300),
    (20.2300, 102.4100),
    (20.3400, 102.5200),
    (20.4200, 102.6100),
    (20.5680, 102.6420),
]


def interpolate(points: list[tuple[float, float]], count: int) -> list[tuple[float, float]]:
    """Evenly spaced positions along the polyline."""
    if count <= len(points):
        return points[:count]
    out: list[tuple[float, float]] = []
    segments = len(points) - 1
    per_segment = count // segments
    for i in range(segments):
        lat1, lon1 = points[i]
        lat2, lon2 = points[i + 1]
        for step in range(per_segment):
            t = step / per_segment
            out.append((lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t))
    out.append(points[-1])
    return out[:count]


def coverage_at(lat: float, lon: float) -> tuple[bool, str | None, float | None, int]:
    """A crude propagation stand-in: signal decays with distance from the towns
    at either end of the route, leaving a genuine dead stretch in the middle.

    Returns (registered, network_type, rsrp_dbm, cells_visible).
    """
    towns = [(19.8845, 102.1350), (20.5680, 102.6420)]
    nearest = min(math.dist((lat, lon), town) for town in towns)

    if nearest < 0.12:
        return True, "LTE", random.uniform(-95, -70), random.randint(3, 6)
    if nearest < 0.22:
        return True, "LTE", random.uniform(-118, -105), random.randint(2, 4)
    if nearest < 0.30:
        return True, random.choice(["UMTS", "EDGE"]), random.uniform(-115, -100), random.randint(1, 3)
    if nearest < 0.36:
        # A tower is visible but the phone cannot attach: the "upgrade, don't
        # build" case the map is meant to distinguish.
        return False, None, None, random.randint(1, 2)
    return False, None, None, 0


def canonical(record: dict) -> bytes:
    """Mirror of app.services.signing.canonical_message, kept standalone so this
    script can run without importing the backend."""
    rsrp = record["signal"].get("rsrp_dbm")
    parts = [
        "v1",
        record["client_record_id"],
        record["captured_at"],
        f"{record['lat']:.6f}",
        f"{record['lon']:.6f}",
        "1" if record["registered"] else "0",
        (record.get("network_type") or "").upper(),
        "" if rsrp is None else f"{rsrp:.1f}",
        str(record["_cells_visible"]),
    ]
    return "|".join(parts).encode("utf-8")


def post(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{url} -> {error.code}: {error.read().decode()}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="backend base URL")
    parser.add_argument("--points", type=int, default=200, help="measurements to generate")
    parser.add_argument("--interval", type=int, default=60, help="seconds between measurements")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducible runs")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    base = args.api.rstrip("/") + "/api/v1"
    key = Ed25519PrivateKey.generate()
    public_key = base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    install_id = f"sim-{uuid.uuid4().hex[:20]}"

    enrolled = post(
        f"{base}/devices/enroll",
        {
            "device": {
                "install_id": install_id,
                "model": "Simulator",
                "manufacturer": "ai-pnicmp",
                "android_api": 34,
                "app_version": "sim-0.1.0",
            },
            "public_key": public_key,
        },
    )
    print(f"enrolled {enrolled['install_id']} (trust: {enrolled['trust_level']})")

    positions = interpolate(ROUTE, args.points)
    # Backdate the journey so the whole run sits in the past, as a real
    # store-and-forward upload would.
    start = datetime.now(timezone.utc) - timedelta(seconds=args.interval * len(positions) + 300)

    records = []
    for index, (lat, lon) in enumerate(positions):
        captured = start + timedelta(seconds=args.interval * index)
        registered, network_type, rsrp, cells = coverage_at(lat, lon)

        record: dict = {
            "client_record_id": f"sim-{uuid.uuid4().hex[:16]}",
            "captured_at": captured.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "lat": round(lat + random.uniform(-0.0002, 0.0002), 6),
            "lon": round(lon + random.uniform(-0.0002, 0.0002), 6),
            "gps_accuracy_m": round(random.uniform(4, 18), 1),
            "speed_mps": round(random.uniform(8, 22), 1),
            "registered": registered,
            "network_type": network_type,
            "operator": {"mcc": "457", "mnc": "01", "name": "LTC"},
            "signal": {
                "rsrp_dbm": round(rsrp, 1) if rsrp is not None else None,
                "rsrq_db": round(random.uniform(-18, -8), 1) if rsrp is not None else None,
                "sinr_db": round(random.uniform(-5, 20), 1) if rsrp is not None else None,
                "level": max(0, min(4, int((rsrp + 125) / 12))) if rsrp is not None else 0,
            },
            "serving_cell": (
                {
                    "radio": "LTE" if network_type in {"LTE", "NR"} else "UMTS",
                    "mcc": "457",
                    "mnc": "01",
                    "cid": random.randint(10_000, 99_999),
                    "is_registered": True,
                }
                if registered
                else None
            ),
            "neighbor_cells": [
                {"radio": "LTE", "mcc": "457", "mnc": "01", "pci_psc": random.randint(0, 503)}
                for _ in range(max(cells - (1 if registered else 0), 0))
            ],
        }

        # Active tests only run where data actually works — the same rule the
        # app follows, and the server rejects records that break it.
        if registered and network_type in {"LTE", "NR"} and rsrp is not None and rsrp > -110:
            record["active_test"] = {
                "download_kbps": round(random.uniform(2_000, 25_000), 1),
                "upload_kbps": round(random.uniform(500, 8_000), 1),
                "latency_ms": round(random.uniform(25, 120), 1),
            }

        record["_cells_visible"] = (1 if record["serving_cell"] else 0) + len(record["neighbor_cells"])
        record["signature"] = base64.b64encode(key.sign(canonical(record))).decode()
        del record["_cells_visible"]
        records.append(record)

    # Upload in chunks, as a phone would when its coverage window is short.
    chunk_size = 250
    totals = {"accepted": 0, "duplicates": 0, "rejected": 0}
    for start_index in range(0, len(records), chunk_size):
        chunk = records[start_index : start_index + chunk_size]
        result = post(
            f"{base}/measurements/batch",
            {
                "batch_id": f"sim-{uuid.uuid4().hex[:16]}",
                "device": {"install_id": install_id},
                "uploaded_from_lat": ROUTE[-1][0],
                "uploaded_from_lon": ROUTE[-1][1],
                "records": chunk,
            },
        )
        totals["accepted"] += result["accepted"]
        totals["duplicates"] += result["duplicates"]
        totals["rejected"] += len(result["rejected"])
        for rejection in result["rejected"][:5]:
            print(f"  rejected {rejection['client_record_id']}: {rejection['reason']} — {rejection['detail']}")

    print(
        f"uploaded {len(records)} records: "
        f"{totals['accepted']} accepted, {totals['duplicates']} duplicate, {totals['rejected']} rejected"
    )
    print("next: POST /api/v1/admin/rebuild-tiles (or run the Celery task) to aggregate into H3 tiles")


if __name__ == "__main__":
    main()
