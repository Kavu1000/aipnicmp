import { createContext, useContext, type ReactNode } from "react";
import { useSessionState, type SessionHook } from "./useSession";

const SessionContext = createContext<SessionHook | null>(null);

/** Mounted once, above the router, so every page in this app shares one
 * answer to "who is signed in". */
export function SessionProvider({ children }: { children: ReactNode }) {
  const value = useSessionState();
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionHook {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error("useSession() called outside <SessionProvider>");
  }
  return context;
}
