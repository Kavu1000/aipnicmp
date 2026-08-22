import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // process.env alone only sees real shell exports — .env/.env.local files
  // need loadEnv, since Vite parses them after this file would otherwise
  // have read process.env. (This app and ../web hit the same gotcha
  // independently; see web/vite.config.ts's note if this one ever needs the
  // fix repeated.)
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    server: {
      // Different from ../web's 5173 on purpose, so both apps can run at
      // once locally without a port clash.
      port: 5175,
      // The API is proxied so the browser sees one origin in development and
      // the backend needs no CORS exception. Same pattern as ../web/vite.config.ts.
      proxy: {
        "/api": {
          target: env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
