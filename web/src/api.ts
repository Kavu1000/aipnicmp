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

/** What a state implies for spending — the project's whole policy argument. */
export type InvestmentAction = "new_tower" | "upgrade" | "optimisation" | "none";

export interface TileProperties {
  h3: string;
  colour: TileColour;
  state: RadioState | null;
  predicted: boolean;
  operator?: string;
  confidence?: number | null;
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
  operator?: string;
  features: TileFeature[];
}

export interface Bounds {
  minLat: number;
  minLon: number;
  maxLat: number;
  maxLon: number;
}

export interface Summary {
  measurements: number;
  devices: number;
  tiles: number;
  no_service_measurements: number;
  measured_area_km2: number;
  country_area_km2: number;
  measured_share_pct: number;
  tile_area_km2: number;
  h3_resolution: number;
  latest_measurement_at: string | null;
  tiles_updated_at: string | null;
  by_state: Partial<Record<RadioState, number>>;
  by_action: Record<InvestmentAction, number>;
  area_by_action_km2: Record<InvestmentAction, number>;
  bounds: { min_lat: number; min_lon: number; max_lat: number; max_lon: number } | null;
}

export interface OperatorCoverage {
  operator: string;
  tiles: number;
  area_km2: number;
  by_state: Partial<Record<RadioState, number>>;
  good_pct: number;
  unusable_pct: number;
  avg_rsrp_dbm: number | null;
}

export interface PriorityArea {
  rank: number;
  h3: string;
  lat: number;
  lon: number;
  state: RadioState;
  colour: TileColour;
  action: InvestmentAction;
  measurements: number;
  devices: number;
  area_km2: number;
  avg_rsrp_dbm: number | null;
  last_measured_at: string | null;
}

export interface Collector {
  id: string;
  model: string | null;
  manufacturer: string | null;
  app_version: string | null;
  key_algorithm: string;
  trust_level: string;
  is_blocked: boolean;
  is_simulated: boolean;
  enrolled_at: string | null;
  last_seen_at: string | null;
  records_accepted: number;
  records_rejected: number;
  rejection_rate_pct: number;
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

export async function fetchTiles(
  bounds: Bounds,
  operator?: string | null,
  signal?: AbortSignal,
): Promise<TileCollection> {
  const params = new URLSearchParams({
    min_lat: String(bounds.minLat),
    min_lon: String(bounds.minLon),
    max_lat: String(bounds.maxLat),
    max_lon: String(bounds.maxLon),
  });
  if (operator) params.set("operator", operator);
  return getJson<TileCollection>(`/tiles?${params}`, signal);
}

export async function fetchSummary(signal?: AbortSignal): Promise<Summary> {
  return getJson<Summary>("/dashboard/summary", signal);
}

export async function fetchOperatorNames(signal?: AbortSignal): Promise<string[]> {
  const body = await getJson<{ operators: string[] }>("/dashboard/operator-names", signal);
  return body.operators;
}

export async function fetchOperatorCoverage(signal?: AbortSignal): Promise<OperatorCoverage[]> {
  const body = await getJson<{ operators: OperatorCoverage[] }>("/dashboard/operators", signal);
  return body.operators;
}

export interface PriorityResponse {
  count: number;
  areas: PriorityArea[];
  /** "measured" until the Layer 4 model exists — the dashboard must say which. */
  source: string;
  modelled_sites_available: boolean;
}

export async function fetchPriorityAreas(
  limit = 25,
  signal?: AbortSignal,
): Promise<PriorityResponse> {
  return getJson<PriorityResponse>(`/dashboard/priority-areas?limit=${limit}`, signal);
}

export async function fetchCollectors(
  signal?: AbortSignal,
): Promise<{ count: number; real: number; collectors: Collector[] }> {
  return getJson<{ count: number; real: number; collectors: Collector[] }>(
    "/dashboard/collectors",
    signal,
  );
}
