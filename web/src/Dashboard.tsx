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

/**
 * Coverage grouped by what it would cost to fix.
 *
 * Not by signal strength, which is how a radio engineer would order it. A dead
 * area needs a tower and a weak one needs an upgrade — two very different
 * budget lines — and reporting them as one "bad coverage" number throws away
 * the distinction the whole platform exists to make.
 */
export function Overview({ summary, t }: { summary: Summary | null; t: Strings }) {
  if (!summary || summary.tiles === 0) {
    return <p className="empty">{t.dashNoData}</p>;
  }

  return (
    <>
      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>{t.dashWhatItWouldTake}</h2>
            <p>
              {formatArea(summary.measured_area_km2)} {t.dashCoverageScope} ·{" "}
              {formatShare(summary.measured_share_pct)} {t.ofCountry}
            </p>
          </div>
        </header>

        <div className="action-grid">
          {ACTION_ORDER.map((action) => (
            <div
              key={action}
              className="action-card"
              style={{ borderTopColor: ACTION_COLOUR[action] }}
            >
              <span className="action-label">{actionLabel(action, t)}</span>
              <span className="action-count">{summary.by_action[action] ?? 0}</span>
              <span className="action-area">
                {formatArea(summary.area_by_action_km2[action] ?? 0)}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>{t.coverage}</h2>
          </div>
        </header>
        <StateBar summary={summary} t={t} />
      </section>
    </>
  );
}

/**
 * The five states as one proportional bar.
 *
 * A table of counts makes the reader do the arithmetic. The point of this
 * figure is the shape — how much of what has been measured is unusable — and a
 * bar shows that at a glance.
 */
function StateBar({ summary, t }: { summary: Summary; t: Strings }) {
  const info = stateInfo(t);
  const order = ["LTE_GOOD", "LTE_WEAK", "REGISTERED_2G_3G", "CELLS_VISIBLE_UNREGISTERED", "NO_CELL"] as const;
  const total = order.reduce((sum, state) => sum + (summary.by_state[state] ?? 0), 0);
  if (total === 0) return null;

  return (
    <>
      <div className="state-bar">
        {order.map((state) => {
          const count = summary.by_state[state] ?? 0;
          if (count === 0) return null;
          return (
            <span
              key={state}
              style={{
                width: `${(count / total) * 100}%`,
                background: COLOUR_HEX[info[state].colour],
              }}
              title={`${info[state].label}: ${count}`}
            />
          );
        })}
      </div>

      <ul className="state-legend">
        {order.map((state) => {
          const count = summary.by_state[state] ?? 0;
          if (count === 0) return null;
          return (
            <li key={state}>
              <span className="dot" style={{ background: COLOUR_HEX[info[state].colour] }} />
              <span className="state-name">{info[state].label}</span>
              <span className="state-count">
                {count} · {((count / total) * 100).toFixed(0)}%
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

export function Networks({ t }: { t: Strings }) {
  const [operators, setOperators] = useState<OperatorCoverage[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    fetchOperatorCoverage(controller.signal).then(setOperators).catch(() => undefined);
    return () => controller.abort();
  }, []);

  if (operators.length === 0) return <p className="empty">{t.dashNoData}</p>;

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{t.networksTitle}</h2>
          <p>{t.navNetworksHint}</p>
        </div>
      </header>

      <div className="table-scroll">
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
      </div>
    </section>
  );
}

export function Priority({
  t,
  onShowOnMap,
}: {
  t: Strings;
  onShowOnMap: (lat: number, lon: number) => void;
}) {
  const [areas, setAreas] = useState<PriorityArea[]>([]);
  const [modelled, setModelled] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchPriorityAreas(50, controller.signal)
      .then((body) => {
        setAreas(body.areas);
        setModelled(body.modelled_sites_available);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const info = stateInfo(t);

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{t.priorityTitle}</h2>
          <p>{t.dashPrioritySubtitle}</p>
        </div>
      </header>

      {/* Saying which kind of list this is matters: measured dead zones and
          modelled site rankings are different claims with different authority,
          and a dashboard must not blur them. */}
      {!modelled && <p className="caveat">{t.dashMeasuredNotModelled}</p>}

      {areas.length === 0 ? (
        <p className="empty">{t.dashNoData}</p>
      ) : (
        <div className="table-scroll">
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
        </div>
      )}
    </section>
  );
}
