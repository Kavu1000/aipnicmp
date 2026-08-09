import type { AreaDetail } from "./api";
import { areaName } from "./AreaFilter";
import { COLOUR_HEX, formatArea, formatShare, formatSignal, stateInfo } from "./coverage";
import type { Language, Strings } from "./i18n";

/**
 * What the platform knows about the selected area.
 *
 * The filter answers "where"; this answers "and what is the service like
 * there" — which is the only reason to filter in the first place.
 *
 * Three things it is careful about. It reports how much of the area has
 * actually been measured, not just what was found, because a province judged
 * on two roads is a different claim from one judged on forty. It says plainly
 * when nothing has been measured, rather than rendering that as zero coverage.
 * And it withholds the detail — never the finding — when too few separate
 * devices contributed, matching the rule a single hexagon already follows.
 */
interface Props {
  detail: AreaDetail;
  language: Language;
  t: Strings;
  onClear: () => void;
}

export function AreaSummary({ detail, language, t, onClear }: Props) {
  const { area, coverage } = detail;
  const states = stateInfo(t);
  // The server's median state, not the most common one — it is the state the
  // swatch beside it is showing.
  const median = coverage?.state ? states[coverage.state] : null;

  return (
    <section className="area-summary">
      <div className="area-summary-head">
        <div>
          <h2>{areaName(area, language)}</h2>
          <p>
            {t[
              (["areaCountry", "areaProvince", "areaDistrict", "areaVillage"] as const)[area.level]
            ]}
            {area.area_km2 != null && ` · ${formatArea(area.area_km2)}`}
          </p>
        </div>
        <button onClick={onClear} aria-label={t.areaClear}>
          ×
        </button>
      </div>

      {!area.has_boundary && area.radius_m != null && (
        <p className="caveat area-caveat">
          {t.areaApproximate.replace("%R%", `${(area.radius_m / 1000).toFixed(1)} km`)}
        </p>
      )}

      {coverage === null ? (
        <p className="area-empty">{t.areaNotMeasured}</p>
      ) : (
        <>
          <div className="area-headline">
            <span className="swatch large" style={{ background: COLOUR_HEX[coverage.colour] }} />
            <span>
              <strong>{median ? median.label : t.none}</strong>
              <em>{median ? median.remedy : ""}</em>
            </span>
          </div>

          <dl className="area-stats">
            <div>
              <dt>{t.areaGood}</dt>
              <dd className="good">{formatShare(coverage.good_pct)}</dd>
            </div>
            <div>
              <dt>{t.areaUnusable}</dt>
              <dd className="bad">{formatShare(coverage.unusable_pct)}</dd>
            </div>
            <div>
              <dt>{t.areaMeasuredHere}</dt>
              <dd>{formatArea(coverage.measured_area_km2)}</dd>
              {/* How much of the area this rests on. Without it, "12% unusable"
                  reads as a finding about the province rather than about the
                  roads someone happened to drive. */}
              {area.area_km2 ? (
                <span className="sub">
                  {formatShare((coverage.measured_area_km2 / area.area_km2) * 100)}{" "}
                  {t.areaOfArea}
                </span>
              ) : null}
            </div>
            <div>
              <dt>{t.areaDevices}</dt>
              <dd>{coverage.devices.toLocaleString()}</dd>
            </div>
          </dl>

          {coverage.low_confidence ? (
            <p className="area-note">{t.areaLowConfidence}</p>
          ) : (
            <p className="area-note">
              {t.inspectorSignal}: {formatSignal(coverage.avg_rsrp_dbm)} ·{" "}
              {coverage.measurements?.toLocaleString()} {t.statMeasurements.toLowerCase()}
            </p>
          )}
        </>
      )}

      {area.source && <p className="area-source">{t.areaSource.replace("%S%", area.source)}</p>}
    </section>
  );
}
