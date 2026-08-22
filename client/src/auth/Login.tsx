import { BrandMark } from "../BrandMark";
import { useEffect, useRef, useState } from "react";
import { signInWithGoogle, type SessionState } from "../api";
import { LoginBackdrop } from "./LoginBackdrop";
import { firebaseConfigured, signInWithGoogleFirebase } from "./firebase";
import { ADVISORS, AFFILIATION, TEAM, personName, personRole } from "../team";
import { avatarUrl, fetchCredits, type CreditedPerson } from "../api";
import type { Language, Strings } from "../i18n";

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

/**
 * Google's mark, drawn here rather than fetched.
 *
 * A remote image on the sign-in page is a request to a third party before
 * anybody has agreed to anything, and one that fails leaves a broken icon on
 * the first screen every visitor sees. Google's brand guidelines require the
 * four-colour mark on a sign-in button, which is what this is.
 */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.33-1.58-5.04-3.71H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.96 10.71a5.4 5.4 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l3-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.96l3 2.33C4.67 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  );
}

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

/**
 * The first letters of a name, for somebody with no portrait stored.
 *
 * A perfectly good portrait, and the only one that never expires. Written to
 * cope with a single-word name and with Lao script, where slicing by character
 * is what the code point boundaries allow.
 */
function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return [...words[0]].slice(0, 2).join("");
  return [...words[0]][0] + [...words[words.length - 1]][0];
}

function Portrait({ person }: { person: CreditedPerson }) {
  const [broken, setBroken] = useState(false);
  if (person.has_avatar && !broken) {
    return (
      <img
        className="credit-avatar"
        src={avatarUrl(person)}
        alt=""
        width={36}
        height={36}
        loading="lazy"
        /* Served from this platform, so this never reaches Google — but a
           stored portrait can still fail, and initials are better than a
           broken-image icon beside somebody's name. */
        onError={() => setBroken(true)}
      />
    );
  }
  return (
    <span className="credit-avatar credit-initials" aria-hidden="true">
      {initialsOf(person.name)}
    </span>
  );
}

function CreditList({ people }: { people: CreditedPerson[] }) {
  return (
    <ul className="credit-list">
      {people.map((person) => (
        <li key={person.id}>
          <Portrait person={person} />
          <span className="credit-text">
            <strong>{person.name}</strong>
            {person.title && <em>{person.title}</em>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The credits, from the accounts a super admin has chosen to publish.
 *
 * Falls back to the static list in team.ts when nobody has been published yet,
 * so a fresh deployment shows the placeholders it always did rather than an
 * empty panel that looks broken. The static file stays the answer for anyone
 * who should be credited without holding an account at all.
 */
function Credits({ t, language }: { t: Strings; language: Language }) {
  const [team, setTeam] = useState<CreditedPerson[] | null>(null);
  const [advisors, setAdvisors] = useState<CreditedPerson[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchCredits(controller.signal)
      .then((body) => {
        setTeam(body.team);
        setAdvisors(body.advisors);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const published = (team?.length ?? 0) + (advisors?.length ?? 0) > 0;

  return (
    <aside className="login-credits">
      <h2>{t.loginTeamTitle}</h2>
      {published ? (
        <CreditList people={team ?? []} />
      ) : (
        <ul>
          {TEAM.map((person, index) => (
            <li key={`${person.name}-${index}`}>
              <strong>{personName(person, language)}</strong>
              {personRole(person, language) && <em>{personRole(person, language)}</em>}
            </li>
          ))}
        </ul>
      )}

      {published
        ? (advisors?.length ?? 0) > 0 && (
            <>
              <h2>{t.loginAdvisorsTitle}</h2>
              <CreditList people={advisors ?? []} />
            </>
          )
        : ADVISORS.length > 0 && (
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

  /**
   * Sign in through Firebase, when this build was given a project.
   *
   * Our own button rather than a rendered one, because nothing here is drawn
   * by anybody else: `signInWithPopup` opens a window this page owns, so the
   * click lands on an ordinary element and the label is ours to translate. The
   * whole apparatus below — the loaded script, the cross-origin frame, the
   * width handed to Google — exists only for the other route.
   */
  const signInThroughFirebase = () => {
    setBusy(true);
    setError(null);
    signInWithGoogleFirebase()
      .then(signInWithGoogle)
      .then(onSignedIn)
      .catch((cause: unknown) => {
        // A closed popup is a decision, not a failure, and saying "sign-in
        // failed" to somebody who changed their mind is noise.
        const code = (cause as { code?: string } | null)?.code ?? "";
        if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") return;
        setError(cause instanceof Error ? cause.message : t.loginFailed);
      })
      .finally(() => setBusy(false));
  };

  useEffect(() => {
    if (awaitingApproval) return;
    // Firebase draws its own button below; loading Google's script here would
    // put two sign-in buttons on the card.
    if (firebaseConfigured) return;
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

        // Google's button, at the size it is actually drawn.
        //
        // It renders inside a cross-origin iframe, so the control the browser
        // dispatches a click to is Google's, not ours, and it is only as big
        // as Google was asked to make it. An icon button stretched with CSS
        // stretches the frame and not the button inside it: the visible pill
        // became entirely dead except for an invisible 40px patch in one
        // corner. Nothing outside that frame can forward a click into it
        // either — the sign-in flow starts from Google's element or not at
        // all.
        //
        // So the width is handed to Google rather than imposed afterwards, and
        // the button is left visible. That gives up the icon variant, whose
        // appeal was that it never shows an account: the standard button is
        // personalised where a Google session exists, rendering "Sign in as
        // <name>" with the address. On a shared desk that is a real cost, and
        // it is the reason the icon was chosen — but a button nobody can press
        // is a worse one.
        const width = Math.round(
          Math.min(Math.max(buttonHost.current.parentElement?.clientWidth ?? 260, 200), 320),
        );
        window.google.accounts.id.renderButton(buttonHost.current, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: "signin_with",
          shape: "pill",
          width,
          // Google draws its own label, so it has to speak the same language
          // as the page around it.
          locale: language,
        });
      })
      .catch(() => setError(t.loginScriptFailed));

    return () => {
      cancelled = true;
    };
  }, [session.google_client_id, awaitingApproval, serverReachable, language, t, onSignedIn]);

  return (
    <div className="login">
      <LoginBackdrop />

      <div className="login-card">
        <header className="login-head">
          <span className="brand-mark" aria-hidden="true">
            <BrandMark />
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
                {firebaseConfigured ? (
                  <div className="login-google">
                    <button
                      type="button"
                      className="login-firebase-button"
                      onClick={signInThroughFirebase}
                      disabled={busy}
                    >
                      <GoogleMark />
                      <span>{t.loginWithGoogle}</span>
                    </button>
                    <span className="login-google-label">{t.loginChooseAccount}</span>
                  </div>
                ) : (
                  session.google_client_id && (
                  <div className="login-google">
                    {/* Google's own button, visible and full size. Our wording
                        goes underneath rather than inside it: text laid over a
                        cross-origin frame cannot be clicked through, and a
                        label that looks like part of a button but is not is
                        exactly what made this unpressable. */}
                    {/* Google's own button, stretched over the whole card and
                        made invisible. It stays the thing that is actually
                        clicked — the sign-in flow only starts from Google's
                        element, and a click forwarded to it from ours does
                        not count. Before this it was a 40px icon inside a
                        238px card, so seven eighths of the button did
                        nothing when pressed. */}
                    <div className="login-button" ref={buttonHost} />
                    <span className="login-google-label">{t.loginChooseAccount}</span>
                  </div>
                  )
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
