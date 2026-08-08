import { COLOUR_HEX, LEGEND_ORDER, STATE_INFO } from "./coverage";

/**
 * The legend carries the argument, not just the key.
 *
 * A colour scale alone would say "this area is red". Naming the remedy beside
 * each colour is what turns the map into a budget conversation: red means a new
 * tower, red-orange means an upgrade, and those are very different numbers.
 */
export function Legend() {
  return (
    <div className="legend">
      <h2>Coverage</h2>
      <ul>
        {LEGEND_ORDER.map((state) => {
          const info = STATE_INFO[state];
          return (
            <li key={state}>
              <span className="swatch" style={{ background: COLOUR_HEX[info.colour] }} />
              <span className="legend-text">
                <strong>{info.label}</strong>
                <em>{info.remedy}</em>
              </span>
            </li>
          );
        })}
      </ul>

      <div className="legend-note">
        <p>
          <span className="swatch swatch-predicted" /> Dashed and faded hexagons are{" "}
          <strong>predicted</strong>, not measured.
        </p>
        <p>Unmeasured areas are left blank — the map claims nothing about them.</p>
      </div>
    </div>
  );
}
