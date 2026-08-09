import { useState } from "react";
import { COLOUR_HEX, LEGEND_ORDER, stateInfo } from "./coverage";
import type { Strings } from "./i18n";

/**
 * The legend carries the argument, not just the key.
 *
 * A colour scale alone says "this area is red". Naming the remedy beside each
 * colour is what turns the map into a budget conversation: red means a new
 * tower, red-orange means an upgrade, and those are very different numbers.
 *
 * Collapsible because at full size it occupied a third of the screen and
 * competed with the map it was explaining.
 */
export function Legend({ t }: { t: Strings }) {
  const [open, setOpen] = useState(true);
  const info = stateInfo(t);

  if (!open) {
    return (
      <button className="legend-toggle" onClick={() => setOpen(true)}>
        <span className="legend-swatches" aria-hidden="true">
          {LEGEND_ORDER.map((state) => (
            <span key={state} style={{ background: COLOUR_HEX[info[state].colour] }} />
          ))}
        </span>
        {t.legendShow}
      </button>
    );
  }

  return (
    <div className="legend">
      <div className="legend-head">
        <h2>{t.coverage}</h2>
        <button onClick={() => setOpen(false)} aria-label={t.legendHide}>
          ×
        </button>
      </div>

      <ul>
        {LEGEND_ORDER.map((state) => {
          const entry = info[state];
          return (
            <li key={state}>
              <span className="swatch" style={{ background: COLOUR_HEX[entry.colour] }} />
              <span className="legend-text">
                <strong>{entry.label}</strong>
                <em>{entry.remedy}</em>
              </span>
            </li>
          );
        })}
      </ul>

      <div className="legend-note">
        <p>
          <span className="swatch swatch-predicted" /> {t.legendPredicted}
        </p>
        <p>{t.legendUnmeasured}</p>
      </div>
    </div>
  );
}
