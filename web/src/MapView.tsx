import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type MapGeoJSONFeature, type StyleSpecification } from "maplibre-gl";
import {
  MAX_BBOX_DEGREES,
  type AreaChildren,
  type Bounds,
  type Collector,
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
const LINKS_SOURCE = "collector-links";
const LINKS_LAYER = "collector-link-lines";
const LINKS_LABEL_LAYER = "collector-link-labels";
const CELLS_SOURCE = "observed-cells";
const CELLS_LAYER = "observed-cell-points";
const CELLS_HALO_LAYER = "observed-cell-halo";
const CELLS_PULSE_LAYER = "observed-cell-pulse";

/**
 * One colour per network, so masts can be told apart at a glance.
 *
 * Chosen from outside the coverage scale entirely. Green, yellow, orange and
 * red already mean five specific things about signal on this map, and the
 * collector beacon has taken red and blue, so a mast wearing any of those
 * would be read as a reading rather than as a transmitter.
 *
 * An unrecognised network falls back to the first colour rather than
 * disappearing: a mast nobody has a colour for is still a mast.
 */
export const OPERATOR_COLOURS: Record<string, string> = {
  "Lao Telecom": "#6b21a8",
  ETL: "#0f766e",
  Unitel: "#be185d",
  Tplus: "#7c2d12",
};

const OPERATOR_COLOUR_EXPRESSION = [
  "match",
  ["get", "operator"],
  ...Object.entries(OPERATOR_COLOURS).flatMap(([name, hex]) => [name, hex]),
  "#6b21a8",
] as unknown as maplibregl.ExpressionSpecification;

/**
 * The broadcast pulse, in screen pixels rather than metres.
 *
 * Deliberately not drawn to scale. This platform does not know how far any
 * mast reaches — that is what the coverage model is for — so a ring expanding
 * to a real distance would be inventing a coverage radius and putting it on a
 * map somebody spends money from. In pixels it stays the same size as the map
 * zooms, which reads as an indicator rather than a measurement.
 */
const PULSE_FRAMES = 28;
const PULSE_INTERVAL_MS = 55;
const COLLECTORS_SOURCE = "collectors";
const COLLECTORS_LAYER = "collector-points";

/**
 * The two colours the collector marker alternates between.
 *
 * Asked for as a beacon, and it behaves as one. Worth knowing what it costs:
 * red is this map's colour for "no service at all", so a red dot sitting in a
 * hexagon is one glance away from being read as a reading rather than a phone.
 * The white ring around it is what keeps the two apart — no tile is ever
 * outlined in white — and the blue half of the cycle is never a coverage
 * colour at all, so the marker spends half its time unmistakable.
 */
const BEACON = ["#e11d2f", "#1d4ed8"] as const;

/** How long each colour holds. Slow enough to read, fast enough to notice. */
const BEACON_INTERVAL_MS = 700;
const COLLECTORS_COUNT_LAYER = "collector-count";
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
 *
 * Added as a layer inside the vector style rather than as a style of its own.
 * It used to be its own style, which meant switching to satellite replaced
 * every layer the vector basemap provided — including all of its place names.
 * The result was a beautiful, unlabelled green expanse: you could see a valley
 * had no coverage but not which valley it was, which is most of what a reader
 * needs. Imagery now slots in *below* the label layers and hides only the
 * painted land beneath them.
 */
const SATELLITE_SOURCE = "s2cloudless";
const SATELLITE_LAYER = "s2cloudless";

const SATELLITE_TILES: maplibregl.RasterSourceSpecification = {
  type: "raster",
  tiles: ["https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg"],
  tileSize: 256,
  maxzoom: 14,
  attribution:
    '<a href="https://s2maps.eu">Sentinel-2 cloudless</a> by EOX IT Services GmbH (CC BY 4.0)',
};

/**
 * Elevation, for the 3D view.
 *
 * Terrain is not decoration on this map. Lao coverage gaps are largely a
 * terrain story — a valley with no line of sight to a mast reads as an
 * inexplicable red patch flat on, and as an obvious one when the ridge between
 * them is visible. Proposal 2.5 leans on the same fact when it models where a
 * tower would help.
 *
 * AWS's public terrain tiles, for the reason the satellite layer uses EOX:
 * no API key, so there is one less credential for a pilot to manage or leak.
 *
 * Loaded only when the view is switched on. A raster-dem source costs nothing
 * until something asks it for elevation, which matters on the provincial links
 * this map is meant to be usable over.
 */
const TERRAIN_SOURCE = "terrain-dem";

const TERRAIN_TILES: maplibregl.RasterDEMSourceSpecification = {
  type: "raster-dem",
  tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
  encoding: "terrarium",
  tileSize: 256,
  // The source really does go to 15, checked tile by tile over the hills
  // north-east of Vientiane: z14 and z15 return full tiles and z16 is a 404.
  // This said 13, so the last two levels of relief were being thrown away and
  // the 3D view flattened into smooth mounds exactly when a reader zoomed in
  // to see which ridge was blocking a valley.
  maxzoom: 15,
  attribution:
    '<a href="https://registry.opendata.aws/terrain-tiles/">Terrain Tiles</a> (AWS Open Data)',
};

/**
 * Vertical exaggeration.
 *
 * Laos rises about 2 km over roughly 1,000 km, so true-to-scale relief is
 * nearly invisible at the zoom where a province fits on screen. This is a
 * cartographic convention rather than a measurement, and the only figure on
 * this map that is deliberately not literal — hence a modest value, and hence
 * saying so here.
 */
const TERRAIN_EXAGGERATION = 1.4;

/**
 * Tilted enough to read a ridge line, not so far that the map becomes a wall.
 *
 * Must stay within MAX_PITCH below. MapLibre defaults its limit to 60 and
 * silently ignores a request past it — asking for 62 left the map perfectly
 * flat with terrain switched on, which looks like broken terrain rather than a
 * rejected camera move.
 */
const TERRAIN_PITCH = 65;

/** Room above TERRAIN_PITCH so the reader can tilt further by hand. */
const MAX_PITCH = 78;

/**
 * Labels legible over dark imagery.
 *
 * Positron sets dark grey text with a white halo, which is right on a pale
 * basemap and nearly invisible over Lao forest. Inverting it — white text, dark
 * halo — is the standard hybrid treatment, and the halo is what carries it over
 * the bright patches of cleared ground.
 */
const IMAGERY_LABEL_PAINT = {
  "text-color": "#ffffff",
  "text-halo-color": "rgba(0, 0, 0, 0.8)",
  "text-halo-width": 1.6,
} as const;

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

/**
 * Raise or flatten the landscape.
 *
 * Tilting is what makes terrain legible — relief seen from directly overhead
 * is just shading — so the camera pitches with it and returns to flat, facing
 * north, on the way back. Rotation is left wherever the reader put it while
 * tilted, but a bearing on a flat map is disorienting with nothing to explain
 * it, so going back to 2D resets that too.
 */
function applyTerrain(map: maplibregl.Map, on: boolean): void {
  if (!map.getSource(TERRAIN_SOURCE)) return;

  map.setTerrain(
    on ? { source: TERRAIN_SOURCE, exaggeration: TERRAIN_EXAGGERATION } : null,
  );

  // A tilted map with no sky ends at a hard edge where the ground stops.
  // Guarded because setSky is not in every MapLibre version this might build
  // against, and a missing horizon is not worth a broken map.
  if (typeof map.setSky === "function") {
    map.setSky(
      on
        ? {
            "sky-color": "#a8c6e8",
            "horizon-color": "#e8eef6",
            "fog-color": "#eef1f5",
            "horizon-fog-blend": 0.7,
            "sky-horizon-blend": 0.6,
          }
        : {},
    );
  }

  map.easeTo({
    pitch: on ? TERRAIN_PITCH : 0,
    bearing: on ? map.getBearing() : 0,
    duration: 700,
  });
}

/**
 * Show or hide the imagery, and adapt the basemap around it.
 *
 * Everything the vector style paints on the ground — land, water, roads — is
 * hidden while imagery is showing, because the photograph already says all of
 * it and more accurately. Its symbol layers stay, restyled for contrast: those
 * are the place names, and they are the whole reason this is a layer toggle
 * rather than a second style.
 */
function applyBasemap(
  map: maplibregl.Map,
  basemap: Basemap,
  basemapLayers: readonly BasemapLayer[],
): void {
  const satellite = basemap === "satellite";

  if (map.getLayer(SATELLITE_LAYER)) {
    map.setLayoutProperty(SATELLITE_LAYER, "visibility", satellite ? "visible" : "none");
  }

  for (const layer of basemapLayers) {
    if (layer.type === "symbol") {
      // Restore the style's own values when leaving satellite; a hard-coded
      // "dark grey" would quietly become this app's opinion of positron.
      for (const [property, imageryValue] of Object.entries(IMAGERY_LABEL_PAINT)) {
        const value = satellite ? imageryValue : layer.paint[property];
        try {
          map.setPaintProperty(layer.id, property, value);
        } catch {
          // A layer without that paint property — an icon-only shield, say.
        }
      }
      continue;
    }
    map.setLayoutProperty(layer.id, "visibility", satellite ? "none" : "visible");
  }
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

export type GeoJsonData = Parameters<maplibregl.GeoJSONSource["setData"]>[0];

/**
 * A layer that came with the basemap style, remembered before this app adds any
 * of its own — which is the only way to tell the two apart afterwards.
 */
interface BasemapLayer {
  id: string;
  type: string;
  /** The style's own paint values, so leaving satellite can restore them. */
  paint: Record<string, unknown>;
}

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
  /** Tilted, with real elevation under the hexagons. */
  terrain: boolean;
  /** Child areas shaded by coverage, or null when hexagons carry the view. */
  childAreas: AreaChildren | null;
  /** The selected area's border, outlined and used to dim everything else. */
  areaOutline: AreaOutline | null;
  fitTo: FitTarget | null;
  /**
   * The fleet, drawn at hexagon resolution. Devices with no reading yet carry
   * no position and are simply not drawn.
   */
  collectors: Collector[];
  /** Base stations the fleet has placed, with their uncertainty. */
  cells: GeoJsonData;
  /** Wording for the hover popup; kept out of this file so it stays translated. */
  collectorLabels: { collector: string; approximate: string };
  /** Shown when the view outruns the satellite imagery. */
  imageryLimitLabel: string;
  /** Wording for the mast popup, kept out of this file so it stays translated. */
  cellLabels: {
    mast: string;
    accuracy: string;
    heardFrom: string;
    strongest: string;
    estimate: string;
  };
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
  terrain,
  childAreas,
  areaOutline,
  fitTo,
  collectors,
  cells,
  collectorLabels,
  imageryLimitLabel,
  cellLabels,
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
  const latestCollectors = useRef<GeoJsonData>(EMPTY_GEOJSON as unknown as GeoJsonData);
  const latestCells = useRef<GeoJsonData>(EMPTY_GEOJSON as unknown as GeoJsonData);
  const latestLinks = useRef<GeoJsonData>(EMPTY_GEOJSON as unknown as GeoJsonData);
  const handlers = useRef({ onBoundsChange, onSelect, onAreaSelect, collectorLabels, cellLabels });
  handlers.current = { onBoundsChange, onSelect, onAreaSelect, collectorLabels, cellLabels };

  /**
   * Positions as GeoJSON.
   *
   * Built from what the server published — a hexagon centroid — so nothing
   * here can be more precise than the server intended it to be.
   */
  const collectorPoints = useMemo<GeoJsonData>(
    () => ({
      type: "FeatureCollection",
      // Truthiness, not `!== null`: an older server omits the field entirely,
      // and `undefined !== null` is true — which passed the filter and then
      // threw on the first property read, taking the whole page down with it.
      // Grouped by position, because the position is a hexagon centroid and
      // two phones in one hexagon therefore have identical coordinates. Drawn
      // one feature each, they stack exactly and a fleet of five looks like a
      // fleet of one — which is what a collector sitting beside a colleague
      // sees. The count goes on the marker instead.
      //
      // Only collectors still reporting are counted. A reinstalled app cannot
      // resume its old identity, so one handset accumulates an identity per
      // install and every one of them keeps its last hexagon forever: one
      // phone reinstalled three times drew a "4" on a hexagon holding a single
      // collector. Counting the ones that have uploaded recently answers the
      // question the number is actually asked — how many collectors are here
      // now — and a dormant identity cannot inflate it.
      features: Object.values(
        collectors.reduce<
          Record<
            string,
            {
              type: "Feature";
              geometry: { type: "Point"; coordinates: number[] };
              properties: { count: number; reporting: boolean };
            }
          >
        >((grouped, row) => {
          if (!row.position) return grouped;
          const key = `${row.position.lon},${row.position.lat}`;
          const existing = grouped[key];
          if (existing) {
            if (row.is_reporting === true) existing.properties.count += 1;
            // One phone still uploading is enough for the place to count as
            // live; a marker going hollow because a second phone went flat
            // would misreport the first.
            existing.properties.reporting ||= row.is_reporting === true;
            return grouped;
          }
          grouped[key] = {
            type: "Feature",
            geometry: { type: "Point", coordinates: [row.position.lon, row.position.lat] },
            properties: {
              count: row.is_reporting === true ? 1 : 0,
              reporting: row.is_reporting === true,
            },
          };
          return grouped;
        }, {}),
      ),
    }) as unknown as GeoJsonData,
    [collectors],
  );
  latestCollectors.current = collectorPoints;
  latestCells.current = cells;

  /**
   * One line per collector that has a placed mast serving it.
   *
   * Built here rather than on the server because both endpoints are already
   * fetched: the line is simply the two points the client already holds, and
   * sending a third payload to say so would be a round trip for no fact.
   */
  const links = useMemo<GeoJsonData>(
    () => ({
      type: "FeatureCollection",
      features: collectors.flatMap((row) =>
        row.position && row.serving_tower
          ? [
              {
                type: "Feature" as const,
                geometry: {
                  type: "LineString" as const,
                  coordinates: [
                    [row.position.lon, row.position.lat],
                    [row.serving_tower.lon, row.serving_tower.lat],
                  ],
                },
                properties: {
                  // Rounded to the precision the estimate can carry: a metre
                  // figure beside a kilometre of doubt would be a fiction.
                  label:
                    row.serving_tower.distance_m >= 1000
                      ? `≈ ${(row.serving_tower.distance_m / 1000).toFixed(1)} km`
                      : `≈ ${Math.round(row.serving_tower.distance_m / 50) * 50} m`,
                },
              },
            ]
          : [],
      ),
    }) as unknown as GeoJsonData,
    [collectors],
  );
  latestLinks.current = links;

  useEffect(() => {
    const instance = map.current;
    if (!instance?.getSource(LINKS_SOURCE)) return;
    (instance.getSource(LINKS_SOURCE) as maplibregl.GeoJSONSource).setData(links as never);
  }, [links]);

  useEffect(() => {
    const instance = map.current;
    if (!instance?.getSource(CELLS_SOURCE)) return;
    (instance.getSource(CELLS_SOURCE) as maplibregl.GeoJSONSource).setData(cells as never);
  }, [cells]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !instance.getSource(COLLECTORS_SOURCE)) return;
    (instance.getSource(COLLECTORS_SOURCE) as maplibregl.GeoJSONSource).setData(
      collectorPoints as never,
    );
  }, [collectorPoints]);

  /**
   * The broadcast: a ring that swells out of each mast and fades.
   *
   * Driven from here because a paint property cannot depend on the clock. The
   * radius grows and the opacity falls together, so the ring dissolves rather
   * than stopping at an edge — an edge would read as the limit of coverage,
   * which is precisely the thing this platform has not measured and must not
   * appear to claim.
   *
   * Every mast pulses in step. Staggering them would need a phase per feature
   * and a data rewrite each frame, which is a lot of work to make a decorative
   * ring less tidy.
   *
   * Stopped entirely under prefers-reduced-motion, like the collector beacon
   * and the link dashes. Everything the pulse conveys — where the mast is, and
   * whose it is — is already in the dot beneath it.
   */
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;
    const timer = window.setInterval(() => {
      const instance = map.current;
      if (!instance?.getLayer(CELLS_PULSE_LAYER)) return;

      frame = (frame + 1) % PULSE_FRAMES;
      const progress = frame / PULSE_FRAMES;
      instance.setPaintProperty(CELLS_PULSE_LAYER, "circle-radius", 4 + progress * 26);
      // Fades to nothing well before the ring stops growing, so it never
      // draws a boundary.
      instance.setPaintProperty(
        CELLS_PULSE_LAYER,
        "circle-stroke-opacity",
        Math.max(0, 0.55 * (1 - progress) ** 1.6),
      );
    }, PULSE_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, []);

  /**
   * The dashes travel from the phone towards the mast.
   *
   * MapLibre cannot animate a paint property, so the pattern is stepped
   * through by hand — a short cycle of dash arrays that reads as movement in
   * one direction. Direction matters: the line runs phone to mast in the
   * geometry, so the flow says which end is being served by which.
   *
   * Stopped under prefers-reduced-motion, like the collector beacon. A moving
   * line is decoration on top of a fact, and the fact survives without it.
   */
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    // Each frame shifts the gap along, so the drawn segment appears to travel.
    const frames = [
      [0, 4, 3],
      [0.5, 4, 2.5],
      [1, 4, 2],
      [1.5, 4, 1.5],
      [2, 4, 1],
      [2.5, 4, 0.5],
      [3, 4, 0],
    ];
    let step = 0;
    const timer = window.setInterval(() => {
      const instance = map.current;
      if (!instance?.getLayer(LINKS_LAYER)) return;
      step = (step + 1) % frames.length;
      instance.setPaintProperty(LINKS_LAYER, "line-dasharray", frames[step]);
    }, 90);

    return () => window.clearInterval(timer);
  }, []);

  /**
   * The beacon: alternate the marker's colour on a timer.
   *
   * A paint expression cannot depend on the clock, so the swap is driven from
   * here. Only the colour changes — radius and ring stay put, because a marker
   * that also grows and shrinks is harder to click and drags the eye away from
   * the coverage the map exists to show.
   *
   * Stopped entirely when the reader has asked for reduced motion. A blinking
   * element is exactly what that setting is for, and a marker that never
   * changes colour still says everything this one needs to.
   */
  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;

    let phase = 0;
    const timer = window.setInterval(() => {
      const instance = map.current;
      if (!instance?.getLayer(COLLECTORS_LAYER)) return;
      phase = 1 - phase;
      instance.setPaintProperty(COLLECTORS_LAYER, "circle-color", BEACON[phase]);
    }, BEACON_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, []);

  // The auto-fit must happen once, and must not fight the user afterwards.
  const hasFitted = useRef(false);

  // What the basemap style itself contributed, and which basemap is showing.
  const basemapLayers = useRef<BasemapLayer[]>([]);
  const currentBasemap = useRef(basemap);
  currentBasemap.current = basemap;
  const currentTerrain = useRef(terrain);
  currentTerrain.current = terrain;

  /**
   * Whether `style.load` has fired.
   *
   * Deliberately not `isStyleLoaded()`, which stays false until every sprite
   * and tile has arrived — long after the layers exist and can be toggled.
   * Guarding on it silently swallowed the first basemap switch.
   */
  const styleReady = useRef(false);

  /** Whether the view has zoomed past the imagery's own resolution. */
  const [beyondImagery, setBeyondImagery] = useState(false);

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      // Always the vector style. Satellite is a layer inside it, so that its
      // place names survive the switch.
      style: STREETS_STYLE,
      center: INITIAL_VIEW ? [INITIAL_VIEW.lon, INITIAL_VIEW.lat] : INITIAL_CENTRE,
      zoom: INITIAL_VIEW ? INITIAL_VIEW.zoom : INITIAL_ZOOM,
      // Past MapLibre's default of 60, which is not enough to look along a
      // valley — the view terrain is worth switching on for.
      maxPitch: MAX_PITCH,
      attributionControl: { compact: true },
    });
    map.current = instance;

    if (import.meta.env.DEV) {
      (window as unknown as { map?: maplibregl.Map }).map = instance;
    }

    // The compass is shown, and is the way back: dragging with two fingers
    // rotates and tilts the map whether or not anyone meant to, and without it
    // there is no obvious way to get north pointing up again.
    instance.addControl(
      new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }),
      "top-right",
    );
    // Bottom right, not the default bottom left, which is where the legend
    // lives — the scale bar was being drawn underneath it. MapLibre stacks
    // controls sharing a corner, so it sits tidily above the attribution.
    instance.addControl(
      new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }),
      "bottom-right",
    );

    const watchZoom = () => setBeyondImagery(instance.getZoom() > SATELLITE_TILES.maxzoom!);
    instance.on("zoom", watchZoom);
    watchZoom();

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

    /**
     * Record what the basemap brought, then slot the imagery in underneath its
     * labels.
     *
     * Everything after this point is added by this app, so capturing the layer
     * list here is what lets the basemap toggle leave our own layers alone.
     */
    const adoptStyle = () => {
      basemapLayers.current = instance
        .getStyle()
        .layers.map((layer) => ({
          id: layer.id,
          type: layer.type,
          paint: { ...((layer as { paint?: Record<string, unknown> }).paint ?? {}) },
        }));

      // Declared now, drawn only if the 3D view is switched on: a raster-dem
      // source fetches nothing until terrain asks it for elevation.
      if (!instance.getSource(TERRAIN_SOURCE)) {
        instance.addSource(TERRAIN_SOURCE, TERRAIN_TILES);
      }

      if (!instance.getSource(SATELLITE_SOURCE)) {
        instance.addSource(SATELLITE_SOURCE, SATELLITE_TILES);
        // Below the first symbol layer, so place names sit on the photograph
        // instead of being buried by it.
        const firstLabel = basemapLayers.current.find((layer) => layer.type === "symbol");
        instance.addLayer(
          {
            id: SATELLITE_LAYER,
            type: "raster",
            source: SATELLITE_SOURCE,
            layout: { visibility: "none" },
          },
          firstLabel?.id,
        );
      }
    };

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
        paint: {
          "fill-color": COLOUR_EXPRESSION,
          // Shaded as strongly as the evidence is thick.
          //
          // A flat opacity painted a whole district in the colour of whatever
          // had been measured inside it — one hexagon covering 3% of
          // Sisattanak made all 26 km² solid green, which reads as "this
          // district has good coverage" rather than "one place in it was
          // measured and was good". The dashboard is careful to report how
          // little of the country is surveyed; the map has to be as careful.
          //
          // Never zero: an area that has been visited at all should be
          // distinguishable from one nobody has been to, which is drawn grey.
          "fill-opacity": [
            "interpolate",
            ["linear"],
            ["get", "measured_share_pct"],
            0, 0.1,
            5, 0.24,
            25, 0.45,
            60, 0.6,
          ],
        },
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

      // The link from a phone to the mast serving it.
      //
      // Dashed and moving, because a solid line would read as a surveyed
      // connection. Both ends are estimates — the phone is placed at its
      // hexagon centre and the mast to about a kilometre — so this says
      // "these two are associated and roughly this far apart", which is all
      // the data supports.
      instance.addSource(LINKS_SOURCE, { type: "geojson", data: latestLinks.current });
      instance.addLayer({
        id: LINKS_LAYER,
        type: "line",
        source: LINKS_SOURCE,
        layout: { "line-cap": "round" },
        paint: {
          "line-color": "#6b21a8",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 14, 2.4],
          "line-opacity": 0.75,
          "line-dasharray": [0, 2, 3],
        },
      });
      instance.addLayer({
        id: LINKS_LABEL_LAYER,
        type: "symbol",
        source: LINKS_SOURCE,
        layout: {
          "symbol-placement": "line-center",
          "text-field": ["get", "label"],
          "text-size": 11,
          "text-offset": [0, -0.8],
        },
        paint: {
          "text-color": "#6b21a8",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.5,
        },
      });

      // Base stations, drawn under the fleet and over the hexagons.
      //
      // Two layers, and the halo is the important one: it is the uncertainty
      // the estimate carries, in metres, drawn to the map's own scale. A mast
      // placed from readings spread over eight kilometres is not known to the
      // metre, and a bare dot would be believed as though it were.
      instance.addSource(CELLS_SOURCE, { type: "geojson", data: latestCells.current });
      // The pulse sits under the uncertainty halo and the mast itself, so it
      // never obscures either.
      instance.addLayer({
        id: CELLS_PULSE_LAYER,
        type: "circle",
        source: CELLS_SOURCE,
        paint: {
          "circle-radius": 4,
          "circle-color": "transparent",
          "circle-stroke-width": 2,
          "circle-stroke-color": OPERATOR_COLOUR_EXPRESSION,
          "circle-stroke-opacity": 0.55,
        },
      });

      instance.addLayer({
        id: CELLS_HALO_LAYER,
        type: "circle",
        source: CELLS_SOURCE,
        paint: {
          // Radius in real metres, converted at this latitude and zoom, so the
          // circle shrinks and grows with the map rather than staying a
          // decorative blob.
          "circle-radius": [
            "interpolate", ["exponential", 2], ["zoom"],
            8, ["/", ["get", "uncertainty_m"], 150],
            16, ["/", ["get", "uncertainty_m"], 1.2],
          ],
          "circle-color": OPERATOR_COLOUR_EXPRESSION,
          "circle-opacity": 0.10,
          "circle-stroke-width": 1,
          "circle-stroke-color": OPERATOR_COLOUR_EXPRESSION,
          "circle-stroke-opacity": 0.35,
        },
      });
      instance.addLayer({
        id: CELLS_LAYER,
        type: "circle",
        source: CELLS_SOURCE,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3, 14, 6],
          // Coloured by network, from a palette outside the coverage scale, so
          // a mast is never mistaken for a reading or a collector.
          "circle-color": OPERATOR_COLOUR_EXPRESSION,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#ffffff",
        },
      });

      // Where the fleet is, to the nearest hexagon. Drawn last so a collector
      // is never hidden under the coverage it just produced.
      instance.addSource(COLLECTORS_SOURCE, {
        type: "geojson",
        data: latestCollectors.current,
      });
      instance.addLayer({
        id: COLLECTORS_LAYER,
        type: "circle",
        source: COLLECTORS_SOURCE,
        paint: {
          // Indigo, which means nothing on the coverage scale.
          //
          // This was grey for a silent collector, at 55% opacity. Grey is the
          // platform's colour for "no measurement", so a silent phone drew a
          // pale grey disc in the middle of the hexagon it had just measured —
          // unmeasured ground inside measured ground, which is a contradiction,
          // and the transparency made it read as a hole punched through the
          // tile. The marker was also placed at the hexagon's exact centroid,
          // so it landed dead centre and looked like part of the tile rather
          // than something drawn over it.
          //
          // Every coverage colour is spoken for — green, yellow, orange, red —
          // so the fleet gets a hue from outside that scale entirely, and
          // whether a phone is reporting is carried by fill rather than by hue:
          // solid when it has uploaded recently, hollow when it has gone quiet.
          // Grows a little when it stands for more than one phone, so the
          // number has somewhere to sit and a shared hexagon is visibly
          // different from a single collector before the label is read.
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6, ["case", [">", ["get", "count"], 1], 6, 3.5],
            12, ["case", [">", ["get", "count"], 1], 11, 7],
          ],
          // Beacon red and blue, alternating — see BEACON below. The colour is
          // driven from JavaScript rather than an expression because a paint
          // expression cannot depend on time.
          "circle-color": BEACON[0],
          "circle-opacity": 1,
          // A white ring under both colours, always. It is what stops a red
          // marker being read as a red hexagon: no tile on this map has a
          // white outline, so anything wearing one is drawn on top rather than
          // part of the coverage beneath it.
          "circle-stroke-width": 2.5,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-opacity": 1,
        },
      });

      // How many phones that marker stands for. Only where it is more than
      // one: a "1" on every single collector would be noise.
      instance.addLayer({
        id: COLLECTORS_COUNT_LAYER,
        type: "symbol",
        source: COLLECTORS_SOURCE,
        filter: [">", ["get", "count"], 1],
        layout: {
          "text-field": ["to-string", ["get", "count"]],
          "text-size": ["interpolate", ["linear"], ["zoom"], 6, 9, 12, 13],
          "text-font": ["Noto Sans Bold", "Open Sans Bold", "Arial Unicode MS Bold"],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          // Reads against both states of the disc it sits on.
          // White in both beacon phases: red and blue are each dark enough to
          // carry white type, and a colour that switched with them would
          // flicker the number as well as the disc.
          "text-color": "#ffffff",
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

      /*
        Hovering a collector shows the coordinates it reported from.

        They are the hexagon's centre, not the phone's fix — the server never
        publishes the fix — so the popup says so rather than leaving a reader to
        assume six decimal places of truth. Four decimals is about eleven
        metres, which is already far finer than the 740 m the number actually
        means; more would be dressing up an approximation.
      */
      const collectorPopup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 14,
        className: "collector-popup",
      });

      instance.on("mousemove", COLLECTORS_LAYER, (event) => {
        const feature = event.features?.[0] as MapGeoJSONFeature | undefined;
        if (!feature || feature.geometry.type !== "Point") return;
        instance.getCanvas().style.cursor = "pointer";

        const [lon, lat] = feature.geometry.coordinates as [number, number];
        const labels = handlers.current.collectorLabels;
        const count = Number(feature.properties?.count ?? 1);
        const heading = count > 1 ? `${labels.collector} × ${count}` : labels.collector;

        collectorPopup
          .setLngLat([lon, lat])
          .setHTML(
            `<strong>${heading}</strong>` +
              `<span class="collector-popup-coords">lat ${lat.toFixed(4)}<br>lon ${lon.toFixed(4)}</span>` +
              `<span class="collector-popup-note">${labels.approximate}</span>`,
          )
          .addTo(instance);
      });

      /*
        Hovering a mast says what it is and how well it is known.

        The uncertainty is given as prominently as the position, because this
        is an estimate derived from where a phone could hear the cell, not a
        surveyed location. An engineer reading "Lao Telecom" beside a dot will
        otherwise take the dot literally and drive to it.
      */
      const cellPopup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 14,
        className: "collector-popup",
      });

      instance.on("mousemove", CELLS_LAYER, (event) => {
        const feature = event.features?.[0] as MapGeoJSONFeature | undefined;
        if (!feature || feature.geometry.type !== "Point") return;
        instance.getCanvas().style.cursor = "pointer";

        const properties = feature.properties ?? {};
        const labels = handlers.current.cellLabels;
        const accuracy = Number(properties.uncertainty_m ?? 0);
        const best = properties.best_rsrp_dbm;

        const lines = [
          `<strong>${properties.operator ?? labels.mast}</strong>`,
          `<span class="collector-popup-coords">${labels.mast} · ${properties.cell ?? ""}</span>`,
          `<span class="collector-popup-coords">${labels.accuracy}: ±${
            accuracy >= 1000 ? `${(accuracy / 1000).toFixed(1)} km` : `${Math.round(accuracy)} m`
          }</span>`,
          `<span class="collector-popup-coords">${labels.heardFrom}: ${
            properties.observations ?? 0
          }${best != null ? ` · ${labels.strongest} ${best} dBm` : ""}</span>`,
          `<span class="collector-popup-note">${labels.estimate}</span>`,
        ];

        cellPopup
          .setLngLat(feature.geometry.coordinates as [number, number])
          .setHTML(lines.join(""))
          .addTo(instance);
      });

      instance.on("mouseleave", CELLS_LAYER, () => {
        instance.getCanvas().style.cursor = "";
        cellPopup.remove();
      });

      instance.on("mouseleave", COLLECTORS_LAYER, () => {
        instance.getCanvas().style.cursor = "";
        collectorPopup.remove();
      });
    };

    instance.on("style.load", () => {
      window.clearTimeout(styleTimer);
      adoptStyle();
      addLayers();
      styleReady.current = true;
      if (currentTerrain.current) applyTerrain(instance, true);
      // The fallback style can arrive after the user has already chosen
      // satellite, so the choice is re-applied rather than assumed.
      applyBasemap(instance, currentBasemap.current, basemapLayers.current);
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
   * A layer toggle, not a style swap. Replacing the style discarded every layer
   * the vector basemap provided, place names included, which is why satellite
   * used to be unlabelled. It also tore down and rebuilt the coverage layers on
   * every switch; now nothing but visibility changes.
   */
  useEffect(() => {
    const instance = map.current;
    if (!instance || !styleReady.current) return;
    applyBasemap(instance, basemap, basemapLayers.current);
  }, [basemap]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !styleReady.current) return;
    applyTerrain(instance, terrain);
  }, [terrain]);

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

  return (
    <>
      <div ref={container} className="map" />
      {/*
        Sentinel-2 is a 10 m/pixel satellite, which is about zoom 14 at Lao
        latitudes. Past that the screen is asking for detail that was never
        photographed, and MapLibre magnifies what it has. Saying so is better
        than letting a reader conclude the map is broken or the tiles failed —
        and it is the difference between a limit and a fault.
      */}
      {basemap === "satellite" && beyondImagery && (
        <div className="imagery-limit">{imageryLimitLabel}</div>
      )}
    </>
  );
}
