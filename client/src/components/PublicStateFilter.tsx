import type { RadioState } from "../api";
import { LEGEND_ORDER, stateInfo } from "../coverage";
import type { Strings } from "../i18n";

/**
 * One of the five states, so a reader can ask "where is there no network at
 * all" instead of reading five colours off the map at once.
 *
 * Filters client-side, over hexagons the map already has — `dominant_state`
 * is already on every public tile (see backend public.py's
 * `_public_feature`), so narrowing to one state discloses nothing the
 * viewport fetch had not already sent.
 */
export function PublicStateFilter({
  t,
  value,
  onChange,
}: {
  t: Strings;
  value: RadioState | null;
  onChange: (state: RadioState | null) => void;
}) {
  const info = stateInfo(t);
  return (
    <select
      className="select"
      aria-label={t.signalState}
      value={value ?? ""}
      onChange={(event) => onChange((event.target.value || null) as RadioState | null)}
    >
      <option value="">{t.allStates}</option>
      {LEGEND_ORDER.map((state) => (
        <option key={state} value={state}>
          {info[state].label}
        </option>
      ))}
    </select>
  );
}
