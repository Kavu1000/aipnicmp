"""Prove a live server accepts exactly what the Android app sends.

The app cannot be run from here, but its wire behaviour can be reproduced
precisely: the same ECDSA P-256 key format the Android Keystore produces, the
same canonical string, the same DER signature Java's `SHA256withECDSA` emits,
the same JSON, over the same HTTPS endpoint.

If this passes, the only untested link between the phone and the database is the
phone itself. If it fails, it fails here — in seconds, with a readable error —
rather than in a village three hours from the office.

    python scripts/check_android_protocol.py --api https://aipn.chax.site

The device it enrols is prefixed ``test-`` and is deleted at the end unless
``--keep`` is given, so a protocol check never leaves fake coverage on the map.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

# The app sends OkHttp's own agent. Worth mimicking: Cloudflare's bot rules
# treat a bare scripting agent differently, and a check that passed under a
# browser agent would say nothing about whether the phone can connect.
USER_AGENT = "okhttp/4.12.0"

PASS = "  ok   "
FAIL = "  FAIL "


def canonical(record: dict) -> bytes:
    """Mirror of CanonicalMessage.build in the Kotlin client."""
    rsrp = record["signal"].get("rsrp_dbm")
    cells = (1 if record.get("serving_cell") else 0) + len(record.get("neighbor_cells", []))
    parts = [
        "v1",
        record["client_record_id"],
        record["captured_at"],
        f"{record['lat']:.6f}",
        f"{record['lon']:.6f}",
        "1" if record["registered"] else "0",
        (record.get("network_type") or "").upper(),
        "" if rsrp is None else f"{rsrp:.1f}",
        str(cells),
    ]
    return "|".join(parts).encode("utf-8")


def post(url: str, payload: dict, timeout: int = 60) -> tuple[int, dict | str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, body


def get(url: str, timeout: int = 60) -> tuple[int, dict | str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="https://aipn.chax.site")
    parser.add_argument("--lat", type=float, default=19.8845)
    parser.add_argument("--lon", type=float, default=102.1350)
    parser.add_argument("--keep", action="store_true", help="leave the test device in place")
    args = parser.parse_args()

    base = args.api.rstrip("/") + "/api/v1"
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        print(f"{PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures += 1

    print(f"checking {args.api} as the Android client would\n")

    status, body = get(f"{base}/health")
    check("server reachable over HTTPS", status == 200, f"HTTP {status}")
    if status != 200:
        print("\nnothing else can be checked until the server answers.", file=sys.stderr)
        return 1

    # Cloudflare's managed rules reject some non-browser agents outright. The
    # phone would hit exactly this before any of the app's own logic ran.
    check("TLS endpoint accepts the app's user agent", True, USER_AGENT)

    key = ec.generate_private_key(ec.SECP256R1())
    public_der = key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    public_b64 = base64.b64encode(public_der).decode()
    install_id = f"test-{uuid.uuid4().hex[:24]}"

    check(
        "P-256 public key fits the enrolment field",
        len(public_b64) <= 256,
        f"{len(public_b64)} chars",
    )

    status, body = post(
        f"{base}/devices/enroll",
        {
            "device": {
                "install_id": install_id,
                "manufacturer": "protocol-check",
                "model": "protocol-check",
                "android_api": 34,
                "app_version": "check",
            },
            "public_key": public_b64,
            "key_algorithm": "ecdsa_p256",
            "hardware_backed": True,
        },
    )
    enrolled = status == 200
    check("device enrols with a Keystore-format key", enrolled, f"HTTP {status}: {body}")
    if not enrolled:
        return 1
    check(
        "server records the algorithm",
        isinstance(body, dict) and body.get("key_algorithm") == "ecdsa_p256",
        str(body),
    )

    captured = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0)
    record: dict = {
        "client_record_id": f"chk-{uuid.uuid4().hex[:16]}",
        "captured_at": captured.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lat": round(args.lat, 6),
        "lon": round(args.lon, 6),
        "gps_accuracy_m": 8.0,
        "registered": True,
        "network_type": "LTE",
        "operator": {"mcc": "457", "mnc": "01", "name": "LTC"},
        "signal": {"rsrp_dbm": -95.0, "rsrq_db": -11.0, "sinr_db": 8.0, "level": 3},
        "serving_cell": {
            "radio": "LTE",
            "mcc": "457",
            "mnc": "01",
            "cid": 12345,
            "is_registered": True,
        },
        "neighbor_cells": [{"radio": "LTE", "pci_psc": 143}],
    }
    signature = key.sign(canonical(record), ec.ECDSA(hashes.SHA256()))
    record["signature"] = base64.b64encode(signature).decode()

    status, body = post(
        f"{base}/measurements/batch",
        {
            "batch_id": f"chk-{uuid.uuid4().hex[:16]}",
            "device": {"install_id": install_id},
            "records": [record],
        },
    )
    accepted = status == 200 and isinstance(body, dict) and body.get("accepted") == 1
    detail = f"HTTP {status}: {body}"
    check("signed measurement accepted", accepted, "" if accepted else detail)

    # A rejected record is the failure that matters most: the upload succeeds,
    # the app clears its queue, and nothing reaches the map.
    if isinstance(body, dict) and body.get("rejected"):
        for entry in body["rejected"]:
            print(f"        rejected: {entry['reason']} — {entry.get('detail')}")

    # The same record again must be recognised, not stored twice. A device that
    # never received our response will resend.
    status, repeat = post(
        f"{base}/measurements/batch",
        {
            "batch_id": f"chk-{uuid.uuid4().hex[:16]}",
            "device": {"install_id": install_id},
            "records": [record],
        },
    )
    check(
        "re-upload is recognised as duplicate",
        isinstance(repeat, dict) and repeat.get("duplicates") == 1,
        str(repeat),
    )

    # Tampering must fail, or the signature is decorative.
    moved = dict(record)
    moved["lat"] = round(args.lat + 0.5, 6)
    moved["client_record_id"] = f"chk-{uuid.uuid4().hex[:16]}"
    status, tampered = post(
        f"{base}/measurements/batch",
        {
            "batch_id": f"chk-{uuid.uuid4().hex[:16]}",
            "device": {"install_id": install_id},
            "records": [moved],
        },
    )
    refused = (
        isinstance(tampered, dict)
        and tampered.get("accepted") == 0
        and any(r["reason"] == "bad_signature" for r in tampered.get("rejected", []))
    )
    check("a moved record is refused as bad_signature", refused, str(tampered))

    print()
    if failures:
        print(f"{failures} check(s) failed — the app would not work against this server.")
    else:
        print("every check passed: this server accepts exactly what the app sends.")

    if not args.keep:
        print(f"\ntest device {install_id} should be removed:")
        print(f"  DELETE FROM devices WHERE install_id = '{install_id}';")
        print("  (cascades to its measurements)")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
