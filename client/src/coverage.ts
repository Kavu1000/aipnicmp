/**
 * The shared vocabulary of the map: colours, labels, and what each state means
 * for someone deciding where to spend money.
 *
 * Kept in one place because the legend, the tile inspector and the dashboard
 * must never disagree about what a colour means.
 */

import type { InvestmentAction, RadioState, TileColour } from "./api";
import type { Strings } from "./i18n";

export const COLOUR_HEX: Record<TileColour, string> = {
  green: "#1f9d55",
  yellow: "#e3b505",
  orange: "#e07b00",
  red_orange: "#d64500",
  red: "#c1121f",
  grey: "#8a8f98",
};

export const ACTION_COLOUR: Record<InvestmentAction, string> = {
  new_tower: COLOUR_HEX.red,
  upgrade: COLOUR_HEX.orange,
  optimisation: COLOUR_HEX.yellow,
  none: COLOUR_HEX.green,
};

export interface StateDescription {
  label: string;
  meaning: string;
  /** What this state implies for investment — the point of the whole map. */
  remedy: string;
  colour: TileColour;
}

/** Descriptions in the active language. */
export function stateInfo(t: Strings): Record<RadioState, StateDescription> {
  return {
    LTE_GOOD: {
      label: t.stateGoodLabel,
      meaning: t.stateGoodMeaning,
      remedy: t.stateGoodRemedy,
      colour: "green",
    },
    LTE_WEAK: {
      label: t.stateWeakLabel,
      meaning: t.stateWeakMeaning,
      remedy: t.stateWeakRemedy,
      colour: "yellow",
    },
    REGISTERED_2G_3G: {
      label: t.stateCallsLabel,
      meaning: t.stateCallsMeaning,
      remedy: t.stateCallsRemedy,
      colour: "orange",
    },
    CELLS_VISIBLE_UNREGISTERED: {
      label: t.stateUnusableLabel,
      meaning: t.stateUnusableMeaning,
      remedy: t.stateUnusableRemedy,
      colour: "red_orange",
    },
    NO_CELL: {
      label: t.stateNoneLabel,
      meaning: t.stateNoneMeaning,
      remedy: t.stateNoneRemedy,
      colour: "red",
    },
  };
}

/** Legend order: best service at the top, reading down to the worst. */
export const LEGEND_ORDER: RadioState[] = [
  "LTE_GOOD",
  "LTE_WEAK",
  "REGISTERED_2G_3G",
  "CELLS_VISIBLE_UNREGISTERED",
  "NO_CELL",
];

export function actionLabel(action: InvestmentAction, t: Strings): string {
  switch (action) {
    case "new_tower":
      return t.dashNewTower;
    case "upgrade":
      return t.dashUpgrade;
    case "optimisation":
      return t.dashOptimisation;
    default:
      return t.dashNoAction;
  }
}

export function formatSpeed(kbps: number | null | undefined): string {
  if (kbps == null) return "—";
  if (kbps >= 1000) return `${(kbps / 1000).toFixed(1)} Mbps`;
  return `${Math.round(kbps)} kbps`;
}

export function formatSignal(dbm: number | null | undefined): string {
  return dbm == null ? "—" : `${dbm.toFixed(0)} dBm`;
}

/**
 * Area in the unit a reader can picture. Below 1 km² a hexagon is better
 * expressed in hectares than as "0.0 km²", which reads as nothing at all.
 */
export function formatArea(km2: number | null | undefined): string {
  if (km2 == null) return "—";
  if (km2 >= 1000) return `${Math.round(km2).toLocaleString()} km²`;
  if (km2 >= 1) return `${km2.toFixed(1)} km²`;
  return `${Math.round(km2 * 100)} ha`;
}

/**
 * A pilot covers a tiny fraction of a country, and rounding that to a whole
 * percent prints "0%" — wrong, and needlessly discouraging. Small values keep
 * enough decimals to stay a real number.
 */
export function formatShare(pct: number | null | undefined): string {
  if (pct == null) return "—";
  // Exactly zero is a finding, not a rounding artefact. Printing "<0.01%" for
  // it would claim a trace of something that was not measured at all — which
  // matters most where it reads best: "no usable service: 0%".
  if (pct === 0) return "0%";
  if (pct >= 10) return `${pct.toFixed(0)}%`;
  if (pct >= 1) return `${pct.toFixed(1)}%`;
  if (pct >= 0.01) return `${pct.toFixed(2)}%`;
  return `<0.01%`;
}

export function formatWhen(iso: string | null | undefined, fallback: string): string {
  if (!iso) return fallback;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "3 days ago" reads better than a timestamp for a freshness indicator. */
export function formatAge(iso: string | null | undefined, fallback: string): string {
  if (!iso) return fallback;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return fallback;

  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.round(hours / 24)} d`;
}
