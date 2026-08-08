/**
 * Client for the AI-PNICMP API.
 *
 * Types here mirror `backend/app/api/v1`. When the backend contract changes,
 * change this file in the same commit.
 */

export type TileColour = "green" | "yellow" | "orange" | "red_orange" | "red" | "grey";

export type RadioState =
  | "NO_CELL"
  | "CELLS_VISIBLE_UNREGISTERED"
  | "REGISTERED_2G_3G"
  | "LTE_WEAK"
  | "LTE_GOOD";

export interface TileProperties {
  h3: string;
  colour: TileColour;
  state: RadioState | null;
  predicted: boolean;
  confidence?: number | null;
  /** Present only on tiles with enough contributing devices to show detail. */
  measurements?: number;
  devices?: number;
  avg_rsrp_dbm?: number | null;
  avg_download_kbps?: number | null;
  avg_latency_ms?: number | null;
  worst_state?: RadioState | null;
  last_measured_at?: string | null;
  /** Set when the tile rests on too few devices to publish its detail. */
  low_confidence?: boolean;
}

export interface TileFeature {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: TileProperties;
}

export interface TileCollection {
  type: "FeatureCollection";
  features: TileFeature[];
}

export interface Stats {
  measurements: number;
  devices: number;
  tiles: number;
  no_service_measurements: number;
  latest_measurement_at: string | null;
  h3_resolution: number;
}

export interface CandidateSite {
  id: number;
  rank: number | null;
  lat: number;
  lon: number;
  score: number | null;
  population_covered: number | null;
  unserved_population: number | null;
  tiles_improved: number | null;
  recommendation: string | null;
  has_grid_power: boolean | null;
  province: string | null;
  district: string | null;
  model_version: string | null;
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

/** The server refuses a viewport wider than this; see backend tiles.py. */
export const MAX_BBOX_DEGREES = 6;

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { signal });
  if (!response.ok) {
    throw new Error(`${path} responded ${response.status}`);
  }
  return (await response.json()) as T;
}

export interface Bounds {
  minLat: number;
  minLon: number;
  maxLat: number;
  maxLon: number;
}

export async function fetchTiles(bounds: Bounds, signal?: AbortSignal): Promise<TileCollection> {
  const params = new URLSearchParams({
    min_lat: String(bounds.minLat),
    min_lon: String(bounds.minLon),
    max_lat: String(bounds.maxLat),
    max_lon: String(bounds.maxLon),
  });
  return getJson<TileCollection>(`/tiles?${params}`, signal);
}

export async function fetchStats(signal?: AbortSignal): Promise<Stats> {
  return getJson<Stats>("/stats", signal);
}

export async function fetchSites(signal?: AbortSignal): Promise<{ count: number; sites: CandidateSite[] }> {
  return getJson<{ count: number; sites: CandidateSite[] }>("/sites?limit=50", signal);
}
