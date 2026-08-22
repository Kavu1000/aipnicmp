"""People who may see the platform.



Identity comes from Google; authorisation does not. Signing in with Google

proves only that an address belongs to whoever is holding it, which is the

easy half. The half that matters is that a super admin has since looked at the

request and allowed it — so a new account lands in ``pending`` and can read

nothing until then.



That ordering is deliberate. An allowlist checked at sign-in would be the same

idea with the decision made in a config file instead of in the product, and

whoever needed access would have to wait for a redeploy.



No password is ever stored, or could be: this table holds what Google asserts

about an account and what a super admin decided about it, and nothing else.

"""



from __future__ import annotations



from datetime import datetime



from sqlalchemy import Boolean, Index, Integer, LargeBinary, String, func

from sqlalchemy.orm import Mapped, mapped_column



from app.db.base import Base, timestamp_column



ROLE_SUPER_ADMIN = "super_admin"

ROLE_ADMIN = "admin"



# An account belonging to a network, which may see that network and nothing

# else. These four companies compete, so this is not a convenience filter — a

# leak between them is commercially damaging and would end the pilot. The scope

# is therefore taken from the account on every request and never from anything

# the client sends.

ROLE_OPERATOR = "operator"



# Somebody carrying a phone. Sees the ground they personally covered and
# nothing else: not another collector's readings, not the fleet, not any
# network's coverage but the ones their own handsets happened to be on. The
# isolation runs the same way as an operator's — taken from the account on
# every request, never from anything the client sends — because the thing it
# protects is a record of where a particular person has been.
ROLE_COLLECTOR = "collector"

ROLES = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_OPERATOR, ROLE_COLLECTOR)

# The scope given to an operator account with no network set. It matches no
# real network, so a misconfigured account sees nothing rather than everything
# — the only safe direction when the alternative is showing one company its
# competitors' coverage.
NO_NETWORK = "__no_network__"

#: The device scope of a collector account that owns no handsets.
#:
#: Matches no install id, so an account nobody has assigned a phone to sees an
#: empty page rather than the whole fleet. Same direction as NO_NETWORK, and
#: for the same reason: the failure has to be "shows nothing".
NO_DEVICES: frozenset[str] = frozenset()



STATUS_PENDING = "pending"

STATUS_APPROVED = "approved"

STATUS_REJECTED = "rejected"

STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)





class User(Base):

    """One Google account, and what it is allowed to do here."""



    __tablename__ = "users"



    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)



    # Google's stable identifier for the account. The address can change —

    # people rename mailboxes, and organisations reassign them — so the subject

    # is what identity is keyed on, and the address is treated as a label.

    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)



    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)

    name: Mapped[str | None] = mapped_column(String(160))

    picture_url: Mapped[str | None] = mapped_column(String(500))



    role: Mapped[str] = mapped_column(String(16), default=ROLE_ADMIN, server_default=ROLE_ADMIN)

    status: Mapped[str] = mapped_column(

        String(16), default=STATUS_PENDING, server_default=STATUS_PENDING

    )



    requested_at: Mapped[datetime] = timestamp_column(server_default=func.now())

    decided_at: Mapped[datetime | None] = timestamp_column()

    # The email of the super admin who decided, kept rather than a foreign key:

    # this is an audit trail, and it should survive that account being removed.

    decided_by: Mapped[str | None] = mapped_column(String(320))



    # The network an operator account may see. Meaningless for any other role,

    # and required for this one: an operator account with no network would be

    # scoped to nothing, which fails open the moment a query treats "no scope"

    # as "no restriction".

    scoped_operator: Mapped[str | None] = mapped_column(String(120))



    # Who changed this account's role, and when. A government platform granting

    # one company sight of a map its competitors also appear on needs to be

    # able to say who allowed it.

    role_changed_at: Mapped[datetime | None] = timestamp_column()

    role_changed_by: Mapped[str | None] = mapped_column(String(320))



    last_login_at: Mapped[datetime | None] = timestamp_column()

    login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    #: Whether this person appears in the credits on the public sign-in page.
    #:
    #: Deliberately not derived from ``role``. Granting somebody admin would
    #: otherwise publish their name and photograph to every visitor, and taking
    #: their access away would erase them from work they did. The role decides
    #: only which heading they appear under once a super admin has put them
    #: there.
    show_in_credits: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    #: What they did — "Android collector", not "admin".
    credit_title: Mapped[str | None] = mapped_column(String(120))

    #: Their portrait, copied here rather than linked.
    #:
    #: Google's photo URLs expire, and linking one would make every visitor's
    #: browser fetch it from Google before signing in to anything.
    avatar_image: Mapped[bytes | None] = mapped_column(LargeBinary)
    avatar_content_type: Mapped[str | None] = mapped_column(String(40))



    __table_args__ = (Index("ix_users_status_role", "status", "role"),)



    @property

    def is_approved(self) -> bool:

        return self.status == STATUS_APPROVED



    @property

    def is_operator(self) -> bool:

        return self.role == ROLE_OPERATOR



    @property

    def is_collector(self) -> bool:

        return self.role == ROLE_COLLECTOR



    @property

    def operator_scope(self) -> str | None:

        """The network this account is confined to, or None for unrestricted.



        None means "sees everything", so it is only ever returned for roles

        that genuinely should. An operator account whose network is unset

        returns a name that matches nothing rather than None, because failing

        closed on a misconfiguration is the only safe direction here.

        """

        if self.role != ROLE_OPERATOR:

            return None

        return self.scoped_operator or NO_NETWORK



    @property

    def is_super_admin(self) -> bool:

        return self.role == ROLE_SUPER_ADMIN and self.is_approved



    def public_dict(self) -> dict:

        return {

            "id": self.id,

            "email": self.email,

            "name": self.name,

            "picture_url": self.picture_url,

            "role": self.role,
            "scoped_operator": self.scoped_operator,
            # Whether this person appears on the public sign-in page. Sent to
            # the super admin who decides it; never to the page itself, which
            # gets names and titles and nothing else.
            "is_collector": self.is_collector,
            "show_in_credits": self.show_in_credits,
            "credit_title": self.credit_title,
            "role_changed_at": self.role_changed_at.isoformat() if self.role_changed_at else None,
            "role_changed_by": self.role_changed_by,

            "status": self.status,

            "requested_at": self.requested_at.isoformat() if self.requested_at else None,

            "decided_at": self.decided_at.isoformat() if self.decided_at else None,

            "decided_by": self.decided_by,

            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,

            "login_count": self.login_count,

        }

