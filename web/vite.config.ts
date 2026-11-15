import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Im Entwicklungsmodus leitet Vite /api an das lokale Python-Backend weiter.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8600" } },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1200 },
});
