import { useCallback, useState } from "react";
import { PublicHeader } from "./PublicHeader";
import { Method } from "../Method";
import { TRANSLATIONS, loadLanguage, saveLanguage, type Language } from "../i18n";

/**
 * The methodology note, public — no data here, only how the map decides what
 * to show, and that is what makes a stranger trust the numbers next to it.
 *
 * Method itself is unchanged from the signed-in app's copy: it takes no
 * session-shaped prop and reads no gated endpoint, so mounting it here needed
 * nothing but the page furniture around it.
 */
export function PublicMethod() {
  const [language, setLanguage] = useState<Language>(loadLanguage);
  const t = TRANSLATIONS[language];

  const changeLanguage = useCallback((next: Language) => {
    setLanguage(next);
    saveLanguage(next);
    document.documentElement.lang = next;
  }, []);

  return (
    <div className="public-shell">
      <PublicHeader t={t} language={language} onLanguageChange={changeLanguage} />
      <main>
        <div className="pane scrollable">
          <div className="page">
            <Method t={t} />
          </div>
        </div>
      </main>
    </div>
  );
}
