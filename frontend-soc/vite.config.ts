import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { assetsDir: "bundled" },
  server: {
    host: "0.0.0.0",
    port: 5174,
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
