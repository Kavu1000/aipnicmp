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
      ) : (
        /*
          The evidence shows whoever measured it. What a single collector's
          hexagon withholds is the timing — a hexagon plus a moment is a record
          of where somebody was and when, while a hexagon plus an average is
          not. So the rows that place a traveller are the ones that disappear,
          and the panel is no longer all-or-nothing: it used to show this
          caveat *instead of* the figures, which on a pilot where almost every
          hexagon rests on one phone meant a panel with nothing in it.
        */
        <>
          <dl>
            <div>
              <dt>{t.inspectorMeasurements}</dt>
              <dd>{tile.measurements ?? "—"}</dd>
            </div>
            {tile.devices != null && (
              <div>
                <dt>{t.inspectorDevices}</dt>
                <dd>{tile.devices}</dd>
              </div>
            )}
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
            {tile.last_measured_at != null && (
              <div>
                <dt>{t.inspectorLastMeasured}</dt>
                <dd>{formatWhen(tile.last_measured_at, "—")}</dd>
              </div>
            )}
          </dl>
          {tile.low_confidence && <p className="caveat">{t.inspectorLowConfidence}</p>}
        </>
      )}

      {showsDropouts && (
        <p className="caveat">
          {t.inspectorDropout} <strong>{worst.label}</strong>.
        </p>
      )}

      {tile.lat != null && tile.lon != null && (
        <div className="inspector-place">
          <dt>{t.inspectorLocation}</dt>
          <dd>
            {/*
              Four decimals, about 11 m — finer would be false precision, since
              this is the centre of a hexagon 700 m across and not a spot
              anybody measured.
            */}
            <span className="coords">
              {tile.lat.toFixed(4)}, {tile.lon.toFixed(4)}
            </span>
            {/*
              Directions rather than a pin. Someone reading this panel is
              deciding whether to go and look — at a dead zone, a site for a
              mast, a reading they do not believe — and the next thing they
              need is the way there. noreferrer as well as noopener: the map
              provider has no business knowing which coverage page this came
              from.
            */}
            <a
              className="link"
              href={`https://www.google.com/maps/dir/?api=1&destination=${tile.lat},${tile.lon}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t.inspectorDirections}
            </a>
          </dd>
        </div>
      )}

      <p className="hexid">{tile.h3}</p>
    </aside>
  );
}
