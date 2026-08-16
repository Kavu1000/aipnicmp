import { useState } from "react";
import { COLOUR_HEX, LEGEND_ORDER, stateInfo } from "./coverage";
import { OPERATOR_COLOURS } from "./MapView";
import type { Strings } from "./i18n";

/**
 * The legend carries the argument, not just the key.
 *
 * A colour scale alone says "this area is red". Naming the remedy beside each
 * colour is what turns the map into a budget conversation: red means a new
 * tower, red-orange means an upgrade, and those are very different numbers.
 *
 * Collapsible because at full size it occupied a third of the screen and
 * competed with the map it was explaining. On a phone it starts collapsed for
 * the same reason, only more so: at full width it covers the map completely,
 * and the colours are legible enough to ask about rather than be told first.
 */
export function Legend({ t }: { t: Strings }) {
  const [open, setOpen] = useState(() => window.innerWidth > 640);
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
        {/* The dot that prompted "why has a grey core inside?" — it sits at the
            centre of the hexagon a phone last reported from, so without a line
            here it reads as part of the tile rather than something over it. */}
        <p>
          <span className="swatch swatch-collector" /> {t.legendCollector}
        </p>
        {/* Which colour belongs to which network. Without this a reader sees
            four kinds of dot and no way to tell whose mast is whose. */}
        <p className="legend-masts">
          {Object.entries(OPERATOR_COLOURS).map(([operator, hex]) => (
            <span key={operator} className="legend-mast">
              <span className="swatch swatch-mast" style={{ background: hex }} />
              {operator}
            </span>
          ))}
        </p>
        <p>{t.legendMasts}</p>
        <p>
          <span className="swatch swatch-predicted" /> {t.legendPredicted}
        </p>
        {/* Without this the shading looks like a quality scale rather than a
            confidence one, and a faintly green district reads as slightly worse
            coverage instead of barely surveyed. */}
        <p>{t.legendAreaShading}</p>
        <p>{t.legendUnmeasured}</p>
      </div>
    </div>
  );
}
