import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  fetchArea,
  fetchAreaChildren,
  fetchSession,
  signOut,
  type SessionState,
  fetchCollectors,
  fetchNetworks,
  fetchPriorityAreas,
  fetchSummary,
  fetchTiles,
  type AreaChildren,
  type AreaDetail,
  type Bounds,
  type Collector,
  type Network,
  type Summary,
  type TileCollection,
  type TileProperties,
} from "./api";
import {
  MapView,
  type AreaOutline,
  type Basemap,
  type FitTarget,
  type FlyTarget,
} from "./MapView";
import { AreaFilter } from "./AreaFilter";
import { AreaSummary } from "./AreaSummary";
import { Login } from "./Login";
import { Users } from "./Users";
import { Legend } from "./Legend";
import { TileInspector } from "./TileInspector";
import { Networks, Overview, Priority } from "./Dashboard";
import { Collectors } from "./Collectors";
import { Sidebar, type View } from "./Sidebar";
import { formatAge, formatArea, formatShare } from "./coverage";

/**
 * How often the map asks the server what changed.
 *
 * Matched to the aggregation cadence on the server. Anything faster asks the
 * same question of the same tiles; anything slower makes a map that claims to
 * be live but is not.
 */
const REFRESH_INTERVAL_MS = 60_000;
import { outlineOf } from "./geo";
import { LANGUAGE_NAMES, TRANSLATIONS, loadLanguage, saveLanguage, type Language } from "./i18n";

const EMPTY: TileCollection = { type: "FeatureCollection", features: [] };

/**
 * Below this level the map draws hexagons; at or above it, shaded child areas.
 *
 * A national view at hexagon resolution is several hundred thousand shapes,
 * smaller than a pixel each — technically the same data, practically unreadable.
 * A province shaded by district is what a ministry actually reads.
 */
const CHOROPLETH_MAX_LEVEL = 1;

