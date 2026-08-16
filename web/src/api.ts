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
  /** Centre of the hexagon — never finer than the hexagon itself. */
  lat?: number;
  lon?: number;
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
  /** Everything ever enrolled, including handsets that reinstalled. */
  devices_enrolled?: number;
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

/** 0 country, 1 province, 2 district, 3 village — mirrors app/models/area.py. */
export type AreaLevel = 0 | 1 | 2 | 3;

export interface GeoBounds {
  min_lat: number;
  min_lon: number;
  max_lat: number;
  max_lon: number;
}

export type Geometry =
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] }
  | { type: "Point"; coordinates: number[] };

export interface Area {
  code: string;
  level: AreaLevel;
  name_en: string;
  name_lo: string | null;
  parent_code: string | null;
  centroid: { lat: number; lon: number };
  bounds: GeoBounds;
  area_km2: number | null;
  /**
   * False for a village published as a point rather than a polygon. The map
   * must draw a stated-radius circle in that case, never a border — see
   * backend/app/models/area.py.
   */
  has_boundary: boolean;
  radius_m: number | null;
  source: string | null;
  /** Present only on the single-area endpoint. */
  boundary?: Geometry;
}

export interface AreaCoverage {
  tiles: number;
  devices: number;
  measured_area_km2: number;
  by_state: Partial<Record<RadioState, number>>;
  by_action: Record<InvestmentAction, number>;
  good_pct: number;
  unusable_pct: number;
  /** The area's median state — always the one `colour` describes. */
  state: RadioState | null;
  colour: TileColour;
  /** Too few separate devices to publish the detail below. */
  low_confidence: boolean;
  measurements: number | null;
  avg_rsrp_dbm: number | null;
  avg_download_kbps: number | null;
  last_measured_at: string | null;
}

export interface AreaDetail {
  area: Area;
  operator: string | null;
  /** Null means nothing has been measured here — not that coverage is zero. */
  coverage: AreaCoverage | null;
}

export interface AreaChildFeature {
  type: "Feature";
  geometry: Geometry;
  properties: Area & { coverage: AreaCoverage | null; colour: TileColour };
}

export interface AreaChildren {
  type: "FeatureCollection";
  parent: string;
  level: AreaLevel | null;
  level_name: string | null;
  operator: string | null;
  features: AreaChildFeature[];
}

/**
 * Where a phone last reported from, to the nearest hexagon.
 *
 * Never the GPS fix the handset recorded — the server publishes the hexagon
 * centroid, about 740 m across, and only the latest one. There is no history
 * here by design: a sequence of these would be a movement record.
 */
export interface CollectorPosition {
  h3_index: string;
  lat: number;
  lon: number;
  resolution: number;
  at: string;
}

