import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchOperatorNames,
  fetchSummary,
  fetchTiles,
  type Bounds,
  type Summary,
  type TileCollection,
  type TileProperties,
} from "./api";
import { MapView, type FlyTarget } from "./MapView";
import { Legend } from "./Legend";
import { TileInspector } from "./TileInspector";
import { Dashboard } from "./Dashboard";
import { formatAge, formatArea, formatShare } from "./coverage";
import { LANGUAGE_NAMES, TRANSLATIONS, loadLanguage, saveLanguage, type Language } from "./i18n";

const EMPTY: TileCollection = { type: "FeatureCollection", features: [] };

type View = "map" | "dashboard";

export function App() {
  const [language, setLanguage] = useState<Language>(loadLanguage);
  const [view, setView] = useState<View>("map");
  const [tiles, setTiles] = useState<TileCollection>(EMPTY);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [operatorNames, setOperatorNames] = useState<string[]>([]);
  const [operator, setOperator] = useState<string | null>(null);
  const [selected, setSelected] = useState<TileProperties | null>(null);
  const [flyTo, setFlyTo] = useState<FlyTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const t = TRANSLATIONS[language];

  const inFlight = useRef<AbortController | null>(null);
  const debounce = useRef<number | null>(null);
  const lastBounds = useRef<Bounds | null>(null);

  const loadTiles = useCallback(
    (bounds: Bounds) => {
      lastBounds.current = bounds;
      if (debounce.current) window.clearTimeout(debounce.current);
      debounce.current = window.setTimeout(() => {
        inFlight.current?.abort();
        const controller = new AbortController();
        inFlight.current = controller;
        setLoading(true);

        fetchTiles(bounds, operator, controller.signal)
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
    },
    [operator],
  );

  // Switching network refetches the current viewport rather than waiting for
  // the next pan, which would leave the map showing the previous operator.
  useEffect(() => {
    if (lastBounds.current) loadTiles(lastBounds.current);
  }, [operator, loadTiles]);

  useEffect(() => {
    const controller = new AbortController();
    fetchSummary(controller.signal).then(setSummary).catch(() => undefined);
    fetchOperatorNames(controller.signal).then(setOperatorNames).catch(() => undefined);
    return () => controller.abort();
  }, []);

  const changeLanguage = (next: Language) => {
    setLanguage(next);
    saveLanguage(next);
    document.documentElement.lang = next;
  };

  const showOnMap = useCallback((lat: number, lon: number) => {
    setView("map");
    setFlyTo({ lat, lon, zoom: 13, nonce: Date.now() });
  }, []);

  /**
   * The headline finding should be reachable, not just readable. Clicking the
   * no-service count takes you to the worst measured area rather than leaving
   * the most important number on the page inert.
   */
  const goToWorstArea = useCallback(async () => {
    try {
      const { fetchPriorityAreas } = await import("./api");
      const body = await fetchPriorityAreas(1);
      const first = body.areas[0];
      if (first) showOnMap(first.lat, first.lon);
    } catch {
      /* The map is still usable without the shortcut. */
    }
  }, [showOnMap]);

  const jumpToData = useCallback(() => {
    const bounds = summary?.bounds;
    if (!bounds) return;
    showOnMap((bounds.min_lat + bounds.max_lat) / 2, (bounds.min_lon + bounds.max_lon) / 2);
  }, [summary, showOnMap]);

  const freshness = useMemo(
    () => formatAge(summary?.latest_measurement_at, t.never),
    [summary, t.never],
  );

  return (
    <div className="app">
      <header>
        <div className="title">
          <h1>{t.title}</h1>
          <p>{t.tagline}</p>
        </div>

        {summary && (
          <dl className="stats">
            <div>
              <dt>{t.statMeasurements}</dt>
              <dd>{summary.measurements.toLocaleString()}</dd>
            </div>
            <div>
              <dt>{t.statAreaMapped}</dt>
              {/* Area, not a tile count. "124 areas" invites the reader to
                  assume national coverage; km² and the national share say
                  plainly that this is a pilot. */}
              <dd>{formatArea(summary.measured_area_km2)}</dd>
              <span className="sub">
                {formatShare(summary.measured_share_pct)} {t.ofCountry}
              </span>
            </div>
            <div className="highlight">
              <dt>{t.statNoService}</dt>
              <dd>
                <button className="stat-link" onClick={goToWorstArea}>
                  {summary.no_service_measurements.toLocaleString()}
                </button>
              </dd>
            </div>
            <div>
              <dt>{t.statDevices}</dt>
              <dd>{summary.devices.toLocaleString()}</dd>
            </div>
            <div>
              <dt>{t.statUpdated}</dt>
              <dd className="small">{freshness}</dd>
            </div>
          </dl>
        )}

        <nav className="toolbar">
          <div className="tabs">
            <button className={view === "map" ? "on" : ""} onClick={() => setView("map")}>
              {t.navMap}
            </button>
            <button
              className={view === "dashboard" ? "on" : ""}
              onClick={() => setView("dashboard")}
            >
              {t.navDashboard}
            </button>
          </div>

          {view === "map" && operatorNames.length > 0 && (
            <select
              className="operator-select"
              value={operator ?? ""}
              onChange={(event) => setOperator(event.target.value || null)}
              aria-label={t.operator}
            >
              <option value="">{t.allOperators}</option>
              {operatorNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          )}

          <select
            className="lang-select"
            value={language}
            onChange={(event) => changeLanguage(event.target.value as Language)}
            aria-label="Language"
          >
            {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </nav>
      </header>

      <main>
        {/* The map stays mounted while the dashboard is shown, so switching
            back does not rebuild it or lose the user's position. */}
        <div className={view === "map" ? "pane" : "pane hidden"}>
          <MapView
            tiles={tiles}
            summary={summary}
            flyTo={flyTo}
            onBoundsChange={loadTiles}
            onSelect={setSelected}
          />
          <Legend t={t} />
          <TileInspector tile={selected} t={t} onClose={() => setSelected(null)} />

          {loading && <div className="toast">{t.loading}</div>}
          {error && <div className="toast error">{error}</div>}
          {!loading && !error && tiles.features.length === 0 && (
            <div className="toast">
              {t.noTilesInView}
              {summary?.bounds && (
                <button className="link" onClick={jumpToData}>
                  {t.jumpToData}
                </button>
              )}
            </div>
          )}
        </div>

        {view === "dashboard" && (
          <div className="pane scrollable">
            <Dashboard summary={summary} t={t} onShowOnMap={showOnMap} />
          </div>
        )}
      </main>
    </div>
  );
}
