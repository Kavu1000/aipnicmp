import { useCallback, useMemo, useState } from "react";
import { type Area, type RadioState, type TileProperties } from "../api";
import { MapView, type Basemap, type FitTarget, type GeoJsonData } from "../MapView";
import { Legend } from "../Legend";
import { PublicTileCard } from "./PublicTileCard";
import { PublicHeader } from "./PublicHeader";
import { PublicAreaFilter } from "./PublicAreaFilter";
import { PublicStateFilter } from "./PublicStateFilter";
import { PublicNetworkFilter } from "./PublicNetworkFilter";
import { PreviewBanner } from "./PreviewBanner";
import { StatStrip } from "./StatStrip";
import { usePublicTiles } from "./usePublicTiles";
import { TRANSLATIONS, loadLanguage, saveLanguage, type Language } from "../i18n";

const EMPTY_GEOJSON = { type: "FeatureCollection", features: [] } as unknown as GeoJsonData;

/**
 * The public preview at /map: the same MapView component the signed-in app
 * uses, fed only what /public/* answers — combined-network hexagons and the
 * headline numbers, nothing scoped to one operator and nothing that carries
 * a device count or a moment in time. See docs/decisions.md and
 * backend/app/api/v1/public.py for the line between this and /app/map.
 *
 * The province and signal-state filters are safe because neither adds a new
 * question the server has to answer: a province is a fly-to, not a scoped
 * query (`/public/tiles` takes a viewport, never an area code), and
 * `dominant_state` is already on every tile the viewport fetch returns.
 *
 * The network filter *is* a new question, and answering it publicly was a
 * deliberate reversal — see decision 26 in docs/decisions.md. What stays
 * absent is everything that is not a network's coverage: mast positions,
 * the collector fleet, device counts, the ranked investment list. Those
 * live only behind /app/map's sign-in.
 */
export function PublicMap() {
  const [language, setLanguage] = useState<Language>(loadLanguage);
  const [basemap, setBasemap] = useState<Basemap>("streets");
  const [terrain, setTerrain] = useState(false);
  const [selected, setSelected] = useState<TileProperties | null>(null);
  const [state, setState] = useState<RadioState | null>(null);
  const [operator, setOperator] = useState<string | null>(null);
  const [fitTo, setFitTo] = useState<FitTarget | null>(null);
  const { tiles, error, loadTiles } = usePublicTiles(operator);

  const t = TRANSLATIONS[language];
  const changeLanguage = useCallback((next: Language) => {
    setLanguage(next);
    saveLanguage(next);
    document.documentElement.lang = next;
  }, []);

  // Narrowed to one state, over hexagons the viewport already fetched — see
  // the component note above for why this needs no new server request.
  const shownTiles = useMemo(() => {
    if (!state) return tiles;
    return { ...tiles, features: tiles.features.filter((f) => f.properties.state === state) };
  }, [tiles, state]);

  const flyToProvince = useCallback((area: Area) => {
    setFitTo({ bounds: area.bounds, nonce: Date.now() });
  }, []);

  return (
    <div className="public-shell">
      <PublicHeader t={t} language={language} onLanguageChange={changeLanguage} />
      <PreviewBanner t={t} />
      <StatStrip t={t} />

      <div className="public-toolbar">
        <PublicAreaFilter t={t} language={language} onSelect={flyToProvince} />
        <PublicNetworkFilter t={t} value={operator} onChange={setOperator} />
        <PublicStateFilter t={t} value={state} onChange={setState} />
      </div>

      <main>
        <div className="pane map-shell">
          <div className="map-row">
            <div className="map-area">
              <MapView
                  tiles={shownTiles}
                  summary={null}
                  basemap={basemap}
                  flyTo={null}
                  terrain={terrain}
                  childAreas={null}
                  areaOutline={null}
                  fitTo={fitTo}
                  collectors={[]}
                  cells={EMPTY_GEOJSON}
                  collectorLabels={{ collector: "", approximate: "", distanceUnclear: "" }}
                  weakAreas={EMPTY_GEOJSON}
                  showWeakAreas={false}
                  weakLabels={{ rank: "", people: "", shortfall: "", toCell: "", note: "" }}
                  imageryLimitLabel={t.imageryLimit}
                  cellLabels={{
                    mast: "",
                    accuracy: "",
                    heardFrom: "",
                    strongest: "",
                    estimate: "",
                  }}
                  onBoundsChange={loadTiles}
                  onSelect={setSelected}
                  onAreaSelect={() => undefined}
                />
                <Legend t={t} showOperationalNotes={false} />

                <div className="segmented public-basemap" role="group">
                  <button
                    className={basemap === "streets" ? "on" : ""}
                    onClick={() => setBasemap("streets")}
                  >
                    {t.basemapStreets}
                  </button>
                  <button
                    className={basemap === "satellite" ? "on" : ""}
                    onClick={() => setBasemap("satellite")}
                  >
                    {t.basemapSatellite}
                  </button>
                </div>
                <button
                  className={terrain ? "toggle-3d on public-terrain" : "toggle-3d public-terrain"}
                  onClick={() => setTerrain((on) => !on)}
                  aria-pressed={terrain}
                  title={t.terrainHint}
                >
                  {t.terrain}
                </button>

                {error && <div className="toast error">{error}</div>}
                {!error && shownTiles.features.length === 0 && (
                  <div className="toast">{t.noTilesInView}</div>
                )}
              </div>

              {selected && (
                <aside className="detail-rail">
                  <div className="rail-body">
                    <PublicTileCard tile={selected} t={t} onClose={() => setSelected(null)} />
                  </div>
                </aside>
              )}
            </div>
          </div>
      </main>
    </div>
  );
}
