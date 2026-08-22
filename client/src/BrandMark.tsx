/**
 * The platform's mark: signal arcs over a location pin.
 *
 * The same artwork the collector app carries on its launcher icon, drawn to
 * the same geometry. Before this the platform wore three different marks — a
 * diamond in the sidebar and the sign-in card, a hexagon in the browser tab,
 * and this pin on the phone — so nothing on screen said that the app a
 * collector carries and the map a ministry reads are one system.
 *
 * The pin says where, the arcs say what: a signal, measured at a place. It
 * survives being shrunk because it is two shapes and a silhouette, which is
 * all a 16px favicon has room for.
 *
 * White only, with no background of its own. Every place it appears already
 * sits on the accent red — the chip in the sidebar, the chip on the sign-in
 * card, the favicon tile — and that red is the same #C1121F the Android icon
 * uses.
 */
export function BrandMark({ size = 20 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      role="presentation"
      aria-hidden="true"
      fill="none"
    >
      {/* The pin, at half the scale of the 108dp launcher drawable, so the two
          are the same drawing rather than two drawings that resemble each
          other. */}
      <g transform="translate(-11,-5) scale(0.5)" fill="#FFFFFF">
        <path d="M54,36c-5.5,0 -10,4.5 -10,10c0,7.5 10,20 10,20s10,-12.5 10,-20C64,40.5 59.5,36 54,36zM54,49.5c-1.9,0 -3.5,-1.6 -3.5,-3.5s1.6,-3.5 3.5,-3.5s3.5,1.6 3.5,3.5S55.9,49.5 54,49.5z" />
      </g>

      {/* Arcs drawn at full scale rather than inside the group: scaled with the
          pin their strokes would halve too, and at 16px a 0.9px line
          disappears. */}
      <path
        d="M9,11 A9.5,9.5 0 0 1 23,11"
        stroke="#FFFFFF"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M5.5,7.5 A14.5,14.5 0 0 1 26.5,7.5"
        stroke="#FFFFFF"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  );
}
