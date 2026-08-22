import { useCallback, useEffect, useState } from "react";
import { fetchSession, signOut as apiSignOut, type SessionState } from "../api";

export interface SessionHook {
  /** Null until the first /auth/session response lands. */
  session: SessionState | null;
  /** False when the session request never actually reached the server —
   * see the note on `serverReachable` below. */
  reachable: boolean;
  /** Sign-in can be switched off for local development; then everything is
   * permitted and there is no account to show. */
  approved: boolean;
  setSession: (session: SessionState) => void;
  signOut: () => Promise<void>;
}

/** Who is signed in, fetched once and shared by every page in this app. */
export function useSessionState(): SessionHook {
  const [session, setSessionState] = useState<SessionState | null>(null);
  // Whether the session request actually reached the server. False means the
  // API could not be contacted at all, which looks identical to an
  // unconfigured one from here unless it is said out loud.
  const [reachable, setReachable] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetchSession(controller.signal)
      .then((next) => {
        setReachable(true);
        setSessionState(next);
      })
      .catch((cause: unknown) => {
        // StrictMode mounts this effect twice in development, aborting the
        // first fetch on purpose — that abort is not the server being down,
        // and latching `reachable` to false over it would leave the sign-in
        // screen reporting an outage the second, real fetch had already
        // fixed.
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setReachable(false);
        setSessionState({
          auth_enabled: true,
          google_client_id: "",
          authenticated: false,
          approved: false,
          user: null,
        });
      });
    return () => controller.abort();
  }, []);

  const setSession = useCallback((next: SessionState) => setSessionState(next), []);

  const signOut = useCallback(async () => {
    try {
      await apiSignOut();
    } finally {
      window.google?.accounts?.id?.disableAutoSelect?.();
      setSessionState((current) =>
        current ? { ...current, authenticated: false, approved: false, user: null } : current,
      );
    }
  }, []);

  const approved = session !== null && (!session.auth_enabled || session.approved);

  return { session, reachable, approved, setSession, signOut };
}
