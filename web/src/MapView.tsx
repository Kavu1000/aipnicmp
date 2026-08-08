import { useEffect, useRef } from "react";
import maplibregl, { type MapGeoJSONFeature, type StyleSpecification } from "maplibre-gl";
import { MAX_BBOX_DEGREES, type Bounds, type TileCollection, type TileProperties } from "./api";
import { COLOUR_HEX } from "./coverage";

const SOURCE_ID = "coverage";
const FILL_LAYER = "coverage-fill";

// Laos, framed to fit the whole country on first load.
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

/** Colour lookup as a MapLibre match expression, built from the shared table. */
const COLOUR_EXPRESSION = [
  "match",
  ["get", "colour"],
  ...Object.entries(COLOUR_HEX).flatMap(([name, hex]) => [name, hex]),
  COLOUR_HEX.grey,
] as unknown as maplibregl.ExpressionSpecification;

const EMPTY: TileCollection = { type: "FeatureCollection", features: [] };

type GeoJsonData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];

interface Props {
  tiles: TileCollection;
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

export function MapView({ tiles, onBoundsChange, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  // The most recent data, kept so it can be re-applied whenever a style swap
  // recreates the source. Without this, coverage loaded before the basemap
  // finished would be silently dropped.
  const latest = useRef<TileCollection>(EMPTY);
  // Callbacks live in a ref so re-renders never force the map to rebuild.
  const handlers = useRef({ onBoundsChange, onSelect });
  handlers.current = { onBoundsChange, onSelect };

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: INITIAL_CENTRE,
      zoom: INITIAL_ZOOM,
      attributionControl: { compact: true },
      // Keeps the location in the URL, so a district office can send someone
      // a link to the exact area being discussed rather than describing it.
      hash: true,
    });
    map.current = instance;

    if (import.meta.env.DEV) {
      // Handy when debugging layer styling from the browser console.
      (window as unknown as { map?: maplibregl.Map }).map = instance;
    }

    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }));

    // The container is laid out by flexbox and may still be zero-sized when the
    // map is constructed, which would leave the canvas at its default 400x300.
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
      // A failed basemap must not take the coverage data down with it.
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
          // Three tiers of visual confidence, so the map never presents a
          // prediction with the authority of a measurement.
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

      // Measured tiles get a solid edge, predicted ones a dashed edge. Dash
      // patterns cannot be data-driven, so this needs two layers.
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

    // Fires on first load and again after a style swap, so the layers survive
    // the fallback.
    instance.on("style.load", () => {
      window.clearTimeout(styleTimer);
      addLayers();
    });
    instance.on("moveend", () => handlers.current.onBoundsChange(clampBounds(instance)));

    // Ask for data straight away rather than waiting for the basemap. The
    // viewport is known the moment the map is constructed, and coverage is the
    // point of the page — it should not be held hostage by a tile CDN.
    handlers.current.onBoundsChange(clampBounds(instance));

    return () => {
      window.clearTimeout(styleTimer);
      observer.disconnect();
      instance.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    latest.current = tiles;
    const source = map.current?.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    source?.setData(tiles as unknown as GeoJsonData);
  }, [tiles]);

  return <div ref={container} className="map" />;
}
