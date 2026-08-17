"""Who may see the platform — the super admin's queue.

Every route here requires a super admin. Two rules are enforced beyond that,
and both exist to stop the platform locking itself:

*You cannot decide about yourself.* Not approval, not role. Self-approval would
make the pending state decorative, and self-demotion is how someone removes
their own last route back in by accident.

*The last super admin cannot be removed.* Demoting or rejecting them would
leave a platform where nobody can approve anybody, recoverable only by editing
configuration and redeploying.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.core.operators import NETWORK_NAMES
from app.models.user import (
    ROLE_COLLECTOR,
    ROLE_OPERATOR,
    ROLE_SUPER_ADMIN,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    User,
)
from app.services.auth import require_super_admin
from app.models.device import Device
from app.models.user_device import UserDevice
from app.services.credits import cache_avatar, heading_for

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_super_admin)])


class Decision(BaseModel):
    status: Literal["approved", "rejected", "pending"]


class DeviceAssignment(BaseModel):
    """The handsets a collector account may see the readings of."""

    install_ids: list[str]


class CreditChange(BaseModel):
    """Whether somebody appears on the public sign-in page, and as what."""

    show: bool
    title: str | None = None


class RoleChange(BaseModel):
    """A role, and the network that goes with it when the role needs one.

    Every assignable role belongs in this list. It once held only the two
    administrator roles while the body of `set_role` had a whole branch for
    operators — so the branch was unreachable, the network dialog could not
    succeed, and the role this platform's whole scoping design rests on could
    never actually be given to anybody.
    """

    role: Literal["super_admin", "admin", "operator", "collector"]
    operator: str | None = None


async def _load(session: AsyncSession, user_id: int) -> User:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such user")
    return user


async def _approved_super_admins(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == ROLE_SUPER_ADMIN, User.status == STATUS_APPROVED)
        )
        or 0
    )


def _refuse_self(actor: User, target: User) -> None:
    if actor.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="you cannot change your own access; ask another super admin",
        )


async def _refuse_last_super_admin(session: AsyncSession, target: User) -> None:
    if target.role != ROLE_SUPER_ADMIN or target.status != STATUS_APPROVED:
        return
    if await _approved_super_admins(session) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="this is the last super admin; promote another one first",
        )


@router.get("")
async def list_users(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Everyone, pending first — the queue is the reason to open this page."""
    query = select(User)
    if status_filter:
        query = query.where(User.status == status_filter)

    users = (
        await session.scalars(
            query.order_by(
                # Pending sorts first without a CASE: it is the only status
                # whose queue position matters.
                (User.status != STATUS_PENDING),
                User.requested_at.desc(),
            )
        )
    ).all()

    return {
        "count": len(users),
        "pending": sum(1 for user in users if user.status == STATUS_PENDING),
        "users": [user.public_dict() for user in users],
    }


