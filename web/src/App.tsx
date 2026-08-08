import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchStats,
  fetchTiles,
  type Bounds,
  type Stats,
  type TileCollection,
  type TileProperties,
} from "./api";
import { MapView } from "./MapView";
import { Legend } from "./Legend";
import { TileInspector } from "./TileInspector";

const EMPTY: TileCollection = { type: "FeatureCollection", features: [] };

export function App() {
  const [tiles, setTiles] = useState<TileCollection>(EMPTY);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selected, setSelected] = useState<TileProperties | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Panning fires bounds changes faster than the API can answer them; keeping
  // the in-flight request lets a new one cancel the old rather than queue.
  const inFlight = useRef<AbortController | null>(null);
  const debounce = useRef<number | null>(null);

  const loadTiles = useCallback((bounds: Bounds) => {
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      setLoading(true);

      fetchTiles(bounds, controller.signal)
        .then((collection) => {
          setTiles(collection);
          setError(null);
        })
        .catch((cause: unknown) => {
          if (cause instanceof DOMException && cause.name === "AbortError") return;
          setError(cause instanceof Error ? cause.message : "could not load coverage");
        })
        .finally(() => {
          if (inFlight.current === controller) setLoading(false);
        });
    }, 250);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchStats(controller.signal)
      .then(setStats)
      .catch(() => {
        /* The map is still useful without the headline numbers. */
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="app">
      <header>
        <div className="title">
          <h1>Where the internet actually works</h1>
          <p>
            Measured on ordinary phones across Lao PDR — including the places with no
            signal at all.
          </p>
        </div>

        {stats && (
          <dl className="stats">
            <div>
              <dt>Measurements</dt>
              <dd>{stats.measurements.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Areas mapped</dt>
              <dd>{stats.tiles.toLocaleString()}</dd>
            </div>
            <div className="highlight">
              <dt>Readings with no service</dt>
              <dd>{stats.no_service_measurements.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Contributing devices</dt>
              <dd>{stats.devices.toLocaleString()}</dd>
            </div>
          </dl>
        )}
      </header>

      <main>
        <MapView tiles={tiles} onBoundsChange={loadTiles} onSelect={setSelected} />
        <Legend />
        <TileInspector tile={selected} onClose={() => setSelected(null)} />

        {loading && <div className="toast">Loading coverage…</div>}
        {error && <div className="toast error">{error}</div>}
        {!loading && !error && tiles.features.length === 0 && (
          <div className="toast">
            No measurements in view yet. Zoom to a surveyed area, or run a collection
            journey to populate the map.
          </div>
        )}
      </main>
    </div>
  );
}
