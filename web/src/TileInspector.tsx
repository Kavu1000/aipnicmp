import type { TileProperties } from "./api";
import { COLOUR_HEX, formatSignal, formatSpeed, formatWhen, stateInfo } from "./coverage";
import type { Strings } from "./i18n";

interface Props {
  tile: TileProperties | null;
  t: Strings;
  onClose: () => void;
}

/**
 * Detail for one hexagon.
 *
 * Deliberately states what the tile does *not* know as plainly as what it does:
 * a prediction says so, and a tile resting on too few contributors says that
 * too rather than quietly showing thinner numbers.
 */
export function TileInspector({ tile, t, onClose }: Props) {
  if (!tile) return null;

  const info = stateInfo(t);
  const entry = tile.state ? info[tile.state] : null;
  const worst = tile.worst_state ? info[tile.worst_state] : null;
  const showsDropouts = worst && tile.worst_state !== tile.state;

  return (
    <aside className="inspector">
      <button className="close" onClick={onClose} aria-label="Close">
        ×
      </button>

      <div className="inspector-head">
        <span className="swatch large" style={{ background: COLOUR_HEX[tile.colour] }} />
        <div>
          <h2>{entry?.label ?? "—"}</h2>
          <p className="muted">{entry?.meaning}</p>
        </div>
      </div>

      {tile.operator && <p className="operator-tag">{tile.operator}</p>}

      {entry && (
        <p className="remedy">
          <strong>{t.inspectorRemedy}</strong> {entry.remedy}
        </p>
      )}

      {tile.predicted ? (
        <p className="caveat">
          {t.inspectorPredicted}
          {tile.confidence != null && ` ${(tile.confidence * 100).toFixed(0)}%`}
        </p>
      ) : tile.low_confidence ? (
        <p className="caveat">{t.inspectorLowConfidence}</p>
      ) : (
        <dl>
          <div>
            <dt>{t.inspectorMeasurements}</dt>
            <dd>{tile.measurements ?? "—"}</dd>
          </div>
          <div>
            <dt>{t.inspectorDevices}</dt>
            <dd>{tile.devices ?? "—"}</dd>
          </div>
          <div>
            <dt>{t.inspectorSignal}</dt>
            <dd>{formatSignal(tile.avg_rsrp_dbm)}</dd>
          </div>
          <div>
            <dt>{t.inspectorDownload}</dt>
            <dd>{formatSpeed(tile.avg_download_kbps)}</dd>
          </div>
          <div>
            <dt>{t.inspectorLatency}</dt>
            <dd>{tile.avg_latency_ms == null ? "—" : `${Math.round(tile.avg_latency_ms)} ms`}</dd>
          </div>
          <div>
            <dt>{t.inspectorLastMeasured}</dt>
            <dd>{formatWhen(tile.last_measured_at, "—")}</dd>
          </div>
        </dl>
      )}

      {showsDropouts && (
        <p className="caveat">
          {t.inspectorDropout} <strong>{worst.label}</strong>.
        </p>
      )}

      <p className="hexid">{tile.h3}</p>
    </aside>
  );
}
