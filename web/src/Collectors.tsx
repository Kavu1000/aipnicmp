import { useEffect, useState } from "react";
import { fetchCollectors, type Collector } from "./api";
import { formatAge } from "./coverage";
import type { Strings } from "./i18n";

/**
 * The fleet: which phones are reporting, and whether their records land.
 *
 * Shows where each phone last reported from, at hexagon resolution — roughly
 * 740 m — and never its GPS fix. That is a deliberate limit, not an oversight:
 * a collector's own movements are what the map's hexagons exist to hide, so
 * the operations view is allowed to answer "is anyone working in Attapeu"
 * without being able to answer "where is this person". Only the latest hexagon
 * is available, so no history can be assembled from it.
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
                <th>{t.operator}</th>
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
                  {/* Which network the phone is on. Empty means it has
                      enrolled but not yet sent a reading with one attached —
                      not that it has no network. */}
                  <td>{row.networks.length > 0 ? row.networks.join(", ") : "—"}</td>
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
