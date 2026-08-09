import { useEffect, useRef } from "react";
import maplibregl, { type MapGeoJSONFeature, type StyleSpecification } from "maplibre-gl";
import { MAX_BBOX_DEGREES, type Bounds, type Summary, type TileCollection, type TileProperties } from "./api";
import { COLOUR_HEX } from "./coverage";

const SOURCE_ID = "coverage";
const FILL_LAYER = "coverage-fill";

// Laos, framed to fit the whole country. Only used until the real data bounds
// arrive — see fitToData below.
const INITIAL_CENTRE: [number, number] = [103.2, 19.0];
const INITIAL_ZOOM = 5.6;

const STYLE_URL =
  import.meta.env.VITE_MAP_STYLE ?? "https://tiles.openfreemap.org/styles/positron";

/** How long to wait for the basemap before giving up and drawing without it. */
const STYLE_TIMEOUT_MS = 8000;

/**
 * Used when the basemap cannot be reached.
 *
 * A coverage map for rural Laos that fails closed when a CDN is unreachable
 * would be a poor joke, so the hexagons stay readable with no basemap at all.
 */
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#eef1f5" } }],
};

const COLOUR_EXPRESSION = [
  "match",
  ["get", "colour"],
  ...Object.entries(COLOUR_HEX).flatMap(([name, hex]) => [name, hex]),
  COLOUR_HEX.grey,
] as unknown as maplibregl.ExpressionSpecification;

const EMPTY: TileCollection = { type: "FeatureCollection", features: [] };

/**
 * The position a shared link asked for, or null for a fresh visit.
 *
 * The hash is read and written by hand rather than with MapLibre's `hash: true`
 * option. That option writes the URL on *every* move including the programmatic
 * fit-to-data, which had two consequences: the default position was pinned into
 * the URL the instant the page loaded, so anyone who shared the link sent a
 * recipient to an empty view; and the fit could never tell a real shared link
 * from the map's own handiwork.
 *
 * Parsed at module scope — once per page load, before React renders anything.
 */
const INITIAL_VIEW = parseHash(window.location.hash);

