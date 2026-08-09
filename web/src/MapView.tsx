import { useEffect, useRef } from "react";
import maplibregl, { type MapGeoJSONFeature, type StyleSpecification } from "maplibre-gl";
import {
  MAX_BBOX_DEGREES,
  type AreaChildren,
  type Bounds,
  type GeoBounds,
  type Geometry,
  type Summary,
  type TileCollection,
  type TileProperties,
} from "./api";
import { COLOUR_HEX } from "./coverage";
import { maskGeometry } from "./geo";

const SOURCE_ID = "coverage";
const FILL_LAYER = "coverage-fill";

/** Child areas shaded by coverage — the view at country and province zoom. */
const AREAS_SOURCE = "areas";
const AREAS_FILL = "areas-fill";
const AREAS_POINT = "areas-point";

/** The selected area's own border, and the dimming of everything outside it. */
const OUTLINE_SOURCE = "area-outline";
const MASK_SOURCE = "area-mask";
const BORDER_LAYER = "area-border";

// Laos, framed to fit the whole country. Only used until the real data bounds
// arrive — see fitToData below.
const INITIAL_CENTRE: [number, number] = [103.2, 19.0];
const INITIAL_ZOOM = 5.6;

export type Basemap = "streets" | "satellite";

const STREETS_STYLE =
  import.meta.env.VITE_MAP_STYLE ?? "https://tiles.openfreemap.org/styles/positron";

/**
 * Sentinel-2 cloudless, served by EOX under CC BY 4.0.
 *
 * Chosen over the usual commercial imagery for two reasons. It needs no API
 * key, so there is one less credential for a pilot to manage or leak. And it is
 * the same source proposal 2.5(2) names for detecting settlements and
 * electrification — so what an operator sees under the hexagons is the imagery
 * the coverage model will later reason about, not a different picture.
 *
 * Cloudless composites stop at zoom 14; beyond that MapLibre overzooms and the
 * imagery softens. That is past the point where a ~0.7 km hexagon fills the
 * screen, so nothing decision-relevant is lost.
 */
const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    "s2cloudless": {
      type: "raster",
      tiles: [
        "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg",
      ],
      tileSize: 256,
      maxzoom: 14,
      attribution:
        '<a href="https://s2maps.eu">Sentinel-2 cloudless</a> by EOX IT Services GmbH (CC BY 4.0)',
    },
  },
  layers: [{ id: "s2cloudless", type: "raster", source: "s2cloudless" }],
};

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
const EMPTY_GEOJSON = { type: "FeatureCollection", features: [] } as const;

/**
 * The scrim over everything outside the selected area.
 *
 * Light rather than dark, and not quite opaque: the surrounding country should
 * stay legible as context. Hiding it would answer "where is this district"
 * with a shape floating in nothing.
 */
const MASK_COLOUR = "#f5f7fa";
const MASK_OPACITY = 0.66;

function basemapStyle(basemap: Basemap): string | StyleSpecification {
  return basemap === "satellite" ? SATELLITE_STYLE : STREETS_STYLE;
}

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

/** A rectangle to frame, re-applied whenever `nonce` changes. */
export interface FitTarget {
  bounds: GeoBounds;
  nonce: number;
}

export interface AreaOutline {
  geometry: Geometry;
  /**
   * True when this is a radius the platform chose around a village point, not
   * a published boundary. Drawn dashed, and never solid.
   */
  approximate: boolean;
}