@router.post("/{user_id}/decision")
async def decide(
    user_id: int,
    body: Decision,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    target = await _load(session, user_id)
    _refuse_self(actor, target)

    if body.status in (STATUS_REJECTED, STATUS_PENDING):
        await _refuse_last_super_admin(session, target)

    target.status = body.status
    target.decided_at = datetime.now(timezone.utc)
    target.decided_by = actor.email
    await session.commit()

    return {"user": target.public_dict()}


@router.post("/{user_id}/role")
async def set_role(
    user_id: int,
    body: RoleChange,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    target = await _load(session, user_id)
    _refuse_self(actor, target)

    if body.role != ROLE_SUPER_ADMIN:
        await _refuse_last_super_admin(session, target)

    # A network account must name its network. Without one the scope resolves
    # to a sentinel that matches nothing, so the account would see an empty map
    # and nobody would know why — and a future change that treated a missing
    # scope as "no restriction" would open the whole platform instead.
    if body.role == ROLE_OPERATOR:
        network = (body.operator or "").strip()
        if network not in NETWORK_NAMES.values():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"operator must be one of: {', '.join(sorted(NETWORK_NAMES.values()))}",
            )
        target.scoped_operator = network
    else:
        # Demotion clears the network as well as the role. Leaving it behind
        # would let a later promotion silently inherit a scope nobody chose.
        target.scoped_operator = None

    target.role = body.role
    target.decided_at = datetime.now(timezone.utc)
    target.decided_by = actor.email
    # Recorded separately from the approval decision: a government platform
    # letting one company see a map its competitors appear on has to be able to
    # say who allowed it, and when.
    target.role_changed_at = target.decided_at
    target.role_changed_by = actor.email
    await session.commit()

    return {"user": target.public_dict()}


@router.post("/{user_id}/credit")
async def set_credit(
    user_id: int,
    body: CreditChange,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Put somebody on the sign-in page, or take them off it.

    A deliberate act, separate from granting access. Publishing a colleague's
    name and photograph to every visitor should never be a side effect of a
    permission change, and losing access should never erase somebody from work
    they did.

    Their portrait is copied on the way in, so the public page never sends a
    visitor's browser to Google. A failed copy is not a failed request — the
    page falls back to initials, which is a fine portrait and never expires.
    """
    target = await _load(session, user_id)

    if body.show and heading_for(target.role) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only administrators and super admins appear in the credits",
        )

    target.show_in_credits = body.show
    if body.title is not None:
        target.credit_title = body.title.strip() or None
    if not body.show:
        # The portrait goes with the credit. Keeping it would leave a
        # photograph in the database for a page that no longer shows it.
        target.avatar_image = None
        target.avatar_content_type = None
    await session.commit()

    if body.show and target.avatar_image is None:
        await cache_avatar(session, target)

    # The whole account, like every other mutation here returns, so the table
    # can replace the row it has rather than patch two fields of it.
    return {"user": target.public_dict()}


@router.post("/{user_id}/devices")
async def set_devices(
    user_id: int,
    body: DeviceAssignment,
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Say which handsets a collector account owns.

    This opens a window onto one person's movements — the readings of a
    handset are where it went and when — so it is a super admin's decision,
    recorded with an author, and replaced wholesale rather than added to, so
    the assignment on screen is the assignment in force.

    A handset belongs to one account. Assigning one that another account
    already holds is refused rather than moved: two people each told the
    readings are theirs is two people shown a third person's journey.
    """
    target = await _load(session, user_id)
    if target.role != ROLE_COLLECTOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only collector accounts own devices",
        )

    wanted = {install_id.strip() for install_id in body.install_ids if install_id.strip()}

    known = set(
        (await session.scalars(select(Device.install_id).where(Device.install_id.in_(wanted)))).all()
    )
    if wanted - known:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"no such device: {', '.join(sorted(wanted - known))}",
        )

    taken = (
        await session.execute(
            select(UserDevice.install_id, UserDevice.user_id).where(
                UserDevice.install_id.in_(wanted), UserDevice.user_id != user_id
            )
        )
    ).all()
    if taken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"already assigned to another account: {', '.join(x[0] for x in taken)}",
        )

    await session.execute(delete(UserDevice).where(UserDevice.user_id == user_id))
    for install_id in sorted(wanted):
        session.add(
            UserDevice(user_id=user_id, install_id=install_id, assigned_by=actor.email)
        )
    await session.commit()

    return {"user_id": user_id, "install_ids": sorted(wanted)}


@router.get("/devices/assignable")
async def assignable_devices(
    actor: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Every enrolled handset, with whoever already owns it.

    Full install ids, unlike the fleet page, which shortens them to sixteen
    characters so they are enough to tell two devices apart and not enough to
    be worth correlating. Assigning one needs the whole id, and this endpoint
    is a super admin's alone.

    Owners are returned rather than filtered out, so the person choosing sees
    that a handset is taken and by whom instead of wondering why it is missing.
    """
    devices = (
        await session.scalars(select(Device).order_by(Device.records_accepted.desc()))
    ).all()
    owners = {
        install_id: user_id
        for install_id, user_id in (
            await session.execute(select(UserDevice.install_id, UserDevice.user_id))
        ).all()
    }

    return {
        "devices": [
            {
                "install_id": device.install_id,
                "model": device.model,
                "manufacturer": device.manufacturer,
                "records_accepted": device.records_accepted,
                "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
                "owner_user_id": owners.get(device.install_id),
            }
            for device in devices
        ]
    }
