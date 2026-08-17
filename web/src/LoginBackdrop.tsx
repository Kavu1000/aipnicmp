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

/**
 * A survey route across the country, and the masts along it.
 *
 * Invented, not measured — the shape of a drive rather than a drive. Fixed
 * numbers rather than random ones so the page looks the same on every load and
 * nobody wonders whether it is showing them something.
 *
 * Fractions of the country's box, so the route holds its place whatever the
 * shape is scaled to.
 */
const ROUTE: ReadonlyArray<readonly [number, number]> = [
  [0.30, 0.66], [0.33, 0.63], [0.36, 0.61], [0.39, 0.58], [0.42, 0.56],
  [0.45, 0.53], [0.47, 0.50], [0.50, 0.47], [0.53, 0.45], [0.55, 0.42],
  [0.58, 0.39], [0.60, 0.36], [0.63, 0.33], [0.66, 0.30], [0.69, 0.27],
];

/** Every fourth stop carries a mast, so the broadcasts are spaced. */
const MAST_EVERY = 4;

function routePoints(): Array<readonly [number, number]> {
  return ROUTE.map(([x, y]) => [x * SHAPE_WIDTH, y * SHAPE_HEIGHT] as const);
}

function hexAt(cx: number, cy: number, radius: number): string {
  const corners = Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 180) * (60 * i);
    return `${(cx + Math.cos(angle) * radius).toFixed(1)},${(cy + Math.sin(angle) * radius).toFixed(1)}`;
  });
  return `M${corners.join("L")}Z`;
}

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

  const route = useMemo(routePoints, []);
  const routeHexes = useMemo(
    () => route.map(([x, y]) => hexAt(x, y, HEX_RADIUS * 1.15)).join(""),
    [route],
  );
  const masts = useMemo(
    () => route.filter((_, index) => index % MAST_EVERY === 1),
    [route],
  );

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

        {/*
          A route, its masts, and the broadcast from each.

          Every hexagon here is the same colour. The five coverage colours mean
          five specific things about signal, and a decorative route wearing
          them would be a claim about ground nobody has driven — indistinguishable,
          at a glance, from the map this page signs you in to. What it shows is
          the shape of the work: a survey line, transmitters along it, and each
          one reaching out.
        */}
        <path className="backdrop-route" d={routeHexes} />

        <g className="backdrop-masts">
          {masts.map(([x, y], index) => (
            <g key={`${x}-${y}`}>
              {/* The broadcast. Scaled by transform rather than by animating a
                  radius, so each ring is one composited layer and fifteen of
                  them cost a phone nothing. Staggered, because masts that
                  pulse in unison read as one blinking object rather than
                  several transmitters. */}
              <circle
                className="backdrop-pulse"
                cx={x}
                cy={y}
                r={HEX_RADIUS * 1.6}
                style={{ animationDelay: `${index * 0.9}s` }}
              />
              <circle className="backdrop-mast" cx={x} cy={y} r={HEX_RADIUS * 0.42} />
            </g>
          ))}
        </g>

        <path className="backdrop-border" d={LAO_OUTLINE} />
      </svg>
    </div>
  );
}