interface Props {
  tiles: TileCollection;
  summary: Summary | null;
  basemap: Basemap;
  flyTo: FlyTarget | null;
  /** Child areas shaded by coverage, or null when hexagons carry the view. */
  childAreas: AreaChildren | null;
  /** The selected area's border, outlined and used to dim everything else. */
  areaOutline: AreaOutline | null;
  fitTo: FitTarget | null;
  onBoundsChange: (bounds: Bounds) => void;
  onSelect: (properties: TileProperties | null) => void;
  /** A click on a shaded area — the drill-down from province to district. */
  onAreaSelect: (code: string) => void;
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

export function MapView({
  tiles,
  summary,
  basemap,
  flyTo,
  childAreas,
  areaOutline,
  fitTo,
  onBoundsChange,
  onSelect,
  onAreaSelect,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const latest = useRef<TileCollection>(EMPTY);
  // Held so the layers can be rebuilt from scratch after a basemap switch,
  // which discards every source the style did not define.
  const latestAreas = useRef<GeoJsonData>(EMPTY_GEOJSON as unknown as GeoJsonData);
  const latestOutline = useRef<GeoJsonData>(EMPTY_GEOJSON as unknown as GeoJsonData);
  const latestMask = useRef<GeoJsonData>(EMPTY_GEOJSON as unknown as GeoJsonData);
  const handlers = useRef({ onBoundsChange, onSelect, onAreaSelect });
  handlers.current = { onBoundsChange, onSelect, onAreaSelect };

  // The auto-fit must happen once, and must not fight the user afterwards.
  const hasFitted = useRef(false);

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: basemapStyle(basemap),
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

      // Order matters and is the whole visual argument: shaded areas underneath
      // as context, hexagons over them as evidence, and the mask over both so
      // that everything outside the chosen area recedes.
      instance.addSource(AREAS_SOURCE, { type: "geojson", data: latestAreas.current });

      instance.addLayer({
        id: AREAS_FILL,
        type: "fill",
        source: AREAS_SOURCE,
        filter: ["!=", ["geometry-type"], "Point"],
        paint: { "fill-color": COLOUR_EXPRESSION, "fill-opacity": 0.55 },
      });
      instance.addLayer({
        id: "areas-line",
        type: "line",
        source: AREAS_SOURCE,
        filter: ["!=", ["geometry-type"], "Point"],
        paint: { "line-color": "#ffffff", "line-width": 1.2, "line-opacity": 0.9 },
      });
      // A village published as a point, not a polygon. Drawn as a marker so it
      // cannot read as a surveyed extent.
      instance.addLayer({
        id: AREAS_POINT,
        type: "circle",
        source: AREAS_SOURCE,
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 6,
          "circle-color": COLOUR_EXPRESSION,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#ffffff",
        },
      });

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

      instance.addSource(MASK_SOURCE, { type: "geojson", data: latestMask.current });
      instance.addLayer({
        id: "area-mask",
        type: "fill",
        source: MASK_SOURCE,
        paint: { "fill-color": MASK_COLOUR, "fill-opacity": MASK_OPACITY },
      });

      instance.addSource(OUTLINE_SOURCE, { type: "geojson", data: latestOutline.current });
      // Two layers rather than one, because `line-dasharray` cannot be driven
      // from a feature property. The distinction they draw is the difference
      // between a surveyed boundary and a radius the platform chose, and it has
      // to be visible without reading a caption.
      instance.addLayer({
        id: BORDER_LAYER,
        type: "line",
        source: OUTLINE_SOURCE,
        filter: ["!", ["get", "approximate"]],
        paint: { "line-color": "#16202c", "line-width": 2.2 },
      });
      instance.addLayer({
        id: "area-border-approximate",
        type: "line",
        source: OUTLINE_SOURCE,
        filter: ["get", "approximate"],
        paint: { "line-color": "#16202c", "line-width": 2, "line-dasharray": [2, 2] },
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

      for (const layer of [AREAS_FILL, AREAS_POINT]) {
        instance.on("click", layer, (event) => {
          const feature = event.features?.[0] as MapGeoJSONFeature | undefined;
          const code = feature?.properties?.code;
          // Clicking a province is how you get to its districts — the same
          // journey the selects offer, for people who navigate by looking.
          if (typeof code === "string") handlers.current.onAreaSelect(code);
        });
      }

      for (const layer of [FILL_LAYER, AREAS_FILL, AREAS_POINT]) {
        instance.on("mouseenter", layer, () => {
          instance.getCanvas().style.cursor = "pointer";
        });
        instance.on("mouseleave", layer, () => {
          instance.getCanvas().style.cursor = "";
        });
      }
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

  /**
   * Swap the basemap without disturbing anything else.
   *
   * The coverage layers are rebuilt by the existing `style.load` handler, which
   * reads from `latest` — the same path the offline fallback already uses — so
   * the hexagons survive the switch and no refetch is needed.
   */
  const currentBasemap = useRef(basemap);
  useEffect(() => {
    const instance = map.current;
    if (!instance || currentBasemap.current === basemap) return;
    currentBasemap.current = basemap;
    instance.setStyle(basemapStyle(basemap));
  }, [basemap]);

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

  useEffect(() => {
    const data = (childAreas ?? EMPTY_GEOJSON) as unknown as GeoJsonData;
    latestAreas.current = data;
    const source = map.current?.getSource(AREAS_SOURCE) as maplibregl.GeoJSONSource | undefined;
    source?.setData(data);
  }, [childAreas]);

  useEffect(() => {
    // Absent geometry clears both sources: "no area selected" must leave
    // nothing outlined and nothing dimmed.
    const outline = areaOutline
      ? {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: areaOutline.geometry,
              properties: { approximate: areaOutline.approximate },
            },
          ],
        }
      : EMPTY_GEOJSON;
    const mask = areaOutline
      ? {
          type: "FeatureCollection",
          features: [
            { type: "Feature", geometry: maskGeometry(areaOutline.geometry), properties: {} },
          ],
        }
      : EMPTY_GEOJSON;

    latestOutline.current = outline as unknown as GeoJsonData;
    latestMask.current = mask as unknown as GeoJsonData;

    const instance = map.current;
    (instance?.getSource(OUTLINE_SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(
      latestOutline.current,
    );
    (instance?.getSource(MASK_SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(
      latestMask.current,
    );
  }, [areaOutline]);

  /**
   * Frame the selected area.
   *
   * Keyed by nonce rather than by the bounds themselves so that re-selecting
   * the same area, after panning away from it, brings the map back.
   */
  useEffect(() => {
    const instance = map.current;
    if (!instance || !fitTo) return;
    const { min_lat, min_lon, max_lat, max_lon } = fitTo.bounds;
    hasFitted.current = true;
    instance.fitBounds(
      [
        [min_lon, min_lat],
        [max_lon, max_lat],
      ],
      { padding: 64, maxZoom: 13, duration: 900 },
    );
  }, [fitTo]);

  return <div ref={container} className="map" />;
}
