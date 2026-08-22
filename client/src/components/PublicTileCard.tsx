import { COLOUR_HEX, formatWhen, stateInfo } from "../coverage";
import type { TileProperties } from "../api";
import type { Strings } from "../i18n";

/**
 * What a click on a public hexagon shows — deliberately smaller than
 * TileInspector, the signed-in equivalent, and styled to match it.
 *
 * Not that component with fields hidden: the public endpoint never sends
 * `last_measured_at`, `devices` or a raw RSRP figure in the first place (see
 * backend public.py's `_public_feature`), so there is nothing here to
 * withhold in the UI. State, colour, and how fresh the map's own last
 * rebuild was — never when a particular phone was there.
 */
export function PublicTileCard({
  tile,
  t,
  onClose,
}: {
  tile: TileProperties;
  t: Strings;
  onClose: () => void;
}) {
  const info = tile.state ? stateInfo(t)[tile.state] : null;

  return (
    <aside className="inspector">
      <button className="close" onClick={onClose} aria-label="Close">
        ×
      </button>

      <div className="inspector-head">
        <span className="swatch large" style={{ background: COLOUR_HEX[tile.colour] }} />
        <div>
          <h2>{info?.label ?? t.tileNotYetMeasured}</h2>
          <p className="muted">{info?.meaning}</p>
        </div>
      </div>

      {info && (
        <p className="remedy">
          <strong>{t.inspectorRemedy}</strong> {info.remedy}
        </p>
      )}

      {tile.predicted && <p className="caveat">{t.inspectorPredicted}</p>}

      <dl>
        <div>
          <dt>{tile.predicted ? t.tilePredicted : t.tileMeasured}</dt>
          <dd>{tile.updated_at ? formatWhen(tile.updated_at, "—") : "—"}</dd>
        </div>
      </dl>
    </aside>
  );
}
