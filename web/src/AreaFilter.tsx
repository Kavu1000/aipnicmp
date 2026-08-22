import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAreas, type Area } from "./api";
import type { Language, Strings } from "./i18n";

/**
 * Country → Province → District → Village, one select per level.
 *
 * Each level lists only the children of the level above, so the control can
 * never offer a district that is not in the chosen province. Choosing "all" at
 * any level selects the level above it, which is what makes "the whole
 * country" and "this whole province" reachable rather than special cases.
 *
 * Renders nothing at all when no boundaries have been imported. The platform
 * is fully usable before anyone loads a boundary file, and an empty selector
 * would be a promise the data cannot keep.
 */

/** Depth 0 is the country, 3 is the village. */
const DEPTHS = [0, 1, 2, 3] as const;

export function areaName(area: Area, language: Language): string {
  // Falls back to English rather than showing an empty row: not every source
  // carries Lao script, and a nameless district is worse than an English one.
  return (language === "lo" && area.name_lo) || area.name_en;
}

interface Props {
  strings: Strings;
  language: Language;
  /** The chosen area, deepest level first selected by the user. */
  onChange: (area: Area | null) => void;
  /** Drives the selects when the map, not the user, changed the selection. */
  selected: Area | null;
}

export function AreaFilter({ strings, language, onChange, selected }: Props) {
  // options[depth] holds the choices at that depth; chain[depth] the selection.
  const [options, setOptions] = useState<Area[][]>([]);
  const [chain, setChain] = useState<(Area | null)[]>([]);
  const [busy, setBusy] = useState(false);

  const labels = [strings.areaCountry, strings.areaProvince, strings.areaDistrict, strings.areaVillage];
  const allLabels = [
    strings.areaAllCountry,
    strings.areaAllProvinces,
    strings.areaAllDistricts,
    strings.areaAllVillages,
  ];

  const expand = useCallback(
    async (area: Area, depth: number, signal?: AbortSignal) => {
      setBusy(true);
      try {
        const children = await fetchAreas(area.code, signal);
        setOptions((current) => {
          const next = current.slice(0, depth + 1);
          if (children.length) next[depth + 1] = children;
          return next;
        });
      } catch {
        // A level that will not load simply does not appear; the levels above
        // it keep working.
        setOptions((current) => current.slice(0, depth + 1));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchAreas(null, controller.signal)
      .then((roots) => {
        setOptions([roots]);
        // One root is the normal case — Lao PDR — and making the user pick it
        // from a list of one would be ceremony.
        if (roots.length === 1) {
          setChain([roots[0]]);
          void expand(roots[0], 0, controller.signal);
        }
      })
      .catch(() => setOptions([]));
    return () => controller.abort();
  }, [expand]);

  /**
   * Follow an external selection — a click on the choropleth — back up the
   * hierarchy so the selects agree with the map.
   */
  const following = useRef<string | null>(null);
  useEffect(() => {
    const code = selected?.code ?? null;
    if (code === following.current) return;
    following.current = code;

    if (selected === null) {
      setChain((current) => current.slice(0, 1));
      return;
    }
    if (chain.some((area) => area?.code === selected.code)) return;

    // The map hands back one area; its ancestors are already in `options`,
    // because the only way to reach it was through them.
    setChain((current) => {
      const next = current.slice(0, selected.level);
      next[selected.level] = selected;
      return next;
    });
    void expand(selected, selected.level);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const choose = (depth: number, code: string) => {
    const area = options[depth]?.find((candidate) => candidate.code === code) ?? null;

    const next = chain.slice(0, depth);
    if (area) next[depth] = area;
    setChain(next);
    setOptions((current) => current.slice(0, depth + 1));

    // Choosing "all" at a depth means the area above it is the selection.
    const effective = area ?? next[depth - 1] ?? null;
    following.current = effective?.code ?? null;
    onChange(effective);

    if (area) void expand(area, depth);
  };

  if (options.length === 0) return null;

  return (
    <div className={busy ? "area-filter busy" : "area-filter"}>
      {DEPTHS.map((depth) => {
        const choices = options[depth];
        if (!choices?.length) return null;
        // With one country there is nothing to choose, so nothing is shown.
        // It named itself — at length, since the boundary data carries the
        // full official form — while never changing and never being
        // selectable, and "All provinces" already means the whole country.
        // A control that cannot be operated is not a control.
        if (depth === 0 && choices.length === 1) return null;
        return (
          <select
            key={depth}
            className="select"
            aria-label={labels[depth]}
            value={chain[depth]?.code ?? ""}
            onChange={(event) => choose(depth, event.target.value)}
          >
            <option value="">{allLabels[depth]}</option>
            {choices.map((area) => (
              <option key={area.code} value={area.code}>
                {areaName(area, language)}
              </option>
            ))}
          </select>
        );
      })}
    </div>
  );
}
