"""Who a network actually is, as opposed to what a handset calls it.

``TelephonyManager.getNetworkOperatorName()`` returns a display string chosen by
the SIM, the network or the firmware, and the three disagree. One Lao
Telecommunications SIM reports "LTC", another reports "LAO TELECOM", and a third
may report the operator's marketing name. Grouping coverage by that string
splits one operator's map into several partial ones — which is exactly what
happened in the pilot: 124 tiles under "LTC" and 1 under "LAO TELECOM".

The stable identity is the MCC/MNC pair, which the device already sends and the
measurement table already stores. It is what identifies a network in every
standard, and it does not change with the handset.

So: identity comes from MCC/MNC, and the display name comes from the table
below. A pair that is not in the table falls back to the reported name, which
keeps an unrecognised network visible under whatever it called itself rather
than dropping it.
"""

from __future__ import annotations

LAO_MCC = "457"

# Lao PDR networks, by MCC/MNC.
#
# This table decides the name shown on the public map and in every operator
# report, so a wrong entry here mislabels a company rather than degrading
# quietly. Check it against the current ITU/GSMA assignment before a public
# launch — operators merge and rebrand, and Lao PDR has seen both.
NETWORK_NAMES: dict[tuple[str, str], str] = {
    (LAO_MCC, "01"): "Lao Telecom",  # Lao Telecommunications Company (LTC)
    (LAO_MCC, "02"): "ETL",  # Enterprise of Telecommunications Lao
    (LAO_MCC, "03"): "Unitel",  # Star Telecom
    (LAO_MCC, "08"): "Tplus",  # formerly Beeline, and Tigo before that
}


def normalise_mnc(mnc: str | None) -> str | None:
    """MNCs are zero-padded to two digits.

    A handset may report "1" where another reports "01"; without this they are
    two different networks, which is the same bug one level down.
    """
    if mnc is None:
        return None
    digits = mnc.strip()
    if not digits.isdigit():
        return None
    return digits.zfill(2) if len(digits) < 2 else digits


def canonical_operator(
    mcc: str | None, mnc: str | None, reported_name: str | None
) -> str | None:
    """One name per network, whatever the handset called it.

    Returns None when there is nothing to attribute the reading to. A record
    with no network at all has no operator, and inventing one would put dead
    zones on some carrier's ledger.
    """
    key = (mcc.strip() if mcc else None, normalise_mnc(mnc))
    if key[0] and key[1]:
        known = NETWORK_NAMES.get((key[0], key[1]))
        if known:
            return known
        # An unrecognised network still has a stable identity; showing it as
        # "457-05" is honest, and obviously a code rather than a company.
        return f"{key[0]}-{key[1]}"

    name = (reported_name or "").strip()
    return name or None
