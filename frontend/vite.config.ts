import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const FLASK = "http://127.0.0.1:5050";

// Shared by dev + preview: `server.proxy` does NOT apply to `vite preview` unless
// duplicated under `preview.proxy` — that caused POST /read-pdf → empty 404.
const flaskProxy: Record<string, object> = {
  "/read-pdf": {
    target: FLASK,
    changeOrigin: true,
    timeout: 300000,
    proxyTimeout: 300000,
  },
  "/patient-profile": {
    target: FLASK,
    changeOrigin: true,
    timeout: 60000,
    proxyTimeout: 60000,
  },
  "/api": {
    target: FLASK,
    changeOrigin: true,
    timeout: 300000,
    proxyTimeout: 300000,
  },
  "/find-trials": { target: FLASK, changeOrigin: true },
  "/find-trials-stream": { target: FLASK, changeOrigin: true },
};

// When running `npm run dev`, the React app lives on http://localhost:5173 and
// proxies API calls + the SSE stream to Flask at http://127.0.0.1:5050 (avoid
// localhost → IPv6 (::1) mismatches if Flask only binds IPv4).
// When running `npm run build`, the static bundle goes to `dist/` and is served
// by Flask directly.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: flaskProxy,
  },
  preview: {
    port: 4173,
    proxy: flaskProxy,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
});
