import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // process.env alone only sees real shell exports — .env/.env.local files
  // need loadEnv, since Vite parses them after this file would otherwise
  // have read process.env.
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    server: {
      port: 5173,
      // The API is proxied so the browser sees one origin in development and the
      // backend needs no CORS exception for the dev server.
      proxy: {
        "/api": {
          target: env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
