"""Shared plumbing for the feature builders: fetching rasters and reading them.

Downloads are cached on disk and never re-fetched. The whole point of building
features offline is that it happens rarely; re-downloading gigabytes because a
later stage crashed would make the pipeline unusable.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("geodata")

# Overridable so a machine with a small system drive can put several gigabytes
# of raster somewhere else.
CACHE = Path(os.environ.get("AIPN_GEODATA_DIR", Path.home() / ".aipnicmp" / "geodata"))

# Lao PDR, rounded outward to whole degrees. Checked against the hexagon grid:
# its cells span 13.91N-22.51N and 100.09E-107.70E.
LAO_BBOX = {"min_lat": 13, "max_lat": 22, "min_lon": 100, "max_lon": 107}


def fetch(url: str, name: str, *, subdir: str) -> Path | None:
    """Download once, then reuse. Returns None if the source has no such file.

    A missing tile is normal and not an error: the Copernicus grid has no tile
    where a degree square is entirely ocean, and asking for one is how you find
    out. Anything else is raised, because a network failure that silently
    produced a partial feature layer would be much worse than a crash.
    """
    directory = CACHE / subdir
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name

    if target.exists() and target.stat().st_size > 0:
        return target

    partial = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=180) as response, partial.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
    except urllib.error.HTTPError as problem:
        partial.unlink(missing_ok=True)
        if problem.code in (403, 404):
            return None
        raise

    # Renamed only once complete, so an interrupted run cannot leave a
    # truncated file that later looks like a valid cache hit.
    partial.replace(target)
    return target


def dem_tiles() -> list[tuple[str, str]]:
    """Every Copernicus GLO-90 tile covering Laos, as (url, filename).

    GLO-90 rather than GLO-30: at 90 m a hexagon 920 m across still contains
    roughly 100 samples, which is ample for a mean and a ruggedness figure,
    and the whole country is a few hundred megabytes instead of several
    gigabytes.
    """
    out = []
    for lat in range(LAO_BBOX["min_lat"], LAO_BBOX["max_lat"] + 1):
        for lon in range(LAO_BBOX["min_lon"], LAO_BBOX["max_lon"] + 1):
            stem = f"Copernicus_DSM_COG_30_N{lat:02d}_00_E{lon:03d}_00_DEM"
            out.append((f"https://copernicus-dem-90m.s3.amazonaws.com/{stem}/{stem}.tif", f"{stem}.tif"))
    return out