function parseHash(hash: string): { zoom: number; lat: number; lon: number } | null {
  const parts = hash.replace(/^#/, "").split("/");
  if (parts.length < 3) return null;
  const [zoom, lat, lon] = parts.map(Number);
  if (![zoom, lat, lon].every(Number.isFinite)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { zoom, lat, lon };
}

function writeHash(map: maplibregl.Map): void {
  const centre = map.getCenter();
  const next = `#${map.getZoom().toFixed(2)}/${centre.lat.toFixed(5)}/${centre.lng.toFixed(5)}`;
  // replaceState, not a hash assignment: the map should not fill the back
  // button with an entry for every pan.
  window.history.replaceState(null, "", next);
}

type GeoJsonData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];

export interface FlyTarget {
  lat: number;
  lon: number;
  zoom?: number;
  /** Changes on every request so repeat clicks on the same place still fly. */
  nonce: number;
}

interface Props {
  tiles: TileCollection;
  summary: Summary | null;
  flyTo: FlyTarget | null;
  onBoundsChange: (bounds: Bounds) => void;
  onSelect: (properties: TileProperties | null) => void;
}

function clampBounds(map: maplibregl.Map): Bounds {
  const bounds = map.getBounds();
  const minLat = bounds.getSouth();
  const maxLat = bounds.getNorth();
  const minLon = bounds.getWest();
  const maxLon = bounds.getEast();

  // The API refuses a viewport wider than MAX_BBOX_DEGREES. Rather than let the
  // request fail when the user zooms out to the whole country, ask for the
  // centre of what they are looking at.
  const centreLat = (minLat + maxLat) / 2;
  const centreLon = (minLon + maxLon) / 2;
  const half = (MAX_BBOX_DEGREES - 0.1) / 2;

  return {
    minLat: Math.max(minLat, centreLat - half),
    maxLat: Math.min(maxLat, centreLat + half),
    minLon: Math.max(minLon, centreLon - half),
    maxLon: Math.min(maxLon, centreLon + half),
  };
}

export function MapView({ tiles, summary, flyTo, onBoundsChange, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const latest = useRef<TileCollection>(EMPTY);
  const handlers = useRef({ onBoundsChange, onSelect });
  handlers.current = { onBoundsChange, onSelect };

  // The auto-fit must happen once, and must not fight the user afterwards.
  const hasFitted = useRef(false);

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: INITIAL_VIEW ? [INITIAL_VIEW.lon, INITIAL_VIEW.lat] : INITIAL_CENTRE,
      zoom: INITIAL_VIEW ? INITIAL_VIEW.zoom : INITIAL_ZOOM,
      attributionControl: { compact: true },
    });
    map.current = instance;

    if (import.meta.env.DEV) {
      (window as unknown as { map?: maplibregl.Map }).map = instance;
    }

    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }));

    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(container.current);

    let usedFallback = false;
    const useFallback = () => {
      if (usedFallback || instance.isStyleLoaded()) return;
      usedFallback = true;
      instance.setStyle(FALLBACK_STYLE);
    };
    const styleTimer = window.setTimeout(useFallback, STYLE_TIMEOUT_MS);
    instance.on("error", (event) => {
      if (String(event?.error?.message ?? "").toLowerCase().includes("style")) useFallback();
    });

    const addLayers = () => {
      if (instance.getSource(SOURCE_ID)) return;

      instance.addSource(SOURCE_ID, { type: "geojson", data: latest.current as GeoJsonData });

      instance.addLayer({
        id: FILL_LAYER,
        type: "fill",
        source: SOURCE_ID,
        paint: {
          "fill-color": COLOUR_EXPRESSION,
          "fill-opacity": [
            "case",
            ["get", "predicted"],
            0.35,
            ["get", "low_confidence"],
            0.58,
            0.78,
          ],
        },
      });

      instance.addLayer({
        id: "coverage-outline",
        type: "line",
        source: SOURCE_ID,
        filter: ["!", ["get", "predicted"]],
        paint: { "line-color": "#ffffff", "line-width": 0.6, "line-opacity": 0.65 },
      });
      instance.addLayer({
        id: "coverage-outline-predicted",
        type: "line",
        source: SOURCE_ID,
        filter: ["get", "predicted"],
        paint: {
          "line-color": "#4a5568",
          "line-width": 0.8,
          "line-opacity": 0.7,
          "line-dasharray": [2, 2],
        },
      });

      instance.on("click", FILL_LAYER, (event) => {
        const feature = event.features?.[0] as MapGeoJSONFeature | undefined;
        handlers.current.onSelect(
          feature ? (feature.properties as unknown as TileProperties) : null,
        );
      });
      instance.on("click", (event) => {
        const hits = instance.queryRenderedFeatures(event.point, { layers: [FILL_LAYER] });
        if (hits.length === 0) handlers.current.onSelect(null);
      });
      instance.on("mouseenter", FILL_LAYER, () => {
        instance.getCanvas().style.cursor = "pointer";
      });
      instance.on("mouseleave", FILL_LAYER, () => {
        instance.getCanvas().style.cursor = "";
      });
    };

    instance.on("style.load", () => {
      window.clearTimeout(styleTimer);
      addLayers();
    });
    instance.on("moveend", () => {
      handlers.current.onBoundsChange(clampBounds(instance));
      // Only once the map is showing something worth linking to. Writing the
      // default position would hand out links to an empty country.
      if (hasFitted.current || INITIAL_VIEW) writeHash(instance);
    });

    handlers.current.onBoundsChange(clampBounds(instance));

    return () => {
      window.clearTimeout(styleTimer);
      observer.disconnect();
      instance.remove();
      map.current = null;
    };
  }, []);

  /**
   * Frame the measured data on first load.
   *
   * Without this the map opens on the whole country, where a pilot's worth of
   * hexagons is smaller than a pixel — so a working system looks like an empty
   * one. Skipped when the URL already carries a position, because that means
   * the user was sent a link to somewhere specific.
   */
  useEffect(() => {
    const instance = map.current;
    if (!instance || hasFitted.current || !summary?.bounds) return;
    if (INITIAL_VIEW) {
      // Someone followed a link to a specific place; do not move them.
      hasFitted.current = true;
      return;
    }

    const { min_lat, min_lon, max_lat, max_lon } = summary.bounds;
    hasFitted.current = true;
    instance.fitBounds(
      [
        [min_lon, min_lat],
        [max_lon, max_lat],
      ],
      // Instant, not animated. The container is still settling at this point
      // and the ResizeObserver's resize() cancels any easing in flight, which
      // left the map sitting at the default position with the fit silently
      // discarded. There is also nothing to animate away from: the user has
      // not seen the map yet.
      { padding: 80, maxZoom: 12, duration: 0 },
    );
  }, [summary]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !flyTo) return;
    instance.flyTo({ center: [flyTo.lon, flyTo.lat], zoom: flyTo.zoom ?? 12, duration: 1200 });
  }, [flyTo]);

  useEffect(() => {
    latest.current = tiles;
    const source = map.current?.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    source?.setData(tiles as unknown as GeoJsonData);
  }, [tiles]);

  return <div ref={container} className="map" />;
}
