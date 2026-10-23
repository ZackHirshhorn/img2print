import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the app on :5173 and forwards /api to `img2print-web` on :8000.
// `npm run build` writes the static files that the Python package serves.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    outDir: "../src/img2print/web/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
});
