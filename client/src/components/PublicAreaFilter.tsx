import { useEffect, useState } from "react";
import { fetchPublicArea, fetchPublicAreas, type Area } from "../api";
import type { Language, Strings } from "../i18n";

/** Falls back to English rather than an empty row: not every source carries
 * Lao script. */
export function areaName(area: Area, language: Language): string {
  return (language === "lo" && area.name_lo) || area.name_en;
}

/**
 * One dropdown, one level: every province, fetched from `/public/areas`.
 *
 * Not the full Country → Province → District → Village cascade the admin
 * dashboard's AreaFilter offers — that walks the hierarchy one parent at a
 * time, which `/public/areas` cannot answer (it takes a level, not a
 * parent; see backend public.py). Provinces are the useful stop for a
 * visitor orienting themselves on a national map, and "district inside the
 * province I already chose" is a real feature this component does not try
 * to be.
 *
 * Choosing a province flies the map to its bounds rather than locking the
 * query to it — `/public/tiles` takes a viewport, never an area code, so
 * the normal pan/zoom fetch just continues from the new position.
 */
export function PublicAreaFilter({
  t,
  language,
  onSelect,
}: {
  t: Strings;
  language: Language;
  onSelect: (area: Area) => void;
}) {
  const [provinces, setProvinces] = useState<Area[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchPublicAreas(1, controller.signal)
      .then(setProvinces)
      .catch(() => setProvinces([]));
    return () => controller.abort();
  }, []);

  if (provinces.length === 0) return null;

  return (
    <select
      className="select"
      aria-label={t.areaProvince}
      value={selected}
      disabled={busy}
      onChange={(event) => {
        const code = event.target.value;
        setSelected(code);
        if (!code) return;
        setBusy(true);
        fetchPublicArea(code)
          .then((detail) => onSelect(detail.area))
          .catch(() => undefined)
          .finally(() => setBusy(false));
      }}
    >
      <option value="">{t.areaAllProvinces}</option>
      {provinces.map((area) => (
        <option key={area.code} value={area.code}>
          {areaName(area, language)}
        </option>
      ))}
    </select>
  );
}
