/**
 * Client-side geometry for drawing the selected area.
 *
 * Two shapes the server does not send, because both are presentation:
 * the circle standing in for a village with no published polygon, and the
 * inverted polygon that dims everything outside the chosen area.
 */

import type { Area, Geometry } from "./api";

/** Latitude limit of Web Mercator. Beyond this the projection has no meaning. */
const MERCATOR_LIMIT = 85;

const METRES_PER_DEGREE_LAT = 111_320;

/**
 * A circle around a point, as a polygon.
 *
 * Used for villages published as points. Rendered dashed and labelled with its
 * radius, so it can never be mistaken for a surveyed boundary — the platform
 * refuses to invent village borders (see backend/app/models/area.py) and this
 * is the honest picture of what it does know: a place, and how far around it
 * the map is willing to look.
 */
export function circlePolygon(
  lat: number,
  lon: number,
  radiusM: number,
  segments = 72,
): Geometry {
  const latSpan = radiusM / METRES_PER_DEGREE_LAT;
  // A degree of longitude shortens towards the poles; without this the circle
  // is drawn as an ellipse, wider than the radius it claims.
  const lonSpan = latSpan / Math.max(Math.cos((lat * Math.PI) / 180), 1e-6);

  const ring: number[][] = [];
  for (let i = 0; i <= segments; i += 1) {
    const angle = (i / segments) * 2 * Math.PI;
    ring.push([lon + lonSpan * Math.cos(angle), lat + latSpan * Math.sin(angle)]);
  }
  return { type: "Polygon", coordinates: [ring] };
}

/** The area's own outline: its boundary, or its circle when it has none. */
export function outlineOf(area: Area): Geometry | null {
  if (area.boundary && area.boundary.type !== "Point") return area.boundary;
  if (!area.has_boundary && area.radius_m) {
    return circlePolygon(area.centroid.lat, area.centroid.lon, area.radius_m);
  }
  return null;
}

function exteriorRings(geometry: Geometry): number[][][] {
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

/**
 * Everything except the given shape, as one polygon with holes.
 *
 * This is what makes a selection read as a selection. An outline alone leaves
 * the eye to work out which side of the line matters; dimming the outside says
 * it immediately, and keeps the surrounding country visible as context rather
 * than hiding it.
 *
 * MapLibre tessellates a fill from its first ring outwards, treating every
 * later ring as a hole, so the world rectangle goes first and the area's rings
 * follow. An area's own holes are passed through as holes of the mask too,
 * which leaves them undimmed — the same treatment as the area around them, and
 * the right one: a lake inside a district is still inside the district.
 */
export function maskGeometry(geometry: Geometry): Geometry {
  const world = [
    [-180, -MERCATOR_LIMIT],
    [180, -MERCATOR_LIMIT],
    [180, MERCATOR_LIMIT],
    [-180, MERCATOR_LIMIT],
    [-180, -MERCATOR_LIMIT],
  ];
  return { type: "Polygon", coordinates: [world, ...exteriorRings(geometry)] };
}
