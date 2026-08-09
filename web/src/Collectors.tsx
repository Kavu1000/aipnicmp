import { useEffect, useState } from "react";
import { fetchCollectors, type Collector } from "./api";
import { formatAge } from "./coverage";
import type { Strings } from "./i18n";

/**
 * The fleet: which phones are reporting, and whether their records land.
 *
 * Deliberately shows no position of any kind. This answers "is the equipment
 * working" — a question about phones, not about people — and a collector's own
 * movements are exactly what the map's hexagons exist to hide. Reintroducing
 * them here under an operational heading would undo that quietly.
 *
 * The refused column is the one worth watching. A collector whose records are
 * all being rejected looks identical to a healthy one by every other measure,
 * right up until the map stays empty.
 */
export function Collectors({ t }: { t: Strings }) {
  const [rows, setRows] = useState<Collector[]>([]);
  const [real, setReal] = useState(0);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchCollectors(controller.signal)
      .then((body) => {
        setRows(body.collectors);
        setReal(body.real);
      })
      .catch(() => undefined)
      .finally(() => setLoaded(true));
    return () => controller.abort();
  }, []);

  const simulated = rows.length - real;

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{t.collectorsTitle}</h2>
          <p>{t.collectorsSubtitle}</p>
        </div>
        {rows.length > 0 && (
          <span className="pill">
            {t.collectorsRealCount.replace("%REAL%", String(real)).replace("%SIM%", String(simulated))}
          </span>
        )}
      </header>

      {loaded && rows.length === 0 ? (
        <p className="empty">{t.collectorsNone}</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t.collectorsDevice}</th>
                <th>{t.collectorsLastSeen}</th>
                <th className="num">{t.collectorsAccepted}</th>
                <th className="num">{t.collectorsRejected}</th>
                <th className="num">{t.collectorsRejectRate}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className={row.is_simulated ? "muted-row" : undefined}>
                  <td>
                    <span className="device-name">{row.model ?? row.id}</span>
                    <span className="device-meta">
                      {row.id}
                      {row.is_simulated && ` · ${t.collectorsSimulated}`}
                    </span>
                  </td>
                  <td>{formatAge(row.last_seen_at, "—")}</td>
                  <td className="num good">{row.records_accepted.toLocaleString()}</td>
                  <td className="num">{row.records_rejected.toLocaleString()}</td>
                  <td className={row.rejection_rate_pct > 20 ? "num bad" : "num"}>
                    {row.rejection_rate_pct}%
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
