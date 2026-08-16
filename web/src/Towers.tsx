import { useEffect, useState } from "react";
import { fetchTowers, type TowerCount } from "./api";
import type { Strings } from "./i18n";

/**
 * Base stations per operator, for the country or the selected area.
 *
 * Three columns rather than one, because they answer different questions and a
 * single "towers" figure would overstate every network. An operator running
 * three sectors on one structure broadcasts three identities: that is three
 * cells and one site, and only the site corresponds to something standing in a
 * field.
 *
 * Everything here counts what the fleet has *heard*. A network with no towers
 * listed has not been shown to lack them — it means nobody has driven within
 * earshot carrying its SIM, which is why the unmeasured operators stay in the
 * table instead of vanishing from it.
 */
export function Towers({ area, t }: { area: string | null; t: Strings }) {
  const [rows, setRows] = useState<TowerCount[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoaded(false);
    fetchTowers(area, controller.signal)
      .then((body) => setRows(body.operators))
      .catch(() => undefined)
      .finally(() => setLoaded(true));
    return () => controller.abort();
  }, [area]);

  if (!loaded && rows.length === 0) return null;

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{t.towersTitle}</h2>
          <p>{t.towersSubtitle}</p>
        </div>
      </header>

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t.towersOperator}</th>
              <th className="num">{t.towersSites}</th>
              <th className="num">{t.towersPlaced}</th>
              <th className="num">{t.towersCells}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.operator} className={row.cells === 0 ? "muted-row" : undefined}>
                <td>
                  <span className="device-name">{row.operator}</span>
                  {row.cells === 0 && (
                    <span className="device-meta">{t.towersNotMeasured}</span>
                  )}
                </td>
                <td className="num good">{row.sites.toLocaleString()}</td>
                <td className="num">{row.cells_placed.toLocaleString()}</td>
                <td className="num">{row.cells.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="towers-note">{t.towersNote}</p>
    </section>
  );
}
