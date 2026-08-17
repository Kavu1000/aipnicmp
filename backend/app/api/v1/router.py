"""Which routes need an approved account, and which must never.

The split is by *who is calling*, not by how sensitive the data is.

Collector phones authenticate with a device signature over every record and
have no Google account to sign in with, so enrolment and upload stay open —
gating them would silently stop the fleet the moment sign-in was switched on.
Health checks stay open for the same class of reason: a load balancer cannot
sign in either.

Everything a person reads — the map, the areas, the dashboard, the ranked
sites — requires an approved account. The tile rebuild keeps its separate
admin token, which predates accounts and is used by the scheduled worker.
"""

from fastapi import APIRouter, Depends

from app.api.v1 import (
    admin,
    areas,
    cells,
    credits,
    mine,
    auth,
    dashboard,
    devices,
    exports,
    health,
    ingest,
    reports,
    sites,
    speedtest,
    tiles,
    users,
    weak_areas,
)
from app.services.auth import deny_collector_accounts, require_user

api_router = APIRouter()

# Open: machines call these, and they have their own authentication.
api_router.include_router(health.router)
api_router.include_router(devices.router)
api_router.include_router(ingest.router)
api_router.include_router(admin.router)
# The collector measures throughput against this, and it must work from a
# handset that has not signed in to anything.
api_router.include_router(speedtest.router)

# Open because signing in is how you stop being anonymous.
api_router.include_router(auth.router)
# Open: the credits appear on the sign-in page itself, and carry names and
# titles only — never an address, and never who holds which access.
api_router.include_router(credits.router)

# Requires an approved account — and is closed to collector accounts.
#
# The denial sits on the list rather than on each endpoint, so a route added
# later is shut to collectors until somebody decides otherwise. The operator
# role learned this the expensive way: scoping was opt-in, one endpoint did not
# opt in, and a network account could see its competitors' masts. A collector
# account holds a record of where one person has been, so the same mistake here
# would show somebody else's movements.
signed_in = [Depends(require_user), Depends(deny_collector_accounts)]
api_router.include_router(areas.router, dependencies=signed_in)
api_router.include_router(dashboard.router, dependencies=signed_in)
api_router.include_router(tiles.router, dependencies=signed_in)
api_router.include_router(cells.router, dependencies=signed_in)
api_router.include_router(reports.router, dependencies=signed_in)
api_router.include_router(sites.router, dependencies=signed_in)
api_router.include_router(exports.router, dependencies=signed_in)
api_router.include_router(weak_areas.router, dependencies=signed_in)

# The one router a collector account may reach. Every endpoint on it is scoped
# to the handsets that account owns, and owns nothing by default.
api_router.include_router(mine.router, dependencies=[Depends(require_user)])

# Requires a super admin; the router enforces that itself.
api_router.include_router(users.router)