export interface Collector {
  id: string;
  position?: CollectorPosition | null;
  /** Uploaded recently enough to count as active. See REPORTING_WINDOW. */
  is_reporting?: boolean;
  silent_for_s?: number | null;
  model: string | null;
  manufacturer: string | null;
  /**
   * Networks this phone has reported on, busiest first. Usually one; a
   * dual-SIM handset or one that roamed can report several. Empty until it
   * uploads a reading with a network attached.
   */
  networks: string[];
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

export type UserRole = "super_admin" | "admin";
export type UserStatus = "pending" | "approved" | "rejected";

export interface AccountUser {
  id: number;
  email: string;
  name: string | null;
  picture_url: string | null;
  role: UserRole;
  status: UserStatus;
  requested_at: string | null;
  decided_at: string | null;
  decided_by: string | null;
  last_login_at: string | null;
  login_count: number;
}

export interface SessionState {
  auth_enabled: boolean;
  /** Public by design — it identifies this application to Google. */
  google_client_id: string;
  authenticated: boolean;
  approved: boolean;
  user: AccountUser | null;
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

/** The server refuses a viewport wider than this; see backend tiles.py. */
export const MAX_BBOX_DEGREES = 6;

/**
 * Thrown when the server refused the request for a stated reason, as opposed to
 * failing. Carries the status so callers can tell "this area holds too many
 * hexagons to draw" from "the server is down" — the first is answerable by
 * showing the summary instead, the second is not.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function postJson<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // The session is an httpOnly cookie, so it has to be sent explicitly.
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((payload: { detail?: string }) => payload?.detail)
      .catch(() => undefined);
    throw new ApiError(response.status, detail ?? `${path} responded ${response.status}`);
  }
  return (await response.json()) as T;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { credentials: "same-origin", signal });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body?.detail)
      .catch(() => undefined);
    throw new ApiError(response.status, detail ?? `${path} responded ${response.status}`);
  }
  return (await response.json()) as T;
}

export interface TileQuery {
  /** Ignored when `area` is set: an area bounds its own query. */
  bounds?: Bounds | null;
  operator?: string | null;
  area?: string | null;
}

export async function fetchTiles(query: TileQuery, signal?: AbortSignal): Promise<TileCollection> {
  const params = new URLSearchParams();
  if (query.area) {
    params.set("area", query.area);
  } else if (query.bounds) {
    params.set("min_lat", String(query.bounds.minLat));
    params.set("min_lon", String(query.bounds.minLon));
    params.set("max_lat", String(query.bounds.maxLat));
    params.set("max_lon", String(query.bounds.maxLon));
  }
  if (query.operator) params.set("operator", query.operator);
  return getJson<TileCollection>(`/tiles?${params}`, signal);
}

/**
 * Who is signed in, and what the sign-in screen needs to render.
 *
 * Always resolves — "nobody is signed in" is the application's normal first
 * state, not a failure.
 */
export async function fetchSession(signal?: AbortSignal): Promise<SessionState> {
  return getJson<SessionState>("/auth/session", signal);
}

/** Exchange a Google id token for a session on this platform. */
export async function signInWithGoogle(credential: string): Promise<SessionState> {
  const body = await postJson<{
    authenticated: boolean;
    approved: boolean;
    user: AccountUser;
  }>("/auth/google", { credential });
  return { auth_enabled: true, google_client_id: "", ...body };
}

export async function signOut(): Promise<void> {
  await postJson("/auth/logout");
}

export async function fetchUsers(
  signal?: AbortSignal,
): Promise<{ count: number; pending: number; users: AccountUser[] }> {
  return getJson("/users", signal);
}

export async function decideUser(id: number, status: UserStatus): Promise<AccountUser> {
  const body = await postJson<{ user: AccountUser }>(`/users/${id}/decision`, { status });
  return body.user;
}

export async function setUserRole(id: number, role: UserRole): Promise<AccountUser> {
  const body = await postJson<{ user: AccountUser }>(`/users/${id}/role`, { role });
  return body.user;
}

/** One level of the Country → Province → District → Village cascade. */
export async function fetchAreas(
  parent: string | null,
  signal?: AbortSignal,
): Promise<Area[]> {
  const params = new URLSearchParams();
  if (parent) params.set("parent", parent);
  const body = await getJson<{ areas: Area[] }>(`/areas?${params}`, signal);
  return body.areas;
}

export async function fetchArea(
  code: string,
  operator?: string | null,
  signal?: AbortSignal,
): Promise<AreaDetail> {
  const params = new URLSearchParams();
  if (operator) params.set("operator", operator);
  return getJson<AreaDetail>(`/areas/${encodeURIComponent(code)}?${params}`, signal);
}

/** Every child area with its border and its coverage — the choropleth. */
export async function fetchAreaChildren(
  code: string,
  operator?: string | null,
  signal?: AbortSignal,
): Promise<AreaChildren> {
  const params = new URLSearchParams();
  if (operator) params.set("operator", operator);
  return getJson<AreaChildren>(`/areas/${encodeURIComponent(code)}/children?${params}`, signal);
}

export async function fetchSummary(signal?: AbortSignal): Promise<Summary> {
  return getJson<Summary>("/dashboard/summary", signal);
}

export interface Network {
  operator: string;
  mcc: string | null;
  mnc: string | null;
  tiles: number;
  /**
   * False for a network that exists but nobody has measured. A phone can only
   * measure the network its own SIM is attached to, so an unmeasured operator
   * means no collector carries that SIM — not that it has no coverage.
   */
  measured: boolean;
}

export async function fetchOperatorNames(signal?: AbortSignal): Promise<string[]> {
  const body = await getJson<{ operators: string[] }>("/dashboard/operator-names", signal);
  return body.operators;
}

/** Every Lao network, including the ones with no measurements yet. */
export async function fetchNetworks(signal?: AbortSignal): Promise<Network[]> {
  const body = await getJson<{ networks: Network[] }>("/dashboard/operator-names", signal);
  return body.networks ?? [];
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


/**
 * A base station the fleet has placed, with the doubt that came with it.
 *
 * Derived from our own readings rather than a purchased database. The server
 * publishes only cells whose observations were spread widely enough to
 * constrain a position, and `uncertainty_m` is never smaller than half that
 * spread — so the circle can be drawn rather than a point that would be
 * believed.
 */
export interface ObservedCell {
  operator: string | null;
  cell: string;
  observations: number;
  uncertainty_m: number;
  spread_m: number;
  best_rsrp_dbm: number | null;
  last_seen_at: string | null;
}

export async function fetchCells(signal?: AbortSignal) {
  return getJson<{
    type: "FeatureCollection";
    features: {
      type: "Feature";
      geometry: { type: "Point"; coordinates: [number, number] };
      properties: ObservedCell;
    }[];
  }>("/cells", signal);
}
