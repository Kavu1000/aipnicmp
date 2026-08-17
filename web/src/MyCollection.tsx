import { useEffect, useState } from "react";
import { fetchMyDevices, fetchMySummary, type MyDevice, type MySummary } from "./api";
import { formatAge, stateInfo } from "./coverage";
import type { Strings } from "./i18n";

/**
 * What one collector covered, and nothing else.
 *
 * Every figure here comes from `/mine`, which is scoped on the server to the
 * handsets this account owns. There is no parameter for whose data to show,
 * because a parameter is a thing a client can change — and what would be
 * changed into is a record of where somebody else has been.
 */
export function MyCollection({ t }: { t: Strings }) {
  const [devices, setDevices] = useState<MyDevice[] | null>(null);
  const [summary, setSummary] = useState<MySummary | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchMyDevices(controller.signal)
      .then((body) => setDevices(body.devices))
      .catch(() => setDevices([]));
    fetchMySummary(controller.signal)
      .then(setSummary)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const info = stateInfo(t);

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{t.mineTitle}</h2>
          <p>{t.mineSubtitle}</p>
        </div>
      </header>

      {devices !== null && devices.length === 0 ? (
        /* Not an error. An account exists before anybody links a phone to it,
           and saying so beats an empty table that looks broken. */
        <p className="empty">{t.mineNoDevices}</p>
      ) : (
        <>
          {summary && (
            <dl className="metrics">
              <div>
                <dt>{t.mineReadings}</dt>
                <dd>{summary.measurements.toLocaleString()}</dd>
              </div>
              <div>
                <dt>{t.mineHexagons}</dt>
                <dd>{summary.hexagons.toLocaleString()}</dd>
              </div>
              <div>
                <dt>{t.statUpdated}</dt>
                <dd className="small">{formatAge(summary.latest, t.never)}</dd>
              </div>
              {/* The networks this account's own handsets were on. Not a view
                  of any operator's coverage — just which SIMs these phones
                  carried. */}
              {summary.networks.length > 0 && (
                <div>
                  <dt>{t.operator}</dt>
                  <dd className="small">{summary.networks.join(", ")}</dd>
                </div>
              )}
            </dl>
          )}

          {summary && Object.keys(summary.by_state).length > 0 && (
            <ul className="mine-states">
              {Object.entries(summary.by_state).map(([state, count]) => {
                const entry = info[state as keyof typeof info];
                return (
                  <li key={state}>
                    <span
                      className="swatch"
                      style={{ background: entry ? `var(--state-${entry.colour})` : undefined }}
                    />
                    <span className="legend-text">
                      <strong>{entry ? entry.label : state}</strong>
                      <em>{count.toLocaleString()}</em>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t.collectorsDevice}</th>
                  <th>{t.collectorsSpec}</th>
                  <th className="num">{t.collectorsReports}</th>
                  <th>{t.collectorsLastSeen}</th>
                  <th className="num">{t.collectorsAccepted}</th>
                </tr>
              </thead>
              <tbody>
                {(devices ?? []).map((device) => (
                  <tr key={device.id}>
                    <td>
                      <span className="device-name">{device.model ?? device.id}</span>
                      <span className="device-meta">{device.id}</span>
                    </td>
                    <td className="small">
                      <span className="device-name">{device.manufacturer ?? "—"}</span>
                      <span className="device-meta">
                        {device.android_version ? `Android ${device.android_version}` : "—"}
                        {device.app_version && ` · app ${device.app_version}`}
                      </span>
                    </td>
                    <td className="num small">
                      {device.capability ? (
                        <>
                          <span>
                            {t.collectorsHasSignal}: {device.capability.rsrp_pct}%
                          </span>
                          <span className="device-meta">
                            {t.collectorsCellsSeen}: {device.capability.cells_seen ?? "—"}
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>{formatAge(device.last_seen_at, "—")}</td>
                    <td className="num good">{device.records_accepted.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
