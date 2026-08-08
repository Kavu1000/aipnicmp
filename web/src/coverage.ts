/**
 * The shared vocabulary of the map: colours, labels, and what each state means
 * for someone deciding where to spend money.
 *
 * Kept in one place because the legend, the tile inspector and the map layer
 * must never disagree about what a colour means.
 */

import type { RadioState, TileColour } from "./api";

export const COLOUR_HEX: Record<TileColour, string> = {
  green: "#1f9d55",
  yellow: "#e3b505",
  orange: "#e07b00",
  red_orange: "#d64500",
  red: "#c1121f",
  grey: "#8a8f98",
};

export interface StateDescription {
  label: string;
  meaning: string;
  /** What this state implies for investment — the point of the whole map. */
  remedy: string;
  colour: TileColour;
}

export const STATE_INFO: Record<RadioState, StateDescription> = {
  LTE_GOOD: {
    label: "Good service",
    meaning: "4G data works normally",
    remedy: "No action needed",
    colour: "green",
  },
  LTE_WEAK: {
    label: "Weak 4G",
    meaning: "Data works but is slow (RSRP below −110 dBm)",
    remedy: "Optimisation",
    colour: "yellow",
  },
  REGISTERED_2G_3G: {
    label: "Calls only",
    meaning: "Calls and SMS work, data does not",
    remedy: "Data capacity upgrade",
    colour: "orange",
  },
  CELLS_VISIBLE_UNREGISTERED: {
    label: "Too weak to use",
    meaning: "A tower is visible but the phone cannot connect",
    remedy: "Upgrade or repeater — no new tower needed",
    colour: "red_orange",
  },
  NO_CELL: {
    label: "No network at all",
    meaning: "No tower reaches this area",
    remedy: "New tower — capital investment",
    colour: "red",
  },
};

/** Legend order: best service at the top, reading down to the worst. */
export const LEGEND_ORDER: RadioState[] = [
  "LTE_GOOD",
  "LTE_WEAK",
  "REGISTERED_2G_3G",
  "CELLS_VISIBLE_UNREGISTERED",
  "NO_CELL",
];

export function formatSpeed(kbps: number | null | undefined): string {
  if (kbps == null) return "—";
  if (kbps >= 1000) return `${(kbps / 1000).toFixed(1)} Mbps`;
  return `${Math.round(kbps)} kbps`;
}

export function formatSignal(dbm: number | null | undefined): string {
  return dbm == null ? "—" : `${dbm.toFixed(0)} dBm`;
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
