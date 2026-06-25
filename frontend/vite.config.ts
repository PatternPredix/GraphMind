import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    // Built straight into the backend so FastAPI can serve the SPA.
    outDir: "../backend/static",
    emptyOutDir: true,
  },
});
