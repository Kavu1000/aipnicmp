import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { PublicHeader } from "./PublicHeader";
import { StatStrip } from "./StatStrip";
import { MapPreview } from "./MapPreview";
import { TRANSLATIONS, loadLanguage, saveLanguage, type Language } from "../i18n";

/**
 * The front door — a judge, a funder, a visitor who followed a link. This
 * whole app has no account of its own, so nothing here waits on a session:
 * every page renders the moment its own data arrives.
 *
 * Ordered by the question a stranger actually asks first ("what is this, and
 * is it real"), not by the order the project is proudest of. See the design
 * note in docs/ for the reasoning behind each section.
 */
export function Landing() {
  const [language, setLanguage] = useState<Language>(loadLanguage);
  const t = TRANSLATIONS[language];

  const changeLanguage = useCallback((next: Language) => {
    setLanguage(next);
    saveLanguage(next);
    document.documentElement.lang = next;
  }, []);

  const steps = [t.landingStep1, t.landingStep2, t.landingStep3, t.landingStep4, t.landingStep5];
  const status = [
    t.landingStatusBackend,
    t.landingStatusAndroid,
    t.landingStatusMl,
    t.landingStatusWeb,
  ];

  return (
    <div className="public-shell landing">
      <PublicHeader t={t} language={language} onLanguageChange={changeLanguage} />

      <div className="landing-scroll">
        <section className="landing-hero">
          <h1>{t.title}</h1>
          <p>{t.tagline}</p>
          <div className="landing-cta-row">
            <Link className="landing-cta-primary" to="/map">
              {t.landingViewMap} →
            </Link>
            <Link className="landing-cta-secondary" to="/method">
              {t.landingMethodCta}
            </Link>
          </div>
        </section>

        <StatStrip t={t} />

        <section className="landing-section landing-map-section">
          <MapPreview t={t} />
        </section>

        <section className="landing-section landing-concept">
          <p>{t.landingConceptBody}</p>
        </section>

        <section className="landing-section landing-steps">
          <h2>{t.landingHowTitle}</h2>
          <ol>
            {steps.map((label, index) => (
              <li key={label}>
                <span className="landing-step-index">{index + 1}</span>
                <span>{label}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-section landing-status">
          <h2>{t.landingStatusTitle}</h2>
          <ul>
            {status.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>

        <footer className="landing-footer">
          <a className="get-app" href="/download/coverage-collector.apk" download>
            {t.getApp}
          </a>
          <Link to="/signin">{t.loginTitle}</Link>
        </footer>
      </div>
    </div>
  );
}
