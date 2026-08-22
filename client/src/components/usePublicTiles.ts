import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPublicTiles, PUBLIC_MAX_BBOX_DEGREES, type Bounds, type TileCollection } from "../api";

const EMPTY: TileCollection = { type: "FeatureCollection", features: [] };

/**
 * How long a fetched viewport may be reused before it is asked for again.
 *
 * Matched to the `Cache-Control: max-age=60` the public endpoints already
 * send (see backend/app/api/v1/public.py): the server has stated for how long
 * it considers an answer current, and holding it in memory for longer than
 * that would be this client inventing a freshness promise the server did not
 * make. Hexagons are rebuilt by an aggregation run, not by the minute, so a
 * minute costs a reader nothing.
 */
const CACHE_MS = 60_000;

/**
 * The grid a viewport is rounded out to before it is requested, chosen by how
 * much of the world is on screen.
 *
 * A pan produces a continuous stream of *different* bounding boxes, so every
 * request was a new URL: nothing could be reused, neither by this hook nor by
 * the browser's own HTTP cache, and each nudge of the map cost a full round
 * trip to a database that answers in under a millisecond but sits behind a
 * tunnel that takes closer to a second. Rounding outward to a grid makes the
 * URL stable across small movements, which is what turns most pans into a
 * cache hit and no request at all.
 *
 * The grid tracks zoom because a fixed one would be wrong at both ends: 0.25°
 * is ~27 km, invisible padding when the screen shows a province and a tenfold
 * overfetch when it shows a village. Each step keeps the requested box within
 * roughly twice the visible one.
 *
 * It stops at 0.25° rather than continuing to grow, because past that the
 * padding competes with the viewport itself for the server's 3° budget — a
 * coarser grid would cache slightly better while showing a zoomed-out reader
 * less of the country, which is the wrong trade for the one view where the
 * map is trying to say how much of Laos has been surveyed at all.
 */
function snapDegrees(span: number): number {
  if (span < 0.2) return 0.05;
  if (span < 0.5) return 0.1;
  return 0.25;
}

/**
 * The widest box the server will answer, with a margin for float error.
 *
 * `/public/tiles` refuses anything over PUBLIC_MAX_BBOX_DEGREES per side, and
 * a box built by arithmetic can land a rounding error above a limit it was
 * meant to land on.
 */
const LIMIT = PUBLIC_MAX_BBOX_DEGREES - 0.05;

/**
 * One axis of the request: the visible range, clamped, padded and rounded.
 *
 * The padding is what makes a pan free. A box that stops exactly where the
 * screen stops is stale the moment the map moves a pixel, so each axis is
 * grown by one grid step beyond what is visible — a margin the reader can pan
 * into without a request being made at all. The rounding on top of it is what
 * makes the *URL* repeat, so that a viewport returned to is served by the
 * browser's own cache and by the server's.
 *
 * Both give way to the limit rather than the other way around: when the
 * screen already shows nearly as much as the server will answer, the padding
 * shrinks to nothing and the rounding is skipped, leaving exactly the clamped
 * range this function has always returned. A wide view keeps every degree of
 * coverage it can get; only a view with room to spare spends it on margin.
 */
