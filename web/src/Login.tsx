import { useEffect, useRef, useState } from "react";
import { signInWithGoogle, type SessionState } from "./api";
import { LoginBackdrop } from "./LoginBackdrop";
import { ADVISORS, AFFILIATION, TEAM, personName, personRole } from "./team";
import type { Language, Strings } from "./i18n";

/**
 * The front door.
 *
 * Two states share this screen because they are the same moment from the
 * user's side: "sign in" and "you have, and someone is looking at your
 * request". Sending the second one back to a sign-in button would invite them
 * to try again, which changes nothing and reads as a failure.
 *
 * The credits are not decoration. This is a competition entry and a public
 * institution's work, and the sign-in screen is the one page every visitor
 * sees — including the ones who never get approved.
 */

/** Google Identity Services, loaded on demand rather than bundled. */
const GSI_SRC = "https://accounts.google.com/gsi/client";

interface GoogleIdentity {
  accounts: {
    id: {
      initialize(config: {
        client_id: string;
        callback: (response: { credential: string }) => void;
        auto_select?: boolean;
        cancel_on_tap_outside?: boolean;
      }): void;
      renderButton(parent: HTMLElement, options: Record<string, unknown>): void;
      /** Makes Google forget the last account used in this browser. */
      disableAutoSelect(): void;
    };
  };
}

declare global {
  interface Window {
    google?: GoogleIdentity;
  }
}

function loadGoogleScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();

  const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("google script failed")));
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = GSI_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("google script failed"));
    document.head.appendChild(script);
  });
}

function Credits({ t, language }: { t: Strings; language: Language }) {
  return (
    <aside className="login-credits">
      <h2>{t.loginTeamTitle}</h2>
      <ul>
        {TEAM.map((person, index) => (
          <li key={`${person.name}-${index}`}>
            <strong>{personName(person, language)}</strong>
            {personRole(person, language) && <em>{personRole(person, language)}</em>}
          </li>
        ))}
      </ul>

      {ADVISORS.length > 0 && (
        <>
          <h2>{t.loginAdvisorsTitle}</h2>
          <ul>
            {ADVISORS.map((person, index) => (
              <li key={`${person.name}-${index}`}>
                <strong>{personName(person, language)}</strong>
                {personRole(person, language) && <em>{personRole(person, language)}</em>}
              </li>
            ))}
          </ul>
        </>
      )}

      {AFFILIATION && <p className="login-affiliation">{AFFILIATION}</p>}
    </aside>
  );
}

interface Props {
  session: SessionState;
  t: Strings;
  language: Language;
  onLanguageChange: (language: Language) => void;
  onSignedIn: (session: SessionState) => void;
  onSignOut: () => void;
  languageNames: Record<string, string>;
  /**
   * Whether the session request actually reached the server. False means the
   * API could not be contacted at all, which looks identical to an
   * unconfigured one from here unless it is said out loud.
   */
  serverReachable?: boolean;
}

export function Login({
  session,
  t,
  language,
  onLanguageChange,
  onSignedIn,
  onSignOut,
  languageNames,
  serverReachable = true,
}: Props) {
  const buttonHost = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Signed in, but waiting on a super admin.
  const awaitingApproval = session.authenticated && !session.approved;
  const rejected = session.user?.status === "rejected";

  useEffect(() => {
    if (awaitingApproval) return;
    if (!session.google_client_id) {
      setError(serverReachable ? t.loginNotConfigured : t.loginUnreachable);
      return;
    }

    let cancelled = false;
    loadGoogleScript()
      .then(() => {
        if (cancelled || !buttonHost.current || !window.google) return;
        window.google.accounts.id.initialize({
          client_id: session.google_client_id,
          callback: ({ credential }) => {
            setBusy(true);
            setError(null);
            signInWithGoogle(credential)
              .then(onSignedIn)
              .catch((cause: unknown) =>
                setError(cause instanceof Error ? cause.message : t.loginFailed),
              )
              .finally(() => setBusy(false));
          },
          // Nobody should be signed in silently on a shared machine, and this
          // platform is meant to be used from shared machines.
          auto_select: false,
          cancel_on_tap_outside: true,
        });
        // Any account this browser has used before is forgotten, so Google
        // offers the chooser instead of resuming a session. On a shared
        // machine — which this platform is meant to be usable from — resuming
        // somebody else's is the wrong default.
        window.google.accounts.id.disableAutoSelect();

        // The icon button, not the standard one.
        //
        // Google's standard button is *personalised*: when a Google session
        // exists it renders "Sign in as <name>" with the address underneath,
        // and because the button lives in Google's own iframe there is no
        // setting that turns that off. Two reasons that is wrong here. It puts
        // somebody's address on a screen that is often a projector or a shared
        // desk, and it invites a one-click sign-in as whichever account the
        // browser happens to hold — usually a personal one, when this platform
        // wants the institutional account.
        //
        // The icon variant carries no text at all, so the label beside it is
        // ours and always says the same thing.
        window.google.accounts.id.renderButton(buttonHost.current, {
          type: "icon",
          theme: "outline",
          size: "large",
          shape: "circle",
        });
      })
      .catch(() => setError(t.loginScriptFailed));

    return () => {
      cancelled = true;
    };
  }, [session.google_client_id, awaitingApproval, serverReachable, t, onSignedIn]);

  return (
    <div className="login">
      <LoginBackdrop />

      <div className="login-card">
        <header className="login-head">
          <span className="brand-mark" aria-hidden="true">
            ◆
          </span>
          <div>
            <h1>{t.title}</h1>
            <p>{t.brandSubtitle}</p>
          </div>

          <select
            className="select login-language"
            value={language}
            onChange={(event) => onLanguageChange(event.target.value as Language)}
            aria-label="Language"
          >
            {Object.entries(languageNames).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </header>

        <div className="login-body">
          <section className="login-action">
            {awaitingApproval ? (
              <div className="login-pending">
                <span className="login-pending-mark" aria-hidden="true">
                  {rejected ? "✕" : "⏳"}
                </span>
                <h2>{rejected ? t.loginRejectedTitle : t.loginPendingTitle}</h2>
                <p>{rejected ? t.loginRejectedBody : t.loginPendingBody}</p>
                {session.user && (
                  <p className="login-account">
                    {session.user.picture_url && (
                      <img src={session.user.picture_url} alt="" width={28} height={28} />
                    )}
                    <span>
                      <strong>{session.user.name ?? session.user.email}</strong>
                      <em>{session.user.email}</em>
                    </span>
                  </p>
                )}
                <button className="link" onClick={onSignOut}>
                  {t.loginUseAnother}
                </button>
              </div>
            ) : (
              <>
                <h2>{t.loginTitle}</h2>
                <p className="login-why">{t.loginWhy}</p>

                {/* The label is ours, so it never carries an address. Hidden
                    when Google is unconfigured: an empty button beside an
                    error explaining there is no button would be a puzzle. */}
                {session.google_client_id && (
                  <div className="login-google">
                    <div className="login-button" ref={buttonHost} />
                    <span className="login-google-label">
                      <strong>{t.loginWithGoogle}</strong>
                      <em>{t.loginChooseAccount}</em>
                    </span>
                  </div>
                )}

                {busy && <p className="login-note">{t.loginSigningIn}</p>}
                {error && <p className="login-error">{error}</p>}
                <p className="login-note">{t.loginApprovalNote}</p>
              </>
            )}
          </section>

          <Credits t={t} language={language} />
        </div>
      </div>
    </div>
  );
}
