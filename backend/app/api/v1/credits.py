"""The credits, and the portraits beside them.

Open, because the sign-in page is what they appear on and nobody has signed in
yet. That is exactly why the payload is names and titles only: no email
addresses, no roles by name, no counts of who holds what access. A public page
listing the administrators of a system with their email addresses is a
phishing target with a helpful directory attached.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.user import User
from app.services.credits import credited_people

router = APIRouter(prefix="/credits", tags=["credits"])

#: Portraits change when somebody changes their Google photo and a super admin
#: refreshes it, which is rarely. A day of caching saves the fetch on every
#: visit; the id in the path changes if the person does.
AVATAR_CACHE_SECONDS = 86_400


@router.get("")
async def credits(session: AsyncSession = Depends(get_session)) -> dict:
    """Who built the platform and who advised it."""
    return await credited_people(session)


@router.get("/{user_id}/avatar")
async def avatar(user_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    """One credited person's portrait, served from this platform.

    Guarded by the same flag as the list: an id that is not credited returns
    404 rather than a photograph, so this cannot be walked to enumerate the
    portraits of every account that ever signed in.
    """
    user = await session.get(User, user_id)
    if user is None or not user.show_in_credits or user.avatar_image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no portrait")

    return Response(
        content=user.avatar_image,
        media_type=user.avatar_content_type or "image/jpeg",
        headers={"Cache-Control": f"public, max-age={AVATAR_CACHE_SECONDS}"},
    )
