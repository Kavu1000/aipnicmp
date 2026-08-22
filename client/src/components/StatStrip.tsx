import { useEffect, useState } from "react";
import { fetchPublicSummary, type Summary } from "../api";
import { formatAge, formatArea, formatShare } from "../coverage";
import type { Strings } from "../i18n";

/**
 * The headline figures, live from /public/summary — shared by /map and the
 * landing page, so the two can never quote different numbers for the same
 * thing.
 *
 * Renders nothing at all if the fetch fails, rather than a row of zeroes. A
 * stranger has no way to tell "the pilot is this small" from "the server is
 * down"; a blank space at least does not claim to be an answer.
 */
export function StatStrip({ t }: { t: Strings }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchPublicSummary(controller.signal)
      .then(setSummary)
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setFailed(true);
      });
    return () => controller.abort();
  }, []);

  if (failed || !summary) return null;

  return (
    <dl className="metrics stat-strip">
      <div>
        <dt>{t.statMeasurements}</dt>
        <dd>{summary.measurements.toLocaleString()}</dd>
      </div>
      <div>
        <dt>{t.statAreaMapped}</dt>
        <dd>{formatArea(summary.measured_area_km2)}</dd>
        <span className="sub">
          {formatShare(summary.measured_share_pct)} {t.ofCountry}
        </span>
      </div>
      <div className="highlight">
        <dt>{t.statNoService}</dt>
        <dd>{summary.no_service_measurements.toLocaleString()}</dd>
      </div>
      <div>
        <dt>{t.statUpdated}</dt>
        <dd className="small">{formatAge(summary.latest_measurement_at, t.never)}</dd>
      </div>
    </dl>
  );
}
