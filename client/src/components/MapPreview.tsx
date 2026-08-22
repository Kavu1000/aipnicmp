import { useNavigate } from "react-router-dom";
import { MapView, type GeoJsonData } from "../MapView";
import { usePublicTiles } from "./usePublicTiles";
import type { Strings } from "../i18n";

const EMPTY_GEOJSON = { type: "FeatureCollection", features: [] } as unknown as GeoJsonData;

/**
 * The landing page's proof, not its decoration.
 *
 * A live MapView fed by the same /public/tiles a visitor would get at /map —
 * pannable and zoomable for real, because what makes a stranger believe the
 * numbers above it is dragging the map themselves and watching a hexagon
 * move, not a screenshot captioned "live map". Clicking anywhere on it — the
 * map itself, a hexagon, the overlay button — goes to /map, where the same
 * data is the whole page rather than a third of one.
 */
export function MapPreview({ t }: { t: Strings }) {
  const navigate = useNavigate();
  const { tiles, loadTiles } = usePublicTiles();

  return (
    <div className="map-preview">
      {/* No click handler on this wrapper: it holds the live map, and a drag
          that ends over it must pan, never navigate away mid-gesture. Only
          a hexagon click (onSelect below) and the explicit button do. */}
      <div className="map-preview-frame">
        <MapView
          tiles={tiles}
          summary={null}
          basemap="streets"
          flyTo={null}
          terrain={false}
          childAreas={null}
          areaOutline={null}
          fitTo={null}
          collectors={[]}
          cells={EMPTY_GEOJSON}
          collectorLabels={{ collector: "", approximate: "", distanceUnclear: "" }}
          weakAreas={EMPTY_GEOJSON}
          showWeakAreas={false}
          weakLabels={{ rank: "", people: "", shortfall: "", toCell: "", note: "" }}
          imageryLimitLabel={t.imageryLimit}
          cellLabels={{ mast: "", accuracy: "", heardFrom: "", strongest: "", estimate: "" }}
          onBoundsChange={loadTiles}
          onSelect={() => navigate("/map")}
          onAreaSelect={() => undefined}
        />
      </div>
      <button className="map-preview-cta" onClick={() => navigate("/map")}>
        {t.landingViewMap} →
      </button>
    </div>
  );
}