function axis(min: number, max: number, step: number): [number, number] {
  const centre = (min + max) / 2;
  const half = Math.min((max - min) / 2, LIMIT / 2);
  const pad = Math.min(step, LIMIT / 2 - half);

  const lo = centre - half - pad;
  const hi = centre + half + pad;

  const snapped: [number, number] = [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
  return snapped[1] - snapped[0] <= LIMIT ? snapped : [lo, hi];
}

/**
 * A viewport turned into the box that will be asked for.
 *
 * MapView's internal clamp targets MAX_BBOX_DEGREES = 6, the signed-in
 * limit, and is not told which caller it is serving — reused as-is here
 * rather than taught a second constant, so this narrows its answer down to
 * PUBLIC_MAX_BBOX_DEGREES instead. Shrinking around the centre rather than
 * from a corner keeps the visible middle of the screen the part that stays
 * queried when a corner has to give.
 */
function toPublicBounds(bounds: Bounds): Bounds {
  const step = snapDegrees(Math.max(bounds.maxLat - bounds.minLat, bounds.maxLon - bounds.minLon));
  const [minLat, maxLat] = axis(bounds.minLat, bounds.maxLat, step);
  const [minLon, maxLon] = axis(bounds.minLon, bounds.maxLon, step);
  return { minLat, maxLat, minLon, maxLon };
}

/** Does `outer` hold every part of `inner`? */
function contains(outer: Bounds, inner: Bounds): boolean {
  return (
    outer.minLat <= inner.minLat &&
    outer.maxLat >= inner.maxLat &&
    outer.minLon <= inner.minLon &&
    outer.maxLon >= inner.maxLon
  );
}

/** One request's identity: the same box and network is the same answer. */
function cacheKey(bounds: Bounds, operator: string | null): string {
  const round = (value: number) => value.toFixed(3);
  return [
    round(bounds.minLat),
    round(bounds.minLon),
    round(bounds.maxLat),
    round(bounds.maxLon),
    operator ?? "",
  ].join("|");
}

interface Fetched {
  /** The box that was asked for — wider than the viewport that asked. */
  bounds: Bounds;
  at: number;
  collection: TileCollection;
}

/**
 * Debounced, abort-safe loading of /public/tiles for whatever viewport
 * MapView reports — shared by the full map at /map and the small live
 * preview on the landing page, so the clamping, the cache and the debounce
 * exist once.
 *
 * What keeps hexagons on screen is that most viewports are never requested.
 * Every fetch asks for the viewport rounded out to a grid, so what comes back
 * covers more ground than the screen shows; a later viewport that fits inside
 * a box already held is answered from memory, synchronously, with no debounce
 * and no request — a pan of a few hundred metres, or a return to somewhere
 * just visited, redraws in the time it takes React to render. Only a viewport
 * that escapes everything held waits behind the debounce, which exists to
 * stop a drag firing a request per frame.
 *
 * This matters more here than the round trip suggests. The query itself takes
 * under a millisecond; the tunnel to the database takes most of a second, and
 * that second was being paid on every nudge of the map.
 *
 * `operator` re-fetches the last known viewport immediately, no debounce:
 * choosing a network from a dropdown is one deliberate action, not the
 * stream of events a pan produces.
 */
export function usePublicTiles(operator: string | null = null) {
  const [tiles, setTiles] = useState<TileCollection>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef<AbortController | null>(null);
  const debounce = useRef<number | null>(null);
  const lastBounds = useRef<Bounds | null>(null);
  /** Newest first, so the answer a reader gets is the most recent one that fits. */
  const cache = useRef<Fetched[]>([]);
  /** The box currently being fetched, so a repeated pan does not re-ask. */
  const pending = useRef<string | null>(null);

  /** The freshest held box that covers this viewport, if any still does. */
  const held = useCallback((viewport: Bounds): TileCollection | null => {
    const now = Date.now();
    cache.current = cache.current.filter((entry) => now - entry.at < CACHE_MS);
    return cache.current.find((entry) => contains(entry.bounds, viewport))?.collection ?? null;
  }, []);

  const fetchNow = useCallback(
    (viewport: Bounds) => {
      const hit = held(viewport);
      if (hit) {
        setTiles(hit);
        setError(null);
        return;
      }

      const query = toPublicBounds(viewport);
      const key = cacheKey(query, operator);
      if (pending.current === key) return;

      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      pending.current = key;

      fetchPublicTiles(query, operator, controller.signal)
        .then((collection) => {
          // Bounded: a long session panning across the country would
          // otherwise hold every viewport it ever visited.
          cache.current = [{ bounds: query, at: Date.now(), collection }, ...cache.current].slice(
            0,
            24,
          );
          setTiles(collection);
          setError(null);
        })
        .catch((cause: unknown) => {
          if (cause instanceof DOMException && cause.name === "AbortError") return;
          setError(cause instanceof Error ? cause.message : "could not load coverage");
        })
        .finally(() => {
          if (pending.current === key) pending.current = null;
        });
    },
    [held, operator],
  );

  const loadTiles = useCallback(
    (bounds: Bounds) => {
      lastBounds.current = bounds;

      // Already covered: show it now. Waiting out the debounce here would be
      // waiting for nothing — there is no request at the end of it.
      const hit = held(bounds);
      if (hit) {
        if (debounce.current) window.clearTimeout(debounce.current);
        setTiles(hit);
        setError(null);
        return;
      }

      if (debounce.current) window.clearTimeout(debounce.current);
      debounce.current = window.setTimeout(() => fetchNow(bounds), 250);
    },
    [fetchNow, held],
  );

  useEffect(() => {
    // A different network is a different answer for every box already held.
    cache.current = [];
    if (lastBounds.current) fetchNow(lastBounds.current);
    // Only `operator` should retrigger this — `fetchNow` changes identity
    // for the same reason and would otherwise fire it twice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operator]);

  return { tiles, error, loadTiles };
}
