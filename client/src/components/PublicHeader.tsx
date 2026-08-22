import { Link, NavLink } from "react-router-dom";
import { BrandMark } from "../BrandMark";
import { LanguagePicker } from "../LanguagePicker";
import { useSession } from "../session/SessionProvider";
import type { Language, Strings } from "../i18n";

/**
 * The sticky top bar every page in this app shares.
 *
 * The account slot on the right reflects who is signed in, never what they
 * can see — every page under this header calls the same public endpoints
 * regardless (see App.tsx's note), so signing in changes this corner and
 * nothing else on screen.
 */
export function PublicHeader({
  t,
  language,
  onLanguageChange,
}: {
  t: Strings;
  language: Language;
  onLanguageChange: (language: Language) => void;
}) {
  const { session, signOut } = useSession();
  const signedIn = session?.authenticated === true;

  return (
    <header className="public-header">
      <Link to="/" className="public-brand">
        <span className="brand-mark" aria-hidden="true">
          <BrandMark />
        </span>
        <span>{t.title}</span>
      </Link>

      <nav className="public-nav">
        <NavLink to="/map" className={({ isActive }) => (isActive ? "on" : "")}>
          {t.navMap}
        </NavLink>
        <NavLink to="/method" className={({ isActive }) => (isActive ? "on" : "")}>
          {t.landingMethodCta}
        </NavLink>
      </nav>

      <div className="public-header-actions">
        <LanguagePicker language={language} onChange={onLanguageChange} label="Language" />
        {signedIn ? (
          <span className="public-account">
            <span className="public-account-name">
              {session.user?.name ?? session.user?.email}
            </span>
            <button className="public-signout" onClick={() => void signOut()}>
              {t.signOut}
            </button>
          </span>
        ) : (
          <Link className="public-signin-button" to="/signin">
            {t.loginTitle}
          </Link>
        )}
      </div>
    </header>
  );
}