export function App() {
  const [session, setSession] = useState<SessionState | null>(null);
  const [language, setLanguage] = useState<Language>(loadLanguage);
  const [view, setView] = useState<View>("map");
  const [menuOpen, setMenuOpen] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("streets");
  const [tiles, setTiles] = useState<TileCollection>(EMPTY);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [networks, setNetworks] = useState<Network[]>([]);
  const [operator, setOperator] = useState<string | null>(null);
  const [selected, setSelected] = useState<TileProperties | null>(null);
  const [flyTo, setFlyTo] = useState<FlyTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // The administrative area the map is filtered to, and everything that hangs
  // off it: its border, its coverage, and its children shaded by coverage.
  const [areaCode, setAreaCode] = useState<string | null>(null);
  const [areaDetail, setAreaDetail] = useState<AreaDetail | null>(null);
  const [childAreas, setChildAreas] = useState<AreaChildren | null>(null);
  const [fitTo, setFitTo] = useState<FitTarget | null>(null);
  const [areaNotice, setAreaNotice] = useState<string | null>(null);
  const [collectors, setCollectors] = useState<Collector[]>([]);
  const [live, setLive] = useState(true);
  const [railOpen, setRailOpen] = useState(true);

  const t = TRANSLATIONS[language];

  const inFlight = useRef<AbortController | null>(null);
  const debounce = useRef<number | null>(null);
  const lastBounds = useRef<Bounds | null>(null);

  const loadTiles = useCallback(
    (bounds: Bounds, options?: { silent?: boolean }) => {
      const silent = options?.silent === true;
      lastBounds.current = bounds;
      // An area selection is not a viewport query. Panning inside a chosen
      // district must not silently widen the answer back out to the screen.
      if (areaCode) return;

      if (debounce.current) window.clearTimeout(debounce.current);
      debounce.current = window.setTimeout(() => {
        inFlight.current?.abort();
        const controller = new AbortController();
        inFlight.current = controller;
        if (!silent) setLoading(true);

        fetchTiles({ bounds, operator }, controller.signal)
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
      }, silent ? 0 : 250);
    },
    [operator, areaCode],
  );

  // Switching network refetches the current viewport rather than waiting for
  // the next pan, which would leave the map showing the previous operator.
  useEffect(() => {
    if (!areaCode && lastBounds.current) loadTiles(lastBounds.current);
  }, [operator, areaCode, loadTiles]);

  /**
   * Load everything that belongs to the selected area.
   *
   * Three requests, because they answer three questions and fail
   * independently: the area's own border and totals, its children for the
   * choropleth, and the hexagons inside it. A country-sized selection has too
   * many hexagons to draw, and the server says so rather than truncating —
   * that refusal is expected here, not an error.
   */
  useEffect(() => {
    if (!areaCode) {
      setAreaDetail(null);
      setChildAreas(null);
      setAreaNotice(null);
      if (lastBounds.current) loadTiles(lastBounds.current);
      return;
    }

    const controller = new AbortController();
    const { signal } = controller;
    setLoading(true);
    setAreaNotice(null);

    void (async () => {
      try {
        const detail = await fetchArea(areaCode, operator, signal);
        if (signal.aborted) return;
        setAreaDetail(detail);
        setFitTo({ bounds: detail.area.bounds, nonce: Date.now() });

        if (detail.area.level <= CHOROPLETH_MAX_LEVEL) {
          fetchAreaChildren(areaCode, operator, signal)
            .then((children) => !signal.aborted && setChildAreas(children))
            .catch(() => undefined);
        } else {
          setChildAreas(null);
        }

        try {
          const collection = await fetchTiles({ area: areaCode, operator }, signal);
          if (!signal.aborted) setTiles(collection);
        } catch (cause) {
          if (cause instanceof ApiError && cause.status === 400) {
            // Too many hexagons to draw honestly. The shaded children are the
            // answer to this question, so say that rather than showing a
            // partial map that looks complete.
            setTiles(EMPTY);
            setAreaNotice(t.areaTooLarge);
          } else {
            throw cause;
          }
        }
        if (!signal.aborted) setError(null);
      } catch (cause: unknown) {
        if (signal.aborted) return;
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(cause instanceof Error ? cause.message : "could not load this area");
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    })();

    return () => controller.abort();
    // `t` changes with the language; the notice is re-read from it on the next
    // load rather than refetching everything on a language switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [areaCode, operator]);

  /**
   * Who is signed in. Runs before anything else asks the API for data, because
   * every one of those requests would be refused until this is known.
   */
  useEffect(() => {
    const controller = new AbortController();
    fetchSession(controller.signal)
      .then(setSession)
      // A session endpoint that cannot be reached is a server that cannot be
      // reached. Assume closed rather than open.
      .catch(() =>
        setSession({
          auth_enabled: true,
          google_client_id: "",
          authenticated: false,
          approved: false,
          user: null,
        }),
      );
    return () => controller.abort();
  }, []);

  // Sign-in can be switched off for local development; then everything is
  // permitted and there is no account to show.
  const approved = session !== null && (!session.auth_enabled || session.approved);

  const handleSignOut = useCallback(async () => {
    try {
      await signOut();
    } finally {
      // Tell Google to forget the account too, so the next visitor to this
      // browser gets the chooser rather than a one-click way back into
      // somebody else's session.
      window.google?.accounts?.id?.disableAutoSelect?.();
      // Whatever the server said, stop showing data this browser may no longer
      // be entitled to.
      setSession((current) =>
        current ? { ...current, authenticated: false, approved: false, user: null } : current,
      );
      setTiles(EMPTY);
      setSummary(null);
      setAreaCode(null);
      setView("map");
    }
  }, []);

  const areaOutline = useMemo<AreaOutline | null>(() => {
    const area = areaDetail?.area;
    if (!area) return null;
    const geometry = outlineOf(area);
    return geometry ? { geometry, approximate: !area.has_boundary } : null;
  }, [areaDetail]);

  /**
   * Pull everything that changes on its own: the headline figures, the fleet,
   * and the hexagons currently on screen.
   *
   * The network catalogue is not refreshed here — it changes when an operator
   * is added, not when a measurement lands, and reloading it would reset the
   * filter under the reader's cursor.
   */
  const refresh = useCallback(
    (signal?: AbortSignal) => {
      fetchSummary(signal).then(setSummary).catch(() => undefined);
      fetchCollectors(signal)
        .then((body) => setCollectors(body.collectors))
        .catch(() => undefined);
      if (!areaCode && lastBounds.current) loadTiles(lastBounds.current, { silent: true });
    },
    [areaCode, loadTiles],
  );

  useEffect(() => {
    if (!approved) return;
    const controller = new AbortController();
    fetchSummary(controller.signal).then(setSummary).catch(() => undefined);
    fetchNetworks(controller.signal).then(setNetworks).catch(() => undefined);
    fetchCollectors(controller.signal)
      .then((body) => setCollectors(body.collectors))
      .catch(() => undefined);
    return () => controller.abort();
  }, [approved]);

  /**
   * Keep the map current while it is being watched.
   *
   * Matched to the server's one-minute aggregation: polling faster would ask
   * the same question of the same tiles and get the same answer.
   *
   * Paused when the tab is hidden, and refreshed once on return. A dashboard
   * left open on a wall display should not spend the night requesting a map
   * nobody is reading, and one left open for a week should not show Monday's
   * coverage the moment someone looks back at it.
   */
  useEffect(() => {
    // Polling a closed API would be a steady stream of 401s for as long as the
    // page is left open on the sign-in screen.
    if (!live || !approved) return;

    const tick = () => {
      if (document.visibilityState === "visible") refresh();
    };
    const timer = window.setInterval(tick, REFRESH_INTERVAL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [live, approved, refresh]);

  const changeLanguage = useCallback((next: Language) => {
    setLanguage(next);
    saveLanguage(next);
    document.documentElement.lang = next;
  }, []);

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

  const reporting = useMemo(
    () => collectors.filter((row) => row.is_reporting).length,
    [collectors],
  );

  // The rail exists only when it has something to say.
  const detail = areaDetail !== null || selected !== null;

  const freshness = useMemo(
    () => formatAge(summary?.latest_measurement_at, t.never),
    [summary, t.never],
  );

  const titles: Record<View, string> = {
    map: t.title,
    overview: t.overviewTitle,
    priority: t.priorityTitle,
    networks: t.networksTitle,
    collectors: t.collectorsTitle,
    users: t.usersTitle,
  };

  // Nothing at all until the session is known. Rendering the map first and
  // replacing it with a sign-in screen a moment later would flash coverage
  // data at someone who may not be entitled to it.
  if (session === null) {
    return <div className="boot">{t.loading}</div>;
  }

  if (!approved) {
    return (
      <Login
        session={session}
        t={t}
        language={language}
        languageNames={LANGUAGE_NAMES}
        onLanguageChange={changeLanguage}
        onSignedIn={(next) => setSession({ ...session, ...next })}
        onSignOut={handleSignOut}
      />
    );
  }

  return (
    <div className="shell">
      <Sidebar
        view={view}
        strings={t}
        open={menuOpen}
        onSelect={setView}
        onClose={() => setMenuOpen(false)}
        user={session.user}
        onSignOut={handleSignOut}
      />

      <div className="content">
        <header className="topbar">
          <button className="menu-button" onClick={() => setMenuOpen(true)} aria-label={t.menu}>
            ☰
          </button>

          <div className="topbar-title">
            <h1>{titles[view]}</h1>
            {view === "map" && <p>{t.tagline}</p>}
            {view === "overview" && <p>{t.overviewSubtitle}</p>}
          </div>

          <div className="topbar-actions">
            {view === "map" && (
              <div className="segmented" role="group">
                <button
                  className={basemap === "streets" ? "on" : ""}
                  onClick={() => setBasemap("streets")}
                >
                  {t.basemapStreets}
                </button>
                <button
                  className={basemap === "satellite" ? "on" : ""}
                  onClick={() => setBasemap("satellite")}
                >
                  {t.basemapSatellite}
                </button>
              </div>
            )}

            {view === "map" && (
              <AreaFilter
                strings={t}
                language={language}
                selected={areaDetail?.area ?? null}
                onChange={(area) => setAreaCode(area?.code ?? null)}
              />
            )}

            {view === "map" && networks.length > 0 && (
              <select
                className="select"
                value={operator ?? ""}
                onChange={(event) => setOperator(event.target.value || null)}
                aria-label={t.operator}
              >
                <option value="">{t.allOperators}</option>
                {/* Networks nobody has measured are listed and disabled rather
                    than omitted. Leaving them out implies they have no
                    coverage; saying "not measured yet" says the true thing,
                    which is that no collector carries that SIM. */}
                {networks.map((network) => (
                  <option
                    key={network.operator}
                    value={network.operator}
                    disabled={!network.measured}
                  >
                    {network.measured
                      ? network.operator
                      : `${network.operator} — ${t.networkUnmeasured}`}
                  </option>
                ))}
              </select>
            )}

            <select
              className="select"
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
          </div>
        </header>

        {summary && (
          <dl className="metrics">
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
            {/* Whether the page is still listening, and how many phones are
                sending. A dashboard that has quietly stopped updating looks
                exactly like one where nothing is happening. */}
            <div>
              <dt>{live ? t.live : t.livePaused}</dt>
              <dd className="small">
                <button
                  className={live ? "live-toggle live-on" : "live-toggle"}
                  onClick={() => {
                    if (!live) refresh();
                    setLive(!live);
                  }}
                  title={`${live ? t.livePause : t.liveResume} — ${t.reportingExplain}`}
                >
                  <span className="live-dot" aria-hidden="true" />
                  {reporting} {t.collectingNow}
                </button>
              </dd>
            </div>
          </dl>
        )}

        <main>
          {/* The map stays mounted behind the other views so switching back
              never rebuilds it or loses the user's position. */}
          <div className={view === "map" ? "pane map-shell" : "pane map-shell hidden"}>
            <div className="map-area">
            <MapView
              tiles={tiles}
              summary={summary}
              basemap={basemap}
              flyTo={flyTo}
              childAreas={childAreas}
              areaOutline={areaOutline}
              fitTo={fitTo}
              collectors={collectors}
              onBoundsChange={loadTiles}
              onSelect={setSelected}
              onAreaSelect={setAreaCode}
            />
            <Legend t={t} />

            {loading && <div className="toast">{t.loading}</div>}
            {error && <div className="toast error">{error}</div>}
            {/* The area's own summary is still on screen when this shows, so
                this explains the empty hexagon layer rather than the empty
                answer — they are different things. */}
            {!loading && !error && areaNotice && <div className="toast">{areaNotice}</div>}
            {!loading && !error && !areaNotice && tiles.features.length === 0 && (
              <div className="toast">
                {areaCode ? t.areaNotMeasured : t.noTilesInView}
                {!areaCode && summary?.bounds && (
                  <button className="link" onClick={jumpToData}>
                    {t.jumpToData}
                  </button>
                )}
              </div>
            )}
            </div>

            {/*
              One rail, not two floating cards.
              A selected area and a clicked hexagon used to open separate
              panels over the map, both covering the thing they described, and
              each able to hide the other. Docking them shrinks the map instead
              of covering it, so nothing the reader is looking at disappears
              behind the answer to a question about it.
            */}
            {detail && (
              <aside className={railOpen ? "detail-rail" : "detail-rail collapsed"}>
                <button
                  className="rail-handle"
                  onClick={() => setRailOpen(!railOpen)}
                  aria-expanded={railOpen}
                  title={railOpen ? t.railCollapse : t.railExpand}
                >
                  {railOpen ? "›" : "‹"}
                </button>
                <div className="rail-body">
                  {selected && (
                    <TileInspector tile={selected} t={t} onClose={() => setSelected(null)} />
                  )}
                  {areaDetail && (
                    <AreaSummary
                      detail={areaDetail}
                      language={language}
                      t={t}
                      onClear={() => setAreaCode(null)}
                    />
                  )}
                </div>
              </aside>
            )}
          </div>

          {view !== "map" && (
            <div className="pane scrollable">
              <div className="page">
                {view === "overview" && <Overview summary={summary} t={t} />}
                {view === "priority" && <Priority t={t} onShowOnMap={showOnMap} />}
                {view === "networks" && <Networks t={t} />}
                {view === "collectors" && <Collectors t={t} />}
                {view === "users" && (
                  <Users t={t} currentUserId={session.user?.id ?? null} />
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
