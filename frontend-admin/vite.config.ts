import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// KB-018: the browser only ever calls this dev server's own origin
// (http://localhost:3000, mapped from container port 5173). Every
// "/api/*" request is forwarded server-side (inside this container, never
// in the browser) to the backend-api Compose service on the shared
// mssp-backend Docker network, with the "/api" prefix stripped before the
// request reaches the backend. This is what lets the frontend call the
// backend with zero backend CORS changes - the browser never makes a
// cross-origin request at all.
export default defineConfig({
  plugins: [react()],
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
