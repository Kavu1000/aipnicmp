"""Which network a measurement belongs to, expressed as SQL.

The rule itself lives in ``app/core/operators.py``: a network is its MCC/MNC
pair, not the name a handset happened to report. This module is that rule
written as a SQL expression, so grouping happens in the database.

It has to be an expression rather than a Python pass because the aggregates it
feeds count *distinct devices*, and distinct counts cannot be summed back
together after the fact — a collector seen under two spellings of one network
is one collector, and folding the groups afterwards would report two.

Kept in its own module because both the tile aggregation and the collector
fleet need it, and putting it in either one would make the other import it —
``coverage`` and ``aggregate`` already reach each other through ``areas``.
"""

from __future__ import annotations

from sqlalchemy import String, and_, case, func, literal, or_

from app.core.operators import NETWORK_NAMES
from app.models.measurement import Measurement


def padded_mnc():
    """MNC as two digits. One handset reports "1" where another reports "01".

    Concatenation is written with ``+`` on a String column, which SQLAlchemy
    renders as the ``||`` operator. ``concat()`` is a Postgres function and does
    not exist in the SQLite the tests run on.
    """
    return case(
        (func.length(Measurement.mnc) == 1, literal("0", String) + Measurement.mnc),
        else_=Measurement.mnc,
    )


def canonical_operator_column():
    """The operator's identity, resolved from MCC/MNC rather than the reported
    name — see app/core/operators.py for why one company otherwise appears as
    several."""
    mnc = padded_mnc()
    known = [
        (and_(Measurement.mcc == mcc, mnc == network_mnc), name)
        for (mcc, network_mnc), name in NETWORK_NAMES.items()
    ]
    return case(
        *known,
        # A network not in the table keeps its stable identity as a code, which
        # is honest and obviously not a company name.
        (
            and_(Measurement.mcc.is_not(None), mnc.is_not(None)),
            Measurement.mcc + literal("-", String) + mnc,
        ),
        else_=func.trim(Measurement.operator_name),
    )


def has_operator_identity():
    """Something to attribute the reading to — a PLMN, or failing that a name.

    A reading with no network at all has neither, and is excluded: bucketing
    those into "unknown" would put dead zones on some carrier's ledger.
    """
    return or_(
        and_(Measurement.mcc.is_not(None), Measurement.mnc.is_not(None)),
        and_(
            Measurement.operator_name.is_not(None),
            func.trim(Measurement.operator_name) != "",
        ),
    )
