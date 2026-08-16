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
# quietly. Checked against the published MCC/MNC assignments in August 2026;
# recheck before a public launch, because operators merge and rebrand and Lao
# PDR has seen both — 457-08 has been Tigo, then Beeline, and is now Tplus.
# How to check this table against a real SIM.
#
# Lao mobile numbers carry the operator in the digit after the 020 prefix, so a
# phone's own number identifies its operator without trusting anything the
# handset prints:
#
#     020 5xxxxxxx  Lao Telecom (LTC)
#     020 2xxxxxxx  ETL
#     020 9xxxxxxx  Unitel
#     020 7xxxxxxx  Tplus
#
# Written down because the alternative is trusting getNetworkOperatorName(),
# and the pilot fleet showed why that fails: ten handsets reported names that
# contradicted the published MCC/MNC assignment on 98.7% of readings. A number
# is checkable in ten seconds by calling another phone; a display string is a
# guess made by firmware.

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


def lookup_mncs(mnc: str) -> tuple[str, ...]:
    """The forms of an MNC worth looking up, most literal first.

    An MNC is two or three digits and the length is meaningful in principle,
    but Android reports whichever the SIM happens to encode: the same Lao
    Telecom SIM appears as "01" on one handset and "001" on another. Looking up
    only the literal value files those as two different networks — the same
    split that "LTC" and "LAO TELECOM" caused, one layer down.

    So a three-digit form with a leading zero also tries its two-digit form.
    Safe here because no Lao network uses a three-digit MNC; a country that had
    one would need this reconsidered.
    """
    if len(mnc) == 3 and mnc.startswith("0"):
        return (mnc, mnc[1:])
    return (mnc,)


def reported_mnc_forms(table_mnc: str) -> tuple[str, ...]:
    """The inverse: every form a handset might report for a table entry.

    :func:`lookup_mncs` goes from what arrived to what to look up, which suits
    Python. SQL needs the other direction — the table entry is the constant and
    the column is the unknown — so a network stored as "01" has to match both
    "01" and "001" in the measurements.
    """
    if len(table_mnc) == 2:
        return (table_mnc, f"0{table_mnc}")
    return (table_mnc,)


def canonical_operator(
    mcc: str | None, mnc: str | None, reported_name: str | None
) -> str | None:
    """One name per network, whatever the handset called it.

    Returns None when there is nothing to attribute the reading to. A record
    with no network at all has no operator, and inventing one would put dead
    zones on some carrier's ledger.
    """
    code = mcc.strip() if mcc else None
    normalised = normalise_mnc(mnc)

    if code and normalised:
        for candidate in lookup_mncs(normalised):
            known = NETWORK_NAMES.get((code, candidate))
            if known:
                return known
        # An unrecognised network still has a stable identity; showing it as
        # "457-05" is honest, and obviously a code rather than a company.
        return f"{code}-{normalised}"

    name = (reported_name or "").strip()
    return name or None


# What a handset calls each operator, for matching a SIM's own brand.
#
# The reverse of NETWORK_NAMES, and used for a different question. NETWORK_NAMES
# answers "whose radio is this?" from the PLMN. This answers "whose SIM is in
# the phone?" from the string the handset prints, which is the SIM's service
# provider name and follows the subscription rather than the serving network.
#
# The two disagree exactly when a phone is roaming — a Tplus SIM carried by Lao
# Telecom's network reports "TPLUS Digital" while camped on Lao Telecom's PLMN.
# That is worth knowing: for the subscriber, Tplus coverage in that place *is*
# Lao Telecom's coverage, which is a competition and roaming question rather
# than a tower question.
#
# Matched on a squashed form so spacing, case and suffixes like "Mobile" or
# "Digital" do not each become a separate operator.
REPORTED_NAME_PATTERNS: dict[str, tuple[str, ...]] = {
    "Lao Telecom": ("laotelecom", "ltc", "laotel"),
    "ETL": ("etl",),
    "Unitel": ("unitel", "startelecom"),
    "Tplus": ("tplus", "beeline", "tigo"),
}


def operator_from_reported_name(reported: str | None) -> str | None:
    """Which operator a handset's own label refers to, if any.

    Deliberately conservative: an unrecognised string returns None rather than
    a guess. A wrong answer here would invent a roaming relationship between two
    named companies, which is worse than saying nothing.
    """
    if not reported:
        return None
    squashed = "".join(ch for ch in reported.lower() if ch.isalnum())
    if not squashed:
        return None
    for operator, patterns in REPORTED_NAME_PATTERNS.items():
        if any(pattern in squashed for pattern in patterns):
            return operator
    return None
