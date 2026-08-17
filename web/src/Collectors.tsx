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

  /**
   * Enrolments that have never sent a reading.
   *
   * Almost always a phone that was reinstalled. The install id lives in app
   * data and the signing key lives in the Keystore, where it cannot be backed
   * up by design — so a reinstall cannot resume the old identity and enrols a
   * new one. Six identities for two handsets is what that looks like, and
   * listing them together made a fleet look three times its real size.
   */
  const reporting = rows.filter((row) => row.records_accepted + row.records_rejected > 0);
  const dormant = rows.filter((row) => row.records_accepted + row.records_rejected === 0);

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
        <>
        {/* Without this the two new columns look like trivia. They are the
            reason two phones on the same road can disagree, so the sentence
            has to sit beside them. */}
        <p className="caveat">{t.collectorsSpecNote}</p>

        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t.collectorsDevice}</th>
                <th>{t.collectorsSpec}</th>
                <th className="num">{t.collectorsReports}</th>
                <th>{t.operator}</th>
                <th>{t.collectorsLastSeen}</th>
                <th className="num">{t.collectorsAccepted}</th>
                <th className="num">{t.collectorsRejected}</th>
                <th className="num">{t.collectorsRejectRate}</th>
              </tr>
            </thead>
            <tbody>
              {reporting.map((row) => (
                <tr key={row.id} className={row.is_simulated ? "muted-row" : undefined}>
                  <td>
                    <span className="device-name">{row.model ?? row.id}</span>
                    <span className="device-meta">
                      {row.id}
                      {row.is_simulated && ` · ${t.collectorsSimulated}`}
                    </span>
                  </td>
                  {/* What it is. Held since enrolment and never shown until
                      now, which left the page unable to say why two phones on
                      the same road disagree. */}
                  <td className="small">
                    <span className="device-name">
                      {row.manufacturer ?? "—"}
                    </span>
                    <span className="device-meta">
                      {row.android_version ? `Android ${row.android_version}` : "—"}
                      {row.app_version && ` · app ${row.app_version}`}
                    </span>
                  </td>

                  {/* What it manages to report, which is the part that changes
                      what its readings are worth. A reading with no signal
                      strength is classified pessimistically, so a handset that
                      withholds it produces more weak hexagons on the same
                      ground; a handset that hears few neighbours starves the
                      estimator that places masts. */}
                  <td className="num small">
                    {row.capability ? (
                      <>
                        <span className={row.capability.rsrp_pct < 95 ? "bad" : undefined}>
                          {t.collectorsHasSignal}: {row.capability.rsrp_pct}%
                        </span>
                        <span className="device-meta">
                          {t.collectorsCellsSeen}: {row.capability.cells_seen ?? "—"}
                        </span>
                      </>
                    ) : (
                      "—"
                    )}
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

          {/* Kept, not hidden: each of these holds a signing key that once
              signed real records, and an administrator looking at the fleet
              should be able to see that they exist. Separated so they stop
              being counted as working collectors. */}
          {dormant.length > 0 && (
            <div className="dormant">
              <h3>
                {t.collectorsDormant.replace("%N%", String(dormant.length))}
              </h3>
              <p className="dormant-why">{t.collectorsDormantWhy}</p>
              <ul>
                {dormant.map((row) => (
                  <li key={row.id}>
                    <span className="device-name">{row.model ?? row.id}</span>
                    <span className="device-meta">{row.id}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        </>
      )}
    </section>
  );
}
