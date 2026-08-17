"""The people shown on the sign-in page, and their portraits.

Two things are kept separate here that look like one thing.

*Access* is the role: who may read the map, who may approve accounts. *Credit*
is `show_in_credits`: whose name a visitor sees. Deriving the second from the
first would mean granting somebody admin published their photograph to every
visitor, and revoking it erased them from work they did. So a super admin says
who appears; the role only chooses the heading.

Portraits are copied into this platform rather than linked. A Google photo URL
expires, so a linked portrait breaks silently months later — and worse, every
visitor's browser would fetch it from Google before signing in to anything,
which tells Google who reads this platform. One fetch here, from our server,
and no visitor ever talks to Google.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import ROLE_ADMIN, ROLE_SUPER_ADMIN, STATUS_APPROVED, User

log = logging.getLogger(__name__)

#: Refuse anything larger. A profile photo is tens of kilobytes; a megabyte is
#: either not a photo or not one worth putting in a row of this table.
MAX_AVATAR_BYTES = 512 * 1024

#: Only real image types, and only ones every browser renders. The bytes are
#: served back with this header, so an SVG here would be a script running on
#: our own origin.
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

FETCH_TIMEOUT_S = 6.0


async def cache_avatar(session: AsyncSession, user: User) -> bool:
    """Copy this user's Google photo into the database. Returns success.

    Failure is not an error worth stopping for: the sign-in page falls back to
    initials, which is a perfectly good portrait and never expires.
    """
    if not user.picture_url:
        return False

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S, follow_redirects=True) as client:
            response = await client.get(user.picture_url)
            response.raise_for_status()
    except Exception as problem:  # noqa: BLE001 — any failure means initials
        log.warning("could not fetch avatar for %s: %s", user.email, problem)
        return False

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        log.warning("refused avatar for %s: content type %r", user.email, content_type)
        return False
    if len(response.content) > MAX_AVATAR_BYTES:
        log.warning("refused avatar for %s: %d bytes", user.email, len(response.content))
        return False

    user.avatar_image = response.content
    user.avatar_content_type = content_type
    await session.commit()
    return True


def heading_for(role: str) -> str | None:
    """Which part of the credits a role belongs under.

    Only two roles are credited. An operator account belongs to a network
    rather than to this project, and crediting one would say the network built
    the platform that measures it.
    """
    if role == ROLE_ADMIN:
        return "team"
    if role == ROLE_SUPER_ADMIN:
        return "advisors"
    return None


async def credited_people(session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    """Everyone a super admin has put on the sign-in page.

    Returns names, titles and whether a portrait exists — never the email
    address. This is read by anybody who loads the page, and an address on it
    is an address in a scraper's list an hour later.
    """
    users = (
        await session.scalars(
            select(User)
            .where(
                User.show_in_credits.is_(True),
                User.status == STATUS_APPROVED,
                User.role.in_((ROLE_ADMIN, ROLE_SUPER_ADMIN)),
            )
            .order_by(User.credit_title, User.name)
        )
    ).all()

    grouped: dict[str, list[dict[str, Any]]] = {"team": [], "advisors": []}
    for user in users:
        heading = heading_for(user.role)
        if heading is None:
            continue
        grouped[heading].append(
            {
                "id": user.id,
                "name": user.name or "",
                "title": user.credit_title,
                "has_avatar": user.avatar_image is not None,
            }
        )
    return grouped
