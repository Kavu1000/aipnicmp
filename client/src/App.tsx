import { Navigate, Route, Routes } from "react-router-dom";
import { LoginRoute } from "./auth/LoginRoute";
import { Landing } from "./components/Landing";
import { PublicMap } from "./components/PublicMap";
import { PublicMethod } from "./components/PublicMethod";

/**
 * Every path this app answers — all of them public, signed in or not.
 *
 * There is no gated section here on purpose. This app never calls anything
 * but /api/v1/public/* and /api/v1/auth/* (see src/api.ts's note), so being
 * signed in changes who the header says you are, never what the map shows.
 * The full, per-network, role-gated view lives in the separate admin
 * dashboard app (../web) — see docs/decisions.md for why that boundary is
 * not repeated here.
 */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/map" element={<PublicMap />} />
      <Route path="/method" element={<PublicMethod />} />

      <Route path="/signin" element={<LoginRoute />} />
      <Route path="/pending" element={<LoginRoute />} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
