import { useMemo } from "react";
import {
  HEX_CENTRES,
  HEX_RADIUS,
  LAO_OUTLINE,
  LAO_PROVINCES,
  SHAPE_HEIGHT,
  SHAPE_WIDTH,
} from "./laoShape";

/**
 * Lao PDR behind the sign-in card, with a signal sweeping across it.
 *
 * The country is real — the same COD-AB outline the area filter uses. What
 * happens to it is deliberately not: the hexagons carry no measurements and are
 * never coloured by state, because a decorative map dressed in the coverage
 * palette would be indistinguishable from a real reading to anyone glancing at
 * it, and this platform does not show coverage it has not measured. A sweep
 * says "this is a thing that scans the country" without claiming a result.
 *
 * Built to be cheap. The 600-odd hexagons are one `<path>`, not 600 elements,
 * and exactly one thing moves: a gradient band translating behind a mask. That
 * is a single composited layer rather than hundreds of animated nodes, which
 * matters on the phones this platform is aimed at.
 */

/** Width of the travelling band, as a share of the country's width. */
const BAND = 0.45;

function hexPath(): string {
  // Flat-top hexagon, drawn once per centre into a single path.
  const corners = Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 180) * (60 * i);
    return [Math.cos(angle) * HEX_RADIUS, Math.sin(angle) * HEX_RADIUS] as const;
  });

  return HEX_CENTRES.map(([cx, cy]) => {
    const points = corners
      .map(([dx, dy]) => `${(cx + dx).toFixed(1)},${(cy + dy).toFixed(1)}`)
      .join(" L");
    return `M${points} Z`;
  }).join("");
}

export function LoginBackdrop() {
  const hexes = useMemo(hexPath, []);
  const band = SHAPE_WIDTH * BAND;

  return (
    <div className="login-backdrop" aria-hidden="true">
      <svg
        viewBox={`0 0 ${SHAPE_WIDTH} ${SHAPE_HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        role="presentation"
      >
        <defs>
          <mask id="lao-hex-mask">
            <path d={hexes} fill="#ffffff" />
          </mask>

          {/* Soft at both ends so the band has no edge to catch the eye. */}
          <linearGradient id="lao-sweep-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
            <stop offset="50%" stopColor="#ffffff" stopOpacity="1" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* The country itself: a faint mass, its provinces barely suggested. */}
        <path className="backdrop-land" d={LAO_OUTLINE} />
        <g className="backdrop-provinces">
          {LAO_PROVINCES.map((d, index) => (
            <path key={index} d={d} />
          ))}
        </g>

        <g mask="url(#lao-hex-mask)">
          {/* Every hexagon, always, very faintly — the grid the platform
              measures on, at rest. */}
          <rect
            className="backdrop-hexes"
            width={SHAPE_WIDTH}
            height={SHAPE_HEIGHT}
          />
          {/* The one moving thing on the page. */}
          <rect
            className="backdrop-sweep"
            width={band}
            height={SHAPE_HEIGHT}
            fill="url(#lao-sweep-gradient)"
            style={
              {
                "--sweep-from": `${-band}px`,
                "--sweep-to": `${SHAPE_WIDTH + band}px`,
              } as React.CSSProperties
            }
          />
        </g>

        <path className="backdrop-border" d={LAO_OUTLINE} />
      </svg>
    </div>
  );
}
