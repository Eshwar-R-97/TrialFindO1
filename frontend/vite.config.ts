import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// When running `npm run dev`, the React app lives on http://localhost:5173 and
// proxies API calls + the SSE stream to Flask at http://localhost:5050.
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
    proxy: {
      "/api": {
        target: "http://localhost:5050",
        changeOrigin: true,
        // Featherless can take minutes on large PDFs; default proxy timeouts
        // otherwise yield empty responses and break res.json().
        timeout: 300000,
        proxyTimeout: 300000,
      },
      "/find-trials": {
        target: "http://localhost:5050",
        changeOrigin: true,
      },
      "/find-trials-stream": {
        target: "http://localhost:5050",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
});
