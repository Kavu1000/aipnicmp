import { useEffect, useRef, useState } from "react";
import { LANGUAGE_FLAGS } from "./Flags";
import { LANGUAGE_NAMES, type Language } from "./i18n";

/**
 * The language control, replacing a native `<select>`.
 *
 * A `<select>` can hold text and nothing else, so a flag cannot go inside one.
 * The alternative — flag emoji in the option labels — renders as the bare
 * letters "LA" and "GB" on Windows, which is what the whole pilot runs on.
 *
 * Giving up the native element costs the keyboard behaviour it provided for
 * free, so that is rebuilt here rather than dropped: arrow keys move, Enter and
 * Space choose, Escape closes and returns focus, and the open list is a proper
 * listbox so a screen reader still announces it as one.
 */
export function LanguagePicker({
  language,
  onChange,
  label,
}: {
  language: Language;
  onChange: (next: Language) => void;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const codes = Object.keys(LANGUAGE_NAMES) as Language[];

  // A menu that stays open after the click that should have dismissed it looks
  // broken, and this one sits over a map people drag.
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", dismiss);
    return () => document.removeEventListener("mousedown", dismiss);
  }, [open]);

  const choose = (next: Language) => {
    onChange(next);
    setOpen(false);
  };

  const step = (by: number) => {
    const at = codes.indexOf(language);
    choose(codes[(at + by + codes.length) % codes.length]);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      step(event.key === "ArrowDown" ? 1 : -1);
    }
  };

  const Current = LANGUAGE_FLAGS[language];

  return (
    <div className="language-picker" ref={root} onKeyDown={onKeyDown}>
      <button
        type="button"
        className="select language-button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Current />
        <span className="language-name">{LANGUAGE_NAMES[language]}</span>
        <span className="language-caret" aria-hidden="true" />
      </button>

      {open && (
        <ul className="language-menu" role="listbox" aria-label={label}>
          {codes.map((code) => {
            const Flag = LANGUAGE_FLAGS[code];
            return (
              <li key={code}>
                <button
                  type="button"
                  role="option"
                  aria-selected={code === language}
                  className={code === language ? "language-option chosen" : "language-option"}
                  onClick={() => choose(code)}
                >
                  <Flag />
                  <span className="language-name">{LANGUAGE_NAMES[code]}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
