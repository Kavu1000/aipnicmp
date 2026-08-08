import type { TileProperties } from "./api";
import { COLOUR_HEX, STATE_INFO, formatSignal, formatSpeed, formatWhen } from "./coverage";

interface Props {
  tile: TileProperties | null;
  onClose: () => void;
}

/**
 * Detail for one hexagon.
 *
 * Deliberately states what the tile does *not* know as plainly as what it does:
 * a prediction says so, and a tile resting on too few contributors says that
 * too rather than quietly showing thinner numbers.
 */
export function TileInspector({ tile, onClose }: Props) {
  if (!tile) return null;

  const info = tile.state ? STATE_INFO[tile.state] : null;
  const worst = tile.worst_state ? STATE_INFO[tile.worst_state] : null;
  const showsDropouts = worst && tile.worst_state !== tile.state;

  return (
    <aside className="inspector">
      <button className="close" onClick={onClose} aria-label="Close">
        ×
      </button>

      <div className="inspector-head">
        <span className="swatch large" style={{ background: COLOUR_HEX[tile.colour] }} />
        <div>
          <h2>{info?.label ?? "Unknown"}</h2>
          <p className="muted">{info?.meaning}</p>
        </div>
      </div>

      {info && (
        <p className="remedy">
          <strong>What it would take:</strong> {info.remedy}
        </p>
      )}

      {tile.predicted ? (
        <p className="caveat">
          Predicted by the coverage model — nobody has measured this hexagon yet.
          {tile.confidence != null && ` Confidence ${(tile.confidence * 100).toFixed(0)}%.`}
        </p>
      ) : tile.low_confidence ? (
        <p className="caveat">
          Measured, but by too few devices to publish the details without risking
          identifying whoever travelled through.
        </p>
      ) : (
        <dl>
          <div>
            <dt>Measurements</dt>
            <dd>{tile.measurements ?? "—"}</dd>
          </div>
          <div>
            <dt>Contributing devices</dt>
            <dd>{tile.devices ?? "—"}</dd>
          </div>
          <div>
            <dt>Average signal</dt>
            <dd>{formatSignal(tile.avg_rsrp_dbm)}</dd>
          </div>
          <div>
            <dt>Download</dt>
            <dd>{formatSpeed(tile.avg_download_kbps)}</dd>
          </div>
          <div>
            <dt>Latency</dt>
            <dd>{tile.avg_latency_ms == null ? "—" : `${Math.round(tile.avg_latency_ms)} ms`}</dd>
          </div>
          <div>
            <dt>Last measured</dt>
            <dd>{formatWhen(tile.last_measured_at)}</dd>
          </div>
        </dl>
      )}

      {showsDropouts && (
        <p className="caveat">
          Service here is not always this good — at its worst it drops to{" "}
          <strong>{worst.label}</strong>.
        </p>
      )}

      <p className="hexid">{tile.h3}</p>
    </aside>
  );
}
