import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Login } from "./Login";
import { useSession } from "../session/SessionProvider";
import { LANGUAGE_NAMES, TRANSLATIONS, loadLanguage, saveLanguage, type Language } from "../i18n";

/**
 * Mounted at both /signin and /pending — Login already renders one screen or
 * the other from the session it is given (`awaitingApproval`), so the two
 * routes exist for the URL a person lands on, not for two components.
 *
 * Nothing in this app is gated on being signed in — see App.tsx's note — so
 * "signed in" here only ever leads back to the same public pages everyone
 * else sees. Approval is not waited on either: an account pending a super
 * admin's decision still sees exactly the same map an anonymous visitor
 * does, so there is nothing for it to unlock here.
 */
export function LoginRoute() {
  const { session, reachable, setSession, signOut } = useSession();
  const [language, setLanguage] = useState<Language>(loadLanguage);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const t = TRANSLATIONS[language];

  useEffect(() => {
    if (session !== null && session.authenticated) {
      const next = params.get("next");
      navigate(next && next.startsWith("/") ? next : "/map", { replace: true });
    }
  }, [session, params, navigate]);

  const changeLanguage = useCallback((next: Language) => {
    setLanguage(next);
    saveLanguage(next);
    document.documentElement.lang = next;
  }, []);

  if (session === null) {
    return <div className="boot">{t.loading}</div>;
  }

  return (
    <Login
      session={session}
      t={t}
      language={language}
      languageNames={LANGUAGE_NAMES}
      serverReachable={reachable}
      onLanguageChange={changeLanguage}
      onSignedIn={(next) => setSession({ ...session, ...next })}
      onSignOut={signOut}
    />
  );
}
