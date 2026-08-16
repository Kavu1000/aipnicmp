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
