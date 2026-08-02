import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The API host is configurable so `make dev` and docker-compose can differ, but
// it always defaults to a backend running on the same laptop. Both the dev
// server and `vite preview` proxy /api so the built bundle needs no rebuild to
// point somewhere else.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "PORTPULSE");
  const proxy = {
    "/api": {
      target: env.PORTPULSE_API || "http://localhost:8000",
      changeOrigin: true,
    },
  };
  return {
    plugins: [react()],
    server: { host: "0.0.0.0", port: 5173, proxy },
    preview: { host: "0.0.0.0", port: 4173, proxy },
  };
});
