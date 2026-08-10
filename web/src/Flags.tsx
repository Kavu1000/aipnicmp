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
