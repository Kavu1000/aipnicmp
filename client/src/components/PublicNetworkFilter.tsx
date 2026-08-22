import { useEffect, useState } from "react";
import { fetchPublicNetworks, type Network } from "../api";
import type { Strings } from "../i18n";

/**
 * One of the four Lao networks, or the combined view.
 *
 * Safe to offer publicly since decision 26 (docs/decisions.md): a network's
 * own coverage, exactly as measured, is what `/public/tiles?operator=` now
 * answers with. Networks nobody has measured yet are listed and disabled
 * rather than omitted — "not measured" and "no coverage" are different
 * claims, and leaving a network off the list would quietly make the first
 * one read as the second.
 */
export function PublicNetworkFilter({
  t,
  value,
  onChange,
}: {
  t: Strings;
  value: string | null;
  onChange: (operator: string | null) => void;
}) {
  const [networks, setNetworks] = useState<Network[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    fetchPublicNetworks(controller.signal)
      .then(setNetworks)
      .catch(() => setNetworks([]));
    return () => controller.abort();
  }, []);

  if (networks.length === 0) return null;

  return (
    <select
      className="select"
      aria-label={t.operator}
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value || null)}
    >
      <option value="">{t.allOperators}</option>
      {networks.map((network) => (
        <option key={network.operator} value={network.operator} disabled={!network.measured}>
          {network.measured
            ? network.operator
            : `${network.operator} — ${t.networkUnmeasured}`}
        </option>
      ))}
    </select>
  );
}
