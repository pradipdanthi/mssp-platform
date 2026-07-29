import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// KB-021: browser calls this origin only (host :3001 → container :5173).
// /api/* is proxied server-side to backend-api on the Compose network.
export default defineConfig({
  plugins: [react()],
  build: {
    assetsDir: "bundled",
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://backend-api:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
