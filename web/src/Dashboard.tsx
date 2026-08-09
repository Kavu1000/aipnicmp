import { useEffect, useState } from "react";
import {
  fetchOperatorCoverage,
  fetchPriorityAreas,
  type InvestmentAction,
  type OperatorCoverage,
  type PriorityArea,
  type Summary,
} from "./api";
import {
  ACTION_COLOUR,
  COLOUR_HEX,
  actionLabel,
  formatArea,
  formatShare,
  formatSignal,
  stateInfo,
} from "./coverage";
import type { Strings } from "./i18n";

const ACTION_ORDER: InvestmentAction[] = ["new_tower", "upgrade", "optimisation", "none"];

interface Props {
  summary: Summary | null;
  t: Strings;
  /** Sends the map to a priority area, so a finding can be inspected in place. */
  onShowOnMap: (lat: number, lon: number) => void;
}

/**
 * The operator and ministry view — proposal Channel 1.
 *
 * Organised around one question: what would it cost to fix this, and where
 * should the money go first. That is why coverage is grouped by remedy rather
 * than by signal strength, and why the priority list is ranked by weight of
 * evidence rather than by severity alone.
 */
export function Dashboard({ summary, t, onShowOnMap }: Props) {
  const [operators, setOperators] = useState<OperatorCoverage[]>([]);
  const [areas, setAreas] = useState<PriorityArea[]>([]);
  const [modelled, setModelled] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchOperatorCoverage(controller.signal).then(setOperators).catch(() => undefined);
    fetchPriorityAreas(25, controller.signal)
      .then((body) => {
        setAreas(body.areas);
        setModelled(body.modelled_sites_available);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const info = stateInfo(t);

  if (!summary || summary.tiles === 0) {
    return (
      <div className="dashboard">
        <p className="empty">{t.dashNoData}</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <header className="dash-head">
        <div>
          <h1>{t.dashTitle}</h1>
          <p>{t.dashSubtitle}</p>
        </div>
        <p className="scope">
          <strong>{formatArea(summary.measured_area_km2)}</strong> {t.dashCoverageScope} ·{" "}
          {formatShare(summary.measured_share_pct)} {t.ofCountry}
        </p>
      </header>

      {/* Grouped by remedy, because a dead area and a weak one are different
          budget lines — the distinction the whole platform exists to make. */}
      <section>
        <h2>{t.dashWhatItWouldTake}</h2>
        <div className="action-grid">
          {ACTION_ORDER.map((action) => (
            <div key={action} className="action-card" style={{ borderTopColor: ACTION_COLOUR[action] }}>
              <span className="action-label">{actionLabel(action, t)}</span>
              <span className="action-count">{summary.by_action[action] ?? 0}</span>
              <span className="action-area">
                {formatArea(summary.area_by_action_km2[action] ?? 0)}
              </span>
            </div>
          ))}
        </div>
      </section>

      {operators.length > 0 && (
        <section>
          <h2>{t.dashByOperator}</h2>
          <table className="data-table">
            <thead>
              <tr>
                <th>{t.operator}</th>
                <th className="num">{t.dashOperatorTiles}</th>
                <th className="num">{t.dashOperatorArea}</th>
                <th className="num">{t.dashOperatorGood}</th>
                <th className="num">{t.dashOperatorUnusable}</th>
                <th className="num">{t.dashOperatorSignal}</th>
              </tr>
            </thead>
            <tbody>
              {operators.map((row) => (
                <tr key={row.operator}>
                  <td>{row.operator}</td>
                  <td className="num">{row.tiles}</td>
                  <td className="num">{formatArea(row.area_km2)}</td>
                  <td className="num good">{row.good_pct}%</td>
                  <td className="num bad">{row.unusable_pct}%</td>
                  <td className="num">{formatSignal(row.avg_rsrp_dbm)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section>
        <h2>{t.dashPriority}</h2>
        <p className="section-note">{t.dashPrioritySubtitle}</p>

        {/* Saying which kind of list this is matters: measured dead zones and
            modelled site rankings are different claims with different
            authority, and a dashboard must not blur them. */}
        {!modelled && <p className="caveat">{t.dashMeasuredNotModelled}</p>}

        {areas.length === 0 ? (
          <p className="empty">{t.dashNoData}</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th className="num">{t.dashRank}</th>
                <th>{t.dashState}</th>
                <th>{t.dashAction}</th>
                <th className="num">{t.dashEvidence}</th>
                <th>{t.dashLocation}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {areas.map((area) => (
                <tr key={area.h3}>
                  <td className="num rank">{area.rank}</td>
                  <td>
                    <span className="dot" style={{ background: COLOUR_HEX[area.colour] }} />
                    {info[area.state]?.label ?? area.state}
                  </td>
                  <td>{actionLabel(area.action, t)}</td>
                  <td className="num">
                    {area.measurements} / {area.devices}
                  </td>
                  <td className="coords">
                    {area.lat.toFixed(4)}, {area.lon.toFixed(4)}
                  </td>
                  <td>
                    <button className="link" onClick={() => onShowOnMap(area.lat, area.lon)}>
                      {t.dashShowOnMap}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
