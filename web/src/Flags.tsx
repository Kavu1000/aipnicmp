/**
 * Flags as inline SVG, not emoji.
 *
 * Windows ships no glyphs for the regional-indicator pairs that make up flag
 * emoji, so a Lao flag written as an emoji renders there as the two letters
 * "LA" — checked on the machine this dashboard is used from: the codepoints
 * drew 333 monochrome pixels and not one coloured one. Every collector and
 * ministry desktop in the pilot is Windows, so the emoji route would have
 * shipped a language picker with no flags in it for everybody who matters.
 *
 * Drawn to the official constructions rather than by eye, because these are
 * national flags on a government-facing platform and getting one visibly wrong
 * is worse than having none.
 */

interface FlagProps {
  /** Rendered height in pixels; width follows the flag's own ratio. */
  size?: number;
  className?: string;
}

/**
 * Lao PDR: 3:2, red bands a quarter of the height each, blue half, and a white
 * disc whose diameter is four-fifths of the blue band.
 */
export function LaoFlag({ size = 14, className }: FlagProps) {
  return (
    <svg
      viewBox="0 0 60 40"
      height={size}
      width={size * 1.5}
      className={className}
      role="presentation"
      aria-hidden="true"
    >
      <rect width="60" height="40" fill="#CE1126" />
      <rect y="10" width="60" height="20" fill="#002868" />
      <circle cx="30" cy="20" r="8" fill="#FFFFFF" />
    </svg>
  );
}

/**
 * The Union Flag, for English. Simplified: the red saltire is centred on the
 * white one rather than counterchanged, which is invisible at 14px and keeps
 * this to four paths.
 */
export function UnitedKingdomFlag({ size = 14, className }: FlagProps) {
  return (
    <svg
      viewBox="0 0 60 30"
      height={size}
      width={size * 2}
      className={className}
      role="presentation"
      aria-hidden="true"
    >
      <rect width="60" height="30" fill="#012169" />
      <path d="M0,0 L60,30 M60,0 L0,30" stroke="#FFFFFF" strokeWidth="6" />
      <path d="M0,0 L60,30 M60,0 L0,30" stroke="#C8102E" strokeWidth="2" />
      <path d="M30,0 V30 M0,15 H60" stroke="#FFFFFF" strokeWidth="10" />
      <path d="M30,0 V30 M0,15 H60" stroke="#C8102E" strokeWidth="6" />
    </svg>
  );
}

export const LANGUAGE_FLAGS = {
  en: UnitedKingdomFlag,
  lo: LaoFlag,
} as const;


/**
 * The Google "G".
 *
 * Drawn here rather than taken from the rendered sign-in button, because that
 * button is now invisible: it sits over the whole card as the click target, so
 * the only mark left to see is this one. Google's published geometry and its
 * four brand colours, unmodified — the guidelines allow the mark beside your
 * own wording, which is the arrangement this screen uses.
 */
export function GoogleMark({ size = 20 }: { size?: number }) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} role="presentation" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}
